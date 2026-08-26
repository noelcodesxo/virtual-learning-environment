import json
import math

import pytest

from indexer import Indexer


def test_index_gives_zero_score_for_term_in_every_chunk():
    indexer = Indexer()
    chunks = [
        {"text": "cat dog", "chapter": "Ch1", "section": "S1"},
        {"text": "dog bird", "chapter": "Ch1", "section": "S2"},
    ]
    result = indexer.index(chunks)
    assert result[0]["tf_idf"]["dog"] == pytest.approx(0.0)
    assert result[1]["tf_idf"]["dog"] == pytest.approx(0.0)


def test_index_gives_higher_score_to_term_unique_to_one_chunk():
    indexer = Indexer()
    chunks = [
        {"text": "cat dog", "chapter": "Ch1", "section": "S1"},
        {"text": "dog bird", "chapter": "Ch1", "section": "S2"},
    ]
    result = indexer.index(chunks)
    expected_idf = math.log(2 / 1)
    assert result[0]["tf_idf"]["cat"] == pytest.approx(0.5 * expected_idf)
    assert result[1]["tf_idf"]["bird"] == pytest.approx(0.5 * expected_idf)


def test_index_weights_by_term_frequency_within_a_chunk():
    indexer = Indexer()
    chunks = [
        {"text": "cat cat dog", "chapter": "Ch1", "section": "S1"},
        {"text": "dog bird", "chapter": "Ch1", "section": "S2"},
    ]
    result = indexer.index(chunks)
    expected_idf = math.log(2 / 1)
    assert result[0]["tf_idf"]["cat"] == pytest.approx((2 / 3) * expected_idf)


def test_index_handles_single_chunk():
    indexer = Indexer()
    chunks = [{"text": "cat dog", "chapter": "Ch1", "section": "S1", "book": "Book 1"}]
    result = indexer.index(chunks)
    assert result == [
        {
            "book": "Book 1",
            "chapter": "Ch1",
            "section": "S1",
            "tf_idf": {"cat": pytest.approx(0.0), "dog": pytest.approx(0.0)},
        }
    ]


def test_index_handles_empty_text_chunk():
    indexer = Indexer()
    chunks = [
        {"text": "", "chapter": "Ch1", "section": None},
        {"text": "cat", "chapter": "Ch2", "section": "S1"},
    ]
    result = indexer.index(chunks)
    assert result[0]["tf_idf"] == {}


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
    indexed = [{"chapter": "Ch1", "section": "S1", "tf_idf": {"cat": 0.5}}]
    output_path = tmp_path / "index.json"

    indexer.save(indexed, output_path)

    with open(output_path) as f:
        assert json.load(f) == indexed
