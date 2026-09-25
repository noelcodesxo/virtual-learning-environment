import pytest

from vle.core.config import Settings


def _clear_topic_map_environment(monkeypatch):
    for name in ("EXAM_MODEL", "EXAM_TOPIC_MAP_PROVIDER", "EXAM_TOPIC_MAP_MODEL", "LLM_MODEL"):
        monkeypatch.delenv(name, raising=False)


def test_topic_map_defaults_to_the_openrouter_exam_model(monkeypatch):
    _clear_topic_map_environment(monkeypatch)
    monkeypatch.setenv("EXAM_MODEL", "provider/large-context-model")

    settings = Settings.from_environment()

    assert settings.exam_topic_map_provider == "openrouter"
    assert settings.exam_topic_map_model == "provider/large-context-model"


def test_explicit_ollama_topic_map_uses_the_local_chat_model_by_default(monkeypatch):
    _clear_topic_map_environment(monkeypatch)
    monkeypatch.setenv("LLM_MODEL", "local-chat-model")
    monkeypatch.setenv("EXAM_MODEL", "provider/exam-model")
    monkeypatch.setenv("EXAM_TOPIC_MAP_PROVIDER", "ollama")

    settings = Settings.from_environment()

    assert settings.exam_topic_map_provider == "ollama"
    assert settings.exam_topic_map_model == "local-chat-model"


@pytest.mark.parametrize("provider", ["openrouter", "ollama"])
def test_explicit_topic_map_model_overrides_provider_default(monkeypatch, provider):
    _clear_topic_map_environment(monkeypatch)
    monkeypatch.setenv("EXAM_TOPIC_MAP_PROVIDER", provider)
    monkeypatch.setenv("EXAM_TOPIC_MAP_MODEL", "custom/topic-model")

    settings = Settings.from_environment()

    assert settings.exam_topic_map_model == "custom/topic-model"
