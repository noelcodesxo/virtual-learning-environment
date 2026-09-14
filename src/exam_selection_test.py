import pytest

from exam_selection import build_exam_selection_messages, parse_exam_selection_json


BOOKS = [{"title": "AI Engineering", "chapters": ["2. Understanding Foundation Models"]}]


def test_selection_messages_include_catalog_and_description():
    messages = build_exam_selection_messages("Use the second chapter.", BOOKS)

    assert "Available catalog" in messages[1]["content"]
    assert "AI Engineering" in messages[1]["content"]
    assert "Use the second chapter." in messages[1]["content"]


def test_parse_selection_requires_an_exact_catalog_match():
    raw = '{"book": "AI Engineering", "chapter": "2. Understanding Foundation Models"}'

    assert parse_exam_selection_json(raw, BOOKS) == ("AI Engineering", "2. Understanding Foundation Models")

    with pytest.raises(ValueError, match="does not match"):
        parse_exam_selection_json('{"book": "Other", "chapter": "2"}', BOOKS)
