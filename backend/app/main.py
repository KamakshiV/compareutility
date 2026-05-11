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
        if os.environ.get("RENDER") and not settings.azure_storage_connection_string:
            log.warning(
                "Render: AZURE_STORAGE_CONNECTION_STRING is unset — file uploads use local disk "
                "(STORAGE_LOCAL_PATH) and do not survive redeploys; DB rows may reference missing files. "
                "Set AZURE_STORAGE_CONNECTION_STRING + AZURE_CONTAINER_NAME for durable storage."
            )
    except Exception as exc:
        ename = type(exc).__name__
        em = str(exc).lower()
        if "InvalidPassword" in ename or "password authentication failed" in em:
            log.exception(
                "Database startup failed (%s): Postgres rejected the password or role. "
                "Paste DATABASE_URL from Supabase → Connect → Session pooler as postgresql+asyncpg://… "
                "(user must be postgres.<project-ref>, not bare postgres). URL-encode the password in the URL "
                "($ → %%24, @ → %%40, : → %%3A, # → %%23). If you reset the DB password in Supabase, update Render.",
                ename,
            )
        else:
            log.exception(
                "Database startup failed (%s). Pooler/DNS: SUPABASE_POOLER_HOST, SUPABASE_POOL_REGION, "
                "SUPABASE_PROJECT_REF, SUPABASE_POOLER_DISABLE. SSL: on Render, unset DATABASE_SSL_VERIFY uses "
                "encrypted-without-verify for Supabase; set DATABASE_SSL_VERIFY=true to force cert verify.",
                ename,
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
