from prompts import build_rag_messages


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


def test_build_rag_messages_includes_score_formatted_to_4_decimals():
    chunks = [{"book": "Book A", "chapter": "Ch1", "section": "Intro", "text": "some fact", "score": 0.123456}]
    content = build_rag_messages("q", chunks)[1]["content"]
    assert "score: 0.1235" in content


def test_build_rag_messages_omits_missing_section():
    chunks = [{"book": "Book A", "chapter": "Ch1", "section": None, "text": "some fact"}]
    content = build_rag_messages("q", chunks)[1]["content"]
    assert "chapter: Ch1" in content
    assert "section" not in content


def test_build_rag_messages_excludes_tf_idf():
    chunks = [{"book": "Book A", "chapter": "Ch1", "section": None, "text": "some fact", "tf_idf": {"cat": 0.5}}]
    content = build_rag_messages("q", chunks)[1]["content"]
    assert "tf_idf" not in content
    assert "cat" not in content


def test_build_rag_messages_notes_when_no_context_found():
    content = build_rag_messages("q", [])[1]["content"]
    assert "No relevant context" in content
