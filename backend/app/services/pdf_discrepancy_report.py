"""Render structured discrepancy PDF (ReportLab)."""

from __future__ import annotations

import io
from typing import Any
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

_ACCENT_HEX = {"red": "#C0392B", "orange": "#E67E22"}

_MIN_COL_PT = 34  # minimum width per narrow column (~0.47") so labels stay readable


def _column_widths_pt(headers: list[str], usable_pt: float) -> list[float]:
    """Widen Comments vs equal split; keep widths summing to usable_pt."""
    n = len(headers)
    if n <= 0:
        return []
    if n == 1:
        return [usable_pt]

    comments_idx = None
    for i, h in enumerate(headers):
        if str(h).strip().lower() == "comments":
            comments_idx = i

    equal = usable_pt / n
    if comments_idx is None:
        return [equal] * n

    # Aim for Comments ≈ max(2× equal share, 26% of row); cap so others stay ≥ _MIN_COL_PT.
    comments_target = min(max(equal * 2.2, usable_pt * 0.26), usable_pt * 0.45)
    others_w = (usable_pt - comments_target) / (n - 1)
    if others_w < _MIN_COL_PT:
        others_w = _MIN_COL_PT
        comments_target = usable_pt - others_w * (n - 1)
    comments_target = max(comments_target, _MIN_COL_PT)

    out = [others_w] * n
    out[comments_idx] = usable_pt - others_w * (n - 1)
    return out


def _para_fragment(raw: str) -> str:
    """Safe subset HTML for ReportLab Paragraph."""
    if raw is None:
        return ""
    s = str(raw)
    if len(s) > 1200:
        s = s[:1197] + "..."
    s = escape(s)
    return s.replace("\n", "<br/>")


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
    cell_style = ParagraphStyle(
        "PDFCell",
        parent=styles["Normal"],
        fontSize=8,
        leading=9.5,
        textColor=colors.HexColor("#2C3E50"),
        alignment=TA_LEFT,
        wordWrap="LTR",
    )
    header_cell_style = ParagraphStyle(
        "PDFHeaderCell",
        parent=cell_style,
        fontName="Helvetica-Bold",
        textColor=colors.HexColor("#2C3E50"),
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

        header_cells = [
            Paragraph(f"<b>{_para_fragment(h)}</b>", header_cell_style) for h in headers
        ]
        body_cells = [
            [Paragraph(_para_fragment(v), cell_style) for v in row] for row in data
        ]
        table_data = [header_cells] + body_cells
        col_count = len(headers)
        avail = letter[0] - doc.leftMargin - doc.rightMargin
        col_widths = _column_widths_pt(headers, float(avail))
        t = Table(table_data, colWidths=col_widths, repeatRows=1)
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
