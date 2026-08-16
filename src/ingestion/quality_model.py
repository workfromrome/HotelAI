"""Confidence scoring for cross-extractor PDF validation."""
from __future__ import annotations
import re
from difflib import SequenceMatcher
from pydantic import BaseModel, Field

class ExtractionQuality(BaseModel):
    overall_confidence: float = Field(ge=0.0, le=1.0)
    field_confidence: dict[str, float] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    needs_review: bool = False

def compute_field_confidence(val_pymupdf: str, val_pdfplumber: str) -> ExtractionQuality:
    left = " ".join(val_pymupdf.split()).strip().casefold()
    right = " ".join(val_pdfplumber.split()).strip().casefold()
    similarity = SequenceMatcher(None, left, right).ratio() if left and right else 0.0
    warnings: list[str] = []
    if re.search(r'["!�]', val_pymupdf): warnings.append("artefatto_ocr_nel_titolo")
    if re.search(r"\s{2,}", val_pymupdf): warnings.append("spaziatura_anomala")
    if not left: warnings.append("titolo_vuoto")
    score = round(similarity, 4)
    return ExtractionQuality(overall_confidence=score, field_confidence={"nome": score}, warnings=warnings, needs_review=score < 0.85 or bool(warnings))
