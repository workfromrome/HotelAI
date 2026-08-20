from pathlib import Path

import pytest

SAMPLE_PDF = Path(__file__).resolve().parent.parent / "data" / "raw" / "FileHotels.pdf"


def require_sample_pdf() -> Path:
    """PDF di test condiviso: se assente (es. clone senza il file fornito dall'assignment),
    salta il test invece di far fallire l'intera suite con un FileNotFoundError."""
    if not SAMPLE_PDF.is_file():
        pytest.skip(f"PDF di esempio non trovato in {SAMPLE_PDF}")
    return SAMPLE_PDF
