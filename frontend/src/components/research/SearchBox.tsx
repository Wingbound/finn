"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ApiError, apiGet, symbolPath } from "@/lib/api";
import type { SearchHit } from "@/lib/types";

type State = { kind: "idle" } | { kind: "loading" } | { kind: "hits"; hits: SearchHit[] } | { kind: "error"; message: string };

/** Any listed company, found through screener. Known symbols open; new ones build. */
export function SearchBox({ known }: { known: Set<string> }) {
  const [q, setQ] = useState("");
  const [result, setResult] = useState<{ term: string; state: State }>({ term: "", state: { kind: "idle" } });
  const term = q.trim();
  // Results belong to the term they answered; anything else (or a short term) shows as idle.
  const state: State = term.length >= 2 && result.term === term ? result.state : term.length >= 2 ? { kind: "loading" } : { kind: "idle" };

  useEffect(() => {
    if (term.length < 2) return;
    let live = true;
    const t = setTimeout(() => {
      apiGet<SearchHit[]>(`/research/search?q=${encodeURIComponent(term)}`)
        .then((hits) => live && setResult({ term, state: { kind: "hits", hits } }))
        .catch((e: unknown) => {
          if (!live) return;
          const msg = e instanceof ApiError && e.status !== 0 ? "Search is unavailable right now. Try a symbol you know." : (e as Error).message;
          setResult({ term, state: { kind: "error", message: msg } });
        });
    }, 300);
    return () => {
      live = false;
      clearTimeout(t);
    };
  }, [term]);

  return (
    <div className="relative">
      <label htmlFor="search" className="sr-only">
        Search a company or NSE symbol
      </label>
      <input
        id="search"
        type="search"
        autoComplete="off"
        placeholder="Search a company or NSE symbol"
        value={q}
        onChange={(e) => setQ(e.target.value)}
        className="h-12 w-full rounded-lg border border-rule bg-paper px-3 text-title placeholder:text-ink-2"
      />
      {state.kind === "loading" ? (
        <p role="status" className="py-2 text-caption text-ink-2">
          Searching
        </p>
      ) : null}
      {state.kind === "error" ? <p className="py-2 text-caption text-missed">{state.message}</p> : null}
      {state.kind === "hits" ? (
        state.hits.length ? (
          <ul aria-label="Search results" className="mt-1">
            {state.hits.map((h) => {
              const ready = known.has(h.symbol);
              return (
                <li key={h.symbol} className="border-t border-rule">
                  <Link
                    href={`/research/${symbolPath(h.symbol)}${ready ? "" : "?build=1"}`}
                    className="flex min-h-12 items-center justify-between gap-3 py-2"
                  >
                    <span className="min-w-0">
                      <span className="block truncate font-medium">{h.name}</span>
                      <span className="text-caption text-ink-2">{h.symbol}</span>
                    </span>
                    <span className="shrink-0 text-caption text-pencil">{ready ? "Open" : "Build a dossier"}</span>
                  </Link>
                </li>
              );
            })}
          </ul>
        ) : (
          <p className="py-2 text-caption text-ink-2">No listed company matches &ldquo;{term}&rdquo;.</p>
        )
      ) : null}
    </div>
  );
}
