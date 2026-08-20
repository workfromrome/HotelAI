"""Conversational RAG: retrieval + Groq/Gemini answer synthesis with page citations.

Groq is tried first (default), Gemini is the fallback when Groq is not configured
or its call fails — the same cascade shape used by structured_extractor's LLM review,
but here as one synchronous attempt per provider (no retry/backoff: this runs on the
interactive query path, not a batch job). RAGEngine only synthesizes natural-language
answers; it does not touch the MCP server, which returns raw retrieval results instead
(see mcp_server/server.py and search/retriever.py::format_results).
"""
from __future__ import annotations

import logging
import re
from collections.abc import Sequence
from itertools import groupby
from typing import Any

from pydantic import BaseModel, Field

from hotelai.config import settings
from hotelai.prompts import load_prompt

logger = logging.getLogger(__name__)

FALLBACK_MESSAGE = "Informazione non sufficiente nei documenti forniti"

CONVERSATIONAL_RAG_PROMPT = load_prompt("conversational_rag").format(fallback_message=FALLBACK_MESSAGE)


class RAGResponse(BaseModel):
    answer: str
    source_pages: list[int] = Field(default_factory=list)
    retrieved_hotels: list[str] = Field(default_factory=list)
    is_fallback: bool = False


def _pages(metadata: dict[str, Any]) -> list[int]:
    """Chroma metadata only stores scalars, so vector_store.document_from_record joins
    a HotelRecord's `source_pages` list into a "2 | 3" string; the regex branch here
    parses that back out (the `isinstance(raw, list)` branch mainly covers direct-dict
    metadata in tests, where no such flattening happened)."""
    raw = metadata.get("source_pages", [])
    if isinstance(raw, list):
        return [int(page) for page in raw]
    return [int(value) for value in re.findall(r"\d+", str(raw))]


def _page_range_label(pages: Sequence[int]) -> str:
    """Render consecutive pages as a dash range, e.g. [2, 3] -> '2-3', [2, 5, 6] -> '2, 5-6'."""
    ordered = sorted(set(pages))
    if not ordered:
        return "non specificate"
    ranges: list[str] = []
    for _, group in groupby(enumerate(ordered), lambda pair: pair[1] - pair[0]):
        run = [value for _, value in group]
        ranges.append(str(run[0]) if len(run) == 1 else f"{run[0]}-{run[-1]}")
    return ", ".join(ranges)


def _groq_answer(client: Any, prompt: str) -> str:
    response = client.chat.completions.create(
        model=settings.groq_model,
        messages=[
            {"role": "system", "content": CONVERSATIONAL_RAG_PROMPT},
            {"role": "user", "content": prompt},
        ],
    )
    return str(response.choices[0].message.content).strip()


def _gemini_answer(client: Any, prompt: str) -> str:
    response = client.models.generate_content(
        model=settings.google_model,
        contents=prompt,
        config={"system_instruction": CONVERSATIONAL_RAG_PROMPT},
    )
    return str(response.text).strip()


class RAGEngine:
    def __init__(self, retriever: Any, groq_client: Any | None = None, gemini_client: Any | None = None) -> None:
        self.retriever = retriever
        self._groq_client = groq_client
        self._gemini_client = gemini_client

    def _get_groq_client(self) -> Any | None:
        if self._groq_client is not None:
            return self._groq_client
        if not settings.groq_api_key:
            return None
        from groq import Groq

        self._groq_client = Groq(api_key=settings.groq_api_key)
        return self._groq_client

    def _get_gemini_client(self) -> Any | None:
        if self._gemini_client is not None:
            return self._gemini_client
        if not settings.google_api_key:
            return None
        from google import genai

        self._gemini_client = genai.Client(api_key=settings.google_api_key)
        return self._gemini_client

    def _generate_answer(self, prompt: str) -> str:
        """Try Groq first, fall back to Gemini, then to the fallback message. Never raises."""
        groq_client = self._get_groq_client()
        if groq_client is not None:
            try:
                return _groq_answer(groq_client, prompt)
            except Exception as exc:
                logger.warning("Groq RAG answer fallito, fallback su Gemini: %s", exc)

        gemini_client = self._get_gemini_client()
        if gemini_client is not None:
            try:
                return _gemini_answer(gemini_client, prompt)
            except Exception as exc:
                logger.warning("Gemini RAG answer fallito: %s", exc)

        logger.warning("Nessun provider RAG disponibile, uso il messaggio di fallback")
        return FALLBACK_MESSAGE

    @staticmethod
    def _context(results: Sequence[dict[str, Any]]) -> tuple[str, list[int], list[str]]:
        """Builds the LLM prompt's CONTESTO block from retriever hits, and separately
        collects the page numbers/hotel names so RAGResponse can carry citations even if
        the LLM's own [Pag. x-y] text in the answer is missing or malformed."""
        chunks: list[str] = []
        pages: list[int] = []
        hotels: list[str] = []
        for result in results:
            metadata = result.get("metadata", {})
            hotel = str(metadata.get("nome", metadata.get("name", "Hotel")))
            hotel_pages = _pages(metadata)
            pages.extend(hotel_pages)
            hotels.append(hotel)
            chunks.append(f"[Hotel: {hotel} | Pagine: {_page_range_label(hotel_pages)}]\n{result.get('document', '')}")
        return "\n\n".join(chunks), sorted(set(pages)), hotels

    def answer_query(self, query: str, top_k: int = 3) -> RAGResponse:
        """Never raises. Falls back to FALLBACK_MESSAGE on an empty query, empty
        retrieval, or both LLM providers failing/unavailable — is_fallback tells the
        caller (POST /api/chat) which case happened without needing to inspect the text."""
        if not query.strip():
            return RAGResponse(answer=FALLBACK_MESSAGE, is_fallback=True)

        results = self.retriever.search_hotels(query, top_k=min(max(top_k, 1), settings.retrieval_limit))
        context, pages, hotels = self._context(results)
        if not results:
            return RAGResponse(answer=FALLBACK_MESSAGE, source_pages=pages, retrieved_hotels=hotels, is_fallback=True)

        prompt = f"DOMANDA:\n{query}\n\nCONTESTO:\n{context}"
        answer = self._generate_answer(prompt)
        is_fallback = answer == FALLBACK_MESSAGE
        return RAGResponse(answer=answer, source_pages=pages, retrieved_hotels=hotels, is_fallback=is_fallback)
