"""Detect header / column names from uploaded tabular files."""

from __future__ import annotations

import json
import tempfile
import uuid
from pathlib import Path

from app.db.models import FileKind
from app.services.excel_parser import read_excel_column_names, read_excel_dataframe


def list_columns_from_path(path: Path, kind: FileKind) -> list[str]:
    if kind in (FileKind.xlsx, FileKind.xls):
        if kind == FileKind.xlsx and path.suffix.lower() in (".xlsx", ".xlsm"):
            return read_excel_column_names(path)
        if kind == FileKind.xls:
            return [str(c) for c in read_excel_dataframe(path).columns]
        return read_excel_column_names(path)
    if kind == FileKind.sap:
        data = json.loads(path.read_text(encoding="utf-8"))
        cols = data.get("columns")
        if not isinstance(cols, list):
            raise ValueError("SAP export JSON must contain a 'columns' array")
        return [str(c) for c in cols]
    raise ValueError(f"No tabular columns for file kind: {kind.value}")


async def list_columns_from_upload(storage, storage_key: str, original_name: str, kind: FileKind) -> list[str]:
    raw = await storage.read_bytes(storage_key)
    suffix = Path(original_name).suffix or ".bin"
    tmp = Path(tempfile.gettempdir()) / f"reconiq-cols-{uuid.uuid4().hex}{suffix}"
    try:
        tmp.write_bytes(raw)
        return list_columns_from_path(tmp, kind)
    finally:
        if tmp.exists():
            tmp.unlink(missing_ok=True)
