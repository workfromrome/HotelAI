from pathlib import Path

from conftest import require_sample_pdf

from ingestion.structured_extractor import extract_catalogue
from search.retriever import HotelRetriever
from search.vector_store import OfflineEmbedder, build_index_from_csv

QUERIES = [
    "Cerco una struttura pet-friendly vicino al mare.",
    "Mostrami soluzioni con pensione completa e piscina.",
    "Quali strutture sono più adatte a una famiglia con bambini?",
    "Cerco una struttura con spa o centro benessere.",
    "Trova strutture con camere family e parcheggio.",
]

def test_five_queries_return_max_five(tmp_path: Path) -> None:
    pdf = require_sample_pdf()
    csv_path = tmp_path / "hotels.csv"
    extract_catalogue(pdf, csv_path, use_gemini=False)
    build_index_from_csv(csv_path, tmp_path / "chroma", OfflineEmbedder())
    retriever = HotelRetriever(tmp_path / "chroma", OfflineEmbedder())
    for query in QUERIES:
        results = retriever.search_hotels(query)
        assert 1 <= len(results) <= 5
        assert all("similarity" in result for result in results)
