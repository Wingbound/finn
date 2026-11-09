import { fireEvent, render, screen, within } from "@testing-library/react";
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { SWRConfig } from "swr";
import { describe, expect, it } from "vitest";
import { DossierView } from "@/components/dossier/DossierView";
import { splitLedger } from "@/components/dossier/LedgerSection";
import { barGeometry } from "@/components/dossier/MiniBars";
import { findQuote } from "@/components/dossier/SourceSheet";
import type { Dossier } from "@/lib/types";

const DIR = join(__dirname, "fixtures");
const load = (n: string): Dossier => JSON.parse(readFileSync(join(DIR, n), "utf8"));
const all = readdirSync(DIR).filter((f) => f.startsWith("dossier-"));
const wrap = (ui: React.ReactNode) => <SWRConfig value={{ provider: () => new Map() }}>{ui}</SWRConfig>;

describe("DossierView", () => {
  it.each(all)("renders %s", (f) => {
    render(wrap(<DossierView dossier={load(f)} />));
    expect(screen.getByRole("heading", { level: 1 })).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/NaN|undefined/);
  });

  it.each(["ledger", "snapshot", "trajectory", "health"] as const)("survives a missing %s and says why", (k) => {
    const d = { ...load("dossier-PERSISTENT.json"), [k]: null, notes: ["Snapshot unavailable (model unavailable)"] };
    render(wrap(<DossierView dossier={d} />));
    expect(document.body.textContent).not.toMatch(/NaN|undefined/);
    if (k === "snapshot") expect(screen.getAllByText("Snapshot unavailable (model unavailable)").length).toBeGreaterThan(0);
    else expect(screen.getAllByText("Not available for this company.").length).toBeGreaterThan(0);
  });

  it("labels a dropped promise as not mentioned again", () => {
    render(wrap(<DossierView dossier={load("dossier-PERSISTENT.json")} />));
    expect(screen.getAllByText("Not mentioned again").length).toBeGreaterThan(0);
    expect(screen.queryByText(/^Dropped$/)).toBeNull();
  });

  it("never sets a FACTS citation in the quote font", () => {
    render(wrap(<DossierView dossier={load("dossier-PERSISTENT.json")} />));
    const facts = screen.getAllByRole("button", { name: /Computed from filed financials/ });
    expect(facts.length).toBeGreaterThan(0);
    for (const b of facts) expect(b.closest(".quote")).toBeNull();
  });

  it("says when a dossier came from the cache", () => {
    const d = load("dossier-PERSISTENT.json");
    render(wrap(<DossierView dossier={{ ...d, cost: { calls: 9, cached: 9, usd_list_price: 0 } }} />));
    expect(screen.getByText(/Served from cache/)).toBeInTheDocument();
  });

  it("states the cost of a fresh build", () => {
    const d = load("dossier-PERSISTENT.json");
    render(wrap(<DossierView dossier={{ ...d, cost: { calls: 9, cached: 0, usd_list_price: 0.0332 }, build_seconds: 93.4 }} />));
    expect(screen.getByText("9 model calls, $0.033 at list price, 93 s to build.")).toBeInTheDocument();
  });

  it("shows credibility only when the ledger has enough resolved promises", () => {
    const d = load("dossier-PERSISTENT.json");
    const { unmount } = render(wrap(<DossierView dossier={d} />));
    expect(screen.getByText(/Credibility 67%/)).toBeInTheDocument();
    unmount();
    render(wrap(<DossierView dossier={{ ...d, ledger: { ...d.ledger!, credibility_pct: null } }} />));
    expect(screen.queryByText(/Credibility/)).toBeNull();
  });

  it("shows a lender's financing margin and no cash-conversion row", () => {
    render(wrap(<DossierView dossier={load("dossier-HDFCBANK.json")} />));
    expect(screen.getAllByText(/Financing margin/).length).toBeGreaterThan(0);
    expect(screen.queryByText(/Cash from operations/)).toBeNull();
  });

  it("opens the source sheet for a FACTS chip with the computed line, not a quote", () => {
    render(wrap(<DossierView dossier={load("dossier-PERSISTENT.json")} />));
    fireEvent.click(screen.getAllByRole("button", { name: /Computed from filed financials/ })[0] as HTMLElement);
    const sheet = screen.getByRole("dialog");
    expect(within(sheet).getByText(/not quoted from a document/)).toBeInTheDocument();
  });
});

describe("splitLedger", () => {
  it("puts the newest call's promises in Open and groups the rest newest first", () => {
    const d = load("dossier-PERSISTENT.json");
    const { open, track } = splitLedger(d);
    expect(open.every((r) => r.promise.made_in === "Q2 FY27")).toBe(true);
    expect(track.map((g) => g.quarter)).toEqual(["Q1 FY27", "Q4 FY26", "Q3 FY26"]);
    // resolved rows lead each group
    for (const g of track) {
      const firstPending = g.rows.findIndex((r) => r.status === "pending");
      if (firstPending >= 0) expect(g.rows.slice(firstPending).every((r) => r.status === "pending")).toBe(true);
    }
    expect(open.length + track.reduce((n, g) => n + g.rows.length, 0)).toBe(d.ledger!.rows.length);
  });
});

describe("barGeometry", () => {
  it("draws negatives below a zero baseline and skips nulls, with no NaN", () => {
    const g = barGeometry([100, null, -50, 200], 200, 80);
    expect(JSON.stringify(g)).not.toContain("NaN");
    expect(g.bars).toHaveLength(3);
    const neg = g.bars.find((b) => b.value === -50)!;
    expect(neg.y).toBeGreaterThanOrEqual(g.zero);
    const pos = g.bars.find((b) => b.value === 200)!;
    expect(pos.y + pos.h).toBeCloseTo(g.zero);
  });
  it("handles an all-null series", () => {
    expect(barGeometry([null, null], 200, 80).bars).toEqual([]);
  });
});

describe("findQuote", () => {
  it("matches across line breaks, spacing and curly quotes", () => {
    const text = "We said:  “the plant\nwill commission” in Q3.";
    const r = findQuote(text, 'the plant will commission"');
    expect(r).not.toBeNull();
    expect(text.slice(r![0], r![1])).toBe("the plant\nwill commission”");
  });
  it("returns null when absent", () => {
    expect(findQuote("abc", "xyz")).toBeNull();
  });
});

describe("citeLabel", () => {
  it("adds the call's month when two calls share a quarter", async () => {
    const { citeLabel } = await import("@/components/dossier/cite");
    const sources = load("dossier-BAJFINANCE.json").sources;
    const t3 = sources.find((s) => s.id === "T3")!;
    const t4 = sources.find((s) => s.id === "T4")!;
    const a = citeLabel({ source_id: "T3", page: 4, quote: "" }, sources);
    const b = citeLabel({ source_id: "T4", page: 4, quote: "" }, sources);
    expect(t3.quarter).toBe(t4.quarter);
    expect(a).not.toBe(b);
    expect(a).toMatch(/^Q4 FY26 call \(\w+ 2026\), p\. 4$/);
  });
  it("keeps the short label when the quarter is unique", async () => {
    const { citeLabel } = await import("@/components/dossier/cite");
    expect(citeLabel({ source_id: "T1", page: 2, quote: "" }, load("dossier-PERSISTENT.json").sources)).toBe("Q2 FY27 call, p. 2");
  });
});

describe("reflow", () => {
  it("joins hard-wrapped lines but keeps paragraph breaks", async () => {
    const { reflow } = await import("@/components/dossier/SourceSheet");
    expect(reflow("a 190\nbasis point impact.\n\nNext para")).toBe("a 190 basis point impact.\n\nNext para");
  });
});
