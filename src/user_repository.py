"""Server-side persistence for user-owned chats and exams in Supabase."""

import json
import os
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone


class SupabaseRepository:
    def __init__(self, url: str | None = None, service_key: str | None = None):
        self.url = (url or os.environ["SUPABASE_URL"]).rstrip("/")
        self.service_key = service_key or os.environ["SUPABASE_SERVICE_ROLE_KEY"]

    def _request(self, path: str, method: str = "GET", payload=None, prefer: str | None = None):
        headers = {"apikey": self.service_key, "Authorization": f"Bearer {self.service_key}"}
        if prefer:
            headers["Prefer"] = prefer
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        if data is not None:
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(f"{self.url}/rest/v1/{path}", data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                raw = response.read()
                return json.loads(raw) if raw else None
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
            raise RuntimeError("Supabase database request failed") from exc

    def create_thread(self, user_id: str, title: str) -> dict:
        data = self._request("chat_threads", "POST", {"id": str(uuid.uuid4()), "user_id": user_id, "title": title}, "return=representation")
        return data[0]

    def list_threads(self, user_id: str) -> list[dict]:
        return self._request(f"chat_threads?user_id=eq.{urllib.parse.quote(user_id)}&select=*&order=updated_at.desc")

    def get_thread(self, user_id: str, thread_id: str) -> dict | None:
        data = self._request(f"chat_threads?id=eq.{urllib.parse.quote(thread_id)}&user_id=eq.{urllib.parse.quote(user_id)}&select=*")
        return data[0] if data else None

    def add_message(self, user_id: str, thread_id: str, role: str, content: str, sources=None) -> None:
        self._request("chat_messages", "POST", {"user_id": user_id, "thread_id": thread_id, "role": role, "content": content, "sources": sources})
        self._request(f"chat_threads?id=eq.{urllib.parse.quote(thread_id)}&user_id=eq.{urllib.parse.quote(user_id)}", "PATCH", {"updated_at": datetime.now(timezone.utc).isoformat()})

    def get_messages(self, user_id: str, thread_id: str) -> list[dict]:
        return self._request(f"chat_messages?user_id=eq.{urllib.parse.quote(user_id)}&thread_id=eq.{urllib.parse.quote(thread_id)}&select=*&order=created_at.asc")

    def create_exam(self, user_id: str, exam: dict) -> None:
        self._request("exams", "POST", {key: exam[key] for key in ("id", "book", "chapter", "generated_from", "description", "requested_question_count", "created_at")} | {"user_id": user_id})
        questions = []
        answer_keys = []
        for position, question in enumerate(exam["questions"]):
            question_id = str(uuid.uuid4())
            questions.append({"id": question_id, "exam_id": exam["id"], "position": position, "section": question["section"], "question": question["question"], "options": question["options"]})
            answer_keys.append({"question_id": question_id, "correct_index": question["correct_index"], "why": question["why"]})
        self._request("exam_questions", "POST", questions)
        self._request("exam_answer_keys", "POST", answer_keys)

    def list_exams(self, user_id: str) -> list[dict]:
        return self._request(f"exams?user_id=eq.{urllib.parse.quote(user_id)}&select=*&order=created_at.desc")

    def get_exam(self, user_id: str, exam_id: str) -> dict | None:
        rows = self._request(f"exams?id=eq.{urllib.parse.quote(exam_id)}&user_id=eq.{urllib.parse.quote(user_id)}&select=*")
        if not rows:
            return None
        exam = rows[0]
        questions = self._request(f"exam_questions?exam_id=eq.{urllib.parse.quote(exam_id)}&select=*&order=position.asc")
        keys = self._request(f"exam_answer_keys?question_id=in.({','.join(q['id'] for q in questions)})&select=*") if questions else []
        key_by_question = {key["question_id"]: key for key in keys}
        exam["questions"] = [{"section": q["section"], "question": q["question"], "options": q["options"], **key_by_question[q["id"]]} for q in questions]
        return exam

    def grade_exam(self, user_id: str, exam_id: str, answers: dict[int, int]) -> dict | None:
        exam = self.get_exam(user_id, exam_id)
        if exam is None:
            return None
        score = sum(1 for i, question in enumerate(exam["questions"]) if answers.get(i) == question["correct_index"])
        self._request(f"exams?id=eq.{urllib.parse.quote(exam_id)}&user_id=eq.{urllib.parse.quote(user_id)}", "PATCH", {"answers": answers, "score": score})
        exam["answers"] = answers
        exam["score"] = score
        return exam


def get_repository() -> SupabaseRepository:
    return SupabaseRepository()
