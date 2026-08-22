"""pdfplumber-based PDF reading: text/OCR cleanup and word bounding boxes.

`load_hotel_blocks` is no longer the canonical way to get `nome`/`localita` — that job
now belongs to `pymupdf_parser.load_pymupdf_hotel_blocks`, which is font-size-aware and
calls back into this module only for the `.words` bounding boxes (used later by
`structured_extractor._visual_ratings` to crop the header image for Gemini Vision).
This module's own block segmentation (`_candidate_start`) is kept as the structural
fallback described in the README when a catalogue doesn't have PyMuPDF-friendly headers.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import pdfplumber


@dataclass(frozen=True)
class HotelBlock:
    """One hotel's segment of the PDF. `words` and `locality` are populated differently
    depending on which parser built the block — see pymupdf_parser.py for the canonical path."""

    title: str
    pages: tuple[int, ...]
    text: str
    words: tuple[dict[str, float | int | str], ...] = ()
    locality: str = ""


def clean_ocr(text: str) -> str:
    cleaned = unicodedata.normalize("NFKC", text)
    cleaned = cleaned.translate(str.maketrans({
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u2013": "-",
        "\u2014": "-",
        "\u00a0": " ",
    }))
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return re.sub(r"\s+([,.;:!?])", r"\1", cleaned)


def repair_split_words(text: str) -> tuple[str, float]:
    """Ricompone token separati solo quando il blocco fornisce evidenza locale."""
    tokens = text.split()
    corpus = {match.group(0).casefold() for match in re.finditer(r"\b[\wÀ-ÖØ-öø-ÿ']+\b", text)}
    repairs = 0
    for index in range(len(tokens) - 1):
        left, right = tokens[index], tokens[index + 1]
        left_word = re.sub(r"[^\wÀ-ÖØ-öø-ÿ]", "", left)
        right_word = re.sub(r"[^\wÀ-ÖØ-öø-ÿ]", "", right)
        candidate = (left_word + right_word).casefold()
        if len(left_word) <= 3 and len(right_word) >= 3 and candidate in corpus:
            tokens[index] = left[:-len(left_word)] + left_word + right_word
            tokens[index + 1] = ""
            repairs += 1
    repaired = " ".join(token for token in tokens if token)
    confidence = 1.0 if repairs else 0.0
    return repaired, confidence


def _title_from_page(text: str) -> str:
    header = re.split(r"\s+INQUADRA\s+IL\s+QR", clean_ocr(text), maxsplit=1, flags=re.IGNORECASE)[0]
    header = re.sub(r"^AILGUP\s+\d+\s+", "", header, flags=re.IGNORECASE).strip()
    return header or "Hotel non identificato"


def _candidate_start(text: str) -> bool:
    """Identifica l'inizio di una scheda senza assumere una durata fissa."""
    upper = text.upper()
    has_qr_anchor = "INQUADRA IL QR" in upper
    has_catalogue_code = bool(re.search(r"\b[A-ZÀ-ÖØ-Ý]{3,}\s+\d{1,3}\b", text))
    has_category = "CATEGORIA" in upper
    has_title = _title_from_page(text) != "Hotel non identificato"
    return has_title and (has_qr_anchor or (has_catalogue_code and has_category))


def load_hotel_blocks(pdf_path: Path) -> list[HotelBlock]:
    if not pdf_path.is_file():
        raise FileNotFoundError(f"PDF non trovato: {pdf_path}")
    with pdfplumber.open(pdf_path) as pdf:
        pages = []
        page_words: list[tuple[dict[str, float | int | str], ...]] = []
        for page in pdf.pages:
            raw_text = page.extract_text() or ""
            normalized = clean_ocr(" ".join(raw_text.split()))
            repaired, _ = repair_split_words(normalized)
            pages.append(repaired)
            words = []
            for word in page.extract_words() or []:
                words.append({
                    "text": clean_ocr(str(word.get("text", ""))),
                    "x0": float(word["x0"]),
                    "x1": float(word["x1"]),
                    "top": float(word["top"]),
                    "bottom": float(word["bottom"]),
                    "page": len(pages),
                })
            page_words.append(tuple(words))
    starts = [index for index, page in enumerate(pages) if _candidate_start(page)]
    if not starts:
        raise ValueError("Nessuna scheda hotel identificabile nel PDF")
    blocks: list[HotelBlock] = []
    for position, start in enumerate(starts):
        end = starts[position + 1] if position + 1 < len(starts) else len(pages)
        page_numbers = tuple(range(start + 1, end + 1))
        words = tuple(word for page in page_words[start:end] for word in page)
        blocks.append(HotelBlock(_title_from_page(pages[start]), page_numbers, "\n".join(pages[start:end]), words))
    return blocks


def print_report(pdf_path: Path) -> list[HotelBlock]:
    import sys
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    blocks = load_hotel_blocks(pdf_path)
    print(f"Strutture trovate: {len(blocks)}")
    for block in blocks:
        print(f"- {block.title} | pagine: {', '.join(map(str, block.pages))}")
    return blocks


if __name__ == "__main__":
    import argparse

    from hotelai.logging_setup import configure_logging
    configure_logging()
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf", type=Path)
    print_report(parser.parse_args().pdf)
