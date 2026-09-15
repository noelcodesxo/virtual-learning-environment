export type Source = {
  book?: string | null;
  chapter?: string | null;
  section?: string | null;
  score: number;
};

export type ChatResponse = { answer: string; sources: Source[]; thread_id: string; title: string };

export type Book = { title: string; chapters: string[] };

export type ExamQuestion = { section: string; question: string; options: string[] };

export type Exam = {
  id: string;
  book: string;
  chapter: string;
  generated_from: "form" | "description";
  description?: string | null;
  requested_question_count?: number;
  questions: ExamQuestion[];
};

export type ExamSummary = Omit<Exam, "questions"> & {
  score: number | null;
  total: number;
};

export type GradedQuestion = ExamQuestion & {
  correct_index: number;
  given_index: number | null;
  why: string;
};

export type GradedExam = Omit<Exam, "questions"> & {
  score: number;
  total: number;
  review: GradedQuestion[];
  graded: true;
};
