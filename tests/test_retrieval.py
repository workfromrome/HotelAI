from fde_hotel_rag.retrieval import document_from_row, metadata_score


def test_metadata_enriched_document_and_score() -> None:
    row = {"name": "Hotel Test", "locality": "Otranto", "region": "Puglia", "stars": "★★★★", "treatment": "pensione completa", "room_types": "family", "services": "piscina | spiaggia", "highlights": "famiglie", "description": "Sul mare"}
    document = document_from_row(row)
    assert "Servizi: piscina | spiaggia" in document
    assert metadata_score("famiglia piscina", row) > 0
