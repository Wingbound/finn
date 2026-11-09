"use client";

import useSWR, { mutate } from "swr";
import { ApiError, apiGet, apiPost, symbolPath } from "./api";
import type {
  AlertsResponse,
  Digest,
  DigestRequest,
  Dossier,
  Excerpts,
  Portfolio,
  ResearchListItem,
  ResultsCard,
  Rules,
  SourcePage,
} from "./types";

/** null when the server says the thing doesn't exist (404); other failures still throw. */
async function orNull<T>(p: Promise<T>): Promise<T | null> {
  try {
    return await p;
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) return null;
    throw e;
  }
}

export function useDigest(req: DigestRequest | null) {
  return useSWR<Digest, ApiError>(req ? ["digest", JSON.stringify(req)] : null, () =>
    apiPost<Digest>("/digest", req),
  );
}

export function usePortfolio() {
  return useSWR<Portfolio, ApiError>("portfolio", () => apiGet<Portfolio>("/portfolio"));
}

export function useAlerts(rules: Rules | null) {
  return useSWR<AlertsResponse, ApiError>(rules ? ["alerts", JSON.stringify(rules)] : null, () =>
    apiPost<AlertsResponse>("/alerts", rules),
  );
}

export function useResults(symbol: string | null) {
  return useSWR<ResultsCard | null, ApiError>(symbol ? ["results", symbol] : null, () =>
    orNull(apiGet<ResultsCard>(`/results/${symbolPath(symbol as string)}`)),
  );
}

export function useResearchList() {
  return useSWR<ResearchListItem[], ApiError>("research", () => apiGet<ResearchListItem[]>("/research"));
}

const dossierKey = (symbol: string) => ["dossier", symbol.trim().toUpperCase()];
const excerptsKey = (symbol: string) => ["excerpts", symbol.trim().toUpperCase()];

/** The stored dossier, or null when none has been built for this symbol. */
export function useDossier(symbol: string | null) {
  return useSWR<Dossier | null, ApiError>(symbol ? dossierKey(symbol) : null, () =>
    orNull(apiGet<Dossier>(`/research/${symbolPath(symbol as string)}`)),
  );
}

/** Page text a live build sent with its dossier, keyed {source_id: {page: text}}. */
export function useExcerpts(symbol: string | null) {
  return useSWR<Excerpts | null>(symbol ? excerptsKey(symbol) : null, null, { fallbackData: null });
}

export function useSource(symbol: string | null, sourceId: string | null, page: number | null) {
  const key = symbol && sourceId && page ? ["source", symbol.toUpperCase(), sourceId, page] : null;
  return useSWR<SourcePage | null, ApiError>(key, () =>
    orNull(
      apiGet<SourcePage>(
        `/research/${symbolPath(symbol as string)}/source/${encodeURIComponent(sourceId as string)}/${page}`,
      ),
    ),
  );
}

/** After a live build: seed the caches so the dossier page renders without refetching. */
export async function primeDossier(dossier: Dossier, excerpts: Excerpts) {
  await mutate(dossierKey(dossier.symbol), dossier, { revalidate: false });
  await mutate(excerptsKey(dossier.symbol), excerpts, { revalidate: false });
  await mutate("research");
}
