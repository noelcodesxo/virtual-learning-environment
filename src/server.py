import json
import os
import urllib.error
import urllib.request
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from ebooklib import epub
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from chapter_loader import ChapterLoader
from auth import CurrentUser, require_current_user
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
from user_repository import get_repository

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
    thread_id: str | None = None


class Source(BaseModel):
    book: str | None = None
    chapter: str | None = None
    section: str | None = None
    score: float


class ChatResponse(BaseModel):
    answer: str
    sources: list[Source]
    thread_id: str
    title: str


class ModelsResponse(BaseModel):
    models: list[str]


class ChatThreadSummary(BaseModel):
    id: str
    title: str
    updated_at: str


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str
    sources: list[Source] | None = None


class ChatThreadResponse(BaseModel):
    id: str
    title: str
    messages: list[ChatMessage]


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


def _chat_title(text: str) -> str:
    return text if len(text) <= 40 else f"{text[:39].rstrip()}…"


def _user_id(user: CurrentUser) -> str:
    # Direct unit tests call route functions without FastAPI resolving Depends.
    return getattr(user, "id", "test-user")


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest, user: CurrentUser = Depends(require_current_user)):
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
    repository = get_repository()
    if request.thread_id:
        thread = repository.get_thread(_user_id(user), request.thread_id)
        if thread is None:
            raise HTTPException(status_code=404, detail="Chat thread not found")
    else:
        thread = repository.create_thread(_user_id(user), _chat_title(request.query.strip()))
    repository.add_message(_user_id(user), thread["id"], "user", request.query.strip())
    repository.add_message(_user_id(user), thread["id"], "assistant", answer, [source.model_dump() for source in sources])
    return ChatResponse(answer=answer, sources=sources, thread_id=thread["id"], title=thread["title"])


@app.get("/chat/threads", response_model=list[ChatThreadSummary])
def list_chat_threads(user: CurrentUser = Depends(require_current_user)):
    return [ChatThreadSummary(**thread) for thread in get_repository().list_threads(_user_id(user))]


@app.get("/chat/threads/{thread_id}", response_model=ChatThreadResponse)
def get_chat_thread(thread_id: str, user: CurrentUser = Depends(require_current_user)):
    repository = get_repository()
    thread = repository.get_thread(_user_id(user), thread_id)
    if thread is None:
        raise HTTPException(status_code=404, detail="Chat thread not found")
    return ChatThreadResponse(id=thread["id"], title=thread["title"], messages=[ChatMessage(role=m["role"], content=m["content"], sources=m.get("sources")) for m in repository.get_messages(_user_id(user), thread_id)])


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
            given_index=answers.get(i, answers.get(str(i))),
        )
        for i, q in enumerate(exam["questions"])
    ]


@app.get("/books", response_model=BooksResponse)
def list_books(user: CurrentUser = Depends(require_current_user)):
    _require_exam_builder_enabled()
    return BooksResponse(books=[Book(**b) for b in state["chapter_loader"].list_books()])


@app.post("/exams/resolve-description", response_model=ResolveExamDescriptionResponse)
def resolve_exam_description(request: ResolveExamDescriptionRequest, user: CurrentUser = Depends(require_current_user)):
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
def generate_exam(request: GenerateExamRequest, user: CurrentUser = Depends(require_current_user)):
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
    exam = {
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
    get_repository().create_exam(_user_id(user), exam)
    return GenerateExamResponse(
        id=exam_id,
        book=request.book,
        chapter=request.chapter,
        generated_from=request.generated_from,
        description=exam["description"],
        requested_question_count=request.num_questions,
        questions=[
            ExamQuestion(section=q["section"], question=q["question"], options=q["options"]) for q in questions
        ],
    )


@app.get("/exams", response_model=ExamListResponse)
def list_exams(user: CurrentUser = Depends(require_current_user)):
    _require_exam_builder_enabled()
    exams = get_repository().list_exams(_user_id(user))
    return ExamListResponse(
        exams=[
            ExamSummary(
                id=e["id"],
                book=e["book"],
                chapter=e["chapter"],
                created_at=e["created_at"],
                total=e["total"],
                score=e["score"],
                generated_from=e.get("generated_from", "form"),
                description=e.get("description"),
                requested_question_count=e.get("requested_question_count", e["total"]),
            )
            for e in exams
        ]
    )


@app.get("/exams/{exam_id}", response_model=ExamDetailResponse)
def get_exam(exam_id: str, user: CurrentUser = Depends(require_current_user)):
    _require_exam_builder_enabled()
    exam = get_repository().get_exam(_user_id(user), exam_id)
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
def grade_exam(exam_id: str, request: GradeExamRequest, user: CurrentUser = Depends(require_current_user)):
    _require_exam_builder_enabled()
    answers = {int(index): choice for index, choice in request.answers.items()}
    exam = get_repository().grade_exam(_user_id(user), exam_id, answers)
    if exam is None:
        raise HTTPException(status_code=404, detail="Exam not found")

    return GradeExamResponse(
        id=exam["id"],
        book=exam["book"],
        chapter=exam["chapter"],
        score=exam["score"],
        total=len(exam["questions"]),
        review=_build_review(exam),
    )
