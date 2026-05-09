"""Validate and normalize user-selected key columns."""

from __future__ import annotations

from typing import Optional


def coerce_key_fields(requested: Optional[list[str]], available_columns: list[str]) -> tuple[Optional[list[str]], Optional[str]]:
    """
    Returns (key_columns, error_message).
    If requested is None/empty, defaults to the first available column.
    """
    if not available_columns:
        return None, "The file has no column headers to use as keys"
    if not requested:
        return [available_columns[0]], None

    seen: set[str] = set()
    ordered: list[str] = []
    for raw in requested:
        k = (raw or "").strip()
        if not k:
            continue
        if k not in available_columns:
            return None, f"Key column {k!r} is not present in this file"
        if k not in seen:
            seen.add(k)
            ordered.append(k)

    if not ordered:
        return None, "Select at least one key column"
    return ordered, None


def normalize_narrative_columns(
    requested: Optional[list[str]],
    keys: list[str],
    available: list[str],
) -> list[str]:
    """Use requested narrative columns when valid; otherwise fall back to key columns."""
    if not requested:
        return list(keys)
    seen: set[str] = set()
    out: list[str] = []
    for c in requested:
        if c in available and c not in seen:
            seen.add(c)
            out.append(c)
    return out if out else list(keys)
