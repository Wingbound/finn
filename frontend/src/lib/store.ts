"use client";

import { useCallback, useEffect, useState } from "react";
import { CATEGORIES, type Category, type Floor, type Rules, type SymbolOverride } from "./types";

// User settings live on the device (DESIGN §7b) and travel with each request. Storage may be
// blocked or hold junk, so every read validates and falls back to a default.

export const KEYS = {
  rules: "finn:v1:rules",
  floor: "finn:v1:floor",
  window: "finn:v1:window",
  seen: "finn:v1:seen",
} as const;

export const SEEN_CAP = 500;
const CHANGED = "finn:store";

export const DEFAULT_RULES: Rules = {
  volume_multiple: 2,
  price_move_pct: 5,
  lookback: 20,
  categories: ["results", "mna", "management_change", "credit_rating", "litigation", "pledging", "fund_raise"],
  overrides: {},
};

/** The rules editor's bounds (inside the backend's own limits). */
export const LIMITS = {
  volume_multiple: [1, 10],
  price_move_pct: [1, 20],
  lookback: [5, 250],
} as const;

export type WindowChoice = { kind: "hours"; hours: number } | { kind: "range"; start: string; end: string };
export const DEFAULT_WINDOW: WindowChoice = { kind: "hours", hours: 24 };
export const DEFAULT_FLOOR: Floor = "important";

type Obj = Record<string, unknown>;
const isObj = (v: unknown): v is Obj => typeof v === "object" && v !== null && !Array.isArray(v);
const finite = (v: unknown): number | null => (typeof v === "number" && Number.isFinite(v) ? v : null);
const clamp = (n: number, [lo, hi]: readonly [number, number]) => Math.min(hi, Math.max(lo, n));
const SYMBOL = /^[A-Z0-9&_-]{1,20}$/;
const KNOWN = new Set<string>(CATEGORIES);

function validateOverride(v: unknown): SymbolOverride | null {
  if (!isObj(v)) return null;
  const vol = finite(v.volume_multiple);
  const price = finite(v.price_move_pct);
  return {
    volume_multiple: vol === null ? null : clamp(vol, LIMITS.volume_multiple),
    price_move_pct: price === null ? null : clamp(price, LIMITS.price_move_pct),
    muted: v.muted === true,
  };
}

export function validateRules(v: unknown): Rules | null {
  if (!isObj(v)) return null;
  const categories = Array.isArray(v.categories)
    ? [...new Set(v.categories.filter((c): c is Category => typeof c === "string" && KNOWN.has(c)))]
    : [...DEFAULT_RULES.categories];
  const overrides: Record<string, SymbolOverride> = {};
  if (isObj(v.overrides)) {
    for (const [sym, raw] of Object.entries(v.overrides)) {
      const o = validateOverride(raw);
      if (o && SYMBOL.test(sym)) overrides[sym] = o;
    }
  }
  return {
    volume_multiple: clamp(finite(v.volume_multiple) ?? DEFAULT_RULES.volume_multiple, LIMITS.volume_multiple),
    price_move_pct: clamp(finite(v.price_move_pct) ?? DEFAULT_RULES.price_move_pct, LIMITS.price_move_pct),
    lookback: Math.round(clamp(finite(v.lookback) ?? DEFAULT_RULES.lookback, LIMITS.lookback)),
    categories,
    overrides,
  };
}

export function validateFloor(v: unknown): Floor | null {
  return v === "critical" || v === "important" || v === "everything" ? v : null;
}

export function validateWindow(v: unknown): WindowChoice | null {
  if (!isObj(v)) return null;
  if (v.kind === "hours") {
    const h = finite(v.hours);
    return h !== null && h > 0 && h <= 24 * 366 ? { kind: "hours", hours: Math.round(h) } : null;
  }
  if (v.kind === "range" && typeof v.start === "string" && typeof v.end === "string") {
    const s = Date.parse(v.start);
    const e = Date.parse(v.end);
    return Number.isFinite(s) && Number.isFinite(e) && s <= e ? { kind: "range", start: v.start, end: v.end } : null;
  }
  return null;
}

export function validateSeen(v: unknown): string[] | null {
  return Array.isArray(v) ? v.filter((x): x is string => typeof x === "string").slice(-SEEN_CAP) : null;
}

export function readStore<T>(key: string, fallback: T, validate: (v: unknown) => T | null): T {
  try {
    const raw = window.localStorage.getItem(key);
    return raw === null ? fallback : (validate(JSON.parse(raw)) ?? fallback);
  } catch {
    return fallback;
  }
}

/** Saves when it can and tells same-page readers; false when storage refused the write. */
export function writeStore(key: string, value: unknown): boolean {
  let saved = true;
  try {
    window.localStorage.setItem(key, JSON.stringify(value));
  } catch {
    saved = false;
  }
  window.dispatchEvent(new CustomEvent(CHANGED, { detail: { key, value } }));
  return saved;
}

/**
 * One stored setting, kept in sync across every component that reads the key.
 * Renders the fallback until mounted, so the server and first client render agree;
 * `ready` turns true once the stored value is in.
 */
export function useStored<T>(
  key: string,
  fallback: T,
  validate: (v: unknown) => T | null,
): [T, (next: T | ((prev: T) => T)) => void, boolean] {
  const [state, setState] = useState({ value: fallback, ready: false });

  useEffect(() => {
    // localStorage exists only on the client: syncing it in after mount is the point.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setState({ value: readStore(key, fallback, validate), ready: true });
    const sameTab = (e: Event) => {
      const d = (e as CustomEvent<{ key: string; value: unknown }>).detail;
      if (d?.key === key) setState({ value: validate(d.value) ?? fallback, ready: true });
    };
    const otherTab = (e: StorageEvent) => {
      if (e.key === key) setState({ value: readStore(key, fallback, validate), ready: true });
    };
    window.addEventListener(CHANGED, sameTab);
    window.addEventListener("storage", otherTab);
    return () => {
      window.removeEventListener(CHANGED, sameTab);
      window.removeEventListener("storage", otherTab);
    };
    // fallback and validate are module-level constants at every call site
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  const set = useCallback(
    (next: T | ((prev: T) => T)) => {
      setState((prev) => {
        const value = typeof next === "function" ? (next as (p: T) => T)(prev.value) : next;
        queueMicrotask(() => writeStore(key, value)); // never notify from inside an updater
        return { value, ready: true };
      });
    },
    [key],
  );

  return [state.value, set, state.ready];
}
