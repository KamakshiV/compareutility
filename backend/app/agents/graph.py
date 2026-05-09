"""
LangGraph orchestrator: ingestion → schema → mapping → rules → execution → insight → narration.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal, Optional

from langgraph.graph import END, StateGraph

from . import (
    execution_controller_agent,
    ingestion_agent,
    insight_agent,
    mapping_agent,
    report_narration_agent,
    rule_agent,
    schema_profiler_agent,
)
from .state import ReconcileState
from app.db.models import FileKind


def _wrap(agent_run):
    def _node(state: ReconcileState) -> ReconcileState:
        patch = agent_run(state)
        return {**state, **patch}

    return _node


def build_graph():
    g = StateGraph(ReconcileState)
    g.add_node("ingestion", _wrap(ingestion_agent.run))
    g.add_node("schema_profiler", _wrap(schema_profiler_agent.run))
    g.add_node("mapping", _wrap(mapping_agent.run))
    g.add_node("rule_recommendation", _wrap(rule_agent.run))
    g.add_node("execution", _wrap(execution_controller_agent.run))
    g.add_node("insight", _wrap(insight_agent.run))
    g.add_node("report_narration", _wrap(report_narration_agent.run))

    g.set_entry_point("ingestion")
    g.add_edge("ingestion", "schema_profiler")
    g.add_edge("schema_profiler", "mapping")
    g.add_edge("mapping", "rule_recommendation")
    g.add_edge("rule_recommendation", "execution")

    def route_after_execution(state: ReconcileState) -> Literal["insight", "report_narration"]:
        if state.get("error"):
            return "report_narration"
        return "insight"

    g.add_conditional_edges(
        "execution",
        route_after_execution,
        {"insight": "insight", "report_narration": "report_narration"},
    )
    g.add_edge("insight", "report_narration")
    g.add_edge("report_narration", END)
    return g.compile()


def run_compare_graph(
    local_paths: list[Path],
    kinds: list[FileKind],
    key_field_names: Optional[list[str]] = None,
    narrative_field_names: Optional[list[str]] = None,
) -> dict[str, Any]:
    app = build_graph()
    init: dict[str, Any] = {
        "local_paths": [str(p) for p in local_paths],
        "kinds": [k.value for k in kinds],
    }
    if key_field_names:
        init["key_field_names"] = key_field_names
    if narrative_field_names:
        init["narrative_field_names"] = narrative_field_names
    final = app.invoke(init)
    comparison = final.get("comparison_result")
    err = final.get("error")
    agent_trace = {
        "ingestion": final.get("ingest_notes"),
        "schema_profile": final.get("schema_profile"),
        "column_mapping": final.get("column_mapping"),
        "recommended_rules": final.get("recommended_rules"),
    }
    return {
        "comparison": comparison,
        "agent_trace": agent_trace,
        "llm_summary": final.get("llm_insight"),
        "dashboard_narrative": final.get("dashboard_narrative"),
        "error": err,
    }
