import json
import urllib.error

import pytest

from vle.exams.service import ExamService, ExamServiceError


TOPIC_MAP = {
    "topics": [{"topic": "Core concept", "summary": "Summary", "source_excerpt": "chapter text"}]
}
QUESTION = {
    "section": "Core", "question": "What is the concept?", "options": ["A", "B", "C"],
    "correct_index": 0, "why": "A is correct.",
}


class _Loader:
    def list_books(self):
        return [{"title": "Book", "chapters": ["Chapter"]}]

    def load_exam_text(self, source, chapter, count):
        assert (source, chapter, count) == ("Book", "Chapter", 1)
        return "chapter text"


class _Store:
    def __init__(self):
        self.saved = []

    def save(self, value):
        self.saved.append(value)


class _Client:
    def __init__(self, response):
        self.response = response

    def chat(self, messages, response_format=None):
        return self.response


def _service(*, client_factory, exam_store=None, job_store=None, exams=None, jobs=None):
    return ExamService(
        chapter_loader=_Loader(),
        exam_store=exam_store or _Store(),
        exam_job_store=job_store or _Store(),
        exams=exams if exams is not None else {},
        jobs=jobs if jobs is not None else {},
        enabled=True,
        exam_model="exam-model",
        topic_map_provider="ollama",
        topic_map_model="topic-model",
        topic_map_max_attempts=3,
        client_factory=client_factory,
    )


def test_generate_persists_the_complete_exam_and_returns_domain_data():
    responses = iter([json.dumps(TOPIC_MAP), json.dumps([QUESTION])])
    store = _Store()
    exams = {}
    service = _service(client_factory=lambda *_: _Client(next(responses)), exam_store=store, exams=exams)

    exam = service.generate(source="Book", chapter="Chapter", num_questions=1)

    assert exam["id"] in exams
    assert store.saved == [exam]
    assert exam["questions"] == [QUESTION]
    assert exam["topic_map"] == TOPIC_MAP


def test_job_failure_is_persisted_with_the_domain_error_detail():
    jobs = {}
    job_store = _Store()

    class _FailingClient:
        def chat(self, messages, response_format=None):
            raise urllib.error.URLError("connection reset")

    service = _service(client_factory=lambda *_: _FailingClient(), job_store=job_store, jobs=jobs)
    job = service.create_job({"source": "Book", "chapter": "Chapter", "num_questions": 1})

    service.run_job(job["id"])

    assert jobs[job["id"]]["status"] == "failed"
    assert jobs[job["id"]]["error"] == "Topic map request failed: <urlopen error connection reset>"


def test_disabled_service_returns_the_shared_domain_error():
    service = _service(client_factory=lambda *_: _Client(""))
    service.enabled = False

    with pytest.raises(ExamServiceError, match="Exam builder is not enabled") as error:
        service.list_exams()

    assert error.value.status_code == 404
