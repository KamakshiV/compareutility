"""Insight agent: LLM narrative over reconciliation output (optional)."""

from __future__ import annotations

from typing import Any

from app.agents.llm_tools import pipeline_llm_complete
from app.agents.state import ReconcileState


def run(state: ReconcileState) -> dict[str, Any]:
    if state.get("error"):
        return {"llm_insight": None}

    payload = {
        "reconciliation": state.get("comparison_result", {}),
        "schema_profile": state.get("schema_profile"),
        "recommended_rules": state.get("recommended_rules"),
    }
    user = (
        "Summarize the following structured comparison result for a business user "
        "in 5-8 bullet points. Highlight mismatches, row counts, and caveats.\n\n"
        + str(payload)[:12000]
    )
    text = pipeline_llm_complete(
        "You are a data comparison assistant for finance and operations teams.",
        user,
        stage="insight",
        max_user_chars=12000,
    )
    return {"llm_insight": text}
