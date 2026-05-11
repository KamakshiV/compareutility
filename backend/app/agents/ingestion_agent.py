"""Ingestion agent: validate materialized files on disk before profiling."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional

from app.agents.llm_tools import pipeline_llm_complete
from app.agents.state import ReconcileState
from app.db.models import FileKind
from app.services.column_preview import list_columns_from_path

log = logging.getLogger(__name__)

_TABULAR_KINDS = frozenset({FileKind.xlsx.value, FileKind.xls.value, FileKind.sap.value})


def _column_schema_check(paths: list[str], kinds: list[str]) -> tuple[Optional[str], dict[str, Any]]:
    """
    For two tabular files of the same kind, require identical column name sets (order may differ).
    Returns (error_message, fragment to merge into ingest_notes).
    """
    if len(paths) < 2 or len(kinds) < 2:
        return None, {}
    k0, k1 = kinds[0], kinds[1]
    if k0 not in _TABULAR_KINDS or k1 not in _TABULAR_KINDS:
        return None, {"column_schema_check": {"skipped": True, "reason": "non_tabular_or_unsupported_kind"}}
    if k0 != k1:
        return None, {
            "column_schema_check": {
                "skipped": True,
                "reason": "file_kinds_differ",
                "detail": "Schema header compare runs only when File A and File B share the same tabular kind.",
            }
        }
    try:
        kind = FileKind(k0)
        cols_a = list_columns_from_path(Path(paths[0]), kind)
        cols_b = list_columns_from_path(Path(paths[1]), kind)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as e:
        msg = f"Could not read tabular headers for schema check: {e}"
        log.warning(msg)
        return msg, {"column_schema_check": {"error": str(e)}}

    set_a, set_b = set(cols_a), set(cols_b)
    same_order = cols_a == cols_b
    base: dict[str, Any] = {
        "column_schema_check": {
            "aligned": set_a == set_b,
            "same_order": same_order,
            "file_a_column_count": len(cols_a),
            "file_b_column_count": len(cols_b),
        }
    }
    if set_a == set_b:
        if not same_order:
            base["column_schema_check"]["note"] = (
                "Column names match between File A and File B; order differs (OK — matching is by name)."
            )
        return None, base

    only_a = sorted(set_a - set_b)
    only_b = sorted(set_b - set_a)
    base["column_schema_check"]["only_in_file_a"] = only_a
    base["column_schema_check"]["only_in_file_b"] = only_b
    err = (
        "File A and File B do not have the same column headers — reconciliation and mapping will be unreliable. "
        f"Columns only in File A ({len(only_a)}): {only_a[:25]}"
        f"{'…' if len(only_a) > 25 else ''}. "
        f"Columns only in File B ({len(only_b)}): {only_b[:25]}"
        f"{'…' if len(only_b) > 25 else ''}. "
        "Align schemas (same names) or export the same layout, then retry."
    )
    return err, base


def run(state: ReconcileState) -> dict:
    log.info("Run ingestion agent")
    paths = state.get("local_paths") or []
    kinds = state.get("kinds") or []
    if len(paths) < 2:
        return {"error": "At least two files required"}
    missing = [p for p in paths if not Path(p).exists()]
    if missing:
        return {"error": f"Missing files after ingestion: {missing}"}

    schema_err, schema_fragment = _column_schema_check(paths, kinds)
    notes: dict[str, Any] = {
        "status": "ok",
        "file_count": len(paths),
        "paths": [str(Path(p).name) for p in paths],
        **schema_fragment,
    }
    if schema_err:
        notes["status"] = "column_mismatch"
        return {"error": schema_err, "ingest_notes": notes}

    llm = pipeline_llm_complete(
        "You assist a file reconciliation pipeline. Be concise and practical.",
        "Ingestion just validated these inputs (order matters: first file is File A, second is File B for spreadsheets):\n"
        + str(notes)
        + "\n\nGive 3-5 short bullets: what an analyst should double-check before trusting the compare "
        "(pairing, naming, duplicates, file types). Do not invent data not implied above.",
        stage="ingestion",
        max_user_chars=2000,
        chat_model_id=state.get("openai_model"),
    )
    if llm is not None:
        notes["llm_notes"] = llm
    return {"ingest_notes": notes}
