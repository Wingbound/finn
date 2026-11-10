import { API_BASE, symbolPath } from "./api";
import type { Dossier, Excerpts } from "./types";

export interface SseEvent {
  event: string;
  data: string;
}

/** Complete frames from an SSE buffer, plus the unfinished tail. Comment frames (": ping") are dropped. */
export function parseFrames(buffer: string): { events: SseEvent[]; rest: string } {
  const text = buffer.replace(/\r\n/g, "\n");
  const parts = text.split("\n\n");
  const rest = parts.pop() ?? "";
  const events: SseEvent[] = [];
  for (const frame of parts) {
    let event = "message";
    const data: string[] = [];
    for (const line of frame.split("\n")) {
      if (line.startsWith(":") || line === "") continue;
      const i = line.indexOf(":");
      const field = i < 0 ? line : line.slice(0, i);
      const value = i < 0 ? "" : line.slice(i + 1).replace(/^ /, "");
      if (field === "event") event = value;
      else if (field === "data") data.push(value);
    }
    if (data.length) events.push({ event, data: data.join("\n") });
  }
  return { events, rest };
}

export class BuildError extends Error {
  constructor(
    readonly kind: "error" | "incomplete",
    readonly detail: string,
  ) {
    super(detail);
    this.name = "BuildError";
  }
}

export const STOPPED = "The build stopped before finishing";

/** The server's build errors, in words a reader can act on; unknown ones pass through. */
export function friendlyBuildError(detail: string): string {
  if (/timed out/i.test(detail)) {
    return "The build ran out of time on the server. Try again: what FINN already read is cached, so it goes faster.";
  }
  if (/^build failed/i.test(detail)) return "The build hit an error on the server. Try again in a minute.";
  return detail;
}

/**
 * Builds (or fetches the fresh cached) dossier through the SSE endpoint. Uses fetch rather than
 * EventSource so it can be cancelled and still parses a response a proxy buffered whole.
 */
export async function buildDossier(
  symbol: string,
  { onProgress, signal }: { onProgress?: (msg: string) => void; signal?: AbortSignal },
): Promise<{ dossier: Dossier; excerpts: Excerpts }> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}/research/${symbolPath(symbol)}/build`, {
      headers: { accept: "text/event-stream" },
      signal,
    });
  } catch (e) {
    if (signal?.aborted) throw e;
    throw new BuildError("error", "Couldn't reach FINN's server");
  }
  if (!res.ok || !res.body) {
    let detail = `The server answered ${res.status}`;
    try {
      const body = await res.json();
      if (typeof body?.detail === "string") detail = body.detail;
    } catch {
      // not JSON; keep the status line
    }
    throw new BuildError("error", detail);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    let chunk: ReadableStreamReadResult<Uint8Array>;
    try {
      chunk = await reader.read();
    } catch (e) {
      if (signal?.aborted) throw e;
      throw new BuildError("incomplete", STOPPED); // the connection dropped mid-stream
    }
    const { done, value } = chunk;
    buffer += decoder.decode(value, { stream: !done });
    const { events, rest } = parseFrames(done ? `${buffer}\n\n` : buffer);
    buffer = rest;
    for (const ev of events) {
      let payload: Record<string, unknown>;
      try {
        payload = JSON.parse(ev.data);
      } catch {
        continue; // a garbled frame; the rest of the stream may still finish the build
      }
      if (ev.event === "progress" && typeof payload?.msg === "string") onProgress?.(payload.msg);
      else if (ev.event === "error")
        throw new BuildError("error", friendlyBuildError(String(payload?.detail ?? "The build failed")));
      else if (ev.event === "done") {
        const { excerpts = {}, ...dossier } = payload;
        return { dossier: dossier as unknown as Dossier, excerpts: excerpts as Excerpts };
      }
    }
    if (done) throw new BuildError("incomplete", STOPPED);
  }
}
