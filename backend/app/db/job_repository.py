"""Persistence helpers for comparison jobs (metadata DB)."""

from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import ComparisonJob, UploadedFile


async def get_uploaded_file(db: AsyncSession, file_id: uuid.UUID) -> Optional[UploadedFile]:
    result = await db.execute(select(UploadedFile).where(UploadedFile.id == file_id))
    return result.scalar_one_or_none()


async def get_job_with_files(db: AsyncSession, job_id: uuid.UUID) -> Optional[ComparisonJob]:
    result = await db.execute(
        select(ComparisonJob).options(selectinload(ComparisonJob.files)).where(ComparisonJob.id == job_id)
    )
    return result.scalar_one_or_none()


async def get_job(db: AsyncSession, job_id: uuid.UUID) -> Optional[ComparisonJob]:
    result = await db.execute(select(ComparisonJob).where(ComparisonJob.id == job_id))
    return result.scalar_one_or_none()
