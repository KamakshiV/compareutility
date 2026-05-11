"""Insight agent: LLM narrative over reconciliation output (optional)."""

from __future__ import annotations

from typing import Any, Optional

from app.agents.llm_tools import pipeline_llm_complete
from app.agents.state import ReconcileState
from app.services.payload_slim import slim_comparison_for_llm


def run(state: ReconcileState) -> dict[str, Any]:
    if state.get("error"):
        return {"llm_insight": None}

    comp = state.get("comparison_result") or {}
    comp_slim = slim_comparison_for_llm(comp) if isinstance(comp, dict) else comp
    keys = state.get("key_field_names")
    narr = state.get("narrative_field_names")
    lid = comp.get("llm_discrepancy_identification") if isinstance(comp, dict) else None
    lid_slim: Optional[dict[str, Any]] = None
    if isinstance(lid, dict):
        lid_slim = {
            "findings": (lid.get("findings") or [])[:30],
            "material_level_summary": (lid.get("material_level_summary") or [])[:20],
            "limitations": lid.get("limitations"),
        }

    payload = {
        "key_field_names": keys,
        "narrative_field_names": narr,
        "note": (
            "key_field_names identify rows for matching; narrative_field_names are only for human-readable "
            "labels in exports (Discrepancy column, Excel record labels). When describing findings, use the same "
            "vocabulary: refer to records using narrative labels when present in reconciliation text. "
            "If llm_discrepancy_identification is present, it is an LLM synthesis grounded in the same evidence—"
            "align your bullets with it; do not contradict stated row counts from reconciliation."
        ),
        "reconciliation": comp_slim,
        "llm_discrepancy_identification": lid_slim,
        "schema_profile": state.get("schema_profile"),
        "recommended_rules": state.get("recommended_rules"),
    }
    user = (
        "Summarize the following structured comparison result for a business user in 5-8 bullet points. "
        "Respect key_field_names vs narrative_field_names from the payload (do not conflate them). "
        "Highlight mismatches, row counts, and caveats; when the export mentions «labels», those come from "
        "narrative_field_names on File A rows.\n\n"
        + str(payload)[:12000]
    )
    text = pipeline_llm_complete(
        "You are a data comparison assistant for finance and operations teams. "
        "You read JSON summaries of File A → File B reconciliations.",
        user,
        stage="insight",
        max_user_chars=12000,
        chat_model_id=state.get("openai_model"),
    )
    return {"llm_insight": text}
