from pathlib import Path

import pytest

import document_extractors
from document_extractors import PdfExtractor


class _FakePage:
    def __init__(self, text):
        self.text = text

    def extract_text(self):
        return self.text


class _FakeReader:
    def __init__(self, pages):
        self.pages = pages


def test_pdf_extractor_creates_page_labeled_chunks(monkeypatch, tmp_path):
    monkeypatch.setattr(
        document_extractors,
        "PdfReader",
        lambda path: _FakeReader([_FakePage("first page"), _FakePage("second page")]),
    )

    chunks = PdfExtractor().extract_chunks(tmp_path / "course-notes.pdf")

    assert chunks == [
        {"text": "first page", "chapter": "Page 1", "section": None, "book": "course-notes"},
        {"text": "second page", "chapter": "Page 2", "section": None, "book": "course-notes"},
    ]


def test_pdf_extractor_rejects_documents_without_extractable_text(monkeypatch, tmp_path):
    monkeypatch.setattr(document_extractors, "PdfReader", lambda path: _FakeReader([_FakePage("")]))

    with pytest.raises(ValueError, match="extractable text"):
        PdfExtractor().extract_chunks(Path(tmp_path / "scan.pdf"))


def test_pdf_catalog_does_not_open_the_pdf(monkeypatch, tmp_path):
    monkeypatch.setattr(document_extractors, "PdfReader", lambda path: pytest.fail("should not open PDF"))

    catalog = PdfExtractor().catalog(tmp_path / "research-paper.pdf")

    assert catalog == {"title": "research-paper", "chapters": ["Entire document"]}
