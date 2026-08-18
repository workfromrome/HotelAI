from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from api.main import app, get_rag_engine, get_retriever
from rag.rag_engine import FALLBACK_MESSAGE, RAGResponse

client = TestClient(app)


@pytest.fixture(autouse=True)
def _reset_dependency_overrides():
    yield
    app.dependency_overrides.clear()


def test_chat_returns_200_with_answer_and_citations() -> None:
    engine = Mock()
    engine.answer_query.return_value = RAGResponse(
        answer="Bravo Alimini offre pensione completa [Pag. 2-3].",
        source_pages=[2, 3],
        retrieved_hotels=["Bravo Alimini"],
        is_fallback=False,
    )
    app.dependency_overrides[get_rag_engine] = lambda: engine

    response = client.post("/api/chat", json={"query": "pensione completa?", "top_k": 3})

    assert response.status_code == 200
    body = response.json()
    assert body["answer"].endswith("[Pag. 2-3].")
    assert body["source_pages"] == [2, 3]
    assert body["retrieved_hotels"] == ["Bravo Alimini"]
    assert body["is_fallback"] is False
    engine.answer_query.assert_called_once_with("pensione completa?", top_k=3)


def test_chat_falls_back_when_rag_engine_unavailable() -> None:
    app.dependency_overrides[get_rag_engine] = lambda: None

    response = client.post("/api/chat", json={"query": "hotel con piscina"})

    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == FALLBACK_MESSAGE
    assert body["is_fallback"] is True


def test_hotels_endpoint_returns_19_records() -> None:
    response = client.get("/api/hotels")

    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 19
    assert len(body["hotels"]) == 19
    assert "nome" in body["hotels"][0]


def test_health_endpoint_reports_connected_index() -> None:
    retriever = Mock()
    retriever.collection.count.return_value = 19
    app.dependency_overrides[get_retriever] = lambda: retriever

    response = client.get("/api/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["chroma"] == {"connected": True, "count": 19}
    assert set(body["providers"]) == {"groq", "gemini"}


def test_health_endpoint_degraded_without_index() -> None:
    app.dependency_overrides[get_retriever] = lambda: None

    response = client.get("/api/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded"
    assert body["chroma"]["connected"] is False
