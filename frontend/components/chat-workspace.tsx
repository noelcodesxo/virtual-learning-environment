"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { api } from "../lib/api";
import type { Source } from "../lib/types";

type Message = { role: "user" | "assistant"; content: string; sources?: Source[]; error?: boolean };
type Thread = { id: string; title: string; messages: Message[] };

const truncate = (text: string) => (text.length > 40 ? `${text.slice(0, 39).trimEnd()}…` : text);
const sourceLabel = (source: Source) =>
  [source.book, source.chapter, source.section].filter(Boolean).join(" › ") || "Unknown source";

export function ChatWorkspace() {
  const [models, setModels] = useState<string[]>([]);
  const [model, setModel] = useState("");
  const [modelsError, setModelsError] = useState(false);
  const [threads, setThreads] = useState<Thread[]>([]);
  const [currentThreadId, setCurrentThreadId] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [isSending, setIsSending] = useState(false);
  const [isEditingTitle, setIsEditingTitle] = useState(false);
  const [titleDraft, setTitleDraft] = useState("");

  useEffect(() => {
    api
      .models()
      .then(({ models: available }) => {
        setModels(available);
        setModel(available[0] ?? "");
      })
      .catch(() => setModelsError(true));
  }, []);

  const currentThread = useMemo(
    () => threads.find((thread) => thread.id === currentThreadId) ?? null,
    [threads, currentThreadId],
  );
  const replaceThread = (id: string, updater: (thread: Thread) => Thread) =>
    setThreads((all) => all.map((thread) => (thread.id === id ? updater(thread) : thread)));
  const beginTitleEdit = () => {
    if (!currentThread) return;
    setTitleDraft(currentThread.title);
    setIsEditingTitle(true);
  };
  const saveTitle = () => {
    if (currentThread && titleDraft.trim()) {
      replaceThread(currentThread.id, (thread) => ({ ...thread, title: titleDraft.trim() }));
    }
    setIsEditingTitle(false);
  };

  async function submit(event: FormEvent) {
    event.preventDefault();
    const text = query.trim();
    if (!text || isSending) return;
    setQuery("");
    setIsSending(true);
    const id = currentThread?.id ?? crypto.randomUUID();
    if (!currentThread) {
      setThreads((all) => [{ id, title: truncate(text), messages: [] }, ...all]);
      setCurrentThreadId(id);
    }
    const append = (message: Message) =>
      replaceThread(id, (thread) => ({ ...thread, messages: [...thread.messages, message] }));
    append({ role: "user", content: text });
    try {
      const response = await api.chat(text, model);
      append({ role: "assistant", content: response.answer, sources: response.sources });
    } catch (error) {
      append({
        role: "assistant",
        content: error instanceof Error ? error.message : "Could not reach the server.",
        error: true,
      });
    } finally {
      setIsSending(false);
    }
  }

  return (
    <>
      <header className="topbar">
        <div className="chat-header-controls">
          {isEditingTitle ? (
            <input
              autoFocus
              aria-label="Chat title"
              className="chat-title-input"
              value={titleDraft}
              onBlur={saveTitle}
              onChange={(event) => setTitleDraft(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") saveTitle();
                if (event.key === "Escape") setIsEditingTitle(false);
              }}
            />
          ) : (
            <button
              className="chat-title"
              type="button"
              onClick={beginTitleEdit}
              disabled={!currentThread}
              aria-label={currentThread ? "Rename chat" : "New chat"}
            >
              {currentThread?.title ?? "New chat"}
            </button>
          )}
          {threads.length ? (
            <select
              className="thread-picker"
              aria-label="Recent chats"
              value={currentThreadId ?? ""}
              onChange={(event) => setCurrentThreadId(event.target.value || null)}
            >
              <option value="">New chat</option>
              {threads.map((thread) => (
                <option value={thread.id} key={thread.id}>
                  {thread.title}
                </option>
              ))}
            </select>
          ) : null}
          <button
            className="header-action"
            type="button"
            onClick={() => {
              setCurrentThreadId(null);
              setIsEditingTitle(false);
            }}
          >
            New chat
          </button>
        </div>
        <div className="model-picker">
          <span className={`status-dot${modelsError ? " offline" : ""}`} aria-hidden="true" />
          <span className="sr-only">{modelsError ? "Model server unavailable" : "Model server connected"}</span>
          <select
            className="model-select"
            value={model}
            onChange={(event) => setModel(event.target.value)}
            disabled={modelsError || models.length === 0}
          >
            {models.length ? (
              models.map((item) => <option key={item}>{item}</option>)
            ) : (
              <option>{modelsError ? "Model server unavailable" : "Loading models…"}</option>
            )}
          </select>
        </div>
      </header>
      <section className="chat-panel" aria-label="Chat">
        <div className="conversation">
          <div className="thread" role="log" aria-live="polite" aria-relevant="additions text">
            {!currentThread?.messages.length && (
              <div className="empty-state">
                <p>Ask a question about the indexed library.</p>
              </div>
            )}
            {currentThread?.messages.map((message, index) =>
              message.role === "user" ? (
                <div className="msg-row user" key={index}>
                  <span className="message-avatar user-avatar" aria-hidden="true">
                    <svg viewBox="0 0 24 24">
                      <circle cx="12" cy="8" r="3.25" />
                      <path d="M5.5 20c.8-3.35 3.02-5 6.5-5s5.7 1.65 6.5 5" />
                    </svg>
                  </span>
                  <div className="msg-user">{message.content}</div>
                </div>
              ) : (
                <div className="msg-assistant" key={index}>
                  <span className="message-avatar assistant-avatar" aria-hidden="true">
                    <svg viewBox="0 0 24 24">
                      <rect x="5" y="7" width="14" height="11" rx="2" />
                      <path d="M12 4v3M9 12h.01M15 12h.01M9 15h6" />
                    </svg>
                  </span>
                  <div className={`msg-assistant-text${message.error ? " error" : ""}`}>{message.content}</div>
                  {message.sources?.length ? (
                    <div className="sources">
                      <span className="sources-label">Sources</span>
                      {message.sources.map((source, sourceIndex) => (
                        <span className="source-item" key={sourceIndex}>
                          {sourceLabel(source)}
                        </span>
                      ))}
                    </div>
                  ) : null}
                </div>
              ),
            )}
            {isSending && (
              <div className="typing" role="status">
                <span className="sr-only">Thinking…</span>
                <span aria-hidden="true" />
                <span aria-hidden="true" />
                <span aria-hidden="true" />
              </div>
            )}
          </div>
        </div>
        <form className="composer" onSubmit={submit}>
          <label className="sr-only" htmlFor="chat-query">
            Ask a question
          </label>
          <div className="composer-inner">
            <input
              id="chat-query"
              className="query-input"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Ask a question…"
              autoComplete="off"
            />
            <button className="send-btn" disabled={isSending || !query.trim()} aria-label="Send question">
              <svg viewBox="0 0 20 20" aria-hidden="true">
                <path d="M3 3.5 17 10 3 16.5l2.25-5.1H11v-2.8H5.25L3 3.5Z" />
              </svg>
            </button>
          </div>
        </form>
      </section>
    </>
  );
}
