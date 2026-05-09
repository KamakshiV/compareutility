"""Excel report output (tabular export with Issue / Discrepancy columns)."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import xlsxwriter

from app.services.export_tabular import make_export


def _summary_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """JSON summary without duplicating every export row (reference Export sheet / CSV)."""
    p = deepcopy(payload)
    comp = p.get("comparison")
    if isinstance(comp, dict):
        te = comp.get("tabular_export")
        if isinstance(te, dict) and te.get("rows"):
            comp = {**comp, "tabular_export": {
                "headers": te.get("headers"),
                "row_count": len(te["rows"]),
                "truncated": te.get("truncated", False),
                "note": "Full table is on the Export worksheet and in the downloadable CSV.",
            }}
            p["comparison"] = comp
    return p


def write_summary_report(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    comparison = payload.get("comparison") or {}
    tabular = comparison.get("tabular_export")
    if not isinstance(tabular, dict) or not tabular.get("headers"):
        tabular = make_export(
            ["message"],
            [["No", "—", "No tabular export available for this result type.", ""]],
        )

    pdf_part = comparison.get("pdf_report") if isinstance(comparison.get("pdf_report"), dict) else {}
    vmx = pdf_part.get("value_mismatch_excel") if isinstance(pdf_part.get("value_mismatch_excel"), dict) else {}

    workbook = xlsxwriter.Workbook(str(path))

    ws_exp = workbook.add_worksheet("Export")
    headers = list(tabular["headers"])
    for c, h in enumerate(headers):
        ws_exp.write(0, c, h)
    for r, row in enumerate(tabular.get("rows") or [], start=1):
        for c, val in enumerate(row):
            if c < len(headers):
                ws_exp.write(r, c, val)

    by_record = vmx.get("by_record") or []
    if by_record:
        ws_br = workbook.add_worksheet("By record")
        br_headers = [
            "Narrative label",
            "Record key (technical)",
            "Fields changed",
            "What changed (read-only summary)",
        ]
        for c, h in enumerate(br_headers):
            ws_br.write(0, c, h)
        for r, rec in enumerate(by_record, start=1):
            ws_br.write(r, 0, rec.get("narrative_label", rec.get("record_key", "")))
            ws_br.write(r, 1, rec.get("record_key", ""))
            ws_br.write(r, 2, rec.get("field_count", 0))
            ws_br.write(r, 3, rec.get("summary", ""))

    field_headers = vmx.get("field_headers") or []
    field_rows = vmx.get("field_rows") or []
    if field_headers and field_rows:
        ws_fd = workbook.add_worksheet("Field deltas")
        for c, h in enumerate(field_headers):
            ws_fd.write(0, c, h)
        for r, row in enumerate(field_rows, start=1):
            for c, val in enumerate(row):
                if c < len(field_headers):
                    ws_fd.write(r, c, val)

    ws_sum = workbook.add_worksheet("Summary")
    row = 0
    ws_sum.write(row, 0, "Reconiq report (metadata JSON — row-level export is on «Export»)")
    row += 2
    text = json.dumps(_summary_payload(payload), indent=2, default=str)
    for line in text.splitlines():
        ws_sum.write(row, 0, line)
        row += 1

    workbook.close()
