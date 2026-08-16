from fde_hotel_rag.extraction import extract_hotels, hotel_page_groups


def test_groups_and_local_fallback() -> None:
    pages = ["intro"] + [f"card {i}" for i in range(1, 39)]
    # Contratto del catalogo: 39 pagine, schede sulle pagine pari.
    groups = hotel_page_groups(pages)
    assert len(groups) == 19
    assert groups[0][0] == [2, 3]


def test_extracts_expected_number_from_catalogue_shape() -> None:
    pages = ["intro"] + ["CATEGORIA UFFICIALE ★★★★ VALUTAZIONE piscina pensione completa" for _ in range(38)]
    hotels = extract_hotels(pages, use_google=False)
    assert len(hotels) == 19
    assert "piscina" in hotels[0].services
