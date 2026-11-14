"use client";

import Link from "next/link";
import { useCallback, useId, useState } from "react";
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

/** Quotes start at three lines; when the text runs past them (the target can sit there), a
 *  button opens it in full. Overflow is measured, not guessed from a word count: on a phone
 *  about twenty words already fill three lines. */
function Quote({ text }: { text: string }) {
  const [open, setOpen] = useState(false);
  const [overflows, setOverflows] = useState(false);
  const measure = useCallback(
    (el: HTMLElement | null) => {
      if (!el || open) return;
      const check = () => setOverflows(el.scrollHeight > el.clientHeight + 1);
      check();
      void document.fonts?.ready.then(check); // the serif arrives after first paint
      if (typeof ResizeObserver === "undefined") return;
      const ro = new ResizeObserver(check);
      ro.observe(el);
      return () => ro.disconnect();
    },
    [open],
  );
  return (
    <>
      <blockquote ref={measure} className={`quote ${open ? "" : "line-clamp-3"}`}>
        &ldquo;{text}&rdquo;
      </blockquote>
      {open || overflows ? (
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
