import { readFileSync } from "node:fs";
import { join } from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";
import { BuildError, buildDossier, parseFrames } from "@/lib/sse";

const fixture = (n: string) => readFileSync(join(__dirname, "fixtures", n), "utf8");

function streamOf(text: string, chunk = 97): Response {
  const bytes = new TextEncoder().encode(text);
  const body = new ReadableStream<Uint8Array>({
    start(c) {
      for (let i = 0; i < bytes.length; i += chunk) c.enqueue(bytes.slice(i, i + chunk));
      c.close();
    },
  });
  return new Response(body, { status: 200, headers: { "content-type": "text/event-stream" } });
}

afterEach(() => vi.unstubAllGlobals());

describe("parseFrames", () => {
  it("splits complete frames, ignores comments and keeps the remainder", () => {
    const { events, rest } = parseFrames('event: progress\ndata: {"msg":"a"}\n\n: ping\n\nevent: progress\ndata: {"m');
    expect(events).toEqual([{ event: "progress", data: '{"msg":"a"}' }]);
    expect(rest).toBe('event: progress\ndata: {"m');
  });
  it("handles CRLF line endings", () => {
    const { events } = parseFrames('event: error\r\ndata: {"detail":"x"}\r\n\r\n');
    expect(events).toEqual([{ event: "error", data: '{"detail":"x"}' }]);
  });
});

describe("buildDossier", () => {
  it("reports progress and resolves with the dossier and excerpts (chunked stream)", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => streamOf(fixture("build-BAJFINANCE.sse"))));
    const msgs: string[] = [];
    const out = await buildDossier("BAJFINANCE", { onProgress: (m) => msgs.push(m) });
    expect(msgs.length).toBe(3);
    expect(out.dossier.symbol).toBe("BAJFINANCE");
    expect(typeof out.excerpts).toBe("object");
    expect("excerpts" in out.dossier).toBe(false);
  });
  it("works when a proxy buffers the whole stream", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => streamOf(fixture("build-BAJFINANCE.sse"), 1 << 24)));
    await expect(buildDossier("BAJFINANCE", {})).resolves.toHaveProperty("dossier");
  });
  it("rejects with the server's detail on an error event", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => streamOf(fixture("build-error.sse"))));
    const err = await buildDossier("ZZZZ", {}).catch((e) => e);
    expect(err).toBeInstanceOf(BuildError);
    expect(err).toMatchObject({ kind: "error", detail: "ZZZZ not found on screener" });
  });
  it("rejects as incomplete when the stream ends without done", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => streamOf(fixture("build-incomplete.sse"))));
    await expect(buildDossier("BAJFINANCE", {})).rejects.toMatchObject({ kind: "incomplete" });
  });
  it("rejects as error on a non-200 response", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("bad", { status: 502 })));
    await expect(buildDossier("X", {})).rejects.toMatchObject({ kind: "error" });
  });
});
