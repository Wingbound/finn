// Plan 6: results cards show what management said; dossiers show the latest filed quarter.
import { render, screen, within } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { SWRConfig } from "swr";
import { describe, expect, it } from "vitest";
import { DossierView } from "@/components/dossier/DossierView";
import { PromisePanel, paceSentence } from "@/components/today/PromisePanel";
import { StoryCard } from "@/components/today/StoryCard";
import type { Digest, Dossier, PromiseNote } from "@/lib/types";

const load = <T,>(n: string): T => JSON.parse(readFileSync(join(__dirname, "fixtures", n), "utf8"));
const wrap = (ui: React.ReactNode) => <SWRConfig value={{ provider: () => new Map() }}>{ui}</SWRConfig>;
const bajaj = () => load<Digest>("digest-7d.json").stories.find((s) => s.symbol === "BAJFINANCE" && s.category === "results")!;

const note = (over: Partial<PromiseNote> = {}): PromiseNote => ({
  topic: "growth",
  quote: "We expect revenue to grow 15% to 18% in FY27.",
  citation: { source_id: "T2", page: 4, quote: "We expect revenue to grow 15% to 18% in FY27." },
  call: "Q1 FY27 call, p. 4",
  made_in: "Q1 FY27",
  horizon: "FY27",
  target: "15–18%",
  pace: null,
  ...over,
});

describe("PromisePanel", () => {
  it("quotes management in the serif, with the call, target and horizon", () => {
    render(<PromisePanel symbol="ABC" notes={[note()]} />);
    const panel = screen.getByRole("region", { name: "What management said" });
    const quote = within(panel).getByText(/We expect revenue to grow/);
    expect(quote.closest(".quote")).not.toBeNull();
    expect(within(panel).getByText("Q1 FY27 call, p. 4. Target 15–18%, FY27.")).toBeInTheDocument();
    expect(within(panel).getByRole("link", { name: "See the ledger" })).toHaveAttribute("href", "/research/ABC#ledger");
  });

  it("states pace as one quarter beside the target, never as a verdict", () => {
    const n = note({
      pace: { line: "Revenue", actual: 21.6, basis: "YoY growth in Q2 FY27", target_low: 15, target_high: 18, word: "above" },
    });
    expect(paceSentence(n.pace!)).toBe("This quarter: revenue +21.6% YoY, above the 15–18% target. One quarter, not the full year.");
    render(<PromisePanel symbol="ABC" notes={[n]} />);
    expect(screen.getByText(/above the 15–18% target/)).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/\b(kept|missed)\b/i);
  });

  it("words margins and open-ended targets plainly", () => {
    expect(
      paceSentence({ line: "EBITDA margin", actual: 16.1, basis: "margin in Q2 FY27", target_low: 15, target_high: 17, word: "within" }),
    ).toBe("This quarter: EBITDA margin 16.1%, within the 15–17% target. One quarter, not the full year.");
    expect(
      paceSentence({ line: "PAT", actual: 9.5, basis: "YoY growth in Q2 FY27", target_low: 12, target_high: null, word: "below" }),
    ).toBe("This quarter: PAT +9.5% YoY, below the target of at least 12%. One quarter, not the full year.");
  });

  it("renders nothing without notes", () => {
    const { container } = render(<PromisePanel symbol="ABC" notes={[]} />);
    expect(container).toBeEmptyDOMElement();
  });
});

describe("a results story", () => {
  it("shows its company's promises under the numbers", () => {
    render(<StoryCard story={bajaj()} seen={false} onToggleSeen={() => {}} />);
    expect(screen.getByRole("region", { name: "What management said" })).toBeInTheDocument();
  });
  it("shows no panel when the company has no dossier", () => {
    const tata = load<Digest>("digest-7d.json").stories.find((s) => s.symbol === "TATASTEEL" && s.category === "results")!;
    render(<StoryCard story={{ ...tata, promises: [] }} seen={false} onToggleSeen={() => {}} />);
    expect(screen.queryByRole("region", { name: "What management said" })).toBeNull();
  });
});

describe("a dossier", () => {
  it("shows the latest filed quarter when FINN tracks the company", () => {
    render(wrap(<DossierView dossier={load<Dossier>("dossier-BAJFINANCE.json")} />));
    const section = screen.getByRole("region", { name: "Latest filed quarter" });
    expect(within(section).getAllByRole("rowheader").map((r) => r.textContent)).toContain("Credit cost");
  });
  it("leaves the section out when there is no card", () => {
    render(wrap(<DossierView dossier={load<Dossier>("dossier-INDIGO.json")} />));
    expect(screen.queryByRole("region", { name: "Latest filed quarter" })).toBeNull();
  });
});
