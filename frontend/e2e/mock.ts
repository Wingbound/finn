import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import type { Page, Route } from "@playwright/test";
import { API } from "../playwright.config";

const FIX = join(dirname(fileURLToPath(import.meta.url)), "..", "tests", "fixtures");
export const fixture = (name: string) => readFileSync(join(FIX, name), "utf8");
export const json = (name: string) => JSON.parse(fixture(name));

export interface MockOptions {
  digest?: (body: Record<string, unknown>) => string; // fixture name per request body
  missingDossiers?: string[];
  onRequest?: (path: string, body: unknown) => void;
}

/** Serves every API route from tests/fixtures so e2e runs need no backend. */
export async function mockApi(page: Page, opts: MockOptions = {}) {
  await page.route(`${API}/**`, async (route: Route) => {
    const req = route.request();
    const url = new URL(req.url());
    const path = decodeURIComponent(url.pathname);
    const body = req.postData() ? JSON.parse(req.postData() as string) : undefined;
    opts.onRequest?.(path, body);
    const ok = (name: string) =>
      route.fulfill({ status: 200, contentType: "application/json", body: fixture(name) });
    const notFound = (detail: string) =>
      route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ detail }) });

    if (path === "/health") return ok("health.json");
    if (path === "/portfolio") return ok("portfolio.json");
    if (path === "/alerts") return ok("alerts.json");
    if (path === "/digest") return ok(opts.digest ? opts.digest(body ?? {}) : "digest-7d.json");
    if (path === "/research") return ok("research-list.json");
    if (path === "/research/search") {
      const q = (url.searchParams.get("q") ?? "").toLowerCase();
      const hits = [
        { name: "Persistent Systems Ltd", symbol: "PERSISTENT", url: "/company/PERSISTENT/consolidated/" },
        { name: "Pidilite Industries Ltd", symbol: "PIDILITIND", url: "/company/PIDILITIND/consolidated/" },
      ].filter((h) => h.name.toLowerCase().includes(q) || h.symbol.toLowerCase().includes(q));
      return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(hits) });
    }
    let m = path.match(/^\/research\/([^/]+)\/build$/);
    if (m) {
      const sse = fixture("build-BAJFINANCE.sse").replaceAll("BAJFINANCE", m[1] as string);
      return route.fulfill({ status: 200, contentType: "text/event-stream", body: sse });
    }
    m = path.match(/^\/research\/([^/]+)\/source\/([^/]+)\/(\d+)$/);
    if (m) {
      try {
        return ok(`source-${m[1]}.json`);
      } catch {
        return notFound("source page not found");
      }
    }
    m = path.match(/^\/research\/([^/]+)$/);
    if (m) {
      const sym = m[1] as string;
      if (opts.missingDossiers?.includes(sym)) return notFound("not built");
      try {
        return ok(`dossier-${sym}.json`);
      } catch {
        return notFound("not built");
      }
    }
    m = path.match(/^\/results\/(.+)$/);
    if (m) {
      try {
        return ok(`results-${m[1]}.json`);
      } catch {
        return notFound("no results on file");
      }
    }
    if (path.startsWith("/filings/")) return ok("filing.json");
    return notFound(`unmocked ${path}`);
  });
}

/** Collects console errors and page errors for the no-console-errors check. */
export function watchErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on("console", (m) => {
    if (m.type() === "error") errors.push(`${m.text()} ${m.location().url ?? ""}`.trim());
  });
  page.on("pageerror", (e) => errors.push(e.message));
  return errors;
}
