import { describe, expect, it } from "vitest";
import { ago, bps, categoryLabel, crore, level, pct, plural, rupees, stamp, statusLabel, times, when } from "@/lib/format";

const M = "−";

describe("money", () => {
  it("groups crore the Indian way", () => {
    expect(crore(123456.7)).toBe("₹1,23,457 cr");
    expect(crore(999)).toBe("₹999 cr");
    expect(crore(12.34)).toBe("₹12.3 cr");
  });
  it("keeps the sign on negatives", () => {
    expect(crore(-1234.5)).toBe(`${M}₹1,235 cr`);
  });
  it("shows a dash for missing values", () => {
    expect(crore(null)).toBe("–");
    expect(crore(Number.NaN)).toBe("–");
  });
  it("formats share prices with paise", () => {
    expect(rupees(1308.5)).toBe("₹1,308.50");
    expect(rupees(123456.789)).toBe("₹1,23,456.79");
  });
});

describe("changes", () => {
  it("signs percentages", () => {
    expect(pct(4.12)).toBe("+4.1%");
    expect(pct(-2)).toBe(`${M}2.0%`);
    expect(pct(0.04)).toBe("0.0%");
    expect(pct(null)).toBe("–");
  });
  it("signs basis points", () => {
    expect(bps(120)).toBe("+120 bps");
    expect(bps(-35)).toBe(`${M}35 bps`);
    expect(bps(0)).toBe("0 bps");
  });
  it("shows levels and multiples unsigned", () => {
    expect(level(21.44)).toBe("21.4%");
    expect(times(2.36)).toBe("2.4×");
  });
});

describe("times in IST", () => {
  const now = new Date("2026-11-09T10:00:00+05:30");
  it("is relative within a day", () => {
    expect(ago("2026-11-09T09:59:40+05:30", now)).toBe("just now");
    expect(when("2026-11-09T09:15:00+05:30", now)).toBe("45 min ago");
    expect(when("2026-11-09T07:00:00+05:30", now)).toBe("3 h ago");
  });
  it("is absolute beyond a day, in IST across the UTC date line", () => {
    // 20:30 UTC on 6 Nov is 02:00 IST on 7 Nov
    expect(when("2026-11-06T20:30:00Z", now)).toBe("7 Nov, 02:00");
    expect(stamp("2026-11-09T09:15:00+05:30", now)).toBe("9 Nov, 09:15");
  });
  it("adds the year when it differs", () => {
    expect(when("2025-12-31T18:00:00+05:30", now)).toBe("31 Dec 2025, 18:00");
  });
});

describe("labels", () => {
  it("names categories in plain words", () => {
    expect(categoryLabel("mna")).toBe("Deal");
    expect(categoryLabel("management_change")).toBe("People");
    expect(categoryLabel("fund_raise")).toBe("Fund-raise");
  });
  it("gives every status a glyph and a word", () => {
    expect(statusLabel("kept")).toEqual({ glyph: "✓", word: "Kept" });
    expect(statusLabel("dropped").word).toBe("Not mentioned again");
  });
  it("pluralises", () => {
    expect(plural(1, "thing")).toBe("1 thing");
    expect(plural(4, "thing")).toBe("4 things");
  });
});
