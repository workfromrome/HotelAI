from pathlib import Path
from conftest import require_sample_pdf
from ingestion.structured_extractor import extract_catalogue
from search.vector_store import OfflineEmbedder, build_index_from_csv

def test_offline_chroma_index(tmp_path: Path) -> None:
    pdf = require_sample_pdf()
    csv_path = tmp_path / "hotels.csv"
    extract_catalogue(pdf, csv_path, use_gemini=False)
    assert build_index_from_csv(csv_path, tmp_path / "chroma", OfflineEmbedder()) == 19
