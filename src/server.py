import json
import logging
import os
import time
import urllib.error
import urllib.request
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from exam_parser import parse_exam_json
from exam_job_store import ExamJobStore, ExamJobStoreError
from exam_prompts import build_exam_messages
from exam_selection import build_exam_selection_messages, parse_exam_selection_json
from exam_store import ExamStore, ExamStoreError
from exam_topic_map import TOPIC_MAP_JSON_SCHEMA, build_topic_map_messages, parse_topic_map_json
from index_loader import load_index
from library import LibraryError, LibraryService
from llm_client import build_client
from prompts import build_rag_messages
from retriever import Retriever

RESOURCES_DIR = Path(__file__).parent / "resources"
INDEX_PATH = Path(os.environ.get("INDEX_PATH", Path(__file__).parent.parent / "index.json"))
EXAMS_DIR = Path(os.environ.get("EXAMS_DIR", Path(__file__).parent.parent / "data" / "exams"))
EXAM_JOBS_DIR = Path(os.environ.get("EXAM_JOBS_DIR", Path(__file__).parent.parent / "data" / "exam_jobs"))
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
DEFAULT_MODEL = os.environ.get("LLM_MODEL", "qwen3:8b")

# Exam generation is a separate, opt-in module: it reads full source text
# from the document library (a chapter for EPUBs, an entire document for
# other formats) and never touches the BM25 index or chat retriever.
EXAM_BUILDER_ENABLED = os.environ.get("EXAM_BUILDER_ENABLED", "false").lower() == "true"
EXAM_MODEL = os.environ.get("EXAM_MODEL", "anthropic/claude-3.5-sonnet")
# Topic maps are intentionally cheap and fast: by default they use the same
# local Ollama model as chat, while question writing continues to use EXAM_MODEL.
EXAM_TOPIC_MAP_PROVIDER = os.environ.get("EXAM_TOPIC_MAP_PROVIDER", "ollama")
EXAM_TOPIC_MAP_MODEL = os.environ.get("EXAM_TOPIC_MAP_MODEL", DEFAULT_MODEL)
TOPIC_MAP_MAX_ATTEMPTS = 3
BLOOM_LEVELS = ("remember", "understand", "apply", "analyze", "evaluate", "create")
BloomLevel = Literal["remember", "understand", "apply", "analyze", "evaluate", "create"]

# Uvicorn configures this logger at INFO, unlike the application root logger.
# Use it so model timing is visible in the same server logs as API requests.
logger = logging.getLogger("uvicorn.error")
state: dict = {}
library = LibraryService(RESOURCES_DIR, INDEX_PATH)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # The persisted index is only valid while it has source documents to back
    # it. This keeps a stale index from answering chat requests after the
    # resource library has been emptied.
    books = library.list_books()
    if not books:
        state["index"] = []
    else:
        state["index"] = load_index(INDEX_PATH) if INDEX_PATH.exists() else library.build_index()
    state["retriever"] = Retriever()
    state["chapter_loader"] = library
    state["exam_store"] = ExamStore(EXAMS_DIR)
    state["exams"] = state["exam_store"].load()
    state["exam_job_store"] = ExamJobStore(EXAM_JOBS_DIR)
    state["exam_jobs"] = state["exam_job_store"].load()
    for job in state["exam_jobs"].values():
        if job["status"] not in {"queued", "running"}:
            continue
        job["status"] = "failed"
        job["error"] = "Exam generation was interrupted by a server restart. Please start a new exam."
        job["updated_at"] = datetime.now(timezone.utc).isoformat()
        state["exam_job_store"].save(job)
    yield
    state.clear()


app = FastAPI(lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    query: str
    model: str = DEFAULT_MODEL


class Source(BaseModel):
    book: str | None = None
    chapter: str | None = None
    section: str | None = None
    score: float


class ChatResponse(BaseModel):
    answer: str
    sources: list[Source]


class ModelsResponse(BaseModel):
    models: list[str]


class UploadResponse(BaseModel):
    filename: str
    indexed_chunks: int


class DeleteResponse(BaseModel):
    filename: str
    indexed_chunks: int


class LibraryDocument(BaseModel):
    title: str
    filename: str
    format: str
    chapters: list[str]


class LibraryResponse(BaseModel):
    documents: list[LibraryDocument]


def fetch_ollama_models(base_url: str) -> list[str]:
    request = urllib.request.Request(f"{base_url.rstrip('/')}/api/tags")
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            data = json.load(response)
    except (urllib.error.URLError, TimeoutError) as exc:
        raise HTTPException(status_code=502, detail=f"Could not reach Ollama at {base_url}: {exc}") from exc
    return sorted(model["name"] for model in data.get("models", []))


@app.get("/models", response_model=ModelsResponse)
def list_models():
    return ModelsResponse(models=fetch_ollama_models(OLLAMA_BASE_URL))


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest):
    if not request.query.strip():
        raise HTTPException(status_code=400, detail="query must not be empty")

    results = state["retriever"].search(request.query, state["index"])
    messages = build_rag_messages(request.query, results)
    client = build_client("ollama", request.model, base_url=OLLAMA_BASE_URL)

    try:
        answer = client.chat(messages)
    except (urllib.error.URLError, TimeoutError) as exc:
        raise HTTPException(status_code=502, detail=f"LLM request failed: {exc}") from exc

    sources = [
        Source(book=r.get("book"), chapter=r.get("chapter"), section=r.get("section"), score=r["score"])
        for r in results
    ]
    return ChatResponse(answer=answer, sources=sources)


@app.post("/library/upload", response_model=UploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_library_file(request: Request, filename: str):
    try:
        result = await library.upload(filename, request.stream(), request.headers.get("content-length"))
    except LibraryError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    state["index"] = result.indexed
    return UploadResponse(filename=result.filename, indexed_chunks=len(result.indexed))


@app.get("/library", response_model=LibraryResponse)
def list_library_documents():
    return LibraryResponse(documents=[LibraryDocument(**document) for document in library.list_documents()])


@app.delete("/library/{filename}", response_model=DeleteResponse)
async def delete_library_file(filename: str):
    try:
        result = await library.delete(filename)
    except LibraryError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    state["index"] = result.indexed
    return DeleteResponse(filename=result.filename, indexed_chunks=len(result.indexed))


class FeaturesResponse(BaseModel):
    exam_builder: bool


@app.get("/features", response_model=FeaturesResponse)
def get_features():
    return FeaturesResponse(exam_builder=EXAM_BUILDER_ENABLED)


# ===================== Exam builder =====================
#
# Separate from the chat/RAG path above: exams use bounded source excerpts
# from the selected EPUB chapter or full document, not BM25 search results.
# Answers are withheld from the client until the exam is graded.


class Book(BaseModel):
    title: str
    chapters: list[str]


class BooksResponse(BaseModel):
    books: list[Book]


class GenerateExamRequest(BaseModel):
    source: str
    chapter: str
    num_questions: int = Field(10, ge=1, le=30)
    generated_from: Literal["form", "description"] = "form"
    description: str | None = None
    bloom_levels: list[BloomLevel] = Field(default_factory=lambda: list(BLOOM_LEVELS), min_length=1)


class ResolveExamDescriptionRequest(BaseModel):
    description: str = Field(min_length=1, max_length=4_000)


class ResolveExamDescriptionResponse(BaseModel):
    source: str
    chapter: str


class ExamQuestion(BaseModel):
    section: str
    question: str
    options: list[str]


class GenerateExamResponse(BaseModel):
    id: str
    source: str
    chapter: str
    generated_from: Literal["form", "description"]
    description: str | None
    requested_question_count: int
    bloom_levels: list[BloomLevel]
    questions: list[ExamQuestion]


JobStatus = Literal["queued", "running", "completed", "failed"]


class ExamJobResponse(BaseModel):
    id: str
    status: JobStatus
    exam_id: str | None
    error: str | None
    created_at: str
    updated_at: str


class ExamJobListResponse(BaseModel):
    jobs: list[ExamJobResponse]


class GradeExamRequest(BaseModel):
    answers: dict[str, int]


class ReviewQuestion(BaseModel):
    section: str
    question: str
    options: list[str]
    correct_index: int
    why: str
    given_index: int | None


class GradeExamResponse(BaseModel):
    id: str
    source: str
    chapter: str
    generated_from: Literal["form", "description"]
    description: str | None
    requested_question_count: int
    bloom_levels: list[BloomLevel]
    score: int
    total: int
    review: list[ReviewQuestion]


class ExamSummary(BaseModel):
    id: str
    source: str
    chapter: str
    created_at: str
    total: int
    score: int | None
    generated_from: Literal["form", "description"]
    description: str | None
    requested_question_count: int
    bloom_levels: list[BloomLevel]


class ExamListResponse(BaseModel):
    exams: list[ExamSummary]


class ExamDetailResponse(BaseModel):
    id: str
    source: str
    chapter: str
    generated_from: Literal["form", "description"]
    description: str | None
    requested_question_count: int
    bloom_levels: list[BloomLevel]
    graded: bool
    questions: list[ExamQuestion] | None = None
    score: int | None = None
    total: int | None = None
    review: list[ReviewQuestion] | None = None


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


@app.get("/books", response_model=BooksResponse)
def list_books():
    _require_exam_builder_enabled()
    return BooksResponse(books=[Book(**b) for b in state["chapter_loader"].list_books()])


@app.post("/exams/resolve-description", response_model=ResolveExamDescriptionResponse)
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


@app.post("/exams", response_model=GenerateExamResponse)
def generate_exam(request: GenerateExamRequest):
    """Generate synchronously for existing API consumers."""
    return _generate_exam(request)


@app.post("/exam-jobs", response_model=ExamJobResponse, status_code=status.HTTP_202_ACCEPTED)
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


@app.get("/exam-jobs", response_model=ExamJobListResponse)
def list_exam_jobs():
    _require_exam_builder_enabled()
    jobs = sorted(state["exam_jobs"].values(), key=lambda job: job["created_at"], reverse=True)
    return ExamJobListResponse(jobs=[_job_response(job) for job in jobs])


@app.get("/exam-jobs/{job_id}", response_model=ExamJobResponse)
def get_exam_job(job_id: str):
    _require_exam_builder_enabled()
    job = state["exam_jobs"].get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Exam generation job not found")
    return _job_response(job)


@app.get("/exams", response_model=ExamListResponse)
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


@app.get("/exams/{exam_id}", response_model=ExamDetailResponse)
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


@app.post("/exams/{exam_id}/grade", response_model=GradeExamResponse)
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
