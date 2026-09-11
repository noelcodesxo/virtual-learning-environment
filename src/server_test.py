import urllib.error

import pytest
from fastapi import HTTPException

import server
from server import ChatRequest, chat, list_models


class _FakeResponse:
    def __init__(self, payload):
        import json

        self._payload = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        from io import BytesIO

        return BytesIO(self._payload)

    def __exit__(self, *args):
        return False


class _FakeRetriever:
    def __init__(self, results):
        self._results = results

    def search(self, query, index, top_k=None):
        return self._results


class _FakeClient:
    def __init__(self, answer):
        self._answer = answer

    def chat(self, messages):
        return self._answer


def test_list_models_returns_sorted_model_names(monkeypatch):
    def fake_urlopen(request, timeout=None):
        return _FakeResponse({"models": [{"name": "qwen3:8b"}, {"name": "llama3"}]})

    monkeypatch.setattr(server.urllib.request, "urlopen", fake_urlopen)

    response = list_models()

    assert response.models == ["llama3", "qwen3:8b"]


def test_list_models_raises_502_when_ollama_unreachable(monkeypatch):
    def fake_urlopen(request, timeout=None):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(server.urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(HTTPException) as exc_info:
        list_models()

    assert exc_info.value.status_code == 502


def test_chat_returns_answer_and_sources_from_retrieved_chunks(monkeypatch):
    results = [
        {
            "book": "AI Engineering",
            "chapter": "Ch. 4",
            "section": "RLHF",
            "text": "rlhf trains a reward model on human preferences",
            "score": 0.82,
        },
    ]
    monkeypatch.setitem(server.state, "index", [])
    monkeypatch.setitem(server.state, "retriever", _FakeRetriever(results))
    monkeypatch.setattr(server, "build_client", lambda provider, model, base_url=None: _FakeClient("the answer"))

    response = chat(ChatRequest(query="what is RLHF?", model="qwen3:8b"))

    assert response.answer == "the answer"
    assert response.sources == [
        server.Source(book="AI Engineering", chapter="Ch. 4", section="RLHF", score=0.82)
    ]


def test_chat_rejects_empty_query():
    with pytest.raises(HTTPException) as exc_info:
        chat(ChatRequest(query="   "))

    assert exc_info.value.status_code == 400
