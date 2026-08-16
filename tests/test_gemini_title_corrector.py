from unittest.mock import Mock, patch

from ingestion.gemini_title_corrector import TitleCorrectionResult, correct_reviewed_titles
from ingestion.pdf_parser import HotelBlock
from ingestion.quality_model import ExtractionQuality


def _block(title: str, needs_review: bool) -> HotelBlock:
    return HotelBlock(title=title, pages=(2, 3), text=title, quality=ExtractionQuality(overall_confidence=0.5 if needs_review else 1.0, field_confidence={"nome": 0.5 if needs_review else 1.0}, needs_review=needs_review), header_raw_text=title, page_num=2)


@patch("ingestion.gemini_title_corrector.correct_hotel_title")
def test_corrects_only_reviewed_titles(mock_correct: Mock) -> None:
    mock_correct.side_effect = [
        TitleCorrectionResult(corrected_title="HOTEL THALAS CLUB", was_corrected=True, explanation="Artefatto OCR ricostruito"),
        TitleCorrectionResult(corrected_title="VOI DANIELA ESSENTIA", was_corrected=True, explanation="Artefatto OCR ricostruito"),
    ]
    blocks = [_block('HOTEL THA " S CLUB', True), _block('VOI DANIE " ESSENTIA', True), _block("BRAVO ALIMINI", False)]
    result = correct_reviewed_titles(blocks, enabled=True)
    assert [block.title for block in result] == ["HOTEL THALAS CLUB", "VOI DANIELA ESSENTIA", "BRAVO ALIMINI"]
    assert result[0].quality is not None and result[0].quality.needs_review is False
    assert mock_correct.call_count == 2


@patch("ingestion.gemini_title_corrector.correct_hotel_title")
def test_high_confidence_titles_do_not_call_gemini(mock_correct: Mock) -> None:
    result = correct_reviewed_titles([_block("BRAVO ALIMINI", False)], enabled=True)
    assert result[0].title == "BRAVO ALIMINI"
    mock_correct.assert_not_called()
