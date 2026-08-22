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
     the catalogue for indexing (see presentation-notes/csv-driven-indexing.md, local-only,
     for why it re-reads the file from disk instead of reusing the in-memory `records` list).
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


def _header_fields(block: HotelBlock) -> tuple[int | None, list[dict]]:
    header = block.text
    category_match = re.search(r"CATEGORIA\s+UFFICIALE\s+(?P<stars>[★*]{1,7}|[1-7])S?", header, re.IGNORECASE)
    category = None
    if category_match:
        category = len(category_match.group("stars")) if "★" in category_match.group("stars") else int(category_match.group("stars"))

    evaluations: list[dict] = []
    # Il gruppo non catturante dopo l'ente assorbe il badge decorativo che il PDF stampa tra
    # il nome dell'ente e "e scopri" (es. "ANIMAZIONE", "N O V I T À" spaziata lettera per
    # lettera) e la call-to-action "Inquadra il QR" -- MAI una seconda valutazione reale:
    # verificato su tutte le occorrenze del catalogo, il testo li' e' sempre e solo questo
    # invito a scansionare il QR code, non un secondo ente/punteggio. Prima veniva catturato
    # come valutazione aggiuntiva ("tipo": "animazione  inquadra il qr"), sporcando la colonna
    # con doppi spazi e testo che non è affatto una valutazione.
    evaluation_match = re.search(
        r"VALUTAZIONE\s+(?P<agency>[A-ZÀ-ÖØ-Ý][A-ZÀ-ÖØ-Ý&' -]{1,40}?)(?:\s+[A-ZÀ-ÖØ-Ý][A-ZÀ-ÖØ-Ý -]{2,30})?\s+e\s+scopri",
        header, re.IGNORECASE,
    )
    if evaluation_match:
        agency = re.sub(r"\s+", " ", evaluation_match.group("agency")).strip()
        evaluations.append({"ente": agency, "tipo": "generale", "testo_originale": agency})

    return category, evaluations


def _stelle_from_text(text: str) -> str | None:
    """Testo grezzo tra 'CATEGORIA UFFICIALE' e 'VALUTAZIONE' (es. '★★★★', '★★★ S').
    Deterministico: usato sia dal passaggio offline sia per sovrascrivere il campo
    dopo la review LLM, perché il formato libero del testo (stelle a simboli) è quello
    che compare nel PDF, mentre l'LLM tende a restituire solo la cifra (es. '4') --
    incoerente con le altre righe del catalogo che non passano per revisione."""
    match = re.search(r"CATEGORIA UFFICIALE\s+(.+?)\s+VALUTAZIONE", text, re.I)
    return re.sub(r"\s+", " ", match.group(1)).strip() if match else None


_TRATTAMENTO_PRIORITY = ("tutto incluso soft", "tutto incluso", "pensione completa", "mezza pensione", "pernottamento e prima colazione")
# Le altre etichette che nella scheda seguono "TRATTAMENTO(I)" dentro "DA SAPERE" -- delimitano
# dove finisce l'elenco dei trattamenti offerti (variano leggermente da hotel a hotel).
_DA_SAPERE_NEXT_LABELS = ("SISTEMAZIONE", "SISTEMAZIONI", "GIORNO DI INGRESSO", "SOGGIORNO MINIMO", "INFANT", "SERVIZI OBBLIGATORI", "SERVIZI FACOLTATIVI", "VANTAGGI", "ESCLUSIVA")
_TRATTAMENTO_PATTERN = re.compile(
    r"TRATTAMENT[OI]\s+(.+?)(?=\s+(?:" + "|".join(re.escape(label) for label in _DA_SAPERE_NEXT_LABELS) + r")\b|\Z)",
    re.IGNORECASE,
)


def _trattamento_from_text(text: str) -> str | None:
    """'TRATTAMENTO(I)' dentro 'DA SAPERE' e' la sezione autorevole (spesso elenca piu' opzioni,
    es. 'mezza pensione, pensione completa'): la prosa marketing altrove nella scheda cita anche
    trattamenti non inclusi in quella tariffa, e la review LLM -- anche a temperature=0 -- a volte
    sceglie l'opzione sbagliata tra quelle elencate qui (osservato su hotel-016 e hotel-017 in run
    diversi con lo stesso identico input). Se ci sono piu' opzioni si riporta la piu' inclusiva,
    stessa convenzione gia' in uso nel resto del catalogo. None se la sezione non c'e' (PDF futuro
    con layout diverso): extract_block ricade sulla risposta della review in quel caso."""
    da_sapere = text[text.upper().find("DA SAPERE"):] if "DA SAPERE" in text.upper() else text
    match = _TRATTAMENTO_PATTERN.search(da_sapere)
    if not match:
        return None
    segment = re.sub(r"\s+", " ", match.group(1)).lower()
    return next((term for term in _TRATTAMENTO_PRIORITY if term in segment), None)


def _offline(block: HotelBlock, index: int) -> HotelSchema:
    """Zero-API extraction: `nome`/`localita` come straight from PyMuPDF's font-size
    parsing (already reliable, see pymupdf_parser.py), everything else from regex/keyword
    matching over the raw block text. `field_confidence` scores what was actually
    verified (e.g. `nome_affidabile` is false only for a genuinely short/unresolved title,
    not just because this pass is deterministic) — that's what feeds `_needs_llm_fallback`."""
    text = block.text.lower()
    title = block.title
    locality = block.locality.title() if block.locality else "Non specificata"
    treatment = _trattamento_from_text(block.text)
    category, evaluations = _header_fields(block)
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
        "source_pages": 1.0 if block.pages else 0.0,
    }
    record_confidence = min(field_confidence.values())
    return HotelSchema(
        # Nessuna euristica deterministica affidabile per i qualificatori (es. "Palace" come ala
        # separata dal nome): il font decorativo del titolo rende illeggibile la legatura "LA" proprio
        # nei casi che contano, quindi un match testuale sul resto dell'header intercetta solo falsi
        # positivi (visto su hotel-017/Pizzomunno: "PALACE" nella riga categoria, non nel nome).
        # Il campo resta nello schema per i casi in cui la review LLM lo trova davvero nel testo.
        id=f"hotel-{index:03d}", nome=title, localita=locality, source_pages=list(block.pages),
        stelle=_stelle_from_text(block.text),
        categoria_ufficiale=category,
        valutazioni=evaluations,
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
    strutturato di Gemini (rifiuta additionalProperties). `stelle` è escluso perché
    extract_block lo ricalcola sempre con `_stelle_from_text`: lasciarlo libero
    all'LLM produceva formati incoerenti col resto del catalogo (es. '4' invece di
    '★★★★', copiando la forma dell'esempio nel prompt anche se i valori non
    dovrebbero essere copiati).
    """

    model_config = ConfigDict(extra="ignore")

    nome: str
    localita: str | None = "Non specificata"
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
    categoria_ufficiale=4,
    valutazioni=[HotelRating(ente="Es. TripAdvisor", tipo="generale", punteggio=4, massimo=5, testo_originale="testo originale se presente nella scheda")],
    qualificatori=["Es. Superior, valido solo se etichettato esplicitamente come categoria/ala separata dal nome"],
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
    # temperature=0: e' un'estrazione da testo dato, non generazione creativa — la varianza tra
    # run osservata a temperatura di default produceva risultati diversi (e a volte peggiori,
    # es. "Puglia" invece di "Otranto" come localita') sullo stesso identico input.
    response = client.chat.completions.create(
        model=settings.groq_model,
        messages=[
            {"role": "system", "content": _REVIEW_PROMPT},
            {"role": "user", "content": f"TESTO SCHEDA:\n{block_text}"},
        ],
        response_format={"type": "json_object"},
        temperature=0,
    )
    return HotelReview.model_validate_json(response.choices[0].message.content)


def _gemini_review(client: Any, block_text: str) -> HotelReview:
    response = client.models.generate_content(
        model=settings.google_model,
        contents=f"{_REVIEW_PROMPT}\n\nTESTO SCHEDA:\n{block_text}",
        config={"response_mime_type": "application/json", "response_schema": HotelReview, "temperature": 0},
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

    # Come per stelle/trattamento: l'header "VALUTAZIONE <ente> ... e scopri" e' un pattern
    # deterministico affidabile (vedi _header_fields). La review viene interpellata per un
    # motivo qualunque (es. categoria_ufficiale illeggibile, come nell'header a doppia
    # struttura di hotel-017) e a volte non ritrova l'ente li' dove il regex lo trova sempre:
    # in quel caso non si perde il segnale deterministico solo perche' la review non l'ha
    # ripetuto.
    valutazioni = review.valutazioni or deterministic.valutazioni
    # The LLM found rating agencies (e.g. "BRAVO") but no numeric score in the text — that
    # usually means the score is only shown as a visual badge/graphic in the PDF, so fall
    # back to a targeted Gemini Vision crop of just the header (see _visual_ratings above).
    if bool(valutazioni) and all(r.punteggio is None for r in valutazioni):
        try:
            visual = _visual_ratings(pdf_path, block) if pdf_path is not None else []
        except Exception:
            visual = []
        if visual:
            valutazioni = visual
    # L'header del PDF stampa sempre l'ente in maiuscolo (vedi il charclass di
    # _header_fields); l'LLM a volte lo restituisce in altre forme (es. "Alpitour"), e a
    # volte copia anche l'etichetta "VALUTAZIONE" che precede l'ente nel testo grezzo
    # (es. "VALUTAZIONE ALPITOUR" invece di "ALPITOUR"). Normalizziamo entrambi i casi qui
    # per non avere lo stesso ente scritto in più forme diverse nel catalogo.
    valutazioni = [
        rating.model_copy(update={"ente": re.sub(r"^VALUTAZION[EI]\s+", "", rating.ente.strip().upper())})
        for rating in valutazioni
    ]

    # Il nome da font-clustering (pymupdf_parser.py) e' la fonte canonica quando il suo stesso
    # field_confidence e' alto (>=2 parole, non il placeholder) — la review LLM viene interpellata
    # per un motivo qualunque (es. categoria_ufficiale illeggibile) e non dovrebbe rimpiazzare un
    # nome gia' corretto con uno reinventato dal testo grezzo. Visto su hotel-017: il nome
    # deterministico "PIZZOMUNNO VIESTE PALACE" e' corretto, l'LLM lo spezzava in "Pizzomunno" +
    # qualificatore "Palace". La localita' invece non ha un segnale di verifica altrettanto forte
    # (field_confidence e' 0.9 semplicemente se *qualcosa* e' stato separato, non se e' il comune
    # giusto: hotel-009 aveva "Alimini", frazione, al posto del comune "Otranto") quindi per quella
    # ci si affida sempre alla review.
    nome_affidabile = deterministic.quality.field_confidence.get("nome", 0.0) >= settings.llm_fallback_confidence_threshold
    # Il resto del catalogo (nome da pymupdf) e' sempre TUTTO MAIUSCOLO come nell'header del PDF;
    # la review LLM oscilla tra "Koinè Alimini" e "KOINÈ ALIMINI" da un run all'altro sullo stesso
    # input. Uniformiamo al maiuscolo senza toccare le parole scelte dall'LLM.
    nome = deterministic.nome if nome_affidabile else review.nome.strip().upper()
    # Un qualificatore che e' gia' contenuto nel nome scelto e' ridondante (stesso bug di cui sopra:
    # l'LLM a volte lo duplica quando ha appena spezzato quella parola via dal nome).
    qualificatori = [q for q in review.qualificatori if q.strip() and q.strip().lower() not in nome.lower()]

    return HotelSchema(
        id=f"hotel-{index:03d}",
        nome=nome,
        localita=review.localita or "Non specificata",
        stelle=deterministic.stelle,
        categoria_ufficiale=review.categoria_ufficiale,
        valutazioni=valutazioni,
        qualificatori=qualificatori,
        # Come per stelle: la sezione "DA SAPERE" e' autorevole e deterministica, la review LLM
        # sceglie a volte l'opzione sbagliata tra quelle elencate li' (vedi _trattamento_from_text).
        # La si usa come fallback solo se quella sezione manca nel testo.
        trattamento_principale=deterministic.trattamento_principale or review.trattamento_principale,
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
