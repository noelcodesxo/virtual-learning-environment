from vle.rag.prompts import build_rag_messages


def test_build_rag_messages_has_system_and_user_roles():
    messages = build_rag_messages("What is X?", [])
    assert [m["role"] for m in messages] == ["system", "user"]


def test_build_rag_messages_includes_query_in_user_content():
    messages = build_rag_messages("What is X?", [])
    assert "What is X?" in messages[1]["content"]


def test_build_rag_messages_includes_chunk_text_and_metadata():
    chunks = [{"book": "Book A", "chapter": "Ch1", "section": "Intro", "text": "some fact"}]
    content = build_rag_messages("q", chunks)[1]["content"]
    assert "some fact" in content
    assert "book: Book A" in content
    assert "chapter: Ch1" in content
    assert "section: Intro" in content


def test_build_rag_messages_excludes_retrieval_score():
    chunks = [{"book": "Book A", "chapter": "Ch1", "section": "Intro", "text": "some fact", "score": 0.123456}]
    content = build_rag_messages("q", chunks)[1]["content"]
    assert "score" not in content
    assert "0.123456" not in content


def test_build_rag_messages_omits_missing_section():
    chunks = [{"book": "Book A", "chapter": "Ch1", "section": None, "text": "some fact"}]
    content = build_rag_messages("q", chunks)[1]["content"]
    assert "chapter: Ch1" in content
    assert "section" not in content


def test_build_rag_messages_excludes_bm25():
    chunks = [{"book": "Book A", "chapter": "Ch1", "section": None, "text": "some fact", "bm25": {"cat": 0.5}}]
    content = build_rag_messages("q", chunks)[1]["content"]
    assert "bm25" not in content
    assert "cat" not in content


def test_build_rag_messages_excludes_index_identity_metadata():
    chunks = [
        {
            "book": "Book A",
            "chapter": "Ch1",
            "section": "Intro",
            "text": "some fact",
            "source_path": "internal/resources/private.epub",
            "source_sha256": "internal-hash-marker",
            "source_chunk_count": 91,
            "source_ordinal": 7,
        }
    ]
    content = build_rag_messages("q", chunks)[1]["content"]

    for key in ("source_path", "source_sha256", "source_chunk_count", "source_ordinal"):
        assert f"{key}:" not in content
    assert "internal/resources/private.epub" not in content
    assert "internal-hash-marker" not in content
    assert "book: Book A" in content
    assert "chapter: Ch1" in content
    assert "section: Intro" in content


def test_build_rag_messages_notes_when_no_context_found():
    content = build_rag_messages("q", [])[1]["content"]
    assert "No relevant context" in content
