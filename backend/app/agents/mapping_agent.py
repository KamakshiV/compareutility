"""Mapping agent: field alignment between sources (heuristic / stub for POC)."""

from __future__ import annotations

from app.agents.llm_tools import pipeline_llm_complete
from app.agents.state import ReconcileState


def run(state: ReconcileState) -> dict:
    if state.get("error"):
        return {}
    n = len(state.get("local_paths", []))
    keys = state.get("key_field_names")
    narr = state.get("narrative_field_names")
    mapping = {
        "strategy": "same_name_same_order",
        "source_count": n,
        "user_key_fields": keys,
        "user_narrative_fields": narr,
        "confidence": "high_if_schemas_identical",
    }
    llm = pipeline_llm_complete(
        "You advise on column mapping for two-file reconciliation (File A vs File B).",
        "Deterministic mapping stub:\n"
        + str(mapping)
        + "\n\nIn 4-7 bullets: risks when keys or narrative labels are mis-chosen; "
        "when same-name columns might still differ in meaning; what to verify if schemas drift. "
        "Do not contradict that matching is by exact column name in this POC.",
        max_user_chars=3500,
    )
    if llm is not None:
        mapping["llm_notes"] = llm
    return {"column_mapping": mapping}
