// Filled out in Plan 4 Task 6.
import type { Dossier } from "@/lib/types";

export function DossierView({ dossier }: { dossier: Dossier }) {
  return <h1 className="pt-2 text-section font-semibold">{dossier.name ?? dossier.symbol}</h1>;
}
