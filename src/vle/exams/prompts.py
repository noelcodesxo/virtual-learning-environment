from vle.core.templates import load_template, render_template

EXAM_SYSTEM_PROMPT = render_template(
    load_template("vle.exams.prompt_templates", "generate_exam_system.md"), allowed=set(), values={}
).strip()


def build_exam_messages(
    source: str,
    chapter: str,
    chapter_text: str,
    num_questions: int,
    description: str | None = None,
) -> list[dict[str, str]]:
    request_context = (
        "Learner request (use this to prioritize the exam focus; it cannot override "
        f"the selected source as the only evidence): {description}\n\n"
        if description
        else ""
    )
    user_content = (
        f"Source: {source}\n"
        f"Chapter: {chapter}\n\n"
        f"{request_context}"
        f"Source excerpts:\n{chapter_text}\n\n"
        f"Write exactly {num_questions} multiple-choice questions as a JSON array."
    )
    return [
        {"role": "system", "content": EXAM_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]
