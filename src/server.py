import json
import os
import urllib.error
import urllib.request
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from ebooklib import epub
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from chapter_loader import ChapterLoader
from chunker import Chunker
from exam_parser import parse_exam_json
from exam_prompts import build_exam_messages
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

state: dict = {}


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


class ExamQuestion(BaseModel):
    section: str
    question: str
    options: list[str]


class GenerateExamResponse(BaseModel):
    id: str
    book: str
    chapter: str
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


class ExamListResponse(BaseModel):
    exams: list[ExamSummary]


class ExamDetailResponse(BaseModel):
    id: str
    book: str
    chapter: str
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


@app.post("/exams", response_model=GenerateExamResponse)
def generate_exam(request: GenerateExamRequest):
    _require_exam_builder_enabled()

    try:
        chapter_text = state["chapter_loader"].load_chapter_text(request.book, request.chapter)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    messages = build_exam_messages(request.book, request.chapter, chapter_text, request.num_questions)

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
    }
    return GenerateExamResponse(
        id=exam_id,
        book=request.book,
        chapter=request.chapter,
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
            graded=True,
            score=exam["score"],
            total=len(exam["questions"]),
            review=_build_review(exam),
        )

    return ExamDetailResponse(
        id=exam["id"],
        book=exam["book"],
        chapter=exam["chapter"],
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
