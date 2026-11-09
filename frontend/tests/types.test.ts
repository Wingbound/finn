// Every fixture the UI is tested against was captured from the real API
// (backend/scripts/export_fixtures.py). These checks fail when the backend's shape drifts
// from src/lib/types.ts in a field the UI reads.
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { CATEGORIES } from "@/lib/types";

const DIR = join(__dirname, "fixtures");
const load = (name: string) => JSON.parse(readFileSync(join(DIR, name), "utf8"));
const files = readdirSync(DIR);

const isStr = (v: unknown) => typeof v === "string";
const isNum = (v: unknown) => typeof v === "number" && Number.isFinite(v);
const numOrNull = (v: unknown) => v === null || isNum(v);
const strOrNull = (v: unknown) => v === null || isStr(v);
const iso = (v: unknown) => isStr(v) && Number.isFinite(Date.parse(v as string));

function checkStory(s: Record<string, any>) {
  expect(isStr(s.id) && isStr(s.symbol) && isStr(s.company)).toBe(true);
  expect(CATEGORIES).toContain(s.category);
  expect(["critical", "important", "routine", "noise"]).toContain(s.tier);
  expect(iso(s.latest_at)).toBe(true);
  expect(isStr(s.headline.filing.seq_id) && isStr(s.headline.filing.subject)).toBe(true);
  expect(strOrNull(s.headline.filing.pdf_url)).toBe(true);
  expect(Array.isArray(s.headline.reasons)).toBe(true);
  expect(Array.isArray(s.members) && s.members.length >= 1).toBe(true);
  expect(Array.isArray(s.people)).toBe(true);
  if (s.results) checkResults(s.results);
  if (s.brief) {
    expect(isStr(s.brief.one_liner)).toBe(true);
    expect(Array.isArray(s.brief.facts)).toBe(true);
    expect(strOrNull(s.brief.quote)).toBe(true);
  }
  for (const p of s.people) {
    expect(isStr(p.name) && typeof p.incoming === "boolean").toBe(true);
    expect(strOrNull(p.role) && strOrNull(p.profile) && strOrNull(p.effective)).toBe(true);
  }
}

function checkResults(r: Record<string, any>) {
  expect(isStr(r.period_label)).toBe(true);
  expect(["consolidated", "standalone"]).toContain(r.basis);
  expect(["indas", "nbfc", "bank"]).toContain(r.format);
  for (const m of r.metrics) {
    expect(isStr(m.key) && isStr(m.label)).toBe(true);
    expect(numOrNull(m.value) && numOrNull(m.qoq_pct) && numOrNull(m.yoy_pct)).toBe(true);
    expect(typeof m.computed).toBe("boolean");
  }
  for (const m of r.margins) {
    expect(numOrNull(m.value_pct) && numOrNull(m.qoq_bps) && numOrNull(m.yoy_bps)).toBe(true);
  }
  expect(Array.isArray(r.notes)).toBe(true);
}

function checkCitation(c: Record<string, any>) {
  expect(isStr(c.source_id) && isNum(c.page) && isStr(c.quote)).toBe(true);
}

describe("captured API fixtures match the types the UI reads", () => {
  it("has the fixtures the tests rely on", () => {
    for (const f of ["digest-24h.json", "digest-7d.json", "digest-empty.json", "portfolio.json", "alerts.json", "research-list.json"]) {
      expect(files).toContain(f);
    }
    expect(files.some((f) => f.startsWith("dossier-"))).toBe(true);
    expect(files.some((f) => f.endsWith(".sse"))).toBe(true);
  });

  it.each(files.filter((f) => f.startsWith("digest-")))("%s", (f) => {
    const d = load(f);
    expect(iso(d.window.start) && iso(d.window.end)).toBe(true);
    expect(d.latest_filing_at === null || iso(d.latest_filing_at)).toBe(true);
    for (const k of ["shown", "routine", "hidden", "filings"]) expect(isNum(d.counts[k])).toBe(true);
    expect(d.stories.length).toBe(d.counts.shown);
    d.stories.forEach(checkStory);
    for (const [cat, stories] of Object.entries(d.routine)) {
      expect(CATEGORIES).toContain(cat);
      (stories as any[]).forEach(checkStory);
    }
    for (const h of d.hidden) expect(isStr(h.symbol) && isStr(h.subject) && iso(h.filed_at)).toBe(true);
  });

  it("portfolio.json", () => {
    const p = load("portfolio.json");
    expect(p.holdings.length).toBeGreaterThan(0);
    for (const h of p.holdings) {
      expect(isStr(h.symbol) && isStr(h.name) && isStr(h.size)).toBe(true);
      expect(numOrNull(h.close) && numOrNull(h.change_pct) && numOrNull(h.vol_ratio)).toBe(true);
      expect(Array.isArray(h.spark) && h.spark.every(isNum)).toBe(true);
    }
  });

  it("alerts.json", () => {
    const a = load("alerts.json");
    for (const x of a.alerts) {
      expect(["volume", "price", "filing"]).toContain(x.kind);
      expect(isStr(x.symbol) && isStr(x.date) && isStr(x.message)).toBe(true);
      expect(isNum(x.value) && isNum(x.threshold)).toBe(true);
      expect(strOrNull(x.story_id) && strOrNull(x.seq_id)).toBe(true);
    }
  });

  it.each(files.filter((f) => f.startsWith("results-")))("%s", (f) => checkResults(load(f)));

  it("research-list.json carries the ledger tally", () => {
    const list = load("research-list.json");
    expect(list.length).toBeGreaterThan(0);
    for (const r of list) {
      expect(isStr(r.symbol) && iso(r.built_at)).toBe(true);
      expect(typeof r.counts.ledger).toBe("object");
      expect(isNum(r.counts.ledger_rows)).toBe(true);
    }
  });

  it.each(files.filter((f) => f.startsWith("dossier-")))("%s", (f) => {
    const d = load(f);
    expect(isStr(d.symbol) && iso(d.built_at) && isNum(d.build_seconds)).toBe(true);
    for (const s of d.sources) {
      expect(isStr(s.id) && isStr(s.title) && isStr(s.url)).toBe(true);
      expect(s.pages).toBeUndefined();
    }
    if (d.ledger) {
      for (const r of d.ledger.rows) {
        expect(["kept", "partly", "missed", "pending", "dropped"]).toContain(r.status);
        expect(["computed", "judged"]).toContain(r.method);
        checkCitation(r.promise.citation);
        expect(isStr(r.promise.made_in) && isStr(r.promise.topic) && isStr(r.rationale)).toBe(true);
        if (r.evidence) checkCitation(r.evidence);
      }
      expect(numOrNull(d.ledger.credibility_pct)).toBe(true);
    }
    for (const p of [...(d.snapshot?.summary ?? []), ...d.bull, ...d.bear]) {
      expect(isStr(p.text)).toBe(true);
      checkCitation(p.citation);
    }
    if (d.trajectory) {
      const t = d.trajectory;
      for (const k of ["revenue", "operating_profit", "margin_pct", "pat"]) {
        expect(t[k].length).toBe(t.years.length);
        expect(t[k].every(numOrNull)).toBe(true);
      }
      expect(typeof t.lender).toBe("boolean");
    }
    if (d.health) expect(Array.isArray(d.health.flags)).toBe(true);
    expect(Array.isArray(d.notes)).toBe(true);
    expect(typeof d.cost).toBe("object");
  });

  it.each(files.filter((f) => f.startsWith("source-")))("%s", (f) => {
    const s = load(f);
    expect(isStr(s.title) && isNum(s.page) && isStr(s.text)).toBe(true);
    checkCitation(s.citation);
  });
});
