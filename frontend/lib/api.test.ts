import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "./api";

vi.mock("./supabase", () => ({
  supabase: { auth: { getSession: vi.fn().mockResolvedValue({ data: { session: { access_token: "test-token" } } }) } },
}));

describe("api client", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("uses the Next API rewrite for chat requests", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ answer: "Hi", sources: [], thread_id: "thread-1", title: "Hello" }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(api.chat("Hello", "qwen3:8b")).resolves.toEqual({ answer: "Hi", sources: [], thread_id: "thread-1", title: "Hello" });
    expect(fetchMock).toHaveBeenCalledWith("/api/chat", expect.objectContaining({ method: "POST", headers: expect.any(Headers) }));
  });

  it("surfaces the API error detail", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: "Unavailable" }), { status: 503 })));

    await expect(api.models()).rejects.toThrow("Unavailable");
  });
});
