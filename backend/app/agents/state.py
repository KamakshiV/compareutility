"""Shared LangGraph state for the reconciliation pipeline."""

from __future__ import annotations

from typing import Any, Optional, TypedDict


class ReconcileState(TypedDict, total=False):
    """State flowing through ingestion → profiling → mapping → rules → execution → insights."""

    local_paths: list[str]
    kinds: list[str]
    key_field_names: Optional[list[str]]
    narrative_field_names: Optional[list[str]]
    openai_model: Optional[str]
    ingest_notes: dict[str, Any]
    schema_profile: dict[str, Any]
    column_mapping: dict[str, Any]
    recommended_rules: dict[str, Any]
    comparison_result: dict[str, Any]
    llm_insight: Optional[str]
    dashboard_narrative: Optional[str]
    error: Optional[str]
