"""Render structured discrepancy PDF (ReportLab) from `build_excel_pdf_report` payloads."""

from __future__ import annotations

import html
import io
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def _para(text: str, style: ParagraphStyle) -> Paragraph:
    return Paragraph(html.escape(str(text or "")).replace("\n", "<br/>"), style)


def render_discrepancy_pdf(payload: dict[str, Any]) -> bytes:
    """
    payload: from `build_excel_pdf_report` with keys title, subtitle (optional), sections[].
    Each section: title, description, headers[], rows[][] (cell values as strings).
    """
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=letter,
        rightMargin=0.65 * inch,
        leftMargin=0.65 * inch,
        topMargin=0.65 * inch,
        bottomMargin=0.65 * inch,
        title=str(payload.get("title") or "Report"),
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        name="DocTitle",
        parent=styles["Heading1"],
        fontSize=16,
        spaceAfter=8,
        alignment=TA_LEFT,
    )
    sub_style = ParagraphStyle(
        name="DocSub",
        parent=styles["Normal"],
        fontSize=10,
        textColor=colors.HexColor("#444444"),
        spaceAfter=14,
    )
    sec_title_style = ParagraphStyle(
        name="SecTitle",
        parent=styles["Heading2"],
        fontSize=12,
        spaceBefore=10,
        spaceAfter=6,
    )
    desc_style = ParagraphStyle(
        name="SecDesc",
        parent=styles["Normal"],
        fontSize=9,
        leading=12,
        spaceAfter=8,
    )
    cell_style = ParagraphStyle(
        name="TblCell",
        parent=styles["Normal"],
        fontSize=7,
        leading=9,
        wordWrap="CJK",
    )
    header_cell_style = ParagraphStyle(
        name="TblHead",
        parent=styles["Normal"],
        fontSize=7,
        leading=9,
        textColor=colors.white,
    )

    story: list[Any] = []
    story.append(_para(payload.get("title") or "Reconciliation report", title_style))
    if payload.get("subtitle"):
        story.append(_para(payload["subtitle"], sub_style))

    for sec in payload.get("sections") or []:
        if not isinstance(sec, dict):
            continue
        story.append(_para(sec.get("title") or "Section", sec_title_style))
        if sec.get("description"):
            story.append(_para(sec["description"], desc_style))

        headers = list(sec.get("headers") or [])
        rows_raw = list(sec.get("rows") or [])
        if not headers:
            story.append(Spacer(1, 6))
            continue

        max_rows = 400
        trimmed = rows_raw[:max_rows]
        data: list[list[Any]] = [[_para(h, header_cell_style) for h in headers]]
        for row in trimmed:
            r = list(row) if isinstance(row, (list, tuple)) else [row]
            if len(r) < len(headers):
                r = r + [""] * (len(headers) - len(r))
            elif len(r) > len(headers):
                r = r[: len(headers)]
            data.append([_para(str(c), cell_style) for c in r])

        col_count = len(headers)
        col_w = (doc.width / max(col_count, 1)) * 0.98
        tbl = Table(data, colWidths=[col_w] * col_count, repeatRows=1)
        tbl.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2c5282")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, 0), 7),
                    ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
                    ("TOPPADDING", (0, 0), (-1, 0), 4),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.whitesmoke, colors.white]),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cccccc")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 4),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        story.append(tbl)
        if len(rows_raw) > max_rows:
            story.append(_para(f"… {len(rows_raw) - max_rows} more row(s) omitted for PDF size.", desc_style))
        story.append(Spacer(1, 12))

    doc.build(story)
    return buf.getvalue()
