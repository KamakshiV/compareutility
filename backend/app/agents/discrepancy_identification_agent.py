"""
LLM-assisted discrepancy identification: reads deterministic reconciliation evidence
and produces structured findings (grounded in supplied data only).
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from app.agents.llm_tools import pipeline_llm_complete
from app.agents.state import ReconcileState

log = logging.getLogger(__name__)

_MAX_EVIDENCE_CHARS = 14000


def _parse_json_object(text: str) -> Optional[dict[str, Any]]:
    if not text or not text.strip():
        return None
    t = text.strip()
    if t.startswith("```"):
        lines = t.split("\n")
        if lines and lines[0].strip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        t = "\n".join(lines).strip()
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        pass
    i, j = t.find("{"), t.rfind("}")
    if i >= 0 and j > i:
        try:
            return json.loads(t[i : j + 1])
        except json.JSONDecodeError:
            return None
    return None


def _build_evidence(state: ReconcileState, comp: dict[str, Any]) -> dict[str, Any]:
    dd = comp.get("descriptive_discrepancies") if isinstance(comp.get("descriptive_discrepancies"), dict) else {}
    diff = comp.get("diff_sample") if isinstance(comp.get("diff_sample"), dict) else {}
    vm = comp.get("value_mismatch_excel") if isinstance(comp.get("value_mismatch_excel"), dict) else {}
    by_record = vm.get("by_record") or []
    slim_records: list[dict[str, Any]] = []
    for rec in by_record[:45]:
        slim_records.append(
            {
                "record_key": rec.get("record_key"),
                "narrative_label": rec.get("narrative_label"),
                "summary": rec.get("summary"),
                "changes": (rec.get("changes") or [])[:12],
            }
        )
    return {
        "instruction": (
            "Identify discrepancies ONLY from this evidence. Do not invent row counts, keys, or values "
            "not shown. If evidence is thin, say so in limitations."
        ),
        "file_a": comp.get("file_a"),
        "file_b": comp.get("file_b"),
        "comparison_mode": comp.get("comparison_mode"),
        "key_field_names": state.get("key_field_names") or comp.get("key_field_names"),
        "narrative_field_names": state.get("narrative_field_names") or comp.get("narrative_field_names"),
        "row_counts": comp.get("row_counts"),
        "diff_sample": diff,
        "descriptive_discrepancies": {
            "material_level_findings": (dd.get("material_level_findings") or [])[:40],
            "itemized": dd.get("itemized"),
            "duplicate_key_row_count_file_a": dd.get("duplicate_key_row_count_file_a"),
            "duplicate_key_row_count_file_b": dd.get("duplicate_key_row_count_file_b"),
            "material_column_used": dd.get("material_column_used"),
        },
        "value_mismatch_records_sample": slim_records,
    }


def run(state: ReconcileState) -> dict[str, Any]:
    if state.get("error"):
        return {}

    comp = state.get("comparison_result")
    if not isinstance(comp, dict) or comp.get("error"):
        return {}

    evidence = _build_evidence(state, comp)
    user_body = json.dumps(evidence, indent=2, default=str)[:_MAX_EVIDENCE_CHARS]

    system = (
        "You are a senior reconciliation analyst. Your task is to IDENTIFY and CLASSIFY discrepancies for a "
        "File A → File B compare using ONLY the JSON evidence provided by the user. "
        "Rules: (1) Never invent counts, amounts, or keys—only infer what the evidence supports. "
        "(2) Use categories: data_integrity (missing/extra/duplicate keys), financial_valuation "
        "(Value vs Quantity×Price, Price/Quantity/Value cross-file), attribute_field_mismatch "
        "(non-financial fields on matching keys). "
        "(3) Each finding must cite what in the evidence supports it (evidence_refs: short strings). "
        "(4) Respond with a single JSON object only, no markdown fences, no prose outside JSON. "
        "Schema: {\n"
        '  "findings": [\n'
        "    {\n"
        '      "category": "data_integrity|financial_valuation|attribute_field_mismatch",\n'
        '      "severity": "high|medium|low",\n'
        '      "title": "short headline",\n'
        '      "detail": "2-4 sentences",\n'
        '      "evidence_refs": ["string", "..."]\n'
        "    }\n"
        "  ],\n"
        '  "material_level_summary": ["optional bullets tied to Material if evidence mentions it"],\n'
        '  "limitations": "what you could not confirm from evidence only"\n'
        "}"
    )

    raw = pipeline_llm_complete(
        system,
        user_body,
        stage="discrepancy_id",
        max_user_chars=_MAX_EVIDENCE_CHARS,
        chat_model_id=state.get("openai_model"),
    )
    if raw is None:
        return {}
    if isinstance(raw, str) and (
        raw.startswith("LLM skipped") or raw.startswith("LLM error")
    ):
        log.info("discrepancy_identification: %s", raw[:120])
        return {}

    parsed = _parse_json_object(raw)
    if parsed is None:
        log.warning("discrepancy_identification: JSON parse failed, storing raw excerpt")
        parsed = {
            "findings": [],
            "material_level_summary": [],
            "limitations": "Model output was not valid JSON.",
            "raw_model_excerpt": (raw or "")[:8000],
        }

    out: dict[str, Any] = {
        "findings": parsed.get("findings") or [],
        "material_level_summary": parsed.get("material_level_summary") or [],
        "limitations": parsed.get("limitations"),
    }
    if parsed.get("raw_model_excerpt"):
        out["raw_model_excerpt"] = parsed.get("raw_model_excerpt")

    return {"comparison_result": {**comp, "llm_discrepancy_identification": out}}
