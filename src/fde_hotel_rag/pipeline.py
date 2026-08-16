import csv
from pathlib import Path
from .config import settings
from .pdf_loader import load_pages, write_raw
from .extractors.mock_extractor import MockExtractor
from .extractors.gemini_extractor import GeminiExtractor
from .storage.jsonl_storage import JsonlStorage
from .schemas import HotelRecord
def export_csv(records: list[HotelRecord], path: Path = settings.csv_path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(HotelRecord.model_fields)
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fields); writer.writeheader()
        for record in records:
            row = record.model_dump()
            for field, value in row.items():
                if isinstance(value, list): row[field] = " | ".join(map(str, value))
            writer.writerow(row)
def run_extraction(pdf_path: Path, use_google: bool = True) -> int:
    pages = load_pages(pdf_path); write_raw(pages, settings.raw_text_path)
    extractor = GeminiExtractor() if use_google else MockExtractor()
    records = [extractor.extract("\n".join(pages[i:i+2]), list(range(i+1, min(i+3, len(pages)+1)))) for i in range(1, len(pages), 2)]
    JsonlStorage(settings.jsonl_path).save(records); export_csv(records); return len(records)
