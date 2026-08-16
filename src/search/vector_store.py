from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Protocol, Sequence

import chromadb

from fde_hotel_rag.config import settings
from ingestion.pdf_parser import HotelBlock
from ingestion.structured_extractor import HotelSchema


class Embedder(Protocol):
    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


class OfflineEmbedder:
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


def document_from_block(block: HotelBlock, record: HotelSchema) -> tuple[str, dict[str, str]]:
    metadata = {key: " | ".join(map(str, value)) if isinstance(value, list) else str(value or "") for key, value in record.model_dump().items()}
    metadata["source_pages"] = " | ".join(map(str, block.pages))
    return block.text, metadata


def build_index(records: Sequence[HotelSchema], blocks: Sequence[HotelBlock], path: Path | None = None, embedder: Embedder | None = None) -> int:
    if len(records) != len(blocks):
        raise ValueError("Record e blocchi PDF non corrispondono")
    client = chromadb.PersistentClient(path=str(path or settings.chroma_path))
    collection = client.get_or_create_collection(settings.collection_name)
    embedder = embedder or GeminiEmbedder()
    documents, metadata = zip(*(document_from_block(block, record) for block, record in zip(blocks, records, strict=True)))
    collection.upsert(ids=[record.id for record in records], documents=list(documents), metadatas=list(metadata), embeddings=embedder.embed(documents))
    return collection.count()
