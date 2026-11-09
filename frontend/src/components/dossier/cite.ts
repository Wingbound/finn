import type { Citation, Source } from "@/lib/types";

export const FACTS_LABEL = "Computed from filed financials";

/** "Q4 FY26 call, p. 7" ("Q4 FY26 call (May 2026), p. 7" when two calls share the quarter),
 *  "Annual report 2026, p. 5", or the FACTS label. */
export function citeLabel(c: Citation, sources: Source[]): string {
  if (c.source_id === "FACTS") return FACTS_LABEL;
  const s = sources.find((x) => x.id === c.source_id);
  if (!s) return `${c.source_id}, p. ${c.page}`;
  if (s.kind === "transcript" && s.quarter) {
    const twins = sources.filter((x) => x.kind === "transcript" && x.quarter === s.quarter).length > 1;
    const month = twins ? s.title.match(/\(([A-Za-z]{3,9} \d{4})\)/)?.[1] : undefined;
    return `${s.quarter} call${month ? ` (${month})` : ""}, p. ${c.page}`;
  }
  return `${s.title.replace(/^Annual Report/i, "Annual report")}, p. ${c.page}`;
}
