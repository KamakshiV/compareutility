"""Schema profiler agent: summarize detected file kinds and comparison mode."""

from __future__ import annotations

from app.agents.llm_tools import pipeline_llm_complete
from app.agents.state import ReconcileState
from app.db.models import FileKind


def run(state: ReconcileState) -> dict:
    if state.get("error"):
        return {}
    kinds_raw = state.get("kinds") or []
    if not kinds_raw:
        return {"schema_profile": {}, "error": "No kinds provided"}
    kinds = [FileKind(k) for k in kinds_raw]
    dominant = kinds[0].value if kinds else "unknown"
    mode = "tabular_duckdb" if dominant in ("xlsx", "xls") else "text_diff" if dominant == "pdf" else "tabular_json"
    profile = {
        "dominant_kind": dominant,
        "kinds": [k.value for k in kinds],
        "comparison_mode": mode,
        "notes": "POC: Excel uses first sheet only; PDF uses extracted text lines.",
    }
    llm = pipeline_llm_complete(
        "You profile data sources for reconciliation. Be concise.",
        "Schema profile (deterministic):\n"
        + str(profile)
        + "\n\nIn 4-6 bullets, explain limitations and caveats of this POC setup for this kind "
        "(e.g. first sheet only, text PDFs vs scanned, SAP JSON shape). No generic filler.",
        max_user_chars=3000,
    )
    if llm is not None:
        profile["llm_notes"] = llm
    return {"schema_profile": profile}
