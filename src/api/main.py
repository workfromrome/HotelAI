"""FastAPI server exposing the Hotel RAG chatbot to the React frontend.

Run with: uvicorn api.main:app --reload --port 8000 (PYTHONPATH=src, from repo root).
"""
from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from fde_hotel_rag.config import settings
from rag.rag_engine import FALLBACK_MESSAGE, RAGEngine, RAGResponse
from search.retriever import HotelRetriever
from search.vector_store import GeminiEmbedder, OfflineEmbedder

logger = logging.getLogger(__name__)

_retriever: HotelRetriever | None = None
_retriever_error: str | None = None


def _build_retriever() -> HotelRetriever:
    embedder = GeminiEmbedder() if settings.google_api_key else OfflineEmbedder()
    return HotelRetriever(settings.chroma_path, embedder)


@asynccontextmanager
async def lifespan(_: FastAPI):
    global _retriever, _retriever_error
    try:
        _retriever = _build_retriever()
    except Exception as exc:
        _retriever = None
        _retriever_error = str(exc)
        logger.warning("Indice Chroma non disponibile all'avvio: %s", exc)
    yield


app = FastAPI(title="Hotel RAG API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_retriever() -> HotelRetriever | None:
    """Overridable in tests via app.dependency_overrides."""
    return _retriever


def get_rag_engine(retriever: HotelRetriever | None = Depends(get_retriever)) -> RAGEngine | None:
    """Overridable in tests via app.dependency_overrides."""
    return RAGEngine(retriever) if retriever is not None else None


class ChatRequest(BaseModel):
    query: str
    top_k: int = Field(default=5, ge=1, le=5)


@app.post("/api/chat", response_model=RAGResponse)
def chat(request: ChatRequest, engine: RAGEngine | None = Depends(get_rag_engine)) -> RAGResponse:
    if engine is None:
        return RAGResponse(answer=FALLBACK_MESSAGE, is_fallback=True)
    return engine.answer_query(request.query, top_k=request.top_k)


@app.get("/api/hotels")
def hotels() -> dict[str, Any]:
    path = settings.hotel_records_path
    if not path.exists():
        return {"count": 0, "hotels": []}
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return {"count": len(records), "hotels": records}


@app.get("/api/health")
def health(retriever: HotelRetriever | None = Depends(get_retriever)) -> dict[str, Any]:
    chroma_status: dict[str, Any] = {"connected": retriever is not None}
    if retriever is not None:
        try:
            chroma_status["count"] = retriever.collection.count()
        except Exception as exc:
            chroma_status["connected"] = False
            chroma_status["error"] = str(exc)
    elif _retriever_error:
        chroma_status["error"] = _retriever_error
    return {
        "status": "ok" if retriever is not None else "degraded",
        "chroma": chroma_status,
        "providers": {"groq": bool(settings.groq_api_key), "gemini": bool(settings.google_api_key)},
    }
