import json
import re


_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)

EXAM_SELECTION_SYSTEM_PROMPT = (
    "You select the single best source chapter for an exam request. Use only "
    "the provided book and chapter catalog. Respect an explicitly named book "
    "or chapter, including ordinal wording such as 'second chapter'. A topic "
    "in the request guides question focus later; do not switch to another "
    "book or chapter merely because its title seems closer to that topic. "
    "Return ONLY a JSON object with exactly these fields: \"book\" and "
    "\"chapter\". Each value must exactly match a value in the catalog."
)


def build_exam_selection_messages(description: str, books: list[dict]) -> list[dict[str, str]]:
    catalog = json.dumps(books, ensure_ascii=False)
    return [
        {"role": "system", "content": EXAM_SELECTION_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": f"Available catalog:\n{catalog}\n\nLearner request:\n{description}",
        },
    ]


def parse_exam_selection_json(raw: str, books: list[dict]) -> tuple[str, str]:
    text = raw.strip()
    fence_match = _FENCE_RE.search(text)
    if fence_match:
        text = fence_match.group(1).strip()

    try:
        selection = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Model did not return valid JSON: {exc}") from exc

    if not isinstance(selection, dict):
        raise ValueError("Expected a JSON object with book and chapter")

    book = selection.get("book")
    chapter = selection.get("chapter")
    if not isinstance(book, str) or not isinstance(chapter, str):
        raise ValueError("Selection must include string book and chapter values")

    catalog = {item["title"]: item["chapters"] for item in books}
    if book not in catalog or chapter not in catalog[book]:
        raise ValueError("Selection does not match an available book and chapter")

    return book, chapter
