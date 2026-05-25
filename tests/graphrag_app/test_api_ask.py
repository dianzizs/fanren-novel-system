"""API contract tests for GraphRAG-backed ask endpoint."""

from __future__ import annotations

import threading

from fastapi.testclient import TestClient

import novel_system.api as api_module
from novel_system.graphrag_app.answer_adapter import GraphRAGAnswerAdapter
from novel_system.graphrag_app.query_engine import GraphRAGQueryResult
from novel_system.graphrag_app.query_router import GraphRAGQueryRouter
from novel_system.services.qa import QAServiceMixin


class FakeQueryEngine:
    def __init__(self, result: GraphRAGQueryResult) -> None:
        self.result = result
        self.calls: list[dict] = []

    async def search(self, **kwargs):
        self.calls.append(kwargs)
        return self.result


class FakeQAService(QAServiceMixin):
    def __init__(self, result: GraphRAGQueryResult) -> None:
        self.graphrag_query_router = GraphRAGQueryRouter()
        self.graphrag_query_engine = FakeQueryEngine(result)
        self.graphrag_answer_adapter = GraphRAGAnswerAdapter()
        self.session_memory = {}
        self._lock = threading.Lock()
        self.indexed_books: list[str] = []

    def ensure_indexed(self, book_id: str) -> None:
        self.indexed_books.append(book_id)

    def _remember_turns(self, session_id: str, query: str, answer: str) -> None:
        with self._lock:
            self.session_memory.setdefault(session_id, []).extend([query, answer])


def _client_for(monkeypatch, test_config, service: FakeQAService) -> TestClient:
    (test_config.root_dir / "static").mkdir(parents=True, exist_ok=True)
    (test_config.root_dir / "templates").mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(api_module.AppConfig, "load", lambda: test_config)
    monkeypatch.setattr(api_module, "create_service", lambda: service)
    return TestClient(api_module.create_app())


def test_api_ask_uses_graphrag_engine_and_returns_response_contract(monkeypatch, test_config):
    service = FakeQAService(
        GraphRAGQueryResult(
            response="韩立是主角。",
            context_data={},
            mode="global",
            matched_entities=["韩立"],
            used_community_reports=[],
            used_text_units=[],
        )
    )
    client = _client_for(monkeypatch, test_config, service)

    response = client.post(
        "/api/books/book%2520one/ask",
        json={"user_query": "这本书的主题是什么？", "session_id": "s1", "debug": True},
    )

    assert response.status_code == 200
    body = response.json()
    assert service.indexed_books == ["book one"]
    assert service.graphrag_query_engine.calls[0]["book_id"] == "book one"
    assert service.graphrag_query_engine.calls[0]["query"] == "这本书的主题是什么？"
    assert service.graphrag_query_engine.calls[0]["mode"] == "global"
    assert body["answer"] == "韩立是主角。"
    assert body["confidence"] == "high"
    assert body["evidence"][0]["title"] == "韩立"
    assert body["memory"]["search_mode"] == "global"
    assert body["trace"]["book_id"] == "book one"
    assert body["trace"]["retrieval"]["hits_count"] == 1


def test_api_ask_respects_requested_search_mode_and_forwards_history(monkeypatch, test_config):
    service = FakeQAService(
        GraphRAGQueryResult(
            response="墨大夫这样做另有目的。",
            context_data={},
            mode="drift",
            matched_entities=["墨大夫"],
            used_community_reports=[],
            used_text_units=[],
        )
    )
    client = _client_for(monkeypatch, test_config, service)

    response = client.post(
        "/api/books/test-book/ask",
        json={
            "user_query": "墨大夫这样做的动机是什么？",
            "search_mode": "drift",
            "conversation_history": [{"role": "user", "content": "前情提要"}],
        },
    )

    assert response.status_code == 200
    call = service.graphrag_query_engine.calls[0]
    assert call["mode"] == "drift"
    assert call["conversation_history"] == [{"role": "user", "content": "前情提要"}]
    assert response.json()["memory"]["matched_entities"] == ["墨大夫"]
