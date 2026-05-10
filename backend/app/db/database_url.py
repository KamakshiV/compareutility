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
    pooler_host = f"aws-0-{region}.pooler.supabase.com"

    user = u.username or "postgres"
    if user == "postgres":
        new_user = f"postgres.{project_ref}"
    else:
        new_user = user

    try:
        new_u = u.set(host=pooler_host, port=5432, username=new_user)
    except Exception:
        return url

    logger.info(
        "Rewrote Supabase DATABASE_URL to Session pooler at %s:5432 (region %s, Render IPv4). "
        "If this fails, set SUPABASE_POOL_REGION to match Supabase → Database → Region; "
        "SUPABASE_POOLER_DISABLE=1 restores direct db.*:5432.",
        pooler_host,
        region,
    )
    return new_u.render_as_string(hide_password=False)


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
    if "ssl=" in low or "sslmode=" in low:
        return args
    args["ssl"] = True
    return args


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
