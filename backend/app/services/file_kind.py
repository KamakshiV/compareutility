from pathlib import Path

from app.db.models import FileKind


def detect_kind(filename: str) -> FileKind:
    ext = Path(filename).suffix.lower()
    if ext in (".xlsx", ".xlsm"):
        return FileKind.xlsx
    if ext == ".xls":
        return FileKind.xls
    if ext == ".pdf":
        return FileKind.pdf
    if ext == ".json" and "sap" in filename.lower():
        return FileKind.sap
    return FileKind.unknown
