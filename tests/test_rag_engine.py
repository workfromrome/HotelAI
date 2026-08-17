from types import SimpleNamespace
from unittest.mock import Mock

from rag.rag_engine import FALLBACK_MESSAGE, RAGEngine


def _retriever_with(nome: str, source_pages: str, document: str) -> Mock:
    retriever = Mock()
    retriever.search_hotels.return_value = [{"metadata": {"nome": nome, "source_pages": source_pages}, "document": document}]
    return retriever


def _groq_client(answer: str) -> Mock:
    client = Mock()
    client.chat.completions.create.return_value = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=answer))]
    )
    return client


def _gemini_client(answer: str) -> Mock:
    client = Mock()
    client.models.generate_content.return_value = SimpleNamespace(text=answer)
    return client


def test_relevant_answer_contains_citations() -> None:
    retriever = _retriever_with("Bravo Alimini", "2 | 3", "Formula Alpiclub con pensione completa e servizi inclusi.")
    groq_client = _groq_client("Bravo Alimini offre la formula Alpiclub [Pag. 2-3].")
    engine = RAGEngine(retriever, groq_client=groq_client)

    result = engine.answer_query("Quali hotel hanno la formula Alpiclub?")

    assert result.answer.endswith("[Pag. 2-3].")
    assert result.source_pages == [2, 3]
    assert result.retrieved_hotels == ["Bravo Alimini"]
    assert result.is_fallback is False
    groq_client.chat.completions.create.assert_called_once()


def test_missing_information_returns_exact_fallback() -> None:
    retriever = _retriever_with("Bravo Alimini", "2 | 3", "Servizi e trattamento dell'hotel.")
    engine = RAGEngine(retriever, groq_client=_groq_client(FALLBACK_MESSAGE))

    result = engine.answer_query("Qual è il prezzo del volo per la Grecia?")

    assert result.answer == FALLBACK_MESSAGE
    assert result.is_fallback is True


def test_empty_query_does_not_call_dependencies() -> None:
    retriever = Mock()
    groq_client = _groq_client("non deve essere usato")
    gemini_client = _gemini_client("non deve essere usato")

    result = RAGEngine(retriever, groq_client=groq_client, gemini_client=gemini_client).answer_query("   ")

    assert result.answer == FALLBACK_MESSAGE
    assert result.is_fallback is True
    retriever.search_hotels.assert_not_called()
    groq_client.chat.completions.create.assert_not_called()
    gemini_client.models.generate_content.assert_not_called()


def test_no_results_returns_fallback_without_calling_llm() -> None:
    retriever = Mock()
    retriever.search_hotels.return_value = []
    groq_client = _groq_client("non deve essere usato")

    result = RAGEngine(retriever, groq_client=groq_client).answer_query("hotel con piscina sulla luna")

    assert result.answer == FALLBACK_MESSAGE
    assert result.is_fallback is True
    groq_client.chat.completions.create.assert_not_called()


def test_groq_failure_falls_back_to_gemini() -> None:
    retriever = _retriever_with("Bravo Alimini", "2 | 3", "Formula Alpiclub con pensione completa.")
    groq_client = Mock()
    groq_client.chat.completions.create.side_effect = RuntimeError("429 Too Many Requests")
    gemini_client = _gemini_client("Bravo Alimini offre la formula Alpiclub [Pag. 2-3].")

    result = RAGEngine(retriever, groq_client=groq_client, gemini_client=gemini_client).answer_query("Alpiclub?")

    assert result.answer.endswith("[Pag. 2-3].")
    assert result.is_fallback is False
    groq_client.chat.completions.create.assert_called_once()
    gemini_client.models.generate_content.assert_called_once()


def test_both_providers_failing_returns_fallback_message() -> None:
    retriever = _retriever_with("Bravo Alimini", "2 | 3", "Formula Alpiclub con pensione completa.")
    groq_client = Mock()
    groq_client.chat.completions.create.side_effect = RuntimeError("503 Service Unavailable")
    gemini_client = Mock()
    gemini_client.models.generate_content.side_effect = RuntimeError("503 Service Unavailable")

    result = RAGEngine(retriever, groq_client=groq_client, gemini_client=gemini_client).answer_query("Alpiclub?")

    assert result.answer == FALLBACK_MESSAGE
    assert result.is_fallback is True
