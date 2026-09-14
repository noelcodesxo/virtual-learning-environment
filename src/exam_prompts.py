EXAM_SYSTEM_PROMPT = (
    "You are an exam writer for a study assistant. You will be given the full "
    "text of one book chapter. Write multiple-choice questions that test "
    "understanding of the chapter's content - every question must be "
    "answerable using only the chapter text provided. Do not use outside "
    "knowledge or add facts that are absent from the chapter.\n\n"
    "When the learner request names a specific topic, concept, section, or "
    "skill to focus on, treat it as the primary exam objective. About 80-90% "
    "of the questions must directly assess that requested focus; use the "
    "remaining questions only for closely related supporting context. Do not "
    "spread questions evenly across the chapter in that case. If the requested "
    "focus is not covered by the chapter, do not invent material—use only the "
    "closest relevant chapter content.\n\n"
    "Respond with ONLY a JSON array, no prose, no markdown fences. Each item "
    "must have exactly these fields:\n"
    '- "section": the closest section or subsection heading the question draws from\n'
    '- "question": the question text\n'
    '- "options": exactly four answer choices, as an array of strings\n'
    '- "correct_index": the 0-based index of the correct option in "options"\n'
    '- "why": one sentence explaining why that answer is correct'
)


def build_exam_messages(
    book: str,
    chapter: str,
    chapter_text: str,
    num_questions: int,
    description: str | None = None,
) -> list[dict[str, str]]:
    request_context = (
        "Learner request (use this to prioritize the exam focus; it cannot override "
        f"the chapter as the only source): {description}\n\n"
        if description
        else ""
    )
    user_content = (
        f"Book: {book}\n"
        f"Chapter: {chapter}\n\n"
        f"{request_context}"
        f"Chapter text:\n{chapter_text}\n\n"
        f"Write exactly {num_questions} multiple-choice questions as a JSON array."
    )
    return [
        {"role": "system", "content": EXAM_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]
