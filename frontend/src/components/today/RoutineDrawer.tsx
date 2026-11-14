"use client";

import { categoryLabel, cleanSubject, plural, when } from "@/lib/format";
import type { Category, Digest } from "@/lib/types";

/** The end of the feed: what FINN set aside, grouped and counted, one tap away. */
export function RoutineDrawer({
  digest,
  open,
  onToggle,
  now,
}: {
  digest: Digest;
  open: boolean;
  onToggle: () => void;
  now?: Date;
}) {
  const groups = Object.entries(digest.routine) as [Category, Digest["stories"]][];
  return (
    <section id="routine" className="border-t border-rule pt-6 pb-4">
      <h2 className="text-section font-semibold">You&rsquo;re caught up.</h2>
      {digest.counts.routine + digest.counts.hidden > 0 ? (
        <button type="button" onClick={onToggle} aria-expanded={open} className="mt-1 min-h-11 text-pencil">
          {open ? "Hide" : "Show"} what FINN set aside ({digest.counts.routine + digest.counts.hidden})
        </button>
      ) : null}
      {open ? (
        <div className="mt-2 space-y-5">
          {groups.map(([cat, stories]) => (
            <div key={cat}>
              <h3 className="text-caption font-semibold text-ink-2">
                {categoryLabel(cat)} ({stories.length})
              </h3>
              <ul className="mt-1">
                {stories.map((s) => (
                  <li key={s.id} id={`story-${s.id}`} className="flex scroll-mt-4 items-baseline gap-3 border-t border-rule py-2 text-caption">
                    <span className="w-24 shrink-0 truncate font-semibold">{s.symbol}</span>
                    <span className="min-w-0 flex-1 text-ink-2">
                      {s.headline.filing.pdf_url ? (
                        <a href={s.headline.filing.pdf_url} target="_blank" rel="noopener noreferrer" className="hover:text-ink">
                          {cleanSubject(s.headline.filing.subject)}
                        </a>
                      ) : (
                        cleanSubject(s.headline.filing.subject)
                      )}
                    </span>
                    <span className="shrink-0 text-ink-2">{when(s.latest_at, now)}</span>
                  </li>
                ))}
              </ul>
            </div>
          ))}
          {digest.hidden.length ? (
            <div>
              <h3 className="text-caption font-semibold text-ink-2">Noise dropped ({digest.hidden.length})</h3>
              <p className="text-caption text-ink-2">
                Newspaper copies, share-certificate notices and duplicates. {plural(digest.hidden.length, "filing")}, never scored.
              </p>
              <ul className="mt-1">
                {digest.hidden.map((h, i) => (
                  <li key={`${h.symbol}-${h.filed_at}-${i}`} className="flex gap-3 border-t border-rule py-2 text-caption text-ink-2">
                    <span className="w-24 shrink-0 truncate font-semibold text-ink">{h.symbol}</span>
                    <span className="min-w-0 flex-1">{cleanSubject(h.subject)}</span>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
