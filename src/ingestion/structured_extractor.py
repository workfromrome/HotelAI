"""Canonical HotelRecord extraction: deterministic first pass, conditional LLM review.

Pipeline per hotel block, driven by `extract_block`:
  1. `_offline` builds a record from regex/text heuristics alone (no network call) and
     scores each field's confidence based on real signal (e.g. was a locality actually
     separated out, was a category regex match found).
  2. If `_needs_llm_fallback` says the deterministic confidence is too low (and the caller
     allows it via `use_gemini=True`), `_review_with_llm` re-extracts the whole record with
     Groq first, Gemini as fallback — this is *not* selective per field, the LLM redoes the
     entire record from raw text.
  3. `extract_catalogue` runs this per block and writes both CSV and JSONL; `read_csv` is
     the exact inverse of `write_csv` and is what `search/vector_store.py` calls to import
     the catalogue for indexing (see user-doc/csv-driven-indexing.md for why it re-reads
     the file from disk instead of reusing the in-memory `records` list).
"""
from __future__ import annotations

import json
import logging
import re
import csv
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .pdf_parser import HotelBlock
from .pymupdf_parser import load_pymupdf_hotel_blocks
from hotelai.schemas import HotelRecord
from hotelai.schemas import ExtractionQuality, HotelRating, HotelSource, VisualRatings
from hotelai.config import settings
from hotelai.prompts import load_prompt

logger = logging.getLogger(__name__)

HotelSchema = HotelRecord


def _needs_llm_fallback(record: HotelSchema) -> bool:
    """record.quality.confidence is the *minimum* of all per-field confidences from
    `_offline` — one weak field is enough to trigger a full LLM review of the record."""
    return record.quality.confidence < settings.llm_fallback_confidence_threshold


def _visual_ratings(pdf_path: Path, block: HotelBlock) -> list[HotelRating]:
    """Legge solo il crop dell'intestazione; non invia la pagina intera a Gemini."""
    if not settings.google_api_key or not block.pages or not block.words:
        return []
    from google import genai
    import pdfplumber

    first_page = block.pages[0]
    page_words = [word for word in block.words if word["page"] == first_page]
    if not page_words:
        return []
    top = min(float(word["top"]) for word in page_words)
    bottom = min(float(word["bottom"]) for word in page_words) + 170
    with pdfplumber.open(pdf_path) as pdf:
        page = pdf.pages[first_page - 1]
        crop = page.crop((0, max(0, top - 20), page.width, min(page.height, bottom)))
        image = crop.to_image(resolution=150).original
    response = genai.Client(api_key=settings.google_api_key).models.generate_content(
        model=settings.google_model,
        contents=[
            load_prompt("visual_ratings"),
            image,
        ],
        config={"response_mime_type": "application/json", "response_schema": VisualRatings},
    )
    return VisualRatings.model_validate_json(response.text).ratings


def _header_fields(block: HotelBlock) -> tuple[int | None, list[dict], list[str]]:
    header = block.text
    category_match = re.search(r"CATEGORIA\s+UFFICIALE\s+(?P<stars>[★*]{1,7}|[1-7])S?", header, re.IGNORECASE)
    category = None
    if category_match:
        category = len(category_match.group("stars")) if "★" in category_match.group("stars") else int(category_match.group("stars"))

    evaluations: list[dict] = []
    evaluation_match = re.search(r"VALUTAZIONE\s+(?P<agency>[A-ZÀ-ÖØ-Ý][A-ZÀ-ÖØ-Ý&' -]{1,40}?)(?:\s+(?P<custom>[A-ZÀ-ÖØ-Ý][A-ZÀ-ÖØ-Ý -]{2,30}))?\s+e\s+scopri", header, re.IGNORECASE)
    if evaluation_match:
        agency = evaluation_match.group("agency").strip()
        custom = evaluation_match.group("custom")
        evaluations.append({"ente": agency, "tipo": "generale", "testo_originale": agency})
        if custom:
            evaluations.append({"ente": agency, "tipo": custom.strip().lower(), "testo_originale": custom.strip()})

    qualifiers: list[str] = []
    if "PALACE" in header.upper():
        qualifiers.append("Palace")
    return category, evaluations, qualifiers


def _offline(block: HotelBlock, index: int) -> HotelSchema:
    """Zero-API extraction: `nome`/`localita` come straight from PyMuPDF's font-size
    parsing (already reliable, see pymupdf_parser.py), everything else from regex/keyword
    matching over the raw block text. `field_confidence` scores what was actually
    verified (e.g. `nome_affidabile` is false only for a genuinely short/unresolved title,
    not just because this pass is deterministic) — that's what feeds `_needs_llm_fallback`."""
    text = block.text.lower()
    title = block.title
    locality = block.locality.title() if block.locality else "Non specificata"
    treatment = next((term for term in ("tutto incluso", "pensione completa", "mezza pensione", "pernottamento e prima colazione") if term in text), None)
    category, evaluations, qualifiers = _header_fields(block)
    issues = []
    nome_affidabile = len(title.split()) >= 2 and title != "Hotel non identificato"
    if not nome_affidabile:
        issues.append("nome_breve")
    if not block.locality:
        issues.append("localita_non_separata")
    field_confidence = {
        "nome": 0.9 if nome_affidabile else 0.3,
        "localita": 0.9 if block.locality else 0.2,
        "categoria_ufficiale": 0.95 if category is not None else 0.2,
        "valutazioni": 0.7 if evaluations else 0.2,
        "qualificatori": 0.9 if qualifiers else 0.8,
        "source_pages": 1.0 if block.pages else 0.0,
    }
    record_confidence = min(field_confidence.values())
    return HotelSchema(
        id=f"hotel-{index:03d}", nome=title, localita=locality, source_pages=list(block.pages),
        stelle=(re.search(r"CATEGORIA UFFICIALE\s+(.+?)\s+VALUTAZIONE", block.text, re.I) or [None, None])[1],
        categoria_ufficiale=category,
        valutazioni=evaluations,
        qualificatori=qualifiers,
        trattamento_principale=treatment,
        pet_friendly="pet friendly" in text or "amici a 4 zampe" in text or "animali" in text,
        ha_piscina="piscina" in text, ha_spa="spa" in text or "centro benessere" in text,
        ha_biberoneria="biberoneria" in text,
        caratteristiche_chiave=[term for term in ("spiaggia", "family", "parcheggio", "animazione", "mare") if term in text],
        source={"pages": list(block.pages), "raw_text": block.text},
        quality={
            "confidence": record_confidence,
            "needs_review": record_confidence < 0.7 or bool(issues),
            "issues": issues,
            "field_confidence": field_confidence,
        },
    )


class HotelReview(BaseModel):
    """Campi che l'LLM di revisione deve determinare dal testo della scheda.

    Sottoinsieme di HotelSchema: esclude id/source_pages/source/quality perché
    extract_block li ricalcola sempre dal block PDF originale. quality.field_confidence
    (dict a chiavi libere) è escluso anche perché non rappresentabile nello schema
    strutturato di Gemini (rifiuta additionalProperties).
    """

    model_config = ConfigDict(extra="ignore")

    nome: str
    localita: str | None = "Non specificata"
    stelle: str | None = None
    categoria_ufficiale: int | None = Field(default=None, ge=1, le=7)
    valutazioni: list[HotelRating] = Field(default_factory=list)
    qualificatori: list[str] = Field(default_factory=list)
    trattamento_principale: str | None = None
    pet_friendly: bool = False
    ha_piscina: bool = False
    ha_spa: bool = False
    ha_biberoneria: bool = False
    caratteristiche_chiave: list[str] = Field(default_factory=list)


_REVIEW_EXAMPLE = HotelReview(
    nome="NOME COMMERCIALE HOTEL",
    localita="Città",
    stelle="4",
    categoria_ufficiale=4,
    valutazioni=[HotelRating(ente="Es. TripAdvisor", tipo="generale", punteggio=4, massimo=5, testo_originale="testo originale se presente nella scheda")],
    qualificatori=["Palace"],
    trattamento_principale="pensione completa",
    ha_piscina=True,
    caratteristiche_chiave=["spiaggia", "family"],
).model_dump_json(indent=2)

_REVIEW_PROMPT = load_prompt("structured_review").format(example=_REVIEW_EXAMPLE)


def _get_groq_client() -> Any | None:
    if not settings.groq_api_key:
        return None
    from groq import Groq

    return Groq(api_key=settings.groq_api_key)


def _get_gemini_client() -> Any | None:
    if not settings.google_api_key:
        return None
    from google import genai

    return genai.Client(api_key=settings.google_api_key)


def _groq_review(client: Any, block_text: str) -> HotelReview:
    response = client.chat.completions.create(
        model=settings.groq_model,
        messages=[
            {"role": "system", "content": _REVIEW_PROMPT},
            {"role": "user", "content": f"TESTO SCHEDA:\n{block_text}"},
        ],
        response_format={"type": "json_object"},
    )
    return HotelReview.model_validate_json(response.choices[0].message.content)


def _gemini_review(client: Any, block_text: str) -> HotelReview:
    response = client.models.generate_content(
        model=settings.google_model,
        contents=f"{_REVIEW_PROMPT}\n\nTESTO SCHEDA:\n{block_text}",
        config={"response_mime_type": "application/json", "response_schema": HotelReview},
    )
    return HotelReview.model_validate_json(response.text)


def _review_with_llm(
    block_text: str, groq_client: Any | None = None, gemini_client: Any | None = None
) -> tuple[HotelReview, str] | None:
    """Cascade Groq -> Gemini per la revisione dei record a bassa confidenza. Non solleva mai eccezioni."""
    client = groq_client if groq_client is not None else _get_groq_client()
    if client is not None:
        try:
            return _groq_review(client, block_text), "estratto_con_groq_testuale"
        except Exception as exc:
            logger.warning("Review Groq fallita, fallback su Gemini: %s", exc)

    client = gemini_client if gemini_client is not None else _get_gemini_client()
    if client is not None:
        try:
            return _gemini_review(client, block_text), "estratto_con_gemini_testuale"
        except Exception as exc:
            logger.warning("Review Gemini fallita: %s", exc)

    return None


def extract_block(
    block: HotelBlock,
    index: int,
    use_gemini: bool = True,
    pdf_path: Path | None = None,
    groq_client: Any | None = None,
    gemini_client: Any | None = None,
) -> HotelSchema:
    """Deterministic extraction, promoted to an LLM review only when confidence is low.
    Never raises: an unreachable/failed LLM cascade falls back to the deterministic
    record, tagged with `review_llm_non_disponibile` (see `needs_llm_review_warning`)."""
    deterministic = _offline(block, index)
    if not use_gemini or not _needs_llm_fallback(deterministic):
        return deterministic

    reviewed = _review_with_llm(block.text, groq_client, gemini_client)
    if reviewed is None:
        return deterministic.model_copy(update={
            "quality": ExtractionQuality(
                **{
                    **deterministic.quality.model_dump(),
                    "issues": [*deterministic.quality.issues, "review_llm_non_disponibile"],
                }
            ),
        })
    review, provider_issue = reviewed

    # The LLM found rating agencies (e.g. "BRAVO") but no numeric score in the text — that
    # usually means the score is only shown as a visual badge/graphic in the PDF, so fall
    # back to a targeted Gemini Vision crop of just the header (see _visual_ratings above).
    valutazioni = review.valutazioni
    if bool(valutazioni) and all(r.punteggio is None for r in valutazioni):
        try:
            visual = _visual_ratings(pdf_path, block) if pdf_path is not None else []
        except Exception:
            visual = []
        if visual:
            valutazioni = visual

    return HotelSchema(
        id=f"hotel-{index:03d}",
        nome=review.nome,
        localita=review.localita or "Non specificata",
        stelle=review.stelle,
        categoria_ufficiale=review.categoria_ufficiale,
        valutazioni=valutazioni,
        qualificatori=review.qualificatori,
        trattamento_principale=review.trattamento_principale,
        pet_friendly=review.pet_friendly,
        ha_piscina=review.ha_piscina,
        ha_spa=review.ha_spa,
        ha_biberoneria=review.ha_biberoneria,
        caratteristiche_chiave=review.caratteristiche_chiave,
        source_pages=list(block.pages),
        source=HotelSource(pages=list(block.pages), raw_text=block.text),
        quality=ExtractionQuality(confidence=1.0, needs_review=False, issues=[provider_issue]),
    )


def extract_catalogue(
    pdf_path: Path,
    output_path: Path,
    use_gemini: bool = True,
    groq_client: Any | None = None,
    gemini_client: Any | None = None,
) -> list[HotelSchema]:
    """Entry point used by scripts/run_pipeline.py and the /api/ingest endpoint:
    PDF -> blocks (pymupdf_parser) -> per-block extract_block -> CSV + JSONL on disk."""
    records = [
        extract_block(block, index, use_gemini, pdf_path, groq_client, gemini_client)
        for index, block in enumerate(load_pymupdf_hotel_blocks(pdf_path), 1)
    ]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    write_csv(records, output_path)
    write_jsonl(records, output_path.with_suffix(".jsonl"))
    return records


def needs_llm_review_warning(records: list[HotelSchema]) -> bool:
    """True se almeno un record necessitava di revisione LLM ma Groq e Gemini erano entrambi non disponibili."""
    return any("review_llm_non_disponibile" in record.quality.issues for record in records)


def write_jsonl(records: list[HotelSchema], output_path: Path) -> None:
    with output_path.open("w", encoding="utf-8") as file:
        for record in records:
            file.write(json.dumps(record.model_dump(mode="json"), ensure_ascii=False) + "\n")


def write_csv(records: list[HotelSchema], output_path: Path) -> None:
    fields = list(HotelSchema.model_fields)
    with output_path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        for record in records:
            row = record.model_dump(mode="json")
            for field, value in row.items():
                if isinstance(value, (list, dict)):
                    row[field] = json.dumps(value, ensure_ascii=False)
            writer.writerow(row)


_CSV_JSON_LIST_FIELDS = ("valutazioni", "qualificatori", "caratteristiche_chiave", "source_pages")
_CSV_JSON_DICT_FIELDS = ("source", "quality")
_CSV_INT_FIELDS = ("categoria_ufficiale",)
_CSV_BOOL_FIELDS = ("pet_friendly", "ha_piscina", "ha_spa", "ha_biberoneria")


def read_csv(input_path: Path) -> list[HotelSchema]:
    """Inverso di write_csv: è il punto in cui l'indicizzazione importa davvero il CSV esportato."""
    with input_path.open(encoding="utf-8") as file:
        rows = list(csv.DictReader(file))
    records = []
    for row in rows:
        data: dict = dict(row)
        for field in _CSV_JSON_LIST_FIELDS:
            data[field] = json.loads(data[field]) if data.get(field) else []
        for field in _CSV_JSON_DICT_FIELDS:
            data[field] = json.loads(data[field]) if data.get(field) else {}
        for field in _CSV_INT_FIELDS:
            data[field] = int(data[field]) if data.get(field) else None
        for field in _CSV_BOOL_FIELDS:
            data[field] = data.get(field) == "True"
        records.append(HotelSchema.model_validate(data))
    return records


if __name__ == "__main__":
    import argparse
    import sys
    from hotelai.logging_setup import configure_logging
    configure_logging()
    if hasattr(sys.stdout, "reconfigure"): sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(); parser.add_argument("pdf", type=Path); parser.add_argument("output", type=Path); parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    records = extract_catalogue(args.pdf, args.output, not args.offline)
    print(f"Record estratti: {len(records)}")
    print(json.dumps([r.model_dump() for r in records[:3]], ensure_ascii=False, indent=2))
