import type { MoneyTrustInfo } from "./money-trust";

export type EvidenceValueType =
  | "money"
  | "number"
  | "percent"
  | "count"
  | "days"
  | "boolean"
  | "date"
  | "status"
  | "text"
  | string;
export type EvidenceConfidence =
  | "confirmed"
  | "provisional"
  | "estimated"
  | "opportunity"
  | "test_only"
  | "blocked"
  | string;
export type EvidenceImpactType =
  | "confirmed_loss"
  | "probable_loss"
  | "blocked_cash"
  | "lost_sales_risk"
  | "opportunity"
  | "data_blocker"
  | "system_warning"
  | string;

export interface EvidenceDateRange {
  from?: string | null;
  to?: string | null;
  start?: string | null;
  end?: string | null;
  date_from?: string | null;
  date_to?: string | null;
  [key: string]: unknown;
}

export interface EvidenceInputFact {
  label?: string | null;
  metric_code?: string | null;
  value?: unknown;
  unit?: string | null;
  trust_state?: string | null;
  source?: string | null;
  source_table?: string | null;
  source_endpoint?: string | null;
  source_status?: string | null;
  freshness_status?: string | null;
  freshness?: Record<string, unknown> | null;
  last_synced_at?: string | null;
  loaded_at?: string | null;
  sync_run_id?: string | number | null;
  date_range?: EvidenceDateRange | null;
  filters?: Record<string, unknown> | null;
  row_count?: number | null;
  sample_rows?: Array<Record<string, unknown>>;
  [key: string]: unknown;
}

export interface EvidenceSourceReference {
  source_table?: string | null;
  source_endpoint?: string | null;
  date_range?: EvidenceDateRange | null;
  row_count?: number | null;
  source_status?: string | null;
  freshness_status?: string | null;
  freshness?: Record<string, unknown> | null;
  last_synced_at?: string | null;
  table?: string | null;
  primary_key?: string | number | null;
  id?: string | number | null;
  raw_snapshot_id?: string | number | null;
  wb_endpoint?: string | null;
  loaded_at?: string | null;
  sync_run_id?: string | number | null;
  [key: string]: unknown;
}

export interface EvidenceFixAction {
  label?: string | null;
  href?: string | null;
  endpoint?: string | null;
  method?: string | null;
  screen_path?: string | null;
  source_endpoint?: string | null;
  action_type?: string | null;
  [key: string]: unknown;
}

export interface EvidenceLedger {
  value?: unknown;
  value_type?: EvidenceValueType | null;
  confidence?: EvidenceConfidence | null;
  impact_type?: EvidenceImpactType | null;
  formula_human?: string | null;
  formula_code?: string | null;
  formula_id?: string | null;
  input_facts?: EvidenceInputFact[];
  source_references?: EvidenceSourceReference[];
  trust_notes?: string[];
  missing_data?: string[];
  next_fix_action?: EvidenceFixAction | string | null;
  recheck_rule?: string | null;
  recheck_rule_human?: string | null;
  calculation_warnings?: string[];
  money_trust?: MoneyTrustInfo | null;
  is_synthetic?: boolean | null;
  [key: string]: unknown;
}

export function coerceEvidenceLedger(value: unknown): EvidenceLedger | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const obj = value as EvidenceLedger;
  if (
    "evidence_ledger" in obj &&
    obj.evidence_ledger &&
    typeof obj.evidence_ledger === "object" &&
    !Array.isArray(obj.evidence_ledger)
  ) {
    return coerceEvidenceLedger(obj.evidence_ledger);
  }
  const hasContractShape =
    "formula_human" in obj ||
    "formula_code" in obj ||
    "formula_id" in obj ||
    "input_facts" in obj ||
    "source_references" in obj ||
    "confidence" in obj ||
    "missing_data" in obj;
  return hasContractShape ? obj : null;
}

export function evidenceFrom(...values: unknown[]): EvidenceLedger | null {
  for (const value of values) {
    const ledger = coerceEvidenceLedger(value);
    if (ledger) return ledger;
  }
  return null;
}

export function evidenceNeedsWarning(
  ledger: EvidenceLedger | null | undefined,
): boolean {
  const confidence = String(ledger?.confidence ?? "").toLowerCase();
  return (
    confidence === "estimated" ||
    confidence === "test_only" ||
    confidence === "blocked"
  );
}
