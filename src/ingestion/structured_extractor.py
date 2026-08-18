from __future__ import annotations

import json
import re
import csv
from pathlib import Path

from .pdf_parser import HotelBlock
from .pymupdf_parser import load_pymupdf_hotel_blocks
from fde_hotel_rag.schemas import HotelRecord
from fde_hotel_rag.schemas import HotelRating, VisualRatings
from fde_hotel_rag.config import settings

HotelSchema = HotelRecord


def _needs_llm_fallback(record: HotelSchema) -> bool:
    return record.quality.confidence < settings.llm_fallback_confidence_threshold


def _needs_visual_fallback(record: HotelSchema) -> bool:
    return bool(record.valutazioni) and all(r.punteggio is None for r in record.valutazioni)


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
            "Leggi solo le valutazioni visuali nell'immagine. Restituisci JSON. "
            "Se il punteggio non è leggibile, usa null. Non inventare valori.",
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
    text = block.text.lower()
    title = block.title
    locality = block.locality.title() if block.locality else "Non specificata"
    treatment = next((term for term in ("tutto incluso", "pensione completa", "mezza pensione", "pernottamento e prima colazione") if term in text), None)
    category, evaluations, qualifiers = _header_fields(block)
    issues = []
    if len(title.split()) < 2:
        issues.append("nome_breve")
    if not block.locality:
        issues.append("localita_non_separata")
    field_confidence = {
        "nome": 0.45,
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


def extract_block(block: HotelBlock, index: int, use_gemini: bool = True, pdf_path: Path | None = None) -> HotelSchema:
    deterministic = _offline(block, index)
    if not use_gemini or not settings.google_api_key or not _needs_llm_fallback(deterministic):
        return deterministic
    from google import genai
    client = genai.Client(api_key=settings.google_api_key)
    prompt = (
        "Estrai una scheda hotel in italiano usando esclusivamente il testo fornito. "
        "Se un valore non è verificabile, usa null o una lista vuota. "
        "Separa nome commerciale e località. Non correggere nomi sulla base di conoscenza esterna."
    )
    try:
        response = client.models.generate_content(
            model=settings.google_model,
            contents=f"{prompt}\n\nTESTO SCHEDA:\n{block.text}",
            config={"response_mime_type": "application/json", "response_schema": HotelSchema},
        )
        extracted = HotelSchema.model_validate_json(response.text)
    except Exception as exc:
        raise RuntimeError("Fallback Gemini fallito durante l'estrazione strutturata") from exc
    if _needs_visual_fallback(extracted):
        try:
            visual = _visual_ratings(pdf_path, block) if pdf_path is not None else []
        except Exception:
            visual = []
        if visual:
            extracted = extracted.model_copy(update={"valutazioni": visual})
    return extracted.model_copy(update={
        "id": f"hotel-{index:03d}",
        "source_pages": list(block.pages),
        "source": {"pages": list(block.pages), "raw_text": block.text},
        "quality": {
            **extracted.quality.model_dump(),
            "issues": [*extracted.quality.issues, "estratto_con_gemini_testuale"],
        },
    })


def extract_catalogue(pdf_path: Path, output_path: Path, use_gemini: bool = True) -> list[HotelSchema]:
    records = [extract_block(block, index, use_gemini, pdf_path) for index, block in enumerate(load_pymupdf_hotel_blocks(pdf_path), 1)]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    write_csv(records, output_path)
    write_jsonl(records, output_path.with_suffix(".jsonl"))
    return records


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


if __name__ == "__main__":
    import argparse
    import sys
    if hasattr(sys.stdout, "reconfigure"): sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(); parser.add_argument("pdf", type=Path); parser.add_argument("output", type=Path); parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    records = extract_catalogue(args.pdf, args.output, not args.offline)
    print(f"Record estratti: {len(records)}")
    print(json.dumps([r.model_dump() for r in records[:3]], ensure_ascii=False, indent=2))
