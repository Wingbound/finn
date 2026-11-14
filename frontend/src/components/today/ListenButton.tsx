"use client";

import { useEffect, useRef, useState, useSyncExternalStore } from "react";

function canSpeak(): boolean {
  return (
    typeof window !== "undefined" &&
    typeof window.speechSynthesis?.speak === "function" &&
    typeof window.SpeechSynthesisUtterance === "function"
  );
}

const noSubscribe = () => () => {};
// Some Android builds report "en_IN"
const isLang = (v: SpeechSynthesisVoice, lang: string) => v.lang.replace("_", "-").startsWith(lang);

/** The phone's own voice reads Today's brief: no server, no cost. Hidden where it can't speak. */
export function ListenButton({ lines }: { lines: string[] }) {
  // false on the server and in the first client render, so hydration matches
  const supported = useSyncExternalStore(noSubscribe, canSpeak, () => false);
  const [speaking, setSpeaking] = useState(false);
  const speakingRef = useRef(false);
  // Chromium can garbage-collect a queued utterance and never fire its onend: keep them.
  const queue = useRef<SpeechSynthesisUtterance[]>([]);
  const key = lines.join("\n");

  // A new brief (another window, another floor) stops the old one mid-sentence.
  useEffect(
    () => () => {
      if (!speakingRef.current) return;
      window.speechSynthesis?.cancel();
      speakingRef.current = false;
      queue.current = [];
      setSpeaking(false);
    },
    [key],
  );

  useEffect(() => {
    if (!canSpeak()) return;
    const hide = () => {
      if (document.visibilityState === "hidden") {
        window.speechSynthesis?.cancel();
        speakingRef.current = false;
        queue.current = [];
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

  const done = () => {
    speakingRef.current = false;
    queue.current = [];
    setSpeaking(false);
  };
  const start = () => {
    const synth = window.speechSynthesis;
    // cancel only what is playing: some Chrome builds drop a speak() issued right after cancel()
    if (synth.speaking || synth.pending) synth.cancel();
    const voices = synth.getVoices();
    const voice = voices.find((v) => isLang(v, "en-IN")) ?? voices.find((v) => isLang(v, "en")) ?? null;
    queue.current = lines.map((text, i) => {
      const u = new window.SpeechSynthesisUtterance(text);
      u.lang = "en-IN";
      if (voice) u.voice = voice;
      if (i === lines.length - 1) {
        u.onend = done;
        u.onerror = done;
      }
      return u;
    });
    queue.current.forEach((u) => synth.speak(u));
    speakingRef.current = true;
    setSpeaking(true);
  };
  const stop = () => {
    window.speechSynthesis.cancel();
    done();
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
