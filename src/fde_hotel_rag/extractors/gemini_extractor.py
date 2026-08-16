import os, time
from ..config import settings
from ..schemas import HotelRecord
class GeminiExtractor:
    def __init__(self) -> None:
        if not settings.google_api_key: raise RuntimeError("GOOGLE_API_KEY non è configurata")
        from google import genai
        self.client = genai.Client(api_key=settings.google_api_key)
    def extract(self, text: str, source_pages: list[int]) -> HotelRecord:
        from pydantic import TypeAdapter
        prompt = f"Estrai una scheda hotel in italiano, solo fatti presenti nel testo. Pagine: {source_pages}.\n{text}"
        for attempt in range(settings.max_retries):
            try:
                response = self.client.models.generate_content(model=settings.google_model, contents=prompt, config={"response_mime_type":"application/json", "response_schema":HotelRecord})
                time.sleep(settings.request_delay_seconds)
                return TypeAdapter(HotelRecord).validate_json(response.text).model_copy(update={"source_pages": source_pages})
            except Exception as exc:
                status = getattr(exc, "status_code", None)
                if status == 404: raise RuntimeError(f"Modello Google non trovato: {settings.google_model}") from exc
                if status not in (429, 500, 502, 503, 504) or attempt == settings.max_retries - 1: raise RuntimeError(f"Errore Google: {exc}") from exc
                time.sleep(2 ** attempt)
        raise RuntimeError("Estrazione Google fallita")
