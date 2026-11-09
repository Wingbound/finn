"use client";

import { useState } from "react";
import { Sheet } from "@/components/Sheet";
import { Segmented } from "@/components/States";
import { day } from "@/lib/format";
import type { WindowChoice } from "@/lib/store";

const PRESETS = [
  { value: 24, label: "24 hours" },
  { value: 72, label: "3 days" },
  { value: 168, label: "7 days" },
];

/** "2026-11-07T09:00" typed on any device means 09:00 IST. */
export const istInput = (v: string) => `${v}:00+05:30`;
const toInput = (d: Date) => new Date(d.getTime() + 330 * 60_000).toISOString().slice(0, 16);

export function WindowPicker({ value, onChange }: { value: WindowChoice; onChange: (w: WindowChoice) => void }) {
  const [open, setOpen] = useState(false);
  const now = new Date();
  const [start, setStart] = useState(toInput(new Date(now.getTime() - 7 * 86_400_000)));
  const [end, setEnd] = useState(toInput(now));
  const custom = value.kind === "range";
  const valid = start && end && Date.parse(istInput(start)) <= Date.parse(istInput(end));
  return (
    <div>
      <Segmented
        label="Window"
        options={[...PRESETS, { value: -1, label: custom ? `${day(value.start)} to ${day(value.end)}` : "Custom" }]}
        value={value.kind === "hours" ? value.hours : -1}
        onChange={(v) => (v === -1 ? setOpen(true) : onChange({ kind: "hours", hours: v }))}
      />
      <Sheet open={open} onClose={() => setOpen(false)} title="Choose a window">
        <form
          className="space-y-3"
          onSubmit={(e) => {
            e.preventDefault();
            if (!valid) return;
            onChange({ kind: "range", start: istInput(start), end: istInput(end) });
            setOpen(false);
          }}
        >
          <label className="block">
            <span className="text-caption text-ink-2">From (IST)</span>
            <input type="datetime-local" value={start} onChange={(e) => setStart(e.target.value)} className="mt-1 block min-h-11 w-full rounded-lg border border-rule bg-paper px-3" />
          </label>
          <label className="block">
            <span className="text-caption text-ink-2">To (IST)</span>
            <input type="datetime-local" value={end} onChange={(e) => setEnd(e.target.value)} className="mt-1 block min-h-11 w-full rounded-lg border border-rule bg-paper px-3" />
          </label>
          {!valid ? <p className="text-caption text-missed">The start must come before the end.</p> : null}
          <button type="submit" disabled={!valid} className="min-h-11 w-full rounded-lg bg-pencil font-semibold text-paper disabled:opacity-40">
            Show this window
          </button>
        </form>
      </Sheet>
    </div>
  );
}
