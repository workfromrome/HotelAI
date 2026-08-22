from pathlib import Path

from conftest import require_sample_pdf

from ingestion.structured_extractor import extract_catalogue
from mcp_server.server import configure_retriever, search_hotels
from search.retriever import HotelRetriever
from search.vector_store import OfflineEmbedder, build_index_from_csv


def test_mcp_tool_returns_markdown(tmp_path: Path) -> None:
    pdf = require_sample_pdf()
    csv_path = tmp_path / "hotels.csv"
    extract_catalogue(pdf, csv_path, use_gemini=False)
    build_index_from_csv(csv_path, tmp_path / "chroma", OfflineEmbedder())
    configure_retriever(HotelRetriever(tmp_path / "chroma", OfflineEmbedder()))
    result = search_hotels.fn("struttura con piscina")
    assert result.startswith("### 1.")
    assert "Similarità:" in result
