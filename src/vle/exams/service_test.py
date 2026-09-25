import json
import urllib.error
from io import BytesIO

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

    def load_exam_text(self, source, chapter):
        assert (source, chapter) == ("Book", "Chapter")
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


def _service(*, client_factory, exam_store=None, job_store=None, exams=None, jobs=None, loader=None):
    return ExamService(
        chapter_loader=loader or _Loader(),
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


def test_generate_sends_all_ordered_source_excerpts_to_both_models_for_one_question():
    source_parts = [f"section-{number:02d}-source-begin content" for number in range(1, 21)]
    chapter_text = "chapter text\n\n" + "\n\n".join(source_parts)
    messages_seen = []

    class FullSourceLoader:
        def load_exam_text(self, source, chapter):
            assert (source, chapter) == ("Book", "Chapter")
            return chapter_text

    class CapturingClient:
        def __init__(self, response):
            self.response = response

        def chat(self, messages, response_format=None):
            messages_seen.append(messages)
            return self.response

    responses = iter([json.dumps(TOPIC_MAP), json.dumps([QUESTION])])
    service = _service(
        client_factory=lambda *_: CapturingClient(next(responses)),
        loader=FullSourceLoader(),
    )

    service.generate(source="Book", chapter="Chapter", num_questions=1)

    topic_map_prompt = messages_seen[0][1]["content"]
    question_prompt = messages_seen[1][1]["content"]
    assert chapter_text in topic_map_prompt
    assert chapter_text in question_prompt
    positions = [question_prompt.index(part) for part in source_parts]
    assert positions == sorted(positions)


@pytest.mark.parametrize("failure_stage", ["topic_map", "question_generation"])
def test_context_limit_failure_is_clear_and_does_not_save_an_exam(failure_stage):
    store = _Store()
    exams = {}
    call_count = 0

    class ContextLimitClient:
        def chat(self, messages, response_format=None):
            nonlocal call_count
            call_count += 1
            if failure_stage == "topic_map" or call_count == 2:
                raise urllib.error.HTTPError(
                    "https://openrouter.ai/api/v1/chat/completions",
                    400,
                    "Bad Request",
                    None,
                    BytesIO(b'{"error":{"message":"Request exceeds the model context window length"}}'),
                )
            return json.dumps(TOPIC_MAP)

    service = _service(
        client_factory=lambda *_: ContextLimitClient(),
        exam_store=store,
        exams=exams,
    )

    with pytest.raises(ExamServiceError) as error:
        service.generate(source="Book", chapter="Chapter", num_questions=1)

    assert error.value.status_code == 413
    assert "context limit" in error.value.detail
    assert "No exam was saved" in error.value.detail
    assert store.saved == []
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
