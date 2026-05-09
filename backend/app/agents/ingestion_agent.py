"""Ingestion agent: validate materialized files on disk before profiling."""

from __future__ import annotations

from pathlib import Path

from app.agents.llm_tools import pipeline_llm_complete
from app.agents.state import ReconcileState


def run(state: ReconcileState) -> dict:
    paths = state.get("local_paths") or []
    if len(paths) < 2:
        return {"error": "At least two files required"}
    missing = [p for p in paths if not Path(p).exists()]
    if missing:
        return {"error": f"Missing files after ingestion: {missing}"}
    notes = {
        "status": "ok",
        "file_count": len(paths),
        "paths": [str(Path(p).name) for p in paths],
    }
    llm = pipeline_llm_complete(
        "You assist a file reconciliation pipeline. Be concise and practical.",
        "Ingestion just validated these inputs (order matters: first file is File A, second is File B for spreadsheets):\n"
        + str(notes)
        + "\n\nGive 3-5 short bullets: what an analyst should double-check before trusting the compare "
        "(pairing, naming, duplicates, file types). Do not invent data not implied above.",
        max_user_chars=2000,
    )
    if llm is not None:
        notes["llm_notes"] = llm
    return {"ingest_notes": notes}
