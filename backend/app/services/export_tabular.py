"""Build tabular export rows: Issue, Category, Discrepancy, then original data columns."""

from __future__ import annotations

from typing import Any, Optional

ISSUE_COL = "Issue"
CATEGORY_COL = "Category"
DISCREPANCY_COL = "Discrepancy"

# Cap rows stored in job JSON and written to export files (avoid huge payloads)
MAX_EXPORT_ROWS = 8000


def make_export(
    headers_data: list[str],
    rows: list[list[Any]],
    truncated: bool = False,
) -> dict[str, Any]:
    headers = [ISSUE_COL, CATEGORY_COL, DISCREPANCY_COL] + list(headers_data)
    return {
        "headers": headers,
        "rows": rows,
        "truncated": truncated,
    }


def single_row_export(
    headers_data: list[str],
    issue: str,
    discrepancy: str,
    values: Optional[list[Any]] = None,
    category: str = "—",
) -> dict[str, Any]:
    pad = (values or []) + [""] * max(0, len(headers_data) - len(values or []))
    row = [issue, category, discrepancy] + pad[: len(headers_data)]
    return make_export(headers_data, [row])

