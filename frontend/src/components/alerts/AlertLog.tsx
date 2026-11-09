"use client";

import Link from "next/link";
import { useState } from "react";
import { symbolPath } from "@/lib/api";
import { categoryLabel, cleanSubject, day, storyCategory } from "@/lib/format";
import { KEYS, writeStore } from "@/lib/store";
import type { Alert } from "@/lib/types";

const SHOWN = 8;
const KIND: Record<Alert["kind"], string> = { volume: "Volume", price: "Price", filing: "Filing" };

function kindLabel(a: Alert): string {
  const c = a.kind === "filing" && a.story_id ? storyCategory(a.story_id) : null;
  return c ? categoryLabel(c) : KIND[a.kind];
}

export function AlertLog({ alerts }: { alerts: Alert[] }) {
  const [all, setAll] = useState(false);
  if (!alerts.length) {
    return <p className="border-t border-rule py-4 text-ink-2">No alerts in the last 7 days under these rules.</p>;
  }
  const shown = all ? alerts : alerts.slice(0, SHOWN);
  return (
    <>
      <ul>
        {shown.map((a, i) => {
          const text = a.kind === "filing" ? cleanSubject(a.message) : a.message;
          return (
            <li key={`${a.kind}-${a.symbol}-${a.date}-${i}`} className="grid grid-cols-[5.5rem_minmax(0,1fr)] gap-x-3 border-t border-rule py-2.5">
              <p className="text-caption text-ink-2">
                <span className="block">{kindLabel(a)}</span>
                <span className="block">{day(`${a.date}T12:00:00+05:30`)}</span>
              </p>
              <div className="min-w-0">
                <p className="font-semibold">{a.symbol}</p>
                {a.kind === "filing" && a.story_id ? (
                  <Link
                    href={`/#story-${encodeURIComponent(a.story_id)}`}
                    onClick={() => writeStore(KEYS.window, { kind: "hours", hours: 168 })}
                    className="line-clamp-2 text-pencil"
                  >
                    {text}
                  </Link>
                ) : (
                  <p className="line-clamp-2 text-ink-2">
                    {text}{" "}
                    <Link href={`/research/${symbolPath(a.symbol)}`} className="text-pencil">
                      Dig in
                    </Link>
                  </p>
                )}
              </div>
            </li>
          );
        })}
      </ul>
      {alerts.length > SHOWN ? (
        <button type="button" onClick={() => setAll((v) => !v)} className="min-h-11 text-pencil" aria-expanded={all}>
          {all ? "Show the latest 8" : `Show all ${alerts.length}`}
        </button>
      ) : null}
    </>
  );
}
