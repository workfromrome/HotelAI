"""Font-size aware PyMuPDF extractor: canonical source of nome/localita for structured_extractor."""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path

import pymupdf

from .pdf_parser import HotelBlock


def _load_word_list(name: str) -> set[str]:
    """Legge <name>.txt da pdf_artifacts/: una parola per riga, maiuscole; righe
    vuote o che iniziano con # sono ignorate. Tenuto qui (non in un modulo
    condiviso) perche' e' l'unico chiamante."""
    path = Path(__file__).parent / "pdf_artifacts" / f"{name}.txt"
    return {
        line.strip().upper()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    }


_EXCLUDED_HEADER_TEXT = _load_word_list("excluded_header_text")
_EXCLUDED_BADGE_WORDS = _load_word_list("excluded_badge_words")
_STOP_MARKERS = re.compile(r"CATEGORIA\s+UFFICIALE|VALUTAZIONE|INQUADRA\s+IL\s+QR", re.IGNORECASE)

# Il font decorativo dei titoli rende la coppia di lettere "LA" come un unico glifo,
# che PyMuPDF estrae come span isolato con testo '"' o '!' (nessuna corrispondenza Unicode
# reale). Osservato in modo identico su GATTAREL[LA], PA[LA]CE, DANIE[LA], CINTO[LA],
# VIL[LA]GGIO, THA[LA]S: sempre "LA", mai altro. Sostituzione a livello di span, perche'
# qui sappiamo che lo span appartiene al font del titolo.
_LIGATURE_GLYPHS = {'"', "!"}


def _substitute_ligature_glyphs(spans: list[dict[str, object]]) -> list[dict[str, object]]:
    return [
        {**span, "text": "LA"} if str(span["text"]).strip() in _LIGATURE_GLYPHS else span
        for span in spans
    ]


def _join_header_text(spans: list[dict[str, object]]) -> str:
    """Concatena gli span preservando la spaziatura interna (PyMuPDF la incorpora gia'
    nel testo dello span, es. 'GGIO ' o ' RESORT'); tra righe diverse (top differente)
    inserisce uno spazio, perche' un a-capo nel titolo corrisponde a uno spazio logico."""
    parts: list[str] = []
    previous_top: float | None = None
    for span in spans:
        top = round(float(span["top"]), 1)
        if parts and top != previous_top:
            parts.append(" ")
        parts.append(str(span["text"]))
        previous_top = top
    return "".join(parts)


def _clean_header_name(text: str) -> str:
    """Normalize Unicode/layout only; semantic OCR correction is LLM work."""
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", text)).strip()


def _spans(page: pymupdf.Page) -> list[dict[str, object]]:
    """Testo NFKC-normalizzato ma NON strippato: lo spazio iniziale/finale di uno span
    (es. ' RESORT', 'GGIO ') e' l'unico segnale di spaziatura reale disponibile qui, perche'
    i gap x0/x1 fra span consecutivi risultano quasi sempre 0 anche fra parole distinte."""
    result: list[dict[str, object]] = []
    for block in page.get_text("dict").get("blocks", []):
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                text = unicodedata.normalize("NFKC", str(span.get("text", "")))
                bbox = span.get("bbox", (0, 0, 0, 0))
                if text.strip() and len(bbox) == 4:
                    result.append({"text": text, "top": float(bbox[1]), "bottom": float(bbox[3]), "size": float(span.get("size", 0.0))})
    return result


def _page_text(page: pymupdf.Page) -> str:
    spans = _spans(page)
    return " ".join(str(span["text"]) for span in spans)


def _drop_badge_words(spans: list[dict[str, object]]) -> list[dict[str, object]]:
    """Reassemble consecutive single-letter spans (vertical badges like N O V I T À) and drop them if they spell an excluded badge word."""
    kept: list[dict[str, object]] = []
    index = 0
    while index < len(spans):
        span = spans[index]
        text = str(span["text"]).strip()
        if len(text) == 1 and text.isalpha():
            run = [span]
            probe = index + 1
            while (
                probe < len(spans)
                and len(str(spans[probe]["text"]).strip()) == 1
                and str(spans[probe]["text"]).strip().isalpha()
                and abs(float(spans[probe]["size"]) - float(span["size"])) < 0.1
            ):
                run.append(spans[probe])
                probe += 1
            word = "".join(str(item["text"]).strip() for item in run).upper()
            if word in _EXCLUDED_BADGE_WORDS:
                index = probe
                continue
        kept.append(span)
        index += 1
    return kept


def _header_spans(page: pymupdf.Page) -> list[dict[str, object]]:
    """Header spans in document order, stopping at the first content marker (no fixed Y cutoff: page layouts vary)."""
    spans = sorted(_spans(page), key=lambda span: float(span["top"]))
    header: list[dict[str, object]] = []
    for span in spans:
        text = str(span["text"]).strip()
        if not text:
            continue
        if _STOP_MARKERS.search(text.upper()):
            break
        if text.upper() in _EXCLUDED_HEADER_TEXT or re.fullmatch(r"\d+", text):
            continue
        header.append(span)
    return _substitute_ligature_glyphs(_drop_badge_words(header))


def _header_name_and_locality(page: pymupdf.Page) -> tuple[str, str]:
    """Nome = largest header font-size cluster; localita = the next-largest distinct cluster."""
    spans = _header_spans(page)
    if not spans:
        return "Hotel non identificato", ""
    sizes = sorted({round(float(span["size"]), 1) for span in spans}, reverse=True)
    max_size = sizes[0]
    name_spans = [span for span in spans if round(float(span["size"]), 1) == max_size]
    name = _clean_header_name(_join_header_text(name_spans)) or "Hotel non identificato"
    locality = ""
    if len(sizes) > 1:
        second_size = sizes[1]
        locality_spans = [span for span in spans if round(float(span["size"]), 1) == second_size]
        locality = _clean_header_name(_join_header_text(locality_spans))
    return name, locality


def load_pymupdf_hotel_blocks(pdf_path: Path) -> list[HotelBlock]:
    """Extract hotel blocks using PyMuPDF's font-size-aware header parsing (canonical nome/localita source).

    Blocks start at "INQUADRA IL QR" markers (each hotel page has this QR-code caption),
    not at pdf_parser.py's own `_candidate_start` heuristic — the two parsers can disagree
    on block boundaries. `.words` still comes from pdf_parser.load_hotel_blocks, matched
    to this function's blocks by list position (both parsers are expected to find the same
    19 hotels in the same order; if that ever drifts, `.words` would map to the wrong block).
    """
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
            title, locality = _header_name_and_locality(document[start])
            reference = pdfplumber_blocks[position] if position < len(pdfplumber_blocks) else None
            blocks.append(HotelBlock(
                title=title,
                pages=tuple(range(start + 1, end + 1)),
                text="\n".join(pages[start:end]),
                words=reference.words if reference is not None else (),
                locality=locality,
            ))
        return blocks
    finally:
        document.close()
