import { Tally } from "@/components/Tally";
import { level, plural } from "@/lib/format";
import type { Citation, Dossier, LedgerRow as Row } from "@/lib/types";
import { LedgerRow } from "./LedgerRow";
import { SectionNote } from "./SectionNote";

const ORDER: Record<Row["status"], number> = { missed: 0, partly: 1, kept: 2, dropped: 3, pending: 4 };

const qkey = (q: string) => {
  const m = q.match(/Q([1-4])\s*FY\s*(\d{2,4})/i);
  return m ? Number(m[2]!.slice(-2)) * 10 + Number(m[1]) : -1;
};

/** Open promises come from the newest call; the track record is everything older, newest call first. */
export function splitLedger(d: Dossier): { newest: string | null; open: Row[]; track: { quarter: string; rows: Row[] }[] } {
  const rows = d.ledger?.rows ?? [];
  const quarters = [...new Set(rows.map((r) => r.promise.made_in))].sort((a, b) => qkey(b) - qkey(a));
  const fromSources = d.sources.filter((s) => s.kind === "transcript" && s.quarter).map((s) => s.quarter as string);
  const newest = [...fromSources, ...quarters].sort((a, b) => qkey(b) - qkey(a))[0] ?? null;
  const open = rows.filter((r) => r.promise.made_in === newest);
  const track = quarters
    .filter((q) => q !== newest)
    .map((quarter) => ({
      quarter,
      rows: rows.filter((r) => r.promise.made_in === quarter).sort((a, b) => ORDER[a.status] - ORDER[b.status]),
    }));
  return { newest, open, track };
}

export function LedgerSection({ dossier, onCite }: { dossier: Dossier; onCite: (c: Citation) => void }) {
  const ledger = dossier.ledger;
  return (
    <section aria-labelledby="ledger" className="pt-6">
      <h2 id="ledger" className="text-section font-semibold">
        Promise ledger
      </h2>
      {!ledger ? (
        <SectionNote section="ledger" notes={dossier.notes} />
      ) : (
        <LedgerBody dossier={dossier} onCite={onCite} />
      )}
    </section>
  );
}

function LedgerBody({ dossier, onCite }: { dossier: Dossier; onCite: (c: Citation) => void }) {
  const ledger = dossier.ledger!;
  const { newest, open, track } = splitLedger(dossier);
  const c = ledger.counts;
  const resolved = (c.kept ?? 0) + (c.partly ?? 0) + (c.missed ?? 0);
  return (
    <>
      <p className="mt-1 text-ink-2">What management said on its last four calls, checked against what came after.</p>
      {ledger.credibility_pct !== null ? (
        <p className="mt-3 text-title">
          Credibility {level(ledger.credibility_pct, 0)}
          <span className="text-caption text-ink-2">, from {plural(resolved, "resolved promise")}</span>
        </p>
      ) : null}
      <Tally counts={c} className="mt-2" />
      {ledger.note ? <p className="mt-2 text-caption text-ink-2">{ledger.note}</p> : null}

      <h3 className="mt-6 text-title font-semibold">Track record (earlier calls)</h3>
      <p className="text-caption text-ink-2">
        A verdict needs a verbatim quote from a later call. FINN&rsquo;s own checks on period, restated targets and
        figures can only hold a verdict back, never grant one.
      </p>
      {track.length ? (
        track.map((g) => (
          <div key={g.quarter} className="mt-3">
            <h4 className="text-caption font-semibold text-ink-2">From the {g.quarter} call</h4>
            <ul>
              {g.rows.map((r) => (
                <LedgerRow key={r.promise.id} row={r} sources={dossier.sources} onCite={onCite} />
              ))}
            </ul>
          </div>
        ))
      ) : (
        <p className="py-2 text-ink-2">No earlier calls to check yet.</p>
      )}

      {open.length ? (
        <>
          <h3 className="mt-6 text-title font-semibold">Open promises{newest ? ` (${newest} call)` : ""}</h3>
          <p className="text-caption text-ink-2">From the newest call, so nothing later can grade them yet.</p>
          <ul className="mt-1">
            {open.map((r) => (
              <LedgerRow key={r.promise.id} row={r} sources={dossier.sources} onCite={onCite} compact />
            ))}
          </ul>
        </>
      ) : null}
    </>
  );
}
