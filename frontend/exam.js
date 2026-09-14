// Exam Builder - a separate flow from chat. It doesn't call /chat or use
// BM25 search results; exams are generated from a whole chapter's text via
// /exams, and correct answers are only ever returned after /exams/{id}/grade.

const OPTION_LETTERS = ["A", "B", "C", "D"];

const modeSwitchEl = document.getElementById("mode-switch");
const tabChatEl = document.getElementById("tab-chat");
const tabExamsEl = document.getElementById("tab-exams");
const chatSidebarEl = document.getElementById("chat-sidebar");
const examSidebarEl = document.getElementById("exam-sidebar");
const chatTopbarEl = document.getElementById("chat-topbar");
const examTopbarEl = document.getElementById("exam-topbar");
const chatViewEl = document.getElementById("chat-view");
const examViewEl = document.getElementById("exam-view");
const newExamBtnEl = document.getElementById("new-exam-btn");
const recentExamListEl = document.getElementById("recent-exam-list");

const examCrumbEl = document.getElementById("exam-crumb");
const stageStepEls = document.querySelectorAll("#exam-stage-track .step");

const nlInputEl = document.getElementById("nl-input");
const nlGoEl = document.getElementById("nl-go");
const nlFeedbackEl = document.getElementById("nl-feedback");
const bookSelectEl = document.getElementById("book-select");
const chapterSelectEl = document.getElementById("chapter-select");
const countValEl = document.getElementById("count-val");
const countDownEl = document.getElementById("count-down");
const countUpEl = document.getElementById("count-up");
const generateBtnEl = document.getElementById("generate-btn");
const configureErrorEl = document.getElementById("configure-error");

const genTargetEl = document.getElementById("gen-target");
const examRequestEl = document.getElementById("exam-request");
const resultRequestEl = document.getElementById("result-request");

const examProgressLabelEl = document.getElementById("exam-progress-label");
const examAnsweredLabelEl = document.getElementById("exam-answered-label");
const qdotsEl = document.getElementById("qdots");
const qSectionTagEl = document.getElementById("q-section-tag");
const qTextEl = document.getElementById("q-text");
const optListEl = document.getElementById("opt-list");
const examSubmitErrorEl = document.getElementById("exam-submit-error");
const examBackEl = document.getElementById("exam-back");
const examNextEl = document.getElementById("exam-next");

const scoreNumEl = document.getElementById("score-num");
const scoreSourceEl = document.getElementById("score-source");
const reviewListEl = document.getElementById("review-list");
const resultsNewEl = document.getElementById("results-new");

let books = [];
let selectedBook = "";
let selectedChapter = "";
let questionCount = 10;
let generationSource = "form";

let currentExam = null; // { id, book, chapter, questions: [{section, question, options}] }
let examAnswers = {};
let examCurrentIndex = 0;

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function setStage(stage) {
  stageStepEls.forEach((stepEl) => stepEl.classList.toggle("current", stepEl.dataset.stage === stage));
}

function showScreen(id, stage) {
  document.querySelectorAll(".screen").forEach((screenEl) => screenEl.classList.remove("active"));
  document.getElementById(id).classList.add("active");
  setStage(stage);
}

function switchMode(mode) {
  const isExams = mode === "exams";
  tabChatEl.classList.toggle("active", !isExams);
  tabExamsEl.classList.toggle("active", isExams);
  chatSidebarEl.style.display = isExams ? "none" : "";
  examSidebarEl.style.display = isExams ? "" : "none";
  chatTopbarEl.style.display = isExams ? "none" : "";
  examTopbarEl.style.display = isExams ? "" : "none";
  chatViewEl.style.display = isExams ? "none" : "";
  examViewEl.style.display = isExams ? "" : "none";
}

tabChatEl.addEventListener("click", () => switchMode("chat"));
tabExamsEl.addEventListener("click", () => switchMode("exams"));

async function checkExamBuilderFeature() {
  try {
    const response = await fetch(`${API_BASE}/features`);
    if (!response.ok) return;
    const data = await response.json();
    if (data.exam_builder) {
      modeSwitchEl.style.display = "flex";
      loadBooks();
      loadRecentExams();
    }
  } catch (err) {
    // Exams stays hidden if the feature check fails; chat still works.
  }
}

async function loadBooks() {
  try {
    const response = await fetch(`${API_BASE}/books`);
    if (!response.ok) throw new Error(`status ${response.status}`);
    const data = await response.json();
    books = data.books;
    populateBookSelect();
  } catch (err) {
    bookSelectEl.innerHTML = "";
    bookSelectEl.appendChild(el("option", null, "Could not load books"));
  }
}

function populateBookSelect() {
  bookSelectEl.innerHTML = "";
  const placeholder = el("option", null, "Select a book…");
  placeholder.value = "";
  bookSelectEl.appendChild(placeholder);
  for (const book of books) {
    const opt = el("option", null, book.title);
    opt.value = book.title;
    bookSelectEl.appendChild(opt);
  }
}

function populateChapterSelect(bookTitle) {
  chapterSelectEl.innerHTML = "";
  const book = books.find((b) => b.title === bookTitle);
  if (!book) {
    chapterSelectEl.disabled = true;
    chapterSelectEl.appendChild(el("option", null, "Select a book first"));
    return;
  }
  chapterSelectEl.disabled = false;
  const placeholder = el("option", null, "Select a chapter…");
  placeholder.value = "";
  chapterSelectEl.appendChild(placeholder);
  for (const chapter of book.chapters) {
    const opt = el("option", null, chapter);
    opt.value = chapter;
    chapterSelectEl.appendChild(opt);
  }
}

function refreshGenerateState() {
  const ok = Boolean(selectedBook && selectedChapter);
  generateBtnEl.disabled = !ok;
  generateBtnEl.textContent = ok ? "Generate exam" : "Select a book and chapter";
}

bookSelectEl.addEventListener("change", () => {
  generationSource = "form";
  selectedBook = bookSelectEl.value;
  selectedChapter = "";
  populateChapterSelect(selectedBook);
  refreshGenerateState();
});

chapterSelectEl.addEventListener("change", () => {
  generationSource = "form";
  selectedChapter = chapterSelectEl.value;
  refreshGenerateState();
});

countDownEl.addEventListener("click", () => {
  questionCount = Math.max(5, questionCount - 5);
  countValEl.textContent = questionCount;
});

countUpEl.addEventListener("click", () => {
  questionCount = Math.min(25, questionCount + 5);
  countValEl.textContent = questionCount;
});

async function runParse(text) {
  if (!text.trim()) {
    nlFeedbackEl.textContent = "";
    nlFeedbackEl.className = "nl-feedback";
    return;
  }

  nlGoEl.disabled = true;
  nlFeedbackEl.textContent = "Finding the best source chapter…";
  nlFeedbackEl.className = "nl-feedback";

  try {
    const response = await fetch(`${API_BASE}/exams/resolve-description`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ description: text.trim() }),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || `Request failed (${response.status}).`);

    generationSource = "description";
    bookSelectEl.value = data.book;
    selectedBook = data.book;
    populateChapterSelect(data.book);
    chapterSelectEl.value = data.chapter;
    selectedChapter = data.chapter;
    refreshGenerateState();
    nlFeedbackEl.textContent = `Using: ${data.book} → ${data.chapter}. Your description will guide the exam focus.`;
    nlFeedbackEl.className = "nl-feedback ok";
  } catch (err) {
    nlFeedbackEl.textContent = err.message || "Could not identify a source chapter.";
    nlFeedbackEl.className = "nl-feedback err";
  } finally {
    nlGoEl.disabled = false;
  }
}

nlGoEl.addEventListener("click", () => runParse(nlInputEl.value));
nlInputEl.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) runParse(nlInputEl.value);
});

function resetConfigure() {
  selectedBook = "";
  selectedChapter = "";
  questionCount = 10;
  generationSource = "form";
  bookSelectEl.value = "";
  populateChapterSelect("");
  countValEl.textContent = "10";
  nlInputEl.value = "";
  nlFeedbackEl.textContent = "";
  nlFeedbackEl.className = "nl-feedback";
  configureErrorEl.textContent = "";
  refreshGenerateState();
  examCrumbEl.textContent = "New exam";
  showScreen("screen-configure", "configure");
}

newExamBtnEl.addEventListener("click", resetConfigure);
resultsNewEl.addEventListener("click", resetConfigure);

async function generateExam() {
  if (generateBtnEl.disabled) return;

  configureErrorEl.textContent = "";
  genTargetEl.textContent = `${selectedBook} · ${selectedChapter}`;
  showScreen("screen-generating", "generating");

  try {
    const response = await fetch(`${API_BASE}/exams`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        book: selectedBook,
        chapter: selectedChapter,
        num_questions: questionCount,
        generated_from: generationSource,
        description: generationSource === "description" ? nlInputEl.value.trim() : null,
      }),
    });

    if (!response.ok) {
      const detail = await response.json().catch(() => ({}));
      throw new Error(detail.detail || `Request failed (${response.status}).`);
    }

    currentExam = await response.json();
    examAnswers = {};
    examCurrentIndex = 0;
    examCrumbEl.textContent = `${currentExam.book} · ${currentExam.chapter}`;
    renderQuestion();
    showScreen("screen-exam", "exam");
  } catch (err) {
    configureErrorEl.textContent = err.message || "Could not reach the server. Is it running?";
    showScreen("screen-configure", "configure");
  }
}

function requestSummary(exam) {
  if (exam.generated_from === "description" && exam.description) return `Your request: ${exam.description}`;
  const count = exam.requested_question_count || exam.questions?.length || exam.total;
  return `Form request: ${exam.book} · ${exam.chapter} · ${count} questions.`;
}

function renderRequestContext(exam) {
  for (const target of [examRequestEl, resultRequestEl]) {
    target.textContent = requestSummary(exam);
    target.hidden = false;
  }
}

generateBtnEl.addEventListener("click", generateExam);

function renderDots() {
  qdotsEl.innerHTML = "";
  currentExam.questions.forEach((_, i) => {
    const dot = el("div", "qdot" + (examAnswers[i] !== undefined ? " answered" : "") + (i === examCurrentIndex ? " current" : ""));
    dot.addEventListener("click", () => {
      examCurrentIndex = i;
      renderQuestion();
    });
    qdotsEl.appendChild(dot);
  });
}

function renderQuestion() {
  const question = currentExam.questions[examCurrentIndex];
  renderRequestContext(currentExam);
  examProgressLabelEl.textContent = `Question ${examCurrentIndex + 1} of ${currentExam.questions.length}`;
  examAnsweredLabelEl.textContent = `${Object.keys(examAnswers).length} answered`;
  qSectionTagEl.textContent = question.section;
  qTextEl.textContent = question.question;
  examSubmitErrorEl.textContent = "";

  optListEl.innerHTML = "";
  question.options.forEach((opt, i) => {
    const btn = el("button", "opt-btn" + (examAnswers[examCurrentIndex] === i ? " selected" : ""));
    btn.type = "button";
    const letter = el("span", "letter", OPTION_LETTERS[i]);
    const text = el("span", null, opt);
    btn.appendChild(letter);
    btn.appendChild(text);
    btn.addEventListener("click", () => {
      examAnswers[examCurrentIndex] = i;
      renderQuestion();
    });
    optListEl.appendChild(btn);
  });

  examBackEl.disabled = examCurrentIndex === 0;
  examNextEl.textContent = examCurrentIndex === currentExam.questions.length - 1 ? "Submit exam" : "Next";
  renderDots();
}

examBackEl.addEventListener("click", () => {
  if (examCurrentIndex > 0) {
    examCurrentIndex--;
    renderQuestion();
  }
});

examNextEl.addEventListener("click", () => {
  if (examCurrentIndex < currentExam.questions.length - 1) {
    examCurrentIndex++;
    renderQuestion();
  } else {
    submitExam();
  }
});

async function submitExam() {
  examSubmitErrorEl.textContent = "";
  examNextEl.disabled = true;

  try {
    const response = await fetch(`${API_BASE}/exams/${currentExam.id}/grade`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ answers: examAnswers }),
    });

    if (!response.ok) {
      const detail = await response.json().catch(() => ({}));
      throw new Error(detail.detail || `Request failed (${response.status}).`);
    }

    const data = await response.json();
    renderResults(data);
    showScreen("screen-results", "results");
    loadRecentExams();
  } catch (err) {
    examSubmitErrorEl.textContent = err.message || "Could not reach the server. Is it running?";
  } finally {
    examNextEl.disabled = false;
  }
}

function renderResults(data) {
  scoreNumEl.textContent = `${data.score}/${data.total}`;
  scoreSourceEl.innerHTML = "";
  scoreSourceEl.appendChild(document.createTextNode(data.book));
  scoreSourceEl.appendChild(document.createElement("br"));
  scoreSourceEl.appendChild(el("b", null, data.chapter));
  renderRequestContext(currentExam);

  reviewListEl.innerHTML = "";
  data.review.forEach((question, i) => {
    const isCorrect = question.given_index === question.correct_index;
    const item = el("div", "review-item " + (isCorrect ? "correct" : "incorrect"));

    item.appendChild(el("div", "q-section-tag", question.section));
    item.appendChild(el("div", "review-q", `${i + 1}. ${question.question}`));

    const optsWrap = el("div", "review-opts");
    question.options.forEach((opt, oi) => {
      let cls = "review-opt";
      let mark = "";
      if (oi === question.correct_index) {
        cls += " correct-opt";
        mark = "✓";
      } else if (oi === question.given_index) {
        cls += " wrong-pick";
        mark = "✕";
      }
      const optEl = el("div", cls);
      optEl.appendChild(el("span", "letter", OPTION_LETTERS[oi]));
      optEl.appendChild(el("span", "opt-text", opt));
      if (mark) optEl.appendChild(el("span", "mark", mark));
      optsWrap.appendChild(optEl);
    });
    item.appendChild(optsWrap);

    if (question.given_index === null || question.given_index === undefined) {
      item.appendChild(el("div", "no-answer-note", "You didn't answer this one."));
    }

    const why = el("div", "review-why");
    why.appendChild(el("span", "tag", "WHY "));
    why.appendChild(document.createTextNode(question.why));
    item.appendChild(why);

    reviewListEl.appendChild(item);
  });
}

async function loadRecentExams() {
  try {
    const response = await fetch(`${API_BASE}/exams`);
    if (!response.ok) throw new Error(`status ${response.status}`);
    const data = await response.json();
    renderRecentExamList(data.exams);
  } catch (err) {
    recentExamListEl.innerHTML = "";
  }
}

function renderRecentExamList(exams) {
  recentExamListEl.innerHTML = "";
  for (const exam of exams) {
    const item = el("button", "recent-item exam-item");
    item.type = "button";
    item.appendChild(el("span", "recent-item-title", `${exam.book} · ${exam.chapter}`));
    const meta = exam.score === null ? "not started" : `${exam.score}/${exam.total}`;
    const source = exam.generated_from === "description" ? "description" : "form";
    item.appendChild(el("span", "recent-item-meta", `${meta} · ${exam.requested_question_count} questions · ${source}`));
    if (exam.description) item.title = exam.description;
    item.addEventListener("click", () => openExam(exam.id));
    recentExamListEl.appendChild(item);
  }
}

async function openExam(examId) {
  try {
    const response = await fetch(`${API_BASE}/exams/${examId}`);
    if (!response.ok) throw new Error(`status ${response.status}`);
    const data = await response.json();

    examCrumbEl.textContent = `${data.book} · ${data.chapter}`;

    if (data.graded) {
      currentExam = data;
      renderResults(data);
      showScreen("screen-results", "results");
    } else {
      currentExam = {
        id: data.id,
        book: data.book,
        chapter: data.chapter,
        generated_from: data.generated_from,
        description: data.description,
        requested_question_count: data.requested_question_count,
        questions: data.questions,
      };
      examAnswers = {};
      examCurrentIndex = 0;
      renderQuestion();
      showScreen("screen-exam", "exam");
    }
  } catch (err) {
    configureErrorEl.textContent = "Could not open that exam.";
    showScreen("screen-configure", "configure");
  }
}

resetConfigure();
checkExamBuilderFeature();
