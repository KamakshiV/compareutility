"""
Descriptive discrepancy rollups for trade-style reconciliation:

- Material-level summary (when a «Material» column exists)
- Data integrity: missing in B, duplicate composite keys in A or B
- Financial / valuation: Value vs Quantity × Price within each file; cross-file Value/Price/Quantity deltas
- Attribute / field mismatches: cross-file column deltas on 1:1 keys (from ValueMismatchAnalysis)
"""

from __future__ import annotations

from typing import Any, Optional

import polars as pl

from app.services.reconciliation_analysis import ValueMismatchAnalysis, _cell_str, row_key_tuple

_VAL_EPS = 0.5  # tolerate minor rounding; flag larger gaps


def _find_column(df: pl.DataFrame, names: tuple[str, ...]) -> Optional[str]:
    lower = {str(c).lower(): c for c in df.columns}
    for n in names:
        if n.lower() in lower:
            return str(lower[n.lower()])
    return None


def _numeric_expr(col: str) -> pl.Expr:
    return pl.col(col).cast(pl.Float64, strict=False)


def _valuation_anomalies(df: pl.DataFrame, label: str) -> tuple[pl.DataFrame, list[str]]:
    """Rows where Value is present and materially differs from Quantity * Price."""
    qcol = _find_column(df, ("quantity", "qty"))
    pcol = _find_column(df, ("price",))
    vcol = _find_column(df, ("value", "total value"))
    if not qcol or not pcol or not vcol:
        return pl.DataFrame(), []

    work = df.with_columns(
        [
            _numeric_expr(qcol).alias("_q"),
            _numeric_expr(pcol).alias("_p"),
            _numeric_expr(vcol).alias("_v"),
        ]
    ).with_columns((pl.col("_q") * pl.col("_p")).alias("_expected"))

    bad = work.filter(
        pl.col("_v").is_not_null()
        & pl.col("_expected").is_finite()
        & pl.col("_q").is_not_null()
        & pl.col("_p").is_not_null()
        & ((pl.col("_v") - pl.col("_expected")).abs() > _VAL_EPS)
    )

    mat_col = _find_column(df, ("material",))
    doc_col = _find_column(df, ("document",))
    item_col = _find_column(df, ("document_item", "document_it"))

    lines: list[str] = []
    for d in bad.head(200).to_dicts():
        mat = _cell_str(d.get(mat_col)) if mat_col else ""
        doc = _cell_str(d.get(doc_col)) if doc_col else ""
        item = _cell_str(d.get(item_col)) if item_col else ""
        lede = f"«{mat}»" if mat.strip() else f"Document {doc} / item {item}".strip() or "Row"
        qv = _cell_str(d.get(qcol))
        pv = _cell_str(d.get(pcol))
        vv = _cell_str(d.get(vcol))
        ev = _cell_str(d.get("_expected"))
        lines.append(
            f"{label}: {lede} — Value {vv} does not match Quantity × Price "
            f"({qv} × {pv} = {ev}). Possible valuation, unit scale, or rounding error."
        )
    return bad, lines


def _duplicate_key_rows(df: pl.DataFrame, keys: list[str]) -> pl.DataFrame:
    if not keys or not all(k in df.columns for k in keys):
        return pl.DataFrame()
    cnt = df.group_by(keys).len().filter(pl.col("len") > 1)
    if len(cnt) == 0:
        return pl.DataFrame()
    return df.join(cnt.select(keys), on=keys, how="inner")


def _material_for_key(df: pl.DataFrame, keys: list[str], kt: tuple[str, ...], mat_col: Optional[str]) -> str:
    if not mat_col or mat_col not in df.columns:
        return ""
    for d in df.to_dicts():
        if row_key_tuple(d, keys) == kt:
            return _cell_str(d.get(mat_col)).strip()
    return ""


def compute_descriptive_discrepancies(
    da: pl.DataFrame,
    db: pl.DataFrame,
    keys: list[str],
    missing_in_b: pl.DataFrame,
    vm: ValueMismatchAnalysis,
) -> dict[str, Any]:
    mat_col = _find_column(da, ("material",)) or _find_column(db, ("material",))

    dup_a = _duplicate_key_rows(da, keys)
    dup_b = _duplicate_key_rows(db, keys)

    bad_a, val_lines_a = _valuation_anomalies(da, "File A")
    bad_b, val_lines_b = _valuation_anomalies(db, "File B")

    by_material: dict[str, dict[str, int]] = {}

    def _touch(mat: str, **kwargs: int) -> None:
        m = mat.strip() or "(no material)"
        if m not in by_material:
            by_material[m] = {
                "missing_in_file_b": 0,
                "duplicate_keys_file_a": 0,
                "duplicate_keys_file_b": 0,
                "valuation_anomalies_file_a": 0,
                "valuation_anomalies_file_b": 0,
                "cross_file_financial_field_deltas": 0,
                "cross_file_other_field_deltas": 0,
            }
        for k, v in kwargs.items():
            if k in by_material[m]:
                by_material[m][k] += int(v)

    if mat_col and len(missing_in_b) > 0 and mat_col in missing_in_b.columns:
        for row in missing_in_b.group_by(mat_col).len().to_dicts():
            m = _cell_str(row.get(mat_col))
            _touch(m, missing_in_file_b=int(row.get("len", 0)))

    if mat_col and len(dup_a) > 0 and mat_col in dup_a.columns:
        for row in dup_a.group_by(mat_col).len().to_dicts():
            m = _cell_str(row.get(mat_col))
            _touch(m, duplicate_keys_file_a=int(row.get("len", 0)))

    if mat_col and len(dup_b) > 0 and mat_col in dup_b.columns:
        for row in dup_b.group_by(mat_col).len().to_dicts():
            m = _cell_str(row.get(mat_col))
            _touch(m, duplicate_keys_file_b=int(row.get("len", 0)))

    if mat_col and len(bad_a) > 0 and mat_col in bad_a.columns:
        for row in bad_a.group_by(mat_col).len().to_dicts():
            m = _cell_str(row.get(mat_col))
            _touch(m, valuation_anomalies_file_a=int(row.get("len", 0)))

    if mat_col and len(bad_b) > 0 and mat_col in bad_b.columns:
        for row in bad_b.group_by(mat_col).len().to_dicts():
            m = _cell_str(row.get(mat_col))
            _touch(m, valuation_anomalies_file_b=int(row.get("len", 0)))

    fin_tokens = ("value", "price", "quantity", "qty", "amount", "total")
    for rec in vm.by_record:
        kt = tuple(str(x) for x in rec["key_tuple"])
        m = _material_for_key(da, keys, kt, mat_col) if mat_col else ""
        for ch in rec.get("changes") or []:
            fn = str(ch.get("field", "")).lower()
            if any(t in fn for t in fin_tokens):
                _touch(m, cross_file_financial_field_deltas=1)
            else:
                _touch(m, cross_file_other_field_deltas=1)

    material_bullets: list[str] = []
    for m, stats in sorted(by_material.items()):
        parts: list[str] = []
        if stats["missing_in_file_b"]:
            parts.append(
                f"{stats['missing_in_file_b']} row(s) from File A missing in File B "
                "(same Document + line item key not found in File B)"
            )
        if stats["duplicate_keys_file_a"]:
            parts.append(
                f"{stats['duplicate_keys_file_a']} row(s) in File A share a duplicate composite key "
                "(data integrity / booking noise)"
            )
        if stats["duplicate_keys_file_b"]:
            parts.append(
                f"{stats['duplicate_keys_file_b']} row(s) in File B share a duplicate composite key "
                "(blocks clean 1:1 match)"
            )
        if stats["valuation_anomalies_file_a"] or stats["valuation_anomalies_file_b"]:
            parts.append(
                "internal valuation check failed (Value ≠ Quantity × Price) on "
                f"{stats['valuation_anomalies_file_a']} File A row(s), "
                f"{stats['valuation_anomalies_file_b']} File B row(s)"
            )
        if stats["cross_file_financial_field_deltas"]:
            parts.append(
                f"{stats['cross_file_financial_field_deltas']} cross-file financial field delta(s) "
                "(e.g. Price, Quantity, Value) where keys match 1:1"
            )
        if stats["cross_file_other_field_deltas"]:
            parts.append(
                f"{stats['cross_file_other_field_deltas']} cross-file attribute delta(s) "
                "(e.g. Material spelling, delivery date, UoM) on matching keys"
            )
        if parts:
            material_bullets.append(f"«{m}» — " + "; ".join(parts) + ".")

    if not material_bullets:
        fallback: list[str] = []
        if len(missing_in_b):
            fallback.append(
                f"{len(missing_in_b)} File A row(s) missing in File B (by key: {', '.join(keys)})."
            )
        if len(dup_a):
            fallback.append(f"{len(dup_a)} File A row(s) involved in duplicate keys.")
        if len(dup_b):
            fallback.append(f"{len(dup_b)} File B row(s) involved in duplicate keys.")
        if val_lines_a or val_lines_b:
            fallback.append(
                "Internal valuation anomalies detected (Value vs Quantity × Price); "
                "see «Financial / valuation» below."
            )
        if vm.by_record:
            fallback.append(f"{len(vm.by_record)} record(s) with cross-file field differences on 1:1 keys.")
        if mat_col is None:
            fallback.append(
                "No «Material» column detected; add one for trade-book style rollups by commodity."
            )
        material_bullets = fallback or ["No discrepancies detected on the first sheet within the applied rules."]

    data_integrity: list[str] = []
    if len(missing_in_b):
        data_integrity.append(
            f"Missing in File B: {len(missing_in_b)} row(s) from File A whose composite key "
            f"({', '.join(keys)}) does not appear in File B (directional compare File A → File B)."
        )
    if len(dup_a):
        data_integrity.append(
            f"Duplicate keys in File A: {len(dup_a)} row(s) share a composite key with another row. "
            "Automated value comparison skips these keys until the file is de-duplicated or keys are extended."
        )
    if len(dup_b):
        data_integrity.append(
            f"Duplicate keys in File B: {len(dup_b)} row(s) share a composite key. "
            "Resolve duplicates before expecting a single matched line per key."
        )
    if not data_integrity:
        data_integrity.append(
            "No missing-key rows (A→B) and no duplicate composite keys detected on the first sheet."
        )

    financial: list[str] = []
    financial.extend(val_lines_a[:80])
    financial.extend(val_lines_b[:80])

    def _is_financial_field(name: str) -> bool:
        fl = name.lower()
        return any(t in fl for t in ("value", "price", "quantity", "qty", "amount", "total"))

    for rec in vm.by_record[:80]:
        fins = [ch for ch in (rec.get("changes") or []) if _is_financial_field(str(ch.get("field", "")))]
        if fins:
            bits = ", ".join(
                f"«{ch.get('field')}» A={ch.get('source_a')} / B={ch.get('source_b')}" for ch in fins
            )
            financial.append(f"Cross-file (1:1 keys): {rec.get('summary', '')} — {bits}")

    if not val_lines_a and not val_lines_b:
        financial.append(
            "Internal check: either columns «Quantity», «Price», and «Value» are not all present, "
            "or every populated row satisfies Value ≈ Quantity × Price within tolerance."
        )

    attribute_lines: list[str] = []
    for rec in vm.by_record[:120]:
        non_fin = [ch for ch in (rec.get("changes") or []) if not _is_financial_field(str(ch.get("field", "")))]
        if non_fin:
            bits = "; ".join(
                f"«{ch.get('field')}» File A={ch.get('source_a')} vs File B={ch.get('source_b')}"
                for ch in non_fin
            )
            attribute_lines.append(f"{rec.get('summary', '')} Detail: {bits}")
    if not attribute_lines:
        attribute_lines.append(
            "No cross-file attribute-only mismatches on 1:1 keys (e.g. Material, delivery date, UoM). "
            "If financial columns differ, see «Financial / valuation»; if keys duplicate, see «Data integrity»."
        )

    note_trade_book = (
        "When finalized, material-level totals can be tied to the trade book for booked vs line-item checks."
    )

    return {
        "trade_book_note": note_trade_book,
        "material_column_used": mat_col,
        "material_level_findings": material_bullets,
        "by_material_stats": by_material,
        "duplicate_key_row_count_file_a": len(dup_a),
        "duplicate_key_row_count_file_b": len(dup_b),
        "valuation_anomaly_lines_file_a": val_lines_a[:100],
        "valuation_anomaly_lines_file_b": val_lines_b[:100],
        "itemized": {
            "data_integrity": data_integrity,
            "financial_valuation": financial,
            "attribute_field_mismatch": attribute_lines,
        },
    }
