"""Hybrid search over the Chroma index: vector similarity + lexical metadata overlap,
capped at settings.retrieval_limit (5) results regardless of what the caller asks for.
Used directly by mcp_server.server and indirectly by RAGEngine (search/../rag/rag_engine.py)."""
from __future__ import annotations
import re
from pathlib import Path
import chromadb
from hotelai.config import settings
from .vector_store import Embedder, OfflineEmbedder

def _metadata_score(query: str, metadata: dict[str, str]) -> float:
    """Fraction of the query's words that also appear somewhere in the record's metadata
    values (bag-of-words, no stemming/synonyms). Since `document_from_record` puts most
    HotelRecord fields into metadata as text, this mostly re-scores the same words the
    vector search already saw — it's a lexical nudge on top of semantic similarity, not
    an independent structured-field filter (e.g. it won't specifically check `pet_friendly`)."""
    query_terms = set(re.findall(r"\w+", query.lower()))
    value_terms = set(re.findall(r"\w+", " ".join(metadata.values()).lower()))
    return len(query_terms & value_terms) / max(len(query_terms), 1)

class HotelRetriever:
    def __init__(self, path: Path | None = None, embedder: Embedder | None = None) -> None:
        """`embedder` must match whatever built the index at `path` — mixing a real
        GeminiEmbedder query against an OfflineEmbedder-built index (or vice versa)
        would run, just return meaningless distances, since the vector spaces differ."""
        client = chromadb.PersistentClient(path=str(path or settings.chroma_path))
        try: self.collection = client.get_collection(settings.collection_name)
        except Exception as exc: raise RuntimeError("Collection hotels non trovata: eseguire prima l'indicizzazione") from exc
        self.embedder = embedder or OfflineEmbedder()

    def search_hotels(self, query: str, top_k: int = settings.retrieval_limit) -> list[dict]:
        if not query.strip(): raise ValueError("La query non può essere vuota")
        limit = min(max(top_k, 1), settings.retrieval_limit)  # never returns more than 5, whatever top_k the caller passes
        result = self.collection.query(query_embeddings=self.embedder.embed([query]), n_results=limit, include=["documents", "metadatas", "distances"])
        matches = []
        for document, metadata, distance in zip(result["documents"][0], result["metadatas"][0], result["distances"][0], strict=True):
            vector_score = 1 / (1 + float(distance))  # Chroma returns a distance (lower = closer); this turns it into a 0..1-ish similarity
            metadata_score = _metadata_score(query, metadata)
            matches.append({"metadata": metadata, "document": document, "distance": float(distance), "similarity": settings.vector_weight * vector_score + settings.metadata_weight * metadata_score})
        return sorted(matches, key=lambda item: item["similarity"], reverse=True)

def format_results(results: list[dict]) -> str:
    """Raw Markdown for the MCP tool's response — no LLM synthesis involved, just the
    ranked search_hotels() output rendered as text (contrast with RAGEngine.answer_query)."""
    if not results: return "Nessuna struttura trovata."
    return "\n\n".join(f"### {i}. {r['metadata'].get('nome', 'Hotel')}\n- Località: {r['metadata'].get('localita', 'Non specificata')}\n- Stelle: {r['metadata'].get('stelle', 'non specificate')}\n- Similarità: {r['similarity']:.3f}\n- Scheda: {r['document'][:320]}" for i, r in enumerate(results, 1))
