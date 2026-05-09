from __future__ import annotations

import uuid
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.db.job_repository import get_uploaded_file
from app.db.models import FileKind, UploadedFile
from app.models.schemas import FileColumnsOut, UploadedFileOut
from app.services.column_preview import list_columns_from_upload
from app.services.file_kind import detect_kind
from app.services.storage_service import get_storage

router = APIRouter(prefix="/files", tags=["files"])


@router.post("", response_model=UploadedFileOut)
async def upload_file(
    db: Annotated[AsyncSession, Depends(get_db)],
    file: UploadFile = File(...),
    kind_override: Optional[str] = Form(None),
):
    raw = await file.read()
    suffix = ""
    if file.filename and "." in file.filename:
        suffix = file.filename[file.filename.rfind(".") :]

    storage = get_storage()
    key = await storage.save_bytes(raw, suffix=suffix)

    kind = detect_kind(file.filename or "")
    if kind_override:
        try:
            kind = FileKind(kind_override)
        except ValueError:
            kind = detect_kind(file.filename or "")

    row = UploadedFile(original_name=file.filename or key, storage_key=key, kind=kind)
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


@router.get("/{file_id}", response_model=UploadedFileOut)
async def get_file(file_id: uuid.UUID, db: Annotated[AsyncSession, Depends(get_db)]):
    row = await get_uploaded_file(db, file_id)
    if row is None:
        raise HTTPException(status_code=404, detail="File not found")
    return row


@router.get("/{file_id}/columns", response_model=FileColumnsOut)
async def get_file_columns(file_id: uuid.UUID, db: Annotated[AsyncSession, Depends(get_db)]):
    """Header columns for Excel / SAP exports (for choosing record keys before running a job)."""
    row = await get_uploaded_file(db, file_id)
    if row is None:
        raise HTTPException(status_code=404, detail="File not found")
    if row.kind == FileKind.pdf:
        raise HTTPException(status_code=400, detail="PDF uploads have no tabular column headers")
    if row.kind == FileKind.unknown:
        raise HTTPException(status_code=400, detail="Cannot detect columns for unknown file kind")
    storage = get_storage()
    try:
        cols = await list_columns_from_upload(storage, row.storage_key, row.original_name, row.kind)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return FileColumnsOut(file_id=row.id, columns=cols, kind=row.kind.value)
