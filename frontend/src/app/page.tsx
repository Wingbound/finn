"use client";

import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import { ErrorState, Skeleton } from "@/components/States";
import { FloorControl } from "@/components/today/FloorControl";
import { Header } from "@/components/today/Header";
import { ListenButton } from "@/components/today/ListenButton";
import { QuietTeaser } from "@/components/today/QuietTeaser";
import { RoutineDrawer } from "@/components/today/RoutineDrawer";
import { StaleNotice, isEmptyWindow } from "@/components/today/StaleNotice";
import { StoryList } from "@/components/today/StoryList";
import { WindowPicker } from "@/components/today/WindowPicker";
import { briefScript } from "@/lib/briefScript";
import { useDigest } from "@/lib/hooks";
import {
  DEFAULT_FLOOR,
  DEFAULT_RULES,
  DEFAULT_WINDOW,
  KEYS,
  rangeFromSearch,
  useStored,
  validateFloor,
  validateRules,
  validateWindow,
} from "@/lib/store";
import type { WindowChoice } from "@/lib/store";
import type { DigestRequest } from "@/lib/types";

function subscribeHash(onChange: () => void) {
  window.addEventListener("hashchange", onChange);
  window.addEventListener("popstate", onChange);
  return () => {
    window.removeEventListener("hashchange", onChange);
    window.removeEventListener("popstate", onChange);
  };
}

function storyFromHash(hash: string): string | null {
  try {
    const h = decodeURIComponent(hash.slice(1));
    return h.startsWith("story-") ? h.slice("story-".length) : null;
  } catch {
    return null;
  }
}

export default function TodayPage() {
  const [rules, , rulesReady] = useStored(KEYS.rules, DEFAULT_RULES, validateRules);
  const [floor, setFloor, floorReady] = useStored(KEYS.floor, DEFAULT_FLOOR, validateFloor);
  const [win, setWin, winReady] = useStored(KEYS.window, DEFAULT_WINDOW, validateWindow);
  const [drawer, setDrawer] = useState(false);
  const [dismissed, setDismissed] = useState(false);
  // An alert links here as /#story-<id>. Subscribed, not read once: on a client-side
  // navigation the URL changes after the first render. A garbled hash is ignored.
  const hash = useSyncExternalStore(subscribeHash, () => window.location.hash, () => "");
  const target = storyFromHash(hash);
  const scrolled = useRef(false);
  // An alert's own week arrives as ?from=&to=: shown for this visit, never saved over the
  // reader's window. Picking a window drops it.
  const search = useSyncExternalStore(subscribeHash, () => window.location.search, () => "");
  const once = rangeFromSearch(search);
  const active: WindowChoice = once ?? win;
  const choose = (w: WindowChoice) => {
    if (once) window.history.replaceState(null, "", "/");
    setWin(w);
  };

  const ready = rulesReady && floorReady && winReady;
  const req: DigestRequest | null = ready
    ? {
        ...(active.kind === "hours" ? { hours: active.hours } : { start: active.start, end: active.end }),
        floor,
        subscribed: rules.categories,
      }
    : null;
  const { data, error, isLoading, isValidating, mutate } = useDigest(req);

  const openDrawer = () => {
    setDrawer(true);
    requestAnimationFrame(() => document.getElementById("routine")?.scrollIntoView({ behavior: "smooth" }));
  };
  const empty = !!data && isEmptyWindow(data.counts);
  // Nothing at this level in a short preset window: ask what the last 7 days hold.
  const quiet = !!data && !empty && data.stories.length === 0 && active.kind === "hours" && active.hours < 168;
  const week = useDigest(quiet ? { hours: 168, floor, subscribed: rules.categories } : null, { keepPrevious: false });
  const weekCount = week.data?.stories.length ?? 0;
  // Until both answers are in, the slot stays empty: no "Nothing at this level" flash before
  // the teaser, and no teaser over a window that is still loading.
  const weekSettled = !!week.data && !week.isValidating;
  const teaser = quiet && !isValidating && weekSettled && weekCount > 0;
  const waiting = quiet && (isValidating || !weekSettled);

  const inStories = !!target && !!data?.stories.some((st) => st.id === target);
  const inRoutine = !!target && Object.values(data?.routine ?? {}).some((list) => list?.some((st) => st.id === target));
  const drawerOpen = drawer || (inRoutine && !dismissed);
  const outside = !!data && !!target && !inStories && !inRoutine;

  // Bring the linked story into view once, after it has rendered (the drawer opens for routine ones).
  useEffect(() => {
    if (!target || scrolled.current || !(inStories || inRoutine)) return;
    scrolled.current = true;
    requestAnimationFrame(() => document.getElementById(`story-${target}`)?.scrollIntoView({ block: inRoutine ? "center" : "start" }));
  }, [target, inStories, inRoutine]);

  return (
    <>
      {data && !empty ? (
        <>
          <Header counts={data.counts} onOpenRoutine={openDrawer} />
          <div className="-mt-3 pb-3">
            <ListenButton lines={briefScript(data)} />
          </div>
        </>
      ) : null}
      {empty && data ? (
        <StaleNotice latest={data.latest_filing_at} window={active} onChoose={choose} />
      ) : null}
      {!data && !error ? <h1 className="sr-only">Today</h1> : null}

      <div className="space-y-2 pb-2">
        <WindowPicker value={active} onChange={choose} />
        <FloorControl value={floor} onChange={setFloor} />
      </div>
      {/* Always mounted and visually hidden: a line appearing above the stories would shift
          them on every refresh. The list dims instead while the new window loads. */}
      <p role="status" className="sr-only">
        {isValidating && data ? "Updating" : ""}
      </p>

      {outside ? <p className="py-2 text-ink-2">That story is outside this window.</p> : null}
      {error && !data ? <ErrorState message={error.message} onRetry={() => mutate()} /> : null}
      {error && data ? (
        <ErrorState
          message={error.message}
          note="Below, FINN is still showing the previous window."
          onRetry={() => mutate()}
        />
      ) : null}
      {isLoading && !data ? <Skeleton label="Loading today's filings" /> : null}

      {data && !empty ? (
        <div aria-busy={isValidating} className={`transition-opacity ${isValidating ? "opacity-60" : ""}`}>
          {data.stories.length ? (
            <StoryList stories={data.stories} subscribed={rules.categories} />
          ) : teaser && active.kind === "hours" ? (
            <QuietTeaser hours={active.hours} count={weekCount} onShow={() => choose({ kind: "hours", hours: 168 })} />
          ) : waiting && !week.error ? (
            <div className="min-h-24 border-t border-rule" aria-hidden="true" />
          ) : (
            <p className="border-t border-rule py-6 text-ink-2">
              Nothing at this level. Lower the bar to Everything, or widen the window.
            </p>
          )}
          <RoutineDrawer
            digest={data}
            open={drawerOpen}
            onToggle={() => {
              if (drawerOpen) setDismissed(true);
              setDrawer(!drawerOpen);
            }}
          />
        </div>
      ) : null}
    </>
  );
}
