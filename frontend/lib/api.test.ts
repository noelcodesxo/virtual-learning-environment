import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "./api";

describe("api client", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("uses the Next API rewrite for chat requests", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify({ answer: "Hi", sources: [] }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(api.chat("Hello", "qwen3:8b")).resolves.toEqual({ answer: "Hi", sources: [] });
    expect(fetchMock).toHaveBeenCalledWith("/api/chat", expect.objectContaining({ method: "POST" }));
  });

  it("surfaces the API error detail", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: "Unavailable" }), { status: 503 })),
    );

    await expect(api.models()).rejects.toThrow("Unavailable");
  });

  it("creates and checks exam generation jobs through the API rewrite", async () => {
    const job = {
      id: "job-1",
      status: "queued",
      exam_id: null,
      error: null,
      created_at: "2026-09-21T00:00:00Z",
      updated_at: "2026-09-21T00:00:00Z",
    };
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response(JSON.stringify(job), { status: 202 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ ...job, status: "running" }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(api.createExamJob({ source: "Book", chapter: "Chapter" })).resolves.toEqual(job);
    await expect(api.examJob("job-1")).resolves.toMatchObject({ id: "job-1", status: "running" });
    expect(fetchMock).toHaveBeenNthCalledWith(1, "/api/exam-jobs", expect.objectContaining({ method: "POST" }));
    expect(fetchMock).toHaveBeenNthCalledWith(2, "/api/exam-jobs/job-1", undefined);
  });

  it("uploads document files through the API rewrite", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify({ filename: "book.epub", indexed_chunks: 12 }), { status: 201 }));
    vi.stubGlobal("fetch", fetchMock);
    const file = new File(["epub"], "book.epub", { type: "application/epub+zip" });

    await expect(api.uploadLibraryFile(file)).resolves.toEqual({ filename: "book.epub", indexed_chunks: 12 });
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/library/upload?filename=book.epub",
      expect.objectContaining({ method: "POST", body: file }),
    );
  });

  it("loads the document catalog through the API rewrite", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ documents: [] }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(api.library()).resolves.toEqual({ documents: [] });
    expect(fetchMock).toHaveBeenCalledWith("/api/library", undefined);
  });

  it("deletes document files through the API rewrite", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify({ filename: "book.epub", indexed_chunks: 0 }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(api.deleteLibraryFile("book.epub")).resolves.toEqual({ filename: "book.epub", indexed_chunks: 0 });
    expect(fetchMock).toHaveBeenCalledWith("/api/library/book.epub", { method: "DELETE" });
  });
});
