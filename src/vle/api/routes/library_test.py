from asyncio import run

import pytest
from fastapi import HTTPException

from vle.api.routes import library
from vle.library.service import DeleteResult, LibraryError, UploadResult


class _Request:
    def __init__(self):
        self.headers = {}
        self.app = type("App", (), {"state": type("State", (), {"index": []})()})()

    async def stream(self):
        yield b"document"


class _LibraryService:
    async def upload(self, filename, chunks, content_length):
        assert [chunk async for chunk in chunks] == [b"document"]
        return UploadResult(filename=filename, indexed=[{"text": "indexed"}])

    async def delete(self, filename):
        return DeleteResult(filename=filename, indexed=[])

    def list_documents(self):
        return [{"title": "Book", "filename": "book.epub", "format": "epub", "chapters": ["1. One"]}]

    def list_books(self):
        return [{"title": "Book", "chapters": ["1. One"]}]


def test_library_routes_preserve_upload_list_delete_and_books_contracts():
    service = _LibraryService()
    request = _Request()

    uploaded = run(library.upload_library_file(request, "book.epub", service))
    documents = library.list_library_documents(service)
    deleted = run(library.delete_library_file(request, "book.epub", service))
    books = library.list_books(service)

    assert uploaded.model_dump() == {"filename": "book.epub", "indexed_chunks": 1}
    assert request.app.state.index == []
    assert documents.model_dump() == {"documents": [{"title": "Book", "filename": "book.epub", "format": "epub", "chapters": ["1. One"]}]}
    assert deleted.model_dump() == {"filename": "book.epub", "indexed_chunks": 0}
    assert books.model_dump() == {"books": [{"title": "Book", "chapters": ["1. One"]}]}


def test_library_routes_keep_library_error_statuses():
    class _FailingLibrary:
        async def delete(self, filename):
            raise LibraryError(404, "Document book.epub was not found in the library.")

    with pytest.raises(HTTPException) as error:
        run(library.delete_library_file(_Request(), "book.epub", _FailingLibrary()))

    assert error.value.status_code == 404
