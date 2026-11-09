"use client";

import { useState } from "react";
import { bps, crore, level, pct } from "@/lib/format";
import type { Dossier } from "@/lib/types";
import { MiniBars, MiniLine, fyLabel } from "./MiniBars";
import { SectionNote } from "./SectionNote";

const READ: Record<string, string> = {
  growing: "Growing",
  compressing: "Compressing",
  mixed: "Mixed",
  "insufficient data": "Not enough data",
};

export function Trajectory({ dossier }: { dossier: Dossier }) {
  const t = dossier.trajectory;
  const [table, setTable] = useState(false);
  return (
    <section aria-labelledby="trajectory" className="pt-8">
      <h2 id="trajectory" className="text-section font-semibold">
        Trajectory
      </h2>
      {!t ? (
        <SectionNote section="trajectory" notes={dossier.notes} />
      ) : (
        <>
          <p className="mt-1 text-ink-2">
            FINN&rsquo;s read: <span className="font-semibold text-ink">{READ[t.read] ?? t.read}</span>. Filed annual
            figures, {dossier.basis}.
          </p>
          <MiniBars
            title="Revenue"
            years={t.years}
            values={t.revenue}
            format={(v) => crore(v)}
            summary={t.revenue_cagr_pct !== null ? `${pct(t.revenue_cagr_pct)} a year` : undefined}
          />
          <MiniLine
            title={t.lender ? "Financing margin" : "Operating margin"}
            years={t.years}
            values={t.margin_pct}
            format={(v) => level(v)}
            summary={t.margin_change_bps !== null ? `${bps(t.margin_change_bps)} over the period` : undefined}
          />
          <MiniBars
            title="Profit after tax"
            years={t.years}
            values={t.pat}
            format={(v) => crore(v)}
            summary={t.pat_cagr_pct !== null ? `${pct(t.pat_cagr_pct)} a year` : undefined}
          />
          <button type="button" onClick={() => setTable((v) => !v)} aria-expanded={table} className="min-h-11 text-caption text-pencil">
            {table ? "Hide the table" : "Show the numbers as a table"}
          </button>
          {table ? (
            <table className="w-full text-caption">
              <thead>
                <tr className="text-ink-2">
                  <th scope="col" className="py-1 text-left font-normal">Year</th>
                  <th scope="col" className="py-1 text-right font-normal">Revenue</th>
                  <th scope="col" className="py-1 text-right font-normal">{t.lender ? "Fin. margin" : "Op. margin"}</th>
                  <th scope="col" className="py-1 text-right font-normal">PAT</th>
                </tr>
              </thead>
              <tbody>
                {t.years.map((y, i) => (
                  <tr key={y} className="border-t border-rule">
                    <th scope="row" className="py-1 text-left font-normal">{fyLabel(y)}</th>
                    <td className="py-1 text-right">{crore(t.revenue[i])}</td>
                    <td className="py-1 text-right">{level(t.margin_pct[i])}</td>
                    <td className="py-1 text-right">{crore(t.pat[i])}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : null}
        </>
      )}
    </section>
  );
}
