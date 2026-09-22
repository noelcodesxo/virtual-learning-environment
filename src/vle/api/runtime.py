"""Application lifecycle and runtime-owned shared dependencies."""

from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI

from vle.core.config import Settings
from vle.exams.durable_job_store import ExamJobStore
from vle.exams.service import BLOOM_LEVELS
from vle.exams.store import ExamStore
from vle.library.service import LibraryService
from vle.rag.index_loader import load_index
from vle.rag.retrieval import Retriever


# Settings is the production source of truth. The aliases below intentionally
# remain for compatibility with direct-handler tests while routes are migrated.
settings = Settings.from_environment()
RESOURCES_DIR = settings.resources_dir
INDEX_PATH = settings.index_path
EXAMS_DIR = settings.exams_dir
EXAM_JOBS_DIR = settings.exam_jobs_dir
OLLAMA_BASE_URL = settings.ollama_base_url
DEFAULT_MODEL = settings.default_model
EXAM_BUILDER_ENABLED = settings.exam_builder_enabled
EXAM_MODEL = settings.exam_model
EXAM_TOPIC_MAP_PROVIDER = settings.exam_topic_map_provider
EXAM_TOPIC_MAP_MODEL = settings.exam_topic_map_model
TOPIC_MAP_MAX_ATTEMPTS = settings.topic_map_max_attempts

state: dict = {}
library = LibraryService(RESOURCES_DIR, INDEX_PATH)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize persisted state and recover interrupted exam jobs."""
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
