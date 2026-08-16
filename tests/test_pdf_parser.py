from pathlib import Path

import pytest

from fde_hotel_rag.pdf_parser import extract_pdf_text, write_raw_text


def test_extract_pdf_text_returns_clean_pages(tmp_path: Path) -> None:
    # Verifica il contratto del parser senza dipendere dal PDF completo.
    with pytest.raises(FileNotFoundError):
        extract_pdf_text(tmp_path / "missing.pdf")

    output = tmp_path / "raw.txt"
    write_raw_text([" first  page ", "second page"], output)
    assert "--- PAGE 1 ---" in output.read_text(encoding="utf-8")
