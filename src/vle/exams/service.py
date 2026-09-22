"""Business operations for creating, storing, and grading exams.

This module deliberately has no FastAPI or Pydantic dependencies.  HTTP routes
adapt request/response models at the edge and translate :class:`ExamServiceError`
into an HTTP response.
"""

from collections.abc import Callable, MutableMapping
from datetime import datetime, timezone
import logging
import time
import urllib.error
import uuid

from vle.exams.bloom_prompts import build_exam_messages
from vle.exams.durable_job_store import ExamJobStoreError
from vle.exams.parser import parse_exam_json
from vle.exams.selection import build_exam_selection_messages, parse_exam_selection_json
from vle.exams.store import ExamStoreError
from vle.exams.topic_map_workflow import (
    TOPIC_MAP_JSON_SCHEMA,
    build_topic_map_messages,
    parse_topic_map_json,
)
from vle.llm.clients import build_client


BLOOM_LEVELS = ("remember", "understand", "apply", "analyze", "evaluate", "create")


class ExamServiceError(Exception):
    """A client-visible domain failure that an API adapter can translate."""

    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class ExamService:
    """Coordinates LLM calls, durable stores, and the live exam/job mappings."""

    def __init__(
        self,
        *,
        chapter_loader,
        exam_store,
        exam_job_store,
        exams: MutableMapping[str, dict],
        jobs: MutableMapping[str, dict],
        enabled: bool,
        exam_model: str,
        topic_map_provider: str,
        topic_map_model: str,
        topic_map_max_attempts: int,
        bloom_levels: tuple[str, ...] = BLOOM_LEVELS,
        client_factory: Callable = build_client,
        logger: logging.Logger | None = None,
        clock: Callable[[], float] = time.perf_counter,
        id_factory: Callable[[], str] = lambda: str(uuid.uuid4()),
        now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ):
        self.chapter_loader = chapter_loader
        self.exam_store = exam_store
        self.exam_job_store = exam_job_store
        self.exams = exams
        self.jobs = jobs
        self.enabled = enabled
        self.exam_model = exam_model
        self.topic_map_provider = topic_map_provider
        self.topic_map_model = topic_map_model
        self.topic_map_max_attempts = topic_map_max_attempts
        self.bloom_levels = tuple(bloom_levels)
        self.client_factory = client_factory
        self.logger = logger or logging.getLogger("uvicorn.error")
        self.clock = clock
        self.id_factory = id_factory
        self.now = now

    def _require_enabled(self) -> None:
        if not self.enabled:
            raise ExamServiceError(404, "Exam builder is not enabled")

    def _save_exam(self, exam: dict) -> None:
        try:
            self.exam_store.save(exam)
        except ExamStoreError as exc:
            raise ExamServiceError(500, "Could not save exam") from exc

    def _save_job(self, job: dict) -> None:
        try:
            self.exam_job_store.save(job)
        except ExamJobStoreError as exc:
            raise ExamServiceError(500, "Could not save exam generation job") from exc

    def _update_job(self, job_id: str, **changes: str | None) -> dict | None:
        job = self.jobs.get(job_id)
        if job is None:
            return None
        updated = {**job, **changes, "updated_at": self.now().isoformat()}
        self._save_job(updated)
        self.jobs[job_id] = updated
        return updated

    def _stored_bloom_levels(self, exam: dict) -> list[str]:
        levels = exam.get("bloom_levels")
        if isinstance(levels, list) and levels and all(level in self.bloom_levels for level in levels):
            return levels
        return list(self.bloom_levels)

    @staticmethod
    def _review(exam: dict) -> list[dict]:
        answers = exam["answers"] or {}
        return [
            {
                "section": question["section"],
                "question": question["question"],
                "options": question["options"],
                "correct_index": question["correct_index"],
                "why": question["why"],
                "given_index": answers.get(index),
            }
            for index, question in enumerate(exam["questions"])
        ]

    def list_books(self) -> list[dict]:
        self._require_enabled()
        return self.chapter_loader.list_books()

    def resolve_description(self, description: str) -> tuple[str, str]:
        self._require_enabled()
        description = description.strip()
        if not description:
            raise ExamServiceError(400, "description must not be empty")
        books = self.chapter_loader.list_books()
        try:
            raw = self.client_factory("openrouter", self.exam_model).chat(
                build_exam_selection_messages(description, books)
            )
        except KeyError as exc:
            raise ExamServiceError(500, f"Missing required environment variable: {exc}") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise ExamServiceError(502, f"Could not resolve exam source: {exc}") from exc
        try:
            return parse_exam_selection_json(raw, books)
        except ValueError as exc:
            raise ExamServiceError(422, f"Could not resolve a source and chapter: {exc}") from exc

    def _generate_topic_map(self, messages: list[dict[str, str]], chapter_text: str) -> dict:
        response_format = TOPIC_MAP_JSON_SCHEMA if self.topic_map_provider == "ollama" else None
        try:
            client = self.client_factory(self.topic_map_provider, self.topic_map_model)
        except KeyError as exc:
            raise ExamServiceError(500, f"Missing required environment variable: {exc}") from exc
        except ValueError as exc:
            raise ExamServiceError(500, f"Invalid topic-map configuration: {exc}") from exc

        for attempt in range(1, self.topic_map_max_attempts + 1):
            self.logger.info(
                "Starting exam topic-map generation attempt %d/%d (provider=%s, model=%s).",
                attempt, self.topic_map_max_attempts, self.topic_map_provider, self.topic_map_model,
            )
            started_at = self.clock()
            failure_detail = None
            try:
                raw = client.chat(messages, response_format=response_format)
                return parse_topic_map_json(raw, chapter_text)
            except urllib.error.HTTPError as exc:
                if self.topic_map_provider == "openrouter" and exc.code == 404:
                    self.logger.error(
                        "Exam topic-map generation attempt %d/%d failed: Configured topic-map model %r is not available on OpenRouter (HTTP 404).",
                        attempt, self.topic_map_max_attempts, self.topic_map_model,
                    )
                    raise ExamServiceError(
                        503, "Topic-map model is unavailable. Check server logs for the configured model."
                    ) from exc
                failure_detail = f"Topic map request failed: {exc}"
            except (urllib.error.URLError, TimeoutError) as exc:
                failure_detail = f"Topic map request failed: {exc}"
            except ValueError as exc:
                failure_detail = f"Could not parse topic map from model output: {exc}"
            finally:
                self.logger.info(
                    "Exam topic-map generation attempt %d/%d took %.2f seconds (provider=%s, model=%s).",
                    attempt, self.topic_map_max_attempts, self.clock() - started_at,
                    self.topic_map_provider, self.topic_map_model,
                )
            if attempt < self.topic_map_max_attempts:
                self.logger.warning(
                    "Exam topic-map generation attempt %d/%d failed; retrying: %s",
                    attempt, self.topic_map_max_attempts, failure_detail,
                )
                continue
            self.logger.error(
                "Exam topic-map generation failed after %d attempts: %s",
                self.topic_map_max_attempts, failure_detail,
            )
            raise ExamServiceError(502, failure_detail or "Topic map generation failed")
        raise AssertionError("Topic-map retry loop exited unexpectedly")

    def generate(
        self, *, source: str, chapter: str, num_questions: int, generated_from: str = "form",
        description: str | None = None, bloom_levels: list[str] | None = None,
    ) -> dict:
        self._require_enabled()
        description = description.strip() if description else None
        if generated_from == "description" and not description:
            raise ExamServiceError(400, "description must not be empty when generated_from is 'description'")
        try:
            chapter_text = self.chapter_loader.load_exam_text(source, chapter, num_questions)
        except ValueError as exc:
            raise ExamServiceError(404, str(exc)) from exc
        selected_levels = list(dict.fromkeys(bloom_levels or self.bloom_levels))
        topic_map = self._generate_topic_map(build_topic_map_messages(source, chapter, chapter_text), chapter_text)
        messages = build_exam_messages(
            source, chapter, chapter_text, num_questions, topic_map, selected_levels,
            description=description if generated_from == "description" else None,
        )
        self.logger.info("Starting exam question generation (provider=openrouter, model=%s).", self.exam_model)
        started_at = self.clock()
        try:
            raw = self.client_factory("openrouter", self.exam_model).chat(messages)
        except KeyError as exc:
            raise ExamServiceError(500, f"Missing required environment variable: {exc}") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise ExamServiceError(502, f"LLM request failed: {exc}") from exc
        finally:
            self.logger.info(
                "Exam question generation attempt took %.2f seconds (provider=openrouter, model=%s).",
                self.clock() - started_at, self.exam_model,
            )
        try:
            questions = parse_exam_json(raw)
        except ValueError as exc:
            raise ExamServiceError(502, f"Could not parse exam from model output: {exc}") from exc
        exam_id = self.id_factory()
        exam = {
            "id": exam_id, "source": source, "chapter": chapter, "questions": questions,
            "created_at": self.now().isoformat(), "answers": None, "score": None,
            "generated_from": generated_from,
            "description": description if generated_from == "description" else None,
            "requested_question_count": num_questions, "bloom_levels": selected_levels,
            "topic_map": topic_map,
        }
        self._save_exam(exam)
        self.exams[exam_id] = exam
        return exam

    def create_job(self, request: dict) -> dict:
        self._require_enabled()
        now = self.now().isoformat()
        job = {
            "id": self.id_factory(), "status": "queued", "request": request,
            "exam_id": None, "error": None, "created_at": now, "updated_at": now,
        }
        self._save_job(job)
        self.jobs[job["id"]] = job
        return job

    def run_job(self, job_id: str) -> None:
        try:
            job = self._update_job(job_id, status="running", error=None)
            if job is None:
                return
            exam = self.generate(**job["request"])
        except ExamServiceError as exc:
            self.logger.info("Exam generation job %s failed: %s", job_id, exc.detail)
            try:
                self._update_job(job_id, status="failed", error=exc.detail, exam_id=None)
            except ExamServiceError:
                self.logger.exception("Could not record failure for exam generation job %s", job_id)
        except Exception:
            self.logger.exception("Exam generation job %s failed unexpectedly", job_id)
            try:
                self._update_job(
                    job_id, status="failed",
                    error="Exam generation failed unexpectedly. Check server logs for details.", exam_id=None,
                )
            except ExamServiceError:
                self.logger.exception("Could not record failure for exam generation job %s", job_id)
        else:
            try:
                self._update_job(job_id, status="completed", error=None, exam_id=exam["id"])
            except ExamServiceError:
                self.logger.exception("Could not record completion for exam generation job %s", job_id)

    def list_jobs(self) -> list[dict]:
        self._require_enabled()
        return sorted(self.jobs.values(), key=lambda job: job["created_at"], reverse=True)

    def get_job(self, job_id: str) -> dict:
        self._require_enabled()
        job = self.jobs.get(job_id)
        if job is None:
            raise ExamServiceError(404, "Exam generation job not found")
        return job

    def list_exams(self) -> list[dict]:
        self._require_enabled()
        return [self._exam_summary(exam) for exam in sorted(
            self.exams.values(), key=lambda exam: exam["created_at"], reverse=True
        )]

    def _exam_summary(self, exam: dict) -> dict:
        return {
            "id": exam["id"], "source": exam["source"], "chapter": exam["chapter"],
            "created_at": exam["created_at"], "total": len(exam["questions"]), "score": exam["score"],
            "generated_from": exam.get("generated_from", "form"), "description": exam.get("description"),
            "requested_question_count": exam.get("requested_question_count", len(exam["questions"])),
            "bloom_levels": self._stored_bloom_levels(exam),
        }

    def get_exam_detail(self, exam_id: str) -> dict:
        self._require_enabled()
        exam = self.exams.get(exam_id)
        if exam is None:
            raise ExamServiceError(404, "Exam not found")
        detail = self._exam_summary(exam)
        detail.pop("created_at")
        if exam["score"] is not None:
            return {**detail, "graded": True, "review": self._review(exam)}
        return {
            **detail, "graded": False,
            "questions": [
                {"section": q["section"], "question": q["question"], "options": q["options"]}
                for q in exam["questions"]
            ],
        }

    def grade_exam(self, exam_id: str, answers: dict[str, int]) -> dict:
        self._require_enabled()
        exam = self.exams.get(exam_id)
        if exam is None:
            raise ExamServiceError(404, "Exam not found")
        saved_answers = {int(index): choice for index, choice in answers.items()}
        score = sum(
            1 for index, question in enumerate(exam["questions"])
            if saved_answers.get(index) == question["correct_index"]
        )
        updated = {**exam, "answers": saved_answers, "score": score}
        self._save_exam(updated)
        self.exams[exam_id] = updated
        detail = self._exam_summary(updated)
        detail.pop("created_at")
        return {**detail, "score": score, "total": len(updated["questions"]), "review": self._review(updated)}
