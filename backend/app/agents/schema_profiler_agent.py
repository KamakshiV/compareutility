"""Schema profiler agent: summarize detected file kinds and comparison mode."""

from __future__ import annotations

import logging

from app.agents.llm_tools import pipeline_llm_complete
from app.agents.state import ReconcileState
from app.db.models import FileKind

log = logging.getLogger(__name__)


def run(state: ReconcileState) -> dict:
    log.info("Run schema profiler agent")
    if state.get("error"):
        return {}
    kinds_raw = state.get("kinds") or []
    if not kinds_raw:
        return {"schema_profile": {}, "error": "No kinds provided"}
    kinds = [FileKind(k) for k in kinds_raw]
    dominant = kinds[0].value if kinds else "unknown"
    mode = "excel_first_sheet" if dominant in ("xlsx", "xls") else "unknown"
    profile = {
        "dominant_kind": dominant,
        "kinds": [k.value for k in kinds],
        "comparison_mode": mode,
        "notes": "Excel-only: first sheet is compared; column matching is by header name.",
    }
    llm = pipeline_llm_complete(
        "You profile data sources for reconciliation. Be concise.",
        "Schema profile (deterministic):\n"
        + str(profile)
        + "\n\nIn 4-6 bullets, explain limitations and caveats of this Excel-first-sheet setup "
        "(e.g. hidden sheets ignored, merged cells, duplicate headers). No generic filler.",
        stage="schema_profiler",
        max_user_chars=3000,
        chat_model_id=state.get("openai_model"),
    )
    if llm is not None:
        profile["llm_notes"] = llm
    return {"schema_profile": profile}
