import { renderHook, waitFor } from "@testing-library/react";
import { SWRConfig } from "swr";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useDossier } from "@/lib/hooks";

const wrapper = ({ children }: { children: React.ReactNode }) => (
  <SWRConfig value={{ provider: () => new Map(), dedupingInterval: 0 }}>{children}</SWRConfig>
);

afterEach(() => vi.unstubAllGlobals());

describe("useDossier", () => {
  it("treats 404 as not built, not as an error", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ detail: "not built" }), { status: 404 })));
    const { result } = renderHook(() => useDossier("ABC"), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.data).toBeNull();
    expect(result.current.error).toBeUndefined();
  });
  it("surfaces other failures as errors", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ detail: "boom" }), { status: 500 })));
    const { result } = renderHook(() => useDossier("ABC"), { wrapper });
    await waitFor(() => expect(result.current.error).toBeDefined());
    expect(result.current.error?.message).toBe("boom");
  });
  it("requests the encoded symbol", async () => {
    const f = vi.fn(async (_u: string) => new Response(JSON.stringify({ symbol: "M&M" }), { status: 200 }));
    vi.stubGlobal("fetch", f);
    renderHook(() => useDossier("m&m"), { wrapper });
    await waitFor(() => expect(f).toHaveBeenCalled());
    expect(f.mock.calls[0]?.[0]).toMatch(/\/research\/M%26M$/);
  });
});
