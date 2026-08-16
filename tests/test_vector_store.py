from pathlib import Path
from ingestion.pdf_parser import load_hotel_blocks
from ingestion.structured_extractor import extract_catalogue
from search.vector_store import OfflineEmbedder, build_index

def test_offline_chroma_index(tmp_path: Path) -> None:
    pdf = Path(r"C:\Users\olso4\Downloads\FDE_test\FDE_test\FileHotels.pdf")
    records = extract_catalogue(pdf, tmp_path / "hotels.csv", use_gemini=False)
    blocks = load_hotel_blocks(pdf)
    assert build_index(records, blocks, tmp_path / "chroma", OfflineEmbedder()) == 19
