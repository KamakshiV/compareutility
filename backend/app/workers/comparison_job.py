import asyncio
import uuid
from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.agents.graph import run_compare_graph
from app.config import get_settings
from app.db.models import ComparisonJob, JobStatus
from app.services.job_file_order import file_ids_for_compare
from app.services.report_generator import write_summary_report
from app.services.storage_service import StoredBlobMissingError, get_storage


async def run_comparison_job(db: AsyncSession, job_id: uuid.UUID) -> None:
    settings = get_settings()
    result = await db.execute(
        select(ComparisonJob)
        .options(selectinload(ComparisonJob.files))
        .where(ComparisonJob.id == job_id)
    )
    job = result.scalar_one()
    job.status = JobStatus.running
    job.updated_at = datetime.utcnow()
    await db.commit()

    storage = get_storage()
    tmp_dir = Path(settings.storage_local_path) / "tmp" / str(job_id)
    tmp_dir.mkdir(parents=True, exist_ok=True)
    local_paths: list[Path] = []
    kinds: list = []

    try:
        by_id = {uf.id: uf for uf in job.files}
        ordered_ids = file_ids_for_compare(job)

        async def _download(fid: uuid.UUID) -> tuple[uuid.UUID, Path, object]:
            uf = by_id[fid]
            data = await storage.read_bytes(uf.storage_key)
            ext = Path(uf.original_name).suffix or ".bin"
            lp = tmp_dir / f"{uf.id}{ext}"
            lp.write_bytes(data)
            return fid, lp, uf.kind

        downloaded = await asyncio.gather(*[_download(fid) for fid in ordered_ids])
        id_to_pair = {fid: (lp, k) for fid, lp, k in downloaded}
        for fid in ordered_ids:
            lp, k = id_to_pair[fid]
            local_paths.append(lp)
            kinds.append(k)

        graph_out = run_compare_graph(
            local_paths,
            kinds,
            job.key_field_names,
            job.narrative_field_names,
            openai_model=job.openai_model,
        )
        payload = {
            "comparison": graph_out.get("comparison"),
            "agent_trace": graph_out.get("agent_trace"),
            "llm_summary": graph_out.get("llm_summary"),
            "dashboard_narrative": graph_out.get("dashboard_narrative"),
            "key_field_names": job.key_field_names,
            "narrative_field_names": job.narrative_field_names,
            "openai_model": job.openai_model,
        }
        if graph_out.get("error"):
            job.status = JobStatus.failed
            job.error_message = str(graph_out["error"])
            job.result_json = payload
        else:
            job.status = JobStatus.succeeded
            job.result_json = payload
            report_path = tmp_dir / "report.xlsx"
            write_summary_report(report_path, payload)
            report_key = await storage.save_bytes(report_path.read_bytes(), suffix=".xlsx")
            job.report_storage_key = report_key

        job.updated_at = datetime.utcnow()
        await db.commit()
    except StoredBlobMissingError as e:
        job.status = JobStatus.failed
        job.error_message = str(e)
        job.updated_at = datetime.utcnow()
        await db.commit()
    except Exception as e:
        job.status = JobStatus.failed
        job.error_message = str(e)
        job.updated_at = datetime.utcnow()
        await db.commit()
        raise
