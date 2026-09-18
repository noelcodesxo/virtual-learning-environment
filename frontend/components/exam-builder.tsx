"use client";

import Link from "next/link";
import { FormEvent, KeyboardEvent, useCallback, useEffect, useState } from "react";
import { api } from "../lib/api";
import type { Book, Exam, ExamSummary, GradedExam } from "../lib/types";

type Stage = "loading" | "unavailable" | "configure" | "history" | "generating" | "exam" | "results";
const errorText = (error: unknown) => (error instanceof Error ? error.message : "Could not reach the server.");

export function ExamBuilder({ initialView }: { initialView: "configure" | "history" }) {
  const [stage, setStage] = useState<Stage>("loading");
  const [books, setBooks] = useState<Book[]>([]);
  const [book, setBook] = useState("");
  const [chapter, setChapter] = useState("");
  const [description, setDescription] = useState("");
  const [feedback, setFeedback] = useState("");
  const [questionCount, setQuestionCount] = useState(10);
  const [source, setSource] = useState<"form" | "description">("form");
  const [exam, setExam] = useState<Exam | null>(null);
  const [graded, setGraded] = useState<GradedExam | null>(null);
  const [answers, setAnswers] = useState<Record<number, number>>({});
  const [current, setCurrent] = useState(0);
  const [error, setError] = useState("");
  const [recent, setRecent] = useState<ExamSummary[]>([]);
  const [isResolving, setIsResolving] = useState(false);

  const loadRecent = useCallback(
    () =>
      api
        .exams()
        .then((data) => setRecent(data.exams))
        .catch(() => setRecent([])),
    [],
  );
  useEffect(() => {
    api
      .features()
      .then(({ exam_builder }) => {
        if (!exam_builder) return setStage("unavailable");
        return Promise.all([api.books(), api.exams()]).then(([bookData, examData]) => {
          setBooks(bookData.books);
          setRecent(examData.exams);
          setStage(initialView);
        });
      })
      .catch(() => setStage("unavailable"));
  }, [initialView]);

  const selectedBook = books.find((item) => item.title === book);
  const reset = () => {
    setBook("");
    setChapter("");
    setDescription("");
    setFeedback("");
    setQuestionCount(10);
    setSource("form");
    setExam(null);
    setGraded(null);
    setAnswers({});
    setCurrent(0);
    setError("");
    setStage("configure");
  };
  async function resolveDescription() {
    if (!description.trim() || isResolving) return;
    setIsResolving(true);
    setFeedback("Finding the best source chapter…");
    setError("");
    try {
      const selected = await api.resolveDescription(description.trim());
      setBook(selected.book);
      setChapter(selected.chapter);
      setSource("description");
      setFeedback(`Using: ${selected.book} → ${selected.chapter}. Your description will guide the exam focus.`);
    } catch (err) {
      setFeedback("");
      setError(errorText(err));
    } finally {
      setIsResolving(false);
    }
  }
  function submitDescription(event: FormEvent) {
    event.preventDefault();
    resolveDescription();
  }
  function handleDescriptionKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
      event.preventDefault();
      resolveDescription();
    }
  }
  async function generate() {
    if (!book || !chapter) return;
    setStage("generating");
    setError("");
    try {
      const next = await api.generateExam({
        book,
        chapter,
        num_questions: questionCount,
        generated_from: source,
        description: source === "description" ? description.trim() : null,
      });
      setExam(next);
      setAnswers({});
      setCurrent(0);
      setStage("exam");
    } catch (err) {
      setError(errorText(err));
      setStage("configure");
    }
  }
  const grade = useCallback(async () => {
    if (!exam) return;
    setError("");
    try {
      const result = await api.gradeExam(exam.id, answers);
      setGraded(result);
      setStage("results");
      loadRecent();
    } catch (err) {
      setError(errorText(err));
    }
  }, [answers, exam, loadRecent]);
  async function openExam(id: string) {
    try {
      const data = await api.exam(id);
      if ("graded" in data && data.graded) {
        setGraded(data);
        setExam(null);
        setStage("results");
      } else {
        setExam(data as Exam);
        setGraded(null);
        setAnswers({});
        setCurrent(0);
        setStage("exam");
      }
    } catch {
      setError("Could not open that exam.");
      setStage("configure");
    }
  }
  const selectAnswer = useCallback(
    (index: number) => {
      if (!exam || index >= exam.questions[current].options.length) return;
      setAnswers((all) => ({ ...all, [current]: index }));
    },
    [current, exam],
  );
  const goBack = useCallback(() => setCurrent((index) => Math.max(0, index - 1)), []);
  const goForward = useCallback(() => {
    if (!exam) return;
    if (current === exam.questions.length - 1) return;
    setCurrent((index) => index + 1);
  }, [current, exam]);

  useEffect(() => {
    if (stage !== "exam" || !exam) return;

    const handleExamKeyDown = (event: globalThis.KeyboardEvent) => {
      if (event.ctrlKey && !event.altKey && !event.metaKey && !event.shiftKey && event.key === "Enter") {
        event.preventDefault();
        grade();
        return;
      }
      if (event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return;
      const target = event.target as HTMLElement | null;
      if (target?.isContentEditable || ["INPUT", "SELECT", "TEXTAREA"].includes(target?.tagName ?? "")) return;

      if (event.key === "ArrowLeft") {
        event.preventDefault();
        goBack();
      } else if (event.key === "ArrowRight") {
        event.preventDefault();
        goForward();
      } else if (/^[1-4]$/.test(event.key)) {
        const optionIndex = Number(event.key) - 1;
        if (optionIndex < exam.questions[current].options.length) {
          event.preventDefault();
          selectAnswer(optionIndex);
        }
      }
    };

    window.addEventListener("keydown", handleExamKeyDown);
    return () => window.removeEventListener("keydown", handleExamKeyDown);
  }, [current, exam, goBack, goForward, grade, selectAnswer, stage]);

  if (stage === "loading") return <div className="page-message">Loading exam builder…</div>;
  if (stage === "unavailable")
    return (
      <div className="page-message">
        <h1>Exam builder unavailable</h1>
        <p>This feature is disabled or the API cannot be reached.</p>
      </div>
    );
  const request = exam ?? graded;
  const requestSummary =
    request &&
    (request.generated_from === "description" && request.description
      ? `Your request: ${request.description}`
      : `Form request: ${request.book} · ${request.chapter} · ${request.requested_question_count ?? graded?.total ?? exam?.questions.length} questions.`);
  const question = exam?.questions[current];

  return (
    <div className="exam-page">
      <header className="topbar">
        <span className="chat-title">
          {exam ? `${exam.book} · ${exam.chapter}` : stage === "history" ? "Recent exams" : "New exam"}
        </span>
        <div className="exam-header-actions">
          <Link className="header-action" href="/exams">
            New exam
          </Link>
          <Link className="header-action" href="/exams/history">
            Recent exams
          </Link>
        </div>
      </header>
      <section className="exam-content">
        {stage === "configure" && (
          <div className="configure-inner">
            <h1>Build an exam</h1>
            <p className="configure-sub">
              Pick a chapter or document. The model uses a bounded set of source excerpts, not search snippets.
            </p>
            <form className="nl-box" onSubmit={submitDescription}>
              <label className="nl-label" htmlFor="description">
                Describe the exam
              </label>
              <textarea
                id="description"
                className="nl-input"
                value={description}
                onChange={(event) => setDescription(event.target.value)}
                onKeyDown={handleDescriptionKeyDown}
                placeholder="e.g. Generate an exam on transformer architecture."
                aria-describedby="description-help description-feedback"
                rows={3}
              />
              <p id="description-help" className="field-help">
                Press Ctrl+Enter (or Cmd+Enter on Mac) to use your description.
              </p>
              <button className="nl-go" disabled={!description.trim() || isResolving} type="submit">
                {isResolving ? "Finding chapter…" : "Use description"}
              </button>
              <p id="description-feedback" className="nl-feedback" role="status">
                {feedback}
              </p>
            </form>
            <div className="divider-or">or choose directly</div>
            <div className="field-grid">
              <label className="field" htmlFor="book">
                Book
                <select
                  id="book"
                  value={book}
                  onChange={(event) => {
                    setBook(event.target.value);
                    setChapter("");
                    setSource("form");
                  }}
                >
                  <option value="">Select a book…</option>
                  {books.map((item) => (
                    <option key={item.title}>{item.title}</option>
                  ))}
                </select>
              </label>
              <label className="field" htmlFor="chapter">
                Chapter
                <select
                  id="chapter"
                  value={chapter}
                  disabled={!selectedBook}
                  onChange={(event) => {
                    setChapter(event.target.value);
                    setSource("form");
                  }}
                >
                  <option value="">Select a chapter or document…</option>
                  {selectedBook?.chapters.map((item) => (
                    <option key={item}>{item}</option>
                  ))}
                </select>
              </label>
            </div>
            <div className="field">
              <span id="question-count-label">Questions</span>
              <div className="stepper" role="group" aria-labelledby="question-count-label">
                <button
                  type="button"
                  aria-label="Decrease question count"
                  onClick={() => setQuestionCount((count) => Math.max(5, count - 5))}
                >
                  −
                </button>
                <output aria-live="polite">{questionCount}</output>
                <button
                  type="button"
                  aria-label="Increase question count"
                  onClick={() => setQuestionCount((count) => Math.min(25, count + 5))}
                >
                  +
                </button>
              </div>
            </div>
            {error && (
              <p className="exam-error" role="alert">
                {error}
              </p>
            )}
            <button className="generate-btn" disabled={!book || !chapter} type="button" onClick={generate}>
              {book && chapter ? "Generate exam" : "Select a book and chapter"}
            </button>
          </div>
        )}
        {stage === "history" && <ExamHistory recent={recent} onOpen={openExam} />}
        {stage === "generating" && (
          <div className="page-message" role="status">
            <p>
              Source selected: {book} · {chapter}
            </p>
            <h1>Waiting for the exam model response…</h1>
            <p className="generation-note">This can take a little while for longer documents.</p>
            <div className="typing" aria-hidden="true">
              <span />
              <span />
              <span />
            </div>
          </div>
        )}
        {stage === "exam" && exam && question && (
          <div className="exam-inner">
            <p className="exam-request">{requestSummary}</p>
            <div className="exam-progress-row" aria-live="polite">
              <span>
                Question {current + 1} of {exam.questions.length}
              </span>
              <span>{Object.keys(answers).length} answered</span>
            </div>
            <nav className="qdots" aria-label="Question navigation">
              {exam.questions.map((_, index) => (
                <button
                  type="button"
                  aria-label={`Go to question ${index + 1}${answers[index] !== undefined ? ", answered" : ""}`}
                  aria-current={index === current ? "step" : undefined}
                  onClick={() => setCurrent(index)}
                  className={`qdot${answers[index] !== undefined ? " answered" : ""}${index === current ? " current" : ""}`}
                  key={index}
                />
              ))}
            </nav>
            <div className="q-section-tag">{question.section}</div>
            <h1 className="q-text" id="question-heading">
              {question.question}
            </h1>
            <div className="opt-list" aria-labelledby="question-heading">
              {question.options.map((option, index) => (
                <button
                  type="button"
                  aria-pressed={answers[current] === index}
                  aria-keyshortcuts={`${index + 1}`}
                  aria-label={`Option ${index + 1}, shortcut ${index + 1}: ${option}`}
                  className={`opt-btn${answers[current] === index ? " selected" : ""}`}
                  onClick={() => selectAnswer(index)}
                  key={option}
                >
                  <span className="letter" aria-hidden="true">
                    {index + 1}
                  </span>
                  {option}
                </button>
              ))}
            </div>
            {error && (
              <p className="exam-error" role="alert">
                {error}
              </p>
            )}
            <div className="exam-nav">
              <button
                className="nav-btn"
                type="button"
                disabled={current === 0}
                onClick={goBack}
                aria-keyshortcuts="ArrowLeft"
              >
                <kbd aria-hidden="true">←</kbd> Back
              </button>
              <button
                className="nav-btn primary"
                type="button"
                onClick={goForward}
                aria-keyshortcuts={current === exam.questions.length - 1 ? "Control+Enter" : "ArrowRight"}
              >
                {current === exam.questions.length - 1 ? (
                  <>
                    Submit exam <kbd aria-hidden="true">Ctrl</kbd> + <kbd aria-hidden="true">↵</kbd>
                  </>
                ) : (
                  <>
                    Next <kbd aria-hidden="true">→</kbd>
                  </>
                )}
              </button>
            </div>
          </div>
        )}
        {stage === "results" && graded && (
          <div className="results-inner">
            <div className="score-card" role="status" aria-live="polite">
              <div>
                <div className="score-num">
                  {graded.score}/{graded.total}
                </div>
                <div className="score-label">correct</div>
              </div>
              <div>
                {graded.book}
                <br />
                <b>{graded.chapter}</b>
              </div>
            </div>
            <p className="exam-request">{requestSummary}</p>
            <h1>Review</h1>
            {graded.review.map((item, index) => (
              <article
                className={`review-item ${item.given_index === item.correct_index ? "correct" : "incorrect"}`}
                key={index}
              >
                <div className="q-section-tag">{item.section}</div>
                <h2>
                  {index + 1}. {item.question}
                </h2>
                <ul className="review-options">
                  {item.options.map((option, optionIndex) => (
                    <li
                      className={`review-opt${optionIndex === item.correct_index ? " correct-opt" : ""}${optionIndex === item.given_index && optionIndex !== item.correct_index ? " wrong-pick" : ""}`}
                      key={option}
                    >
                      <span className="letter" aria-hidden="true">
                        {optionIndex + 1}
                      </span>
                      {option}
                      {optionIndex === item.correct_index && <span className="sr-only"> (correct answer)</span>}
                      {optionIndex === item.given_index && optionIndex !== item.correct_index && (
                        <span className="sr-only"> (your answer)</span>
                      )}
                    </li>
                  ))}
                </ul>
                <p className="review-why">
                  <b>Why: </b>
                  {item.why}
                </p>
              </article>
            ))}
            <button className="nav-btn primary" type="button" onClick={reset}>
              New exam
            </button>
          </div>
        )}
      </section>
    </div>
  );
}

function ExamHistory({ recent, onOpen }: { recent: ExamSummary[]; onOpen: (id: string) => void }) {
  const [filter, setFilter] = useState<"all" | "in-progress" | "completed">("all");
  const filtered = recent.filter(
    (item) => filter === "all" || (filter === "completed" ? item.score !== null : item.score === null),
  );
  return (
    <div className="history-inner">
      <div className="history-heading">
        <div>
          <p className="eyebrow">Exam activity for this session</p>
          <h1>Recent exams</h1>
          <p>Resume an ungraded exam or review a completed one.</p>
        </div>
        <Link className="primary-action" href="/exams">
          Create an exam
        </Link>
      </div>
      <div className="filter-group" aria-label="Filter recent exams">
        {(["all", "in-progress", "completed"] as const).map((item) => (
          <button
            type="button"
            className={filter === item ? "active" : ""}
            aria-pressed={filter === item}
            onClick={() => setFilter(item)}
            key={item}
          >
            {item === "all" ? "All" : item === "in-progress" ? "In progress" : "Completed"}
          </button>
        ))}
      </div>
      {filtered.length ? (
        <div className="exam-history-list">
          {filtered.map((item) => (
            <article className="history-card" key={item.id}>
              <div>
                <p className="q-section-tag">{item.score === null ? "In progress" : "Completed"}</p>
                <h2>{item.book}</h2>
                <p>
                  {item.chapter} · {item.requested_question_count} questions
                </p>
                {item.score !== null ? (
                  <p className="history-score">
                    Score: {item.score}/{item.total}
                  </p>
                ) : null}
              </div>
              <button className="text-action" type="button" onClick={() => onOpen(item.id)}>
                {item.score === null ? "Resume exam" : "Review result"}
              </button>
            </article>
          ))}
        </div>
      ) : (
        <div className="workspace-message">
          <h2>No matching exams</h2>
          <p>Create an exam to see it here during this session.</p>
        </div>
      )}
    </div>
  );
}
