import Link from "next/link";
import { symbolPath } from "@/lib/api";
import { day, pct, rupees, times } from "@/lib/format";
import type { PortfolioRow, Rules } from "@/lib/types";
import { Sparkline } from "./Sparkline";

/** The newest trading session in the rows (YYYY-MM-DD), or null. */
export function latestSession(rows: { date: string | null }[]): string | null {
  return rows.reduce<string | null>((max, r) => (r.date && (!max || r.date > max) ? r.date : max), null);
}

/** Where the prices came from, and which session's close they are (not when FINN fetched them). */
export function priceCaption(session: string | null, source: string | null, now: Date = new Date()): string | null {
  if (!session) return null;
  const when = day(session, now);
  return source ? `Prices: ${source}. Close of ${when}.` : `Prices at the close of ${when}.`;
}

export function Holdings({ rows, rules, flagged }: { rows: PortfolioRow[]; rules: Rules; flagged: Set<string> }) {
  return (
    <ul>
      {rows.map((h) => {
        const o = rules.overrides[h.symbol];
        const volLimit = o?.volume_multiple ?? rules.volume_multiple;
        const heavy = h.vol_ratio !== null && h.vol_ratio >= volLimit;
        const up = (h.change_pct ?? 0) > 0;
        const down = (h.change_pct ?? 0) < 0;
        return (
          <li
            key={h.symbol}
            className={`grid grid-cols-[minmax(0,1fr)_72px_6.5rem] items-center gap-3 border-t border-rule py-2.5 ${
              flagged.has(h.symbol) ? "-ml-3 border-l-2 border-l-pencil pl-2.5" : ""
            }`}
          >
            <div className="min-w-0">
              <Link href={`/research/${symbolPath(h.symbol)}`} className="block truncate font-semibold">
                {h.symbol}
              </Link>
              <p className="truncate text-caption text-ink-2">
                {o?.muted ? "Muted" : heavy ? `Volume ${times(h.vol_ratio)}` : `${h.size} cap`}
              </p>
            </div>
            <Sparkline values={h.spark} />
            <div className="text-right">
              <p className="font-medium">{rupees(h.close)}</p>
              <p className={`text-caption ${up ? "text-kept" : down ? "text-missed" : "text-ink-2"}`}>
                <span aria-hidden="true">{up ? "▲ " : down ? "▼ " : ""}</span>
                {pct(h.change_pct, 2)}
                <span className="sr-only">{up ? " up" : down ? " down" : ""} on the day</span>
              </p>
            </div>
          </li>
        );
      })}
    </ul>
  );
}
