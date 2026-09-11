import json
from io import BytesIO

import pytest

import llm_client
from llm_client import OllamaClient, OpenRouterClient, build_client


class _FakeResponse:
    def __init__(self, payload):
        self._payload = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return BytesIO(self._payload)

    def __exit__(self, *args):
        return False


def test_ollama_client_posts_messages_and_returns_reply(monkeypatch):
    captured = {}

    def fake_urlopen(request):
        captured["url"] = request.full_url
        captured["body"] = json.loads(request.data)
        return _FakeResponse({"message": {"content": "hello"}})

    monkeypatch.setattr(llm_client.urllib.request, "urlopen", fake_urlopen)

    client = OllamaClient(model="llama3")
    reply = client.chat([{"role": "user", "content": "hi"}])

    assert reply == "hello"
    assert captured["url"] == "http://localhost:11434/api/chat"
    assert captured["body"] == {
        "model": "llama3",
        "messages": [{"role": "user", "content": "hi"}],
        "stream": False,
    }


def test_ollama_client_uses_custom_base_url(monkeypatch):
    captured = {}

    def fake_urlopen(request):
        captured["url"] = request.full_url
        return _FakeResponse({"message": {"content": "hello"}})

    monkeypatch.setattr(llm_client.urllib.request, "urlopen", fake_urlopen)

    client = OllamaClient(model="llama3", base_url="http://remote:11434/")
    client.chat([{"role": "user", "content": "hi"}])

    assert captured["url"] == "http://remote:11434/api/chat"


def test_openrouter_client_sends_bearer_token_and_parses_choice(monkeypatch):
    captured = {}

    def fake_urlopen(request):
        captured["headers"] = request.headers
        captured["url"] = request.full_url
        return _FakeResponse({"choices": [{"message": {"content": "hi there"}}]})

    monkeypatch.setattr(llm_client.urllib.request, "urlopen", fake_urlopen)

    client = OpenRouterClient(model="some/model", api_key="test-key")
    reply = client.chat([{"role": "user", "content": "hi"}])

    assert reply == "hi there"
    assert captured["url"] == "https://openrouter.ai/api/v1/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer test-key"


def test_openrouter_client_falls_back_to_env_var_api_key(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "env-key")
    client = OpenRouterClient(model="some/model")
    assert client.api_key == "env-key"


def test_build_client_returns_ollama_client_for_ollama_provider():
    assert isinstance(build_client("ollama", "llama3"), OllamaClient)


def test_build_client_returns_openrouter_client_for_openrouter_provider(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "env-key")
    assert isinstance(build_client("openrouter", "some/model"), OpenRouterClient)


def test_build_client_raises_for_unknown_provider():
    with pytest.raises(ValueError):
        build_client("unknown", "model")
