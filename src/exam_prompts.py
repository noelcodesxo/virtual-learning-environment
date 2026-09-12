EXAM_SYSTEM_PROMPT = (
    "You are an exam writer for a study assistant. You will be given the full "
    "text of one book chapter. Write multiple-choice questions that test "
    "understanding of the chapter's content - every question must be "
    "answerable using only the chapter text provided.\n\n"
    "Respond with ONLY a JSON array, no prose, no markdown fences. Each item "
    "must have exactly these fields:\n"
    '- "section": the closest section or subsection heading the question draws from\n'
    '- "question": the question text\n'
    '- "options": exactly four answer choices, as an array of strings\n'
    '- "correct_index": the 0-based index of the correct option in "options"\n'
    '- "why": one sentence explaining why that answer is correct'
)


def build_exam_messages(book: str, chapter: str, chapter_text: str, num_questions: int) -> list[dict[str, str]]:
    user_content = (
        f"Book: {book}\n"
        f"Chapter: {chapter}\n\n"
        f"Chapter text:\n{chapter_text}\n\n"
        f"Write exactly {num_questions} multiple-choice questions as a JSON array."
    )
    return [
        {"role": "system", "content": EXAM_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]
