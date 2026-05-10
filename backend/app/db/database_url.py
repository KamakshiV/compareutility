"""Normalize DATABASE_URL and derive asyncpg connect_args (Render + Supabase friendly)."""

from __future__ import annotations

import logging
import os
import re
import socket

from sqlalchemy.engine.url import make_url

logger = logging.getLogger(__name__)

# Supabase Session pooler (IPv4-friendly). Region must match your project (dashboard → Database).
_DEFAULT_POOL_REGION = "us-east-1"


def sanitize_pool_region(raw: str | None) -> str:
    """
    Pooler hostname is ``aws-0-<region>.pooler.supabase.com``. Region must look like ``us-east-1``;
    dashboard labels like "East US" or typos cause DNS failures (gaierror -2).
    """
    r = (raw or _DEFAULT_POOL_REGION).strip().lower().replace("_", "-")
    if re.fullmatch(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*", r or ""):
        return r
    if (raw or "").strip():
        logger.warning(
            "SUPABASE_POOL_REGION=%r is not a valid AWS-style region slug; using %s instead.",
            raw,
            _DEFAULT_POOL_REGION,
        )
    return _DEFAULT_POOL_REGION


def sanitize_pooler_host(raw: str) -> str:
    """Strip common copy/paste mistakes from SUPABASE_POOLER_HOST (scheme, path, port, quotes)."""
    h = (raw or "").strip().strip('"').strip("'")
    for prefix in ("https://", "http://"):
        if h.lower().startswith(prefix):
            h = h[len(prefix) :]
    h = h.strip().split("/")[0].strip()
    if ":" in h and not h.startswith("["):
        # "host:5432" from dashboard; not IPv6
        parts = h.rsplit(":", 1)
        if len(parts) == 2 and parts[1].isdigit():
            h = parts[0].strip()
    return h.strip()


def normalize_database_url(url: str) -> str:
    """
    Fix common mistakes from dashboards (typos, wrong scheme).
    Does not log or expose secrets.
    """
    u = (url or "").strip()
    if len(u) >= 2 and u[0] == u[-1] and u[0] in "'\"":
        u = u[1:-1].strip()
    if not u:
        return u
    # Supabase / docs typo
    u = re.sub(r"ssl\s*=\s*required\b", "ssl=require", u, flags=re.IGNORECASE)
    # Ensure async driver for SQLAlchemy asyncio engine
    if u.startswith("postgres://"):
        u = "postgresql+asyncpg://" + u[len("postgres://") :]
    elif u.startswith("postgresql://") and not u.startswith("postgresql+asyncpg://"):
        u = "postgresql+asyncpg://" + u[len("postgresql://") :]
    return u


def rewrite_supabase_direct_to_session_pooler_on_render(url: str) -> str:
    """
    Render is often IPv4-only; Supabase *direct* host ``db.<ref>.supabase.co:5432`` is frequently
    IPv6-only, so connections hang or fail. Supavisor Session pooler (pooler host, port 5432) is IPv4-compatible.

    Opt out: ``SUPABASE_POOLER_DISABLE=1``. Set region if not us-east-1: ``SUPABASE_POOL_REGION``.
    """
    if not os.environ.get("RENDER"):
        return url
    if os.environ.get("SUPABASE_POOLER_DISABLE", "").strip().lower() in ("1", "true", "yes"):
        return url
    try:
        u = make_url(url)
    except Exception:
        return url
    host = (u.host or "").lower()
    m = re.fullmatch(r"db\.([a-z0-9]+)\.supabase\.co", host)
    if not m:
        return url
    port = u.port or 5432
    if port != 5432:
        return url

    project_ref = m.group(1)
    region = sanitize_pool_region(os.getenv("SUPABASE_POOL_REGION"))
    # Dashboard "Connect" shows the exact host (aws-0 vs aws-1, etc.); guessing causes "Tenant or user not found".
    pooler_host = sanitize_pooler_host(os.getenv("SUPABASE_POOLER_HOST") or "")
    if not pooler_host:
        pooler_host = f"aws-0-{region}.pooler.supabase.com"
    try:
        pool_port = int((os.getenv("SUPABASE_POOLER_PORT") or "5432").strip() or "5432")
    except ValueError:
        pool_port = 5432

    user = u.username or "postgres"
    if user == "postgres":
        new_user = f"postgres.{project_ref}"
    else:
        new_user = user

    try:
        new_u = u.set(host=pooler_host, port=pool_port, username=new_user)
    except Exception:
        return url

    logger.info(
        "Rewrote Supabase DATABASE_URL to pooler host %s:%s (user %s). "
        "If you see 'Tenant or user not found', set SUPABASE_POOLER_HOST to the exact host from "
        "Supabase → Connect → Session pooler (may be aws-1-… not aws-0-…). "
        "SUPABASE_POOLER_PORT if your string uses 6543. SUPABASE_POOLER_DISABLE=1 restores direct.",
        pooler_host,
        pool_port,
        new_user,
    )
    return new_u.render_as_string(hide_password=False)


def align_supabase_pooler_username(url: str) -> str:
    """
    Supavisor Session pooler expects ``postgres.<project-ref>``, not bare ``postgres``.
    If ``DATABASE_URL`` already points at ``*.pooler.supabase.com`` with user ``postgres``,
    set env ``SUPABASE_PROJECT_REF`` (same id as in ``db.<id>.supabase.co``) so we can fix it.
    """
    ref = (os.getenv("SUPABASE_PROJECT_REF") or os.getenv("SUPABASE_PROJECT_ID") or "").strip()
    try:
        u = make_url(url)
    except Exception:
        return url
    host = (u.host or "").lower()
    if not host.endswith(".pooler.supabase.com"):
        return url
    user = (u.username or "").strip()
    if user.startswith("postgres.") and len(user) > len("postgres."):
        return url
    if user not in ("postgres", ""):
        return url
    if not ref:
        if os.environ.get("RENDER"):
            logger.warning(
                "DATABASE_URL uses pooler host with user 'postgres'. "
                "Add SUPABASE_PROJECT_REF=<your project ref> (from db.<ref>.supabase.co) or use user postgres.<ref> in the URL."
            )
        return url
    try:
        new_u = u.set(username=f"postgres.{ref}")
        logger.info("Adjusted pooler DATABASE_URL username using SUPABASE_PROJECT_REF.")
        return new_u.render_as_string(hide_password=False)
    except Exception:
        return url


def connect_args_for_asyncpg(url: str) -> dict:
    """
    Local Docker: no extra SSL (plain Postgres).

    Remote: if the URL already sets ssl / sslmode, do NOT pass ssl=True in connect_args —
    combining both breaks some asyncpg / SQLAlchemy combinations. If the URL has no ssl
    parameter, require TLS with ssl=True.

    Always set a connect ``timeout`` on remote hosts so misconfigured IPv6 / firewall fails fast.
    """
    low = url.lower()
    local = "127.0.0.1" in low or "localhost" in low
    try:
        connect_timeout = float(os.getenv("DATABASE_CONNECT_TIMEOUT", "25"))
    except ValueError:
        connect_timeout = 25.0

    if local:
        return {}

    args: dict = {"timeout": connect_timeout}
    # Transaction pooler / PgBouncer-style: disable prepared statement cache for asyncpg.
    try:
        pu = make_url(url)
        ph = (pu.host or "").lower()
        pport = pu.port or 5432
        if ph.endswith(".pooler.supabase.com") and pport == 6543:
            args["statement_cache_size"] = 0
    except Exception:
        pass
    if "ssl=" in low or "sslmode=" in low:
        return args
    args["ssl"] = True
    return args


def validate_database_url_dns_on_render(url: str) -> None:
    """
    Fail fast on Render with a clear message when the DB hostname does not resolve (gaierror -2),
    or when the URL parsed to a bogus host (often unescaped ``@`` / ``:`` in the password).
    """
    if not os.environ.get("RENDER"):
        return
    if os.getenv("SKIP_DATABASE_DNS_CHECK", "").strip().lower() in ("1", "true", "yes"):
        logger.warning("SKIP_DATABASE_DNS_CHECK is set; skipping DNS validation for DATABASE_URL.")
        return
    low = url.lower()
    if "127.0.0.1" in low or "localhost" in low:
        return
    try:
        u = make_url(url)
    except Exception as exc:
        raise ValueError(
            "DATABASE_URL is not a valid SQLAlchemy URL (check special characters: password must be "
            "URL-encoded, e.g. @ as %40, : as %3A, $ as %24)."
        ) from exc
    host = (u.host or "").strip()
    if not host:
        raise ValueError(
            "DATABASE_URL has an empty hostname after parsing. This usually means the password "
            "contains @ or : without URL-encoding, which splits the URL in the wrong place."
        )
    if any(c in host for c in " \t\n\r@") or ".." in host:
        raise ValueError(
            f"DATABASE_URL hostname looks invalid ({host!r}). Check SUPABASE_POOLER_HOST for typos, "
            "quotes, or newlines; fix password encoding if host contains '@'."
        )
    port = int(u.port or 5432)
    try:
        socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        msg = (
            f"Database hostname does not resolve in DNS: {host!r} (port {port}). "
            "Remove or fix SUPABASE_POOLER_HOST; set SUPABASE_POOL_REGION to a slug like us-east-1 "
            "(not a display name); or paste the full Session pooler URI from Supabase → Connect as "
            "DATABASE_URL and set SUPABASE_POOLER_DISABLE=1. Password must be URL-encoded (@ as %40). "
            f"(getaddrinfo error: {exc!s})"
        )
        logger.error(msg)
        raise ValueError(msg) from None


def log_effective_db_target(url: str) -> None:
    """On Render, log host/port/db user (no password) to debug pooler / tenant issues."""
    if not os.environ.get("RENDER"):
        return
    try:
        pu = make_url(url)
        logger.info(
            "Effective DATABASE_URL target: host=%s port=%s database=%s username=%s",
            pu.host,
            pu.port or 5432,
            pu.database,
            pu.username or "",
        )
    except Exception:
        pass


def log_supabase_pooler_hint_if_render(url: str) -> None:
    """Direct db.*.supabase.co:5432 is often IPv6-only; Render is IPv4-heavy."""
    if not os.environ.get("RENDER"):
        return
    try:
        u = make_url(url)
    except Exception:
        return
    host = (u.host or "").lower()
    port = u.port or 5432
    if host.startswith("db.") and host.endswith(".supabase.co") and port == 5432:
        logger.warning(
            "DATABASE_URL uses Supabase direct host db.*.port 5432 — often IPv6-only. "
            "If connections fail or hang from Render, switch to the Session pooler URI in "
            "Supabase Connect → Session pooler (host …pooler.supabase.com:5432), still as "
            "postgresql+asyncpg://…?ssl=require."
        )
