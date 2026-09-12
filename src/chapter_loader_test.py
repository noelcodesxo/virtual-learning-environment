import ebooklib
import pytest

import chapter_loader
from chapter_loader import ChapterLoader


class FakeItem:
    def __init__(self, name, content):
        self._name = name
        self._content = content

    def get_type(self):
        return ebooklib.ITEM_DOCUMENT

    def get_name(self):
        return self._name

    def get_content(self):
        return self._content


class FakeTocEntry:
    def __init__(self, href, title):
        self.href = href
        self.title = title


class FakeBook:
    def __init__(self, items, toc, title):
        self.toc = toc
        self._items = items
        self._title = title

    def get_items(self):
        return self._items

    def get_metadata(self, namespace, name):
        if namespace == "DC" and name == "title":
            return [(self._title, {})]
        return []


def _make_book(title, chapters):
    """chapters: list of (chapter_title, body_text) in document order."""
    toc = [FakeTocEntry(f"ch{i}.html", chapter_title) for i, (chapter_title, _) in enumerate(chapters)]
    items = [
        FakeItem(f"ch{i}.html", f"<html><body><p>{body}</p></body></html>".encode())
        for i, (_, body) in enumerate(chapters)
    ]
    return FakeBook(items, toc, title)


@pytest.fixture
def loader(tmp_path, monkeypatch):
    (tmp_path / "book-a.epub").write_bytes(b"")
    (tmp_path / "book-b.epub").write_bytes(b"")

    books_by_path = {
        str(tmp_path / "book-a.epub"): _make_book(
            "Book A", [("1. Intro", "intro text"), ("2. Deep Dive", "deep text")]
        ),
        str(tmp_path / "book-b.epub"): _make_book(
            "Book B", [("Preface", "preface text"), ("1. Only Chapter", "only text")]
        ),
    }

    monkeypatch.setattr(chapter_loader.epub, "read_epub", lambda path: books_by_path[path])
    return ChapterLoader(tmp_path)


def test_list_books_returns_title_and_numbered_chapters(loader):
    books = loader.list_books()
    assert books == [
        {"title": "Book A", "chapters": ["1. Intro", "2. Deep Dive"]},
        {"title": "Book B", "chapters": ["1. Only Chapter"]},
    ]


def test_list_books_excludes_non_numbered_entries_like_preface(loader):
    books = loader.list_books()
    book_b = next(b for b in books if b["title"] == "Book B")
    assert "Preface" not in book_b["chapters"]


def test_load_chapter_text_returns_full_text_for_matching_chapter(loader):
    assert loader.load_chapter_text("Book A", "2. Deep Dive") == "deep text"


def test_load_chapter_text_raises_for_unknown_chapter(loader):
    with pytest.raises(ValueError):
        loader.load_chapter_text("Book A", "9. Nonexistent")


def test_load_chapter_text_raises_for_unknown_book(loader):
    with pytest.raises(ValueError):
        loader.load_chapter_text("Unknown Book", "1. Intro")
