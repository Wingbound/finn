"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";
import { BuildProgress } from "@/components/research/BuildProgress";
import { ErrorState, Skeleton } from "@/components/States";
import { primeDossier, useDossier } from "@/lib/hooks";
import { DossierView } from "./DossierView";

export function DossierScreen({ symbol }: { symbol: string }) {
  const params = useSearchParams();
  const router = useRouter();
  const [building, setBuilding] = useState(params.get("build") === "1");
  // While building, the stored dossier is known to be missing; don't ask for it.
  const { data, error, isLoading, mutate } = useDossier(building ? null : symbol);

  if (building) {
    return (
      <>
        <Back />
        <BuildProgress
          symbol={symbol}
          onDone={async ({ dossier, excerpts }) => {
            await primeDossier(dossier, excerpts);
            setBuilding(false);
            router.replace(`/research/${encodeURIComponent(symbol)}`);
          }}
          onCancel={() => {
            // Drop ?build=1 too, or a reload would start another build.
            setBuilding(false);
            router.replace(`/research/${encodeURIComponent(symbol)}`);
          }}
          onCheckSaved={() => {
            setBuilding(false);
            router.replace(`/research/${encodeURIComponent(symbol)}`);
          }}
        />
      </>
    );
  }
  if (error && !data) {
    return (
      <>
        <Back />
        <ErrorState message={error.message} onRetry={() => mutate()} />
      </>
    );
  }
  if (isLoading && !data) return <Skeleton label="Loading the dossier" />;
  if (data === null || data === undefined) {
    return (
      <>
        <Back />
        <h1 className="pt-2 text-section font-semibold">{symbol}</h1>
        <p className="mt-1 text-ink-2">
          FINN hasn&rsquo;t read this company yet. A build reads its last four earnings calls and latest annual report,
          usually in 40 to 90 seconds.
        </p>
        <button type="button" onClick={() => setBuilding(true)} className="mt-4 min-h-11 rounded-lg bg-pencil px-5 font-semibold text-paper">
          Build a dossier
        </button>
      </>
    );
  }
  return (
    <>
      <Back />
      <DossierView dossier={data} />
    </>
  );
}

function Back() {
  return (
    <Link href="/research" className="inline-flex min-h-11 items-center text-caption text-pencil">
      All research
    </Link>
  );
}
