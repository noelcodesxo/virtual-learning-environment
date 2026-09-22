"""Exam-builder HTTP endpoints and their asynchronous generation workflow."""

import logging
import time
import urllib.error
import uuid
from datetime import datetime, timezone

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
    GenerateExamResponse, GradeExamRequest, GradeExamResponse, ResolveExamDescriptionRequest,
    ResolveExamDescriptionResponse, ReviewQuestion,
)
from vle.exams.bloom_prompts import build_exam_messages
from vle.exams.durable_job_store import ExamJobStoreError
from vle.exams.parser import parse_exam_json
from vle.exams.selection import build_exam_selection_messages, parse_exam_selection_json
from vle.exams.store import ExamStoreError
from vle.exams.topic_map_workflow import TOPIC_MAP_JSON_SCHEMA, build_topic_map_messages, parse_topic_map_json
from vle.llm.clients import build_client

router = APIRouter()
logger = logging.getLogger("uvicorn.error")


def _require_exam_builder_enabled() -> None:
    if not EXAM_BUILDER_ENABLED:
        raise HTTPException(status_code=404, detail="Exam builder is not enabled")


def _build_review(exam: dict) -> list[ReviewQuestion]:
    answers = exam["answers"] or {}
    return [
        ReviewQuestion(
            section=q["section"],
            question=q["question"],
            options=q["options"],
            correct_index=q["correct_index"],
            why=q["why"],
            given_index=answers.get(i),
        )
        for i, q in enumerate(exam["questions"])
    ]


def _save_exam(exam: dict) -> None:
    try:
        state["exam_store"].save(exam)
    except ExamStoreError as exc:
        raise HTTPException(status_code=500, detail="Could not save exam") from exc


def _save_exam_job(job: dict) -> None:
    try:
        state["exam_job_store"].save(job)
    except ExamJobStoreError as exc:
        raise HTTPException(status_code=500, detail="Could not save exam generation job") from exc


def _job_response(job: dict) -> ExamJobResponse:
    return ExamJobResponse(
        id=job["id"],
        status=job["status"],
        exam_id=job["exam_id"],
        error=job["error"],
        created_at=job["created_at"],
        updated_at=job["updated_at"],
    )


def _update_exam_job(job_id: str, **changes: str | None) -> dict | None:
    job = state["exam_jobs"].get(job_id)
    if job is None:
        return None
    updated = {**job, **changes, "updated_at": datetime.now(timezone.utc).isoformat()}
    _save_exam_job(updated)
    state["exam_jobs"][job_id] = updated
    return updated


def _stored_bloom_levels(exam: dict) -> list[str]:
    """Read Bloom metadata while keeping examinations saved before this feature valid."""
    bloom_levels = exam.get("bloom_levels")
    if isinstance(bloom_levels, list) and bloom_levels and all(level in BLOOM_LEVELS for level in bloom_levels):
        return bloom_levels
    return list(BLOOM_LEVELS)


@router.get("/books", response_model=BooksResponse)
def list_books():
    _require_exam_builder_enabled()
    return BooksResponse(books=[Book(**b) for b in state["chapter_loader"].list_books()])


@router.post("/exams/resolve-description", response_model=ResolveExamDescriptionResponse)
def resolve_exam_description(request: ResolveExamDescriptionRequest):
    _require_exam_builder_enabled()
    description = request.description.strip()
    if not description:
        raise HTTPException(status_code=400, detail="description must not be empty")

    books = state["chapter_loader"].list_books()
    messages = build_exam_selection_messages(description, books)
    try:
        raw = build_client("openrouter", EXAM_MODEL).chat(messages)
    except KeyError as exc:
        raise HTTPException(status_code=500, detail=f"Missing required environment variable: {exc}") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise HTTPException(status_code=502, detail=f"Could not resolve exam source: {exc}") from exc

    try:
        source, chapter = parse_exam_selection_json(raw, books)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Could not resolve a source and chapter: {exc}") from exc

    return ResolveExamDescriptionResponse(source=source, chapter=chapter)


def _generate_topic_map(topic_map_messages: list[dict[str, str]], chapter_text: str) -> dict:
    """Generate a source-grounded topic map, retrying transient model failures."""
    response_format = TOPIC_MAP_JSON_SCHEMA if EXAM_TOPIC_MAP_PROVIDER == "ollama" else None
    try:
        client = build_client(EXAM_TOPIC_MAP_PROVIDER, EXAM_TOPIC_MAP_MODEL)
    except KeyError as exc:
        raise HTTPException(status_code=500, detail=f"Missing required environment variable: {exc}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=f"Invalid topic-map configuration: {exc}") from exc

    for attempt in range(1, TOPIC_MAP_MAX_ATTEMPTS + 1):
        logger.info(
            "Starting exam topic-map generation attempt %d/%d (provider=%s, model=%s).",
            attempt,
            TOPIC_MAP_MAX_ATTEMPTS,
            EXAM_TOPIC_MAP_PROVIDER,
            EXAM_TOPIC_MAP_MODEL,
        )
        topic_map_started_at = time.perf_counter()
        failure_detail = None
        try:
            topic_map_raw = client.chat(topic_map_messages, response_format=response_format)
            return parse_topic_map_json(topic_map_raw, chapter_text)
        except urllib.error.HTTPError as exc:
            if EXAM_TOPIC_MAP_PROVIDER == "openrouter" and exc.code == 404:
                logger.error(
                    "Exam topic-map generation attempt %d/%d failed: Configured topic-map model %r is not available on OpenRouter (HTTP 404).",
                    attempt,
                    TOPIC_MAP_MAX_ATTEMPTS,
                    EXAM_TOPIC_MAP_MODEL,
                )
                raise HTTPException(
                    status_code=503,
                    detail="Topic-map model is unavailable. Check server logs for the configured model.",
                ) from exc
            failure_detail = f"Topic map request failed: {exc}"
        except (urllib.error.URLError, TimeoutError) as exc:
            failure_detail = f"Topic map request failed: {exc}"
        except ValueError as exc:
            failure_detail = f"Could not parse topic map from model output: {exc}"
        finally:
            logger.info(
                "Exam topic-map generation attempt %d/%d took %.2f seconds (provider=%s, model=%s).",
                attempt,
                TOPIC_MAP_MAX_ATTEMPTS,
                time.perf_counter() - topic_map_started_at,
                EXAM_TOPIC_MAP_PROVIDER,
                EXAM_TOPIC_MAP_MODEL,
            )

        if attempt < TOPIC_MAP_MAX_ATTEMPTS:
            logger.warning(
                "Exam topic-map generation attempt %d/%d failed; retrying: %s",
                attempt,
                TOPIC_MAP_MAX_ATTEMPTS,
                failure_detail,
            )
            continue

        logger.error(
            "Exam topic-map generation failed after %d attempts: %s",
            TOPIC_MAP_MAX_ATTEMPTS,
            failure_detail,
        )
        raise HTTPException(status_code=502, detail=failure_detail)

    raise AssertionError("Topic-map retry loop exited unexpectedly")


def _generate_exam(request: GenerateExamRequest) -> GenerateExamResponse:
    _require_exam_builder_enabled()

    description = request.description.strip() if request.description else None
    if request.generated_from == "description" and not description:
        raise HTTPException(status_code=400, detail="description must not be empty when generated_from is 'description'")

    try:
        chapter_text = state["chapter_loader"].load_exam_text(
            request.source,
            request.chapter,
            request.num_questions,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    bloom_levels = list(dict.fromkeys(request.bloom_levels))
    topic_map_messages = build_topic_map_messages(request.source, request.chapter, chapter_text)
    topic_map = _generate_topic_map(topic_map_messages, chapter_text)

    messages = build_exam_messages(
        request.source,
        request.chapter,
        chapter_text,
        request.num_questions,
        topic_map,
        bloom_levels,
        description=description if request.generated_from == "description" else None,
    )

    logger.info("Starting exam question generation (provider=openrouter, model=%s).", EXAM_MODEL)
    exam_started_at = time.perf_counter()
    try:
        client = build_client("openrouter", EXAM_MODEL)
        raw = client.chat(messages)
    except KeyError as exc:
        raise HTTPException(status_code=500, detail=f"Missing required environment variable: {exc}") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise HTTPException(status_code=502, detail=f"LLM request failed: {exc}") from exc
    finally:
        logger.info(
            "Exam question generation attempt took %.2f seconds (provider=openrouter, model=%s).",
            time.perf_counter() - exam_started_at,
            EXAM_MODEL,
        )

    try:
        questions = parse_exam_json(raw)
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=f"Could not parse exam from model output: {exc}") from exc

    exam_id = str(uuid.uuid4())
    exam = {
        "id": exam_id,
        "source": request.source,
        "chapter": request.chapter,
        "questions": questions,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "answers": None,
        "score": None,
        "generated_from": request.generated_from,
        "description": description if request.generated_from == "description" else None,
        "requested_question_count": request.num_questions,
        "bloom_levels": bloom_levels,
        "topic_map": topic_map,
    }
    _save_exam(exam)
    state["exams"][exam_id] = exam
    return GenerateExamResponse(
        id=exam_id,
        source=request.source,
        chapter=request.chapter,
        generated_from=request.generated_from,
        description=exam["description"],
        requested_question_count=request.num_questions,
        bloom_levels=bloom_levels,
        questions=[
            ExamQuestion(section=q["section"], question=q["question"], options=q["options"]) for q in questions
        ],
    )


def _run_exam_job(job_id: str) -> None:
    try:
        job = _update_exam_job(job_id, status="running", error=None)
        if job is None:
            return
        response = _generate_exam(GenerateExamRequest.model_validate(job["request"]))
    except HTTPException as exc:
        logger.info("Exam generation job %s failed: %s", job_id, exc.detail)
        try:
            _update_exam_job(job_id, status="failed", error=str(exc.detail), exam_id=None)
        except HTTPException:
            logger.exception("Could not record failure for exam generation job %s", job_id)
    except Exception:
        logger.exception("Exam generation job %s failed unexpectedly", job_id)
        try:
            _update_exam_job(
                job_id,
                status="failed",
                error="Exam generation failed unexpectedly. Check server logs for details.",
                exam_id=None,
            )
        except HTTPException:
            logger.exception("Could not record failure for exam generation job %s", job_id)
    else:
        try:
            _update_exam_job(job_id, status="completed", error=None, exam_id=response.id)
        except HTTPException:
            logger.exception("Could not record completion for exam generation job %s", job_id)


@router.post("/exams", response_model=GenerateExamResponse)
def generate_exam(request: GenerateExamRequest):
    """Generate synchronously for existing API consumers."""
    return _generate_exam(request)


@router.post("/exam-jobs", response_model=ExamJobResponse, status_code=status.HTTP_202_ACCEPTED)
def create_exam_job(request: GenerateExamRequest, background_tasks: BackgroundTasks):
    _require_exam_builder_enabled()
    now = datetime.now(timezone.utc).isoformat()
    job = {
        "id": str(uuid.uuid4()),
        "status": "queued",
        "request": request.model_dump(mode="json"),
        "exam_id": None,
        "error": None,
        "created_at": now,
        "updated_at": now,
    }
    _save_exam_job(job)
    state["exam_jobs"][job["id"]] = job
    background_tasks.add_task(_run_exam_job, job["id"])
    return _job_response(job)


@router.get("/exam-jobs", response_model=ExamJobListResponse)
def list_exam_jobs():
    _require_exam_builder_enabled()
    jobs = sorted(state["exam_jobs"].values(), key=lambda job: job["created_at"], reverse=True)
    return ExamJobListResponse(jobs=[_job_response(job) for job in jobs])


@router.get("/exam-jobs/{job_id}", response_model=ExamJobResponse)
def get_exam_job(job_id: str):
    _require_exam_builder_enabled()
    job = state["exam_jobs"].get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Exam generation job not found")
    return _job_response(job)


@router.get("/exams", response_model=ExamListResponse)
def list_exams():
    _require_exam_builder_enabled()
    exams = sorted(state["exams"].values(), key=lambda e: e["created_at"], reverse=True)
    return ExamListResponse(
        exams=[
            ExamSummary(
                id=e["id"],
                source=e["source"],
                chapter=e["chapter"],
                created_at=e["created_at"],
                total=len(e["questions"]),
                score=e["score"],
                generated_from=e.get("generated_from", "form"),
                description=e.get("description"),
                requested_question_count=e.get("requested_question_count", len(e["questions"])),
                bloom_levels=_stored_bloom_levels(e),
            )
            for e in exams
        ]
    )


@router.get("/exams/{exam_id}", response_model=ExamDetailResponse)
def get_exam(exam_id: str):
    _require_exam_builder_enabled()
    exam = state["exams"].get(exam_id)
    if exam is None:
        raise HTTPException(status_code=404, detail="Exam not found")

    if exam["score"] is not None:
        return ExamDetailResponse(
            id=exam["id"],
            source=exam["source"],
            chapter=exam["chapter"],
            generated_from=exam.get("generated_from", "form"),
            description=exam.get("description"),
            requested_question_count=exam.get("requested_question_count", len(exam["questions"])),
            bloom_levels=_stored_bloom_levels(exam),
            graded=True,
            score=exam["score"],
            total=len(exam["questions"]),
            review=_build_review(exam),
        )

    return ExamDetailResponse(
        id=exam["id"],
        source=exam["source"],
        chapter=exam["chapter"],
        generated_from=exam.get("generated_from", "form"),
        description=exam.get("description"),
        requested_question_count=exam.get("requested_question_count", len(exam["questions"])),
        bloom_levels=_stored_bloom_levels(exam),
        graded=False,
        questions=[
            ExamQuestion(section=q["section"], question=q["question"], options=q["options"])
            for q in exam["questions"]
        ],
    )


@router.post("/exams/{exam_id}/grade", response_model=GradeExamResponse)
def grade_exam(exam_id: str, request: GradeExamRequest):
    _require_exam_builder_enabled()
    exam = state["exams"].get(exam_id)
    if exam is None:
        raise HTTPException(status_code=404, detail="Exam not found")

    answers = {int(index): choice for index, choice in request.answers.items()}
    score = sum(1 for i, q in enumerate(exam["questions"]) if answers.get(i) == q["correct_index"])
    updated_exam = {**exam, "answers": answers, "score": score}
    _save_exam(updated_exam)
    state["exams"][exam_id] = updated_exam
    exam = updated_exam

    return GradeExamResponse(
        id=exam["id"],
        source=exam["source"],
        chapter=exam["chapter"],
        generated_from=exam.get("generated_from", "form"),
        description=exam.get("description"),
        requested_question_count=exam.get("requested_question_count", len(exam["questions"])),
        bloom_levels=_stored_bloom_levels(exam),
        score=score,
        total=len(exam["questions"]),
        review=_build_review(exam),
    )
