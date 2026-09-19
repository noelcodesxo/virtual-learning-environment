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


class _LegacyOutlineReader(_FakeReader):
    @property
    def outline(self):
        raise AttributeError("outline is unavailable in this reader version")

    @property
    def outlines(self):
        return self._legacy_outlines

    def __init__(self, pages, outlines):
        self.pages = pages
        self._legacy_outlines = outlines


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


def test_pdf_extractor_supports_legacy_outline_reader_api(monkeypatch, tmp_path):
    reader = _LegacyOutlineReader(
        [_FakePage("intro")],
        [_FakeDestination("1. Introduction", 0)],
    )
    monkeypatch.setattr(document_extractors, "PdfReader", lambda path: reader)

    assert PdfExtractor().catalog(tmp_path / "research-paper.pdf") == {
        "title": "research-paper",
        "chapters": ["1. Introduction"],
    }


def test_pdf_extractor_uses_a_printed_table_of_contents_when_bookmarks_are_missing(monkeypatch, tmp_path):
    pages = [_FakePage("") for _ in range(31)]
    pages[6] = _FakePage(
        "6\nContents\nChapter 1. Basics 10\n1.1. First Topic 10\nChapter 2. Methods 20\n"
    )
    pages[7] = _FakePage("7\nChapter 3. Results 30\n")
    pages[10] = _FakePage("basics")
    pages[20] = _FakePage("methods")
    pages[30] = _FakePage("results")
    monkeypatch.setattr(document_extractors, "PdfReader", lambda path: _FakeReader(pages))

    extractor = PdfExtractor()
    catalog = extractor.catalog(tmp_path / "book.pdf")
    chunks = extractor.extract_chunks(tmp_path / "book.pdf")

    assert catalog == {
        "title": "book",
        "chapters": ["Chapter 1. Basics", "Chapter 2. Methods", "Chapter 3. Results"],
    }
    assert [chunk for chunk in chunks if chunk["text"] in {"basics", "methods", "results"}] == [
        {"text": "basics", "chapter": "Chapter 1. Basics", "section": "1.1. First Topic", "book": "book"},
        {"text": "methods", "chapter": "Chapter 2. Methods", "section": None, "book": "book"},
        {"text": "results", "chapter": "Chapter 3. Results", "section": None, "book": "book"},
    ]


def test_pdf_extractor_parses_unnumbered_academic_toc_entries(monkeypatch, tmp_path):
    pages = [_FakePage("") for _ in range(13)]
    pages[0] = _FakePage(
        "Contents\nAbstract 1\n1 Introduction 2\n2 Related Work 4\n"
        "2.1 Prior Studies 5\n3 Methodology 8\nReferences 12\n"
    )
    pages[1] = _FakePage("abstract")
    pages[2] = _FakePage("introduction")
    pages[4] = _FakePage("related work")
    pages[5] = _FakePage("prior studies")
    pages[8] = _FakePage("methodology")
    pages[12] = _FakePage("references")
    monkeypatch.setattr(document_extractors, "PdfReader", lambda path: _FakeReader(pages))

    extractor = PdfExtractor()

    assert extractor.catalog(tmp_path / "paper.pdf") == {
        "title": "paper",
        "chapters": ["Abstract", "1 Introduction", "2 Related Work", "3 Methodology", "References"],
    }
    chunks = extractor.extract_chunks(tmp_path / "paper.pdf")
    assert [chunk for chunk in chunks if chunk["text"] in {"abstract", "prior studies", "references"}] == [
        {"text": "abstract", "chapter": "Abstract", "section": None, "book": "paper"},
        {"text": "prior studies", "chapter": "2 Related Work", "section": "2.1 Prior Studies", "book": "paper"},
        {"text": "references", "chapter": "References", "section": None, "book": "paper"},
    ]


def test_pdf_extractor_recovers_chapters_from_section_only_bookmarks(monkeypatch, tmp_path):
    pages = [_FakePage("") for _ in range(24)]
    pages[2] = _FakePage(
        "Contents\n1. Systems\n1.1 Overview 5\n2. Networking\n2.1 Overview 10\n"
    )
    pages[12] = _FakePage("1.1 Overview\nsystems body")
    pages[17] = _FakePage("2.1 Overview\nnetworking body")
    reader = _FakeReader(
        pages,
        [[_FakeDestination("1.1 Overview", 5)], [_FakeDestination("2.1 Overview", 10)]],
    )
    monkeypatch.setattr(document_extractors, "PdfReader", lambda path: reader)

    extractor = PdfExtractor()

    assert extractor.catalog(tmp_path / "book.pdf") == {
        "title": "book",
        "chapters": ["1. Systems", "2. Networking"],
    }
    chunks = extractor.extract_chunks(tmp_path / "book.pdf")
    assert [chunk for chunk in chunks if chunk["text"].endswith("body")] == [
        {"text": "1.1 Overview\nsystems body", "chapter": "1. Systems", "section": "1.1 Overview", "book": "book"},
        {"text": "2.1 Overview\nnetworking body", "chapter": "2. Networking", "section": "2.1 Overview", "book": "book"},
    ]


def test_pdf_extractor_keeps_unnumbered_toc_labels_nested_under_chapters(monkeypatch, tmp_path):
    pages = [_FakePage("") for _ in range(16)]
    pages[1] = _FakePage(
        "Contents\n1. Systems\n1.1 Overview 5\nNested label 6\n2. Networking\n2.1 Overview 10\n"
    )
    pages[8] = _FakePage("1.1 Overview\nsystems body")
    pages[13] = _FakePage("2.1 Overview\nnetworking body")
    monkeypatch.setattr(document_extractors, "PdfReader", lambda path: _FakeReader(pages))

    assert PdfExtractor().catalog(tmp_path / "book.pdf") == {
        "title": "book",
        "chapters": ["1. Systems", "2. Networking"],
    }
