import json

import pytest

from exam_parser import parse_exam_json


def _question(**overrides):
    base = {
        "section": "Evaluation Criteria",
        "question": "What is X?",
        "options": ["A", "B", "C"],
        "correct_index": 1,
        "why": "Because B is right.",
    }
    base.update(overrides)
    return base


def test_parses_plain_json_array():
    assert parse_exam_json(json.dumps([_question()])) == [_question()]


def test_strips_markdown_json_fence():
    raw = "```json\n" + json.dumps([_question()]) + "\n```"
    assert parse_exam_json(raw) == [_question()]


def test_raises_on_invalid_json():
    with pytest.raises(ValueError):
        parse_exam_json("not json at all")


def test_raises_when_not_a_list():
    with pytest.raises(ValueError):
        parse_exam_json(json.dumps(_question()))


def test_raises_on_empty_list():
    with pytest.raises(ValueError):
        parse_exam_json(json.dumps([]))


def test_raises_when_missing_required_field():
    question = _question()
    del question["why"]
    with pytest.raises(ValueError):
        parse_exam_json(json.dumps([question]))


def test_raises_when_options_count_is_not_three():
    with pytest.raises(ValueError):
        parse_exam_json(json.dumps([_question(options=["A", "B"])]))


def test_raises_when_correct_index_out_of_range():
    with pytest.raises(ValueError):
        parse_exam_json(json.dumps([_question(correct_index=9)]))
