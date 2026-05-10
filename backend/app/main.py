import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import routes_health, routes_jobs, routes_reports, routes_upload
from app.config import get_settings
from app.db.base import Base
from app.db.database import engine
from app.db import models as db_models  # noqa: F401
from app.db.schema_patches import apply_comparison_job_column_patches


settings = get_settings()

# Ensure pipeline LLM INFO lines appear in Render / uvicorn stderr (child loggers propagate).
logging.getLogger("app.agents").setLevel(logging.INFO)


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Render sets RENDER=true; a missing DATABASE_URL leaves the default local URL and startup will fail.
    if os.environ.get("RENDER") and "DATABASE_URL" not in os.environ:
        raise RuntimeError(
            "DATABASE_URL is not set on Render. Add it under Environment: your Supabase URI as "
            "postgresql+asyncpg://USER:PASSWORD@HOST:5432/postgres?ssl=require "
            "(URL-encode special characters in the password)."
        )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await apply_comparison_job_column_patches(conn)
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
