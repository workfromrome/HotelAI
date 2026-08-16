from __future__ import annotations
from fastmcp import FastMCP
from search.retriever import HotelRetriever, format_results

mcp = FastMCP("Hotel-Search-RAG")
_retriever: HotelRetriever | None = None

def configure_retriever(retriever: HotelRetriever) -> None:
    global _retriever
    _retriever = retriever

@mcp.tool()
def search_hotels(query: str) -> str:
    """Cerca hotel nel catalogo e restituisce i cinque risultati più rilevanti."""
    if _retriever is None:
        return "Retriever non configurato: inizializzare l'indice prima di avviare il server."
    try: return format_results(_retriever.search_hotels(query, top_k=5))
    except ValueError as exc: return str(exc)

if __name__ == "__main__": mcp.run()
