"""PDF text extraction (PyMuPDF primary, pdfplumber secondary)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import fitz  # PyMuPDF


@dataclass
class PdfTextBundle:
    pymupdf_text: str
    page_count: int


def extract_text_pymupdf(path: Path) -> PdfTextBundle:
    doc = fitz.open(path)
    parts: list[str] = []
    for page in doc:
        parts.append(page.get_text())
    doc.close()
    return PdfTextBundle(pymupdf_text="\n".join(parts), page_count=len(parts))


def extract_text_pdfplumber(path: Path) -> str:
    import pdfplumber

    chunks: list[str] = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            chunks.append(page.extract_text() or "")
    return "\n".join(chunks)
