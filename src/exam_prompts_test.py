from exam_prompts import build_exam_messages


def test_build_exam_messages_includes_book_chapter_text_and_count():
    messages = build_exam_messages("AI Engineering", "4. Evaluate AI Systems", "chapter text here", 5)

    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    assert "AI Engineering" in messages[1]["content"]
    assert "4. Evaluate AI Systems" in messages[1]["content"]
    assert "chapter text here" in messages[1]["content"]
    assert "5 multiple-choice questions" in messages[1]["content"]


def test_build_exam_messages_system_prompt_requires_json_array():
    messages = build_exam_messages("Book", "Chapter", "text", 10)
    assert "JSON array" in messages[0]["content"]
    assert "correct_index" in messages[0]["content"]
    assert "every question must directly assess" in messages[0]["content"]
    assert "central concepts" in messages[0]["content"]
    assert "Avoid trivia" in messages[0]["content"]
    assert "outside knowledge" in messages[0]["content"]


def test_build_exam_messages_includes_the_learner_description_when_given():
    messages = build_exam_messages("Book", "Chapter", "text", 10, description="Focus on practical use cases.")

    assert "prioritize the exam focus" in messages[1]["content"]
    assert "Focus on practical use cases." in messages[1]["content"]
