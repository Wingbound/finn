"use client";

import { useEffect, useEffectEvent, useRef, useState } from "react";
import { BuildError, STOPPED, buildDossier } from "@/lib/sse";
import type { Dossier, Excerpts } from "@/lib/types";

type Phase = { kind: "running" } | { kind: "failed"; detail: string; incomplete: boolean };

/** A live build: FINN's own progress lines, elapsed time, and a way out. */
export function BuildProgress({
  symbol,
  onDone,
  onCancel,
  onCheckSaved,
}: {
  symbol: string;
  onDone: (r: { dossier: Dossier; excerpts: Excerpts }) => void;
  onCancel?: () => void;
  /** After a dropped stream: the server may have finished and saved the dossier anyway. */
  onCheckSaved?: () => void;
}) {
  const [lines, setLines] = useState<string[]>([]);
  const [phase, setPhase] = useState<Phase>({ kind: "running" });
  const [attempt, setAttempt] = useState(0);
  const [elapsed, setElapsed] = useState(0);
  const ctrl = useRef<AbortController | null>(null);
  const finished = useEffectEvent((r: { dossier: Dossier; excerpts: Excerpts }) => onDone(r));

  useEffect(() => {
    const c = new AbortController();
    ctrl.current = c;
    const started = Date.now();
    const tick = setInterval(() => setElapsed(Math.round((Date.now() - started) / 1000)), 1000);
    buildDossier(symbol, { onProgress: (m) => setLines((l) => [...l, m]), signal: c.signal })
      .then((r) => finished(r))
      .catch((e: unknown) => {
        if (c.signal.aborted) return;
        if (e instanceof BuildError) setPhase({ kind: "failed", detail: e.detail, incomplete: e.kind === "incomplete" });
        else setPhase({ kind: "failed", detail: STOPPED, incomplete: true });
      })
      .finally(() => clearInterval(tick));
    return () => {
      clearInterval(tick);
      c.abort();
    };
  }, [symbol, attempt]);

  const retry = () => {
    setLines([]);
    setElapsed(0);
    setPhase({ kind: "running" });
    setAttempt((a) => a + 1);
  };

  return (
    <section aria-live="polite" className="py-4">
      <h2 className="text-title font-semibold">Reading {symbol}&rsquo;s calls and annual report</h2>
      <p className="text-caption text-ink-2">
        {phase.kind === "running" ? `Usually 40 to 90 seconds. ${elapsed} s so far.` : `Stopped after ${elapsed} s.`}
      </p>
      <ol className="mt-3 space-y-1.5 border-l-2 border-rule pl-3">
        {lines.map((l, i) => (
          <li key={`${i}-${l}`} className={i === lines.length - 1 && phase.kind === "running" ? "text-ink" : "text-ink-2"}>
            {l}
          </li>
        ))}
        {!lines.length && phase.kind === "running" ? <li className="text-ink-2">Starting</li> : null}
      </ol>
      {phase.kind === "failed" ? (
        <div role="alert" className="mt-4">
          <p className="font-medium">{phase.incomplete ? `${phase.detail}.` : phase.detail}</p>
          {phase.incomplete ? (
            <p className="text-caption text-ink-2">The server may still finish and save it. Try again in a minute.</p>
          ) : null}
          <div className="mt-2 flex flex-wrap gap-3">
            {phase.incomplete && onCheckSaved ? (
              <button type="button" onClick={onCheckSaved} className="min-h-11 rounded-lg bg-pencil px-4 font-semibold text-paper">
                Check for a saved copy
              </button>
            ) : null}
            <button type="button" onClick={retry} className="min-h-11 rounded-lg border border-rule px-4 font-medium text-pencil">
              Try again
            </button>
          </div>
        </div>
      ) : (
        <button
          type="button"
          onClick={() => {
            ctrl.current?.abort();
            onCancel?.();
          }}
          className="mt-4 min-h-11 text-ink-2"
        >
          Cancel
        </button>
      )}
    </section>
  );
}
