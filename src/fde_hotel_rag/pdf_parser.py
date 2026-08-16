"""Deterministic extraction of readable text from the supplied catalogue."""

from __future__ import annotations

from pathlib import Path

import pdfplumber


def extract_pdf_text(pdf_path: Path) -> list[str]:
    """Return one cleaned text block for each PDF page."""
    if not pdf_path.is_file():
        raise FileNotFoundError(f"PDF non trovato: {pdf_path}")
    with pdfplumber.open(pdf_path) as pdf:
        pages = [" ".join((page.extract_text() or "").split()) for page in pdf.pages]
    if not any(pages):
        raise ValueError("Nel PDF non è stato trovato testo estraibile")
    return pages


def write_raw_text(pages: list[str], output_path: Path) -> None:
    """Write page-labelled raw text so extraction can be audited."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    content = "\n\n".join(f"--- PAGE {index} ---\n{text}" for index, text in enumerate(pages, 1))
    output_path.write_text(content, encoding="utf-8")
