import json
import logging
import os
import uuid
from pathlib import Path


logger = logging.getLogger(__name__)

_REQUIRED_JOB_FIELDS = {"id", "status", "request", "created_at", "updated_at", "exam_id", "error"}
_VALID_JOB_STATUSES = {"queued", "running", "completed", "failed"}


class ExamJobStoreError(Exception):
    pass


class ExamJobStore:
    """Durably stores exam-generation jobs so clients can recover after a disconnect."""

    def __init__(self, directory: Path):
        self.directory = Path(directory)

    def load(self) -> dict[str, dict]:
        if not self.directory.exists():
            return {}
        if not self.directory.is_dir():
            raise ExamJobStoreError(f"Exam job storage path is not a directory: {self.directory}")

        jobs = {}
        for path in sorted(self.directory.glob("*.json")):
            try:
                job = self._read(path)
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                logger.warning("Skipping invalid saved exam job %s: %s", path.name, exc)
                continue
            if job["id"] in jobs:
                logger.warning("Skipping duplicate saved exam job id %s from %s", job["id"], path.name)
                continue
            jobs[job["id"]] = job
        return jobs

    def save(self, job: dict) -> None:
        job_id = job.get("id")
        if not isinstance(job_id, str) or not job_id:
            raise ExamJobStoreError("Exam job must have a non-empty string id")

        temporary_path = None
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            destination = self.directory / f"{job_id}.json"
            temporary_path = self.directory / f".{job_id}.{uuid.uuid4().hex}.tmp"
            with temporary_path.open("w", encoding="utf-8") as file:
                json.dump(job, file, ensure_ascii=False, indent=2, sort_keys=True)
                file.write("\n")
                file.flush()
                os.fsync(file.fileno())
            temporary_path.replace(destination)
        except (OSError, TypeError, ValueError) as exc:
            raise ExamJobStoreError(f"Could not save exam job {job_id!r}: {exc}") from exc
        finally:
            if temporary_path is not None and temporary_path.exists():
                temporary_path.unlink(missing_ok=True)

    @staticmethod
    def _read(path: Path) -> dict:
        with path.open(encoding="utf-8") as file:
            job = json.load(file)
        if not isinstance(job, dict):
            raise ValueError("exam job must be a JSON object")

        missing_fields = _REQUIRED_JOB_FIELDS - job.keys()
        if missing_fields:
            raise ValueError(f"exam job is missing fields: {sorted(missing_fields)}")
        if not isinstance(job["id"], str) or not job["id"]:
            raise ValueError("exam job id must be a non-empty string")
        if job["status"] not in _VALID_JOB_STATUSES:
            raise ValueError(f"exam job has invalid status: {job['status']!r}")
        if not isinstance(job["request"], dict):
            raise ValueError("exam job request must be an object")
        if job["exam_id"] is not None and not isinstance(job["exam_id"], str):
            raise ValueError("exam job exam_id must be a string or null")
        if job["error"] is not None and not isinstance(job["error"], str):
            raise ValueError("exam job error must be a string or null")
        return job
