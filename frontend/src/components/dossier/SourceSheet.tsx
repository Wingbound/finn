"use client";

import { useEffect, useRef } from "react";
import { Sheet } from "@/components/Sheet";
import { Skeleton } from "@/components/States";
import { useExcerpts, useSource } from "@/lib/hooks";
import type { Citation, Source } from "@/lib/types";
import { citeLabel } from "./cite";

const FOLD: Record<string, string> = {
  "‘": "'",
  "’": "'",
  "“": '"',
  "”": '"',
  "–": "-",
  "—": "-",
  " ": " ",
};

/** Normalised text plus, for each normalised char, its index in the original. */
function fold(s: string): { text: string; map: number[] } {
  let text = "";
  const map: number[] = [];
  let space = false;
  for (let i = 0; i < s.length; i++) {
    const raw = s[i] as string;
    const ch = FOLD[raw] ?? raw;
    if (/\s/.test(ch)) {
      if (!space && text) {
        text += " ";
        map.push(i);
      }
      space = true;
      continue;
    }
    space = false;
    text += ch.toLowerCase();
    map.push(i);
  }
  return { text, map };
}

/** Where a quote sits in page text, ignoring spacing, line breaks, case and curly quotes. */
export function findQuote(text: string, quote: string): [number, number] | null {
  const hay = fold(text);
  const needle = fold(quote).text.trim();
  if (!needle) return null;
  const at = hay.text.indexOf(needle);
  if (at < 0) return null;
  const start = hay.map[at] as number;
  const end = (hay.map[at + needle.length - 1] as number) + 1;
  return [start, end];
}

/** PDF text breaks lines mid-sentence; join single breaks, keep blank-line paragraphs. */
export function reflow(text: string): string {
  return text.replace(/[ \t]*\n(?!\n)(?<!\n\n)[ \t]*/g, " ").replace(/\n{3,}/g, "\n\n");
}

function PageText({ text, quote }: { text: string; quote: string }) {
  const mark = useRef<HTMLElement>(null);
  const shown = reflow(text);
  const range = findQuote(shown, quote);
  useEffect(() => {
    // the sheet opens in its own effect, after this one; scroll once it is showing
    const id = requestAnimationFrame(() => mark.current?.scrollIntoView?.({ block: "center" }));
    return () => cancelAnimationFrame(id);
  }, [shown, quote]);
  if (!range) return <p className="quote whitespace-pre-line">{shown}</p>;
  return (
    <p className="quote whitespace-pre-line">
      {shown.slice(0, range[0])}
      <mark ref={mark}>{shown.slice(range[0], range[1])}</mark>
      {shown.slice(range[1])}
    </p>
  );
}

export function SourceSheet({
  symbol,
  citation,
  sources,
  onClose,
}: {
  symbol: string;
  citation: Citation | null;
  sources: Source[];
  onClose: () => void;
}) {
  const facts = citation?.source_id === "FACTS";
  const { data: excerpts } = useExcerpts(symbol);
  const local = citation && !facts ? excerpts?.[citation.source_id]?.[String(citation.page)] : undefined;
  const remote = useSource(
    local || facts || !citation ? null : symbol,
    citation?.source_id ?? null,
    citation?.page ?? null,
  );
  const text = local ?? remote.data?.text;
  const source = sources.find((s) => s.id === citation?.source_id);
  const failed = !text && (remote.error !== undefined || remote.data === null);
  return (
    <Sheet open={citation !== null} onClose={onClose} title={citation ? citeLabel(citation, sources) : ""}>
      {citation && facts ? (
        <div className="space-y-2">
          <p className="text-title font-medium">{citation.quote}</p>
          <p className="text-ink-2">
            Computed by FINN from screener&rsquo;s filed financials, not quoted from a document. The model may cite this
            line, but the number comes from code.
          </p>
        </div>
      ) : citation ? (
        <div className="space-y-3">
          {source ? (
            <p className="text-caption text-ink-2">
              {source.title}, page {citation.page}
            </p>
          ) : null}
          {text ? <PageText text={text} quote={citation.quote} /> : null}
          {failed ? (
            <>
              <p className="text-ink-2">This page couldn&rsquo;t be loaded. The quote, as FINN verified it:</p>
              <blockquote className="quote">&ldquo;{citation.quote}&rdquo;</blockquote>
            </>
          ) : null}
          {!text && !failed ? <Skeleton lines={8} label="Loading the page" /> : null}
          {source?.url ? (
            <a
              href={`${source.url}#page=${citation.page}`}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex min-h-11 items-center text-pencil"
            >
              Open the PDF
            </a>
          ) : null}
        </div>
      ) : null}
    </Sheet>
  );
}
