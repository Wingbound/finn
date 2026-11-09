import { STATUS_ORDER, statusLabel } from "@/lib/format";
import type { Status } from "@/lib/types";

const COLOR: Record<Status, string> = {
  kept: "var(--kept)",
  partly: "var(--partly)",
  missed: "var(--missed)",
  pending: "var(--pending)",
  dropped: "transparent",
};

/** The ledger at a glance: proportional segments (2px gaps) and the same counts in words. */
export function Tally({ counts, className = "" }: { counts: Partial<Record<Status, number>>; className?: string }) {
  const present = STATUS_ORDER.filter((s) => (counts[s] ?? 0) > 0);
  if (!present.length) return null;
  const words = present.map((s) => `${counts[s]} ${s === "dropped" ? "not mentioned again" : statusLabel(s).word.toLowerCase()}`);
  return (
    <div className={className}>
      <div className="flex h-2 gap-[2px]" aria-hidden="true">
        {present.map((s) => (
          <span
            key={s}
            data-status={s}
            className="block min-w-[3px] rounded-[2px]"
            style={{
              flexGrow: counts[s],
              flexBasis: 0,
              background: COLOR[s],
              boxShadow: s === "dropped" ? "inset 0 0 0 1px var(--pending)" : undefined,
            }}
          />
        ))}
      </div>
      <p className="mt-1 text-caption text-ink-2">{words.join(", ")}</p>
    </div>
  );
}
