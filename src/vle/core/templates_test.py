import os

import pytest

from vle.core.templates import TemplateContractError, load_template, render_template
from vle.exams.bloom_prompts import build_exam_messages
from vle.rag.prompts import build_rag_messages


def test_prompt_templates_load_from_package_when_current_directory_changes(tmp_path):
    original_directory = os.getcwd()
    try:
        os.chdir(tmp_path)
        assert "study assistant" in load_template("vle.rag.prompt_templates", "chat_system.md")
        assert "exam writer" in load_template("vle.exams.prompt_templates", "generate_exam_system.md")
    finally:
        os.chdir(original_directory)


@pytest.mark.parametrize(
    ("template", "allowed", "values", "message"),
    [
        ("Hello {{name}}", set(), {}, "undeclared"),
        ("Hello {{name}}", {"name"}, {}, "missing values"),
        ("Hello", set(), {"name": "Learner"}, "unused values"),
        ("Hello {{name.upper()}}", {"name"}, {"name": "Learner"}, "invalid placeholder"),
    ],
)
def test_template_contracts_reject_invalid_placeholder_usage(template, allowed, values, message):
    with pytest.raises(TemplateContractError, match=message):
        render_template(template, allowed=allowed, values=values)


def test_prompt_builders_return_a_system_and_user_message():
    rag_messages = build_rag_messages("What is BM25?", [])
    exam_messages = build_exam_messages("Book", "Chapter", "source", 1, {"topics": []}, ["remember"])

    assert [message["role"] for message in rag_messages] == ["system", "user"]
    assert [message["role"] for message in exam_messages] == ["system", "user"]


def test_template_contract_renders_only_declared_values():
    assert render_template("Hello {{name}}", allowed={"name"}, values={"name": "Learner"}) == "Hello Learner"
