import { categoryLabel, cleanSubject, plural } from "./format";
import type { Digest, PersonChange, Story } from "./types";

/** At most this many stories are read aloud; the rest are named as a count. */
export const SPOKEN_STORIES = 6;

const CHANGE: Record<PersonChange["change"], string> = {
  appointed: "appointed",
  resigned: "resigned",
  retired: "retired",
  ceased: "ceased",
  redesignated: "redesignated",
  other: "changed role",
};

function windowPhrase(d: Digest): string {
  const hours = Math.round((Date.parse(d.window.end) - Date.parse(d.window.start)) / 3_600_000);
  if (hours === 24) return "the last 24 hours";
  if (hours > 24 && hours % 24 === 0) return `the last ${hours / 24} days`;
  return "this window";
}

const spokenName = (company: string) => company.replace(/\s+(?:limited|ltd\.?)$/i, "");
const sentence = (s: string) => (/[.!?]$/.test(s.trim()) ? s.trim() : `${s.trim()}.`);
const words = (s: string, n: number) => s.split(/\s+/).slice(0, n).join(" ");

/** "up 11.5 percent": the filed figure, rounded for the ear; nothing is computed. */
function move(v: number): string {
  if (v === 0) return "flat";
  return `${v > 0 ? "up" : "down"} ${Math.abs(v).toFixed(1)} percent`;
}

function resultsLine(s: Story): string | null {
  const rows = s.results?.metrics ?? [];
  const revenue = rows.find((m) => m.key === "revenue" && m.yoy_pct !== null);
  const pat = rows.find((m) => m.key === "pat" && m.yoy_pct !== null);
  const parts: string[] = [];
  if (revenue) parts.push(`Revenue ${move(revenue.yoy_pct as number)} year on year`);
  if (pat) parts.push(`PAT ${move(pat.yoy_pct as number)}${revenue ? "" : " year on year"}`);
  return parts.length ? `${parts.join(", ")}.` : null;
}

function peopleLine(s: Story): string | null {
  const people = s.people.slice(0, 2).map((p) => {
    const name = p.name.replace(/^(Mr|Mrs|Ms|Dr|Shri|Smt)\.?\s+/i, "");
    return p.role ? `${name}, ${CHANGE[p.change]} as ${p.role}` : `${name}, ${CHANGE[p.change]}`;
  });
  return people.length ? sentence(people.join("; ")) : null;
}

function storyLine(s: Story): string {
  const what =
    (s.category === "results" ? resultsLine(s) : null) ??
    (s.people.length ? peopleLine(s) : null) ??
    (s.brief ? sentence(s.brief.one_liner) : null) ??
    sentence(words(cleanSubject(s.headline.filing.subject), 30));
  return `${spokenName(s.company)}: ${categoryLabel(s.category).toLowerCase()}. ${what}`;
}

/**
 * Today as a minute of speech: how much matters, the first few stories in the order the
 * screen ranks them, and where the reader stands. Every figure is one the digest carries.
 */
export function briefScript(d: Digest): string[] {
  const span = windowPhrase(d);
  const n = d.counts.shown;
  const lines = [n === 0 ? `Nothing matters in ${span}.` : `${plural(n, "thing")} ${n === 1 ? "matters" : "matter"} in ${span}.`];
  lines.push(...d.stories.slice(0, SPOKEN_STORIES).map(storyLine));
  if (d.stories.length > SPOKEN_STORIES) lines.push(`And ${d.stories.length - SPOKEN_STORIES} more on screen.`);
  if (d.counts.routine > 0) lines.push(`${plural(d.counts.routine, "routine filing")} set aside.`);
  lines.push("You're caught up.");
  return lines;
}
