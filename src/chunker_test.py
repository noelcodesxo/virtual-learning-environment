from chunker import Chunker


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


def test_chunker_processer_splits_long_text_into_chunk_size_pieces():
    chunker = Chunker()
    text = "a" * (Chunker.CHUNK_SIZE + 50)
    chunker.chunker_processer(text, "Chapter 1", None)
    assert len(chunker.chunks) == 2
    assert chunker.chunks[0]["text"] == text[:Chunker.CHUNK_SIZE]
    assert chunker.chunks[1]["text"] == text[Chunker.CHUNK_SIZE:]


def test_chunker_processer_skips_blank_text():
    chunker = Chunker()
    chunker.chunker_processer("   ", "Chapter 1", None)
    assert chunker.chunks == []
