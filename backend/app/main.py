import logging
import os
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import routes_health, routes_jobs, routes_reports, routes_upload
from app.config import get_settings
from app.db.base import Base
from app.db.database import engine
from app.db.database_url import normalize_database_url
from app.db import models as db_models  # noqa: F401
from app.db.schema_patches import apply_comparison_job_column_patches


settings = get_settings()

# Ensure pipeline LLM INFO lines appear in Render / uvicorn stderr (child loggers propagate).
logging.getLogger("app.agents").setLevel(logging.INFO)


def _render_database_url_problem() -> Optional[str]:
    """Return an error message if DB URL is missing or still local-dev on Render."""
    if not os.environ.get("RENDER"):
        return None
    raw = (os.environ.get("DATABASE_URL") or "").strip()
    if not raw:
        return (
            "DATABASE_URL is not set. In the Render dashboard: Web Service → Environment → "
            "add variable DATABASE_URL (exact name, case-sensitive). Value: Supabase URI as "
            "postgresql+asyncpg://USER:PASSWORD@db.PROJECT.supabase.co:5432/postgres?ssl=require "
            "(URL-encode special characters in the password). Save, then redeploy."
        )
    if "127.0.0.1:5433" in raw or "localhost:5433" in raw:
        return (
            "DATABASE_URL still points to local Docker Postgres (port 5433). On Render, replace it "
            "with your Supabase connection string (postgresql+asyncpg://…?ssl=require)."
        )
    effective = normalize_database_url(raw)
    if effective.startswith("postgresql://") and "+asyncpg" not in effective.split("://", 1)[0]:
        return (
            "DATABASE_URL must use the async driver prefix postgresql+asyncpg:// (not postgresql:// alone). "
            "Example: postgresql+asyncpg://postgres:PASSWORD@db.xxx.supabase.co:5432/postgres?ssl=require"
        )
    return None


@asynccontextmanager
async def lifespan(_: FastAPI):
    log = logging.getLogger(__name__)
    # Runs only after a successful image/build when the web process starts (not during `pip install`).
    log.info("Startup: FastAPI lifespan running — next step is database connect + schema.")
    msg = _render_database_url_problem()
    if msg:
        raise RuntimeError(msg)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await apply_comparison_job_column_patches(conn)
        log.info("Database schema ready (create_all + patches applied).")
    except Exception as exc:
        log.error("Database startup failed — %s: %s", type(exc).__name__, exc)
        log.exception(
            "Context: postgresql+asyncpg://, URL-encoded password, ?ssl=require. "
            "If error mentions tenant/user: copy Session pooler host from Supabase → Connect into "
            "SUPABASE_POOLER_HOST (not always aws-0-…), set SUPABASE_POOLER_PORT if needed, or paste the full pooler "
            "DATABASE_URL and set SUPABASE_POOLER_DISABLE=1 only if using direct with IPv6/IPv4 add-on. "
            "SUPABASE_PROJECT_REF helps bare pooler user 'postgres'."
        )
        raise
    yield
    await engine.dispose()


app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_list(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(routes_health.router)
app.include_router(routes_upload.router)
app.include_router(routes_jobs.router)
app.include_router(routes_reports.router)


@app.get("/")
async def root():
    return {"service": settings.app_name, "docs": "/docs"}
