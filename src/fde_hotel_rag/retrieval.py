import re
from collections.abc import Sequence
from .config import settings
def document_from_row(row: dict[str, str]) -> str:
    return "\n".join((f"Servizi: {value}" if key == "services" else f"{key}: {value}") for key, value in row.items())

class GoogleEmbeddingProvider:
    def __init__(self):
        if not settings.google_api_key: raise RuntimeError("GOOGLE_API_KEY non è configurata")
        from google import genai
        self.client = genai.Client(api_key=settings.google_api_key)
    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [item.values for item in self.client.models.embed_content(model=settings.embedding_model, contents=list(texts)).embeddings]
from .config import settings
def metadata_score(query: str, metadata: dict[str, str]) -> float:
    words = set(re.findall(r"\w+", query.lower()))
    values = " ".join(metadata.values()).lower()
    return len(words & set(re.findall(r"\w+", values))) / max(len(words), 1)
class HybridRetriever:
    def __init__(self, repository): self.repository = repository
    def search(self, query: str, limit: int | None = None) -> list[dict]:
        rows = self.repository.search(query, min(limit or settings.retrieval_limit, settings.retrieval_limit))
        for row in rows: row["metadata_score"] = metadata_score(query, row["metadata"])
        return sorted(rows, key=lambda r: settings.vector_weight * (1/(1+r["distance"])) + settings.metadata_weight * r["metadata_score"], reverse=True)
def format_results(results: list[dict]) -> str:
    if not results: return "Nessuna struttura trovata."
    return "\n\n".join(f"{i}. {r['metadata'].get('name','Hotel')} - {r['metadata'].get('locality','Non specificata')}\nServizi: {r['metadata'].get('services','non specificati')}" for i,r in enumerate(results,1))
