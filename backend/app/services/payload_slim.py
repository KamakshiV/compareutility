"""Trim heavy comparison payloads before LLM / logging (keeps counts, drops bulk rows)."""

from __future__ import annotations

from typing import Any


def slim_comparison_for_llm(comparison: dict[str, Any]) -> dict[str, Any]:
    """
    Remove large row arrays from comparison JSON so `str(payload)` and LLM calls stay fast.
    Full exports remain in the job result on disk / DB elsewhere.
    """
    if not isinstance(comparison, dict):
        return comparison
    out: dict[str, Any] = dict(comparison)

    te = out.get("tabular_export")
    if isinstance(te, dict) and te.get("rows"):
        out["tabular_export"] = {
            "headers": te.get("headers"),
            "row_count": len(te["rows"]),
            "truncated": te.get("truncated", False),
            "note": "Row data omitted here for speed; see job Export / Excel report.",
        }

    pr = out.get("pdf_report")
    if isinstance(pr, dict):
        pr_slim = dict(pr)
        secs = pr_slim.get("sections")
        if isinstance(secs, list):
            pr_slim["sections"] = []
            for sec in secs:
                if not isinstance(sec, dict):
                    continue
                s = {k: v for k, v in sec.items() if k != "rows"}
                rows = sec.get("rows") or []
                s["row_count"] = len(rows) if isinstance(rows, list) else 0
                pr_slim["sections"].append(s)
        vm = pr_slim.get("value_mismatch_excel")
        if isinstance(vm, dict):
            vm2 = dict(vm)
            fr = vm2.get("field_rows")
            if isinstance(fr, list) and len(fr) > 200:
                vm2["field_rows"] = fr[:200]
                vm2["field_rows_truncated"] = len(fr) - 200
            br = vm2.get("by_record")
            if isinstance(br, list) and len(br) > 200:
                vm2["by_record"] = br[:200]
                vm2["by_record_truncated"] = len(br) - 200
            pr_slim["value_mismatch_excel"] = vm2
        out["pdf_report"] = pr_slim

    return out
