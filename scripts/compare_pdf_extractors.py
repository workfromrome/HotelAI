from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ingestion.pdf_parser import load_hotel_blocks
from ingestion.pymupdf_parser import load_pymupdf_hotel_blocks
from ingestion.structured_extractor import _offline


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Confronta parser pdfplumber e PyMuPDF.")
    parser.add_argument("pdf", type=Path)
    args = parser.parse_args()
    canonical = load_hotel_blocks(args.pdf)
    candidate = load_pymupdf_hotel_blocks(args.pdf)
    print(f"pdfplumber_blocks={len(canonical)}")
    print(f"pymupdf_blocks={len(candidate)}")
    for index, (canonical_block, candidate_block) in enumerate(zip(canonical, candidate, strict=True), 1):
        record = _offline(candidate_block, index)
        print(f"{index:02d} | pdfplumber={canonical_block.title} | pymupdf={candidate_block.title} | pages={candidate_block.pages}")
        if "CATEGORIA UFFICIALE" in record.nome.upper() or "AILGUP" in record.nome.upper():
            raise RuntimeError(f"Nome PyMuPDF non pulito al record {index}: {record.nome}")


if __name__ == "__main__":
    main()
