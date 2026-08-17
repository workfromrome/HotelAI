from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from fde_hotel_rag.config import settings
from ingestion.gemini_title_corrector import TitleCorrectionResult, correct_hotel_title, correct_reviewed_titles
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


def test_cached_title_returns_without_calling_any_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    """Level 2 cassette test: a title present in the real-response cache never touches Groq or Gemini."""
    monkeypatch.setattr(settings, "llm_cache_path", Path("tests/fixtures/llm_cached_responses.json"))

    def _fail(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("non deve contattare alcun provider quando il titolo è in cache")

    monkeypatch.setattr("ingestion.gemini_title_corrector._call_groq", _fail)
    monkeypatch.setattr("ingestion.gemini_title_corrector._call_gemini", _fail)

    result = correct_hotel_title("GATTAREL ! RESORT", "GATTAREL ! RESORT", 12)

    assert result.was_corrected is True
    assert result.corrected_title == "Gattarella Resort"


def test_uncached_title_falls_back_to_raw_when_no_provider_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "llm_cache_path", Path("tests/fixtures/does_not_exist.json"))
    monkeypatch.setattr(settings, "groq_api_key", None)
    monkeypatch.setattr(settings, "google_api_key", None)

    result = correct_hotel_title("TITOLO SCONOSCIUTO", "TITOLO SCONOSCIUTO", 2)

    assert result.was_corrected is False
    assert result.corrected_title == "TITOLO SCONOSCIUTO"
