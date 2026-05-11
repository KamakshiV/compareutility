"""
SAP / tabular JSON comparison: File A (first export) → File B (second), one-way.

Expected JSON shape per file: {"columns": ["a","b"], "rows": [[1,"x"], [2,"y"]]}
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

import polars as pl

from app.services.export_tabular import MAX_EXPORT_ROWS, make_export, single_row_export
from app.services.key_fields import coerce_key_fields, normalize_narrative_columns
from app.services.tabular_pdf_sections import (
    build_tabular_pdf_report,
    compute_value_mismatch_analysis,
    discrepancy_missing_in_b_row,
    row_key_tuple,
)


def _cell_value(v: Any) -> Any:
    if v is None:
        return ""
    if hasattr(v, "isoformat"):
        return str(v)
    return v


def _load_export(path: Path) -> pl.DataFrame:
    data = json.loads(path.read_text(encoding="utf-8"))
    return pl.DataFrame(data["rows"], schema=data["columns"], orient="row")


def compare_sap_exports(
    paths: list[Path],
    key_field_names: Optional[list[str]] = None,
    narrative_field_names: Optional[list[str]] = None,
) -> dict[str, Any]:
    if len(paths) < 2:
        return {"error": "Need at least two SAP export JSON files for POC"}

    paths_eff = paths[:2]
    dfs = [_load_export(p) for p in paths_eff]
    summary: dict[str, Any] = {
        "type": "sap_export_json",
        "comparison_mode": "file_a_to_file_b",
        "file_a": paths_eff[0].name,
        "file_b": paths_eff[1].name,
        "note": "Replace with live SAP/HANA connection in production.",
        "schemas_match": dfs[0].columns == dfs[1].columns,
        "row_counts": {"file_a": len(dfs[0]), "file_b": len(dfs[1])},
    }
    if len(paths) > 2:
        summary["files_ignored_note"] = (
            f"Only the first two exports are compared; {len(paths) - 2} additional file(s) were ignored."
        )

    if not summary["schemas_match"]:
        summary["columns"] = [d.columns for d in dfs]
        summary["tabular_export"] = single_row_export(
            ["detail"],
            "Yes",
            "Schema mismatch: column names or order differ between SAP exports; cannot reconcile rows.",
            ["See result columns list in JSON summary."],
            category="Schema mismatch",
        )
        return summary

    left, right = dfs[0], dfs[1]
    cols = list(left.columns)
    keys, key_err = coerce_key_fields(key_field_names, cols)
    if key_err:
        return {"error": key_err}

    narrative_cols = normalize_narrative_columns(narrative_field_names, keys, cols)
    summary["key_field_names"] = keys
    summary["narrative_field_names"] = narrative_cols

    b_key_index = right.select(keys).unique()
    missing_in_b = left.join(b_key_index, on=keys, how="anti")
    vm = compute_value_mismatch_analysis(left, right, keys, narrative_cols)

    summary["diff"] = {
        "keys_in_file_a_not_file_b": len(missing_in_b),
        "value_mismatch_records_1_1": len(vm.by_record),
        "sample_missing_in_b": missing_in_b.head(10).to_dicts() if len(missing_in_b) else [],
    }

    pair_label = f"{paths_eff[0].name} vs {paths_eff[1].name}"
    summary["pdf_report"] = build_tabular_pdf_report(
        paths_eff[0].name,
        paths_eff[1].name,
        left,
        right,
        missing_in_b,
        keys,
        narrative_cols,
        vm_analysis=vm,
    )

    export_rows: list[list[Any]] = []
    truncated = False

    for d in missing_in_b.head(MAX_EXPORT_ROWS).to_dicts():
        if len(export_rows) >= MAX_EXPORT_ROWS:
            truncated = True
            break
        disc_miss = discrepancy_missing_in_b_row(d, narrative_cols, pair_label=pair_label)
        export_rows.append(["Yes", "Missing in File B", disc_miss] + [_cell_value(d.get(c)) for c in cols])

    cat_vm = "Value mismatch (same key)"
    for rec in vm.by_record:
        if len(export_rows) >= MAX_EXPORT_ROWS:
            truncated = True
            break
        kt = tuple(str(x) for x in rec["key_tuple"])
        vals: list[Any] = []
        for d in left.to_dicts():
            if row_key_tuple(d, keys) == kt:
                vals = [_cell_value(d.get(c)) for c in cols]
                break
        if not vals:
            vals = [""] * len(cols)
        export_rows.append(["Yes", cat_vm, rec["summary"]] + vals)

    if not export_rows:
        summary["tabular_export"] = make_export(
            cols,
            [
                [
                    "No",
                    "—",
                    "No discrepancies for File A → File B between the two SAP exports.",
                ]
                + [""] * len(cols)
            ],
        )
    else:
        summary["tabular_export"] = make_export(cols, export_rows, truncated=truncated)

    return summary
