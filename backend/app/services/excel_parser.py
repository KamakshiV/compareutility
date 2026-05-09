"""Excel ingestion helpers (Polars + openpyxl / xlrd)."""

from __future__ import annotations

from pathlib import Path

import polars as pl


def read_excel_dataframe(path: Path) -> pl.DataFrame:
    if path.suffix.lower() == ".xls":
        return pl.read_excel(path, engine="xlrd")
    return pl.read_excel(path, engine="openpyxl")
