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
});
