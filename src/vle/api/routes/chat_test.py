import pytest
from fastapi import HTTPException

from vle.api.routes import chat
from vle.api.schemas.chat import ChatRequest
from vle.core.config import Settings


class _Retriever:
    def search(self, query, index):
        return [{"book": "Book", "chapter": "One", "section": "Intro", "text": "fact", "score": 0.8}]


class _Client:
    def chat(self, messages):
        return "answer"


def _settings(tmp_path):
    return Settings(tmp_path / "resources", tmp_path / "index.json", tmp_path / "exams",
                    "http://ollama.test", "test-model", False, "test/exam")


def test_chat_preserves_response_contract_and_rejects_blank_queries(monkeypatch, tmp_path):
    monkeypatch.setattr(chat, "build_client", lambda *args, **kwargs: _Client())
    response = chat.chat(ChatRequest(query="what?"), _settings(tmp_path), [], _Retriever())
    assert response.model_dump() == {"answer": "answer", "sources": [{"book": "Book", "chapter": "One", "section": "Intro", "score": 0.8}]}
    with pytest.raises(HTTPException) as error:
        chat.chat(ChatRequest(query="   "), _settings(tmp_path), [], _Retriever())
    assert error.value.status_code == 400
    assert error.value.detail == "query must not be empty"
