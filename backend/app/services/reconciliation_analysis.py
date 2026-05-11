"""
Value-mismatch analysis and narrative helpers for Excel reconciliation (File A → File B, one-way).

Keys with duplicate rows on either side are skipped for 1:1 field comparison.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Optional

import polars as pl

MAX_VALUE_MISMATCH_ROWS = 500


def _cell_str(v: Any) -> str:
    if v is None:
        return ""
    if hasattr(v, "isoformat"):
        return str(v)
    return str(v)


def _variance_display(a: Any, b: Any) -> str:
    try:
        fa, fb = float(a), float(b)
        return str(abs(fa - fb))
    except (TypeError, ValueError):
        return "n/a"


def _mismatch_category(field_name: str) -> str:
    n = field_name.lower()
    if any(x in n for x in ("amount", "price", "total", "qty", "quantity")):
        return "Amount mismatch"
    if "date" in n:
        return "Date mismatch"
    return "Field mismatch"


def row_key_tuple(d: dict[str, Any], key_cols: list[str]) -> tuple[str, ...]:
    return tuple(_cell_str(d.get(c)) for c in key_cols)


def narrative_label_from_row(d: dict[str, Any], narrative_cols: list[str]) -> str:
    if not narrative_cols:
        return ""
    return " | ".join(_cell_str(d.get(c)) for c in narrative_cols)


def discrepancy_missing_in_b_row(
    row: dict[str, Any],
    narrative_cols: list[str],
    *,
    pair_label: str,
) -> str:
    """Export / Excel «Discrepancy» text for a File A row missing from File B (uses narrative when set)."""
    lab = narrative_label_from_row(row, narrative_cols).strip()
    if lab:
        return (
            f"File A record «{lab}»: this row’s composite key does not appear in File B "
            f"(compare {pair_label})."
        )
    return (
        f"File A row: composite key not found in File B ({pair_label}). "
        "Choose narrative columns in the app to show a clearer record label here."
    )


def _format_record_summary(narrative_label: str, changes: list[dict[str, Any]]) -> str:
    """One readable sentence per record for Excel «Discrepancy» and the By record sheet."""
    lede = f"«{narrative_label}»" if narrative_label.strip() else "This record"
    if len(changes) == 1:
        c = changes[0]
        return (
            f"{lede} — only «{c['field']}» differs between File A and File B. "
            f"File A: {c['source_a']}  →  File B: {c['source_b']}"
        )
    tail = "; ".join(
        f"«{c['field']}» (File A: {c['source_a']} | File B: {c['source_b']})" for c in changes
    )
    return f"{lede} — {len(changes)} columns differ. {tail}"


@dataclass
class ValueMismatchAnalysis:
    """Field-level rows for Excel «Field deltas», plus per-record narratives."""

    field_rows: list[list[Any]] = field(default_factory=list)
    by_record: list[dict[str, Any]] = field(default_factory=list)
    mismatch_key_tuples: set[tuple[str, ...]] = field(default_factory=set)


def compute_value_mismatch_analysis(
    left: pl.DataFrame,
    right: pl.DataFrame,
    key_cols: list[str],
    narrative_cols: Optional[list[str]] = None,
) -> ValueMismatchAnalysis:
    """
    Keys with exactly one row on each side that differ on any non-key column.
    narrative_cols: columns used for human-facing «Record» labels (from File A row); defaults to key_cols.
    """
    out = ValueMismatchAnalysis()
    if not key_cols:
        return out
    for c in key_cols:
        if c not in left.columns or c not in right.columns:
            return out

    narr = narrative_cols if narrative_cols else key_cols
    for c in narr:
        if c not in left.columns:
            return out

    def build_map(df: pl.DataFrame) -> dict[tuple[str, ...], list[dict[str, Any]]]:
        m: dict[tuple[str, ...], list[dict[str, Any]]] = defaultdict(list)
        for d in df.to_dicts():
            kt = row_key_tuple(d, key_cols)
            m[kt].append(d)
        return m

    lm = build_map(left)
    rm = build_map(right)
    value_cols = [c for c in left.columns if c not in key_cols]

    for kt in sorted(set(lm.keys()) & set(rm.keys()), key=lambda x: x):
        if len(out.field_rows) >= MAX_VALUE_MISMATCH_ROWS:
            break
        la, lb = lm[kt], rm[kt]
        if len(la) != 1 or len(lb) != 1:
            continue
        ra, rb = la[0], lb[0]
        key_display = " | ".join(kt)
        narrative_label = narrative_label_from_row(ra, narr)
        changes: list[dict[str, Any]] = []
        for c in value_cols:
            if c not in right.columns:
                continue
            va, vb = ra.get(c), rb.get(c)
            if _cell_str(va) != _cell_str(vb):
                changes.append(
                    {
                        "field": c,
                        "source_a": _cell_str(va),
                        "source_b": _cell_str(vb),
                        "category": _mismatch_category(c),
                    }
                )
                out.field_rows.append(
                    [
                        narrative_label,
                        c,
                        _cell_str(va),
                        _cell_str(vb),
                        _variance_display(va, vb),
                        _mismatch_category(c),
                    ]
                )
                if len(out.field_rows) >= MAX_VALUE_MISMATCH_ROWS:
                    break
        if changes:
            out.mismatch_key_tuples.add(kt)
            out.by_record.append(
                {
                    "record_key": key_display,
                    "narrative_label": narrative_label,
                    "key_tuple": list(kt),
                    "field_count": len(changes),
                    "summary": _format_record_summary(narrative_label, changes),
                    "changes": changes,
                }
            )
    return out


def build_value_mismatch_excel_block(
    vm: ValueMismatchAnalysis,
    key_columns: list[str],
    narrative_field_names: list[str],
) -> dict[str, Any]:
    """Payload for Excel «By record» / «Field deltas» sheets and LLM evidence."""
    key_desc = ", ".join(key_columns) if key_columns else "(first column)"
    narr_desc = ", ".join(narrative_field_names) if narrative_field_names else key_desc
    vm_key_header = f"Record ({narr_desc})" if narrative_field_names else f"Record key ({key_desc})"
    vm_headers = [vm_key_header, "Field", "File A value", "File B value", "Variance", "Category"]
    return {
        "by_record": vm.by_record,
        "field_headers": vm_headers,
        "field_rows": vm.field_rows,
    }
