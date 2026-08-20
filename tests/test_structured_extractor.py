from pathlib import Path
import pytest
from conftest import require_sample_pdf
from ingestion.pdf_parser import HotelBlock
from ingestion.structured_extractor import _needs_llm_fallback, _offline, extract_catalogue, read_csv
from hotelai.schemas import ExtractionQuality, HotelRating, HotelRecord, HotelSource

def test_offline_structured_csv(tmp_path: Path) -> None:
    pdf = require_sample_pdf()
    output = tmp_path / "hotels_data.csv"
    records = extract_catalogue(pdf, output, use_gemini=False)
    assert len(records) == 19
    assert output.exists()
    assert output.with_suffix(".jsonl").exists()
    assert records[0].ha_piscina is True
    assert records[0].nome == "BRAVO ALIMINI"
    assert records[0].localita == "Otranto"


def test_read_csv_round_trips_write_csv(tmp_path: Path) -> None:
    pdf = require_sample_pdf()
    output = tmp_path / "hotels_data.csv"
    written = extract_catalogue(pdf, output, use_gemini=False)
    imported = read_csv(output)
    assert len(imported) == len(written)
    for original, roundtripped in zip(written, imported, strict=True):
        assert roundtripped.id == original.id
        assert roundtripped.nome == original.nome
        assert roundtripped.categoria_ufficiale == original.categoria_ufficiale
        assert roundtripped.ha_piscina == original.ha_piscina
        assert roundtripped.caratteristiche_chiave == original.caratteristiche_chiave
        assert roundtripped.source.raw_text == original.source.raw_text
        assert roundtripped.quality.confidence == original.quality.confidence


def test_offline_uses_deterministic_locality_when_available() -> None:
    block = HotelBlock(title="TORRE GUACETO GREENBLU RESORT", pages=(36,), text="", locality="CAROVIGNO")
    record = _offline(block, 1)
    assert record.nome == "TORRE GUACETO GREENBLU RESORT"
    assert record.localita == "Carovigno"
    assert "localita_non_separata" not in record.quality.issues


def test_offline_flags_missing_locality() -> None:
    block = HotelBlock(title="HOTEL SENZA LOCALITA", pages=(1,), text="", locality="")
    record = _offline(block, 1)
    assert record.localita == "Non specificata"
    assert "localita_non_separata" in record.quality.issues


def test_structured_ratings_and_quality_are_validated() -> None:
    record = HotelRecord(
        nome="Hotel Test",
        categoria_ufficiale=4,
        valutazioni=[HotelRating(ente="Alpitour", tipo="animazione", punteggio=4, massimo=6)],
        qualificatori=["Palace"],
    )
    assert record.valutazioni[0].punteggio == 4
    assert record.quality.confidence == 1.0


def test_structured_record_serializes_sources_and_quality() -> None:
    record = HotelRecord(
        nome="Hotel Test",
        source=HotelSource(pages=[4, 5], raw_text="testo originale"),
        quality=ExtractionQuality(confidence=0.62, needs_review=True, issues=["localita_ambigua"]),
    )
    data = record.model_dump()
    assert data["source"]["pages"] == [4, 5]
    assert data["quality"]["needs_review"] is True


def test_rating_cannot_exceed_maximum() -> None:
    with pytest.raises(ValueError):
        HotelRating(ente="Alpitour", punteggio=7, massimo=6)


def test_field_confidence_is_bounded() -> None:
    with pytest.raises(ValueError):
        HotelRecord(nome="Hotel Test", quality={"field_confidence": {"nome": 1.5}})


def test_llm_fallback_uses_record_confidence() -> None:
    assert _needs_llm_fallback(HotelRecord(nome="Hotel Test")) is False
    low = HotelRecord(nome="Hotel Test", quality={"confidence": 0.4})
    assert _needs_llm_fallback(low) is True
