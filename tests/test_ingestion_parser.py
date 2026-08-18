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
    # blocks[1]/[2] (THALAS CLUB, DANIELA ESSENTIA) usano il glifo decorativo "LA": la
    # sostituzione deterministica in pymupdf_parser li rende puliti, needs_review=False.
    assert blocks[1].quality is not None
    assert blocks[1].quality.needs_review is False
    assert blocks[2].quality is not None
    assert blocks[2].quality.needs_review is False
    for block in blocks:
        assert "CATEGORIA UFFICIALE" not in block.title.upper()
        assert "AILGUP" not in block.title.upper()


# Nome/localita di verita per i 19 record, ricavati dagli span reali (font size 30pt = nome,
# 11pt = localita) e confermati contro gli screenshot delle schede originali. Copre i due
# layout di pagina del catalogo (compatto e con banner PUGLIA) e il glifo decorativo "LA"
# (reso da pymupdf come span isolato '"' o '!') presente in 6 delle 19 schede.
_EXPECTED_NAME_LOCALITY = [
    ("BRAVO ALIMINI", "OTRANTO"),
    ("HOTEL THALAS CLUB", "TORRE DELL'ORSO"),
    ("VOI DANIELA ESSENTIA", "OTRANTO"),
    ("TORRE CINTOLA GREENBLU SEA EMOTIONS", "MONOPOLI"),
    ("MASSERIA BARONI DI MONTESARDO", "LIDO MARINI"),
    ("GATTARELLA RESORT", "VIESTE"),
    ("TORRE GUACETO GREENBLU RESORT", "CAROVIGNO"),
    ("ACAYA GOLF RESORT & SPA", "ACAYA"),
    ("KOINÈ", "ALIMINI"),
    ("ROBINSON APULIA", "MARINA DI UGENTO"),
    ("VILLAGGIO ESPERIA PALACE", "LIDO MARINI"),
    ("ANTICA MASSERIA ROTTACAPOZZA", "TORRE MOZZA"),
    ("BAIAMALVA RESORT", "PORTO CESAREO"),
    ("HOTEL BAIA SANTA BARBARA", "RODI GARGANICO"),
    ("VILLAGGIO CAMPING INTERNAZIONALE MANACORE", "PESCHICI"),
    ("PAGLIANZA", "PESCHICI"),
    ("PIZZOMUNNO VIESTE PALACE", "VIESTE"),
    ("HOTEL DEL FARO PUGNOCHIUSO RESORT", "PUGNOCHIUSO"),
    ("HOTEL DEGLI ULIVI PUGNOCHIUSO RESORT", "PUGNOCHIUSO"),
]


def test_all_19_records_have_clean_name_and_locality() -> None:
    """Nome e localita non devono mai risultare impastati, sui due layout di pagina del catalogo."""
    blocks = load_pymupdf_hotel_blocks(PDF)
    assert len(blocks) == len(_EXPECTED_NAME_LOCALITY)
    for index, (block, (expected_name, expected_locality)) in enumerate(
        zip(blocks, _EXPECTED_NAME_LOCALITY, strict=True), 1
    ):
        assert block.title == expected_name, f"record {index}: nome inatteso"
        assert block.locality == expected_locality, f"record {index}: localita inattesa"


def test_novita_badge_is_never_leaked_into_name_or_locality() -> None:
    """La scheda Acaya (pagina con badge NOVITA) non deve contenere il badge in nome/localita."""
    blocks = load_pymupdf_hotel_blocks(PDF)
    acaya = next(block for block in blocks if block.locality == "ACAYA")
    assert acaya.title == "ACAYA GOLF RESORT & SPA"
    tokens = f"{acaya.title} {acaya.locality}".upper().split()
    assert "NOVITA" not in "".join(tokens)
    assert not any(len(token) == 1 and token in "NOVITÀ" for token in tokens)
