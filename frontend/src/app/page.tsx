"use client";

import { useEffect, useState } from "react";
import { ErrorState, Skeleton } from "@/components/States";
import { FloorControl } from "@/components/today/FloorControl";
import { Header } from "@/components/today/Header";
import { RoutineDrawer } from "@/components/today/RoutineDrawer";
import { StaleNotice } from "@/components/today/StaleNotice";
import { StoryList } from "@/components/today/StoryList";
import { WindowPicker } from "@/components/today/WindowPicker";
import { useDigest } from "@/lib/hooks";
import {
  DEFAULT_FLOOR,
  DEFAULT_RULES,
  DEFAULT_WINDOW,
  KEYS,
  useStored,
  validateFloor,
  validateRules,
  validateWindow,
} from "@/lib/store";
import type { DigestRequest } from "@/lib/types";

export default function TodayPage() {
  const [rules, , rulesReady] = useStored(KEYS.rules, DEFAULT_RULES, validateRules);
  const [floor, setFloor, floorReady] = useStored(KEYS.floor, DEFAULT_FLOOR, validateFloor);
  const [win, setWin, winReady] = useStored(KEYS.window, DEFAULT_WINDOW, validateWindow);
  const [drawer, setDrawer] = useState(false);

  const ready = rulesReady && floorReady && winReady;
  const req: DigestRequest | null = ready
    ? {
        ...(win.kind === "hours" ? { hours: win.hours } : { start: win.start, end: win.end }),
        floor,
        subscribed: rules.categories,
      }
    : null;
  const { data, error, isLoading, isValidating, mutate } = useDigest(req);

  const openDrawer = () => {
    setDrawer(true);
    requestAnimationFrame(() => document.getElementById("routine")?.scrollIntoView({ behavior: "smooth" }));
  };
  const empty = data && data.counts.shown === 0 && data.counts.routine === 0;

  // An alert links here as /#story-<id>: bring that story into view once it has rendered.
  useEffect(() => {
    const hash = decodeURIComponent(window.location.hash.slice(1));
    if (!data || !hash.startsWith("story-")) return;
    document.getElementById(hash)?.scrollIntoView({ block: "start" });
  }, [data]);

  return (
    <>
      {data && !empty ? <Header counts={data.counts} onOpenRoutine={openDrawer} /> : null}
      {empty ? (
        <StaleNotice latest={data.latest_filing_at} window={win} onWiden={(h) => setWin({ kind: "hours", hours: h })} />
      ) : null}
      {!data && !error ? <h1 className="sr-only">Today</h1> : null}

      <div className="space-y-2 pb-2">
        <WindowPicker value={win} onChange={setWin} />
        <FloorControl value={floor} onChange={setFloor} />
      </div>
      {isValidating && data ? (
        <p role="status" className="text-caption text-ink-2">
          Updating
        </p>
      ) : null}

      {error && !data ? <ErrorState message={error.message} onRetry={() => mutate()} /> : null}
      {isLoading && !data ? <Skeleton label="Loading today's filings" /> : null}

      {data && !empty ? (
        <>
          {data.stories.length ? (
            <StoryList stories={data.stories} subscribed={rules.categories} />
          ) : (
            <p className="border-t border-rule py-6 text-ink-2">
              Nothing at this level. Lower the bar to Everything, or widen the window.
            </p>
          )}
          <RoutineDrawer digest={data} open={drawer} onToggle={() => setDrawer((v) => !v)} />
        </>
      ) : null}
    </>
  );
}
