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

from vle.exams.bloom_prompts import build_exam_messages
from vle.exams.durable_job_store import ExamJobStore, ExamJobStoreError
from vle.exams.parser import parse_exam_json
from vle.exams.selection import build_exam_selection_messages, parse_exam_selection_json
from vle.exams.store import ExamStore, ExamStoreError
from vle.exams.topic_map_workflow import TOPIC_MAP_JSON_SCHEMA, build_topic_map_messages, parse_topic_map_json
from vle.library.service import LibraryError, LibraryService
from vle.llm.clients import build_client
from vle.rag.index_loader import load_index
from vle.rag.prompts import build_rag_messages
from vle.rag.retrieval import Retriever

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
RESOURCES_DIR = REPOSITORY_ROOT / "src" / "resources"
INDEX_PATH = Path(os.environ.get("INDEX_PATH", REPOSITORY_ROOT / "index.json"))
EXAMS_DIR = Path(os.environ.get("EXAMS_DIR", REPOSITORY_ROOT / "data" / "exams"))
EXAM_JOBS_DIR = Path(os.environ.get("EXAM_JOBS_DIR", REPOSITORY_ROOT / "data" / "exam_jobs"))
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
