import json

from exam_job_store import ExamJobStore


def _job(**overrides):
    job = {
        "id": "job-1",
        "status": "queued",
        "request": {"source": "AI Engineering", "chapter": "4. Evaluate AI Systems", "num_questions": 1},
        "exam_id": None,
        "error": None,
        "created_at": "2026-09-21T00:00:00+00:00",
        "updated_at": "2026-09-21T00:00:00+00:00",
    }
    job.update(overrides)
    return job


def test_exam_job_store_saves_and_reloads_a_job(tmp_path):
    store = ExamJobStore(tmp_path / "exam-jobs")
    store.save(_job(status="completed", exam_id="exam-1"))

    saved = json.loads((tmp_path / "exam-jobs" / "job-1.json").read_text())
    assert saved["exam_id"] == "exam-1"
    assert store.load() == {"job-1": _job(status="completed", exam_id="exam-1")}


def test_exam_job_store_skips_corrupt_files_without_losing_valid_jobs(tmp_path, caplog):
    store = ExamJobStore(tmp_path / "exam-jobs")
    store.save(_job())
    (store.directory / "broken.json").write_text("not json")

    assert store.load() == {"job-1": _job()}
    assert "Skipping invalid saved exam job broken.json" in caplog.text
