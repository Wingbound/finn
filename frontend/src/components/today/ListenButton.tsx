"use client";

import { useEffect, useState, useSyncExternalStore } from "react";

function canSpeak(): boolean {
  return (
    typeof window !== "undefined" &&
    typeof window.speechSynthesis?.speak === "function" &&
    typeof window.SpeechSynthesisUtterance === "function"
  );
}

const noSubscribe = () => () => {};

/** The phone's own voice reads Today's brief: no server, no cost. Hidden where it can't speak. */
export function ListenButton({ lines }: { lines: string[] }) {
  // false on the server and in the first client render, so hydration matches
  const supported = useSyncExternalStore(noSubscribe, canSpeak, () => false);
  const [speaking, setSpeaking] = useState(false);

  useEffect(() => {
    if (!canSpeak()) return;
    const hide = () => {
      if (document.visibilityState === "hidden") {
        window.speechSynthesis?.cancel();
        setSpeaking(false);
      }
    };
    document.addEventListener("visibilitychange", hide);
    return () => {
      document.removeEventListener("visibilitychange", hide);
      window.speechSynthesis?.cancel(); // leaving Today stops the voice
    };
  }, []);

  if (!supported || !lines.length) return null;

  const start = () => {
    const synth = window.speechSynthesis;
    synth.cancel();
    const voices = synth.getVoices();
    const voice = voices.find((v) => v.lang === "en-IN") ?? voices.find((v) => v.lang.startsWith("en")) ?? null;
    lines.forEach((text, i) => {
      const u = new window.SpeechSynthesisUtterance(text);
      u.lang = "en-IN";
      if (voice) u.voice = voice;
      if (i === lines.length - 1) {
        u.onend = () => setSpeaking(false);
        u.onerror = () => setSpeaking(false);
      }
      synth.speak(u);
    });
    setSpeaking(true);
  };
  const stop = () => {
    window.speechSynthesis.cancel();
    setSpeaking(false);
  };

  return (
    <button
      type="button"
      onClick={speaking ? stop : start}
      className="inline-flex min-h-11 items-center gap-2 rounded-lg border border-rule px-4 text-caption font-medium text-pencil"
    >
      <span aria-hidden="true">{speaking ? "■" : "▶"}</span>
      {speaking ? "Stop listening" : "Listen"}
    </button>
  );
}
