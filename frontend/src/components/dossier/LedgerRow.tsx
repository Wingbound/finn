import { statusLabel } from "@/lib/format";
import type { Citation, LedgerRow as Row, Promise as P, Source } from "@/lib/types";
import { CitationChip } from "./CitationChip";

const MARK: Record<Row["status"], string> = {
  kept: "text-kept",
  partly: "text-partly",
  missed: "text-missed",
  pending: "text-pending",
  dropped: "text-pending",
};

const n = (v: number) => (Number.isInteger(v) ? String(v) : v.toFixed(1));

export function targetText(p: P): string | null {
  if (p.target_low === null) return p.horizon ? `By ${p.horizon}` : null;
  const range = p.target_high !== null && p.target_high !== p.target_low ? `${n(p.target_low)}–${n(p.target_high)}` : n(p.target_low);
  const value =
    p.unit === "%" ? `${range}%`
    : p.unit === "cr" ? `₹${range} cr`
    : p.unit === "x" ? `${range}×`
    : p.unit === "usd_mn" ? `$${range} mn`
    : p.unit === "usd_bn" ? `$${range} bn`
    : range;
  return `Target ${value}${p.horizon ? `, ${p.horizon}` : ""}`;
}

export function LedgerRow({
  row,
  sources,
  onCite,
  compact = false,
}: {
  row: Row;
  sources: Source[];
  onCite: (c: Citation) => void;
  compact?: boolean;
}) {
  const s = statusLabel(row.status);
  const target = targetText(row.promise);
  return (
    <li className="grid grid-cols-[1.75rem_minmax(0,1fr)] border-t border-rule py-3">
      <span aria-hidden="true" className={`pt-0.5 text-title leading-none font-semibold ${MARK[row.status]}`}>
        {s.glyph}
      </span>
      <div className="min-w-0">
        <p className="flex flex-wrap items-baseline gap-x-2">
          <span className="text-caption font-semibold">{s.word}</span>
          <span className="font-semibold">{row.promise.topic.charAt(0).toUpperCase() + row.promise.topic.slice(1)}</span>
        </p>
        <blockquote className="quote mt-1">&ldquo;{row.promise.citation.quote}&rdquo;</blockquote>
        <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1">
          <CitationChip citation={row.promise.citation} sources={sources} onOpen={onCite} />
          {target ? <span className="text-caption text-ink-2">{target}</span> : null}
        </div>
        {row.actual ? (
          <p className="mt-2 text-caption">
            Delivered {n(row.actual.value)}
            {row.actual.unit === "%" ? "%" : ` ${row.actual.unit}`} in {row.actual.period}.{" "}
            <span className="text-ink-2">Computed from filed financials ({row.actual.basis}).</span>
          </p>
        ) : null}
        {row.evidence ? (
          <div className="mt-2 border-l-2 border-rule pl-3">
            <blockquote className="quote">&ldquo;{row.evidence.quote}&rdquo;</blockquote>
            <div className="mt-1.5">
              <CitationChip citation={row.evidence} sources={sources} onOpen={onCite} prefix="Later:" />
            </div>
          </div>
        ) : null}
        {!compact ? (
          <p className="mt-1.5 text-caption text-ink-2">
            {row.status === "dropped" ? "Not mentioned again in the later calls FINN read." : row.rationale}
          </p>
        ) : null}
      </div>
    </li>
  );
}
