"""Eval di retrieval per la pipeline RAG: query reali contro l'indice committato, con
embedding Gemini veri (non l'OfflineEmbedder usato nei test, che non è semantico e non
potrebbe misurare se il retrieval trova davvero l'hotel giusto). Non fa parte della suite
pytest automatica (consuma quota API) — eseguire su richiesta esplicita:

    $env:PYTHONPATH = "src"; python scripts/eval_rag.py

Il dataset di query/hotel attesi è in scripts/eval_queries.json.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from hotelai.config import settings
from hotelai.logging_setup import configure_logging
from search.retriever import HotelRetriever
from search.vector_store import GeminiEmbedder

configure_logging()

if not settings.google_api_key:
    print("GOOGLE_API_KEY non configurata: serve per generare gli embedding reali delle query. Impostala in .env.")
    sys.exit(1)

queries = json.loads((Path(__file__).parent / "eval_queries.json").read_text(encoding="utf-8"))
retriever = HotelRetriever(embedder=GeminiEmbedder())

hits = 0
for case in queries:
    results = retriever.search_hotels(case["query"], top_k=5)
    found_ids = {result["metadata"].get("id") for result in results}
    expected_ids = set(case["expected_hotel_ids"])
    ok = bool(found_ids & expected_ids)
    hits += ok
    print(f"[{'OK  ' if ok else 'MISS'}] {case['query']}")
    print(f"       atteso: {sorted(expected_ids)} | trovato: {sorted(found_ids)}")

total = len(queries)
print(f"\nRecall@5: {hits}/{total} ({hits / total:.0%})")
