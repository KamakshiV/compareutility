"""Deterministic reconciliation: Excel workbooks (File A → File B)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from app.db.models import FileKind
from app.services.excel_compare import compare_excel_files


def run_reconciliation(
    local_paths: list[Path],
    kinds: list[FileKind],
    key_field_names: Optional[list[str]] = None,
    narrative_field_names: Optional[list[str]] = None,
) -> dict[str, Any]:
    if len(local_paths) < 2:
        return {"error": "At least two files required"}

    dominant = kinds[0]
    if not all(k == dominant for k in kinds):
        return {
            "error": "All files in a job must be the same kind for this POC",
            "kinds": [k.value for k in kinds],
        }

    if dominant in (FileKind.xlsx, FileKind.xls):
        return compare_excel_files(local_paths, key_field_names, narrative_field_names)

    return {"error": f"Only Excel (.xlsx, .xls) is supported; got: {dominant.value}"}
