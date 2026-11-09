import { stamp } from "@/lib/format";
import type { WindowChoice } from "@/lib/store";

const WIDER = [
  { hours: 72, label: "Show 3 days" },
  { hours: 168, label: "Show 7 days" },
];

/** An empty window is usually a quiet market or an old snapshot: say which, and widen it. */
export function StaleNotice({
  latest,
  window,
  onWiden,
  now,
}: {
  latest: string | null;
  window: WindowChoice;
  onWiden: (hours: number) => void;
  now?: Date;
}) {
  const current = window.kind === "hours" ? window.hours : Number.POSITIVE_INFINITY;
  const options = WIDER.filter((w) => w.hours > current);
  return (
    <section className="py-6">
      <h1 className="text-headline font-semibold tracking-[-0.01em]">Nothing matters yet</h1>
      <p className="mt-3 text-title">
        {window.kind === "hours" && window.hours === 24 ? "Nothing new in the last 24 hours." : "Nothing new in this window."}
      </p>
      {latest ? <p className="text-ink-2">Newest filing: {stamp(latest, now)}.</p> : null}
      {options.length ? (
        <div className="mt-3 flex gap-3">
          {options.map((o) => (
            <button
              key={o.hours}
              type="button"
              onClick={() => onWiden(o.hours)}
              className="min-h-11 rounded-lg border border-rule px-4 font-medium text-pencil"
            >
              {o.label}
            </button>
          ))}
        </div>
      ) : null}
    </section>
  );
}
