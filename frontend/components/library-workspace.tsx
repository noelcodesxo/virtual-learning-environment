"use client";

import { ChangeEvent, useEffect, useRef, useState } from "react";
import { api } from "../lib/api";
import type { LibraryDocument } from "../lib/types";

const MAX_UPLOAD_BYTES = 50 * 1024 * 1024;

export function LibraryWorkspace() {
  const [documents, setDocuments] = useState<LibraryDocument[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState("");
  const [uploadStatus, setUploadStatus] = useState("");
  const [isUploading, setIsUploading] = useState(false);
  const [expanded, setExpanded] = useState<string | null>(null);
  const uploadInput = useRef<HTMLInputElement>(null);

  async function loadLibrary() {
    setIsLoading(true);
    setError("");
    try {
      const response = await api.library();
      setDocuments(response.documents);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Could not load the library.");
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => { loadLibrary(); }, []);

  async function uploadFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file || isUploading) return;
    if (file.size > MAX_UPLOAD_BYTES) {
      setUploadStatus("File must be 50 MB or smaller.");
      if (uploadInput.current) uploadInput.current.value = "";
      return;
    }

    setIsUploading(true);
    setUploadStatus(`Adding and indexing ${file.name}…`);
    try {
      const uploaded = await api.uploadLibraryFile(file);
      await loadLibrary();
      setUploadStatus(`Added ${uploaded.filename}. It is ready to use.`);
    } catch (requestError) {
      setUploadStatus(requestError instanceof Error ? requestError.message : "Could not add the file.");
    } finally {
      setIsUploading(false);
      if (uploadInput.current) uploadInput.current.value = "";
    }
  }

  return <section className="library-page" aria-labelledby="library-title">
    <header className="workspace-header">
      <div><p className="eyebrow">Your study materials</p><h1 id="library-title">Resources</h1><p>Documents are indexed and ready for chat and exam generation.</p></div>
      <label className="primary-action upload-library"><input ref={uploadInput} type="file" accept=".epub,application/epub+zip,.pdf,application/pdf" onChange={uploadFile} disabled={isUploading} /><span>{isUploading ? "Adding document…" : "Add document"}</span></label>
    </header>
    <p className="upload-status" role="status">{uploadStatus}</p>
    {isLoading ? <div className="workspace-message" role="status">Loading resources…</div> : null}
    {!isLoading && error ? <div className="workspace-message error-state" role="alert"><p>Couldn’t load your resources.</p><button className="text-action" type="button" onClick={loadLibrary}>Try again</button></div> : null}
    {!isLoading && !error && documents.length === 0 ? <div className="workspace-message"><h2>Your library is empty</h2><p>Add an EPUB or PDF to start chatting and building exams from it.</p></div> : null}
    {!isLoading && !error && documents.length > 0 ? <div className="document-list">{documents.map((document) => <article className="document-card" key={document.filename}>
      <div className="document-main"><span className="format-badge">{document.format.toUpperCase()}</span><div><h2>{document.title}</h2><p>{document.chapters.length} {document.chapters.length === 1 ? "chapter" : "chapters"} · Ready</p><span className="document-filename">{document.filename}</span></div></div>
      <button className="text-action" type="button" aria-expanded={expanded === document.filename} onClick={() => setExpanded((current) => current === document.filename ? null : document.filename)}>{expanded === document.filename ? "Hide chapters" : "View chapters"}</button>
      {expanded === document.filename ? <ul className="chapter-list">{document.chapters.map((chapter) => <li key={chapter}>{chapter}</li>)}</ul> : null}
    </article>)}</div> : null}
  </section>;
}
