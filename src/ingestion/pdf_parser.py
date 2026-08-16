from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import pdfplumber
from .quality_model import ExtractionQuality


@dataclass(frozen=True)
class HotelBlock:
    title: str
    pages: tuple[int, ...]
    text: str
    lines: tuple[str, ...] = ()
    words: tuple[dict[str, float | int | str], ...] = ()
    segmentation_confidence: float = 0.0
    segmentation_issues: tuple[str, ...] = ()
    quality: ExtractionQuality | None = None
    header_raw_text: str = ""
    page_num: int = 0


_OCR_REPLACEMENTS = {
    "GATTAREL!": "GATTARELLA",
    "PA!CE": "PALACE",
    'DANIE"': "DANIELI",
    'CINTO"': "CINTOLA",
    "VIL!GGIO": "VILLAGGIO",
    "THA\"S": "THB'S",
}


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
    for source, target in _OCR_REPLACEMENTS.items():
        cleaned = cleaned.replace(source, target)
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


def _candidate_start(text: str) -> tuple[bool, float, tuple[str, ...]]:
    """Identifica l'inizio di una scheda senza assumere una durata fissa."""
    upper = text.upper()
    has_qr_anchor = "INQUADRA IL QR" in upper
    has_catalogue_code = bool(re.search(r"\b[A-ZÀ-ÖØ-Ý]{3,}\s+\d{1,3}\b", text))
    has_category = "CATEGORIA" in upper
    has_title = _title_from_page(text) != "Hotel non identificato"
    signals = sum((has_qr_anchor, has_catalogue_code, has_category, has_title))
    issues: list[str] = []
    if not has_qr_anchor:
        issues.append("ancora_qr_assente")
    if not has_title:
        issues.append("titolo_non_identificato")
    return has_title and (has_qr_anchor or (has_catalogue_code and has_category)), signals / 4, tuple(issues)


def load_hotel_blocks(pdf_path: Path) -> list[HotelBlock]:
    if not pdf_path.is_file():
        raise FileNotFoundError(f"PDF non trovato: {pdf_path}")
    with pdfplumber.open(pdf_path) as pdf:
        pages = []
        page_lines: list[tuple[str, ...]] = []
        page_words: list[tuple[dict[str, float | int | str], ...]] = []
        for page in pdf.pages:
            raw_text = page.extract_text() or ""
            lines = tuple(clean_ocr(line) for line in raw_text.splitlines() if line.strip())
            normalized = clean_ocr(" ".join(raw_text.split()))
            repaired, _ = repair_split_words(normalized)
            pages.append(repaired)
            page_lines.append(lines)
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
    candidates = [_candidate_start(page) for page in pages]
    starts = [index for index, (is_start, _, _) in enumerate(candidates) if is_start]
    if not starts:
        raise ValueError("Nessuna scheda hotel identificabile nel PDF")
    blocks: list[HotelBlock] = []
    for position, start in enumerate(starts):
        end = starts[position + 1] if position + 1 < len(starts) else len(pages)
        page_numbers = tuple(range(start + 1, end + 1))
        lines = tuple(line for page in page_lines[start:end] for line in page)
        words = tuple(word for page in page_words[start:end] for word in page)
        _, confidence, issues = candidates[start]
        blocks.append(HotelBlock(_title_from_page(pages[start]), page_numbers, "\n".join(pages[start:end]), lines, words, confidence, issues))
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
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf", type=Path)
    print_report(parser.parse_args().pdf)
