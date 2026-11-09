"use client";

import Link from "next/link";
import { useState } from "react";
import { symbolPath } from "@/lib/api";
import { categoryLabel, cleanSubject, plural, stamp, when } from "@/lib/format";
import type { Story } from "@/lib/types";
import { BriefBlock } from "./BriefBlock";
import { PeopleList } from "./PeopleList";
import { ResultsGrid } from "./ResultsGrid";

function Body({ story }: { story: Story }) {
  if (story.results) return <ResultsGrid card={story.results} />;
  if (story.people.length) return <PeopleList people={story.people} />;
  if (story.brief) return <BriefBlock brief={story.brief} />;
  return <p className="mt-1.5 text-ink-2">{cleanSubject(story.headline.filing.subject)}</p>;
}

export function StoryCard({
  story,
  seen,
  onToggleSeen,
  now,
}: {
  story: Story;
  seen: boolean;
  onToggleSeen: () => void;
  now?: Date;
}) {
  const [why, setWhy] = useState(false);
  const [members, setMembers] = useState(false);
  const pdf = story.headline.filing.pdf_url;
  const label = `${story.symbol} ${categoryLabel(story.category).toLowerCase()}`;
  return (
    <article
      data-story={story.id}
      id={`story-${story.id}`}
      aria-label={`${story.symbol}: ${categoryLabel(story.category)}`}
      className={`grid grid-cols-[2.25rem_minmax(0,1fr)] border-t border-rule py-4 ${seen ? "opacity-55" : ""}`}
    >
      <button
        type="button"
        onClick={onToggleSeen}
        aria-pressed={seen}
        aria-label={seen ? `Mark ${label} unseen` : `Mark ${label} seen`}
        className="-ml-2 flex h-11 w-11 items-start justify-center pt-0.5"
      >
        <span
          aria-hidden="true"
          className={`flex h-5 w-5 items-center justify-center rounded-full border-[1.5px] text-[12px] leading-none ${
            seen ? "border-pencil bg-pencil text-paper" : "border-rule text-transparent"
          }`}
        >
          ✓
        </span>
      </button>
      <div className="min-w-0">
        <div className="flex items-baseline justify-between gap-3">
          <p className="min-w-0 truncate">
            <span className="text-title font-semibold">{story.symbol}</span>
            <span className="ml-2 text-caption text-ink-2">{categoryLabel(story.category)}</span>
          </p>
          <time dateTime={story.latest_at} title={stamp(story.latest_at, now)} className="shrink-0 text-caption text-ink-2">
            {when(story.latest_at, now)}
          </time>
        </div>
        <p className="truncate text-caption text-ink-2">{story.company}</p>
        <Body story={story} />

        <div className="mt-2 flex flex-wrap items-center gap-x-4 text-caption">
          <button type="button" className="min-h-11 text-ink-2" aria-expanded={why} onClick={() => setWhy((v) => !v)}>
            Why it&rsquo;s here
          </button>
          {story.members.length > 1 ? (
            <button type="button" className="min-h-11 text-ink-2" aria-expanded={members} onClick={() => setMembers((v) => !v)}>
              {plural(story.members.length, "filing")}
            </button>
          ) : null}
          <span className="ml-auto flex gap-4">
            {pdf ? (
              <a href={pdf} target="_blank" rel="noopener noreferrer" className="flex min-h-11 items-center text-pencil">
                Open filing
              </a>
            ) : null}
            <Link href={`/research/${symbolPath(story.symbol)}`} className="flex min-h-11 items-center font-semibold text-pencil">
              Dig in
            </Link>
          </span>
        </div>
        {why ? (
          <p className="text-caption text-ink-2">
            Score {story.score}: {story.headline.reasons.join(", ")}.
          </p>
        ) : null}
        {members ? (
          <ul className="mt-1 space-y-1.5 text-caption">
            {story.members.map((m) => (
              <li key={m.filing.seq_id} className="flex gap-3">
                <span className="min-w-0 flex-1 text-ink-2">{cleanSubject(m.filing.subject)}</span>
                {m.filing.pdf_url ? (
                  <a href={m.filing.pdf_url} target="_blank" rel="noopener noreferrer" className="shrink-0 text-pencil">
                    PDF
                  </a>
                ) : null}
              </li>
            ))}
          </ul>
        ) : null}
      </div>
    </article>
  );
}
