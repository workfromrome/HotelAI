from __future__ import annotations

import argparse
from pathlib import Path

from hotelai.config import settings
from hotelai.logging_setup import configure_logging
from ingestion.structured_extractor import extract_catalogue
from search.vector_store import GeminiEmbedder, build_index_from_csv

configure_logging()
parser = argparse.ArgumentParser(description="Estrae il catalogo hotel e costruisce l'indice.")
parser.add_argument("pdf", type=Path)
parser.add_argument("--offline", action="store_true")
args = parser.parse_args()
output = settings.data_dir / "processed" / "hotels_data.csv"
records = extract_catalogue(args.pdf, output, use_gemini=not args.offline)
print(f"Estrazione completata: {len(records)} hotel")
if args.offline:
    print("Modalità offline: indice Chroma non costruito.")
else:
    count = build_index_from_csv(output, embedder=GeminiEmbedder())
    print(f"Indice Chroma pronto: {count} record (importati da {output.name})")
