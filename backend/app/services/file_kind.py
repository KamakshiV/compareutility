from pathlib import Path

from app.db.models import FileKind


def detect_kind(filename: str) -> FileKind:
    ext = Path(filename).suffix.lower()
    if ext in (".xlsx", ".xlsm"):
        return FileKind.xlsx
    if ext == ".xls":
        return FileKind.xls
    return FileKind.unknown
