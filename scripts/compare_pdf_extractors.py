from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from hotelai.logging_setup import configure_logging
from ingestion.pdf_parser import load_hotel_blocks
from ingestion.pymupdf_parser import load_pymupdf_hotel_blocks

logger = logging.getLogger(__name__)


def main() -> None:
    configure_logging()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Confronta parser pdfplumber e PyMuPDF.")
    parser.add_argument("pdf", type=Path)
    args = parser.parse_args()
    canonical = load_hotel_blocks(args.pdf)
    candidate = load_pymupdf_hotel_blocks(args.pdf)
    print(f"pdfplumber_blocks={len(canonical)}")
    print(f"pymupdf_blocks={len(candidate)}")
    if len(canonical) != len(candidate):
        message = (
            f"MISMATCH: pdfplumber e pymupdf trovano un numero diverso di blocchi "
            f"(pdfplumber={len(canonical)}, pymupdf={len(candidate)}); "
            f"confronto limitato ai primi {min(len(canonical), len(candidate))} record comuni"
        )
        print(message)
        logger.warning(message)  # solo il print sparirebbe alla chiusura del terminale; questo resta in logs/app.log
    for index, (canonical_block, candidate_block) in enumerate(zip(canonical, candidate), 1):
        print(f"{index:02d} | pdfplumber={canonical_block.title} | pymupdf={candidate_block.title} | pages={candidate_block.pages}")
        if "CATEGORIA UFFICIALE" in candidate_block.title.upper() or "AILGUP" in candidate_block.title.upper():
            raise RuntimeError(f"Nome PyMuPDF non pulito al record {index}: {candidate_block.title}")


if __name__ == "__main__":
    main()
