import { act, fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { RulesSheet } from "@/components/alerts/RulesSheet";
import { Sparkline, sparkPath } from "@/components/alerts/Sparkline";
import { KEYS } from "@/lib/store";

describe("sparkPath", () => {
  it("scales min to the bottom and max to the top", () => {
    const { points } = sparkPath([10, 20, 15], 100, 20, 2);
    expect(points[0]).toEqual([2, 18]);
    expect(points[1]).toEqual([50, 2]);
    expect(points[2]?.[0]).toBe(98);
  });
  it("draws a flat series at mid-height with no NaN", () => {
    const { d, points } = sparkPath([5, 5, 5, 5], 100, 20, 2);
    expect(d).not.toContain("NaN");
    expect(points.every(([, y]) => y === 10)).toBe(true);
  });
  it("handles one point and no points", () => {
    expect(sparkPath([7], 100, 20, 2).d).not.toContain("NaN");
    expect(sparkPath([], 100, 20, 2).d).toBe("");
  });
});

describe("Sparkline", () => {
  it("describes its range for screen readers", () => {
    render(<Sparkline values={[1158.9, 1200, 1308.5]} />);
    expect(screen.getByRole("img")).toHaveAccessibleName("20-day close, from ₹1,158.90 to ₹1,308.50");
  });
});

describe("RulesSheet", () => {
  it("clamps invalid input and saves the rules on the device", async () => {
    render(<RulesSheet open onClose={() => {}} symbols={["TCS", "M&M"]} />);
    fireEvent.change(screen.getByLabelText("Volume multiple"), { target: { value: "0.2" } });
    fireEvent.change(screen.getByLabelText("Price move (%)"), { target: { value: "75" } });
    fireEvent.click(screen.getByLabelText("Dividend"));
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Save rules" }));
      await Promise.resolve();
    });
    const saved = JSON.parse(localStorage.getItem(KEYS.rules) ?? "{}");
    expect(saved.volume_multiple).toBe(1);
    expect(saved.price_move_pct).toBe(20);
    expect(saved.categories).toContain("dividend");
  });
  it("adds a per-stock override, including a symbol with an ampersand", async () => {
    render(<RulesSheet open onClose={() => {}} symbols={["TCS", "M&M"]} />);
    fireEvent.change(screen.getByLabelText("Add a stock"), { target: { value: "M&M" } });
    fireEvent.click(screen.getByLabelText("Mute M&M"));
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Save rules" }));
      await Promise.resolve();
    });
    const saved = JSON.parse(localStorage.getItem(KEYS.rules) ?? "{}");
    expect(saved.overrides["M&M"]).toEqual({ volume_multiple: null, price_move_pct: null, muted: true });
  });
});

describe("AlertLog", () => {
  it("shows the newest 8, names filing alerts by category, and expands on request", async () => {
    const { AlertLog } = await import("@/components/alerts/AlertLog");
    const { readFileSync } = await import("node:fs");
    const { join } = await import("node:path");
    const alerts = JSON.parse(readFileSync(join(__dirname, "fixtures", "alerts.json"), "utf8")).alerts;
    render(<AlertLog alerts={alerts} window={{ start: "2026-10-31T00:00:00+05:30", end: "2026-11-07T18:00:00+05:30" }} />);
    expect(screen.getAllByRole("listitem")).toHaveLength(8);
    expect(screen.getAllByText("Fund-raise").length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole("button", { name: `Show all ${alerts.length}` }));
    expect(screen.getAllByRole("listitem")).toHaveLength(alerts.length);
  });
});

describe("alert links (final review I5)", () => {
  it("open Today on the alert log's own window, for that visit only (Plan 8)", async () => {
    const { AlertLog } = await import("@/components/alerts/AlertLog");
    const { readFileSync } = await import("node:fs");
    const { join } = await import("node:path");
    const data = JSON.parse(readFileSync(join(__dirname, "fixtures", "alerts.json"), "utf8"));
    render(<AlertLog alerts={data.alerts} window={data.window} />);
    const link = screen.getAllByRole("link").find((a) => a.getAttribute("href")?.includes("#story-")) as HTMLElement;
    const href = link.getAttribute("href") as string;
    const url = new URL(href, "https://finn.test");
    expect(url.pathname).toBe("/");
    expect(url.searchParams.get("from")).toBe(data.window.start);
    expect(url.searchParams.get("to")).toBe(data.window.end);
    expect(url.hash.startsWith("#story-")).toBe(true);
    fireEvent.click(link);
    expect(localStorage.getItem(KEYS.window)).toBeNull(); // the reader's own window is untouched
  });
});

describe("rangeFromSearch (Plan 8)", () => {
  it("reads a one-off window from ?from=&to=, and ignores anything malformed", async () => {
    const { rangeFromSearch } = await import("@/lib/store");
    const start = "2026-11-06T11:24:22+05:30";
    const end = "2026-11-13T11:24:22+05:30";
    const q = `?from=${encodeURIComponent(start)}&to=${encodeURIComponent(end)}`;
    expect(rangeFromSearch(q)).toEqual({ kind: "range", start, end });
    expect(rangeFromSearch("")).toBeNull();
    expect(rangeFromSearch("?from=yesterday&to=today")).toBeNull();
    expect(rangeFromSearch(`?from=${encodeURIComponent(end)}&to=${encodeURIComponent(start)}`)).toBeNull();
  });
});

describe("price provenance (Plan 7)", () => {
  it("names where the prices came from and the session they close (Plan 8)", async () => {
    const { priceCaption } = await import("@/components/alerts/Holdings");
    const now = new Date("2026-11-13T09:00:00+05:30");
    expect(priceCaption("2026-11-12", "NSE end-of-day", now)).toBe("Prices: NSE end-of-day. Close of 12 Nov.");
    expect(priceCaption("2026-11-12", "NSE end-of-day (Yahoo for 3); 2 not updated", now)).toBe(
      "Prices: NSE end-of-day (Yahoo for 3); 2 not updated. Close of 12 Nov.",
    );
    expect(priceCaption("2026-11-12", null, now)).toBe("Prices at the close of 12 Nov.");
    expect(priceCaption(null, null, now)).toBeNull();
  });
  it("takes the session from the newest row, not from when FINN fetched (Plan 8)", async () => {
    const { latestSession } = await import("@/components/alerts/Holdings");
    expect(latestSession([{ date: "2026-11-11" }, { date: "2026-11-12" }, { date: null }])).toBe("2026-11-12");
    expect(latestSession([{ date: null }])).toBeNull();
    expect(latestSession([])).toBeNull();
  });
});
