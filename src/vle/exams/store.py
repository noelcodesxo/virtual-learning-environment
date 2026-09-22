import json
import logging
import os
import uuid
from pathlib import Path


logger = logging.getLogger(__name__)

_REQUIRED_EXAM_FIELDS = {
    "id",
    "source",
    "chapter",
    "questions",
    "created_at",
    "answers",
    "score",
}
_REQUIRED_QUESTION_FIELDS = {"section", "question", "options", "correct_index", "why"}


class ExamStoreError(Exception):
    pass


class ExamStore:
    """Durably stores each generated exam as an individual JSON file."""

    def __init__(self, directory: Path):
        self.directory = Path(directory)

    def load(self) -> dict[str, dict]:
        if not self.directory.exists():
            return {}
        if not self.directory.is_dir():
            raise ExamStoreError(f"Exam storage path is not a directory: {self.directory}")

        exams = {}
        for path in sorted(self.directory.glob("*.json")):
            try:
                exam = self._read(path)
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                logger.warning("Skipping invalid saved exam %s: %s", path.name, exc)
                continue

            if exam["id"] in exams:
                logger.warning("Skipping duplicate saved exam id %s from %s", exam["id"], path.name)
                continue
            exams[exam["id"]] = exam
        return exams

    def save(self, exam: dict) -> None:
        exam_id = exam.get("id")
        if not isinstance(exam_id, str) or not exam_id:
            raise ExamStoreError("Exam must have a non-empty string id")

        temporary_path = None
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            destination = self.directory / f"{exam_id}.json"
            temporary_path = self.directory / f".{exam_id}.{uuid.uuid4().hex}.tmp"
            with temporary_path.open("w", encoding="utf-8") as file:
                json.dump(exam, file, ensure_ascii=False, indent=2, sort_keys=True)
                file.write("\n")
                file.flush()
                os.fsync(file.fileno())
            temporary_path.replace(destination)
        except (OSError, TypeError, ValueError) as exc:
            raise ExamStoreError(f"Could not save exam {exam_id!r}: {exc}") from exc
        finally:
            if temporary_path is not None and temporary_path.exists():
                temporary_path.unlink(missing_ok=True)

    @staticmethod
    def _read(path: Path) -> dict:
        with path.open(encoding="utf-8") as file:
            exam = json.load(file)
        if not isinstance(exam, dict):
            raise ValueError("exam must be a JSON object")

        if "source" not in exam and "book" in exam:
            exam["source"] = exam.pop("book")

        missing_fields = _REQUIRED_EXAM_FIELDS - exam.keys()
        if missing_fields:
            raise ValueError(f"exam is missing fields: {sorted(missing_fields)}")
        if not isinstance(exam["id"], str) or not exam["id"]:
            raise ValueError("exam id must be a non-empty string")
        if not isinstance(exam["questions"], list):
            raise ValueError("exam questions must be a list")
        for question in exam["questions"]:
            if not isinstance(question, dict) or _REQUIRED_QUESTION_FIELDS - question.keys():
                raise ValueError("exam question has an invalid schema")

        answers = exam["answers"]
        if answers is not None:
            if not isinstance(answers, dict):
                raise ValueError("exam answers must be an object or null")
            try:
                exam["answers"] = {int(index): choice for index, choice in answers.items()}
            except (TypeError, ValueError) as exc:
                raise ValueError("exam answer indexes must be integers") from exc
        return exam
