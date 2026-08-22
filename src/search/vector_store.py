"""Embeddings + ChromaDB indexing: turns HotelRecords into a searchable collection.

`Embedder` is the seam between this module and whichever provider computes vectors —
`GeminiEmbedder` for real semantic search, `OfflineEmbedder` as a deterministic stand-in
so tests and `--offline` runs never need a network call or an API key. Both return plain
`list[list[float]]`, so `HotelRetriever` (search/retriever.py) doesn't care which one built
the index it's querying, as long as the same embedder type built it and searches it.
"""
from __future__ import annotations

import hashlib
from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

import chromadb

from hotelai.config import settings
from ingestion.structured_extractor import HotelSchema, read_csv


class Embedder(Protocol):
    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


class OfflineEmbedder:
    """Hash-based fake embedding: same text -> same vector, no network. Good enough to
    exercise Chroma's storage/query mechanics in tests, not semantically meaningful."""

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [[byte / 255 for byte in hashlib.sha256(text.lower().encode()).digest()[:32]] for text in texts]


class GeminiEmbedder:
    def __init__(self) -> None:
        if not settings.google_api_key:
            raise RuntimeError("GOOGLE_API_KEY non è configurata")
        from google import genai
        self.client = genai.Client(api_key=settings.google_api_key)

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        values = list(texts)
        embeddings: list[list[float]] = []
        for start in range(0, len(values), settings.embedding_batch_size):
            response = self.client.models.embed_content(
                model=settings.embedding_model,
                contents=values[start:start + settings.embedding_batch_size],
            )
            embeddings.extend(item.values for item in response.embeddings)
        return embeddings


_METADATA_EXCLUDED_FIELDS = {"source", "quality"}


def document_from_record(record: HotelSchema) -> tuple[str, dict[str, str]]:
    """`source`/`quality` sono esclusi dai metadata: `source.raw_text` è già il documento
    indicizzato (duplicarlo nei metadata gonfierebbe lo storage e il bag-of-words di
    `_metadata_score` senza aggiungere segnale), `quality` è solo per audit interno."""
    metadata = {
        key: " | ".join(map(str, value)) if isinstance(value, list) else str(value or "")
        for key, value in record.model_dump().items()
        if key not in _METADATA_EXCLUDED_FIELDS
    }
    return record.source.raw_text, metadata


def build_index(records: Sequence[HotelSchema], path: Path | None = None, embedder: Embedder | None = None) -> int:
    """`upsert` (not `add`) so re-running indexing on the same records is idempotent —
    IDs are stable (`hotel-001`, ...) so a hotel's vector/metadata just gets overwritten."""
    client = chromadb.PersistentClient(path=str(path or settings.chroma_path))
    collection = client.get_or_create_collection(settings.collection_name)
    embedder = embedder or GeminiEmbedder()
    documents, metadata = zip(*(document_from_record(record) for record in records))
    collection.upsert(ids=[record.id for record in records], documents=list(documents), metadatas=list(metadata), embeddings=embedder.embed(documents))
    return collection.count()


def build_index_from_csv(csv_path: Path, path: Path | None = None, embedder: Embedder | None = None) -> int:
    """Importa il catalogo dal CSV prodotto dall'estrazione: collega esplicitamente Parte 1 e Parte 2 del flusso."""
    return build_index(read_csv(csv_path), path, embedder)
