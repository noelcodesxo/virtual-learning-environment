import json

from exam_store import ExamStore


def _exam(**overrides):
    exam = {
        "id": "exam-1",
        "source": "AI Engineering",
        "chapter": "4. Evaluate AI Systems",
        "questions": [{
            "section": "Evaluation Criteria",
            "question": "What is X?",
            "options": ["A", "B", "C"],
            "correct_index": 1,
            "why": "Because B is right.",
        }],
        "created_at": "2026-09-18T00:00:00+00:00",
        "answers": None,
        "score": None,
        "generated_from": "form",
        "description": None,
        "requested_question_count": 1,
    }
    exam.update(overrides)
    return exam


def test_exam_store_saves_and_reloads_an_exam(tmp_path):
    store = ExamStore(tmp_path / "exams")
    store.save(_exam(answers={0: 1}, score=1))

    saved = json.loads((tmp_path / "exams" / "exam-1.json").read_text())
    assert saved["answers"] == {"0": 1}
    assert store.load() == {"exam-1": _exam(answers={0: 1}, score=1)}


def test_exam_store_overwrites_an_exam_when_it_is_graded(tmp_path):
    store = ExamStore(tmp_path / "exams")
    store.save(_exam())
    store.save(_exam(answers={0: 1}, score=1))

    assert list((tmp_path / "exams").glob("*.json")) == [tmp_path / "exams" / "exam-1.json"]
    assert store.load()["exam-1"]["score"] == 1


def test_exam_store_skips_corrupt_files_without_losing_valid_exams(tmp_path, caplog):
    store = ExamStore(tmp_path / "exams")
    store.save(_exam())
    (tmp_path / "exams" / "broken.json").write_text("not json")

    assert store.load() == {"exam-1": _exam()}
    assert "Skipping invalid saved exam broken.json" in caplog.text


def test_exam_store_migrates_existing_book_fields_to_source(tmp_path):
    store = ExamStore(tmp_path / "exams")
    legacy_exam = _exam()
    legacy_exam["book"] = legacy_exam.pop("source")
    store.directory.mkdir()
    (store.directory / "exam-1.json").write_text(json.dumps(legacy_exam))

    assert store.load()["exam-1"]["source"] == "AI Engineering"
