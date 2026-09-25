import pytest

from vle.core.config import Settings


_EXAM_SETTING_KEYS = (
    "LLM_MODEL",
    "EXAM_MODEL",
    "EXAM_TOPIC_MAP_PROVIDER",
    "EXAM_TOPIC_MAP_MODEL",
)


def _clear_exam_settings(monkeypatch):
    for key in _EXAM_SETTING_KEYS:
        monkeypatch.delenv(key, raising=False)


def test_topic_map_defaults_to_openrouter_and_the_effective_exam_model(monkeypatch):
    _clear_exam_settings(monkeypatch)
    monkeypatch.setenv("EXAM_MODEL", "openrouter/final-exam-model")

    settings = Settings.from_environment()

    assert settings.exam_topic_map_provider == "openrouter"
    assert settings.exam_topic_map_model == settings.exam_model == "openrouter/final-exam-model"


def test_explicit_ollama_topic_map_provider_uses_llm_model_by_default(monkeypatch):
    _clear_exam_settings(monkeypatch)
    monkeypatch.setenv("LLM_MODEL", "local-topic-model")
    monkeypatch.setenv("EXAM_TOPIC_MAP_PROVIDER", "ollama")

    settings = Settings.from_environment()

    assert settings.exam_topic_map_provider == "ollama"
    assert settings.exam_topic_map_model == "local-topic-model"


@pytest.mark.parametrize("provider", ["openrouter", "ollama"])
def test_explicit_topic_map_model_overrides_either_provider(monkeypatch, provider):
    _clear_exam_settings(monkeypatch)
    monkeypatch.setenv("EXAM_TOPIC_MAP_PROVIDER", provider)
    monkeypatch.setenv("EXAM_TOPIC_MAP_MODEL", "explicit-topic-model")

    settings = Settings.from_environment()

    assert settings.exam_topic_map_provider == provider
    assert settings.exam_topic_map_model == "explicit-topic-model"
