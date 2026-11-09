import { crore, level, times } from "@/lib/format";
import type { Dossier, Flag } from "@/lib/types";
import { SectionNote } from "./SectionNote";

const FLAG: Record<Flag["level"], { glyph: string; cls: string; word: string }> = {
  good: { glyph: "●", cls: "text-kept", word: "Good" },
  watch: { glyph: "▲", cls: "text-partly", word: "Watch" },
  concern: { glyph: "■", cls: "text-missed", word: "Concern" },
};

export function Health({ dossier }: { dossier: Dossier }) {
  const h = dossier.health;
  const rows: [string, string | null][] = h
    ? [
        ["Debt to equity", h.debt_to_equity !== null ? h.debt_to_equity.toFixed(2) : null],
        ["Cash from operations to profit (3 years)", h.cfo_to_pat_3y !== null ? times(h.cfo_to_pat_3y, 2) : null],
        ["Free cash flow (3 years)", h.fcf_3y_cr !== null ? crore(h.fcf_3y_cr) : null],
        [
          "Working capital days",
          h.working_capital_days !== null
            ? `${Math.round(h.working_capital_days)}${
                h.wc_days_change_3y ? ` (${h.wc_days_change_3y > 0 ? "up" : "down"} ${Math.abs(Math.round(h.wc_days_change_3y))} in 3 years)` : ""
              }`
            : null,
        ],
        ["Return on capital employed", h.roce_pct !== null ? level(h.roce_pct) : null],
      ]
    : [];
  const present = rows.filter(([, v]) => v !== null);
  return (
    <section aria-labelledby="health" className="pt-8">
      <h2 id="health" className="text-section font-semibold">
        Balance sheet and cash
      </h2>
      {!h ? (
        <SectionNote section="health" notes={dossier.notes} />
      ) : (
        <>
          <p className="mt-1 text-ink-2">Computed by FINN from filed financials, as of {h.as_of}.</p>
          {present.length ? (
            <dl className="mt-2">
              {present.map(([k, v]) => (
                <div key={k} className="flex items-baseline justify-between gap-4 border-t border-rule py-2">
                  <dt className="text-ink-2">{k}</dt>
                  <dd className="font-medium whitespace-nowrap">{v}</dd>
                </div>
              ))}
            </dl>
          ) : null}
          {h.flags.length ? (
            <ul className="mt-3 space-y-1.5">
              {h.flags.map((f) => (
                <li key={f.text} className="flex gap-2">
                  <span aria-hidden="true" className={FLAG[f.level].cls}>
                    {FLAG[f.level].glyph}
                  </span>
                  <span>
                    <span className="sr-only">{FLAG[f.level].word}: </span>
                    {f.text}
                  </span>
                </li>
              ))}
            </ul>
          ) : null}
        </>
      )}
    </section>
  );
}
