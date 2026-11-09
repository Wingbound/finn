import type { Citation, Point, Source } from "@/lib/types";
import { CitationChip } from "./CitationChip";

/** FINN's sentences, each followed by the citation it stands on. */
export function Points({
  points,
  sources,
  onCite,
}: {
  points: Point[];
  sources: Source[];
  onCite: (c: Citation) => void;
}) {
  return (
    <ul className="mt-2 space-y-3">
      {points.map((p) => (
        <li key={`${p.text}-${p.citation.page}`}>
          <p>{p.text}</p>
          <div className="mt-1">
            <CitationChip citation={p.citation} sources={sources} onOpen={onCite} />
          </div>
        </li>
      ))}
    </ul>
  );
}
