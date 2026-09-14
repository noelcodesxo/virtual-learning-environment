"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { api } from "../lib/api";
import type { Source } from "../lib/types";

type Message = { role: "user" | "assistant"; content: string; sources?: Source[]; error?: boolean };
type Thread = { id: string; title: string; messages: Message[] };

const truncate = (text: string) => text.length > 40 ? `${text.slice(0, 39).trimEnd()}…` : text;
const sourceLabel = (source: Source) => [source.book, source.chapter, source.section].filter(Boolean).join(" › ") || "Unknown source";

export function ChatWorkspace() {
  const [models, setModels] = useState<string[]>([]);
  const [model, setModel] = useState("");
  const [modelsError, setModelsError] = useState(false);
  const [threads, setThreads] = useState<Thread[]>([]);
  const [currentThreadId, setCurrentThreadId] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [isSending, setIsSending] = useState(false);

  useEffect(() => {
    api.models().then(({ models: available }) => {
      setModels(available); setModel(available[0] ?? "");
    }).catch(() => setModelsError(true));
  }, []);

  const currentThread = useMemo(() => threads.find((thread) => thread.id === currentThreadId) ?? null, [threads, currentThreadId]);
  const replaceThread = (id: string, updater: (thread: Thread) => Thread) => setThreads((all) => all.map((thread) => thread.id === id ? updater(thread) : thread));

  async function submit(event: FormEvent) {
    event.preventDefault();
    const text = query.trim();
    if (!text || isSending) return;
    setQuery(""); setIsSending(true);
    const id = currentThread?.id ?? crypto.randomUUID();
    if (!currentThread) {
      setThreads((all) => [{ id, title: truncate(text), messages: [] }, ...all]);
      setCurrentThreadId(id);
    }
    const append = (message: Message) => replaceThread(id, (thread) => ({ ...thread, messages: [...thread.messages, message] }));
    append({ role: "user", content: text });
    try {
      const response = await api.chat(text, model);
      append({ role: "assistant", content: response.answer, sources: response.sources });
    } catch (error) {
      append({ role: "assistant", content: error instanceof Error ? error.message : "Could not reach the server.", error: true });
    } finally { setIsSending(false); }
  }

  return <>
    <header className="topbar"><span className="chat-title">{currentThread?.title ?? "New chat"}</span><div className="model-picker">
      <span className={`status-dot${modelsError ? " offline" : ""}`} aria-hidden="true" />
      <span className="sr-only">{modelsError ? "Model server unavailable" : "Model server connected"}</span>
      <select className="model-select" value={model} onChange={(event) => setModel(event.target.value)} disabled={modelsError || models.length === 0}>
        {models.length ? models.map((item) => <option key={item}>{item}</option>) : <option>{modelsError ? "Model server unavailable" : "Loading models…"}</option>}
      </select>
    </div></header>
    <div className="workspace">
      <aside className="workspace-sidebar"><button className="new-chat" type="button" onClick={() => setCurrentThreadId(null)}>＋ <span>New chat</span></button><div className="section-label">Recent</div>
        <div className="recent-list">{threads.map((thread) => <button key={thread.id} type="button" className={`recent-item${thread.id === currentThreadId ? " active" : ""}`} aria-current={thread.id === currentThreadId ? "page" : undefined} onClick={() => setCurrentThreadId(thread.id)}>{thread.title}</button>)}</div>
      </aside>
      <section className="chat-panel" aria-label="Chat"><div className="conversation"><div className="thread" role="log" aria-live="polite" aria-relevant="additions text">
        {!currentThread?.messages.length && <div className="empty-state"><p>Ask a question about the indexed library.</p></div>}
        {currentThread?.messages.map((message, index) => message.role === "user" ? <div className="msg-row user" key={index}><div className="msg-user">{message.content}</div></div> : <div className="msg-assistant" key={index}><div className={`msg-assistant-text${message.error ? " error" : ""}`}>{message.content}</div>{message.sources?.length ? <div className="sources"><span className="sources-label">Sources</span>{message.sources.map((source, sourceIndex) => <span className="source-item" key={sourceIndex}>{sourceLabel(source)}</span>)}</div> : null}</div>)}
        {isSending && <div className="typing" role="status"><span className="sr-only">Thinking…</span><span aria-hidden="true" /><span aria-hidden="true" /><span aria-hidden="true" /></div>}
      </div></div>
      <form className="composer" onSubmit={submit}><label className="sr-only" htmlFor="chat-query">Ask a question</label><div className="composer-inner"><input id="chat-query" className="query-input" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Ask a question…" autoComplete="off" /><button className="send-btn" disabled={isSending} aria-label="Send question">→</button></div></form>
      </section>
    </div>
  </>;
}
