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

export function useDigest(req: DigestRequest | null, { keepPrevious = true }: { keepPrevious?: boolean } = {}) {
  return useSWR<Digest, ApiError>(
    req ? ["digest", JSON.stringify(req)] : null,
    () => apiPost<Digest>("/digest", req),
    // a window change keeps the old stories up until the new ones land; a count that must
    // match its request (the quiet-day teaser) passes keepPrevious: false
    { keepPreviousData: keepPrevious },
  );
}

export function usePortfolio() {
  return useSWR<Portfolio, ApiError>("portfolio", () => apiGet<Portfolio>("/portfolio"));
}

export function useAlerts(rules: Rules | null) {
  return useSWR<AlertsResponse, ApiError>(
    rules ? ["alerts", JSON.stringify(rules)] : null,
    () => apiPost<AlertsResponse>("/alerts", rules),
    { keepPreviousData: true },
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

// Dossiers this tab built live. On Vercel a build is saved to one instance's /tmp, so a
// later GET can land on another instance and 404; the dossier the user just watched being
// built must not vanish because of that.
const builtHere = new Map<string, Dossier>();

/** The stored dossier (or the one built live in this tab), or null when there is neither. */
export function useDossier(symbol: string | null) {
  return useSWR<Dossier | null, ApiError>(
    symbol ? dossierKey(symbol) : null,
    async () => {
      const stored = await orNull(apiGet<Dossier>(`/research/${symbolPath(symbol as string)}`));
      return stored ?? builtHere.get((symbol as string).trim().toUpperCase()) ?? null;
    },
    { revalidateOnFocus: false },
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
  builtHere.set(dossier.symbol.trim().toUpperCase(), dossier);
  await mutate(dossierKey(dossier.symbol), dossier, { revalidate: false });
  await mutate(excerptsKey(dossier.symbol), excerpts, { revalidate: false });
  await mutate("research");
}
