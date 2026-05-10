"""Normalize DATABASE_URL and derive asyncpg connect_args (Render + Supabase friendly)."""

from __future__ import annotations

import logging
import os
import re

from sqlalchemy.engine.url import make_url

logger = logging.getLogger(__name__)

# Supabase Session pooler (IPv4-friendly). Region must match your project (dashboard → Database).
_DEFAULT_POOL_REGION = "us-east-1"


def normalize_database_url(url: str) -> str:
    """
    Fix common mistakes from dashboards (typos, wrong scheme).
    Does not log or expose secrets.
    """
    u = (url or "").strip()
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
    region = (os.getenv("SUPABASE_POOL_REGION") or _DEFAULT_POOL_REGION).strip().replace("_", "-")
    if not region:
        region = _DEFAULT_POOL_REGION
    # Dashboard "Connect" shows the exact host (aws-0 vs aws-1, etc.); guessing causes "Tenant or user not found".
    pooler_host = (os.getenv("SUPABASE_POOLER_HOST") or "").strip()
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
