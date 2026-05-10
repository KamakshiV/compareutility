"""Idempotent DDL for POC: SQLAlchemy create_all() does not add new columns to existing tables."""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection


async def apply_comparison_job_column_patches(conn: AsyncConnection) -> None:
    await conn.execute(
        text("ALTER TABLE comparison_jobs ADD COLUMN IF NOT EXISTS key_field_names JSONB")
    )
    await conn.execute(
        text("ALTER TABLE comparison_jobs ADD COLUMN IF NOT EXISTS narrative_field_names JSONB")
    )
    await conn.execute(
        text("ALTER TABLE comparison_jobs ADD COLUMN IF NOT EXISTS ordered_file_ids JSONB")
    )
