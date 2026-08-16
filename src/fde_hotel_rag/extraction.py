"""Estrazione strutturata Gemini con fallback locale deterministico."""
from __future__ import annotations
import hashlib, json, re, time
from pathlib import Path
from .config import EXTRACTION_STATE_PATH, settings
from .models import HotelExtraction, HotelRecord

HEADER = re.compile(r"(?:\d+\s+)?(?P<name>.+?)\s+(?P<locality>[A-Z][A-Z ']+)\s+INQUADRA IL QR", re.I)
LOCALITY = re.compile(r"(TORRE DELL['’]ORSO|LIDO M ARINI|MARINA DI UGENTO|PORTO CES AREO|RODI GARGANICO|PUGNOCHIUSO|CAROVIGNO|MONOPOLI|OTRANTO|VIESTE|ALIMINI|TORRE MOZZA|PESCHICI|ACAYA)", re.I)

def _clean_name(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace('"', "I").replace("!", "L")).strip().title()

def _header_fields(text: str) -> tuple[str, str]:
    head = text.split("INQUADRA IL QR", 1)[0]
    head = re.sub(r"^AILGUP\s+\d+\s+", "", head, flags=re.I)
    cities = list(LOCALITY.finditer(head))
    city = cities[-1] if cities else None
    if not city: return (_clean_name(head), "Non specificata")
    return (_clean_name(head[:city.start()]), city.group(0).replace(" M ", " ").title())

def hotel_page_groups(pages: list[str]) -> list[tuple[list[int], str]]:
    cards = [(n, p) for n, p in enumerate(pages, 1) if HEADER.search(p)]
    # Fallback per cataloghi testuali privi di intestazioni: prima pagina introduttiva,
    # poi schede composte da due pagine. Non contiene nomi o dati di catalogo.
    if not cards and len(pages) > 1:
        cards = [(n, pages[n - 1]) for n in range(2, len(pages) + 1, 2)]
    return [([n, n + 1] if n < len(pages) else [n], p + ("\n" + pages[n] if n < len(pages) else "")) for n, p in cards]

def _keywords(text: str, patterns: dict[str, tuple[str, ...]]) -> list[str]:
    low = text.lower()
    return [label for label, terms in patterns.items() if any(term in low for term in terms)]

def fallback_extract(source_pages: list[int], text: str, name: str) -> HotelRecord:
    match = HEADER.search(text)
    _, locality = _header_fields(text) if match else (name, "Non specificata")
    stars = re.search(r"CATEGORIA UFFICIALE\s+(.+?)\s+VALUTAZIONE", text, re.I)
    treatments = _keywords(text, {"tutto incluso": ("tutto incluso", "all inclusive"), "pensione completa": ("pensione completa",), "mezza pensione": ("mezza pensione",), "bed and breakfast": ("pernottamento e prima colazione",)})
    services = _keywords(text, {"spiaggia": ("spiaggia", "mare"), "piscina": ("piscina",), "spa": ("spa", "benessere", "wellness"), "pet-friendly": ("pet friendly", "animali", "dog-"), "parcheggio": ("parcheggio",), "wifi": ("wi-fi", "wifi"), "golf": ("golf",), "tennis": ("tennis",), "animazione": ("animazione", "miniclub")})
    rooms = _keywords(text, {"family": ("family",), "suite": ("suite",), "classic": ("classic",), "superior": ("superior",)})
    return HotelRecord(name=name, locality=locality, stars=stars.group(1).strip() if stars else None, treatment=treatments, room_types=rooms, services=services, highlights=services[:4], source_pages=source_pages, description=" ".join(text.split())[:3500])

def gemini_extract(source_pages: list[int], text: str) -> HotelRecord:
    if not settings.google_api_key:
        raise RuntimeError("GOOGLE_API_KEY non è configurata")
    from google import genai
    client = genai.Client(api_key=settings.google_api_key)
    prompt = f"Estrai una scheda hotel in italiano. Usa solo fatti presenti, senza inferenze. Pagine: {source_pages}.\n\n{text}"
    for attempt in range(settings.max_retries):
        try:
            response = client.models.generate_content(model=settings.google_model, contents=prompt, config={"response_mime_type": "application/json", "response_schema": HotelExtraction})
            record = HotelExtraction.model_validate_json(response.text).hotel
            time.sleep(settings.request_delay_seconds)
            return record.model_copy(update={"source_pages": source_pages})
        except Exception as exc:
            status = getattr(exc, "status_code", None)
            if status == 404: raise RuntimeError(f"Modello Google non trovato: {settings.google_model}") from exc
            if status not in (429, 500, 502, 503, 504) or attempt == settings.max_retries - 1: raise RuntimeError(f"Errore Google durante l'estrazione: {exc}") from exc
            time.sleep(2 ** attempt)
    raise RuntimeError("Estrazione Google fallita")

def extract_hotels(pages: list[str], use_google: bool = True, state_path: Path = EXTRACTION_STATE_PATH) -> list[HotelRecord]:
    groups = hotel_page_groups(pages)
    if not groups: raise ValueError("Nel PDF non sono state riconosciute schede hotel")
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
    records = []
    for index, (source_pages, text) in enumerate(groups):
        key = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if key in state: records.append(HotelRecord.model_validate(state[key])); continue
        match = HEADER.search(text)
        name, _ = _header_fields(text) if match else (f"Hotel pagina {source_pages[0]}", "Non specificata")
        try: record = gemini_extract(source_pages, text) if use_google else fallback_extract(source_pages, text, name)
        except RuntimeError as exc:
            print(f"Avviso: {exc}. Uso il fallback locale."); record = fallback_extract(source_pages, text, name)
        records.append(record); state[key] = record.model_dump(); state_path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    return records
