"""In-memory view of persisted exams for one running application."""


class ExamJobStore:
    def __init__(self, exams: dict[str, dict] | None = None):
        self.exams = exams or {}

    def get(self, exam_id: str) -> dict | None:
        return self.exams.get(exam_id)

    def save(self, exam: dict) -> None:
        self.exams[exam["id"]] = exam

    def values(self):
        return self.exams.values()
