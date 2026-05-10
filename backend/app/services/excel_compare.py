"""Excel comparison: File A (first file) → File B (second), key-based, one-way."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional
import logging
import polars as pl

from app.services.excel_parser import read_excel_dataframe
from app.services.export_tabular import MAX_EXPORT_ROWS, make_export, single_row_export
from app.services.key_fields import coerce_key_fields, normalize_narrative_columns
from app.services.tabular_pdf_sections import (
    build_tabular_pdf_report,
    compute_value_mismatch_analysis,
    row_key_tuple,
)


def _cell_value(v: Any) -> Any:
    if v is None:
        return ""
    if hasattr(v, "isoformat"):
        return str(v)
    return v


def _row_values_for_key(
    source: pl.DataFrame,
    cols: list[str],
    key_cols: list[str],
    kt: tuple[str, ...],
) -> list[Any]:
    for d in source.to_dicts():
        if row_key_tuple(d, key_cols) == kt:
            return [_cell_value(d.get(c)) for c in cols]
    return [""] * len(cols)


def _append_data_rows(
    rows_out: list[list[Any]],
    df: pl.DataFrame,
    cols: list[str],
    issue_val: str,
    category: str,
    discrepancy: str,
    budget: int,
) -> int:
    n = 0
    for d in df.head(budget).to_dicts():
        if len(rows_out) >= MAX_EXPORT_ROWS:
            break
        rows_out.append([issue_val, category, discrepancy] + [_cell_value(d.get(c)) for c in cols])
        n += 1
    return n


def compare_excel_files(
    paths: list[Path],
    key_field_names: Optional[list[str]] = None,
    narrative_field_names: Optional[list[str]] = None,
) -> dict[str, Any]:
    logging.info("Comparing Excel files (File A → File B)")
    if len(paths) < 2:
        return {"error": "Need at least two Excel files"}

    paths_eff = paths[:2]
    da = read_excel_dataframe(paths_eff[0])
    db = read_excel_dataframe(paths_eff[1])
    first_cols = list(da.columns)
    keys, key_err = coerce_key_fields(key_field_names, first_cols)
    if key_err:
        return {"error": key_err}

    narrative_cols = normalize_narrative_columns(narrative_field_names, keys, first_cols)

    pair_label = f"{paths_eff[0].name} vs {paths_eff[1].name}"
    logging.info("Building Excel comparison summary for %s", pair_label)

    summary: dict[str, Any] = {
        "type": "excel",
        "sheets_mode": "first_sheet_only",
        "comparison_mode": "file_a_to_file_b",
        "file_a": paths_eff[0].name,
        "file_b": paths_eff[1].name,
        "pair_label": pair_label,
        "key_field_names": keys,
        "narrative_field_names": narrative_cols,
        "row_counts": {"file_a": len(da), "file_b": len(db)},
    }
    if len(paths) > 2:
        summary["files_ignored_note"] = (
            f"Only the first two workbooks are compared ({summary['file_a']} → {summary['file_b']}); "
            f"{len(paths) - 2} additional file(s) were ignored."
        )

    cols = list(da.columns)
    b_key_index = db.select(keys).unique()
    missing_in_b = da.join(b_key_index, on=keys, how="anti")
    vm = compute_value_mismatch_analysis(da, db, keys, narrative_cols)

    summary["diff_sample"] = {
        "keys_in_file_a_not_file_b": len(missing_in_b),
        "value_mismatch_records_1_1": len(vm.by_record),
        "sample_missing_in_b": missing_in_b.head(5).to_dicts() if len(missing_in_b) else [],
    }
    logging.info("Build PDF Report")
    pdf_report = build_tabular_pdf_report(
        paths_eff[0].name,
        paths_eff[1].name,
        da,
        db,
        missing_in_b,
        keys,
        narrative_cols,
        vm_analysis=vm,
    )

    export_rows: list[list[Any]] = []
    truncated = False

    disc_miss = (
        f"File A row («{pair_label}»): this record’s key does not appear in File B."
    )
    remaining = MAX_EXPORT_ROWS - len(export_rows)
    if remaining > 0:
        used = _append_data_rows(
            export_rows,
            missing_in_b,
            cols,
            "Yes",
            "Missing in File B",
            disc_miss,
            remaining,
        )
        if used < len(missing_in_b):
            truncated = True

    cat_vm = "Value mismatch (same key)"
    for rec in vm.by_record:
        if len(export_rows) >= MAX_EXPORT_ROWS:
            truncated = True
            break
        kt = tuple(str(x) for x in rec["key_tuple"])
        vals = _row_values_for_key(da, cols, keys, kt)
        export_rows.append(["Yes", cat_vm, rec["summary"]] + vals)

    if not export_rows:
        summary["tabular_export"] = make_export(
            cols,
            [
                [
                    "No",
                    "—",
                    "No discrepancies for File A → File B on the first sheet (within export limits).",
                ]
                + [""] * len(cols)
            ],
        )
    else:
        summary["tabular_export"] = make_export(cols, export_rows, truncated=truncated)

    summary["pdf_report"] = pdf_report
    return summary
