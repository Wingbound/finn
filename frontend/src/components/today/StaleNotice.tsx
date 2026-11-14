import { day, stamp } from "@/lib/format";
import type { WindowChoice } from "@/lib/store";
import type { Digest } from "@/lib/types";

const PRESETS = [
  { hours: 72, label: "Show 3 days" },
  { hours: 168, label: "Show 7 days" },
];
const HOUR = 3_600_000;

/** Empty means nothing at all: a window holding only noise still shows its noise list. */
export function isEmptyWindow(counts: Digest["counts"]): boolean {
  return counts.shown === 0 && counts.routine === 0 && counts.hidden === 0;
}

/**
 * An empty window is usually a quiet market or an old snapshot: say which, and offer only
 * the windows that actually reach the newest filing. When none does, offer the week that
 * ends at it, so Today is never a dead end.
 */
export function StaleNotice({
  latest,
  window,
  onChoose,
  now = new Date(),
}: {
  latest: string | null;
  window: WindowChoice;
  onChoose: (w: WindowChoice) => void;
  now?: Date;
}) {
  const current = window.kind === "hours" ? window.hours : Number.POSITIVE_INFINITY;
  const age = latest ? now.getTime() - Date.parse(latest) : Number.POSITIVE_INFINITY;
  const presets = PRESETS.filter((p) => p.hours > current && p.hours * HOUR >= age);
  const week =
    latest && !presets.length
      ? {
          kind: "range" as const,
          start: new Date(Date.parse(latest) - 7 * 24 * HOUR).toISOString(),
          end: new Date(Date.parse(latest) + 60_000).toISOString(),
        }
      : null;
  return (
    <section className="py-6">
      <h1 className="text-headline font-semibold tracking-[-0.01em]">Nothing matters yet</h1>
      <p className="mt-3 text-title">
        {window.kind === "hours" && window.hours === 24 ? "Nothing new in the last 24 hours." : "Nothing new in this window."}
      </p>
      {latest ? <p className="text-ink-2">Newest filing: {stamp(latest, now)}.</p> : null}
      <div className="mt-3 flex flex-wrap gap-3">
        {presets.map((p) => (
          <button
            key={p.hours}
            type="button"
            onClick={() => onChoose({ kind: "hours", hours: p.hours })}
            className="min-h-11 rounded-lg border border-rule px-4 font-medium text-pencil"
          >
            {p.label}
          </button>
        ))}
        {week && latest ? (
          <button type="button" onClick={() => onChoose(week)} className="min-h-11 rounded-lg border border-rule px-4 font-medium text-pencil">
            Show the week up to {day(latest, now)}
          </button>
        ) : null}
      </div>
    </section>
  );
}
