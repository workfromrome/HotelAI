from __future__ import annotations
from fastmcp import FastMCP
from fde_hotel_rag.config import settings
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
    try: return format_results(_retriever.search_hotels(query, top_k=5))
    except ValueError as exc: return str(exc)

if __name__ == "__main__":
    configure_retriever(_build_retriever())
    mcp.run()
