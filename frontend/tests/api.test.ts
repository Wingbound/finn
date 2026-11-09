import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, UNREACHABLE, apiGet, apiPost, symbolPath } from "@/lib/api";

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("api", () => {
  it("returns parsed JSON", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ ok: true }), { status: 200 })));
    await expect(apiGet("/health")).resolves.toEqual({ ok: true });
  });
  it("posts JSON bodies", async () => {
    const f = vi.fn(async (_url: string, _init?: RequestInit) => new Response("{}", { status: 200 }));
    vi.stubGlobal("fetch", f);
    await apiPost("/digest", { hours: 24 });
    const init = f.mock.calls[0]?.[1];
    expect(init?.method).toBe("POST");
    expect(init?.body).toBe(JSON.stringify({ hours: 24 }));
  });
  it("surfaces the server's detail", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ detail: "not built" }), { status: 404 })));
    await expect(apiGet("/research/X")).rejects.toMatchObject({ status: 404, detail: "not built" });
  });
  it("turns a network failure into the unreachable message", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => Promise.reject(new TypeError("Failed to fetch"))));
    const err = await apiGet<never>("/health").catch((e: ApiError) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err.message).toBe(UNREACHABLE);
  });
  it("times out after 15 s", async () => {
    vi.useFakeTimers();
    vi.stubGlobal(
      "fetch",
      vi.fn(
        (_u: string, init?: RequestInit) =>
          new Promise((_, reject) => init?.signal?.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")))),
      ),
    );
    const p = apiGet<never>("/health").catch((e: ApiError) => e);
    await vi.advanceTimersByTimeAsync(15_001);
    const err = await p;
    expect(err.status).toBe(0);
    expect(err.message).toBe(UNREACHABLE);
  });
  it("encodes symbols for paths", () => {
    expect(symbolPath("m&m")).toBe("M%26M");
  });
});
