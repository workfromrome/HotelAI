from __future__ import annotations

import json
from pathlib import Path

from ingestion.gemini_title_corrector import correct_reviewed_titles
from ingestion.pymupdf_parser import load_pymupdf_hotel_blocks


def serialize(block: object) -> dict[str, object]:
    quality = getattr(block, "quality", None)
    return {
        "nome": getattr(block, "title"),
        "pagine": list(getattr(block, "pages")),
        "confidence": quality.overall_confidence if quality else None,
        "needs_review": quality.needs_review if quality else None,
        "warnings": quality.warnings if quality else [],
    }


def main() -> None:
    pdf = Path(r"C:\Users\olso4\Downloads\FDE_test\FDE_test\FileHotels.pdf")
    output_dir = Path("data/processed")
    base = load_pymupdf_hotel_blocks(pdf, correct_titles=False)
    (output_dir / "records_without_llm.json").write_text(
        json.dumps([serialize(block) for block in base], ensure_ascii=False, indent=2), encoding="utf-8"
    )
    corrected = correct_reviewed_titles(base, enabled=True)
    (output_dir / "records_with_llm.json").write_text(
        json.dumps([serialize(block) for block in corrected], ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"without={len(base)}")
    print(f"with={len(corrected)}")
    print(f"candidates={sum(bool(block.quality and block.quality.needs_review) for block in base)}")
    print(f"changed={sum(left.title != right.title for left, right in zip(base, corrected))}")


if __name__ == "__main__":
    main()
