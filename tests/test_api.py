import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from conftest import require_sample_pdf
from fastapi.testclient import TestClient

import api.main as api_main
from api.main import app, get_rag_engine, get_retriever
from hotelai.config import settings
from ingestion import structured_extractor
from rag.rag_engine import FALLBACK_MESSAGE, RAGResponse

client = TestClient(app)


@pytest.fixture(autouse=True)
def _reset_dependency_overrides():
    yield
    app.dependency_overrides.clear()
    api_main._retriever = None
    api_main._retriever_error = None


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


def test_ingest_rejects_non_pdf_file() -> None:
    response = client.post("/api/ingest", files={"file": ("notes.txt", b"hello", "text/plain")})

    assert response.status_code == 422


def test_ingest_refreshes_hotels_and_warns_when_no_llm_provider_available(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    monkeypatch.setattr(settings, "google_api_key", None)
    monkeypatch.setattr(settings, "groq_api_key", None)

    with require_sample_pdf().open("rb") as handle:
        response = client.post("/api/ingest", files={"file": ("FileHotels.pdf", handle, "application/pdf")})

    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 19
    assert len(body["hotels"]) == 19
    assert body["warning"] is not None
    assert "Groq" in body["warning"] and "Gemini" in body["warning"]

    hotels_response = client.get("/api/hotels")
    assert hotels_response.json()["count"] == 19


def test_ingest_reports_no_warning_when_groq_review_succeeds(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    monkeypatch.setattr(settings, "google_api_key", None)
    monkeypatch.setattr(settings, "groq_api_key", "test-key")

    groq_client = Mock()
    groq_client.chat.completions.create.return_value = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps({"nome": "Hotel di Test"})))]
    )
    monkeypatch.setattr(structured_extractor, "_get_groq_client", lambda: groq_client)

    with require_sample_pdf().open("rb") as handle:
        response = client.post("/api/ingest", files={"file": ("FileHotels.pdf", handle, "application/pdf")})

    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 19
    assert body["warning"] is None
    # Solo i record a bassa confidence deterministica passano dalla revisione LLM
    # (si veda _needs_llm_fallback): non deve essere invocata per tutti i 19 record.
    assert groq_client.chat.completions.create.call_count > 0
