"""Rule recommendation agent: proposes deterministic reconciliation rules."""

from __future__ import annotations

import logging

from app.agents.llm_tools import pipeline_llm_complete
from app.agents.state import ReconcileState

log = logging.getLogger(__name__)


def run(state: ReconcileState) -> dict:
    log.info("Run rule recommendation agent")
    if state.get("error"):
        return {}
    profile = state.get("schema_profile") or {}
    mode = profile.get("comparison_mode", "unknown")
    is_tabular = mode in ("tabular_duckdb", "tabular_json", "excel_first_sheet")
    rules = {
        "row_identity": "composite_key" if is_tabular else "na",
        "diff_policy": (
            "file_a_to_file_b: missing_keys_in_b + value_mismatch_1_1"
            if is_tabular
            else "unified_line_diff"
        ),
        "tolerance": {"numeric_epsilon": 0, "ignore_case": False},
        "notes": "Execution engine uses user-selected keys; tabular compare is directional (File A baseline).",
    }
    llm = pipeline_llm_complete(
        "You explain reconciliation rules to analysts.",
        "Proposed rule metadata (informational; engine behavior is fixed in code):\n"
        + str({"schema_profile": profile, "recommended_rules": rules})
        + "\n\nIn 4-6 bullets: what this policy implies, edge cases (duplicate keys, type coercion), "
        "and what is NOT detected. Mention one-way File A→File B for spreadsheets.",
        stage="rules",
        max_user_chars=4000,
        chat_model_id=state.get("openai_model"),
    )
    if llm is not None:
        rules["llm_notes"] = llm
    return {"recommended_rules": rules}
