"""PDF text comparison (connectors + deterministic diff)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.services.export_tabular import MAX_EXPORT_ROWS, make_export
from app.services.pdf_parser import extract_text_pdfplumber, extract_text_pymupdf
from app.services.tabular_pdf_sections import build_text_pdf_report


def simple_text_diff(a: str, b: str, max_lines: int = 200) -> dict[str, Any]:
    la = a.splitlines()
    lb = b.splitlines()
    from difflib import unified_diff

    diff = list(unified_diff(la, lb, lineterm="", n=2))
    return {
        "lines_left": len(la),
        "lines_right": len(lb),
        "unified_diff_head": diff[:max_lines],
        "truncated": len(diff) > max_lines,
    }


def _pdf_tabular_export(paths: list[Path], bundles: list) -> dict[str, Any]:
    """
    PDFs have no spreadsheet columns; export uses synthetic headers that mirror
    a simple line-oriented layout: original «line» column plus Issue + Discrepancy.
    """
    pdf_headers = ["Line reference", "Content"]
    rows: list[list[Any]] = []

    for i in range(len(bundles)):
        for j in range(i + 1, len(bundles)):
            key = f"file{i}_vs_file{j}"
            la = bundles[i].pymupdf_text.splitlines()
            lb = bundles[j].pymupdf_text.splitlines()
            from difflib import unified_diff

            diff = list(unified_diff(la, lb, lineterm="", n=2))
            pair_label = f"{paths[i].name} vs {paths[j].name}"
            for line in diff:
                if len(rows) >= MAX_EXPORT_ROWS:
                    return make_export(pdf_headers, rows, truncated=True)
                if line.startswith("+++ ") or line.startswith("--- ") or line.startswith("@@"):
                    rows.append(
                        [
                            "No",
                            "Diff structure",
                            "Unified diff section header (not a content mismatch by itself).",
                            "",
                            line,
                        ]
                    )
                    continue
                if line.startswith("+"):
                    rows.append(
                        [
                            "Yes",
                            "Added in second file",
                            f"Text added in the second PDF relative to the first ({pair_label}).",
                            "second",
                            line[1:],
                        ]
                    )
                elif line.startswith("-"):
                    rows.append(
                        [
                            "Yes",
                            "Only in first file",
                            f"Text present only in the first PDF ({pair_label}); removed or missing in the second.",
                            "first",
                            line[1:],
                        ]
                    )
                else:
                    rows.append(
                        [
                            "No",
                            "Context",
                            "Context line (unchanged vicinity between differences).",
                            "both",
                            line,
                        ]
                    )

    if not rows:
        return make_export(
            pdf_headers,
            [["No", "—", "No text differences in unified diff output.", "", ""]],
        )
    return make_export(pdf_headers, rows)


def compare_pdf_files(paths: list[Path]) -> dict[str, Any]:
    if len(paths) < 2:
        return {"error": "Need at least two PDF files"}

    bundles = [extract_text_pymupdf(p) for p in paths]
    out: dict[str, Any] = {
        "type": "pdf",
        "engines": {"primary": "pymupdf", "secondary_sample": "pdfplumber_page0"},
        "files": [{"path": str(p), "pages": b.page_count} for p, b in zip(paths, bundles)],
        "pairwise_text_diff": {},
    }

    for i in range(len(bundles)):
        for j in range(i + 1, len(bundles)):
            key = f"file{i}_vs_file{j}"
            out["pairwise_text_diff"][key] = simple_text_diff(
                bundles[i].pymupdf_text, bundles[j].pymupdf_text
            )

    try:
        out["pdfplumber_sample_file0"] = extract_text_pdfplumber(paths[0])[:2000]
    except Exception as e:
        out["pdfplumber_sample_file0"] = f"skipped: {e}"

    tabular = _pdf_tabular_export(paths, bundles)
    out["tabular_export"] = tabular
    if len(paths) >= 2:
        out["pdf_report"] = build_text_pdf_report(paths[0].name, paths[1].name, tabular)
    return out
