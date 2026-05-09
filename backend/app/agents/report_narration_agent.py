"""Report narration agent: shapes output for Excel export + dashboard consumption."""

from __future__ import annotations

from typing import Any

from app.agents.state import ReconcileState


def run(state: ReconcileState) -> dict[str, Any]:
    if state.get("error"):
        insight = state.get("llm_insight")
        return {
            "dashboard_narrative": insight
            or "Comparison failed; see reconciliation error in technical details."
        }
    insight = state.get("llm_insight")
    summary = state.get("comparison_result") or {}
    headline = summary.get("type", "comparison")
    return {
        "dashboard_narrative": insight
        or f"Deterministic {headline} complete; enable USE_LLM_SUMMARY for natural language insight."
    }
