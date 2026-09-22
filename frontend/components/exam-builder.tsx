"use client";

import Link from "next/link";
import { FormEvent, KeyboardEvent, useCallback, useEffect, useState } from "react";
import { api } from "../lib/api";
import type { BloomLevel, Book, Exam, ExamJob, ExamSummary, GradedExam } from "../lib/types";

type Stage = "loading" | "unavailable" | "configure" | "history" | "generating" | "exam" | "results";
const errorText = (error: unknown) => (error instanceof Error ? error.message : "Could not reach the server.");
const bloomOptions: { value: BloomLevel; label: string; description: string }[] = [
  { value: "remember", label: "Remember", description: "Recall facts and terms" },
  { value: "understand", label: "Understand", description: "Explain ideas and relationships" },
  { value: "apply", label: "Apply", description: "Use methods in a situation" },
  { value: "analyze", label: "Analyze", description: "Distinguish structure and relationships" },
  { value: "evaluate", label: "Evaluate", description: "Judge using source-based criteria" },
  { value: "create", label: "Create", description: "Plan a supported approach" },
];
const allBloomLevels = bloomOptions.map((option) => option.value);
const formatBloomLevels = (levels: BloomLevel[]) =>
  levels.map((level) => level[0].toUpperCase() + level.slice(1)).join(", ");

export function ExamBuilder({ initialView }: { initialView: "configure" | "history" }) {
  const [stage, setStage] = useState<Stage>("loading");
  const [books, setBooks] = useState<Book[]>([]);
  const [examSource, setExamSource] = useState("");
  const [chapter, setChapter] = useState("");
  const [description, setDescription] = useState("");
  const [feedback, setFeedback] = useState("");
  const [questionCount, setQuestionCount] = useState(10);
  const [bloomLevels, setBloomLevels] = useState<BloomLevel[]>(allBloomLevels);
  const [generationMethod, setGenerationMethod] = useState<"form" | "description">("form");
  const [exam, setExam] = useState<Exam | null>(null);
  const [graded, setGraded] = useState<GradedExam | null>(null);
  const [examJob, setExamJob] = useState<ExamJob | null>(null);
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
        return Promise.all([api.books(), api.exams(), api.examJobs()]).then(([bookData, examData, jobData]) => {
          setBooks(bookData.books);
          setRecent(examData.exams);
          const activeJob = jobData.jobs.find((job) => job.status === "queued" || job.status === "running");
          if (activeJob) {
            setExamJob(activeJob);
            setStage("generating");
          } else {
            setStage(initialView);
          }
        });
      })
      .catch(() => setStage("unavailable"));
  }, [initialView]);

  const selectedExamSource = books.find((item) => item.title === examSource);
  const reset = () => {
    setExamSource("");
    setChapter("");
    setDescription("");
    setFeedback("");
    setQuestionCount(10);
    setBloomLevels(allBloomLevels);
    setGenerationMethod("form");
    setExam(null);
    setGraded(null);
    setExamJob(null);
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
      setExamSource(selected.source);
      setChapter(selected.chapter);
      setGenerationMethod("description");
      setFeedback(`Using: ${selected.source} → ${selected.chapter}. Your description will guide the exam focus.`);
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
  function toggleBloomLevel(level: BloomLevel) {
    setBloomLevels((levels) =>
      levels.includes(level) ? levels.filter((selected) => selected !== level) : [...levels, level],
    );
  }
  async function generate() {
    if (!examSource || !chapter || !bloomLevels.length) return;
    setStage("generating");
    setError("");
    try {
      const nextJob = await api.createExamJob({
        source: examSource,
        chapter,
        num_questions: questionCount,
        generated_from: generationMethod,
        description: generationMethod === "description" ? description.trim() : null,
        bloom_levels: bloomLevels,
      });
      setExamJob(nextJob);
    } catch (err) {
      setError(errorText(err));
      setStage("configure");
    }
  }
  const examJobId = examJob?.id;
  useEffect(() => {
    if (stage !== "generating" || !examJobId) return;
    let cancelled = false;

    const poll = async () => {
      try {
        const nextJob = await api.examJob(examJobId);
        if (cancelled) return;
        setExamJob(nextJob);
        if (nextJob.status === "completed" && nextJob.exam_id) {
          const nextExam = await api.exam(nextJob.exam_id);
          if (cancelled) return;
          setExam(nextExam as Exam);
          setAnswers({});
          setCurrent(0);
          setStage("exam");
          loadRecent();
        } else if (nextJob.status === "failed") {
          setError(nextJob.error ?? "Exam generation failed.");
          setStage("configure");
        }
      } catch (err) {
        if (cancelled) return;
        setError(errorText(err));
        setStage("configure");
      }
    };

    poll();
    const interval = window.setInterval(poll, 2_000);
    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, [examJobId, loadRecent, stage]);
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
      : `Form request: ${request.source} · ${request.chapter} · ${request.requested_question_count ?? graded?.total ?? exam?.questions.length} questions.`);
  const bloomSummary = request && `Bloom levels: ${formatBloomLevels(request.bloom_levels)}`;
  const question = exam?.questions[current];

  return (
    <div className="exam-page">
      <header className="topbar">
        <span className="chat-title">
          {exam ? `${exam.source} · ${exam.chapter}` : stage === "history" ? "Recent exams" : "New exam"}
        </span>
        <div className="exam-header-actions">
          <Link className="header-action" href="/exams" onClick={initialView === "configure" ? reset : undefined}>
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
              <label className="field" htmlFor="source">
                Source
                <select
                  id="source"
                  value={examSource}
                  onChange={(event) => {
                    setExamSource(event.target.value);
                    setChapter("");
                    setGenerationMethod("form");
                  }}
                >
                  <option value="">Select a source…</option>
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
                  disabled={!selectedExamSource}
                  onChange={(event) => {
                    setChapter(event.target.value);
                    setGenerationMethod("form");
                  }}
                >
                  <option value="">Select a chapter or document…</option>
                  {selectedExamSource?.chapters.map((item) => (
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
                  disabled={questionCount <= 5}
                  onClick={() => setQuestionCount((count) => Math.max(5, count - 5))}
                >
                  −
                </button>
                <output aria-live="polite">{questionCount}</output>
                <button
                  type="button"
                  aria-label="Increase question count"
                  disabled={questionCount >= 25}
                  onClick={() => setQuestionCount((count) => Math.min(25, count + 5))}
                >
                  +
                </button>
              </div>
            </div>
            <fieldset className="field bloom-levels">
              <legend>Bloom&apos;s taxonomy levels</legend>
              <p className="field-help" id="bloom-levels-help">
                Select one or more levels to shape the kind of questions in this exam.
              </p>
              <div className="bloom-options" aria-describedby="bloom-levels-help">
                {bloomOptions.map((option) => (
                  <label className="bloom-option" key={option.value}>
                    <input
                      type="checkbox"
                      checked={bloomLevels.includes(option.value)}
                      onChange={() => toggleBloomLevel(option.value)}
                    />
                    <span>
                      <b>{option.label}</b>
                      <small>{option.description}</small>
                    </span>
                  </label>
                ))}
              </div>
            </fieldset>
            {error && (
              <p className="exam-error" role="alert">
                {error}
              </p>
            )}
            <button
              className="generate-btn"
              disabled={!examSource || !chapter || !bloomLevels.length}
              type="button"
              onClick={generate}
            >
              {examSource && chapter
                ? bloomLevels.length
                  ? "Generate exam"
                  : "Select a Bloom level"
                : "Select a source and chapter"}
            </button>
          </div>
        )}
        {stage === "history" && <ExamHistory recent={recent} onOpen={openExam} />}
        {stage === "generating" && (
          <div className="page-message" role="status">
            {examSource && chapter && (
              <p>
                Source selected: {examSource} · {chapter}
              </p>
            )}
            <h1>{examJob?.status === "queued" ? "Exam generation is queued…" : "Generating your exam…"}</h1>
            <p className="generation-note">
              This can take a little while for longer documents. You can safely refresh this page while it runs.
            </p>
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
            <p className="exam-request">{bloomSummary}</p>
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
                {graded.source}
                <br />
                <b>{graded.chapter}</b>
              </div>
            </div>
            <p className="exam-request">{requestSummary}</p>
            <p className="exam-request">{bloomSummary}</p>
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
                <h2>{item.source}</h2>
                <p>
                  {item.chapter} · {item.requested_question_count} questions
                </p>
                <p className="history-bloom">Bloom: {formatBloomLevels(item.bloom_levels)}</p>
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
