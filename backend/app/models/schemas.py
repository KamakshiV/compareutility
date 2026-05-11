from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field

from app.db.models import JobStatus


class CreateJobRequest(BaseModel):
    file_ids: list[uuid.UUID] = Field(min_length=2)
    key_field_names: Optional[list[str]] = Field(
        default=None,
        description="Column names that uniquely identify a record (Excel).",
    )
    narrative_field_names: Optional[list[str]] = Field(
        default=None,
        description="Columns used for export wording, e.g. document number (Excel).",
    )
    openai_model: Optional[str] = Field(
        default=None,
        description="OpenAI model id (or Azure deployment name) when USE_LLM_SUMMARY is enabled.",
    )


class UploadedFileOut(BaseModel):
    id: uuid.UUID
    original_name: str
    kind: str
    created_at: datetime

    model_config = {"from_attributes": True}


class JobOut(BaseModel):
    id: uuid.UUID
    status: JobStatus
    error_message: Optional[str]
    result_json: Optional[dict[str, Any]]
    report_storage_key: Optional[str]
    key_field_names: Optional[list[str]]
    narrative_field_names: Optional[list[str]]
    openai_model: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    file_ids: list[uuid.UUID]

    model_config = {"from_attributes": True}


class OpenaiModelOptionsOut(BaseModel):
    """Options for the UI model dropdown (must match server allowlist)."""

    models: list[str]
    default: str


class FileColumnsOut(BaseModel):
    file_id: uuid.UUID
    columns: list[str]
    kind: str
