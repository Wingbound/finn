// Plan 6: results cards show what management said; dossiers show the latest filed quarter.
import { fireEvent, render, screen, within } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { SWRConfig } from "swr";
import { describe, expect, it, vi } from "vitest";
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
  horizon_label: "FY27",
  target: "15–18%",
  target_kind: "target",
  pace: null,
  ...over,
});

describe("PromisePanel", () => {
  it("quotes management in the serif, with the call, target and horizon", () => {
    render(<PromisePanel symbol="ABC" notes={[note()]} />);
    const panel = screen.getByRole("region", { name: "What management said" });
    const quote = within(panel).getByText(/We expect revenue to grow/);
    expect(quote.closest(".quote")).not.toBeNull();
    expect(within(panel).getByText("Q1 FY27 call, p. 4. Target 15–18% for FY27.")).toBeInTheDocument();
    expect(within(panel).getByRole("link", { name: "See the ledger" })).toHaveAttribute("href", "/research/ABC#ledger");
  });

  it("states pace as one quarter beside the target, never as a verdict", () => {
    const n = note({
      pace: { line: "Revenue", actual: 21.6, basis: "YoY growth in Q2 FY27", target_low: 15, target_high: 18, word: "above", scope: "year" },
    });
    expect(paceSentence(n.pace!)).toBe("This quarter: revenue +21.6% YoY, above the 15–18% target. One quarter, not the full year.");
    render(<PromisePanel symbol="ABC" notes={[n]} />);
    expect(screen.getByText(/above the 15–18% target/)).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/\b(kept|missed)\b/i);
  });

  it("words margins and open-ended targets plainly", () => {
    expect(
      paceSentence({ line: "EBITDA margin", actual: 16.1, basis: "margin in Q2 FY27", target_low: 15, target_high: 17, word: "within", scope: "year" }),
    ).toBe("This quarter: EBITDA margin 16.1%, within the 15–17% target. One quarter, not the full year.");
    expect(
      paceSentence({ line: "PAT", actual: 9.5, basis: "YoY growth in Q2 FY27", target_low: 12, target_high: null, word: "below", scope: "year" }),
    ).toBe("This quarter: PAT +9.5% YoY, below the 12% target. One quarter, not the full year.");
  });

  it("renders nothing without notes", () => {
    const { container } = render(<PromisePanel symbol="ABC" notes={[]} />);
    expect(container).toBeEmptyDOMElement();
  });
});

describe("the note's period (Plan 6 review I4, I5, M4)", () => {
  it.each([
    [{ horizon_label: "FY27", target: "15–18%", target_kind: "target" }, "Q1 FY27 call, p. 4. Target 15–18% for FY27."],
    [{ horizon_label: "was due Q1 FY27", target: null }, "Q1 FY27 call, p. 4. Was due Q1 FY27."],
    [{ horizon_label: "Q2 FY27", target: null }, "Q1 FY27 call, p. 4. For Q2 FY27."],
    [
      { horizon: "next year", horizon_label: '"next year", said on the Q4 FY26 call', target: "₹3,500 cr", target_kind: "guided" },
      'Q1 FY27 call, p. 4. Guided ₹3,500 cr. Timing: "next year", said on the Q4 FY26 call.',
    ],
    [{ horizon_label: null, horizon: null, target: "$25–30 mn", target_kind: "figure" }, "Q1 FY27 call, p. 4. Figure quoted: $25–30 mn."],
  ] as [Partial<PromiseNote>, string][])("%o reads %s", (over, text) => {
    render(<PromisePanel symbol="ABC" notes={[note(over)]} />);
    expect(screen.getByText(text)).toBeInTheDocument();
  });

  it("only adds 'not the full year' when the target is for the year", () => {
    const pace = { line: "Revenue", actual: 21.6, basis: "YoY growth in Q2 FY27", target_low: 15, target_high: 18, word: "above" as const };
    expect(paceSentence({ ...pace, scope: "year" })).toMatch(/One quarter, not the full year\.$/);
    expect(paceSentence({ ...pace, scope: "quarter" })).toBe("This quarter: revenue +21.6% YoY, above the 15–18% target set for it.");
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
  it("doesn't point at promises a dossier doesn't have (M8)", () => {
    const d = load<Dossier>("dossier-BAJFINANCE.json");
    render(wrap(<DossierView dossier={{ ...d, ledger: { ...d.ledger!, rows: [] } }} />));
    const section = screen.getByRole("region", { name: "Latest filed quarter" });
    expect(section.textContent).not.toMatch(/promises above/);
  });
  it("leaves the section out when there is no card", () => {
    render(wrap(<DossierView dossier={load<Dossier>("dossier-INDIGO.json")} />));
    expect(screen.queryByRole("region", { name: "Latest filed quarter" })).toBeNull();
  });
});

describe("PromisePanel quotes and headings (Plan 8)", () => {
  // jsdom has no layout: give clamped quotes a measured height, as a phone would
  function layout(scrollHeight: number, clientHeight: number) {
    const sh = vi.spyOn(HTMLElement.prototype, "scrollHeight", "get").mockReturnValue(scrollHeight);
    const ch = vi.spyOn(HTMLElement.prototype, "clientHeight", "get").mockReturnValue(clientHeight);
    return () => {
      sh.mockRestore();
      ch.mockRestore();
    };
  }
  const short = "Revenue to grow 15% to 18% in FY27 on the new plant and exports, with margins steady near sixteen percent.";

  it("offers Show more whenever the clamped quote overflows, however few its words (final review I2)", () => {
    const restore = layout(96, 72);
    try {
      render(<PromisePanel symbol="ABC" notes={[note({ quote: short })]} />);
      const quote = screen.getByText(/Revenue to grow/);
      expect(quote.className).toContain("line-clamp-3");
      const more = screen.getByRole("button", { name: "Show more" });
      fireEvent.click(more);
      expect(more).toHaveAttribute("aria-expanded", "true");
      expect(screen.getByText(/Revenue to grow/).className).not.toContain("line-clamp-3");
    } finally {
      restore();
    }
  });

  it("offers no button when the quote fits in three lines", () => {
    const restore = layout(72, 72);
    try {
      render(<PromisePanel symbol="ABC" notes={[note({ quote: short })]} />);
      expect(screen.queryByRole("button", { name: "Show more" })).toBeNull();
    } finally {
      restore();
    }
  });

  it("names its region from its visible title without adding a heading level", () => {
    render(<PromisePanel symbol="ABC" notes={[note()]} />);
    expect(screen.getByRole("region", { name: "What management said" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { level: 4 })).toBeNull();
  });
});
