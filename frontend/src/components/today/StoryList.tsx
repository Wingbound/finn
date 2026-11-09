"use client";

import { KEYS, useStored, validateSeen } from "@/lib/store";
import type { Category, Story } from "@/lib/types";
import { StoryCard } from "./StoryCard";

const NONE: string[] = [];

/** Unseen stories first, in the server's ranking; seen ones sink to the end, dimmed. */
export function StoryList({ stories, now }: { stories: Story[]; subscribed: Category[]; now?: Date }) {
  const [seen, setSeen] = useStored(KEYS.seen, NONE, validateSeen);
  const isSeen = new Set(seen);
  const ordered = [...stories.filter((s) => !isSeen.has(s.id)), ...stories.filter((s) => isSeen.has(s.id))];
  const toggle = (id: string) =>
    setSeen((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id].slice(-500)));
  return (
    <div>
      {ordered.map((s) => (
        <StoryCard key={s.id} story={s} seen={isSeen.has(s.id)} onToggleSeen={() => toggle(s.id)} now={now} />
      ))}
    </div>
  );
}
