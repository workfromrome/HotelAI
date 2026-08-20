"""FastAPI server exposing the Hotel RAG chatbot to the React frontend.

Run with: uvicorn api.main:app --reload --reload-dir src --port 8000 (PYTHONPATH=src, from repo root).
--reload-dir src is required: /api/ingest writes the uploaded PDF and rebuilt index under data/,
and an unrestricted --reload watches the whole repo, so those writes would restart the server mid-request.

The module-level `_retriever` is built once in `lifespan` at startup (or rebuilt by
/api/ingest) and handed to endpoints through `Depends(get_retriever)`/`Depends(get_rag_engine)`
rather than imported directly — that's what lets tests swap in a Mock via
`app.dependency_overrides` without ever touching the real Chroma index (see tests/test_api.py).
"""
from __future__ import annotations

import json
import logging
import shutil
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from hotelai.config import settings
from hotelai.logging_setup import configure_logging
from ingestion.structured_extractor import extract_catalogue, needs_llm_review_warning
from rag.rag_engine import FALLBACK_MESSAGE, RAGEngine, RAGResponse
from search.retriever import HotelRetriever
from search.vector_store import GeminiEmbedder, OfflineEmbedder, build_index_from_csv

configure_logging()
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


@app.exception_handler(Exception)
async def log_unhandled_exception(request: Request, exc: Exception) -> JSONResponse:
    """Catches anything not already turned into an HTTPException (HTTPException has its
    own handler and never reaches here) — genuine bugs, not routine validation errors."""
    logger.error("Errore non gestito su %s %s", request.method, request.url.path, exc_info=exc)
    return JSONResponse(status_code=500, content={"detail": "Errore interno del server"})


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


def _read_hotel_records() -> list[dict[str, Any]]:
    path = settings.hotel_records_path
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


@app.get("/api/hotels")
def hotels() -> dict[str, Any]:
    records = _read_hotel_records()
    return {"count": len(records), "hotels": records}


class IngestResponse(BaseModel):
    count: int
    hotels: list[dict[str, Any]]
    warning: str | None = None


def _safe_upload_name(filename: str | None) -> str:
    """Riduce il filename multipart al solo nome file, senza componenti di path.

    ``UploadFile.filename`` arriva non sanificato dal client: usarlo direttamente per
    costruire un path su disco permette path traversal / scritture arbitrarie (es. un
    filename assoluto tipo 'C:\\Windows\\...\\x.pdf' sovrascriverebbe l'intero path su
    Windows). Si normalizzano prima entrambi i separatori così il comportamento non
    dipende dal sistema operativo su cui gira il server.
    """
    candidate = Path((filename or "").replace("\\", "/")).name
    return candidate or "upload.pdf"


@app.post("/api/ingest", response_model=IngestResponse)
async def ingest(file: UploadFile = File(...)) -> IngestResponse:
    """Re-runs the whole pipeline synchronously on request: save PDF -> extract_catalogue
    (writes CSV+JSONL) -> build_index_from_csv (re-reads the CSV, embeds, upserts into
    Chroma) -> rebuild the module-level retriever so subsequent /api/chat calls see the
    new data immediately. No auth/size limit — acceptable for this take-home demo, would
    need both before being exposed beyond localhost."""
    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(status_code=422, detail="Il file caricato deve essere un PDF")

    safe_filename = _safe_upload_name(file.filename)
    if not safe_filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=422, detail="Il file caricato deve essere un PDF")

    pdf_path = settings.data_dir / "raw" / safe_filename
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    with pdf_path.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    csv_path = settings.data_dir / "processed" / "hotels_data.csv"
    try:
        records = extract_catalogue(pdf_path, csv_path, use_gemini=True)
    except Exception as exc:
        logger.error("Estrazione del PDF fallita (%s)", pdf_path, exc_info=exc)
        raise HTTPException(status_code=422, detail=f"Estrazione del PDF fallita: {exc}") from exc

    embedder = GeminiEmbedder() if settings.google_api_key else OfflineEmbedder()
    try:
        build_index_from_csv(csv_path, embedder=embedder)
    except Exception as exc:
        logger.error("Aggiornamento dell'indice fallito (%s)", csv_path, exc_info=exc)
        raise HTTPException(status_code=500, detail=f"Aggiornamento dell'indice fallito: {exc}") from exc

    global _retriever, _retriever_error
    try:
        _retriever = _build_retriever()
        _retriever_error = None
    except Exception as exc:
        _retriever = None
        _retriever_error = str(exc)

    warning = (
        "Alcuni hotel hanno dati incompleti: né Groq né Gemini erano disponibili per la revisione automatica."
        if needs_llm_review_warning(records)
        else None
    )
    hotel_records = _read_hotel_records()
    return IngestResponse(count=len(hotel_records), hotels=hotel_records, warning=warning)


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
