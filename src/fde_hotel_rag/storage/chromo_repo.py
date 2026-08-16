from collections.abc import Sequence
from ..config import settings
from ..schemas import HotelRecord
class ChromaRepository:
    def __init__(self, embedding_provider, path=None, collection_name=None):
        import chromadb
        self.embedding = embedding_provider; client = chromadb.PersistentClient(path=str(path or settings.chroma_path))
        self.collection = client.get_or_create_collection(collection_name or settings.collection_name)
    def upsert(self, records: Sequence[HotelRecord]) -> int:
        rows = list(records); texts = [r.searchable_text() for r in rows]
        self.collection.upsert(ids=[f"hotel-{i}" for i in range(len(rows))], documents=texts, embeddings=self.embedding.embed(texts), metadatas=[r.metadata() for r in rows])
        return self.collection.count()
    def search(self, query: str, limit: int) -> list[dict]:
        if not query.strip(): raise ValueError("La query non può essere vuota")
        result = self.collection.query(query_embeddings=self.embedding.embed([query]), n_results=limit, include=["documents","metadatas","distances"])
        return [{"metadata": m, "document": d, "distance": float(dist)} for m,d,dist in zip(result["metadatas"][0], result["documents"][0], result["distances"][0], strict=True)]
