"""Canonical MCP server: exposes hotel search as a single FastMCP tool.

This is the deliverable for "Parte 2" of the assignment brief — no LLM synthesis here,
just `HotelRetriever.search_hotels` formatted as Markdown (contrast with the web app's
`RAGEngine`, which adds a conversational LLM layer on top of the same retriever). Start
with `python -m mcp_server.server`; `configure_retriever` exists so tests can inject a
retriever built against a temp Chroma path instead of the real one (see tests/test_mcp_server.py).
"""
from __future__ import annotations
from fastmcp import FastMCP
from hotelai.config import settings
from hotelai.logging_setup import configure_logging
from search.retriever import HotelRetriever, format_results
from search.vector_store import GeminiEmbedder, OfflineEmbedder

mcp = FastMCP("Hotel-Search-RAG")
_retriever: HotelRetriever | None = None

def configure_retriever(retriever: HotelRetriever) -> None:
    global _retriever
    _retriever = retriever

def _build_retriever() -> HotelRetriever:
    embedder = GeminiEmbedder() if settings.google_api_key else OfflineEmbedder()
    return HotelRetriever(settings.chroma_path, embedder)

@mcp.tool()
def search_hotels(query: str) -> str:
    """Cerca hotel nel catalogo e restituisce i cinque risultati più rilevanti."""
    if _retriever is None:
        return "Retriever non configurato: inizializzare l'indice prima di avviare il server."
    try: return format_results(_retriever.search_hotels(query, top_k=5))  # top_k=5 hardcoded: the assignment's "primi 5 risultati" requirement
    except ValueError as exc: return str(exc)

if __name__ == "__main__":
    configure_logging()
    configure_retriever(_build_retriever())
    mcp.run()
