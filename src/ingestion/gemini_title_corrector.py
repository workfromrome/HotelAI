"""Targeted Gemini correction for low-confidence hotel titles."""
from __future__ import annotations

import time
from collections.abc import Sequence

from pydantic import BaseModel, Field

from fde_hotel_rag.config import settings


class TitleCorrectionResult(BaseModel):
    corrected_title: str
    was_corrected: bool
    explanation: str = Field(default="")


def is_gemini_enabled() -> bool:
    return bool(settings.google_api_key)


def correct_hotel_title(raw_title: str, header_text: str, page_num: int) -> TitleCorrectionResult:
    if not is_gemini_enabled():
        raise RuntimeError("GOOGLE_API_KEY non è configurata")
    from google import genai

    prompt = (
        "Sei un esperto di data-cleaning e OCR per cataloghi turistici italiani. "
        "Ricostruisci il nome proprio corretto dell'hotel usando esclusivamente il testo fornito. "
        "Non aggiungere località, categoria, servizi o informazioni inventate. "
        "Correggi solo artefatti tipografici/OCR. Restituisci JSON conforme allo schema.\n\n"
        f"Pagina: {page_num}\nTitolo grezzo: {raw_title}\nHeader completo: {header_text}"
    )
    client = genai.Client(api_key=settings.google_api_key)
    response = client.models.generate_content(
        model=settings.google_model,
        contents=prompt,
        config={"response_mime_type": "application/json", "response_schema": TitleCorrectionResult},
    )
    result = TitleCorrectionResult.model_validate_json(response.text)
    time.sleep(settings.request_delay_seconds)
    return result


def correct_reviewed_titles(blocks: Sequence[object], enabled: bool = True) -> list[object]:
    """Correct only blocks explicitly marked for review; return immutable replacements."""
    from dataclasses import replace

    corrected: list[object] = []
    for block in blocks:
        quality = getattr(block, "quality", None)
        if not enabled or not quality or not quality.needs_review:
            corrected.append(block)
            continue
        result = correct_hotel_title(getattr(block, "title"), getattr(block, "header_raw_text", getattr(block, "title", "")), getattr(block, "page_num", getattr(block, "pages")[0]))
        if result.was_corrected:
            updated_quality = quality.model_copy(update={"needs_review": False, "warnings": [*quality.warnings, f"Titolo corretto da Gemini: {result.explanation}"]})
            corrected.append(replace(block, title=result.corrected_title, quality=updated_quality))
        else:
            corrected.append(block)
    return corrected
