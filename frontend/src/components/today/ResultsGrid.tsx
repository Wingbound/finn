import { bps, crore, level, pct } from "@/lib/format";
import type { ResultsCard } from "@/lib/types";

/** Filed numbers for the quarter. Deltas stay in ink: a rising cost line is not good news. */
export function ResultsGrid({ card }: { card: ResultsCard }) {
  const audited = card.audited === true ? "audited" : card.audited === false ? "unaudited" : null;
  const caption = [card.period_label, card.basis, audited].filter(Boolean).join(", ");
  return (
    <div className="mt-2">
      <table className="w-full border-collapse text-body">
        <caption className="pb-1 text-left text-caption text-ink-2">{caption}</caption>
        <thead>
          <tr className="text-caption text-ink-2">
            <th scope="col" className="py-1 text-left font-normal">
              <span className="sr-only">Line</span>
            </th>
            <th scope="col" className="py-1 text-right font-normal">
              Value
            </th>
            <th scope="col" className="py-1 text-right font-normal">
              QoQ
            </th>
            <th scope="col" className="py-1 text-right font-normal">
              YoY
            </th>
          </tr>
        </thead>
        <tbody>
          {card.metrics.map((m) => (
            <tr key={m.key} className="border-t border-rule">
              <th scope="row" className="py-1.5 pr-2 text-left font-normal">
                {m.label}
                {m.computed ? <span aria-label=" (computed by FINN)">†</span> : null}
              </th>
              <td className="py-1.5 text-right font-medium whitespace-nowrap">{crore(m.value)}</td>
              <td className="py-1.5 pl-2 text-right whitespace-nowrap">{pct(m.qoq_pct)}</td>
              <td className="py-1.5 pl-2 text-right whitespace-nowrap">{pct(m.yoy_pct)}</td>
            </tr>
          ))}
          {card.margins.map((m) => (
            <tr key={m.key} className="border-t border-rule text-ink-2">
              <th scope="row" className="py-1.5 pr-2 text-left font-normal">
                {m.label}
              </th>
              <td className="py-1.5 text-right whitespace-nowrap">{level(m.value_pct)}</td>
              <td className="py-1.5 pl-2 text-right whitespace-nowrap">{bps(m.qoq_bps)}</td>
              <td className="py-1.5 pl-2 text-right whitespace-nowrap">{bps(m.yoy_bps)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {card.notes.length || card.metrics.some((m) => m.computed) ? (
        <ul className="mt-2 space-y-0.5 text-caption text-ink-2">
          {card.metrics.some((m) => m.computed) ? <li>† Computed by FINN from the filed lines, not a reported figure.</li> : null}
          {card.notes.map((n) => (
            <li key={n}>{n}</li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
