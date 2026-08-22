import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from conftest import require_sample_pdf

from hotelai.schemas import ExtractionQuality, HotelRating, HotelRecord, HotelSource
from ingestion.pdf_parser import HotelBlock
from ingestion.structured_extractor import _needs_llm_fallback, _offline, extract_block, extract_catalogue, read_csv


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


def test_offline_does_not_treat_qr_badge_as_second_rating() -> None:
    """Il badge decorativo tra l'ente e 'e scopri' (es. 'ANIMAZIONE Inquadra il QR') non è
    una seconda valutazione: prima veniva catturato come tale, sporcando il CSV con voci
    tipo 'animazione  inquadra il qr'."""
    text = (
        "CATEGORIA UFFICIALE  ★★★★  VALUTAZIONE BRAVO  ANIMAZIONE  Inquadra il QR  "
        "e scopri l'hotel"
    )
    block = HotelBlock(title="HOTEL TEST", pages=(1,), text=text, locality="Test")
    record = _offline(block, 1)
    assert len(record.valutazioni) == 1
    assert record.valutazioni[0].ente == "BRAVO"
    assert record.valutazioni[0].tipo == "generale"


def test_offline_stelle_collapses_extra_whitespace() -> None:
    text = "CATEGORIA UFFICIALE DÉPENDANCE  ★★★★  / PALACE  ★★★★★ VALUTAZIONE FRANCOROSSO e scopri"
    block = HotelBlock(title="HOTEL TEST", pages=(1,), text=text, locality="Test")
    record = _offline(block, 1)
    assert record.stelle == "DÉPENDANCE ★★★★ / PALACE ★★★★★"


def test_extract_block_falls_back_to_deterministic_valutazioni_when_review_finds_none() -> None:
    """La review LLM viene interpellata (categoria assente qui) e a volte non ritrova
    l'ente nell'header, pur essendo lì (vedi hotel-017 nel catalogo reale, header a
    doppia struttura Dépendance/Palace): non deve azzerare un segnale deterministico
    già trovato da _header_fields."""
    text = "CATEGORIA UFFICIALE testo illeggibile VALUTAZIONE FRANCOROSSO e scopri l'hotel"
    block = HotelBlock(title="HOTEL TEST PALACE", pages=(1,), text=text, locality="Test")
    groq_client = Mock()
    groq_client.chat.completions.create.return_value = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps({"nome": "HOTEL TEST PALACE"})))]
    )
    record = extract_block(block, 1, use_gemini=True, groq_client=groq_client, gemini_client=None)
    assert len(record.valutazioni) == 1
    assert record.valutazioni[0].ente == "FRANCOROSSO"


def test_extract_block_strips_valutazione_label_copied_into_ente() -> None:
    """La review LLM a volte copia anche l'etichetta 'VALUTAZIONE' che precede l'ente nel
    testo grezzo (osservato con Groq su hotel-009: ente 'VALUTAZIONE ALPITOUR' invece di
    'ALPITOUR')."""
    text = "CATEGORIA UFFICIALE testo illeggibile VALUTAZIONE ALPITOUR e scopri l'hotel"
    block = HotelBlock(title="HOTEL TEST", pages=(1,), text=text, locality="Test")
    groq_client = Mock()
    groq_client.chat.completions.create.return_value = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps({
            "nome": "HOTEL TEST",
            "valutazioni": [{"ente": "VALUTAZIONE ALPITOUR", "tipo": "generale"}],
        })))]
    )
    record = extract_block(block, 1, use_gemini=True, groq_client=groq_client, gemini_client=None)
    assert record.valutazioni[0].ente == "ALPITOUR"


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
