"""Targeted title correction for needs_review blocks.

Groq (`openai/gpt-oss-120b`) is the default provider because its free-tier daily
quota is far higher than Gemini's; Gemini is used as a fallback when Groq is not
configured or its retries are exhausted (rate limit or service unavailable).

Real responses previously obtained from a provider can be cached by raw title in
`settings.llm_cache_path` (see `tests/fixtures/llm_cached_responses.json`); a cache
hit short-circuits both providers so cassette-style tests run with zero API calls.
"""
from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable, Sequence

from pydantic import BaseModel, Field

from fde_hotel_rag.config import settings

logger = logging.getLogger(__name__)


class GeminiTitleCorrectionPayload(BaseModel):
    corrected_title: str
    was_corrected: bool
    explanation: str = Field(default="")


# Compatibility alias for existing callers and tests.
TitleCorrectionResult = GeminiTitleCorrectionPayload

_TITLE_CORRECTION_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "corrected_title": {"type": "string"},
        "was_corrected": {"type": "boolean"},
        "explanation": {"type": "string"},
    },
    "required": ["corrected_title", "was_corrected", "explanation"],
    "additionalProperties": False,
}


def _load_cached_responses() -> dict[str, dict[str, object]]:
    path = settings.llm_cache_path
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Impossibile leggere la cache LLM %s: %s", path, exc)
        return {}


def is_groq_enabled() -> bool:
    return bool(settings.groq_api_key)


def is_gemini_enabled() -> bool:
    return bool(settings.google_api_key)


GENERIC_TITLE_CORRECTOR_PROMPT = """Sei un sistema esperto di data-cleaning e ricostruzione di testo per cataloghi turistici e ricettivi in lingua italiana.

### CONTESTO E TASK
Ti viene fornito un titolo di hotel estratto da PDF che contiene artefatti causati da font custom o errori di decodifica vettoriale/OCR (virgolette isolate ", punti esclamativi a metà parola !, spazi anomali o lettere tronche).
Il tuo compito è ricostruire il nome proprio corretto dell'hotel usando esclusivamente il testo fornito (titolo grezzo ed header di pagina), senza aggiungere località, categoria, servizi o altre informazioni non presenti nel testo.

### REGOLE TASSATIVE DI RICOSTRUZIONE
1. DIVIETO DI TRONCAMENTO: non eliminare mai parole o token solo perché contengono caratteri di rumore (", !). Ricostruisci la parola corretta anziché rimuoverla.
2. RICOSTRUZIONE LINGUISTICA: le virgolette " o ! all'interno di una parola rappresentano caratteri o legature mancanti. Completa le parole tronche mantenendo la tipologia di struttura suggerita dal contesto (es. Villaggio, Palace, Resort, Club, Spa) coerente con il resto del titolo.
3. USO DEL CONTESTO: usa l'header di pagina fornito per disambiguare il nome del brand quando il titolo grezzo è ambiguo o incompleto.
4. NESSUNA INVENZIONE: correggi solo artefatti tipografici/OCR; non introdurre parole non supportate dal testo fornito.
5. FORMATTAZIONE: restituisci il nome con spaziatura pulita, senza virgolette o punti esclamativi spuri.

Restituisci sempre un JSON conforme allo schema richiesto."""


def _correction_user_content(raw_title: str, header_text: str, page_num: int) -> str:
    return f"Pagina: {page_num}\nTitolo grezzo: {raw_title}\nHeader completo: {header_text}"


def _call_groq(raw_title: str, header_text: str, page_num: int) -> GeminiTitleCorrectionPayload:
    from groq import Groq

    client = Groq(api_key=settings.groq_api_key)
    response = client.chat.completions.create(
        model=settings.groq_model,
        messages=[
            {"role": "system", "content": GENERIC_TITLE_CORRECTOR_PROMPT},
            {"role": "user", "content": _correction_user_content(raw_title, header_text, page_num)},
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {"name": "title_correction", "strict": True, "schema": _TITLE_CORRECTION_JSON_SCHEMA},
        },
    )
    return GeminiTitleCorrectionPayload.model_validate_json(response.choices[0].message.content or "{}")


def _call_gemini(raw_title: str, header_text: str, page_num: int) -> GeminiTitleCorrectionPayload:
    from google import genai

    client = genai.Client(api_key=settings.google_api_key)
    response = client.models.generate_content(
        model=settings.google_model,
        contents=_correction_user_content(raw_title, header_text, page_num),
        config={
            "response_mime_type": "application/json",
            "response_schema": GeminiTitleCorrectionPayload,
            "system_instruction": GENERIC_TITLE_CORRECTOR_PROMPT,
        },
    )
    return GeminiTitleCorrectionPayload.model_validate_json(response.text)


def _is_retryable(exc: Exception) -> bool:
    status = getattr(exc, "status_code", None) or getattr(exc, "code", None)
    message = str(exc).upper()
    return (
        status in (429, 503)
        or "429" in message
        or "503" in message
        or "TOO MANY REQUESTS" in message
        or "UNAVAILABLE" in message
    )


def _call_with_backoff(
    call: Callable[[], GeminiTitleCorrectionPayload], requests_per_minute: int, provider: str, page_num: int
) -> GeminiTitleCorrectionPayload | None:
    """Run a single provider's call with backoff aligned to *that provider's own* RPM limit.

    Each provider gets its own timer derived from its configured RPM, so Groq (30 RPM)
    and Gemini (5 RPM) never share a backoff schedule. Returns None only when retries are
    exhausted or the failure is not retryable (429/503); the caller decides what to try next.
    """
    min_interval = 60.0 / requests_per_minute
    delays = tuple(min_interval * (2**attempt) for attempt in range(3))
    for attempt, delay in enumerate(delays, 1):
        try:
            result = call()
            time.sleep(min_interval)
            return result
        except Exception as exc:
            if not _is_retryable(exc) or attempt == len(delays):
                logger.warning("%s title correction failed for page %s: %s", provider, page_num, exc)
                return None
            time.sleep(max(delay, min_interval))
    return None


def correct_hotel_title(raw_title: str, header_text: str, page_num: int) -> TitleCorrectionResult:
    """Correct one title. Checks the local cache first, then tries Groq, then Gemini, then the raw title."""
    cached = _load_cached_responses().get(raw_title)
    if cached is not None:
        return GeminiTitleCorrectionPayload.model_validate(cached)

    if is_groq_enabled():
        result = _call_with_backoff(
            lambda: _call_groq(raw_title, header_text, page_num), settings.groq_requests_per_minute, "Groq", page_num
        )
        if result is not None:
            return result
        logger.warning("Groq non disponibile per pagina %s, fallback su Gemini", page_num)

    if is_gemini_enabled():
        result = _call_with_backoff(
            lambda: _call_gemini(raw_title, header_text, page_num),
            settings.gemini_requests_per_minute,
            "Gemini",
            page_num,
        )
        if result is not None:
            return result

    logger.warning("Nessun provider di correzione titolo disponibile per pagina %s, uso il titolo grezzo", page_num)
    return GeminiTitleCorrectionPayload(
        corrected_title=raw_title, was_corrected=False, explanation="Fallback locale: nessun provider disponibile"
    )


def correct_reviewed_titles(blocks: Sequence[object], enabled: bool = True) -> list[object]:
    """Correct only blocks explicitly marked for review; return immutable replacements."""
    from dataclasses import replace

    corrected: list[object] = []
    for block in blocks:
        quality = getattr(block, "quality", None)
        if not enabled or not quality or not quality.needs_review:
            corrected.append(block)
            continue
        result = correct_hotel_title(
            getattr(block, "title"),
            getattr(block, "header_raw_text", getattr(block, "title", "")),
            getattr(block, "page_num", getattr(block, "pages")[0]),
        )
        if result.was_corrected:
            updated_quality = quality.model_copy(
                update={"needs_review": False, "warnings": [*quality.warnings, f"Titolo corretto automaticamente: {result.explanation}"]}
            )
            corrected.append(replace(block, title=result.corrected_title, quality=updated_quality))
        else:
            corrected.append(block)
    return corrected
