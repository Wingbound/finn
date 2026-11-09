import { Suspense } from "react";
import { DossierScreen } from "@/components/dossier/DossierScreen";
import { Skeleton } from "@/components/States";

export default async function DossierPage({ params }: { params: Promise<{ symbol: string }> }) {
  const { symbol } = await params;
  return (
    <Suspense fallback={<Skeleton label="Loading the dossier" />}>
      <DossierScreen symbol={decodeURIComponent(symbol).toUpperCase()} />
    </Suspense>
  );
}
