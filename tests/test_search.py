from pathlib import Path

from conftest import require_sample_pdf

from hotelai.schemas import HotelRecord, HotelSource
from ingestion.structured_extractor import extract_catalogue
from search.retriever import HotelRetriever
from search.vector_store import OfflineEmbedder, build_index, build_index_from_csv

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


def test_explicit_criterion_rerank_prefers_hotel_that_actually_has_it(tmp_path: Path) -> None:
    """Both records share the same raw_text (so OfflineEmbedder's hash-based vector score
    ties them) — isolates _criteria_matched as the only thing that can break the tie, since
    that's the deterministic part of ranking this test can actually exercise without a real
    (semantic) embedder."""
    same_text = "Struttura con piscina panoramica e vista mare."
    records = [
        HotelRecord(id="h-with-pool", nome="Hotel Con Piscina", ha_piscina=True, source=HotelSource(raw_text=same_text)),
        HotelRecord(id="h-without-pool", nome="Hotel Senza Piscina", ha_piscina=False, source=HotelSource(raw_text=same_text)),
    ]
    build_index(records, tmp_path / "chroma", OfflineEmbedder())
    retriever = HotelRetriever(tmp_path / "chroma", OfflineEmbedder())
    results = retriever.search_hotels("Cerco un hotel con piscina", top_k=2)
    assert results[0]["metadata"]["id"] == "h-with-pool"


def test_compound_criteria_rerank_prefers_hotel_matching_all_of_them(tmp_path: Path) -> None:
    same_text = "Struttura pensata per le famiglie in vacanza."
    records = [
        HotelRecord(id="h-both", nome="Hotel Family Parcheggio", caratteristiche_chiave=["family", "parcheggio"], source=HotelSource(raw_text=same_text)),
        HotelRecord(id="h-partial", nome="Hotel Solo Family", caratteristiche_chiave=["family"], source=HotelSource(raw_text=same_text)),
    ]
    build_index(records, tmp_path / "chroma", OfflineEmbedder())
    retriever = HotelRetriever(tmp_path / "chroma", OfflineEmbedder())
    results = retriever.search_hotels("Trova strutture con camere family e parcheggio", top_k=2)
    assert results[0]["metadata"]["id"] == "h-both"
