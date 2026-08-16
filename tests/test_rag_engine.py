from types import SimpleNamespace
from unittest.mock import Mock

from rag.rag_engine import FALLBACK_MESSAGE, RAGEngine


def _client(answer: str) -> Mock:
    client = Mock()
    client.models.generate_content.return_value = SimpleNamespace(text=answer)
    return client


def test_relevant_answer_contains_citations() -> None:
    retriever = Mock()
    retriever.search_hotels.return_value = [{
        "metadata": {"nome": "Bravo Alimini", "source_pages": "2 | 3"},
        "document": "Formula Alpiclub con pensione completa e servizi inclusi.",
    }]
    engine = RAGEngine(retriever, client=_client("Bravo Alimini offre la formula Alpiclub [Pag. 2-3]."))
    result = engine.answer_query("Quali hotel hanno la formula Alpiclub?")
    assert result.answer.endswith("[Pag. 2-3].")
    assert result.source_pages == [2, 3]
    assert result.retrieved_hotels == ["Bravo Alimini"]
    assert result.is_fallback is False


def test_missing_information_returns_exact_fallback() -> None:
    retriever = Mock()
    retriever.search_hotels.return_value = [{
        "metadata": {"nome": "Bravo Alimini", "source_pages": "2 | 3"},
        "document": "Servizi e trattamento dell'hotel.",
    }]
    engine = RAGEngine(retriever, client=_client(FALLBACK_MESSAGE))
    result = engine.answer_query("Qual è il prezzo del volo per la Grecia?")
    assert result.answer == FALLBACK_MESSAGE
    assert result.is_fallback is True


def test_empty_query_does_not_call_dependencies() -> None:
    retriever = Mock()
    client = _client("non deve essere usato")
    result = RAGEngine(retriever, client=client).answer_query("   ")
    assert result.answer == FALLBACK_MESSAGE
    retriever.search_hotels.assert_not_called()
    client.models.generate_content.assert_not_called()
