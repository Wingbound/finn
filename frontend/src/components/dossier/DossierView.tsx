"use client";

import { useState } from "react";
import { stamp } from "@/lib/format";
import type { Citation, Dossier } from "@/lib/types";
import { CostLine } from "./CostLine";
import { Health } from "./Health";
import { LedgerSection } from "./LedgerSection";
import { Points } from "./Points";
import { SectionNote } from "./SectionNote";
import { SourceSheet } from "./SourceSheet";
import { Trajectory } from "./Trajectory";

export function DossierView({ dossier }: { dossier: Dossier }) {
  const [cite, setCite] = useState<Citation | null>(null);
  const d = dossier;
  return (
    <article>
      <header className="pt-2">
        <h1 className="text-[1.75rem] leading-tight font-semibold">{d.name ?? d.symbol}</h1>
        <p className="text-ink-2">
          {d.symbol}, {d.basis}. Built {stamp(d.built_at)}.
        </p>
        <CostLine dossier={d} />
        <p className="mt-3 border-l-2 border-pencil pl-3 text-caption text-ink-2">
          <span className="quote text-ink">Serif text</span> is quoted word for word from the company&rsquo;s calls and
          annual report. Everything else is FINN&rsquo;s reading or filed numbers. Tap a citation to see the page.
        </p>
      </header>

      <LedgerSection dossier={d} onCite={setCite} />

      <section aria-labelledby="snapshot" className="pt-8">
        <h2 id="snapshot" className="text-section font-semibold">
          Snapshot
        </h2>
        {d.snapshot?.summary.length ? (
          <Points points={d.snapshot.summary} sources={d.sources} onCite={setCite} />
        ) : (
          <SectionNote section="snapshot" notes={d.notes} />
        )}
      </section>

      <Trajectory dossier={d} />
      <Health dossier={d} />

      <section aria-labelledby="bullbear" className="pt-8">
        <h2 id="bullbear" className="text-section font-semibold">
          Bull and bear
        </h2>
        {d.bull.length || d.bear.length ? (
          <>
            <h3 className="mt-3 text-title font-semibold">The case for</h3>
            {d.bull.length ? (
              <Points points={d.bull} sources={d.sources} onCite={setCite} />
            ) : (
              <p className="text-ink-2">No cited points.</p>
            )}
            <h3 className="mt-5 text-title font-semibold">The case against</h3>
            {d.bear.length ? (
              <Points points={d.bear} sources={d.sources} onCite={setCite} />
            ) : (
              <p className="text-ink-2">No cited points.</p>
            )}
          </>
        ) : (
          <SectionNote section="bullbear" notes={d.notes} />
        )}
      </section>

      {d.notes.length ? (
        <section aria-labelledby="skipped" className="pt-8 pb-4">
          <h2 id="skipped" className="text-title font-semibold">
            What FINN skipped
          </h2>
          <ul className="mt-1 list-disc pl-5 text-caption text-ink-2">
            {d.notes.map((n) => (
              <li key={n}>{n}</li>
            ))}
          </ul>
        </section>
      ) : null}

      <p className="pt-6 pb-2 text-caption text-ink-2">Sources: {d.sources.map((s) => s.title).join("; ")}.</p>

      <SourceSheet symbol={d.symbol} citation={cite} sources={d.sources} onClose={() => setCite(null)} />
    </article>
  );
}
