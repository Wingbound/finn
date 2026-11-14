"use client";

import Link from "next/link";
import { useId, useState } from "react";
import { symbolPath } from "@/lib/api";
import { level, pct } from "@/lib/format";
import type { PaceNote, PromiseNote } from "@/lib/types";

const num = (v: number) => (Number.isInteger(v) ? String(v) : v.toFixed(1));

/** One quarter beside the target, in words that never grade the promise. */
export function paceSentence(p: PaceNote): string {
  const figure =
    p.line === "EBITDA margin"
      ? `EBITDA margin ${level(p.actual)}`
      : `${p.line === "PAT" ? "PAT" : p.line.toLowerCase()} ${pct(p.actual)} YoY`;
  const range =
    p.target_high === null || p.target_high === p.target_low
      ? `${num(p.target_low)}%`
      : `${num(p.target_low)}–${num(p.target_high)}%`;
  return p.scope === "quarter"
    ? `This quarter: ${figure}, ${p.word} the ${range} target set for it.`
    : `This quarter: ${figure}, ${p.word} the ${range} target. One quarter, not the full year.`;
}

const KIND: Record<PromiseNote["target_kind"], string> = { target: "Target", guided: "Guided", figure: "Figure quoted:" };

/** "{call}. Target 15–18% for FY27." The period is resolved against this card, never echoed:
 *  "next year" said a year ago would mislead. */
export function noteMeta(n: PromiseNote): string {
  const parts = [n.call];
  const label = n.horizon_label;
  const resolved = !!label && !label.startsWith('"');
  const passed = !!label && label.startsWith("was due");
  if (n.target) parts.push(`${KIND[n.target_kind]} ${n.target}${resolved && !passed ? ` for ${label}` : ""}`);
  if (label && passed) parts.push(`Was due ${label.slice("was due ".length)}`);
  else if (label && !resolved) parts.push(`Timing: ${label}`);
  else if (label && !n.target) parts.push(`For ${label}`);
  return `${parts.join(". ")}.`;
}

/** Long quotes start at three lines; the target can sit past them, so they open in full. */
function Quote({ text }: { text: string }) {
  const [open, setOpen] = useState(false);
  const long = text.split(/\s+/).length > 30;
  return (
    <>
      <blockquote className={`quote ${open || !long ? "" : "line-clamp-3"}`}>&ldquo;{text}&rdquo;</blockquote>
      {long ? (
        <button type="button" className="min-h-11 text-caption text-pencil" onClick={() => setOpen((v) => !v)} aria-expanded={open}>
          {open ? "Show less" : "Show more"}
        </button>
      ) : null}
    </>
  );
}

/** What management said on its calls, beside the quarter it just filed. */
export function PromisePanel({ symbol, notes }: { symbol: string; notes: PromiseNote[] }) {
  const title = useId();
  if (!notes.length) return null;
  return (
    <section aria-labelledby={title} className="mt-3 border-l-2 border-pencil pl-3">
      <p id={title} className="text-caption font-semibold">
        What management said
      </p>
      <ul className="mt-1 space-y-2.5">
        {notes.map((n) => (
          <li key={`${n.citation.source_id}-${n.citation.page}-${n.quote.slice(0, 24)}`}>
            <Quote text={n.quote} />
            <p className="text-caption text-ink-2">{noteMeta(n)}</p>
            {n.pace ? <p className="text-caption font-medium">{paceSentence(n.pace)}</p> : null}
          </li>
        ))}
      </ul>
      <Link href={`/research/${symbolPath(symbol)}#ledger`} className="inline-flex min-h-11 items-center text-caption font-semibold text-pencil">
        See the ledger
      </Link>
    </section>
  );
}
