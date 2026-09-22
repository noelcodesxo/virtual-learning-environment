import json
import logging
import urllib.error
from asyncio import run

import pytest
from fastapi import BackgroundTasks, HTTPException

from vle.api import app as application
from vle.api import runtime
from vle.api.routes import chat as chat_routes
from vle.api.routes import exams as exam_routes
from vle.api.routes import features as feature_routes
from vle.api.routes import library as library_routes
from vle.exams.store import ExamStore, ExamStoreError
from vle.library.service import DeleteResult, LibraryError, UploadResult
from vle.api.routes.chat import ChatRequest, chat, list_models


class _LiveHandlers:
    """Expose the live routes through the old test seams during the move."""

    _chat_names = {
        "ChatRequest", "ChatResponse", "ModelsResponse", "Source", "fetch_ollama_models",
        "list_models", "chat", "urllib",
    }
    _library_names = {
        "UploadResponse", "DeleteResponse", "LibraryDocument", "LibraryResponse",
        "upload_library_file", "delete_library_file", "list_library_documents",
    }
    _feature_names = {"FeaturesResponse", "get_features"}
    _runtime_names = {
        "state", "library", "lifespan", "INDEX_PATH", "EXAMS_DIR", "EXAM_JOBS_DIR",
        "DEFAULT_MODEL", "load_index",
    }

    def __getattr__(self, name):
        if name == "app":
            return application.app
        if name in self._chat_names:
            return getattr(chat_routes, name)
        if name in self._library_names:
            return getattr(library_routes, name)
        if name in self._feature_names:
            return getattr(feature_routes, name)
        if name in self._runtime_names:
            return getattr(runtime, name)
        return getattr(exam_routes, name)

    def __setattr__(self, name, value):
        if name.startswith("_"):
            return super().__setattr__(name, value)
        if name == "build_client":
            chat_routes.build_client = value
            exam_routes.build_client = value
            return
        if name == "library":
            runtime.library = value
            library_routes.library = value
            return
        if name == "EXAM_BUILDER_ENABLED":
            feature_routes.EXAM_BUILDER_ENABLED = value
            exam_routes.EXAM_BUILDER_ENABLED = value
            return
        if name in self._runtime_names:
            setattr(runtime, name, value)
            return
        if name in self._chat_names:
            setattr(chat_routes, name, value)
            return
        if name in self._library_names:
            setattr(library_routes, name, value)
            return
        if name in self._feature_names:
            setattr(feature_routes, name, value)
            return
        setattr(exam_routes, name, value)


server = _LiveHandlers()


class _FakeResponse:
    def __init__(self, payload):
        import json

        self._payload = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        from io import BytesIO

        return BytesIO(self._payload)

    def __exit__(self, *args):
        return False


class _FakeRetriever:
    def __init__(self, results):
        self._results = results

    def search(self, query, index, top_k=None):
        return self._results


class _FakeClient:
    def __init__(self, answer):
        self._answer = answer

    def chat(self, messages, response_format=None):
        return self._answer


class _FakeUploadRequest:
    def __init__(self, chunks, headers=None):
        self._chunks = chunks
        self.headers = headers or {}

    async def stream(self):
        for chunk in self._chunks:
            yield chunk


class _FakeLibrary:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.uploaded = None
        self.deleted = None

    async def upload(self, filename, chunks, content_length):
        self.uploaded = (filename, [chunk async for chunk in chunks], content_length)
        if self.error:
            raise self.error
        return self.result

    def list_documents(self):
        return [{"title": "Research paper", "filename": "research.pdf", "format": "pdf", "chapters": ["Entire document"]}]

    async def delete(self, filename):
        self.deleted = filename
        if self.error:
            raise self.error
        return self.result


class _FakeExamStore:
    def __init__(self, error=None):
        self.error = error
        self.saved = []

    def save(self, exam):
        if self.error:
            raise self.error
        self.saved.append(exam)


class _FakeExamJobStore:
    def __init__(self, error=None):
        self.error = error
        self.saved = []

    def save(self, job):
        if self.error:
            raise self.error
        self.saved.append(job)


def test_list_models_returns_sorted_model_names(monkeypatch):
    def fake_urlopen(request, timeout=None):
        return _FakeResponse({"models": [{"name": "qwen3:8b"}, {"name": "llama3"}]})

    monkeypatch.setattr(server.urllib.request, "urlopen", fake_urlopen)

    response = list_models()

    assert response.models == ["llama3", "qwen3:8b"]


def test_list_models_raises_502_when_ollama_unreachable(monkeypatch):
    def fake_urlopen(request, timeout=None):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(server.urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(HTTPException) as exc_info:
        list_models()

    assert exc_info.value.status_code == 502


def test_chat_returns_answer_and_sources_from_retrieved_chunks(monkeypatch):
    results = [
        {
            "book": "AI Engineering",
            "chapter": "Ch. 4",
            "section": "RLHF",
            "text": "rlhf trains a reward model on human preferences",
            "score": 0.82,
        },
    ]
    monkeypatch.setitem(server.state, "index", [])
    monkeypatch.setitem(server.state, "retriever", _FakeRetriever(results))
    monkeypatch.setattr(server, "build_client", lambda provider, model, base_url=None: _FakeClient("the answer"))

    response = chat(ChatRequest(query="what is RLHF?", model="qwen3:8b"))

    assert response.answer == "the answer"
    assert response.sources == [
        server.Source(book="AI Engineering", chapter="Ch. 4", section="RLHF", score=0.82)
    ]


def test_chat_rejects_empty_query():
    with pytest.raises(HTTPException) as exc_info:
        chat(ChatRequest(query="   "))

    assert exc_info.value.status_code == 400


def test_upload_library_file_delegates_to_the_library_service(monkeypatch):
    indexed = [{"book": "Uploaded", "text": "chunk"}]
    fake_library = _FakeLibrary(UploadResult(filename="uploaded.epub", indexed=indexed))
    monkeypatch.setattr(server, "library", fake_library)
    server.state["index"] = []

    response = run(server.upload_library_file(_FakeUploadRequest([b"epub bytes"]), "uploaded.epub"))

    assert response == server.UploadResponse(filename="uploaded.epub", indexed_chunks=1)
    assert fake_library.uploaded == ("uploaded.epub", [b"epub bytes"], None)
    assert server.state["index"] == indexed


def test_upload_library_file_maps_library_errors_to_http_errors(monkeypatch):
    monkeypatch.setattr(server, "library", _FakeLibrary(error=LibraryError(409, "duplicate")))

    with pytest.raises(HTTPException) as exc_info:
        run(server.upload_library_file(_FakeUploadRequest([b"paper"]), "book.epub"))

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "duplicate"


def test_delete_library_file_delegates_to_the_library_service(monkeypatch):
    indexed = [{"book": "Remaining", "text": "chunk"}]
    fake_library = _FakeLibrary(DeleteResult(filename="uploaded.epub", indexed=indexed))
    monkeypatch.setattr(server, "library", fake_library)
    server.state["index"] = []

    response = run(server.delete_library_file("uploaded.epub"))

    assert response == server.DeleteResponse(filename="uploaded.epub", indexed_chunks=1)
    assert fake_library.deleted == "uploaded.epub"
    assert server.state["index"] == indexed


def test_delete_library_file_maps_library_errors_to_http_errors(monkeypatch):
    monkeypatch.setattr(server, "library", _FakeLibrary(error=LibraryError(404, "missing")))

    with pytest.raises(HTTPException) as exc_info:
        run(server.delete_library_file("missing.epub"))

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "missing"


def test_get_features_reflects_the_env_flag(monkeypatch):
    monkeypatch.setattr(server, "EXAM_BUILDER_ENABLED", True)
    assert server.get_features().exam_builder is True

    monkeypatch.setattr(server, "EXAM_BUILDER_ENABLED", False)
    assert server.get_features().exam_builder is False


def test_lifespan_restores_saved_exams(monkeypatch, tmp_path):
    exam = {
        "id": "exam-1",
        "source": "Book",
        "chapter": "Chapter",
        "questions": [_exam_question()],
        "created_at": "2024-01-01T00:00:00+00:00",
        "answers": {0: 1},
        "score": 1,
    }
    exams_dir = tmp_path / "exams"
    ExamStore(exams_dir).save(exam)
    index_path = tmp_path / "index.json"
    index_path.write_text("[]")
    monkeypatch.setattr(server, "EXAMS_DIR", exams_dir)
    monkeypatch.setattr(server, "INDEX_PATH", index_path)
    monkeypatch.setattr(server, "load_index", lambda path: [])

    async def run_lifespan():
        async with server.lifespan(server.app):
            assert server.state["exams"] == {"exam-1": exam}

    run(run_lifespan())


def test_lifespan_ignores_a_cached_index_without_library_documents(monkeypatch, tmp_path):
    index_path = tmp_path / "index.json"
    index_path.write_text('[{"book": "Stale book", "text": "stale chunk"}]')
    monkeypatch.setattr(server, "INDEX_PATH", index_path)
    monkeypatch.setattr(server, "EXAMS_DIR", tmp_path / "exams")
    monkeypatch.setattr(server, "library", _FakeChapterLoader())
    monkeypatch.setattr(server, "load_index", lambda path: pytest.fail("should not load a stale index"))

    async def run_lifespan():
        async with server.lifespan(server.app):
            assert server.state["index"] == []

    run(run_lifespan())


def test_list_library_documents_is_available_when_exam_builder_is_disabled(monkeypatch):
    monkeypatch.setattr(server, "EXAM_BUILDER_ENABLED", False)
    monkeypatch.setattr(server, "library", _FakeLibrary())

    response = server.list_library_documents()

    assert response.documents == [server.LibraryDocument(
        title="Research paper", filename="research.pdf", format="pdf", chapters=["Entire document"]
    )]


class _FakeChapterLoader:
    def __init__(self, books=None, chapter_text_by_key=None, missing=False):
        self._books = books or []
        self._chapter_text_by_key = chapter_text_by_key or {}
        self._missing = missing

    def list_books(self):
        return self._books

    def load_chapter_text(self, book, chapter):
        if self._missing:
            raise ValueError(f"Chapter {chapter!r} not found in {book!r}")
        return self._chapter_text_by_key[(book, chapter)]

    def load_exam_text(self, book, chapter, num_questions):
        return self.load_chapter_text(book, chapter)


def _exam_question(**overrides):
    base = {
        "section": "Evaluation Criteria",
        "question": "What is X?",
        "options": ["A", "B", "C"],
        "correct_index": 1,
        "why": "Because B is right.",
    }
    base.update(overrides)
    return base


TOPIC_MAP = {
    "topics": [
        {"topic": "Core concept", "summary": "A chapter concept.", "source_excerpt": "text"}
    ]
}


def _mock_exam_clients(monkeypatch, exam_raw=None):
    calls = []

    def fake_build_client(provider, model):
        calls.append((provider, model))
        if len(calls) == 1:
            return _FakeClient(json.dumps(TOPIC_MAP))
        return _FakeClient(exam_raw if exam_raw is not None else json.dumps([_exam_question()]))

    monkeypatch.setattr(server, "build_client", fake_build_client)
    return calls


def test_exam_endpoints_return_404_when_feature_disabled(monkeypatch):
    monkeypatch.setattr(server, "EXAM_BUILDER_ENABLED", False)
    monkeypatch.setitem(server.state, "exams", {})

    for call in [
        lambda: server.list_books(),
        lambda: server.resolve_exam_description(server.ResolveExamDescriptionRequest(description="a request")),
        lambda: server.generate_exam(server.GenerateExamRequest(source="B", chapter="C")),
        lambda: server.list_exams(),
        lambda: server.get_exam("missing"),
        lambda: server.grade_exam("missing", server.GradeExamRequest(answers={})),
    ]:
        with pytest.raises(HTTPException) as exc_info:
            call()
        assert exc_info.value.status_code == 404


def test_list_books_returns_books_from_the_chapter_loader(monkeypatch):
    monkeypatch.setattr(server, "EXAM_BUILDER_ENABLED", True)
    books = [{"title": "AI Engineering", "chapters": ["4. Evaluate AI Systems"]}]
    monkeypatch.setitem(server.state, "chapter_loader", _FakeChapterLoader(books=books))

    response = server.list_books()

    assert response.books == [server.Book(title="AI Engineering", chapters=["4. Evaluate AI Systems"])]


def test_resolve_exam_description_uses_a_valid_model_selection(monkeypatch):
    monkeypatch.setattr(server, "EXAM_BUILDER_ENABLED", True)
    books = [{"title": "AI Engineering", "chapters": ["2. Understanding Foundation Models"]}]
    monkeypatch.setitem(server.state, "chapter_loader", _FakeChapterLoader(books=books))
    monkeypatch.setattr(server, "build_client", lambda provider, model: _FakeClient(json.dumps({
        "source": "AI Engineering", "chapter": "2. Understanding Foundation Models"
    })))

    response = server.resolve_exam_description(server.ResolveExamDescriptionRequest(
        description="AI Engineering book second chapter, mostly on transformer architecture"
    ))

    assert response.source == "AI Engineering"
    assert response.chapter == "2. Understanding Foundation Models"


def test_generate_exam_stores_answers_but_does_not_return_them(monkeypatch):
    monkeypatch.setattr(server, "EXAM_BUILDER_ENABLED", True)
    loader = _FakeChapterLoader(chapter_text_by_key={("AI Engineering", "4. Evaluate AI Systems"): "chapter text"})
    monkeypatch.setitem(server.state, "chapter_loader", loader)
    monkeypatch.setitem(server.state, "exams", {})
    exam_store = _FakeExamStore()
    monkeypatch.setitem(server.state, "exam_store", exam_store)
    calls = _mock_exam_clients(monkeypatch)

    response = server.generate_exam(
        server.GenerateExamRequest(source="AI Engineering", chapter="4. Evaluate AI Systems", num_questions=1)
    )

    assert response.source == "AI Engineering"
    assert response.questions == [
        server.ExamQuestion(section="Evaluation Criteria", question="What is X?", options=["A", "B", "C"])
    ]
    stored = server.state["exams"][response.id]
    assert stored["questions"][0]["correct_index"] == 1
    assert stored["score"] is None
    assert stored["bloom_levels"] == list(server.BLOOM_LEVELS)
    assert stored["topic_map"] == TOPIC_MAP
    assert calls == [(server.EXAM_TOPIC_MAP_PROVIDER, server.EXAM_TOPIC_MAP_MODEL), ("openrouter", server.EXAM_MODEL)]
    assert exam_store.saved == [stored]


def test_exam_job_returns_immediately_then_persists_a_completed_exam(monkeypatch):
    monkeypatch.setattr(server, "EXAM_BUILDER_ENABLED", True)
    monkeypatch.setitem(server.state, "chapter_loader", _FakeChapterLoader(
        chapter_text_by_key={("AI Engineering", "4. Evaluate AI Systems"): "chapter text"}
    ))
    monkeypatch.setitem(server.state, "exams", {})
    monkeypatch.setitem(server.state, "exam_store", _FakeExamStore())
    job_store = _FakeExamJobStore()
    monkeypatch.setitem(server.state, "exam_job_store", job_store)
    monkeypatch.setitem(server.state, "exam_jobs", {})
    _mock_exam_clients(monkeypatch)
    background_tasks = BackgroundTasks()

    response = server.create_exam_job(
        server.GenerateExamRequest(source="AI Engineering", chapter="4. Evaluate AI Systems", num_questions=1),
        background_tasks,
    )

    assert response.status == "queued"
    assert response.exam_id is None
    assert len(background_tasks.tasks) == 1
    assert server.get_exam_job(response.id).status == "queued"

    run(background_tasks())

    completed = server.get_exam_job(response.id)
    assert completed.status == "completed"
    assert completed.exam_id in server.state["exams"]
    assert job_store.saved[-1]["status"] == "completed"


def test_exam_job_records_a_model_failure_without_losing_the_job(monkeypatch):
    monkeypatch.setattr(server, "EXAM_BUILDER_ENABLED", True)
    monkeypatch.setitem(server.state, "chapter_loader", _FakeChapterLoader(
        chapter_text_by_key={("Book", "Chapter"): "chapter text"}
    ))
    monkeypatch.setitem(server.state, "exams", {})
    monkeypatch.setitem(server.state, "exam_store", _FakeExamStore())
    monkeypatch.setitem(server.state, "exam_job_store", _FakeExamJobStore())
    monkeypatch.setitem(server.state, "exam_jobs", {})

    class FailingClient:
        def chat(self, messages, response_format=None):
            raise urllib.error.URLError("connection reset")

    monkeypatch.setattr(server, "build_client", lambda provider, model: FailingClient())
    background_tasks = BackgroundTasks()
    response = server.create_exam_job(server.GenerateExamRequest(source="Book", chapter="Chapter"), background_tasks)

    run(background_tasks())

    failed = server.get_exam_job(response.id)
    assert failed.status == "failed"
    assert failed.exam_id is None
    assert failed.error == "Topic map request failed: <urlopen error connection reset>"


def test_generate_exam_preserves_a_description_request(monkeypatch):
    monkeypatch.setattr(server, "EXAM_BUILDER_ENABLED", True)
    monkeypatch.setitem(server.state, "chapter_loader", _FakeChapterLoader(
        chapter_text_by_key={("AI Engineering", "4. Evaluate AI Systems"): "chapter text"}
    ))
    monkeypatch.setitem(server.state, "exams", {})
    monkeypatch.setitem(server.state, "exam_store", _FakeExamStore())
    _mock_exam_clients(monkeypatch)

    response = server.generate_exam(server.GenerateExamRequest(
        source="AI Engineering",
        chapter="4. Evaluate AI Systems",
        num_questions=1,
        generated_from="description",
        description="  Focus on practical evaluation tradeoffs.  ",
    ))

    assert response.generated_from == "description"
    assert response.description == "Focus on practical evaluation tradeoffs."
    assert response.requested_question_count == 1
    assert server.state["exams"][response.id]["description"] == "Focus on practical evaluation tradeoffs."
    assert server.get_exam(response.id).description == "Focus on practical evaluation tradeoffs."


def test_generate_exam_returns_500_without_retaining_an_unsaved_exam(monkeypatch):
    monkeypatch.setattr(server, "EXAM_BUILDER_ENABLED", True)
    monkeypatch.setitem(server.state, "chapter_loader", _FakeChapterLoader(
        chapter_text_by_key={("Book", "Chapter"): "text"}
    ))
    exams = {}
    monkeypatch.setitem(server.state, "exams", exams)
    monkeypatch.setitem(server.state, "exam_store", _FakeExamStore(ExamStoreError("disk full")))
    _mock_exam_clients(monkeypatch)

    with pytest.raises(HTTPException) as exc_info:
        server.generate_exam(server.GenerateExamRequest(source="Book", chapter="Chapter"))

    assert exc_info.value.status_code == 500
    assert exams == {}


def test_generate_exam_raises_404_when_chapter_not_found(monkeypatch):
    monkeypatch.setattr(server, "EXAM_BUILDER_ENABLED", True)
    monkeypatch.setitem(server.state, "chapter_loader", _FakeChapterLoader(missing=True))

    with pytest.raises(HTTPException) as exc_info:
        server.generate_exam(server.GenerateExamRequest(source="X", chapter="Y"))

    assert exc_info.value.status_code == 404


def test_generate_exam_raises_500_when_openrouter_api_key_is_missing(monkeypatch):
    monkeypatch.setattr(server, "EXAM_BUILDER_ENABLED", True)
    loader = _FakeChapterLoader(chapter_text_by_key={("Book", "Chapter"): "text"})
    monkeypatch.setitem(server.state, "chapter_loader", loader)

    def fake_build_client(provider, model):
        raise KeyError("OPENROUTER_API_KEY")

    monkeypatch.setattr(server, "build_client", fake_build_client)

    with pytest.raises(HTTPException) as exc_info:
        server.generate_exam(server.GenerateExamRequest(source="Book", chapter="Chapter"))

    assert exc_info.value.status_code == 500


def test_generate_exam_raises_502_when_model_output_cannot_be_parsed(monkeypatch):
    monkeypatch.setattr(server, "EXAM_BUILDER_ENABLED", True)
    loader = _FakeChapterLoader(chapter_text_by_key={("Book", "Chapter"): "text"})
    monkeypatch.setitem(server.state, "chapter_loader", loader)
    _mock_exam_clients(monkeypatch, exam_raw="not json")

    with pytest.raises(HTTPException) as exc_info:
        server.generate_exam(server.GenerateExamRequest(source="Book", chapter="Chapter"))

    assert exc_info.value.status_code == 502


def test_generate_exam_logs_unavailable_topic_map_model_and_returns_503(monkeypatch, caplog):
    monkeypatch.setattr(server, "EXAM_BUILDER_ENABLED", True)
    monkeypatch.setattr(server, "EXAM_TOPIC_MAP_PROVIDER", "openrouter")
    monkeypatch.setattr(server, "EXAM_TOPIC_MAP_MODEL", "missing/model")
    monkeypatch.setitem(server.state, "chapter_loader", _FakeChapterLoader(
        chapter_text_by_key={("Book", "Chapter"): "text"}
    ))

    class MissingModelClient:
        def chat(self, messages, response_format=None):
            raise urllib.error.HTTPError("https://openrouter.ai/api/v1/chat/completions", 404, "Not Found", None, None)

    calls = []

    def fake_build_client(provider, model):
        calls.append((provider, model))
        return MissingModelClient()

    monkeypatch.setattr(server, "build_client", fake_build_client)

    with pytest.raises(HTTPException) as exc_info:
        server.generate_exam(server.GenerateExamRequest(source="Book", chapter="Chapter"))

    assert exc_info.value.status_code == 503
    assert "Topic-map model is unavailable" in exc_info.value.detail
    assert "Configured topic-map model 'missing/model' is not available on OpenRouter" in caplog.text
    assert calls == [("openrouter", "missing/model")]


def test_generate_exam_uses_the_local_chat_model_for_topic_mapping_by_default(monkeypatch):
    monkeypatch.setattr(server, "EXAM_BUILDER_ENABLED", True)
    monkeypatch.setattr(server, "EXAM_TOPIC_MAP_PROVIDER", "ollama")
    monkeypatch.setattr(server, "EXAM_TOPIC_MAP_MODEL", server.DEFAULT_MODEL)
    monkeypatch.setitem(server.state, "chapter_loader", _FakeChapterLoader(
        chapter_text_by_key={("Book", "Chapter"): "chapter text"}
    ))
    monkeypatch.setitem(server.state, "exams", {})
    monkeypatch.setitem(server.state, "exam_store", _FakeExamStore())
    calls = _mock_exam_clients(monkeypatch)

    server.generate_exam(server.GenerateExamRequest(source="Book", chapter="Chapter", num_questions=1))

    assert calls == [("ollama", server.DEFAULT_MODEL), ("openrouter", server.EXAM_MODEL)]


def test_generate_exam_requests_the_topic_map_json_schema_from_ollama(monkeypatch):
    monkeypatch.setattr(server, "EXAM_BUILDER_ENABLED", True)
    monkeypatch.setattr(server, "EXAM_TOPIC_MAP_PROVIDER", "ollama")
    monkeypatch.setitem(server.state, "chapter_loader", _FakeChapterLoader(
        chapter_text_by_key={("Book", "Chapter"): "chapter text"}
    ))
    monkeypatch.setitem(server.state, "exams", {})
    monkeypatch.setitem(server.state, "exam_store", _FakeExamStore())
    response_formats = []

    class SchemaCapturingClient:
        def __init__(self, response):
            self.response = response

        def chat(self, messages, response_format=None):
            response_formats.append(response_format)
            return self.response

    def fake_build_client(provider, model):
        if not response_formats:
            return SchemaCapturingClient(json.dumps(TOPIC_MAP))
        return SchemaCapturingClient(json.dumps([_exam_question()]))

    monkeypatch.setattr(server, "build_client", fake_build_client)

    server.generate_exam(server.GenerateExamRequest(source="Book", chapter="Chapter", num_questions=1))

    assert response_formats == [server.TOPIC_MAP_JSON_SCHEMA, None]


def test_generate_exam_logs_topic_map_and_question_generation_durations(monkeypatch, caplog):
    monkeypatch.setattr(server, "EXAM_BUILDER_ENABLED", True)
    monkeypatch.setitem(server.state, "chapter_loader", _FakeChapterLoader(
        chapter_text_by_key={("Book", "Chapter"): "chapter text"}
    ))
    monkeypatch.setitem(server.state, "exams", {})
    monkeypatch.setitem(server.state, "exam_store", _FakeExamStore())
    _mock_exam_clients(monkeypatch)
    clock = iter([10.0, 11.25, 20.0, 23.5])
    monkeypatch.setattr(server.time, "perf_counter", lambda: next(clock))
    caplog.set_level(logging.INFO, logger="uvicorn.error")

    server.generate_exam(server.GenerateExamRequest(source="Book", chapter="Chapter", num_questions=1))

    assert "Starting exam topic-map generation attempt 1/3" in caplog.text
    assert "Exam topic-map generation attempt 1/3 took 1.25 seconds" in caplog.text
    assert "Starting exam question generation" in caplog.text
    assert "Exam question generation attempt took 3.50 seconds" in caplog.text


def test_generate_exam_passes_selected_bloom_levels_and_topic_map_to_exam_model(monkeypatch):
    monkeypatch.setattr(server, "EXAM_BUILDER_ENABLED", True)
    monkeypatch.setitem(server.state, "chapter_loader", _FakeChapterLoader(
        chapter_text_by_key={("Book", "Chapter"): "chapter text"}
    ))
    monkeypatch.setitem(server.state, "exams", {})
    monkeypatch.setitem(server.state, "exam_store", _FakeExamStore())
    messages = []

    class CapturingClient(_FakeClient):
        def chat(self, request_messages, response_format=None):
            messages.append(request_messages)
            return super().chat(request_messages, response_format=response_format)

    def fake_build_client(provider, model):
        if not messages:
            return CapturingClient(json.dumps(TOPIC_MAP))
        return CapturingClient(json.dumps([_exam_question()]))

    monkeypatch.setattr(server, "build_client", fake_build_client)

    response = server.generate_exam(server.GenerateExamRequest(
        source="Book", chapter="Chapter", num_questions=1, bloom_levels=["apply", "evaluate"]
    ))

    assert response.bloom_levels == ["apply", "evaluate"]
    assert "apply, evaluate" in messages[1][1]["content"]
    assert json.dumps(TOPIC_MAP) in messages[1][1]["content"]


def test_generate_exam_rejects_an_invalid_topic_map(monkeypatch):
    monkeypatch.setattr(server, "EXAM_BUILDER_ENABLED", True)
    monkeypatch.setitem(server.state, "chapter_loader", _FakeChapterLoader(
        chapter_text_by_key={("Book", "Chapter"): "chapter text"}
    ))
    monkeypatch.setattr(server, "build_client", lambda provider, model: _FakeClient("not json"))

    with pytest.raises(HTTPException) as exc_info:
        server.generate_exam(server.GenerateExamRequest(source="Book", chapter="Chapter"))

    assert exc_info.value.status_code == 502
    assert "topic map" in exc_info.value.detail


def test_generate_exam_retries_invalid_topic_maps_and_recovers_on_the_third_attempt(monkeypatch, caplog):
    monkeypatch.setattr(server, "EXAM_BUILDER_ENABLED", True)
    monkeypatch.setitem(server.state, "chapter_loader", _FakeChapterLoader(
        chapter_text_by_key={("Book", "Chapter"): "chapter text"}
    ))
    monkeypatch.setitem(server.state, "exams", {})
    monkeypatch.setitem(server.state, "exam_store", _FakeExamStore())
    topic_map_responses = iter(["not json", "still not json", json.dumps(TOPIC_MAP)])
    topic_map_calls = []

    class TopicMapClient:
        def chat(self, messages, response_format=None):
            topic_map_calls.append((messages, response_format))
            return next(topic_map_responses)

    def fake_build_client(provider, model):
        if provider == server.EXAM_TOPIC_MAP_PROVIDER and model == server.EXAM_TOPIC_MAP_MODEL:
            return TopicMapClient()
        return _FakeClient(json.dumps([_exam_question()]))

    monkeypatch.setattr(server, "build_client", fake_build_client)
    caplog.set_level(logging.INFO, logger="uvicorn.error")

    response = server.generate_exam(server.GenerateExamRequest(source="Book", chapter="Chapter", num_questions=1))

    assert response.questions[0].question == "What is X?"
    assert len(topic_map_calls) == 3
    assert "attempt 1/3 failed; retrying" in caplog.text
    assert "attempt 2/3 failed; retrying" in caplog.text
    assert "failed after 3 attempts" not in caplog.text


def test_generate_exam_returns_an_error_after_three_failed_topic_map_attempts(monkeypatch, caplog):
    monkeypatch.setattr(server, "EXAM_BUILDER_ENABLED", True)
    monkeypatch.setitem(server.state, "chapter_loader", _FakeChapterLoader(
        chapter_text_by_key={("Book", "Chapter"): "chapter text"}
    ))
    topic_map_calls = []

    class InvalidTopicMapClient:
        def chat(self, messages, response_format=None):
            topic_map_calls.append((messages, response_format))
            return "not json"

    monkeypatch.setattr(server, "build_client", lambda provider, model: InvalidTopicMapClient())
    caplog.set_level(logging.INFO, logger="uvicorn.error")

    with pytest.raises(HTTPException) as exc_info:
        server.generate_exam(server.GenerateExamRequest(source="Book", chapter="Chapter"))

    assert exc_info.value.status_code == 502
    assert "Could not parse topic map" in exc_info.value.detail
    assert len(topic_map_calls) == 3
    assert "Exam topic-map generation failed after 3 attempts" in caplog.text


def test_grade_exam_scores_answers_and_returns_full_review(monkeypatch):
    monkeypatch.setattr(server, "EXAM_BUILDER_ENABLED", True)
    exams = {
        "exam-1": {
            "id": "exam-1",
            "source": "Book",
            "chapter": "Chapter",
            "questions": [_exam_question(correct_index=0), _exam_question(correct_index=1)],
            "created_at": "2024-01-01T00:00:00+00:00",
            "answers": None,
            "score": None,
        }
    }
    monkeypatch.setitem(server.state, "exams", exams)
    exam_store = _FakeExamStore()
    monkeypatch.setitem(server.state, "exam_store", exam_store)

    response = server.grade_exam("exam-1", server.GradeExamRequest(answers={"0": 0, "1": 0}))

    assert response.score == 1
    assert response.bloom_levels == list(server.BLOOM_LEVELS)
    assert response.total == 2
    assert response.review[0].given_index == 0
    assert response.review[1].given_index == 0
    assert exams["exam-1"]["score"] == 1
    assert exam_store.saved[-1]["answers"] == {0: 0, 1: 0}


def test_grade_exam_returns_500_without_changing_an_unsaved_result(monkeypatch):
    monkeypatch.setattr(server, "EXAM_BUILDER_ENABLED", True)
    exams = {
        "exam-1": {
            "id": "exam-1",
            "source": "Book",
            "chapter": "Chapter",
            "questions": [_exam_question(correct_index=0)],
            "created_at": "2024-01-01T00:00:00+00:00",
            "answers": None,
            "score": None,
        }
    }
    monkeypatch.setitem(server.state, "exams", exams)
    monkeypatch.setitem(server.state, "exam_store", _FakeExamStore(ExamStoreError("disk full")))

    with pytest.raises(HTTPException) as exc_info:
        server.grade_exam("exam-1", server.GradeExamRequest(answers={"0": 0}))

    assert exc_info.value.status_code == 500
    assert exams["exam-1"]["answers"] is None
    assert exams["exam-1"]["score"] is None


def test_grade_exam_raises_404_for_unknown_exam(monkeypatch):
    monkeypatch.setattr(server, "EXAM_BUILDER_ENABLED", True)
    monkeypatch.setitem(server.state, "exams", {})

    with pytest.raises(HTTPException) as exc_info:
        server.grade_exam("missing", server.GradeExamRequest(answers={}))

    assert exc_info.value.status_code == 404


def test_get_exam_hides_answers_until_graded(monkeypatch):
    monkeypatch.setattr(server, "EXAM_BUILDER_ENABLED", True)
    exams = {
        "exam-1": {
            "id": "exam-1",
            "source": "Book",
            "chapter": "Chapter",
            "questions": [_exam_question()],
            "created_at": "2024-01-01T00:00:00+00:00",
            "answers": None,
            "score": None,
        }
    }
    monkeypatch.setitem(server.state, "exams", exams)

    response = server.get_exam("exam-1")

    assert response.graded is False
    assert response.questions == [
        server.ExamQuestion(section="Evaluation Criteria", question="What is X?", options=["A", "B", "C"])
    ]
    assert response.review is None


def test_get_exam_returns_review_once_graded(monkeypatch):
    monkeypatch.setattr(server, "EXAM_BUILDER_ENABLED", True)
    exams = {
        "exam-1": {
            "id": "exam-1",
            "source": "Book",
            "chapter": "Chapter",
            "questions": [_exam_question()],
            "created_at": "2024-01-01T00:00:00+00:00",
            "answers": {0: 1},
            "score": 1,
        }
    }
    monkeypatch.setitem(server.state, "exams", exams)

    response = server.get_exam("exam-1")

    assert response.graded is True
    assert response.score == 1
    assert response.review[0].given_index == 1
    assert response.review[0].correct_index == 1


def test_get_exam_raises_404_for_unknown_exam(monkeypatch):
    monkeypatch.setattr(server, "EXAM_BUILDER_ENABLED", True)
    monkeypatch.setitem(server.state, "exams", {})

    with pytest.raises(HTTPException) as exc_info:
        server.get_exam("missing")

    assert exc_info.value.status_code == 404


def test_list_exams_sorted_newest_first(monkeypatch):
    monkeypatch.setattr(server, "EXAM_BUILDER_ENABLED", True)
    exams = {
        "a": {
            "id": "a",
            "source": "B1",
            "chapter": "C1",
            "questions": [_exam_question()],
            "created_at": "2024-01-01T00:00:00+00:00",
            "answers": None,
            "score": None,
        },
        "b": {
            "id": "b",
            "source": "B2",
            "chapter": "C2",
            "questions": [_exam_question(), _exam_question()],
            "created_at": "2024-02-01T00:00:00+00:00",
            "answers": {0: 1, 1: 1},
            "score": 2,
        },
    }
    monkeypatch.setitem(server.state, "exams", exams)

    response = server.list_exams()

    assert [e.id for e in response.exams] == ["b", "a"]
    assert response.exams[0].score == 2
    assert response.exams[1].score is None
