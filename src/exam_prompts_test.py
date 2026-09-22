from exam_prompts import build_bloom_question_examples, build_exam_messages


TOPIC_MAP = {
    "topics": [
        {"topic": "Evaluation", "summary": "Measures system quality.", "source_excerpt": "evaluation"}
    ]
}
BLOOM_LEVELS = ["apply", "analyze"]


def test_build_exam_messages_includes_source_chapter_text_and_count():
    messages = build_exam_messages(
        "AI Engineering", "4. Evaluate AI Systems", "chapter text here", 5, TOPIC_MAP, BLOOM_LEVELS
    )

    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    assert "AI Engineering" in messages[1]["content"]
    assert "4. Evaluate AI Systems" in messages[1]["content"]
    assert "chapter text here" in messages[1]["content"]
    assert "5 multiple-choice questions" in messages[1]["content"]
    assert '"topic": "Evaluation"' in messages[1]["content"]
    assert "apply, analyze" in messages[1]["content"]


def test_build_exam_messages_system_prompt_requires_json_array():
    messages = build_exam_messages("Book", "Chapter", "text", 10, TOPIC_MAP, BLOOM_LEVELS)
    assert "JSON array" in messages[0]["content"]
    assert "correct_index" in messages[0]["content"]
    assert "every question must directly assess" in messages[0]["content"]
    assert "central concepts" in messages[0]["content"]
    assert "Avoid trivia" in messages[0]["content"]
    assert "outside knowledge" in messages[0]["content"]
    assert "Bloom's taxonomy levels" in messages[0]["content"]
    assert "topic map" in messages[0]["content"]


def test_build_exam_messages_requires_high_quality_distractors():
    messages = build_exam_messages("Book", "Chapter", "text", 10, TOPIC_MAP, BLOOM_LEVELS)

    assert "Distractor design principles" in messages[0]["content"]
    assert "valid, non-false statement" in messages[0]["content"]
    assert "failing to answer the specific condition, relationship, scope, or task" in messages[0]["content"]
    assert "realistic misconceptions, nearby concepts, partial truths" in messages[0]["content"]
    assert "parallel in grammatical form, detail, and length" in messages[0]["content"]


def test_build_exam_messages_includes_only_examples_for_selected_bloom_levels():
    messages = build_exam_messages("Book", "Chapter", "text", 10, TOPIC_MAP, BLOOM_LEVELS)

    prompt = messages[1]["content"]
    assert "Apply reference questions:" in prompt
    assert "Analyze reference questions:" in prompt
    assert "Use the supplied formula to calculate acceleration" in prompt
    assert "binary BERT classifiers slightly outperformed" in prompt
    assert "Remember reference questions:" not in prompt
    assert "Understand reference questions:" not in prompt
    assert "Evaluate reference questions:" not in prompt
    assert "Create reference questions:" not in prompt


def test_build_bloom_question_examples_preserves_selected_order_without_duplicates():
    examples = build_bloom_question_examples(["evaluate", "remember", "evaluate"])

    assert examples.index("Evaluate reference questions:") < examples.index("Remember reference questions:")
    assert examples.count("Evaluate reference questions:") == 1
    assert "Pilot it with human review" in examples
    assert "How many learning objectives did the researchers collect?" in examples


def test_build_exam_messages_includes_the_learner_description_when_given():
    messages = build_exam_messages(
        "Book", "Chapter", "text", 10, TOPIC_MAP, BLOOM_LEVELS, description="Focus on practical use cases."
    )

    assert "prioritize the exam focus" in messages[1]["content"]
    assert "Focus on practical use cases." in messages[1]["content"]
