import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "./api";

describe("api client", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("uses the Next API rewrite for chat requests", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ answer: "Hi", sources: [] }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(api.chat("Hello", "qwen3:8b")).resolves.toEqual({ answer: "Hi", sources: [] });
    expect(fetchMock).toHaveBeenCalledWith("/api/chat", expect.objectContaining({ method: "POST" }));
  });

  it("surfaces the API error detail", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: "Unavailable" }), { status: 503 })));

    await expect(api.models()).rejects.toThrow("Unavailable");
  });

  it("uploads document files through the API rewrite", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ filename: "book.epub", indexed_chunks: 12 }), { status: 201 }));
    vi.stubGlobal("fetch", fetchMock);
    const file = new File(["epub"], "book.epub", { type: "application/epub+zip" });

    await expect(api.uploadLibraryFile(file)).resolves.toEqual({ filename: "book.epub", indexed_chunks: 12 });
    expect(fetchMock).toHaveBeenCalledWith("/api/library/upload?filename=book.epub", expect.objectContaining({ method: "POST", body: file }));
  });

  it("loads the document catalog through the API rewrite", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ documents: [] }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(api.library()).resolves.toEqual({ documents: [] });
    expect(fetchMock).toHaveBeenCalledWith("/api/library", undefined);
  });

  it("deletes document files through the API rewrite", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ filename: "book.epub", indexed_chunks: 0 }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(api.deleteLibraryFile("book.epub")).resolves.toEqual({ filename: "book.epub", indexed_chunks: 0 });
    expect(fetchMock).toHaveBeenCalledWith("/api/library/book.epub", { method: "DELETE" });
  });
});
