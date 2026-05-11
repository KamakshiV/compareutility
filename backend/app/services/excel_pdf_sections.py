"""Build structured sections for the Excel reconciliation PDF (File A → File B, one-way)."""

from __future__ import annotations

from typing import Any, Optional

import polars as pl

from app.services.reconciliation_analysis import ValueMismatchAnalysis, narrative_label_from_row

MAX_PDF_SECTION_ROWS = 500


def _cell_str(v: Any) -> str:
    if v is None:
        return ""
    if hasattr(v, "isoformat"):
        return str(v)
    return str(v)


def _descriptive_prelude_sections(descriptive: dict[str, Any], key_columns: list[str]) -> list[dict[str, Any]]:
    keys_desc = ", ".join(key_columns) if key_columns else "(first column)"
    note = descriptive.get("trade_book_note") or ""
    material_bullets = descriptive.get("material_level_findings") or []
    item = descriptive.get("itemized") or {}
    data_integrity = item.get("data_integrity") or []
    financial = item.get("financial_valuation") or []
    attribute_lines = item.get("attribute_field_mismatch") or []

    sec3: dict[str, Any] = {
        "id": "3",
        "title": "Executive summary — material level (File A → File B)",
        "description": (
            "Rollup by «Material» when that column exists; otherwise aggregate counts only. "
            f"Match key: {keys_desc}. {note}"
        ),
        "accent": "orange",
        "headers": ["Finding"],
        "rows": [[b] for b in material_bullets] if material_bullets else [["No material-level findings to report."]],
    }
    sec31: dict[str, Any] = {
        "id": "3.1",
        "title": "Itemized discrepancies by category",
        "description": (
            "1) Data integrity — missing rows in File B or duplicate keys within a file. "
            "2) Financial / valuation — Value vs Quantity × Price within each file, plus cross-file "
            "financial columns on 1:1 keys. "
            "3) Attribute / field mismatch — non-financial columns that differ when the same key exists once per side."
        ),
        "accent": "red",
        "headers": ["Category", "Detail"],
        "rows": (
            [["Data integrity", x] for x in data_integrity]
            + [["Financial / valuation", x] for x in financial[:200]]
            + [["Attribute / field mismatch (cross-file)", x] for x in attribute_lines[:200]]
        ),
    }
    return [sec3, sec31]


def build_excel_pdf_report(
    source_a_name: str,
    source_b_name: str,
    left_full: pl.DataFrame,
    missing_in_b: pl.DataFrame,
    key_columns: list[str],
    narrative_field_names: list[str],
    vm_analysis: ValueMismatchAnalysis,
    descriptive: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """
    One-way compare: File A (left_full) vs File B.
    missing_in_b: rows from File A whose composite key does not appear in File B.
    """
    cols = list(left_full.columns) if len(left_full.columns) else []
    key_desc = ", ".join(key_columns) if key_columns else "(first column)"
    narr_desc = ", ".join(narrative_field_names) if narrative_field_names else key_desc

    headers_missing = list(cols) + ["Comments"]
    rows_b: list[list[Any]] = []
    for d in missing_in_b.head(MAX_PDF_SECTION_ROWS).to_dicts():
        lab = narrative_label_from_row(d, narrative_field_names).strip()
        comment = (
            f"Not in File B — record «{lab}»" if lab else "Key from File A not found in File B"
        )
        rows_b.append([_cell_str(d.get(c)) for c in cols] + [comment])

    vm_key_header = f"Record ({narr_desc})" if narrative_field_names else f"Record key ({key_desc})"
    vm_headers = [vm_key_header, "Field", "File A value", "File B value", "Variance", "Category"]
    vm_rows = vm_analysis.field_rows

    prelude: list[dict[str, Any]] = []
    if isinstance(descriptive, dict) and descriptive:
        prelude = _descriptive_prelude_sections(descriptive, key_columns)

    sections: list[dict[str, Any]] = (
        prelude
        + [
            {
                "id": "4.1",
                "title": "Missing in File B",
                "description": (
                    "Rows from File A whose key does not appear in File B. "
                    f"Match key: {key_desc}. "
                    "Records that exist only in File B are not listed in this one-way compare."
                ),
                "accent": "red",
                "headers": headers_missing,
                "rows": rows_b,
            },
            {
                "id": "4.2",
                "title": "Value mismatch",
                "description": (
                    "Same key in File A and File B (exactly one row on each side) but different values in other columns. "
                    f"Record labels use: {narr_desc}. "
                    "Keys with duplicate rows on either side are skipped."
                ),
                "accent": "orange",
                "headers": vm_headers,
                "rows": vm_rows,
            },
        ]
    )

    return {
        "report_type": "tabular",
        "title": "Reconciliation report",
        "subtitle": f"File A → File B (one-way): {source_a_name} vs {source_b_name}",
        "comparison_mode": "file_a_to_file_b",
        "key_field_names": key_columns,
        "narrative_field_names": narrative_field_names,
        "sections": sections,
    }
