import uuid
from datetime import datetime
from typing import Annotated, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.database import AsyncSessionLocal, get_db
from app.db.models import ComparisonJob, FileKind, JobStatus, UploadedFile
from app.constants.openai_models import DEFAULT_OPENAI_CHAT_MODEL, OPENAI_CHAT_MODEL_IDS
from app.models.schemas import CreateJobRequest, JobOut, OpenaiModelOptionsOut
from app.services.column_preview import list_columns_from_upload
from app.services.storage_service import StoredBlobMissingError, get_storage
from app.services.job_file_order import file_ids_for_compare
from app.workers.comparison_job import run_comparison_job

router = APIRouter(prefix="/jobs", tags=["jobs"])

_TABULAR = {FileKind.xlsx, FileKind.xls, FileKind.sap}
_ALLOWED_MODELS = frozenset(OPENAI_CHAT_MODEL_IDS)


def _normalize_job_openai_model(raw: Optional[str]) -> Optional[str]:
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    if s not in _ALLOWED_MODELS:
        raise HTTPException(
            status_code=400,
            detail=f"openai_model must be one of: {', '.join(OPENAI_CHAT_MODEL_IDS)}",
        )
    return s


async def _validate_key_fields(body: CreateJobRequest, files: list[UploadedFile]) -> Optional[list[str]]:
    kinds = {f.kind for f in files}
    if kinds <= {FileKind.pdf}:
        return None
    if not kinds.issubset(_TABULAR):
        raise HTTPException(
            status_code=400,
            detail="All files must be the same supported type (Excel, SAP export, or PDF).",
        )
    if len(files) != 2:
        raise HTTPException(
            status_code=400,
            detail="Spreadsheet jobs compare exactly two files: File A (first upload order) vs File B (second).",
        )
    if not body.key_field_names:
        raise HTTPException(
            status_code=400,
            detail="Select at least one key column for Excel or SAP exports (use GET /files/{id}/columns).",
        )
    keys: list[str] = []
    for x in body.key_field_names:
        if isinstance(x, str) and x.strip():
            keys.append(x.strip())
    if not keys:
        raise HTTPException(status_code=400, detail="key_field_names must contain at least one non-empty name")
    if len(keys) != len(set(keys)):
        raise HTTPException(status_code=400, detail="Duplicate key column names are not allowed")

    storage = get_storage()
    for f in files:
        try:
            cols = set(
                await list_columns_from_upload(storage, f.storage_key, f.original_name, f.kind)
            )
        except StoredBlobMissingError as e:
            raise HTTPException(status_code=410, detail=str(e)) from e
        for k in keys:
            if k not in cols:
                raise HTTPException(
                    status_code=400,
                    detail=f"Column {k!r} not found in file {f.original_name!r}",
                )
    return keys


async def _validate_narrative_fields(
    body: CreateJobRequest,
    files: list[UploadedFile],
    keys: Optional[list[str]],
) -> Optional[list[str]]:
    """Columns used in export wording; defaults to key columns when omitted."""
    kinds = {f.kind for f in files}
    if kinds <= {FileKind.pdf}:
        return None
    raw = body.narrative_field_names
    ordered: list[str] = []
    if raw:
        seen: set[str] = set()
        for x in raw:
            if isinstance(x, str) and x.strip():
                k = x.strip()
                if k not in seen:
                    seen.add(k)
                    ordered.append(k)
    if not ordered and keys:
        ordered = list(keys)
    if not ordered:
        raise HTTPException(
            status_code=400,
            detail="Select at least one column for report labels (narrative_field_names), or rely on key columns.",
        )
    storage = get_storage()
    for f in files:
        try:
            cols = set(
                await list_columns_from_upload(storage, f.storage_key, f.original_name, f.kind)
            )
        except StoredBlobMissingError as e:
            raise HTTPException(status_code=410, detail=str(e)) from e
        for name in ordered:
            if name not in cols:
                raise HTTPException(
                    status_code=400,
                    detail=f"Narrative column {name!r} not found in file {f.original_name!r}",
                )
    return ordered


async def _bg_run_job(job_id: uuid.UUID) -> None:
    async with AsyncSessionLocal() as session:
        await run_comparison_job(session, job_id)


@router.get("/openai-model-options", response_model=OpenaiModelOptionsOut)
async def openai_model_options():
    """Public list for the UI dropdown (validated again on POST /jobs)."""
    return OpenaiModelOptionsOut(models=list(OPENAI_CHAT_MODEL_IDS), default=DEFAULT_OPENAI_CHAT_MODEL)


@router.post("", response_model=JobOut)
async def create_job(
    body: CreateJobRequest,
    background_tasks: BackgroundTasks,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    files: list[UploadedFile] = []
    for fid in body.file_ids:
        result = await db.execute(select(UploadedFile).where(UploadedFile.id == fid))
        f = result.scalar_one_or_none()
        if f is None:
            raise HTTPException(status_code=404, detail=f"File {fid} not found")
        files.append(f)

    key_fields = await _validate_key_fields(body, files)
    narrative_fields = await _validate_narrative_fields(body, files, key_fields)
    openai_model = _normalize_job_openai_model(body.openai_model)

    job = ComparisonJob(
        status=JobStatus.pending,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        key_field_names=key_fields,
        narrative_field_names=narrative_fields,
        ordered_file_ids=[str(x) for x in body.file_ids],
        openai_model=openai_model,
    )
    job.files = files
    db.add(job)
    await db.commit()
    await db.refresh(job)

    background_tasks.add_task(_bg_run_job, job.id)

    return JobOut(
        id=job.id,
        status=job.status,
        error_message=job.error_message,
        result_json=job.result_json,
        report_storage_key=job.report_storage_key,
        key_field_names=job.key_field_names,
        narrative_field_names=job.narrative_field_names,
        openai_model=job.openai_model,
        created_at=job.created_at,
        updated_at=job.updated_at,
        file_ids=[f.id for f in files],
    )


def _job_to_out(job: ComparisonJob) -> JobOut:
    return JobOut(
        id=job.id,
        status=job.status,
        error_message=job.error_message,
        result_json=job.result_json,
        report_storage_key=job.report_storage_key,
        key_field_names=job.key_field_names,
        narrative_field_names=job.narrative_field_names,
        openai_model=job.openai_model,
        created_at=job.created_at,
        updated_at=job.updated_at,
        file_ids=file_ids_for_compare(job),
    )


@router.get("/{job_id}", response_model=JobOut)
async def get_job(job_id: uuid.UUID, db: Annotated[AsyncSession, Depends(get_db)]):
    result = await db.execute(
        select(ComparisonJob).options(selectinload(ComparisonJob.files)).where(ComparisonJob.id == job_id)
    )
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return _job_to_out(job)
