"""Candidate PyMuPDF extractor for comparing multi-column PDF layouts."""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path

import pymupdf

from .pdf_parser import HotelBlock, clean_ocr
from .quality_model import compute_field_confidence


_HEADER_MAX_Y = 170.0
_EXCLUDED_HEADER_TEXT = {"PUGLIA", "AILGUP"}


def _clean_header_name(text: str) -> str:
    """Normalize Unicode/layout only; semantic OCR correction is LLM work."""
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", text)).strip()


def _spans(page: pymupdf.Page) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for block in page.get_text("dict").get("blocks", []):
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                text = unicodedata.normalize("NFKC", str(span.get("text", ""))).strip()
                bbox = span.get("bbox", (0, 0, 0, 0))
                if text and len(bbox) == 4:
                    result.append({"text": clean_ocr(text), "top": float(bbox[1]), "bottom": float(bbox[3]), "size": float(span.get("size", 0.0))})
    return result


def _header_name(page: pymupdf.Page) -> str:
    spans = [span for span in _spans(page) if float(span["top"]) < _HEADER_MAX_Y]
    candidates = [span for span in spans if str(span["text"]).upper() not in _EXCLUDED_HEADER_TEXT and not re.fullmatch(r"\d+", str(span["text"]).strip())]
    if not candidates:
        return "Hotel non identificato"
    max_size = max(float(span["size"]) for span in candidates)
    name_spans = [span for span in candidates if abs(float(span["size"]) - max_size) < 0.1]
    name = " ".join(str(span["text"]) for span in name_spans)
    name = re.sub(r"\s+", " ", unicodedata.normalize("NFKC", name)).strip()
    return _clean_header_name(name) or "Hotel non identificato"


def _page_text(page: pymupdf.Page) -> str:
    spans = _spans(page)
    return " ".join(str(span["text"]) for span in spans)


def load_pymupdf_hotel_blocks(pdf_path: Path, correct_titles: bool = False) -> list[HotelBlock]:
    """Extract hotel blocks using PyMuPDF while preserving the canonical block type."""
    if not pdf_path.is_file():
        raise FileNotFoundError(f"PDF non trovato: {pdf_path}")
    document = pymupdf.open(pdf_path)
    try:
        pages = [_page_text(page) for page in document]
        starts = [index for index, text in enumerate(pages) if "INQUADRA IL QR" in text.upper()]
        if not starts:
            raise ValueError("Nessuna scheda hotel identificabile nel PDF")
        blocks: list[HotelBlock] = []
        pdfplumber_blocks = __import__("ingestion.pdf_parser", fromlist=["load_hotel_blocks"]).load_hotel_blocks(pdf_path)
        for position, start in enumerate(starts):
            end = starts[position + 1] if position + 1 < len(starts) else len(pages)
            title = _header_name(document[start])
            reference = pdfplumber_blocks[position].title if position < len(pdfplumber_blocks) else ""
            quality = compute_field_confidence(title, reference)
            blocks.append(HotelBlock(title=title, pages=tuple(range(start + 1, end + 1)), text="\n".join(pages[start:end]), quality=quality, header_raw_text=_page_text(document[start]), page_num=start + 1))
        if correct_titles:
            from .gemini_title_corrector import correct_reviewed_titles
            return correct_reviewed_titles(blocks, enabled=True)
        return blocks
    finally:
        document.close()
