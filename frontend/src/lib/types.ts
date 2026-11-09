// Mirrors backend/finn/models.py and the dict-shaped routes in backend/finn/api/main.py.
// tests/types.test.ts checks every captured fixture against the fields the UI reads.

export const CATEGORIES = [
  "results",
  "mna",
  "fund_raise",
  "management_change",
  "litigation",
  "insider_trading",
  "earnings_call",
  "investor_meetings",
  "credit_rating",
  "dividend",
  "bonus_split",
  "capex",
  "press_release",
  "postal_ballot",
  "agm_egm",
  "pledging",
  "unclassified",
] as const;
export type Category = (typeof CATEGORIES)[number];

export type Tier = "critical" | "important" | "routine" | "noise";
export type Floor = "critical" | "important" | "everything";

export interface Filing {
  seq_id: string;
  symbol: string;
  company: string;
  nse_desc: string;
  subject: string;
  nse_summary: string | null;
  pdf_url: string | null;
  filed_at: string;
  has_xbrl: boolean;
}

export interface Classification {
  category: Category;
  subtype: string | null;
  noise: boolean;
  by: "rules" | "llm" | "default";
  confidence: number;
}

export interface ScoredFiling {
  filing: Filing;
  cls: Classification;
  score: number;
  tier: Tier;
  reasons: string[];
}

export interface PersonChange {
  name: string;
  role: string | null;
  change: "appointed" | "resigned" | "retired" | "ceased" | "redesignated" | "other";
  effective: string | null;
  profile: string | null;
  incoming: boolean;
  source_seq_id: string;
}

export interface Fact {
  label: string;
  value: string;
}

export interface Brief {
  one_liner: string;
  facts: Fact[];
  quote: string | null;
  by: "llm" | "nse_summary";
  source_seq_id: string;
}

export interface MetricRow {
  key: string;
  label: string;
  value: number | null;
  qoq_pct: number | null;
  yoy_pct: number | null;
  computed: boolean;
}

export interface MarginRow {
  key: string;
  label: string;
  value_pct: number | null;
  qoq_bps: number | null;
  yoy_bps: number | null;
}

export interface ResultsCard {
  symbol: string;
  period_end: string;
  period_label: string;
  basis: "consolidated" | "standalone";
  format: "indas" | "nbfc" | "bank";
  audited: boolean | null;
  compared_qoq: string | null;
  compared_yoy: string | null;
  metrics: MetricRow[];
  margins: MarginRow[];
  notes: string[];
  sources: string[];
}

export interface Story {
  id: string;
  symbol: string;
  company: string;
  category: Category;
  subtype: string | null;
  score: number;
  tier: Tier;
  headline: ScoredFiling;
  members: ScoredFiling[];
  latest_at: string;
  results: ResultsCard | null;
  people: PersonChange[];
  brief: Brief | null;
}

export interface HiddenFiling {
  symbol: string;
  subject: string;
  filed_at: string;
}

export interface Window {
  start: string;
  end: string;
}

export interface Digest {
  window: Window;
  as_of: string | null;
  latest_filing_at: string | null;
  counts: { shown: number; routine: number; hidden: number; filings: number };
  stories: Story[];
  routine: Partial<Record<Category, Story[]>>;
  hidden: HiddenFiling[];
}

export interface DigestRequest {
  hours?: number;
  start?: string;
  end?: string;
  floor: Floor;
  subscribed: Category[];
}

export interface SymbolOverride {
  volume_multiple: number | null;
  price_move_pct: number | null;
  muted: boolean;
}

export interface Rules {
  volume_multiple: number;
  price_move_pct: number;
  lookback: number;
  categories: Category[];
  overrides: Record<string, SymbolOverride>;
}

export interface Alert {
  kind: "volume" | "price" | "filing";
  symbol: string;
  date: string;
  value: number;
  threshold: number;
  message: string;
  story_id: string | null;
  seq_id: string | null;
}

export interface AlertsResponse {
  as_of: string | null;
  window: Window;
  alerts: Alert[];
}

export interface PortfolioRow {
  symbol: string;
  name: string;
  sector: string;
  size: string;
  date: string | null;
  close: number | null;
  change_pct: number | null;
  vol_ratio: number | null;
  spark: number[];
}

export interface Portfolio {
  as_of: string | null;
  holdings: PortfolioRow[];
}

export interface Health {
  ok: boolean;
  filings_as_of: string | null;
  prices_as_of: string | null;
}

// ---- research ----

export type Status = "kept" | "partly" | "missed" | "pending" | "dropped";

export interface Citation {
  source_id: string; // "FACTS" (page 0) marks a line computed by FINN from filed financials
  page: number;
  quote: string;
}

export interface Promise {
  id: string;
  citation: Citation;
  topic: string;
  kind: "quantitative" | "qualitative";
  metric: string | null;
  target_low: number | null;
  target_high: number | null;
  unit: "%" | "cr" | "x" | "usd_mn" | "usd_bn" | null;
  horizon: string | null;
  made_in: string;
}

export interface Actual {
  value: number;
  unit: string;
  period: string;
  basis: string;
}

export interface LedgerRow {
  promise: Promise;
  status: Status;
  method: "computed" | "judged";
  actual: Actual | null;
  evidence: Citation | null;
  rationale: string;
}

export interface Ledger {
  rows: LedgerRow[];
  counts: Partial<Record<Status, number>>;
  credibility_pct: number | null;
  note: string | null;
}

export interface Point {
  text: string;
  citation: Citation;
}

export interface Source {
  id: string;
  kind: "transcript" | "annual_report";
  title: string;
  quarter: string | null;
  url: string;
}

export interface Flag {
  level: "good" | "watch" | "concern";
  text: string;
}

export interface Trajectory {
  years: string[];
  revenue: (number | null)[];
  operating_profit: (number | null)[];
  margin_pct: (number | null)[];
  pat: (number | null)[];
  revenue_cagr_pct: number | null;
  pat_cagr_pct: number | null;
  margin_change_bps: number | null;
  read: "growing" | "compressing" | "mixed" | "insufficient data";
  lender: boolean;
}

export interface BalanceSheetHealth {
  as_of: string;
  debt_to_equity: number | null;
  cfo_to_pat_3y: number | null;
  fcf_3y_cr: number | null;
  working_capital_days: number | null;
  wc_days_change_3y: number | null;
  roce_pct: number | null;
  flags: Flag[];
}

export interface Dossier {
  symbol: string;
  name: string | null;
  basis: string;
  built_at: string;
  sources: Source[];
  ledger: Ledger | null;
  snapshot: { summary: Point[] } | null;
  trajectory: Trajectory | null;
  health: BalanceSheetHealth | null;
  bull: Point[];
  bear: Point[];
  notes: string[];
  cost: { calls?: number; usd_list_price?: number; [k: string]: unknown };
  build_seconds: number;
  guard: Record<string, unknown>;
}

/** {source_id: {page: text}}, sent with a live build's `done` event. */
export type Excerpts = Record<string, Record<string, string>>;

export interface ResearchListItem {
  symbol: string;
  name: string | null;
  built_at: string;
  counts: {
    sources: number;
    ledger_rows: number;
    bull: number;
    bear: number;
    notes: number;
    ledger: Partial<Record<Status, number>>;
  };
}

export interface SearchHit {
  name: string;
  symbol: string;
  url: string;
}

export interface SourcePage {
  title: string;
  page: number;
  text: string;
}
