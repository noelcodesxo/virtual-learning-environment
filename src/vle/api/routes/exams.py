"""Exam-builder HTTP endpoints; workflows live in ``vle.exams``."""

from fastapi import APIRouter, Depends, HTTPException

from vle.api.dependencies import exam_service, require_exam_builder
from vle.api.schemas.exams import (
    ExamDetailResponse,
    ExamListResponse,
    ExamQuestion,
    ExamSummary,
    GenerateExamRequest,
    GenerateExamResponse,
    GradeExamRequest,
    GradeExamResponse,
    ResolveExamDescriptionRequest,
    ResolveExamDescriptionResponse,
    ReviewQuestion,
)
from vle.exams.topic_map import ExamWorkflowError


router = APIRouter(dependencies=[Depends(require_exam_builder)])


def _workflow_error(error: ExamWorkflowError) -> HTTPException:
    return HTTPException(status_code=error.status_code, detail=error.detail)


def _review(exam: dict) -> list[ReviewQuestion]:
    answers = exam["answers"] or {}
    return [
        ReviewQuestion(
            section=question["section"], question=question["question"], options=question["options"],
            correct_index=question["correct_index"], why=question["why"], given_index=answers.get(index),
        )
        for index, question in enumerate(exam["questions"])
    ]


@router.post("/exams/resolve-description", response_model=ResolveExamDescriptionResponse)
def resolve_exam_description(request: ResolveExamDescriptionRequest, service=Depends(exam_service)):
    try:
        source, chapter = service.resolve_description(request.description)
    except ExamWorkflowError as exc:
        raise _workflow_error(exc) from exc
    return ResolveExamDescriptionResponse(source=source, chapter=chapter)


@router.post("/exams", response_model=GenerateExamResponse)
def generate_exam(request: GenerateExamRequest, service=Depends(exam_service)):
    try:
        exam = service.generate(
            request.source, request.chapter, request.num_questions, request.generated_from, request.description
        )
    except ExamWorkflowError as exc:
        raise _workflow_error(exc) from exc
    return GenerateExamResponse(
        id=exam["id"], source=exam["source"], chapter=exam["chapter"],
        generated_from=exam["generated_from"], description=exam["description"],
        requested_question_count=exam["requested_question_count"],
        questions=[ExamQuestion(section=q["section"], question=q["question"], options=q["options"]) for q in exam["questions"]],
    )


@router.get("/exams", response_model=ExamListResponse)
def list_exams(service=Depends(exam_service)):
    return ExamListResponse(
        exams=[
            ExamSummary(
                id=exam["id"], source=exam["source"], chapter=exam["chapter"], created_at=exam["created_at"],
                total=len(exam["questions"]), score=exam["score"],
                generated_from=exam.get("generated_from", "form"), description=exam.get("description"),
                requested_question_count=exam.get("requested_question_count", len(exam["questions"])),
            )
            for exam in service.list()
        ]
    )


@router.get("/exams/{exam_id}", response_model=ExamDetailResponse)
def get_exam(exam_id: str, service=Depends(exam_service)):
    try:
        exam = service.get(exam_id)
    except ExamWorkflowError as exc:
        raise _workflow_error(exc) from exc
    common = {
        "id": exam["id"], "source": exam["source"], "chapter": exam["chapter"],
        "generated_from": exam.get("generated_from", "form"), "description": exam.get("description"),
        "requested_question_count": exam.get("requested_question_count", len(exam["questions"])),
    }
    if exam["score"] is not None:
        return ExamDetailResponse(
            **common, graded=True, score=exam["score"], total=len(exam["questions"]), review=_review(exam)
        )
    return ExamDetailResponse(
        **common,
        graded=False,
        questions=[ExamQuestion(section=q["section"], question=q["question"], options=q["options"]) for q in exam["questions"]],
    )


@router.post("/exams/{exam_id}/grade", response_model=GradeExamResponse)
def grade_exam(exam_id: str, request: GradeExamRequest, service=Depends(exam_service)):
    try:
        exam = service.grade(exam_id, request.answers)
    except ExamWorkflowError as exc:
        raise _workflow_error(exc) from exc
    return GradeExamResponse(
        id=exam["id"], source=exam["source"], chapter=exam["chapter"],
        score=exam["score"], total=len(exam["questions"]), review=_review(exam),
    )
