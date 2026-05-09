"""Render structured discrepancy PDF (ReportLab)."""

from __future__ import annotations

import io
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

_ACCENT_HEX = {"red": "#C0392B", "orange": "#E67E22"}


def render_discrepancy_pdf(payload: dict[str, Any]) -> bytes:
    """
    payload: from build_tabular_pdf_report / build_text_pdf_report with keys
    title, subtitle, sections[{id,title,description,accent,headers,rows}]
    """
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=letter,
        rightMargin=0.65 * inch,
        leftMargin=0.65 * inch,
        topMargin=0.65 * inch,
        bottomMargin=0.65 * inch,
        title=payload.get("title", "Report"),
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "T",
        parent=styles["Heading1"],
        fontSize=16,
        spaceAfter=6,
        textColor=colors.HexColor("#1a1a1a"),
    )
    sub_style = ParagraphStyle(
        "S",
        parent=styles["Normal"],
        fontSize=10,
        textColor=colors.HexColor("#555555"),
        spaceAfter=14,
    )
    sec_title_style = ParagraphStyle(
        "ST",
        parent=styles["Heading2"],
        fontSize=12,
        spaceAfter=4,
        textColor=colors.HexColor("#1a1a1a"),
        alignment=TA_LEFT,
    )
    desc_style = ParagraphStyle(
        "D",
        parent=styles["Normal"],
        fontSize=9,
        textColor=colors.HexColor("#444444"),
        spaceAfter=8,
    )

    story: list[Any] = []
    story.append(Paragraph(payload.get("title", "Report"), title_style))
    if payload.get("subtitle"):
        story.append(Paragraph(payload["subtitle"], sub_style))

    for sec in payload.get("sections") or []:
        hex_c = _ACCENT_HEX.get(sec.get("accent"), "#34495E")
        bullet = f'<font color="{hex_c}">●</font>'
        story.append(
            Paragraph(
                f"{bullet} &nbsp; <b>{sec.get('id', '')} {sec.get('title', '')}</b>",
                sec_title_style,
            )
        )
        story.append(Paragraph(sec.get("description", ""), desc_style))

        headers: list[str] = [str(h) for h in (sec.get("headers") or [])]
        rows_raw: list[list[Any]] = sec.get("rows") or []
        if not headers:
            headers = ["(no columns)"]
            data = [["—"]]
        elif not rows_raw:
            data = [["—" for _ in headers]]
        else:
            data = [[_pdf_cell(v) for v in row] for row in rows_raw]
            # pad ragged rows
            for row in data:
                while len(row) < len(headers):
                    row.append("")
                row[:] = row[: len(headers)]

        table_data = [headers] + data
        col_count = len(headers)
        avail = letter[0] - 1.3 * inch
        col_w = avail / max(col_count, 1)
        t = Table(table_data, colWidths=[col_w] * col_count, repeatRows=1)
        t.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#ECF0F1")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#2C3E50")),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#BDC3C7")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#FAFAFA")]),
                ]
            )
        )
        story.append(t)
        story.append(Spacer(1, 0.22 * inch))

    doc.build(story)
    return buf.getvalue()


def _pdf_cell(v: Any) -> str:
    if v is None:
        return ""
    s = str(v)
    if len(s) > 500:
        return s[:497] + "..."
    return s
