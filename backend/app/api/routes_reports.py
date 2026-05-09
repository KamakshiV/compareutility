import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.db.job_repository import get_job
from app.db.models import JobStatus
from app.services.export_tabular import make_export
from app.services.pdf_discrepancy_report import render_discrepancy_pdf
from app.services.storage_service import get_storage
from app.services.tabular_pdf_sections import build_text_pdf_report

router = APIRouter(prefix="/jobs", tags=["reports"])


@router.get("/{job_id}/report")
async def download_report(
    job_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    job = await get_job(db, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if not job.report_storage_key:
        raise HTTPException(status_code=404, detail="No report yet")

    storage = get_storage()
    data = await storage.read_bytes(job.report_storage_key)
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@router.get("/{job_id}/export.pdf")
async def download_export_pdf(
    job_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Structured discrepancy PDF (sections 4.1–4.3 for tabular data; text layout for document PDFs)."""
    job = await get_job(db, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if not job.result_json:
        raise HTTPException(status_code=404, detail="No result payload for this job")
    if job.status != JobStatus.succeeded:
        raise HTTPException(status_code=404, detail="PDF export is only available for successful jobs")

    comparison = job.result_json.get("comparison") or {}
    pdf_payload = comparison.get("pdf_report")
    if not isinstance(pdf_payload, dict) or not pdf_payload.get("sections"):
        tabular = comparison.get("tabular_export")
        if not isinstance(tabular, dict) or not tabular.get("headers"):
            tabular = make_export(
                ["detail"],
                [["No", "—", "No structured export available for this job.", ""]],
            )
        pdf_payload = build_text_pdf_report("Source A", "Source B", tabular)

    pdf_bytes = render_discrepancy_pdf(pdf_payload)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="reconiq-job-{job_id}.pdf"'},
    )
