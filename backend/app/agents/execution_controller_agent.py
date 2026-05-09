"""Execution controller agent: invokes the deterministic reconciliation engine."""

from __future__ import annotations

from pathlib import Path

from app.agents.state import ReconcileState
from app.db.models import FileKind
from app.services.reconciliation_engine import run_reconciliation


def run(state: ReconcileState) -> dict:
    if state.get("error"):
        return {}
    paths = [Path(p) for p in state["local_paths"]]
    kinds = [FileKind(k) for k in state["kinds"]]
    result = run_reconciliation(
        paths,
        kinds,
        state.get("key_field_names"),
        state.get("narrative_field_names"),
    )
    if "error" in result:
        return {"comparison_result": result, "error": str(result.get("error"))}
    return {"comparison_result": result}
