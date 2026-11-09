import type { Citation, Source } from "@/lib/types";
import { citeLabel } from "./cite";

export function CitationChip({
  citation,
  sources,
  onOpen,
  prefix,
}: {
  citation: Citation;
  sources: Source[];
  onOpen: (c: Citation) => void;
  prefix?: string;
}) {
  const label = citeLabel(citation, sources);
  return (
    <button
      type="button"
      onClick={() => onOpen(citation)}
      className="inline-flex min-h-8 items-center rounded-md border border-rule px-2 font-sans text-caption text-pencil not-italic"
    >
      {prefix ? `${prefix} ${label}` : label}
    </button>
  );
}
