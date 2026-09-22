import json

import pytest

from vle.exams.job_store import ExamJobStore
from vle.exams.service import ExamService
from vle.exams.store import ExamStore, ExamStoreError
from vle.exams.topic_map import ExamWorkflowError


class _Library:
    def load_exam_text(self, source, chapter, count):
        if source == "Missing":
            raise ValueError("Book 'Missing' not found")
        return "source text"

    def list_books(self):
        return [{"title": "Book", "chapters": ["Chapter"]}]


class _Client:
    def __init__(self, response):
        self.response = response

    def chat(self, messages):
        return self.response


def _question():
    return {"section": "Section", "question": "Question?", "options": ["A", "B", "C", "D"], "correct_index": 1, "why": "B is correct."}


def _service(tmp_path, response=None):
    store = ExamStore(tmp_path / "exams")
    return ExamService(_Library(), store, ExamJobStore(), lambda *_: _Client(response or json.dumps([_question()])), "model")


def test_generation_persists_hidden_answers_and_grade_updates_only_after_save(tmp_path):
    service = _service(tmp_path)
    exam = service.generate("Book", "Chapter", 1, "form", None)

    assert exam["questions"][0]["correct_index"] == 1
    assert exam["score"] is None
    graded = service.grade(exam["id"], {"0": 1})
    assert graded["score"] == 1
    assert ExamStore(tmp_path / "exams").load()[exam["id"]]["answers"] == {0: 1}


def test_generation_preserves_existing_error_statuses(tmp_path):
    service = _service(tmp_path)
    with pytest.raises(ExamWorkflowError, match="not found") as missing:
        service.generate("Missing", "Chapter", 1, "form", None)
    assert missing.value.status_code == 404

    with pytest.raises(ExamWorkflowError, match="description must not be empty") as description:
        service.generate("Book", "Chapter", 1, "description", "   ")
    assert description.value.status_code == 400


def test_failed_exam_save_does_not_add_a_job(monkeypatch, tmp_path):
    service = _service(tmp_path)
    monkeypatch.setattr(service.store, "save", lambda exam: (_ for _ in ()).throw(ExamStoreError("disk full")))

    with pytest.raises(ExamWorkflowError) as error:
        service.generate("Book", "Chapter", 1, "form", None)
    assert error.value.status_code == 500
    assert service.jobs.exams == {}
