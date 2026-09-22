import type { Book, ChatResponse, Exam, ExamJob, ExamSummary, GradedExam, LibraryDocument } from "./types";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, init);
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
  library: () => request<{ documents: LibraryDocument[] }>("/library"),
  chat: (query: string, model: string) =>
    request<ChatResponse>("/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query, model }),
    }),
  uploadLibraryFile: (file: File) =>
    request<{ filename: string; indexed_chunks: number }>(`/library/upload?filename=${encodeURIComponent(file.name)}`, {
      method: "POST",
      headers: { "Content-Type": file.type || "application/epub+zip" },
      body: file,
    }),
  deleteLibraryFile: (filename: string) =>
    request<{ filename: string; indexed_chunks: number }>(`/library/${encodeURIComponent(filename)}`, {
      method: "DELETE",
    }),
  resolveDescription: (description: string) =>
    request<{ source: string; chapter: string }>("/exams/resolve-description", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ description }),
    }),
  createExamJob: (body: object) =>
    request<ExamJob>("/exam-jobs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  examJobs: () => request<{ jobs: ExamJob[] }>("/exam-jobs"),
  examJob: (id: string) => request<ExamJob>(`/exam-jobs/${id}`),
  exams: () => request<{ exams: ExamSummary[] }>("/exams"),
  exam: (id: string) => request<Exam | GradedExam>(`/exams/${id}`),
  gradeExam: (id: string, answers: Record<number, number>) =>
    request<GradedExam>(`/exams/${id}/grade`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ answers }),
    }),
};
