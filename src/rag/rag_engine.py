from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any

from pydantic import BaseModel, Field

from fde_hotel_rag.config import settings


FALLBACK_MESSAGE = "Informazione non sufficiente nei documenti forniti"


class RAGResponse(BaseModel):
    answer: str
    source_pages: list[int] = Field(default_factory=list)
    retrieved_hotels: list[str] = Field(default_factory=list)
    is_fallback: bool = False


def _pages(metadata: dict[str, Any]) -> list[int]:
    raw = metadata.get("source_pages", [])
    if isinstance(raw, list):
        return [int(page) for page in raw]
    return [int(value) for value in re.findall(r"\d+", str(raw))]


class RAGEngine:
    def __init__(self, retriever: Any, client: Any | None = None) -> None:
        self.retriever = retriever
        self.client = client

    def _client(self) -> Any:
        if self.client is None:
            if not settings.google_api_key:
                raise RuntimeError("GOOGLE_API_KEY non è configurata")
            from google import genai
            self.client = genai.Client(api_key=settings.google_api_key)
        return self.client

    @staticmethod
    def _context(results: Sequence[dict[str, Any]]) -> tuple[str, list[int], list[str]]:
        chunks: list[str] = []
        pages: list[int] = []
        hotels: list[str] = []
        for result in results:
            metadata = result.get("metadata", {})
            hotel = str(metadata.get("nome", metadata.get("name", "Hotel")))
            hotel_pages = _pages(metadata)
            pages.extend(hotel_pages)
            hotels.append(hotel)
            page_label = ", ".join(map(str, hotel_pages)) or "non specificate"
            chunks.append(f"[Hotel: {hotel} | Pagine: {page_label}]\n{result.get('document', '')}")
        return "\n\n".join(chunks), sorted(set(pages)), hotels

    def answer_query(self, query: str, top_k: int = 3) -> RAGResponse:
        if not query.strip():
            return RAGResponse(answer=FALLBACK_MESSAGE, is_fallback=True)
        results = self.retriever.search_hotels(query, top_k=min(max(top_k, 1), 5))
        context, pages, hotels = self._context(results)
        if not results:
            return RAGResponse(answer=FALLBACK_MESSAGE, source_pages=pages, retrieved_hotels=hotels, is_fallback=True)
        prompt = (
            "Rispondi in italiano usando esclusivamente il contesto fornito. "
            "Inserisci sempre le citazioni delle pagine tra parentesi quadre, ad esempio [Pag. 2-3]. "
            f"Se il contesto non contiene informazioni sufficienti, rispondi esattamente: {FALLBACK_MESSAGE}\n\n"
            f"DOMANDA:\n{query}\n\nCONTESTO:\n{context}"
        )
        response = self._client().models.generate_content(model=settings.google_model, contents=prompt)
        answer = str(response.text).strip()
        is_fallback = answer == FALLBACK_MESSAGE
        return RAGResponse(answer=answer, source_pages=pages, retrieved_hotels=hotels, is_fallback=is_fallback)


def answer_query(query: str, vectorstore: Any, top_k: int = 3, client: Any | None = None) -> RAGResponse:
    return RAGEngine(vectorstore, client=client).answer_query(query, top_k=top_k)
