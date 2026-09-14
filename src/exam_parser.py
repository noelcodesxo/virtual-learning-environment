import json
import re

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)

REQUIRED_FIELDS = {"section", "question", "options", "correct_index", "why"}


def parse_exam_json(raw: str) -> list[dict]:
    """Parse an LLM's exam response into a list of question dicts, tolerating
    a markdown code fence around the JSON. Raises ValueError on anything that
    doesn't match the schema we asked the model for."""
    text = raw.strip()
    fence_match = _FENCE_RE.search(text)
    if fence_match:
        text = fence_match.group(1).strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Model did not return valid JSON: {exc}") from exc

    if not isinstance(data, list) or not data:
        raise ValueError("Expected a non-empty JSON array of questions")

    for question in data:
        missing = REQUIRED_FIELDS - question.keys()
        if missing:
            raise ValueError(f"Question missing fields: {sorted(missing)}")
        if not isinstance(question["options"], list) or len(question["options"]) != 4:
            raise ValueError("Each question must have exactly 4 options")
        if not isinstance(question["correct_index"], int) or not (0 <= question["correct_index"] < 4):
            raise ValueError("correct_index must be an integer between 0 and 3")

    return data
