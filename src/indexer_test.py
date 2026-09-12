import json
import math

import pytest

from indexer import Indexer


def test_index_gives_negative_score_for_term_in_every_chunk():
    indexer = Indexer()
    chunks = [
        {"text": "cat dog", "chapter": "Ch1", "section": "S1"},
        {"text": "dog bird", "chapter": "Ch1", "section": "S2"},
    ]
    result = indexer.index(chunks)
    # BM25's IDF goes negative once a term appears in more than half the
    # chunks; "dog" appears in both of the 2 chunks here (df=2, N=2).
    expected_idf = math.log((2 - 2 + 0.5) / (2 + 0.5))
    assert result[0]["bm25"]["dog"] == pytest.approx(expected_idf)
    assert result[1]["bm25"]["dog"] == pytest.approx(expected_idf)


def test_index_gives_higher_score_to_term_unique_to_one_chunk():
    indexer = Indexer()
    chunks = [
        {"text": "cat dog", "chapter": "Ch1", "section": "S1"},
        {"text": "dog bird", "chapter": "Ch1", "section": "S2"},
    ]
    result = indexer.index(chunks)
    unique_idf = math.log((2 - 1 + 0.5) / (1 + 0.5))
    common_idf = math.log((2 - 2 + 0.5) / (2 + 0.5))
    assert result[0]["bm25"]["cat"] == pytest.approx(unique_idf)
    assert result[1]["bm25"]["bird"] == pytest.approx(unique_idf)
    assert result[0]["bm25"]["cat"] > result[0]["bm25"]["dog"]
    assert unique_idf > common_idf


def test_index_weights_by_term_frequency_within_a_chunk():
    indexer = Indexer()
    # A third chunk is needed here so "cat" (unique to chunk 0) doesn't land
    # exactly on BM25's zero-IDF crossover (df == N/2), which would mask the
    # term-frequency weighting this test is meant to demonstrate.
    chunks = [
        {"text": "cat cat dog", "chapter": "Ch1", "section": "S1"},
        {"text": "dog bird", "chapter": "Ch1", "section": "S2"},
        {"text": "dog fish", "chapter": "Ch1", "section": "S3"},
    ]
    result = indexer.index(chunks)

    k1, b = Indexer._K1, Indexer._B
    average_chunk_length = (3 + 2 + 2) / 3
    expected_tf = 2 * (k1 + 1) / (2 + k1) * (1 - b + b * 3 / average_chunk_length)
    expected_idf = math.log((3 - 1 + 0.5) / (1 + 0.5))
    assert result[0]["bm25"]["cat"] == pytest.approx(expected_tf * expected_idf)


def test_index_handles_single_chunk():
    indexer = Indexer()
    chunks = [{"text": "cat dog", "chapter": "Ch1", "section": "S1", "book": "Book 1"}]
    result = indexer.index(chunks)
    # With a single chunk, every term has df=1 and N=1, so BM25's IDF is
    # log((1-1+0.5)/(1+0.5)) = log(1/3), not zero.
    expected_idf = math.log((1 - 1 + 0.5) / (1 + 0.5))
    assert result == [
        {
            "book": "Book 1",
            "chapter": "Ch1",
            "section": "S1",
            "text": "cat dog",
            "bm25": {
                "cat": pytest.approx(expected_idf),
                "dog": pytest.approx(expected_idf),
            },
        }
    ]


def test_index_handles_empty_text_chunk():
    indexer = Indexer()
    chunks = [
        {"text": "", "chapter": "Ch1", "section": None},
        {"text": "cat", "chapter": "Ch2", "section": "S1"},
    ]
    result = indexer.index(chunks)
    assert result[0]["bm25"] == {}


def test_index_keeps_each_chunk_chapter_and_section():
    indexer = Indexer()
    chunks = [
        {"text": "cat dog", "chapter": "Ch1", "section": "S1", "book": "Book 1"},
        {"text": "dog bird", "chapter": "Ch2", "section": None, "book": "Book 1"},
    ]
    result = indexer.index(chunks)
    assert result[0]["chapter"] == "Ch1"
    assert result[0]["section"] == "S1"
    assert result[1]["chapter"] == "Ch2"
    assert result[1]["section"] is None


def test_index_keeps_each_chunk_book():
    indexer = Indexer()
    chunks = [
        {"text": "cat dog", "chapter": "Ch1", "section": "S1", "book": "Book 1"},
        {"text": "dog bird", "chapter": "Ch1", "section": "S2", "book": "Book 2"},
    ]
    result = indexer.index(chunks)
    assert result[0]["book"] == "Book 1"
    assert result[1]["book"] == "Book 2"


def test_save_writes_indexed_data_as_json(tmp_path):
    indexer = Indexer()
    indexed = [{"chapter": "Ch1", "section": "S1", "bm25": {"cat": 0.5}}]
    output_path = tmp_path / "index.json"

    indexer.save(indexed, output_path)

    with open(output_path) as f:
        assert json.load(f) == indexed
