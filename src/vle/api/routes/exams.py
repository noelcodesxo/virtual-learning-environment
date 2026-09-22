"""Thin HTTP adapters for the exam-builder domain service."""

import logging
import time

from fastapi import APIRouter, BackgroundTasks, HTTPException, status

from vle.api.runtime import (
    BLOOM_LEVELS,
    EXAM_BUILDER_ENABLED,
    EXAM_MODEL,
    EXAM_TOPIC_MAP_MODEL,
    EXAM_TOPIC_MAP_PROVIDER,
    TOPIC_MAP_MAX_ATTEMPTS,
    state,
)
from vle.api.schemas.exams import (
    Book, BooksResponse, ExamDetailResponse, ExamJobListResponse, ExamJobResponse,
    ExamListResponse, ExamQuestion, ExamSummary, GenerateExamRequest,
    GenerateExamResponse, GradeExamRequest, GradeExamResponse,
    ResolveExamDescriptionRequest, ResolveExamDescriptionResponse,
)
from vle.exams.service import ExamService, ExamServiceError
from vle.exams.topic_map_workflow import TOPIC_MAP_JSON_SCHEMA
from vle.llm.clients import build_client


router = APIRouter()
logger = logging.getLogger("uvicorn.error")


def _service() -> ExamService:
    """Build a domain service over the live runtime mappings.

    Module-level configuration and ``build_client`` remain forwarding seams for
    direct-handler tests. Production values originate in ``runtime.settings``.
    """
    return ExamService(
        chapter_loader=state.get("chapter_loader"),
        exam_store=state.get("exam_store"),
        exam_job_store=state.get("exam_job_store"),
        exams=state.get("exams", {}),
        jobs=state.get("exam_jobs", {}),
        enabled=EXAM_BUILDER_ENABLED,
        exam_model=EXAM_MODEL,
        topic_map_provider=EXAM_TOPIC_MAP_PROVIDER,
        topic_map_model=EXAM_TOPIC_MAP_MODEL,
        topic_map_max_attempts=TOPIC_MAP_MAX_ATTEMPTS,
        bloom_levels=BLOOM_LEVELS,
        client_factory=build_client,
        logger=logger,
        clock=time.perf_counter,
    )


def _raise_http(error: ExamServiceError) -> None:
    raise HTTPException(status_code=error.status_code, detail=error.detail) from error


def _job_response(job: dict) -> ExamJobResponse:
    return ExamJobResponse(
        id=job["id"], status=job["status"], exam_id=job["exam_id"], error=job["error"],
        created_at=job["created_at"], updated_at=job["updated_at"],
    )


@router.get("/books", response_model=BooksResponse)
def list_books():
    try:
        return BooksResponse(books=[Book(**book) for book in _service().list_books()])
    except ExamServiceError as exc:
        _raise_http(exc)


@router.post("/exams/resolve-description", response_model=ResolveExamDescriptionResponse)
def resolve_exam_description(request: ResolveExamDescriptionRequest):
    try:
        source, chapter = _service().resolve_description(request.description)
        return ResolveExamDescriptionResponse(source=source, chapter=chapter)
    except ExamServiceError as exc:
        _raise_http(exc)


def _generate_exam(request: GenerateExamRequest) -> GenerateExamResponse:
    """Compatibility helper for synchronous exam generation callers."""
    try:
        exam = _service().generate(**request.model_dump())
    except ExamServiceError as exc:
        _raise_http(exc)
    return GenerateExamResponse(
        id=exam["id"], source=exam["source"], chapter=exam["chapter"],
        generated_from=exam["generated_from"], description=exam["description"],
        requested_question_count=exam["requested_question_count"], bloom_levels=exam["bloom_levels"],
        questions=[
            ExamQuestion(section=q["section"], question=q["question"], options=q["options"])
            for q in exam["questions"]
        ],
    )


@router.post("/exams", response_model=GenerateExamResponse)
def generate_exam(request: GenerateExamRequest):
    return _generate_exam(request)


@router.post("/exam-jobs", response_model=ExamJobResponse, status_code=status.HTTP_202_ACCEPTED)
def create_exam_job(request: GenerateExamRequest, background_tasks: BackgroundTasks):
    service = _service()
    try:
        job = service.create_job(request.model_dump(mode="json"))
    except ExamServiceError as exc:
        _raise_http(exc)
    background_tasks.add_task(service.run_job, job["id"])
    return _job_response(job)


@router.get("/exam-jobs", response_model=ExamJobListResponse)
def list_exam_jobs():
    try:
        return ExamJobListResponse(jobs=[_job_response(job) for job in _service().list_jobs()])
    except ExamServiceError as exc:
        _raise_http(exc)


@router.get("/exam-jobs/{job_id}", response_model=ExamJobResponse)
def get_exam_job(job_id: str):
    try:
        return _job_response(_service().get_job(job_id))
    except ExamServiceError as exc:
        _raise_http(exc)


@router.get("/exams", response_model=ExamListResponse)
def list_exams():
    try:
        return ExamListResponse(exams=[ExamSummary(**exam) for exam in _service().list_exams()])
    except ExamServiceError as exc:
        _raise_http(exc)


@router.get("/exams/{exam_id}", response_model=ExamDetailResponse)
def get_exam(exam_id: str):
    try:
        return ExamDetailResponse(**_service().get_exam_detail(exam_id))
    except ExamServiceError as exc:
        _raise_http(exc)


@router.post("/exams/{exam_id}/grade", response_model=GradeExamResponse)
def grade_exam(exam_id: str, request: GradeExamRequest):
    try:
        return GradeExamResponse(**_service().grade_exam(exam_id, request.answers))
    except ExamServiceError as exc:
        _raise_http(exc)
