import io
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
    def __init__(self, chapter_text="chapter text"):
        self.chapter_text = chapter_text

    def list_books(self):
        return [{"title": "Book", "chapters": ["Chapter"]}]

    def load_exam_text(self, source, chapter, count):
        assert (source, chapter, count) == ("Book", "Chapter", 1)
        return self.chapter_text


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


def _service(
    *, client_factory, exam_store=None, job_store=None, exams=None, jobs=None, chapter_loader=None
):
    return ExamService(
        chapter_loader=chapter_loader or _Loader(),
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


def test_generate_passes_the_entire_source_to_both_model_calls_in_order():
    excerpts = [f"Source excerpt {index}:\nunique-source-part-{index:02d}" for index in range(1, 16)]
    full_source = "\n\n".join(excerpts)
    calls = []

    class _CapturingClient:
        def __init__(self, response):
            self.response = response

        def chat(self, messages, response_format=None):
            calls.append(messages[-1]["content"])
            return self.response

    topic_map = {
        "topics": [{
            "topic": "Source concept", "summary": "Summary from the full source",
            "source_excerpt": "unique-source-part-01",
        }]
    }
    responses = iter([json.dumps(topic_map), json.dumps([QUESTION])])
    service = _service(
        client_factory=lambda *_: _CapturingClient(next(responses)),
        chapter_loader=_Loader(full_source),
    )

    service.generate(source="Book", chapter="Chapter", num_questions=1)

    assert len(calls) == 2
    for call in calls:
        positions = [call.index(f"unique-source-part-{index:02d}") for index in range(1, 16)]
        assert positions == sorted(positions)


@pytest.mark.parametrize("failing_call", [1, 2])
def test_context_limit_fails_the_job_without_saving_an_exam(failing_call):
    calls = 0
    exam_store = _Store()
    job_store = _Store()
    exams = {}
    jobs = {}

    class _Client:
        def chat(self, messages, response_format=None):
            nonlocal calls
            calls += 1
            if calls == failing_call:
                raise urllib.error.HTTPError(
                    "https://example.test/chat", 400, "Bad Request", {},
                    io.BytesIO(b'{"error":{"message":"maximum context length exceeded"}}'),
                )
            return json.dumps(TOPIC_MAP if calls == 1 else [QUESTION])

    service = _service(
        client_factory=lambda *_: _Client(), exam_store=exam_store, job_store=job_store,
        exams=exams, jobs=jobs,
    )
    job = service.create_job({"source": "Book", "chapter": "Chapter", "num_questions": 1})

    service.run_job(job["id"])

    failed_job = jobs[job["id"]]
    assert failed_job["status"] == "failed"
    assert failed_job["exam_id"] is None
    assert "exceeds the configured model's context window" in failed_job["error"]
    assert exam_store.saved == []
    assert exams == {}


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
