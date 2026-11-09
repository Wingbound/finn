import Link from "next/link";
import { Tally } from "@/components/Tally";
import { symbolPath } from "@/lib/api";
import { day } from "@/lib/format";
import type { ResearchListItem } from "@/lib/types";

export function DossierList({ items }: { items: ResearchListItem[] }) {
  return (
    <ul>
      {items.map((d) => (
        <li key={d.symbol} className="border-t border-rule">
          <Link href={`/research/${symbolPath(d.symbol)}`} className="block py-3">
            <span className="flex items-baseline justify-between gap-3">
              <span className="min-w-0 truncate font-semibold">{d.name ?? d.symbol}</span>
              <span className="shrink-0 text-caption text-ink-2">{d.symbol}</span>
            </span>
            <span className="block text-caption text-ink-2">
              {d.counts.ledger_rows} promises tracked, built {day(d.built_at)}
            </span>
            <Tally counts={d.counts.ledger ?? {}} className="mt-2" />
          </Link>
        </li>
      ))}
    </ul>
  );
}
