import type { Book, ChatResponse, Exam, ExamSummary, GradedExam } from "./types";
import { supabase } from "./supabase";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const { data: { session } } = await supabase.auth.getSession();
  if (!session) throw new Error("Please sign in to continue.");
  const headers = new Headers(init?.headers);
  headers.set("Authorization", `Bearer ${session.access_token}`);
  const response = await fetch(`/api${path}`, { ...init, headers });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.detail || `Request failed (${response.status}).`);
  }
  return response.json() as Promise<T>;
}

export const api = {
  models: () => request<{ models: string[] }>("/models"),
  features: () => request<{ exam_builder: boolean }>("/features"),
  books: () => request<{ books: Book[] }>("/books"),
  chat: (query: string, model: string, threadId?: string) => request<ChatResponse>("/chat", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ query, model, thread_id: threadId }),
  }),
  chatThreads: () => request<{ id: string; title: string; updated_at: string }[]>("/chat/threads"),
  chatThread: (id: string) => request<{ id: string; title: string; messages: { role: "user" | "assistant"; content: string; sources?: import("./types").Source[] }[] }>(`/chat/threads/${id}`),
  resolveDescription: (description: string) => request<{ book: string; chapter: string }>("/exams/resolve-description", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ description }),
  }),
  generateExam: (body: object) => request<Exam>("/exams", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  }),
  exams: () => request<{ exams: ExamSummary[] }>("/exams"),
  exam: (id: string) => request<Exam | GradedExam>(`/exams/${id}`),
  gradeExam: (id: string, answers: Record<number, number>) => request<GradedExam>(`/exams/${id}/grade`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ answers }),
  }),
};
