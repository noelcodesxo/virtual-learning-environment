from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from vle.api.routes import chat, exams, features, library
from vle.core.config import Settings
from vle.exams.job_store import ExamJobStore
from vle.exams.service import ExamService
from vle.exams.store import ExamStore
from vle.library.service import LibraryService
from vle.llm.clients import build_client
from vle.rag.index_loader import load_index
from vle.rag.retrieval import Retriever


def create_app(settings: Settings | None = None) -> FastAPI:
    app_settings = settings or Settings.from_environment()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        service = LibraryService(app_settings.resources_dir, app_settings.index_path)
        if not service.list_books():
            indexed = []
        else:
            indexed = load_index(app_settings.index_path) if app_settings.index_path.exists() else service.build_index()
        store = ExamStore(app_settings.exams_dir)
        jobs = ExamJobStore(store.load())
        app.state.settings = app_settings
        app.state.library = service
        app.state.index = indexed
        app.state.retriever = Retriever()
        app.state.exam_store = store
        app.state.exam_jobs = jobs
        app.state.exam_service = ExamService(service, store, jobs, build_client, app_settings.exam_model)
        yield
        app.state._state.clear()

    application = FastAPI(lifespan=lifespan)
    application.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
    application.include_router(chat.router)
    application.include_router(library.router)
    application.include_router(features.router)
    application.include_router(exams.router)
    return application


app = create_app()

# The feature-complete API currently lives in ``legacy`` while its route
# workflows are being extracted. Keep both package entrypoints on the same
# application so deployment cannot silently lose exam-job behavior.
from vle.api.legacy import app as app
