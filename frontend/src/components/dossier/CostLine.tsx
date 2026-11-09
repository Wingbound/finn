import type { Dossier } from "@/lib/types";

/** What this dossier cost to build, or that it came from FINN's cache. */
export function costText(d: Dossier): string {
  const calls = typeof d.cost.calls === "number" ? d.cost.calls : 0;
  const cached = typeof d.cost.cached === "number" ? d.cost.cached : 0;
  const usd = typeof d.cost.usd_list_price === "number" ? d.cost.usd_list_price : 0;
  const secs = Math.round(d.build_seconds);
  if (!calls) return `Built in ${secs} s with no model calls.`;
  if (usd > 0) return `${calls} model calls, $${usd.toFixed(3)} at list price, ${secs} s to build.`;
  if (cached >= calls) return `Served from cache: ${calls} model calls reused, no new cost.`;
  return `${calls} model calls (${cached} reused), ${secs} s to build. The judge model has no published price.`;
}

export function CostLine({ dossier }: { dossier: Dossier }) {
  return <p className="text-caption text-ink-2">{costText(dossier)}</p>;
}
