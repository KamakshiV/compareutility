"""Normalize DATABASE_URL and derive asyncpg connect_args (Render + Supabase friendly)."""

from __future__ import annotations

import logging
import os
import re

from sqlalchemy.engine.url import make_url

logger = logging.getLogger(__name__)


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


def connect_args_for_asyncpg(url: str) -> dict:
    """
    Local Docker: no extra SSL (plain Postgres).

    Remote: if the URL already sets ssl / sslmode, do NOT pass ssl=True in connect_args —
    combining both breaks some asyncpg / SQLAlchemy combinations. If the URL has no ssl
    parameter, require TLS with ssl=True.
    """
    low = url.lower()
    if "127.0.0.1" in low or "localhost" in low:
        return {}
    if "ssl=" in low or "sslmode=" in low:
        return {}
    return {"ssl": True}


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
            "Supabase Connect (e.g. port 6543, host …pooler.supabase.com), still as "
            "postgresql+asyncpg://…?ssl=require."
        )
