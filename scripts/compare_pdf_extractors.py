from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

import pymupdf

from ingestion.pdf_parser import HotelBlock, clean_ocr, repair_split_words
from ingestion.structured_extractor import _offline


@dataclass(frozen=True)
class PageData:
    text: str
    lines: tuple[str, ...]


def load_pymupdf_pages(pdf_path: Path) -> list[PageData]:
    document = pymupdf.open(pdf_path)
    pages: list[PageData] = []
    for page in document:
        raw = page.get_text("text", sort=True)
        lines = tuple(clean_ocr(line) for line in raw.splitlines() if line.strip())
        text, _ = repair_split_words(clean_ocr(" ".join(raw.split())))
        pages.append(PageData(text=text, lines=lines))
    return pages


def blocks_from_pages(pages: list[PageData]) -> list[HotelBlock]:
    starts = [i for i, page in enumerate(pages) if "INQUADRA IL QR" in page.text.upper()]
    blocks: list[HotelBlock] = []
    for position, start in enumerate(starts):
        end = starts[position + 1] if position + 1 < len(starts) else len(pages)
        text = "\n".join(page.text for page in pages[start:end])
        lines = tuple(line for page in pages[start:end] for line in page.lines)
        title = " ".join(line for line in pages[start].lines if "INQUADRA IL QR" not in line.upper())
        blocks.append(HotelBlock(title=title, pages=tuple(range(start + 1, end + 1)), text=text, lines=lines))
    return blocks


def main() -> None:
    import sys
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf", type=Path)
    args = parser.parse_args()
    records = [_offline(block, i) for i, block in enumerate(blocks_from_pages(load_pymupdf_pages(args.pdf)), 1)]
    print(f"blocks={len(records)}")
    for record in records:
        ratings = "; ".join(f"{r.ente}/{r.tipo}" for r in record.valutazioni) or "-"
        print(" | ".join((record.nome, record.localita, str(record.categoria_ufficiale or "-"), ratings, ",".join(map(str, record.source_pages)))))


if __name__ == "__main__":
    main()
