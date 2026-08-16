from pathlib import Path
from ingestion.pdf_parser import load_hotel_blocks
from ingestion.structured_extractor import extract_catalogue
from mcp_server.server import configure_retriever, search_hotels
from search.retriever import HotelRetriever
from search.vector_store import OfflineEmbedder, build_index

def test_mcp_tool_returns_markdown(tmp_path: Path) -> None:
    pdf = Path(r"C:\Users\olso4\Downloads\FDE_test\FDE_test\FileHotels.pdf")
    records = extract_catalogue(pdf, tmp_path / "hotels.csv", use_gemini=False)
    build_index(records, load_hotel_blocks(pdf), tmp_path / "chroma", OfflineEmbedder())
    configure_retriever(HotelRetriever(tmp_path / "chroma", OfflineEmbedder()))
    result = search_hotels.fn("struttura con piscina")
    assert result.startswith("### 1.")
    assert "Similarità:" in result
