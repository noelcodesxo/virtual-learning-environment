import ebooklib

from chunker import Chunker


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


class FakeBook:
    def __init__(self, items, toc=None, title=None):
        self.toc = toc or []
        self._items = items
        self._title = title

    def get_items(self):
        return self._items

    def get_metadata(self, namespace, name):
        if namespace == 'DC' and name == 'title' and self._title is not None:
            return [(self._title, {})]
        return []


def test_split_href_splits_filename_and_anchor():
    chunker = Chunker()
    result = chunker.split_href("ch01.html#section-2")
    assert result == ("ch01.html", "section-2")


def test_split_href_returns_none_anchor_when_no_fragment():
    chunker = Chunker()
    result = chunker.split_href("ch01.html")
    assert result == ("ch01.html", None)


def test_merge_blocks_merges_consecutive_same_context_leaves():
    chunker = Chunker()
    leaves = [
        ("Hello", "Chapter 1", None),
        ("world", "Chapter 1", None),
    ]
    result = chunker.merge_blocks(leaves)
    assert result == [("Hello world", "Chapter 1", None)]


def test_merge_blocks_keeps_different_context_leaves_separate():
    chunker = Chunker()
    leaves = [
        ("Hello", "Chapter 1", None),
        ("Goodbye", "Chapter 2", None),
    ]
    result = chunker.merge_blocks(leaves)
    assert result == [("Hello", "Chapter 1", None), ("Goodbye", "Chapter 2", None)]


def test_chunker_processer_appends_short_text_as_single_chunk():
    chunker = Chunker()
    chunker.chunker_processer("short text", "Chapter 1", "Section 1")
    assert chunker.chunks == [{"text": "short text", "chapter": "Chapter 1", "section": "Section 1"}]


def test_chunker_processer_keeps_unsplittable_word_as_single_oversized_chunk():
    chunker = Chunker()
    text = "a" * (Chunker.CHUNK_SIZE + 50)
    chunker.chunker_processer(text, "Chapter 1", None)
    assert chunker.chunks == [{"text": text, "chapter": "Chapter 1", "section": None}]


def test_chunker_processer_splits_by_paragraph_before_falling_back_to_sentence():
    chunker = Chunker()
    para1 = "A" * 150
    para2 = "B" * 150
    text = para1 + "\n\n" + para2
    chunker.chunker_processer(text, "Chapter 1", None)
    assert chunker.chunks == [
        {"text": para1, "chapter": "Chapter 1", "section": None},
        {"text": para2, "chapter": "Chapter 1", "section": None},
    ]


def test_chunker_processer_splits_by_sentence_when_paragraph_too_long():
    chunker = Chunker()
    sentence1 = "A" * 90 + "."
    sentence2 = "B" * 90 + "."
    sentence3 = "C" * 90 + "."
    text = " ".join([sentence1, sentence2, sentence3])
    chunker.chunker_processer(text, "Chapter 1", None)
    assert chunker.chunks == [
        {"text": sentence1, "chapter": "Chapter 1", "section": None},
        {"text": sentence2, "chapter": "Chapter 1", "section": None},
        {"text": sentence3, "chapter": "Chapter 1", "section": None},
    ]


def test_chunker_processer_splits_oversized_sentence_on_word_boundaries_with_overlap():
    chunker = Chunker()
    words = [f"word{i}" for i in range(60)]
    text = " ".join(words)
    chunker.chunker_processer(text, "Chapter 1", None)

    assert len(chunker.chunks) > 1
    for chunk in chunker.chunks:
        assert len(chunk["text"]) <= Chunker.CHUNK_SIZE
        for token in chunk["text"].split():
            assert token in words

    for prev, nxt in zip(chunker.chunks, chunker.chunks[1:]):
        assert nxt["text"].split()[0] in prev["text"].split()


def test_chunker_processer_skips_blank_text():
    chunker = Chunker()
    chunker.chunker_processer("   ", "Chapter 1", None)
    assert chunker.chunks == []


def test_process_book_separates_paragraphs_with_blank_line():
    book = FakeBook(
        [FakeItem("ch1.html", b"<html><body><p>first para</p><p>second para</p></body></html>")],
        title="My Book",
    )
    chunker = Chunker()
    result = chunker.process_book(book)
    assert result == [{"text": "first para\n\nsecond para", "chapter": None, "section": None, "book": "My Book"}]


def test_process_book_does_not_break_paragraph_for_inline_tags():
    book = FakeBook(
        [FakeItem("ch1.html", b"<html><body><p>hello <em>world</em> foo</p></body></html>")],
        title="My Book",
    )
    chunker = Chunker()
    result = chunker.process_book(book)
    assert result == [{"text": "hello world foo", "chapter": None, "section": None, "book": "My Book"}]


def test_process_book_returns_chunks_for_a_single_book():
    book = FakeBook(
        [FakeItem("ch1.html", b"<html><body><p>hello world</p></body></html>")],
        title="My Book",
    )
    chunker = Chunker()
    result = chunker.process_book(book)
    assert result == [{"text": "hello world", "chapter": None, "section": None, "book": "My Book"}]


def test_process_book_tags_chunks_with_none_when_book_has_no_title():
    book = FakeBook([FakeItem("ch1.html", b"<html><body><p>hello world</p></body></html>")])
    chunker = Chunker()
    result = chunker.process_book(book)
    assert result == [{"text": "hello world", "chapter": None, "section": None, "book": None}]


def test_process_book_resets_chunks_between_calls():
    chunker = Chunker()
    book1 = FakeBook([FakeItem("a.html", b"<html><body><p>first</p></body></html>")], title="Book 1")
    book2 = FakeBook([FakeItem("b.html", b"<html><body><p>second</p></body></html>")], title="Book 2")
    chunker.process_book(book1)
    result2 = chunker.process_book(book2)
    assert result2 == [{"text": "second", "chapter": None, "section": None, "book": "Book 2"}]


def test_process_books_returns_one_chunk_list_per_book():
    book1 = FakeBook([FakeItem("a.html", b"<html><body><p>first</p></body></html>")], title="Book 1")
    book2 = FakeBook([FakeItem("b.html", b"<html><body><p>second</p></body></html>")], title="Book 2")
    chunker = Chunker()
    result = chunker.process_books([book1, book2])
    assert result == [
        [{"text": "first", "chapter": None, "section": None, "book": "Book 1"}],
        [{"text": "second", "chapter": None, "section": None, "book": "Book 2"}],
    ]
