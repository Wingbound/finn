import type { Category, Status } from "./types";

const MINUS = "−";
const TZ = "Asia/Kolkata";
export const DASH = "–";

const fin = (n: number | null | undefined): n is number => typeof n === "number" && Number.isFinite(n);
const neg = (n: number) => (n < 0 ? MINUS : "");
const sign = (n: number, shown: string) => (Number(shown) === 0 ? "" : n > 0 ? "+" : MINUS);

const inr0 = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 });
const inr1 = new Intl.NumberFormat("en-IN", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
const inr2 = new Intl.NumberFormat("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

/** ₹ crore, Indian grouping: 123456.7 → "₹1,23,457 cr"; under 100 keeps one decimal. */
export function crore(n: number | null | undefined): string {
  if (!fin(n)) return DASH;
  const a = Math.abs(n);
  return `${neg(n)}₹${(a >= 100 ? inr0 : inr1).format(a)} cr`;
}

/** A share price: "₹1,308.50". */
export function rupees(n: number | null | undefined): string {
  if (!fin(n)) return DASH;
  return `${neg(n)}₹${inr2.format(Math.abs(n))}`;
}

/** Signed change: "+4.1%", "−2.0%", "0.0%". */
export function pct(n: number | null | undefined, digits = 1): string {
  if (!fin(n)) return DASH;
  const shown = Math.abs(n).toFixed(digits);
  return `${sign(n, shown)}${shown}%`;
}

/** Signed basis points: "+120 bps". */
export function bps(n: number | null | undefined): string {
  if (!fin(n)) return DASH;
  const shown = String(Math.round(Math.abs(n)));
  return `${sign(n, shown)}${shown} bps`;
}

/** A level, not a change: "21.4%". */
export function level(n: number | null | undefined, digits = 1): string {
  if (!fin(n)) return DASH;
  return `${neg(n)}${Math.abs(n).toFixed(digits)}%`;
}

/** A multiple: "2.4×". */
export function times(n: number | null | undefined, digits = 1): string {
  if (!fin(n)) return DASH;
  return `${neg(n)}${Math.abs(n).toFixed(digits)}×`;
}

const fmtDay = new Intl.DateTimeFormat("en-IN", { timeZone: TZ, day: "numeric", month: "short" });
const fmtDayYear = new Intl.DateTimeFormat("en-IN", { timeZone: TZ, day: "numeric", month: "short", year: "numeric" });
const fmtTime = new Intl.DateTimeFormat("en-IN", { timeZone: TZ, hour: "2-digit", minute: "2-digit", hourCycle: "h23" });
const fmtYear = new Intl.DateTimeFormat("en-IN", { timeZone: TZ, year: "numeric" });

const asDate = (v: string | Date) => (v instanceof Date ? v : new Date(v));

/** "just now", "45 min ago", "3 h ago", "2 d ago". */
export function ago(iso: string | Date, now: Date = new Date()): string {
  const mins = Math.floor((now.getTime() - asDate(iso).getTime()) / 60_000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins} min ago`;
  const hours = Math.floor(mins / 60);
  return hours < 24 ? `${hours} h ago` : `${Math.floor(hours / 24)} d ago`;
}

/** "9 Nov" in IST; "31 Dec 2025" when the year differs from now's. */
export function day(iso: string | Date, now: Date = new Date()): string {
  const d = asDate(iso);
  return fmtYear.format(d) === fmtYear.format(now) ? fmtDay.format(d) : fmtDayYear.format(d);
}

/** "9 Nov, 14:05" in IST. */
export function stamp(iso: string | Date, now: Date = new Date()): string {
  return `${day(iso, now)}, ${fmtTime.format(asDate(iso))}`;
}

/** Relative within the last 24 hours, otherwise a stamp. */
export function when(iso: string | Date, now: Date = new Date()): string {
  const diff = now.getTime() - asDate(iso).getTime();
  return diff >= 0 && diff < 86_400_000 ? ago(iso, now) : stamp(iso, now);
}

const CATEGORY: Record<Category, string> = {
  results: "Results",
  mna: "Deal",
  fund_raise: "Fund-raise",
  management_change: "People",
  litigation: "Litigation",
  insider_trading: "Insider trade",
  earnings_call: "Earnings call",
  investor_meetings: "Investor meeting",
  credit_rating: "Credit rating",
  dividend: "Dividend",
  bonus_split: "Bonus or split",
  capex: "Capex",
  press_release: "Press release",
  postal_ballot: "Postal ballot",
  agm_egm: "AGM or EGM",
  pledging: "Pledge",
  unclassified: "Other",
};

export function categoryLabel(c: Category): string {
  return CATEGORY[c] ?? "Other";
}

export const STATUS_ORDER: Status[] = ["kept", "partly", "missed", "pending", "dropped"];

const STATUS: Record<Status, { glyph: string; word: string }> = {
  kept: { glyph: "✓", word: "Kept" },
  partly: { glyph: "◐", word: "Partly" },
  missed: { glyph: "✕", word: "Missed" },
  pending: { glyph: "○", word: "Pending" },
  dropped: { glyph: DASH, word: "Not mentioned again" },
};

export function statusLabel(s: Status): { glyph: string; word: string } {
  return STATUS[s];
}

export function plural(n: number, one: string, many = `${one}s`): string {
  return `${n} ${n === 1 ? one : many}`;
}
