import { plural } from "@/lib/format";

function windowLabel(hours: number): string {
  if (hours % 24 === 0 && hours > 24) return `${hours / 24} days`;
  return `${hours} hours`;
}

/**
 * Nothing at this level in a short window is the normal state of a quiet market, not a dead
 * end: say so plainly, and say what the last week held, one tap away.
 */
export function QuietTeaser({ hours, count, onShow }: { hours: number; count: number; onShow: () => void }) {
  return (
    <section className="border-t border-rule py-6">
      <p className="text-title">Quiet {windowLabel(hours)}.</p>
      <p className="mt-1 text-ink-2">
        Over the last 7 days, {plural(count, "thing")} mattered.
      </p>
      <button
        type="button"
        onClick={onShow}
        className="mt-3 min-h-11 rounded-lg border border-rule px-4 font-medium text-pencil"
      >
        Show 7 days
      </button>
    </section>
  );
}
