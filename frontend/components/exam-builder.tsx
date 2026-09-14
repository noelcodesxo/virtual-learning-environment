"use client";

import { useEffect, useState } from "react";
import { api } from "../lib/api";
import type { Book, Exam, ExamSummary, GradedExam } from "../lib/types";

const letters = ["A", "B", "C", "D"];
type Stage = "loading" | "unavailable" | "configure" | "generating" | "exam" | "results";
const errorText = (error: unknown) => error instanceof Error ? error.message : "Could not reach the server.";

export function ExamBuilder() {
  const [stage, setStage] = useState<Stage>("loading");
  const [books, setBooks] = useState<Book[]>([]);
  const [book, setBook] = useState(""); const [chapter, setChapter] = useState("");
  const [description, setDescription] = useState(""); const [feedback, setFeedback] = useState("");
  const [questionCount, setQuestionCount] = useState(10); const [source, setSource] = useState<"form" | "description">("form");
  const [exam, setExam] = useState<Exam | null>(null); const [graded, setGraded] = useState<GradedExam | null>(null);
  const [answers, setAnswers] = useState<Record<number, number>>({}); const [current, setCurrent] = useState(0);
  const [error, setError] = useState(""); const [recent, setRecent] = useState<ExamSummary[]>([]);

  const loadRecent = () => api.exams().then((data) => setRecent(data.exams)).catch(() => setRecent([]));
  useEffect(() => { api.features().then(({ exam_builder }) => {
    if (!exam_builder) return setStage("unavailable");
    return Promise.all([api.books(), api.exams()]).then(([bookData, examData]) => { setBooks(bookData.books); setRecent(examData.exams); setStage("configure"); });
  }).catch(() => setStage("unavailable")); }, []);

  const selectedBook = books.find((item) => item.title === book);
  const reset = () => { setBook(""); setChapter(""); setDescription(""); setFeedback(""); setQuestionCount(10); setSource("form"); setExam(null); setGraded(null); setAnswers({}); setCurrent(0); setError(""); setStage("configure"); };
  async function resolveDescription() { if (!description.trim()) return; setFeedback("Finding the best source chapter…"); setError(""); try { const selected = await api.resolveDescription(description.trim()); setBook(selected.book); setChapter(selected.chapter); setSource("description"); setFeedback(`Using: ${selected.book} → ${selected.chapter}. Your description will guide the exam focus.`); } catch (err) { setFeedback(""); setError(errorText(err)); } }
  async function generate() { if (!book || !chapter) return; setStage("generating"); setError(""); try { const next = await api.generateExam({ book, chapter, num_questions: questionCount, generated_from: source, description: source === "description" ? description.trim() : null }); setExam(next); setAnswers({}); setCurrent(0); setStage("exam"); } catch (err) { setError(errorText(err)); setStage("configure"); } }
  async function grade() { if (!exam) return; setError(""); try { const result = await api.gradeExam(exam.id, answers); setGraded(result); setStage("results"); loadRecent(); } catch (err) { setError(errorText(err)); } }
  async function openExam(id: string) { try { const data = await api.exam(id); if ("graded" in data && data.graded) { setGraded(data); setExam(null); setStage("results"); } else { setExam(data as Exam); setGraded(null); setAnswers({}); setCurrent(0); setStage("exam"); } } catch { setError("Could not open that exam."); setStage("configure"); } }

  if (stage === "loading") return <div className="page-message">Loading exam builder…</div>;
  if (stage === "unavailable") return <div className="page-message"><h1>Exam builder unavailable</h1><p>This feature is disabled or the API cannot be reached.</p></div>;
  const request = exam ?? graded;
  const requestSummary = request && (request.generated_from === "description" && request.description ? `Your request: ${request.description}` : `Form request: ${request.book} · ${request.chapter} · ${request.requested_question_count ?? graded?.total ?? exam?.questions.length} questions.`);
  const question = exam?.questions[current];

  return <div className="exam-page">
    <header className="topbar"><span className="chat-title">{exam ? `${exam.book} · ${exam.chapter}` : "New exam"}</span><div className="stage-track">{["Configure", "Generate", "Take exam", "Review"].map((name, index) => <span className={(stage === ["configure", "generating", "exam", "results"][index] ? "current" : "")} key={name}>{name}</span>)}</div></header>
    <div className="exam-layout"><aside className="workspace-sidebar"><button className="new-chat" onClick={reset}>＋ <span>New exam</span></button><div className="section-label">Recent exams</div><div className="recent-list">{recent.map((item) => <button className="recent-item" key={item.id} onClick={() => openExam(item.id)}>{item.book} · {item.chapter}<small>{item.score === null ? "not started" : `${item.score}/${item.total}`} · {item.requested_question_count} questions</small></button>)}</div></aside>
    <section className="exam-content">
      {stage === "configure" && <div className="configure-inner"><h1>Build an exam</h1><p className="configure-sub">Pick a chapter, or describe what you want. The model reads the full chapter, not search snippets.</p><div className="nl-box"><label className="nl-label" htmlFor="description">Describe the exam</label><textarea id="description" className="nl-input" value={description} onChange={(event) => setDescription(event.target.value)} placeholder="e.g. Generate an exam on transformer architecture." rows={3} /><button className="nl-go" onClick={resolveDescription}>Use description</button><p className="nl-feedback">{feedback}</p></div><div className="divider-or">or choose directly</div><div className="field-grid"><label className="field">Book<select value={book} onChange={(event) => { setBook(event.target.value); setChapter(""); setSource("form"); }}>{<option value="">Select a book…</option>}{books.map((item) => <option key={item.title}>{item.title}</option>)}</select></label><label className="field">Chapter<select value={chapter} disabled={!selectedBook} onChange={(event) => { setChapter(event.target.value); setSource("form"); }}><option value="">Select a chapter…</option>{selectedBook?.chapters.map((item) => <option key={item}>{item}</option>)}</select></label></div><div className="field"><span>Questions</span><div className="stepper"><button onClick={() => setQuestionCount((count) => Math.max(5, count - 5))}>−</button><span>{questionCount}</span><button onClick={() => setQuestionCount((count) => Math.min(25, count + 5))}>+</button></div></div>{error && <p className="exam-error">{error}</p>}<button className="generate-btn" disabled={!book || !chapter} onClick={generate}>{book && chapter ? "Generate exam" : "Select a book and chapter"}</button></div>}
      {stage === "generating" && <div className="page-message"><p>{book} · {chapter}</p><h1>Building your exam…</h1><div className="typing"><span /><span /><span /></div></div>}
      {stage === "exam" && exam && question && <div className="exam-inner"><p className="exam-request">{requestSummary}</p><div className="exam-progress-row"><span>Question {current + 1} of {exam.questions.length}</span><span>{Object.keys(answers).length} answered</span></div><div className="qdots">{exam.questions.map((_, index) => <button aria-label={`Question ${index + 1}`} onClick={() => setCurrent(index)} className={`qdot${answers[index] !== undefined ? " answered" : ""}${index === current ? " current" : ""}`} key={index} />)}</div><div className="q-section-tag">{question.section}</div><h1 className="q-text">{question.question}</h1><div className="opt-list">{question.options.map((option, index) => <button className={`opt-btn${answers[current] === index ? " selected" : ""}`} onClick={() => setAnswers((all) => ({ ...all, [current]: index }))} key={option}><span className="letter">{letters[index]}</span>{option}</button>)}</div>{error && <p className="exam-error">{error}</p>}<div className="exam-nav"><button className="nav-btn" disabled={current === 0} onClick={() => setCurrent((index) => index - 1)}>Back</button><button className="nav-btn primary" onClick={() => current === exam.questions.length - 1 ? grade() : setCurrent((index) => index + 1)}>{current === exam.questions.length - 1 ? "Submit exam" : "Next"}</button></div></div>}
      {stage === "results" && graded && <div className="results-inner"><div className="score-card"><div><div className="score-num">{graded.score}/{graded.total}</div><div className="score-label">correct</div></div><div>{graded.book}<br /><b>{graded.chapter}</b></div></div><p className="exam-request">{requestSummary}</p><h2>Review</h2>{graded.review.map((item, index) => <article className={`review-item ${item.given_index === item.correct_index ? "correct" : "incorrect"}`} key={index}><div className="q-section-tag">{item.section}</div><h3>{index + 1}. {item.question}</h3>{item.options.map((option, optionIndex) => <div className={`review-opt${optionIndex === item.correct_index ? " correct-opt" : ""}${optionIndex === item.given_index && optionIndex !== item.correct_index ? " wrong-pick" : ""}`} key={option}><span className="letter">{letters[optionIndex]}</span>{option}</div>)}<p className="review-why"><b>WHY </b>{item.why}</p></article>)}<button className="nav-btn primary" onClick={reset}>New exam</button></div>}
    </section></div>
  </div>;
}
