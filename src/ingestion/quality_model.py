"""Confidence scoring for cross-extractor PDF validation."""
from __future__ import annotations
import re
from pydantic import BaseModel, Field

class CrossExtractorQuality(BaseModel):
    """Confidence from comparing pdfplumber/PyMuPDF headers — distinct from HotelRecord.quality."""

    overall_confidence: float = Field(ge=0.0, le=1.0)
    field_confidence: dict[str, float] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    needs_review: bool = False


def _normalize_title(value: str) -> str:
    value = value.strip().casefold()
    value = value.replace("★", "").replace("-", " ").replace("'", "")
    return re.sub(r"\s+", " ", value).strip()

_HEADER_STOP_MARKERS = re.compile(r"CATEGORIA\s+UFFICIALE|VALUTAZIONE|INQUADRA\s+IL\s+QR", re.IGNORECASE)
_HEADER_NOISE_TOKENS = {"PUGLIA", "AILGUP", "NOVITA", "NOVITÀ"}


def compute_field_confidence(nome: str, localita: str, header_raw_text: str) -> CrossExtractorQuality:
    """Self-check: every token in the raw header (before the first content marker) must be
    accounted for by either nome or localita. Replaces the old pymupdf-vs-pdfplumber comparison,
    which used the pdfplumber title (itself impastato with locality) as reference and therefore
    could not detect the very defect this scoring exists to catch."""
    warnings: list[str] = []
    if re.search(r'["!�]', nome):
        warnings.append("artefatto_ocr_nel_titolo")
    if not _normalize_title(nome):
        warnings.append("titolo_vuoto")
    if not _normalize_title(localita):
        warnings.append("localita_non_identificata")

    header_before_stop = _HEADER_STOP_MARKERS.split(header_raw_text, maxsplit=1)[0]
    header_tokens = {
        token for token in re.findall(r"[\wÀ-ÖØ-öø-ÿ']+", header_before_stop.upper())
        if not token.isdigit() and token not in _HEADER_NOISE_TOKENS
    }
    covered_tokens = set(re.findall(r"[\wÀ-ÖØ-öø-ÿ']+", f"{nome} {localita}".upper()))
    uncovered = header_tokens - covered_tokens
    if uncovered:
        warnings.append("span_header_non_classificato")

    score = 1.0 if not uncovered and _normalize_title(nome) and _normalize_title(localita) else 0.6
    field_confidence = {"nome": score, "localita": 1.0 if _normalize_title(localita) else 0.0}
    return CrossExtractorQuality(overall_confidence=score, field_confidence=field_confidence, warnings=warnings, needs_review=score < 0.85 or bool(warnings))
