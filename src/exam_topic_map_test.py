import json

import pytest

from exam_topic_map import TOPIC_MAP_JSON_EXAMPLE, TOPIC_MAP_JSON_SCHEMA, build_topic_map_messages, parse_topic_map_json


CHAPTER_TEXT = "A reward model is trained from human preferences. Evaluation measures helpfulness."
TOPIC_MAP = {
    "topics": [
        {
            "topic": "Reward models",
            "summary": "Reward models learn from human preferences.",
            "source_excerpt": "A reward model is trained from human preferences.",
        }
    ]
}


def test_build_topic_map_messages_includes_selected_source_text():
    messages = build_topic_map_messages("AI Engineering", "Evaluation", CHAPTER_TEXT)

    assert messages[0]["role"] == "system"
    assert "JSON object" in messages[0]["content"]
    assert TOPIC_MAP_JSON_EXAMPLE in messages[0]["content"]
    assert TOPIC_MAP_JSON_SCHEMA["properties"]["topics"]["items"]["required"] == [
        "topic",
        "summary",
        "source_excerpt",
    ]
    assert "AI Engineering" in messages[1]["content"]
    assert CHAPTER_TEXT in messages[1]["content"]


def test_parse_topic_map_json_accepts_fenced_grounded_json():
    raw = f"```json\n{json.dumps(TOPIC_MAP)}\n```"

    assert parse_topic_map_json(raw, CHAPTER_TEXT) == TOPIC_MAP


def test_parse_topic_map_json_rejects_ungrounded_evidence():
    topic_map = {
        "topics": [
            {
                "topic": "Quantum entanglement",
                "summary": "Particles correlate across distance.",
                "source_excerpt": "Invented fact",
            }
        ]
    }

    with pytest.raises(ValueError, match="grounded in the supplied"):
        parse_topic_map_json(json.dumps(topic_map), CHAPTER_TEXT)


def test_parse_topic_map_json_replaces_paraphrased_evidence_with_a_source_sentence():
    topic_map = {
        "topics": [
            {
                "topic": "Reward model training",
                "summary": "A reward model learns from human preferences.",
                "source_excerpt": "People rank outputs to train a reward model.",
            }
        ]
    }

    parsed = parse_topic_map_json(json.dumps(topic_map), CHAPTER_TEXT)

    assert parsed["topics"][0]["source_excerpt"] == "A reward model is trained from human preferences."


def test_parse_topic_map_json_rejects_an_invalid_shape():
    with pytest.raises(ValueError, match="topics array"):
        parse_topic_map_json("[]", CHAPTER_TEXT)


def test_parse_topic_map_json_reports_an_empty_model_response_clearly():
    with pytest.raises(ValueError, match="empty response"):
        parse_topic_map_json("   ", CHAPTER_TEXT)
