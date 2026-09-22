import json
import re


TOPIC_MAP_JSON_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["topics"],
    "properties": {
        "topics": {
            "type": "array",
            "minItems": 1,
            "maxItems": 12,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["topic", "summary", "source_excerpt"],
                "properties": {
                    "topic": {"type": "string"},
                    "summary": {"type": "string"},
                    "source_excerpt": {"type": "string"},
                },
            },
        }
    },
}

TOPIC_MAP_JSON_EXAMPLE = json.dumps(
    {
        "topics": [
            {
                "topic": "descriptive topic name",
                "summary": "short summary grounded in the supplied excerpts",
                "source_excerpt": "exact short quotation copied from the supplied excerpts",
            }
        ]
    },
    ensure_ascii=False,
)

TOPIC_MAP_SYSTEM_PROMPT = (
    "You create a compact content map for an exam writer. Read only the supplied "
    "source excerpts. Identify the most important, distinct topics that are useful "
    "for assessing the chapter. Do not use outside knowledge or infer facts that "
    "are not in the excerpts. Prefer central concepts, relationships, processes, "
    "trade-offs, and skills over trivia.\n\n"
    "Respond with ONLY one JSON object, no prose, markdown fences, analysis, or "
    "explanation. Your response must begin with `{` and end with `}`. It must "
    "match this exact JSON shape and field names:\n"
    + TOPIC_MAP_JSON_EXAMPLE
    + "\n\nReturn 1 to 12 topics. Keep each summary and quotation short. Do not "
    "include placeholder text from the example; replace every value with source-grounded content."
)

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)
_TOPIC_FIELDS = ("topic", "summary", "source_excerpt")
_TOPIC_FIELD_SET = set(_TOPIC_FIELDS)
_WORD_RE = re.compile(r"[a-z0-9]+")
_EVIDENCE_STOP_WORDS = {
    "about",
    "after",
    "and",
    "are",
    "from",
    "into",
    "that",
    "the",
    "their",
    "this",
    "with",
}


def build_topic_map_messages(source: str, chapter: str, chapter_text: str) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": TOPIC_MAP_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": f"Source: {source}\nChapter: {chapter}\n\nSource excerpts:\n{chapter_text}",
        },
    ]


def parse_topic_map_json(raw: str, chapter_text: str) -> dict[str, list[dict[str, str]]]:
    """Parse and validate a compact, source-grounded topic map from an LLM."""
    text = raw.strip()
    if not text:
        raise ValueError("Model returned an empty response instead of the required JSON object")
    fence_match = _FENCE_RE.search(text)
    if fence_match:
        text = fence_match.group(1).strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Model did not return valid JSON: {exc}") from exc

    if not isinstance(data, dict) or set(data) != {"topics"}:
        raise ValueError("Expected a JSON object containing only a topics array")
    topics = data["topics"]
    if not isinstance(topics, list) or not 1 <= len(topics) <= 12:
        raise ValueError("Expected between 1 and 12 topics")

    normalized_source = " ".join(chapter_text.split())
    normalized_topics = []
    for item in topics:
        if not isinstance(item, dict) or set(item) != _TOPIC_FIELD_SET:
            raise ValueError(f"Each topic must have exactly these fields: {sorted(_TOPIC_FIELDS)}")
        if not all(isinstance(item[field], str) and item[field].strip() for field in _TOPIC_FIELDS):
            raise ValueError("Topic fields must be non-empty strings")

        normalized_item = {field: item[field].strip() for field in _TOPIC_FIELDS}
        normalized_excerpt = " ".join(normalized_item["source_excerpt"].split())
        if normalized_excerpt not in normalized_source:
            verified_excerpt = _find_verified_excerpt(
                normalized_item["topic"], normalized_item["summary"], normalized_source
            )
            if verified_excerpt is None:
                raise ValueError("Each topic must be grounded in the supplied source excerpts")
            normalized_item["source_excerpt"] = verified_excerpt
        normalized_topics.append(normalized_item)

    return {"topics": normalized_topics}


def _find_verified_excerpt(topic: str, summary: str, source: str) -> str | None:
    """Return a verbatim evidence sentence for a topic whose model quote was paraphrased."""
    target_words = _meaningful_words(f"{topic} {summary}")
    if not target_words:
        return None

    candidates = [sentence.strip() for sentence in re.split(r"(?<=[.!?])\s+", source) if sentence.strip()]
    scored_candidates = [
        (len(target_words & _meaningful_words(candidate)), candidate)
        for candidate in candidates
    ]
    overlap, candidate = max(scored_candidates, default=(0, ""), key=lambda item: item[0])
    return candidate if overlap >= 2 else None


def _meaningful_words(text: str) -> set[str]:
    return {
        word
        for word in _WORD_RE.findall(text.lower())
        if len(word) >= 3 and word not in _EVIDENCE_STOP_WORDS
    }
