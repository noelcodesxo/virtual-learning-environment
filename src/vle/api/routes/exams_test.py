import pytest
from fastapi import HTTPException

from vle.api.routes import exams
from vle.api.schemas.exams import GenerateExamRequest, GradeExamRequest, ResolveExamDescriptionRequest
from vle.exams.topic_map import ExamWorkflowError


def _question(**overrides):
    question = {
        "section": "Evaluation", "question": "What is X?", "options": ["A", "B", "C", "D"],
        "correct_index": 1, "why": "B is correct.",
    }
    question.update(overrides)
    return question


class _ExamService:
    def __init__(self):
        self.exam = {
            "id": "exam-1", "source": "Book", "chapter": "Chapter", "questions": [_question()],
            "created_at": "2026-01-01T00:00:00+00:00", "answers": None, "score": None,
            "generated_from": "form", "description": None, "requested_question_count": 1,
        }

    def resolve_description(self, description):
        return "Book", "Chapter"

    def generate(self, source, chapter, num_questions, generated_from, description):
        return self.exam

    def list(self):
        return [self.exam]

    def get(self, exam_id):
        if exam_id != self.exam["id"]:
            raise ExamWorkflowError(404, "Exam not found")
        return self.exam

    def grade(self, exam_id, answers):
        self.get(exam_id)
        self.exam = {**self.exam, "answers": {int(key): value for key, value in answers.items()}, "score": 1}
        return self.exam


def test_exam_routes_preserve_generation_listing_and_grading_response_contracts():
    service = _ExamService()

    resolved = exams.resolve_exam_description(ResolveExamDescriptionRequest(description="topic"), service)
    generated = exams.generate_exam(GenerateExamRequest(source="Book", chapter="Chapter", num_questions=1), service)
    listed = exams.list_exams(service)
    ungraded = exams.get_exam("exam-1", service)
    graded = exams.grade_exam("exam-1", GradeExamRequest(answers={"0": 1}), service)
    detail = exams.get_exam("exam-1", service)

    assert resolved.model_dump() == {"source": "Book", "chapter": "Chapter"}
    assert generated.model_dump(exclude={"id"}) == {
        "source": "Book", "chapter": "Chapter", "generated_from": "form", "description": None,
        "requested_question_count": 1,
        "questions": [{"section": "Evaluation", "question": "What is X?", "options": ["A", "B", "C", "D"]}],
    }
    assert [exam.id for exam in listed.exams] == ["exam-1"]
    assert ungraded.graded is False and ungraded.questions[0].question == "What is X?"
    assert graded.score == 1 and graded.review[0].given_index == 1
    assert detail.graded is True and detail.review[0].correct_index == 1


def test_exam_routes_map_domain_errors_to_the_original_http_statuses():
    service = _ExamService()

    with pytest.raises(HTTPException) as error:
        exams.get_exam("missing", service)

    assert error.value.status_code == 404
    assert error.value.detail == "Exam not found"
