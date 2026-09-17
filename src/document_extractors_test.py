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
    def __init__(self, pages, outline=None):
        self.pages = pages
        self.outline = outline or []

    @staticmethod
    def get_destination_page_number(destination):
        return destination.page_number


class _FakeDestination:
    def __init__(self, title, page_number):
        self.title = title
        self.page_number = page_number


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
    monkeypatch.setattr(document_extractors, "PdfReader", lambda path: _FakeReader([]))

    catalog = PdfExtractor().catalog(tmp_path / "research-paper.pdf")

    assert catalog == {"title": "research-paper", "chapters": ["Entire document"]}


def test_pdf_extractor_maps_outline_chapters_and_sections_to_page_chunks(monkeypatch, tmp_path):
    first = _FakeDestination("1. Introduction", 0)
    section = _FakeDestination("Background", 1)
    second = _FakeDestination("2. Methods", 2)
    reader = _FakeReader(
        [_FakePage("intro"), _FakePage("background"), _FakePage("methods")],
        [first, [section], second],
    )
    monkeypatch.setattr(document_extractors, "PdfReader", lambda path: reader)

    chunks = PdfExtractor().extract_chunks(tmp_path / "research-paper.pdf")

    assert chunks == [
        {"text": "intro", "chapter": "1. Introduction", "section": None, "book": "research-paper"},
        {"text": "background", "chapter": "1. Introduction", "section": "Background", "book": "research-paper"},
        {"text": "methods", "chapter": "2. Methods", "section": None, "book": "research-paper"},
    ]
    assert PdfExtractor().catalog(tmp_path / "research-paper.pdf") == {
        "title": "research-paper",
        "chapters": ["1. Introduction", "2. Methods"],
    }
