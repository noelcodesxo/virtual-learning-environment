from asyncio import run
from pathlib import Path

import pytest

from library import LibraryError, LibraryService


class _FakeExtractor:
    extensions = frozenset({".epub"})

    def __init__(self, chunks=None, error=None):
        self.chunks = chunks or [{"book": "Uploaded", "chapter": None, "section": None, "text": "source text"}]
        self.error = error
        self.paths = []
        self.catalog_paths = []

    def extract_chunks(self, path: Path) -> list[dict]:
        self.paths.append(path)
        if self.error:
            raise self.error
        return [chunk.copy() for chunk in self.chunks]

    def catalog(self, path: Path) -> dict:
        self.catalog_paths.append(path)
        title = self.chunks[0].get("book") or path.stem
        if ".epub" in self.extensions:
            chapters = list(dict.fromkeys(
                chunk["chapter"]
                for chunk in self.chunks
                if chunk.get("chapter") and chunk["chapter"].startswith(tuple(str(i) + "." for i in range(10)))
            ))
        else:
            chapters = ["Entire document"]
        return {"title": title, "chapters": chapters}


class _TextExtractor(_FakeExtractor):
    extensions = frozenset({".txt"})


class _PdfExtractor(_FakeExtractor):
    extensions = frozenset({".pdf"})


class _FakeUpload:
    def __init__(self, chunks):
        self.chunks = chunks
        self.was_streamed = False

    async def stream(self):
        self.was_streamed = True
        for chunk in self.chunks:
            yield chunk


def _service(tmp_path, extractor=None, **kwargs):
    return LibraryService(tmp_path / "resources", tmp_path / "index.json", [extractor or _FakeExtractor()], **kwargs)


def test_build_index_uses_registered_extractors_for_supported_documents(tmp_path):
    extractor = _FakeExtractor()
    service = _service(tmp_path, extractor)
    service.resources_dir.mkdir()
    (service.resources_dir / "book.epub").write_bytes(b"epub")
    (service.resources_dir / "ignored.pdf").write_bytes(b"pdf")

    indexed = service.build_index()

    assert extractor.paths == [service.resources_dir / "book.epub"]
    assert indexed[0]["text"] == "source text"
    assert service.index_path.exists()


def test_upload_saves_a_supported_document_and_refreshes_the_index(monkeypatch, tmp_path):
    service = _service(tmp_path)
    indexed = [{"book": "Uploaded", "text": "chunk"}]
    monkeypatch.setattr(service, "build_index", lambda: indexed)

    result = run(service.upload("uploaded.epub", _FakeUpload([b"epub bytes"]).stream()))

    assert result.filename == "uploaded.epub"
    assert result.indexed == indexed
    assert (service.resources_dir / "uploaded.epub").read_bytes() == b"epub bytes"


def test_upload_rejects_unsupported_extensions(tmp_path):
    service = LibraryService(tmp_path / "resources", tmp_path / "index.json")

    with pytest.raises(LibraryError, match="Only EPUB, PDF files are supported") as exc_info:
        run(service.upload("notes.txt", _FakeUpload([b"text"]).stream()))

    assert exc_info.value.status_code == 415


def test_upload_accepts_extensions_registered_by_a_new_extractor(monkeypatch, tmp_path):
    service = _service(tmp_path, _TextExtractor())
    indexed = [{"book": "Note", "text": "chunk"}]
    monkeypatch.setattr(service, "build_index", lambda: indexed)

    result = run(service.upload("note.txt", _FakeUpload([b"plain text"]).stream()))

    assert result.filename == "note.txt"
    assert (service.resources_dir / "note.txt").read_bytes() == b"plain text"


def test_list_books_and_load_chapter_text_support_full_document_exams(tmp_path):
    pdf_extractor = _PdfExtractor([
        {"book": "Research paper", "chapter": "Page 1", "section": None, "text": "first page"},
        {"book": "Research paper", "chapter": "Page 2", "section": None, "text": "second page"},
    ])
    service = LibraryService(tmp_path / "resources", tmp_path / "index.json", [pdf_extractor])
    service.resources_dir.mkdir()
    (service.resources_dir / "research.pdf").write_bytes(b"pdf")

    assert service.list_books() == [{"title": "Research paper", "chapters": ["Entire document"]}]
    assert service.load_chapter_text("Research paper", "Entire document") == "first page\n\nsecond page"


def test_list_books_uses_lightweight_catalogs_without_extracting_document_text(tmp_path):
    pdf_extractor = _PdfExtractor(error=AssertionError("should not extract PDF text"))
    service = LibraryService(tmp_path / "resources", tmp_path / "index.json", [pdf_extractor])
    service.resources_dir.mkdir()
    (service.resources_dir / "research.pdf").write_bytes(b"pdf")

    assert service.list_books() == [{"title": "Uploaded", "chapters": ["Entire document"]}]
    assert pdf_extractor.paths == []
    assert pdf_extractor.catalog_paths == [service.resources_dir / "research.pdf"]


def test_list_books_caches_unchanged_document_catalogs(tmp_path):
    extractor = _FakeExtractor()
    service = _service(tmp_path, extractor)
    service.resources_dir.mkdir()
    (service.resources_dir / "book.epub").write_bytes(b"epub")

    assert service.list_books() == service.list_books()
    assert extractor.catalog_paths == [service.resources_dir / "book.epub"]


def test_load_exam_text_uses_bounded_evenly_distributed_document_excerpts(tmp_path):
    pdf_extractor = _PdfExtractor([
        {"book": "Research paper", "chapter": f"Page {number}", "section": None, "text": f"page {number} " + "word " * 280}
        for number in range(1, 5)
    ])
    service = LibraryService(tmp_path / "resources", tmp_path / "index.json", [pdf_extractor])
    service.resources_dir.mkdir()
    (service.resources_dir / "research.pdf").write_bytes(b"pdf")

    exam_text = service.load_exam_text("Research paper", "Entire document", num_questions=2)

    assert exam_text.count("Source excerpt") == 2
    assert "Page 1" in exam_text
    assert "Page 4" in exam_text
    assert "Page 2" not in exam_text


def test_load_exam_text_chunks_epub_chapters_with_the_same_limits(tmp_path):
    epub_extractor = _FakeExtractor([
        {"book": "Course book", "chapter": "1. Start", "section": None, "text": f"part {number} " + "word " * 280}
        for number in range(1, 5)
    ])
    service = LibraryService(tmp_path / "resources", tmp_path / "index.json", [epub_extractor])
    service.resources_dir.mkdir()
    (service.resources_dir / "course.epub").write_bytes(b"epub")

    exam_text = service.load_exam_text("Course book", "1. Start", num_questions=2)

    assert exam_text.count("Source excerpt") == 2
    assert "part 1" in exam_text
    assert "part 4" in exam_text


def test_list_books_preserves_epub_chapters(tmp_path):
    epub_extractor = _FakeExtractor([
        {"book": "Course book", "chapter": "Preface", "section": None, "text": "preface"},
        {"book": "Course book", "chapter": "1. Start", "section": None, "text": "chapter one"},
        {"book": "Course book", "chapter": "2. Finish", "section": None, "text": "chapter two"},
    ])
    service = LibraryService(tmp_path / "resources", tmp_path / "index.json", [epub_extractor])
    service.resources_dir.mkdir()
    (service.resources_dir / "course.epub").write_bytes(b"epub")

    assert service.list_books() == [{"title": "Course book", "chapters": ["1. Start", "2. Finish"]}]
    assert service.load_chapter_text("Course book", "2. Finish") == "chapter two"


def test_upload_rejects_a_duplicate_after_consuming_the_request_stream(monkeypatch, tmp_path):
    service = _service(tmp_path)
    service.resources_dir.mkdir()
    destination = service.resources_dir / "uploaded.epub"
    destination.write_bytes(b"existing epub")
    monkeypatch.setattr(service, "build_index", lambda: pytest.fail("should not rebuild the index"))
    upload = _FakeUpload([b"new epub"])

    with pytest.raises(LibraryError, match="already exists") as exc_info:
        run(service.upload("uploaded.epub", upload.stream()))

    assert exc_info.value.status_code == 409
    assert upload.was_streamed
    assert destination.read_bytes() == b"existing epub"


def test_upload_removes_an_invalid_document(monkeypatch, tmp_path):
    service = _service(tmp_path)
    monkeypatch.setattr(service, "build_index", lambda: (_ for _ in ()).throw(ValueError("invalid epub")))

    with pytest.raises(LibraryError, match="Could not read this EPUB file") as exc_info:
        run(service.upload("bad.epub", _FakeUpload([b"not an epub"]).stream()))

    assert exc_info.value.status_code == 422
    assert not (service.resources_dir / "bad.epub").exists()


def test_upload_rejects_empty_and_oversized_documents(tmp_path):
    service = _service(tmp_path, max_upload_bytes=3)

    with pytest.raises(LibraryError, match="empty") as empty_error:
        run(service.upload("empty.epub", _FakeUpload([]).stream()))
    with pytest.raises(LibraryError, match="0 MB or smaller") as size_error:
        run(service.upload("large.epub", _FakeUpload([b"four"]).stream()))

    assert empty_error.value.status_code == 400
    assert size_error.value.status_code == 413
    assert not list((tmp_path / "resources").glob(".*.upload"))
