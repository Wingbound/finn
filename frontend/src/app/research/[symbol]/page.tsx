// Replaced by the dossier screen in Plan 4 Task 6.
export default async function DossierPage({ params }: { params: Promise<{ symbol: string }> }) {
  const { symbol } = await params;
  return <h1 className="text-section font-semibold">{decodeURIComponent(symbol)}</h1>;
}
