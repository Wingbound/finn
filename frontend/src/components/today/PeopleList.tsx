"use client";

import { useState } from "react";
import type { PersonChange } from "@/lib/types";

const VERB: Record<PersonChange["change"], string> = {
  appointed: "Appointed",
  resigned: "Resigned",
  retired: "Retiring",
  ceased: "Ceased",
  redesignated: "Redesignated",
  other: "Change",
};

function Profile({ text }: { text: string }) {
  const [open, setOpen] = useState(false);
  const long = text.split(/\s+/).length > 45;
  return (
    <div className="mt-1">
      {/* the profile is the filing's own text, so it is set as a quote */}
      <p className={`quote text-ink ${open || !long ? "" : "line-clamp-3"}`}>{text}</p>
      {long ? (
        <button type="button" className="min-h-11 text-caption text-pencil" onClick={() => setOpen((v) => !v)} aria-expanded={open}>
          {open ? "Show less" : "Show more"}
        </button>
      ) : null}
    </div>
  );
}

export function PeopleList({ people }: { people: PersonChange[] }) {
  return (
    <ul className="mt-2 space-y-3">
      {people.map((p) => (
        <li key={`${p.name}-${p.change}`}>
          <p className="font-semibold">{p.name.replace(/^(Mr|Mrs|Ms|Dr|Shri|Smt)\.?\s+/i, "")}</p>
          <p className="text-ink-2">
            {VERB[p.change]}
            {p.role ? `, ${p.role}` : ""}
            {p.effective ? ` (${p.effective})` : ""}
          </p>
          {p.profile ? <Profile text={p.profile} /> : null}
        </li>
      ))}
    </ul>
  );
}
