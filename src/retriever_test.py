from retriever import Retriever


def test_search_ranks_entries_by_cosine_similarity_to_query():
    retriever = Retriever()
    index = [
        {"book": "B", "chapter": "Ch1", "section": None, "text": "low match",
         "tf_idf": {"cat": 0.1}},
        {"book": "B", "chapter": "Ch2", "section": None, "text": "high match",
         "tf_idf": {"cat": 0.9, "dog": 0.9}},
    ]
    results = retriever.search("cat dog", index)
    assert [r["text"] for r in results] == ["high match", "low match"]


def test_search_excludes_entries_with_no_matching_terms():
    retriever = Retriever()
    index = [
        {"book": "B", "chapter": "Ch1", "section": None, "text": "about cats",
         "tf_idf": {"cat": 0.5}},
        {"book": "B", "chapter": "Ch2", "section": None, "text": "about birds",
         "tf_idf": {"bird": 0.5}},
    ]
    results = retriever.search("cat", index)
    assert [r["text"] for r in results] == ["about cats"]


def test_search_limits_results_to_top_10():
    retriever = Retriever()
    index = [
        {"book": "B", "chapter": f"Ch{i}", "section": None, "text": f"chunk {i}",
         "tf_idf": {"cat": 1.0 / (i + 1)}}
        for i in range(15)
    ]
    results = retriever.search("cat", index)
    assert len(results) == 10


def test_search_limits_results_to_given_top_k():
    retriever = Retriever()
    index = [
        {"book": "B", "chapter": f"Ch{i}", "section": None, "text": f"chunk {i}",
         "tf_idf": {"cat": 1.0 / (i + 1)}}
        for i in range(15)
    ]
    results = retriever.search("cat", index, top_k=3)
    assert len(results) == 3


def test_search_preprocesses_query_like_chunks():
    retriever = Retriever()
    index = [
        {"book": "B", "chapter": "Ch1", "section": None, "text": "about cats",
         "tf_idf": {"cat": 0.5}},
    ]
    results = retriever.search("The Cat!", index)
    assert [r["text"] for r in results] == ["about cats"]


def test_search_returns_empty_list_for_query_with_no_terms():
    retriever = Retriever()
    index = [
        {"book": "B", "chapter": "Ch1", "section": None, "text": "about cats",
         "tf_idf": {"cat": 0.5}},
    ]
    results = retriever.search("the and", index)
    assert results == []


def test_search_includes_score_in_each_result():
    retriever = Retriever()
    index = [
        {"book": "B", "chapter": "Ch1", "section": None, "text": "about cats",
         "tf_idf": {"cat": 0.5}},
    ]
    results = retriever.search("cat", index)
    assert results[0]["score"] > 0
