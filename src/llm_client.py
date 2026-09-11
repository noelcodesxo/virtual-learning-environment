import json
import os
import urllib.request
from abc import ABC, abstractmethod


class LLMClient(ABC):
    @abstractmethod
    def chat(self, messages: list[dict[str, str]]) -> str:
        pass


def _post_json(url: str, payload: dict, headers: dict[str, str]) -> dict:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )
    with urllib.request.urlopen(request) as response:
        return json.load(response)


class OllamaClient(LLMClient):
    def __init__(self, model: str, base_url: str = "http://localhost:11434"):
        self.model = model
        self.base_url = base_url.rstrip("/")

    def chat(self, messages: list[dict[str, str]]) -> str:
        payload = {"model": self.model, "messages": messages, "stream": False}
        data = _post_json(f"{self.base_url}/api/chat", payload, headers={})
        return data["message"]["content"]


class OpenAICompatibleClient(LLMClient):
    # Any provider exposing an OpenAI-style /chat/completions endpoint (OpenRouter, and future ones) can subclass this.
    def __init__(self, model: str, base_url: str, api_key: str):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    def chat(self, messages: list[dict[str, str]]) -> str:
        payload = {"model": self.model, "messages": messages}
        headers = {"Authorization": f"Bearer {self.api_key}"}
        data = _post_json(f"{self.base_url}/chat/completions", payload, headers)
        return data["choices"][0]["message"]["content"]


class OpenRouterClient(OpenAICompatibleClient):
    def __init__(self, model: str, api_key: str | None = None):
        api_key = api_key or os.environ["OPENROUTER_API_KEY"]
        super().__init__(model, base_url="https://openrouter.ai/api/v1", api_key=api_key)


def build_client(provider: str, model: str, base_url: str | None = None) -> LLMClient:
    if provider == "ollama":
        return OllamaClient(model, base_url=base_url or os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434"))
    if provider == "openrouter":
        return OpenRouterClient(model)
    raise ValueError(f"Unknown provider: {provider}")
