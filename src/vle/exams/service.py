"""Exam workflows, separate from HTTP concerns and BM25 chat retrieval."""

from datetime import datetime, timezone
import uuid
import urllib.error

from vle.exams.job_store import ExamJobStore
from vle.exams.parser import parse_exam_json
from vle.exams.prompts import build_exam_messages
from vle.exams.store import ExamStore, ExamStoreError
from vle.exams.topic_map import ExamWorkflowError, resolve_topic


class ExamService:
    def __init__(self, library, store: ExamStore, jobs: ExamJobStore, client_factory, model: str):
        self.library = library
        self.store = store
        self.jobs = jobs
        self.client_factory = client_factory
        self.model = model

    def list_books(self) -> list[dict]:
        return self.library.list_books()

    def resolve_description(self, description: str) -> tuple[str, str]:
        if not description.strip():
            raise ExamWorkflowError(400, "description must not be empty")
        return resolve_topic(description.strip(), self.list_books(), self.client_factory("openrouter", self.model))

    def generate(self, source: str, chapter: str, num_questions: int, generated_from: str, description: str | None) -> dict:
        description = description.strip() if description else None
        if generated_from == "description" and not description:
            raise ExamWorkflowError(400, "description must not be empty when generated_from is 'description'")
        try:
            chapter_text = self.library.load_exam_text(source, chapter, num_questions)
        except ValueError as exc:
            raise ExamWorkflowError(404, str(exc)) from exc
        try:
            raw = self.client_factory("openrouter", self.model).chat(
                build_exam_messages(source, chapter, chapter_text, num_questions,
                                    description=description if generated_from == "description" else None)
            )
        except KeyError as exc:
            raise ExamWorkflowError(500, f"Missing required environment variable: {exc}") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise ExamWorkflowError(502, f"LLM request failed: {exc}") from exc
        try:
            questions = parse_exam_json(raw)
        except ValueError as exc:
            raise ExamWorkflowError(502, f"Could not parse exam from model output: {exc}") from exc
        exam = {
            "id": str(uuid.uuid4()), "source": source, "chapter": chapter, "questions": questions,
            "created_at": datetime.now(timezone.utc).isoformat(), "answers": None, "score": None,
            "generated_from": generated_from,
            "description": description if generated_from == "description" else None,
            "requested_question_count": num_questions,
        }
        self._persist(exam)
        return exam

    def list(self) -> list[dict]:
        return sorted(self.jobs.values(), key=lambda exam: exam["created_at"], reverse=True)

    def get(self, exam_id: str) -> dict:
        exam = self.jobs.get(exam_id)
        if exam is None:
            raise ExamWorkflowError(404, "Exam not found")
        return exam

    def grade(self, exam_id: str, answers: dict[str, int]) -> dict:
        exam = self.get(exam_id)
        normalized = {int(index): choice for index, choice in answers.items()}
        score = sum(1 for i, question in enumerate(exam["questions"]) if normalized.get(i) == question["correct_index"])
        updated = {**exam, "answers": normalized, "score": score}
        self._persist(updated)
        return updated

    def _persist(self, exam: dict) -> None:
        try:
            self.store.save(exam)
        except ExamStoreError as exc:
            raise ExamWorkflowError(500, "Could not save exam") from exc
        self.jobs.save(exam)
