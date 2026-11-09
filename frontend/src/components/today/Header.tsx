import { PencilStrike } from "@/components/PencilStrike";
import { plural } from "@/lib/format";
import type { Digest } from "@/lib/types";

export function headline(shown: number): string {
  if (shown === 0) return "Nothing matters yet";
  return shown === 1 ? "1 thing matters" : `${shown} things matter`;
}

export function Header({ counts, onOpenRoutine }: { counts: Digest["counts"]; onOpenRoutine: () => void }) {
  return (
    <header className="pt-2 pb-5">
      <h1 className="text-headline font-semibold tracking-[-0.01em]">{headline(counts.shown)}</h1>
      {counts.routine > 0 ? (
        <button
          type="button"
          onClick={onOpenRoutine}
          className="mt-2 min-h-11 text-left text-title text-ink-2"
        >
          <PencilStrike>{plural(counts.routine, "routine filing")}</PencilStrike>{" "}
          <span className="ml-1 text-caption text-pencil">set aside</span>
          <span className="sr-only">. Show them</span>
        </button>
      ) : null}
      {counts.hidden > 0 ? (
        <p className="text-caption text-ink-2">{plural(counts.hidden, "piece")} of noise dropped</p>
      ) : null}
    </header>
  );
}
