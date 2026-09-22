import json
import re

from vle.core.templates import load_template, render_template


_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)

EXAM_SELECTION_SYSTEM_PROMPT = render_template(
    load_template("vle.exams.prompt_templates", "topic_map_system.md"), allowed=set(), values={}
).strip()


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
        raise ValueError("Expected a JSON object with source and chapter")

    source = selection.get("source")
    chapter = selection.get("chapter")
    if not isinstance(source, str) or not isinstance(chapter, str):
        raise ValueError("Selection must include string source and chapter values")

    catalog = {item["title"]: item["chapters"] for item in books}
    if source not in catalog or chapter not in catalog[source]:
        raise ValueError("Selection does not match an available source and chapter")

    return source, chapter
