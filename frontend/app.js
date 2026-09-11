const API_BASE = window.API_BASE || "http://localhost:8000";

const recentListEl = document.getElementById("recent-list");
const conversationEl = document.getElementById("conversation");
const chatTitleEl = document.getElementById("chat-title");
const modelSelectEl = document.getElementById("model-select");
const modelStatusEl = document.getElementById("model-status");
const composerEl = document.getElementById("composer");
const queryInputEl = document.getElementById("query-input");
const sendBtnEl = document.getElementById("send-btn");
const newChatBtnEl = document.getElementById("new-chat-btn");

let threads = [];
let currentThreadId = null;
let isSending = false;

function truncate(text, max) {
  return text.length > max ? text.slice(0, max - 1).trimEnd() + "…" : text;
}

function currentThread() {
  return threads.find((thread) => thread.id === currentThreadId) || null;
}

function renderRecentList() {
  recentListEl.innerHTML = "";
  for (const thread of threads) {
    const item = document.createElement("button");
    item.type = "button";
    item.className = "recent-item" + (thread.id === currentThreadId ? " active" : "");
    item.textContent = thread.title;
    item.addEventListener("click", () => {
      currentThreadId = thread.id;
      render();
    });
    recentListEl.appendChild(item);
  }
}

function sourceLabel(source) {
  const parts = [source.book, source.chapter, source.section].filter(Boolean);
  return parts.length ? parts.join(" › ") : "Unknown source";
}

function renderConversation() {
  const thread = currentThread();
  conversationEl.innerHTML = "";

  if (!thread || thread.messages.length === 0) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    empty.innerHTML = "<p>Ask a question about the indexed library.</p>";
    conversationEl.appendChild(empty);
    return;
  }

  const wrap = document.createElement("div");
  wrap.className = "thread";

  for (const message of thread.messages) {
    if (message.role === "user") {
      const row = document.createElement("div");
      row.className = "msg-row user";
      const bubble = document.createElement("div");
      bubble.className = "msg-user";
      bubble.textContent = message.content;
      row.appendChild(bubble);
      wrap.appendChild(row);
    } else if (message.role === "assistant") {
      const box = document.createElement("div");
      box.className = "msg-assistant";

      const text = document.createElement("div");
      text.className = "msg-assistant-text" + (message.error ? " error" : "");
      text.textContent = message.content;
      box.appendChild(text);

      if (message.sources && message.sources.length > 0) {
        const sources = document.createElement("div");
        sources.className = "sources";
        const label = document.createElement("span");
        label.className = "sources-label";
        label.textContent = "Sources";
        sources.appendChild(label);

        const list = document.createElement("div");
        list.className = "source-list";
        for (const source of message.sources) {
          const item = document.createElement("span");
          item.className = "source-item";
          item.textContent = sourceLabel(source);
          list.appendChild(item);
        }
        sources.appendChild(list);
        box.appendChild(sources);
      }

      wrap.appendChild(box);
    } else if (message.role === "pending") {
      const typing = document.createElement("div");
      typing.className = "typing";
      typing.innerHTML = "<span></span><span></span><span></span>";
      wrap.appendChild(typing);
    }
  }

  conversationEl.appendChild(wrap);
  conversationEl.scrollTop = conversationEl.scrollHeight;
}

function render() {
  const thread = currentThread();
  chatTitleEl.textContent = thread ? thread.title : "New chat";
  renderRecentList();
  renderConversation();
}

async function loadModels() {
  try {
    const response = await fetch(`${API_BASE}/models`);
    if (!response.ok) throw new Error(`status ${response.status}`);
    const data = await response.json();

    modelSelectEl.innerHTML = "";
    if (data.models.length === 0) {
      const opt = document.createElement("option");
      opt.textContent = "No models found";
      modelSelectEl.appendChild(opt);
      modelSelectEl.disabled = true;
      modelStatusEl.classList.add("offline");
      return;
    }

    for (const model of data.models) {
      const opt = document.createElement("option");
      opt.value = model;
      opt.textContent = model;
      modelSelectEl.appendChild(opt);
    }
    modelSelectEl.disabled = false;
    modelStatusEl.classList.remove("offline");
    modelStatusEl.title = "Model server connected";
  } catch (err) {
    modelSelectEl.innerHTML = "<option>Model server unavailable</option>";
    modelSelectEl.disabled = true;
    modelStatusEl.classList.add("offline");
    modelStatusEl.title = "Could not reach the model server";
  }
}

function startNewThread(firstQuery) {
  const thread = {
    id: crypto.randomUUID(),
    title: truncate(firstQuery, 40),
    messages: [],
  };
  threads.unshift(thread);
  currentThreadId = thread.id;
  return thread;
}

async function sendQuery(query) {
  if (isSending) return;
  isSending = true;
  sendBtnEl.disabled = true;

  let thread = currentThread();
  if (!thread) {
    thread = startNewThread(query);
  }

  thread.messages.push({ role: "user", content: query });
  thread.messages.push({ role: "pending" });
  render();

  try {
    const response = await fetch(`${API_BASE}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query, model: modelSelectEl.value }),
    });

    thread.messages.pop(); // remove pending indicator

    if (!response.ok) {
      const detail = await response.json().catch(() => ({}));
      thread.messages.push({
        role: "assistant",
        content: detail.detail || `Request failed (${response.status}).`,
        error: true,
      });
    } else {
      const data = await response.json();
      thread.messages.push({
        role: "assistant",
        content: data.answer,
        sources: data.sources,
      });
    }
  } catch (err) {
    thread.messages.pop();
    thread.messages.push({
      role: "assistant",
      content: "Could not reach the server. Is it running?",
      error: true,
    });
  } finally {
    isSending = false;
    sendBtnEl.disabled = false;
    render();
  }
}

composerEl.addEventListener("submit", (event) => {
  event.preventDefault();
  const query = queryInputEl.value.trim();
  if (!query) return;
  queryInputEl.value = "";
  sendQuery(query);
});

newChatBtnEl.addEventListener("click", () => {
  currentThreadId = null;
  render();
});

loadModels();
render();
