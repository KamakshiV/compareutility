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

_MIN_NARROW_PT = 32  # generic numeric / short code columns
_MIN_DOC_PT = 64  # Document, Document_item — avoid splitting IDs across lines
_MIN_DATE_PT = 68  # delivery date, etc.
_MIN_COMMENT_PT = 78  # Comments may wrap; floor keeps one short line readable


def _col_weight_and_floor(header: str) -> tuple[float, float]:
    """
    Return (weight for extra width after floors, minimum width in pt).
    Higher weight → more of the slack width after minimums are satisfied.
    """
    hl = str(header).strip().lower()
    if hl == "comments":
        return (0.85, float(_MIN_COMMENT_PT))
    if "document" in hl:
        return (2.5, float(_MIN_DOC_PT))
    if "date" in hl:
        return (2.4, float(_MIN_DATE_PT))
    if "material" in hl:
        return (1.6, float(_MIN_NARROW_PT + 8))
    if any(x in hl for x in ("price", "value", "currency", "quantity", "qty", "uom")):
        return (1.15, float(_MIN_NARROW_PT))
    return (1.0, float(_MIN_NARROW_PT))


def _column_widths_pt(headers: list[str], usable_pt: float) -> list[float]:
    """
    Widths sum to usable_pt. Document / date columns get higher floors and extra share;
    Comments gets a modest floor so it wraps instead of stealing width from identifiers.
    """
    n = len(headers)
    if n <= 0:
        return []
    if n == 1:
        return [usable_pt]

    meta = [_col_weight_and_floor(h) for h in headers]
    floors = [m[1] for m in meta]
    weights = [m[0] for m in meta]
    floor_sum = sum(floors)
    if floor_sum >= usable_pt:
        # Too many columns / wide floors: scale floors down uniformly
        scale = usable_pt / floor_sum
        return [f * scale for f in floors]

    remaining = usable_pt - floor_sum
    wsum = sum(weights)
    extras = [(remaining * w / wsum) if wsum else remaining / n for w in weights]
    return [floors[i] + extras[i] for i in range(n)]


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
