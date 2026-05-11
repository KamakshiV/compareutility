from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import Column, DateTime, Enum, ForeignKey, String, Table, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class FileKind(str, enum.Enum):
    xlsx = "xlsx"
    xls = "xls"
    pdf = "pdf"  # legacy DB rows only; uploads no longer accept PDF
    sap = "sap"  # legacy DB rows only; uploads no longer accept SAP JSON
    unknown = "unknown"


class JobStatus(str, enum.Enum):
    pending = "pending"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"


comparison_job_files = Table(
    "comparison_job_files",
    Base.metadata,
    Column("job_id", UUID(as_uuid=True), ForeignKey("comparison_jobs.id", ondelete="CASCADE"), primary_key=True),
    Column("file_id", UUID(as_uuid=True), ForeignKey("uploaded_files.id", ondelete="CASCADE"), primary_key=True),
)


class UploadedFile(Base):
    __tablename__ = "uploaded_files"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    original_name: Mapped[str] = mapped_column(String(512))
    storage_key: Mapped[str] = mapped_column(String(1024), unique=True)
    kind: Mapped[FileKind] = mapped_column(Enum(FileKind), default=FileKind.unknown)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    jobs: Mapped[list["ComparisonJob"]] = relationship(
        secondary=comparison_job_files, back_populates="files"
    )


class ComparisonJob(Base):
    __tablename__ = "comparison_jobs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    status: Mapped[JobStatus] = mapped_column(Enum(JobStatus), default=JobStatus.pending)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    result_json: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    report_storage_key: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    # Composite business key for Excel reconciliation
    key_field_names: Mapped[Optional[list[str]]] = mapped_column(JSONB, nullable=True)
    # Columns used to phrase export narratives (e.g. document number)
    narrative_field_names: Mapped[Optional[list[str]]] = mapped_column(JSONB, nullable=True)
    # Request order of file_ids (File A first, File B second for spreadsheets). If null (legacy rows),
    # workers fall back to sorting uploads by created_at.
    ordered_file_ids: Mapped[Optional[list[str]]] = mapped_column(JSONB, nullable=True)
    # When USE_LLM_SUMMARY is on, pipeline LLM calls use this model (OpenAI) or deployment name (Azure).
    openai_model: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    files: Mapped[list[UploadedFile]] = relationship(
        secondary=comparison_job_files, back_populates="jobs"
    )
