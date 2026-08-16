from pathlib import Path
from ingestion.pdf_parser import clean_ocr, load_hotel_blocks, repair_split_words
from ingestion.pymupdf_parser import load_pymupdf_hotel_blocks

PDF = Path(r"C:\Users\olso4\Downloads\FDE_test\FDE_test\FileHotels.pdf")

def test_ocr_cleanup() -> None:
    assert clean_ocr('GATTAREL! PA!CE VOI DANIE"') == "GATTARELLA PALACE VOI DANIELI"


def test_ocr_cleanup_normalizes_unicode_and_layout_whitespace() -> None:
    assert clean_ocr("Hotel\u00a0\u201cAlba\u201d  sul\n mare ;") == 'Hotel "Alba" sul mare;'


def test_split_word_is_repaired_only_with_local_evidence() -> None:
    repaired, confidence = repair_split_words("Hotel LIDO M ARINI. La struttura è a LIDO MARINI.")
    assert "LIDO MARINI." in repaired
    assert confidence == 1.0

    unchanged, confidence = repair_split_words("Hotel M ARINI senza altro contesto.")
    assert unchanged == "Hotel M ARINI senza altro contesto."
    assert confidence == 0.0

def test_original_catalogue_has_19_blocks() -> None:
    blocks = load_hotel_blocks(PDF)
    assert len(blocks) == 19
    assert blocks[0].pages == (2, 3)
    assert blocks[0].lines
    assert blocks[0].words
    assert {"text", "x0", "x1", "top", "bottom", "page"}.issubset(blocks[0].words[0])
    assert blocks[0].segmentation_confidence >= 0.66
    assert blocks[0].segmentation_issues == ()


def test_pymupdf_candidate_has_clean_header_names() -> None:
    blocks = load_pymupdf_hotel_blocks(PDF)
    assert len(blocks) == 19
    assert blocks[0].title == "BRAVO ALIMINI"
    titles = [block.title for block in blocks]
    assert "CATEGORIA UFFICIALE" not in " ".join(titles).upper()
    assert blocks[1].quality is not None
    assert blocks[1].quality.needs_review is True
    assert blocks[2].quality is not None
    assert blocks[2].quality.needs_review is True
    for block in blocks:
        assert "CATEGORIA UFFICIALE" not in block.title.upper()
        assert "AILGUP" not in block.title.upper()
