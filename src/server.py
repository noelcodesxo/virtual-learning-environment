import json
import os
import urllib.error
import urllib.request
from contextlib import asynccontextmanager
from pathlib import Path

from ebooklib import epub
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from chunker import Chunker
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
