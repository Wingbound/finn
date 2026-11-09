"use client";

import { useEffect, useState } from "react";
import { OFFLINE_EVENT } from "@/lib/api";
import { stamp } from "@/lib/format";

/** Registers the worker in production builds and says when a screen is showing saved data. */
export function ServiceWorker() {
  const [savedAt, setSavedAt] = useState<string | null>(null);

  useEffect(() => {
    if (process.env.NODE_ENV === "production" && "serviceWorker" in navigator) {
      navigator.serviceWorker.register("/sw.js").catch(() => {
        // no worker (private mode, unsupported browser): the app works without one
      });
    }
    const onOffline = (e: Event) => setSavedAt((e as CustomEvent<string | null>).detail);
    window.addEventListener(OFFLINE_EVENT, onOffline);
    return () => window.removeEventListener(OFFLINE_EVENT, onOffline);
  }, []);

  if (savedAt === null) return null;
  return (
    <p
      role="status"
      className="fixed inset-x-0 top-0 z-30 bg-ink px-4 py-1.5 pt-[max(0.375rem,env(safe-area-inset-top))] text-center text-caption text-paper"
    >
      Offline: showing what FINN had{savedAt ? ` at ${stamp(savedAt)}` : ""}.
    </p>
  );
}
