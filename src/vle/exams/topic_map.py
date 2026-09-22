"""Resolve prose exam requests to an exact catalog source and chapter."""

import urllib.error

from vle.exams.selection import build_exam_selection_messages, parse_exam_selection_json


class ExamWorkflowError(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


def resolve_topic(description: str, books: list[dict], client) -> tuple[str, str]:
    try:
        raw = client.chat(build_exam_selection_messages(description, books))
    except KeyError as exc:
        raise ExamWorkflowError(500, f"Missing required environment variable: {exc}") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise ExamWorkflowError(502, f"Could not resolve exam source: {exc}") from exc
    try:
        return parse_exam_selection_json(raw, books)
    except ValueError as exc:
        raise ExamWorkflowError(422, f"Could not resolve a source and chapter: {exc}") from exc
