const KEYS: Record<string, RegExp> = {
  ledger: /ledger|promise/i,
  snapshot: /snapshot/i,
  trajectory: /financials|trajectory/i,
  health: /financials|balance/i,
  bullbear: /bull/i,
};

/** Why a section is missing: the build's own note when it left one, else a plain default. */
export function SectionNote({ section, notes }: { section: keyof typeof KEYS; notes: string[] }) {
  const note = notes.find((n) => KEYS[section]?.test(n));
  return <p className="py-2 text-ink-2">{note ?? "Not available for this company."}</p>;
}
