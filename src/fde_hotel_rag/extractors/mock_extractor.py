import re
from ..schemas import HotelRecord
class MockExtractor:
    def extract(self, text: str, source_pages: list[int]) -> HotelRecord:
        title = text.split("INQUADRA IL QR", 1)[0].strip()
        title = re.sub(r"^AILGUP\s+\d+\s+", "", title, flags=re.I)
        return HotelRecord(name=title[:120], source_pages=source_pages, description=text[:3500], services=self._terms(text))
    @staticmethod
    def _terms(text: str) -> list[str]:
        return [term for term in ("spiaggia", "piscina", "spa", "parcheggio", "wifi", "animazione") if term in text.lower()]
