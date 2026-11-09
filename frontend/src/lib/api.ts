export const API_BASE = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/+$/, "");
export const TIMEOUT_MS = 15_000;
export const UNREACHABLE = "Couldn't reach FINN's server";
/** Fired with the saved-at time when the service worker answered from its cache, null when live. */
export const OFFLINE_EVENT = "finn:offline";

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly detail: string,
  ) {
    super(status === 0 ? UNREACHABLE : detail);
    this.name = "ApiError";
  }
}

/** An NSE symbol as a path segment: "m&m" → "M%26M". */
export function symbolPath(symbol: string): string {
  return encodeURIComponent(symbol.trim().toUpperCase());
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), TIMEOUT_MS);
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, { ...init, signal: ctrl.signal });
  } catch {
    throw new ApiError(0, UNREACHABLE);
  } finally {
    clearTimeout(timer);
  }
  if (typeof window !== "undefined") {
    const saved = res.headers.get("x-finn-offline");
    window.dispatchEvent(new CustomEvent(OFFLINE_EVENT, { detail: saved === null ? null : saved }));
  }
  if (!res.ok) {
    let detail = `The server answered ${res.status}`;
    try {
      const body = await res.json();
      if (typeof body?.detail === "string") detail = body.detail;
    } catch {
      // not JSON; keep the status line
    }
    throw new ApiError(res.status, detail);
  }
  return (await res.json()) as T;
}

export function apiGet<T>(path: string): Promise<T> {
  return request<T>(path);
}

export function apiPost<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
}
