"""Resolve comparison file order: POST file_ids order wins; legacy jobs use upload created_at."""

from __future__ import annotations

import uuid

from app.db.models import ComparisonJob


def file_ids_for_compare(job: ComparisonJob) -> list[uuid.UUID]:
    files = list(job.files or [])
    by_id = {f.id: f for f in files}
    raw = job.ordered_file_ids
    if raw:
        try:
            ordered = [uuid.UUID(str(x)) for x in raw]
            if set(ordered) == set(by_id.keys()) and len(ordered) == len(by_id):
                return ordered
        except (ValueError, TypeError):
            pass
    return [f.id for f in sorted(files, key=lambda f: f.created_at)]
