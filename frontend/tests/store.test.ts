import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  DEFAULT_RULES,
  KEYS,
  SEEN_CAP,
  readStore,
  useStored,
  validateFloor,
  validateRules,
  validateSeen,
  validateWindow,
  writeStore,
} from "@/lib/store";

afterEach(() => vi.restoreAllMocks());

describe("readStore", () => {
  it("returns the default for corrupt JSON", () => {
    localStorage.setItem(KEYS.rules, "{bad");
    expect(readStore(KEYS.rules, DEFAULT_RULES, validateRules)).toEqual(DEFAULT_RULES);
  });
  it("returns the default when storage throws", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("SecurityError");
    });
    expect(readStore(KEYS.floor, "important", validateFloor)).toBe("important");
  });
  it("reads a valid stored value", () => {
    localStorage.setItem(KEYS.floor, JSON.stringify("critical"));
    expect(readStore(KEYS.floor, "important", validateFloor)).toBe("critical");
  });
});

describe("writeStore", () => {
  it("reports failure without throwing when storage is blocked", () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("QuotaExceededError");
    });
    expect(writeStore(KEYS.floor, "critical")).toBe(false);
  });
});

describe("validateRules", () => {
  it("clamps out-of-range numbers to the UI's bounds", () => {
    const r = validateRules({ ...DEFAULT_RULES, volume_multiple: 0.1, price_move_pct: 500, lookback: 3 });
    expect(r).toMatchObject({ volume_multiple: 1, price_move_pct: 20, lookback: 5 });
  });
  it("drops unknown categories and bad overrides", () => {
    const r = validateRules({
      ...DEFAULT_RULES,
      categories: ["results", "nonsense"],
      overrides: { TCS: { volume_multiple: 3, muted: true }, "bad key!": { muted: true }, INFY: "x" },
    });
    expect(r?.categories).toEqual(["results"]);
    expect(Object.keys(r?.overrides ?? {})).toEqual(["TCS"]);
    expect(r?.overrides.TCS).toEqual({ volume_multiple: 3, price_move_pct: null, muted: true });
  });
  it("keeps M&M as an override key", () => {
    expect(Object.keys(validateRules({ overrides: { "M&M": { muted: true } } })?.overrides ?? {})).toEqual(["M&M"]);
  });
  it("rejects non-objects", () => {
    expect(validateRules("x")).toBeNull();
    expect(validateRules([1])).toBeNull();
  });
});

describe("other validators", () => {
  it("accepts only the three floors", () => {
    expect(validateFloor("everything")).toBe("everything");
    expect(validateFloor("all")).toBeNull();
  });
  it("accepts an hours window or an ordered range", () => {
    expect(validateWindow({ kind: "hours", hours: 72 })).toEqual({ kind: "hours", hours: 72 });
    expect(validateWindow({ kind: "hours", hours: -1 })).toBeNull();
    expect(validateWindow({ kind: "range", start: "2026-11-02T00:00", end: "2026-11-01T00:00" })).toBeNull();
  });
  it("caps seen ids, keeping the newest", () => {
    const ids = Array.from({ length: SEEN_CAP + 10 }, (_, i) => `s${i}`);
    const out = validateSeen(ids) ?? [];
    expect(out).toHaveLength(SEEN_CAP);
    expect(out.at(-1)).toBe(`s${SEEN_CAP + 9}`);
  });
});

describe("useStored", () => {
  it("shares a value between hooks on the same key", async () => {
    const a = renderHook(() => useStored(KEYS.floor, "important", validateFloor));
    const b = renderHook(() => useStored(KEYS.floor, "important", validateFloor));
    await act(async () => {
      a.result.current[1]("critical");
      await Promise.resolve();
    });
    expect(b.result.current[0]).toBe("critical");
    expect(JSON.parse(localStorage.getItem(KEYS.floor) ?? "null")).toBe("critical");
  });
  it("still works for the session when storage is blocked", async () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    const h = renderHook(() => useStored(KEYS.floor, "important", validateFloor));
    await act(async () => {
      h.result.current[1]("everything");
      await Promise.resolve();
    });
    expect(h.result.current[0]).toBe("everything");
  });
});
