import json
import os
import urllib.error
import urllib.request
import uuid
from asyncio import Lock
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from ebooklib import epub
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from chapter_loader import ChapterLoader
from chunker import Chunker
from exam_parser import parse_exam_json
from exam_prompts import build_exam_messages
from exam_selection import build_exam_selection_messages, parse_exam_selection_json
from index_loader import load_index
from indexer import Indexer
from llm_client import build_client
from preprocessor import PreProcessor
from prompts import build_rag_messages
from retriever import Retriever

RESOURCES_DIR = Path(__file__).parent / "resources"
INDEX_PATH = Path(os.environ.get("INDEX_PATH", Path(__file__).parent.parent / "index.json"))
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
DEFAULT_MODEL = os.environ.get("LLM_MODEL", "qwen3:8b")

# Exam generation is a separate, opt-in module: it reads whole chapters
# straight from the epub (via ChapterLoader) and never touches the BM25
# index or the chat retriever, so it can stay off while it's still new.
EXAM_BUILDER_ENABLED = os.environ.get("EXAM_BUILDER_ENABLED", "false").lower() == "true"
EXAM_MODEL = os.environ.get("EXAM_MODEL", "anthropic/claude-3.5-sonnet")
MAX_UPLOAD_BYTES = 50 * 1024 * 1024

state: dict = {}
library_lock = Lock()


def build_index() -> list[dict]:
    epub_paths = sorted(RESOURCES_DIR.glob("*.epub"))
    books = [epub.read_epub(str(path)) for path in epub_paths]

    chunker = Chunker()
    chunks = [chunk for book_chunks in chunker.process_books(books) for chunk in book_chunks]

    preprocessor = PreProcessor()
    for chunk in chunks:
        chunk["text"] = preprocessor.process(chunk["text"])

    indexer = Indexer()
    indexed = indexer.index(chunks)
    indexer.save(indexed, INDEX_PATH)
    return indexed


@asynccontextmanager
async def lifespan(app: FastAPI):
    state["index"] = load_index(INDEX_PATH) if INDEX_PATH.exists() else build_index()
    state["retriever"] = Retriever()
    state["chapter_loader"] = ChapterLoader(RESOURCES_DIR)
    state["exams"] = {}
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


def _safe_epub_filename(filename: str) -> str:
    candidate = Path(filename).name
    if not filename or candidate != filename or candidate in {".", ".."}:
        raise HTTPException(status_code=400, detail="A valid filename is required")
    if Path(candidate).suffix.lower() != ".epub":
        raise HTTPException(status_code=415, detail="Only EPUB files are supported")
    return candidate


@app.post("/library/upload", response_model=UploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_library_file(request: Request, filename: str):
    safe_filename = _safe_epub_filename(filename)
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File must be 50 MB or smaller")

    RESOURCES_DIR.mkdir(parents=True, exist_ok=True)
    async with library_lock:
        destination = RESOURCES_DIR / safe_filename
        if destination.exists():
            raise HTTPException(
                status_code=409,
                detail=f"A book named {safe_filename} already exists in the library.",
            )

        temporary_path = RESOURCES_DIR / f".{uuid.uuid4().hex}.upload"
        size = 0
        try:
            with temporary_path.open("wb") as upload:
                async for chunk in request.stream():
                    size += len(chunk)
                    if size > MAX_UPLOAD_BYTES:
                        raise HTTPException(status_code=413, detail="File must be 50 MB or smaller")
                    upload.write(chunk)

            if size == 0:
                raise HTTPException(status_code=400, detail="The uploaded file is empty")

            temporary_path.replace(destination)
            try:
                indexed = build_index()
            except Exception as exc:
                destination.unlink(missing_ok=True)
                raise HTTPException(status_code=422, detail="Could not read this EPUB file") from exc

            state["index"] = indexed
            return UploadResponse(filename=destination.name, indexed_chunks=len(indexed))
        finally:
            temporary_path.unlink(missing_ok=True)


class FeaturesResponse(BaseModel):
    exam_builder: bool


@app.get("/features", response_model=FeaturesResponse)
def get_features():
    return FeaturesResponse(exam_builder=EXAM_BUILDER_ENABLED)


# ===================== Exam builder =====================
#
# Separate from the chat/RAG path above: exams are generated from a whole
# chapter's text (via ChapterLoader), not BM25 search results, and answers
# are withheld from the client until the exam is graded.


class Book(BaseModel):
    title: str
    chapters: list[str]


class BooksResponse(BaseModel):
    books: list[Book]


class GenerateExamRequest(BaseModel):
    book: str
    chapter: str
    num_questions: int = Field(10, ge=1, le=30)
    generated_from: Literal["form", "description"] = "form"
    description: str | None = None


class ResolveExamDescriptionRequest(BaseModel):
    description: str = Field(min_length=1, max_length=4_000)


class ResolveExamDescriptionResponse(BaseModel):
    book: str
    chapter: str


class ExamQuestion(BaseModel):
    section: str
    question: str
    options: list[str]


class GenerateExamResponse(BaseModel):
    id: str
    book: str
    chapter: str
    generated_from: Literal["form", "description"]
    description: str | None
    requested_question_count: int
    questions: list[ExamQuestion]


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
    book: str
    chapter: str
    score: int
    total: int
    review: list[ReviewQuestion]


class ExamSummary(BaseModel):
    id: str
    book: str
    chapter: str
    created_at: str
    total: int
    score: int | None
    generated_from: Literal["form", "description"]
    description: str | None
    requested_question_count: int


class ExamListResponse(BaseModel):
    exams: list[ExamSummary]


class ExamDetailResponse(BaseModel):
    id: str
    book: str
    chapter: str
    generated_from: Literal["form", "description"]
    description: str | None
    requested_question_count: int
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
        book, chapter = parse_exam_selection_json(raw, books)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Could not resolve a book and chapter: {exc}") from exc

    return ResolveExamDescriptionResponse(book=book, chapter=chapter)


@app.post("/exams", response_model=GenerateExamResponse)
def generate_exam(request: GenerateExamRequest):
    _require_exam_builder_enabled()

    description = request.description.strip() if request.description else None
    if request.generated_from == "description" and not description:
        raise HTTPException(status_code=400, detail="description must not be empty when generated_from is 'description'")

    try:
        chapter_text = state["chapter_loader"].load_chapter_text(request.book, request.chapter)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    messages = build_exam_messages(
        request.book,
        request.chapter,
        chapter_text,
        request.num_questions,
        description=description if request.generated_from == "description" else None,
    )

    try:
        client = build_client("openrouter", EXAM_MODEL)
        raw = client.chat(messages)
    except KeyError as exc:
        raise HTTPException(status_code=500, detail=f"Missing required environment variable: {exc}") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise HTTPException(status_code=502, detail=f"LLM request failed: {exc}") from exc

    try:
        questions = parse_exam_json(raw)
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=f"Could not parse exam from model output: {exc}") from exc

    exam_id = str(uuid.uuid4())
    state["exams"][exam_id] = {
        "id": exam_id,
        "book": request.book,
        "chapter": request.chapter,
        "questions": questions,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "answers": None,
        "score": None,
        "generated_from": request.generated_from,
        "description": description if request.generated_from == "description" else None,
        "requested_question_count": request.num_questions,
    }
    return GenerateExamResponse(
        id=exam_id,
        book=request.book,
        chapter=request.chapter,
        generated_from=request.generated_from,
        description=state["exams"][exam_id]["description"],
        requested_question_count=request.num_questions,
        questions=[
            ExamQuestion(section=q["section"], question=q["question"], options=q["options"]) for q in questions
        ],
    )


@app.get("/exams", response_model=ExamListResponse)
def list_exams():
    _require_exam_builder_enabled()
    exams = sorted(state["exams"].values(), key=lambda e: e["created_at"], reverse=True)
    return ExamListResponse(
        exams=[
            ExamSummary(
                id=e["id"],
                book=e["book"],
                chapter=e["chapter"],
                created_at=e["created_at"],
                total=len(e["questions"]),
                score=e["score"],
                generated_from=e.get("generated_from", "form"),
                description=e.get("description"),
                requested_question_count=e.get("requested_question_count", len(e["questions"])),
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
            book=exam["book"],
            chapter=exam["chapter"],
            generated_from=exam.get("generated_from", "form"),
            description=exam.get("description"),
            requested_question_count=exam.get("requested_question_count", len(exam["questions"])),
            graded=True,
            score=exam["score"],
            total=len(exam["questions"]),
            review=_build_review(exam),
        )

    return ExamDetailResponse(
        id=exam["id"],
        book=exam["book"],
        chapter=exam["chapter"],
        generated_from=exam.get("generated_from", "form"),
        description=exam.get("description"),
        requested_question_count=exam.get("requested_question_count", len(exam["questions"])),
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
    exam["answers"] = answers
    exam["score"] = score

    return GradeExamResponse(
        id=exam["id"],
        book=exam["book"],
        chapter=exam["chapter"],
        score=score,
        total=len(exam["questions"]),
        review=_build_review(exam),
    )
