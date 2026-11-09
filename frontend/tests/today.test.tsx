import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it, vi } from "vitest";
import { Header } from "@/components/today/Header";
import { ResultsGrid } from "@/components/today/ResultsGrid";
import { StaleNotice } from "@/components/today/StaleNotice";
import { StoryList } from "@/components/today/StoryList";
import { KEYS } from "@/lib/store";
import type { Digest, ResultsCard } from "@/lib/types";

const load = <T,>(n: string): T => JSON.parse(readFileSync(join(__dirname, "fixtures", n), "utf8"));

describe("Header", () => {
  const counts = (shown: number) => ({ shown, routine: 37, hidden: 2, filings: 50 });
  it("counts what matters", () => {
    const { rerender } = render(<Header counts={counts(4)} onOpenRoutine={() => {}} />);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("4 things matter");
    rerender(<Header counts={counts(1)} onOpenRoutine={() => {}} />);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("1 thing matters");
    rerender(<Header counts={counts(0)} onOpenRoutine={() => {}} />);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Nothing matters yet");
  });
  it("offers the struck routine count as a way into the drawer", () => {
    const open = vi.fn();
    render(<Header counts={counts(4)} onOpenRoutine={open} />);
    fireEvent.click(screen.getByRole("button", { name: /37 routine filings/ }));
    expect(open).toHaveBeenCalled();
    expect(screen.getByText(/2 pieces of noise dropped/)).toBeInTheDocument();
  });
});

describe("ResultsGrid", () => {
  it("shows a lender's own lines and no EBITDA row", () => {
    render(<ResultsGrid card={load<ResultsCard>("results-BAJFINANCE.json")} />);
    const rows = screen.getAllByRole("rowheader").map((r) => r.textContent ?? "");
    expect(rows.some((r) => r.startsWith("Net interest income"))).toBe(true);
    expect(rows.some((r) => r.startsWith("Credit cost"))).toBe(true);
    expect(rows.some((r) => r.startsWith("EBITDA"))).toBe(false);
  });
  it("shows value, QoQ and YoY with signs, and marks computed lines", () => {
    render(<ResultsGrid card={load<ResultsCard>("results-TATASTEEL.json")} />);
    const ebitda = screen.getByRole("rowheader", { name: /^EBITDA ?\(computed by FINN\)$/ }).closest("tr") as HTMLElement;
    expect(within(ebitda).getByText("₹10,533 cr")).toBeInTheDocument();
    expect(within(ebitda).getByText("+13.7%")).toBeInTheDocument();
    expect(ebitda).toHaveTextContent("†");
    expect(screen.getByText(/Q2 FY27, consolidated/)).toBeInTheDocument();
    expect(screen.getByText("+86 bps")).toBeInTheDocument();
  });
});

describe("StoryList", () => {
  it("marks a story seen, saves it on the device and moves it below the unseen ones", async () => {
    const d = load<Digest>("digest-24h.json");
    render(<StoryList stories={d.stories} subscribed={[]} />);
    const first = d.stories[0]!;
    const before = screen.getAllByRole("article");
    expect(before[0]).toHaveAttribute("data-story", first.id);
    await act(async () => {
      fireEvent.click(within(before[0] as HTMLElement).getByRole("button", { name: /mark .* seen/i }));
      await Promise.resolve();
    });
    const after = screen.getAllByRole("article");
    expect(after.at(-1)).toHaveAttribute("data-story", first.id);
    expect(JSON.parse(localStorage.getItem(KEYS.seen) ?? "[]")).toContain(first.id);
  });
});

describe("StaleNotice", () => {
  it("says how old the newest filing is and offers wider windows", () => {
    const d = load<Digest>("digest-empty.json");
    const widen = vi.fn();
    render(
      <StaleNotice
        latest={d.latest_filing_at}
        window={{ kind: "hours", hours: 24 }}
        onChoose={widen}
        now={new Date("2026-11-09T09:00:00+05:30")}
      />,
    );
    expect(screen.getByText("Nothing new in the last 24 hours.")).toBeInTheDocument();
    expect(screen.getByText(/Newest filing: 7 Nov, 16:58/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Show 7 days" }));
    expect(widen).toHaveBeenCalledWith({ kind: "hours", hours: 168 });
  });
  it("only offers presets that reach the newest filing (final review I4)", () => {
    render(
      <StaleNotice
        latest="2026-11-07T16:58:42+05:30"
        window={{ kind: "hours", hours: 24 }}
        onChoose={() => {}}
        now={new Date("2026-11-11T09:00:00+05:30")}
      />,
    );
    // 88 hours old: 3 days can't reach it, 7 days can
    expect(screen.queryByRole("button", { name: "Show 3 days" })).toBeNull();
    expect(screen.getByRole("button", { name: "Show 7 days" })).toBeInTheDocument();
  });
  it("offers the week up to the newest filing when no preset reaches it (final review I4)", () => {
    const choose = vi.fn();
    render(
      <StaleNotice
        latest="2026-11-07T16:58:42+05:30"
        window={{ kind: "hours", hours: 168 }}
        onChoose={choose}
        now={new Date("2026-11-19T09:00:00+05:30")}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Show the week up to 7 Nov" }));
    const w = choose.mock.calls[0]?.[0];
    expect(w.kind).toBe("range");
    expect(Date.parse(w.end)).toBeGreaterThan(Date.parse("2026-11-07T16:58:42+05:30"));
    expect(Date.parse(w.end) - Date.parse(w.start)).toBeGreaterThanOrEqual(7 * 86_400_000);
  });
});

describe("story times (final review M3, re-graded)", () => {
  it("are relative within a day and absolute beyond it", async () => {
    const { StoryCard } = await import("@/components/today/StoryCard");
    const story = load<Digest>("digest-24h.json").stories[0]!;
    const now = new Date(Date.parse(story.latest_at) + 3 * 86_400_000);
    render(<StoryCard story={story} seen={false} onToggleSeen={() => {}} now={now} />);
    expect(screen.getByText(/^\d{1,2} [A-Z][a-z]{2}, \d{2}:\d{2}$/)).toBeInTheDocument();
    expect(screen.queryByText(/d ago$/)).toBeNull();
  });
});
