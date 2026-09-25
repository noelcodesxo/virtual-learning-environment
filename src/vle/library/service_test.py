from asyncio import run
import json
from pathlib import Path

import pytest

from vle.library.service import DeleteResult, LibraryError, LibraryService
from vle.rag.indexing import Indexer


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


class _FileTextExtractor:
    extensions = frozenset({".epub"})

    def __init__(self, split_chunks=False, error=None):
        self.split_chunks = split_chunks
        self.error = error
        self.paths = []

    def extract_chunks(self, path: Path) -> list[dict]:
        self.paths.append(path)
        if self.error:
            raise self.error
        texts = path.read_text().split("|") if self.split_chunks else [path.read_text()]
        return [
            {"book": path.stem, "chapter": None, "section": None, "text": text}
            for text in texts
        ]

    def catalog(self, path: Path) -> dict:
        return {"title": path.stem, "chapters": []}


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


def test_synchronize_index_reuses_verified_source_chunks_on_restart(tmp_path):
    extractor = _FileTextExtractor()
    service = _service(tmp_path, extractor)
    service.resources_dir.mkdir()
    (service.resources_dir / "book.epub").write_text("Original source")

    first_index = service.synchronize_index()
    second_index = service.synchronize_index()

    assert extractor.paths == [service.resources_dir / "book.epub"]
    assert second_index == first_index
    assert first_index[0]["source_path"] == "book.epub"
    assert first_index[0]["source_chunk_count"] == 1
    assert first_index[0]["source_ordinal"] == 0
    assert len(first_index[0]["source_sha256"]) == 64


def test_synchronize_index_repairs_partial_and_duplicate_source_ordinals(tmp_path):
    extractor = _FileTextExtractor(split_chunks=True)
    service = _service(tmp_path, extractor)
    service.resources_dir.mkdir()
    (service.resources_dir / "book.epub").write_text("first|second")
    indexed = service.synchronize_index()

    service.index_path.write_text(json.dumps([indexed[0]]))
    repaired = service.synchronize_index()
    service.index_path.write_text(json.dumps(repaired + [repaired[0]]))
    deduplicated = service.synchronize_index()

    assert extractor.paths == [service.resources_dir / "book.epub"] * 3
    assert [chunk["source_ordinal"] for chunk in deduplicated] == [0, 1]
    assert len(deduplicated) == 2


def test_synchronize_index_reextracts_changed_files_and_reweights_bm25_globally(tmp_path):
    extractor = _FileTextExtractor()
    service = _service(tmp_path, extractor)
    service.resources_dir.mkdir()
    first = service.resources_dir / "first.epub"
    second = service.resources_dir / "second.epub"
    first.write_text("alpha")
    second.write_text("bravo")

    initial = service.synchronize_index()
    second.write_text("charlie")
    changed = service.synchronize_index()
    (service.resources_dir / "third.epub").write_text("delta")
    reweighted = service.synchronize_index()

    assert extractor.paths.count(second) == 2
    assert next(chunk for chunk in changed if chunk["source_path"] == "second.epub")["text"] == "charlie"
    assert next(chunk for chunk in initial if chunk["source_path"] == "first.epub")["bm25"]["alpha"] == 0
    assert next(chunk for chunk in reweighted if chunk["source_path"] == "first.epub")["bm25"]["alpha"] > 0


def test_synchronize_index_removes_stale_source_chunks(tmp_path):
    extractor = _FileTextExtractor()
    service = _service(tmp_path, extractor)
    service.resources_dir.mkdir()
    (service.resources_dir / "keep.epub").write_text("keep")
    removed = service.resources_dir / "remove.epub"
    removed.write_text("remove")
    service.synchronize_index()

    removed.unlink()
    indexed = service.synchronize_index()

    assert [chunk["source_path"] for chunk in indexed] == ["keep.epub"]


def test_synchronize_index_rebuilds_legacy_and_corrupt_indexes(tmp_path, caplog):
    extractor = _FileTextExtractor()
    service = _service(tmp_path, extractor)
    service.resources_dir.mkdir()
    (service.resources_dir / "book.epub").write_text("current")
    service.index_path.write_text(json.dumps([{"book": "old", "text": "stale", "bm25": {}}]))

    legacy_rebuilt = service.synchronize_index()
    service.index_path.write_text("not json")
    corrupt_rebuilt = service.synchronize_index()

    assert [chunk["text"] for chunk in legacy_rebuilt] == ["current"]
    assert [chunk["text"] for chunk in corrupt_rebuilt] == ["current"]
    assert extractor.paths == [service.resources_dir / "book.epub"] * 2
    assert "Could not read persisted library index" in caplog.text


def test_synchronize_index_preserves_existing_file_when_extraction_or_save_fails(monkeypatch, tmp_path):
    extractor = _FileTextExtractor()
    service = _service(tmp_path, extractor)
    service.resources_dir.mkdir()
    document = service.resources_dir / "book.epub"
    document.write_text("original")
    service.synchronize_index()
    original_index = service.index_path.read_text()
    document.write_text("changed")
    extractor.error = ValueError("cannot extract")

    with pytest.raises(ValueError, match="cannot extract"):
        service.synchronize_index()
    assert service.index_path.read_text() == original_index

    extractor.error = None
    monkeypatch.setattr(Indexer, "save", lambda *args: (_ for _ in ()).throw(OSError("disk full")))
    with pytest.raises(OSError, match="disk full"):
        service.synchronize_index()
    assert service.index_path.read_text() == original_index


def test_synchronize_index_persists_an_empty_index_for_an_empty_library(tmp_path):
    service = _service(tmp_path, _FileTextExtractor())
    service.index_path.write_text(json.dumps([{"source_path": "gone.epub", "text": "stale"}]))

    assert service.synchronize_index() == []
    assert json.loads(service.index_path.read_text()) == []


def test_initialize_migrates_legacy_resources_once_without_resurrecting_deleted_files(tmp_path):
    legacy_dir = tmp_path / "legacy"
    legacy_dir.mkdir()
    (legacy_dir / "book.epub").write_text("legacy source")
    resources_dir = tmp_path / "data" / "resources"
    marker = tmp_path / "data" / "migration-complete"
    service = LibraryService(
        resources_dir,
        tmp_path / "data" / "index.json",
        [_FileTextExtractor()],
        legacy_resources_dir=legacy_dir,
        migration_marker_path=marker,
    )

    first_index = service.initialize()
    (resources_dir / "book.epub").unlink()
    second_index = service.initialize()

    assert marker.exists()
    assert [chunk["text"] for chunk in first_index] == ["legacy source"]
    assert second_index == []
    assert not (resources_dir / "book.epub").exists()


def test_initialize_legacy_migration_keeps_existing_persistent_files(tmp_path):
    legacy_dir = tmp_path / "legacy"
    legacy_dir.mkdir()
    (legacy_dir / "book.epub").write_text("legacy source")
    resources_dir = tmp_path / "data" / "resources"
    resources_dir.mkdir(parents=True)
    (resources_dir / "book.epub").write_text("persistent source")
    service = LibraryService(
        resources_dir,
        tmp_path / "data" / "index.json",
        [_FileTextExtractor()],
        legacy_resources_dir=legacy_dir,
    )

    indexed = service.initialize()

    assert (resources_dir / "book.epub").read_text() == "persistent source"
    assert [chunk["text"] for chunk in indexed] == ["persistent source"]


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


def test_list_documents_includes_filename_and_format_without_extracting_text(tmp_path):
    epub_extractor = _FakeExtractor()
    pdf_extractor = _PdfExtractor()
    service = LibraryService(tmp_path / "resources", tmp_path / "index.json", [epub_extractor, pdf_extractor])
    service.resources_dir.mkdir()
    (service.resources_dir / "course.epub").write_bytes(b"epub")
    (service.resources_dir / "paper.pdf").write_bytes(b"pdf")

    assert service.list_documents() == [
        {"title": "Uploaded", "chapters": [], "filename": "course.epub", "format": "epub"},
        {"title": "Uploaded", "chapters": ["Entire document"], "filename": "paper.pdf", "format": "pdf"},
    ]
    assert epub_extractor.paths == []
    assert pdf_extractor.paths == []


def test_load_exam_text_includes_every_ordered_pdf_page_in_more_than_twelve_excerpts(tmp_path):
    pdf_extractor = _PdfExtractor([
        {
            "book": "Research paper",
            "chapter": f"Page {number}",
            "section": None,
            "text": f"page marker {number} " + "word " * 330,
        }
        for number in range(1, 16)
    ])
    service = LibraryService(tmp_path / "resources", tmp_path / "index.json", [pdf_extractor])
    service.resources_dir.mkdir()
    (service.resources_dir / "research.pdf").write_bytes(b"pdf")

    exam_text = service.load_exam_text("Research paper", "Entire document")

    assert exam_text.count("Source excerpt") > 12
    page_markers = [exam_text.index(f"Page {number}") for number in range(1, 16)]
    assert page_markers == sorted(page_markers)
    assert all(f"page marker {number}" in exam_text for number in range(1, 16))


def test_load_exam_text_includes_every_ordered_epub_chapter_chunk(tmp_path):
    epub_extractor = _FakeExtractor([
        {
            "book": "Course book",
            "chapter": "1. Start",
            "section": None,
            "text": f"chapter marker {number} " + "word " * 330,
        }
        for number in range(1, 16)
    ] + [
        {"book": "Course book", "chapter": "2. Finish", "section": None, "text": "other chapter"}
    ])
    service = LibraryService(tmp_path / "resources", tmp_path / "index.json", [epub_extractor])
    service.resources_dir.mkdir()
    (service.resources_dir / "course.epub").write_bytes(b"epub")

    exam_text = service.load_exam_text("Course book", "1. Start")

    assert exam_text.count("Source excerpt") > 12
    marker_positions = [exam_text.index(f"chapter marker {number}") for number in range(1, 16)]
    assert marker_positions == sorted(marker_positions)
    assert "other chapter" not in exam_text


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


def test_delete_removes_a_document_and_refreshes_the_index(monkeypatch, tmp_path):
    service = _service(tmp_path)
    service.resources_dir.mkdir()
    document = service.resources_dir / "uploaded.epub"
    document.write_bytes(b"epub bytes")
    indexed = [{"book": "Remaining", "text": "chunk"}]
    monkeypatch.setattr(service, "build_index", lambda: indexed)

    result = run(service.delete("uploaded.epub"))

    assert result == DeleteResult(filename="uploaded.epub", indexed=indexed)
    assert not document.exists()


def test_delete_rejects_missing_or_unsafe_filenames(tmp_path):
    service = _service(tmp_path)

    with pytest.raises(LibraryError, match="was not found") as missing_error:
        run(service.delete("missing.epub"))
    with pytest.raises(LibraryError, match="valid filename") as unsafe_error:
        run(service.delete("../book.epub"))

    assert missing_error.value.status_code == 404
    assert unsafe_error.value.status_code == 400


def test_delete_restores_a_document_when_reindexing_fails(monkeypatch, tmp_path):
    service = _service(tmp_path)
    service.resources_dir.mkdir()
    document = service.resources_dir / "uploaded.epub"
    document.write_bytes(b"epub bytes")
    monkeypatch.setattr(service, "build_index", lambda: (_ for _ in ()).throw(ValueError("index error")))

    with pytest.raises(LibraryError, match="Could not remove") as exc_info:
        run(service.delete("uploaded.epub"))

    assert exc_info.value.status_code == 500
    assert document.read_bytes() == b"epub bytes"
