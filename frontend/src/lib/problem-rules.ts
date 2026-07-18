import { api } from "./api";
import type { JsonObject, JsonValue } from "./api";

export type MetricValueType = "money" | "number" | "percent" | "count" | "days" | "boolean" | "text" | string;
export type MetricGrain = "account_day" | "product_day" | "product_period" | "campaign_day" | "warehouse_day" | string;
export type ProblemEntityType = "account" | "product" | "campaign" | "warehouse" | "category" | string;
export type ProblemDefinitionStatus = "draft" | "testing" | "active" | "paused" | "archived" | string;
export type ProblemRuleVersionStatus = "draft" | "testing" | "active" | "paused" | "retired" | "archived" | string;
export type ProblemTrustState = "confirmed" | "provisional" | "estimated" | "opportunity" | "blocked" | "test_only" | string;
export type ProblemImpactType =
  | "confirmed_loss"
  | "probable_loss"
  | "blocked_cash"
  | "lost_sales_risk"
  | "opportunity"
  | "data_blocker"
  | "system_warning"
  | string;
export type ProblemSeverity = "critical" | "high" | "medium" | "low" | string;

export interface MetricCatalogItem {
  id: number;
  metric_code: string;
  title: string;
  description?: string;
  value_type: MetricValueType;
  unit?: string | null;
  grain: MetricGrain;
  entity_type: ProblemEntityType;
  source_module: string;
  formula_json?: JsonObject | null;
  source_tables_json?: string[];
  source_endpoints_json?: string[];
  required_metrics_json?: string[];
  trust_state: ProblemTrustState;
  is_admin_visible: boolean;
  is_deprecated: boolean;
  created_at: string;
  updated_at: string;
}

export interface ProblemDefinition {
  id: number;
  problem_code: string;
  source_module: string;
  category: string;
  entity_type: ProblemEntityType;
  title_template: string;
  description_template: string;
  recommendation_template: string;
  impact_type_default: ProblemImpactType;
  trust_state_default: ProblemTrustState;
  severity_default: ProblemSeverity;
  allowed_actions_json: string[];
  status: ProblemDefinitionStatus;
  created_by_user_id?: number | null;
  created_at: string;
  updated_at: string;
}

export interface ProblemRuleVersion {
  id: number;
  problem_definition_id: number;
  version: number;
  status: ProblemRuleVersionStatus;
  evaluation_grain: MetricGrain;
  lookback_days: number;
  condition_json: JsonValue;
  impact_formula_json: JsonValue;
  severity_formula_json: JsonValue;
  confidence_formula_json: JsonValue;
  dedup_key_template: string;
  recheck_rule_json: JsonObject;
  evidence_template_json: JsonObject;
  created_by_user_id?: number | null;
  published_by_user_id?: number | null;
  published_at?: string | null;
  created_at: string;
  updated_at: string;
}

export interface ProblemRuleAudit {
  id: number;
  object_type: "definition" | "rule_version" | string;
  object_id: number;
  event_type: string;
  old_value_json?: JsonObject | null;
  new_value_json?: JsonObject | null;
  comment?: string | null;
  actor_user_id?: number | null;
  created_at: string;
}

export interface ProblemDefinitionDetail extends ProblemDefinition {
  versions: ProblemRuleVersion[];
  audit: ProblemRuleAudit[];
}

export interface ProblemDefinitionCreatePayload {
  problem_code: string;
  source_module: string;
  category: string;
  entity_type: ProblemEntityType;
  title_template: string;
  description_template: string;
  recommendation_template: string;
  impact_type_default: ProblemImpactType;
  trust_state_default: ProblemTrustState;
  severity_default: ProblemSeverity;
  allowed_actions_json: string[];
}

export type ProblemDefinitionUpdatePayload = Partial<Omit<ProblemDefinitionCreatePayload, "problem_code">> & {
  status?: ProblemDefinitionStatus;
};

export interface ProblemRuleVersionCreatePayload {
  evaluation_grain: MetricGrain;
  lookback_days: number;
  condition_json: JsonValue;
  impact_formula_json: JsonValue;
  severity_formula_json: JsonValue;
  confidence_formula_json: JsonValue;
  dedup_key_template: string;
  recheck_rule_json: JsonObject;
  evidence_template_json: JsonObject;
}

export interface RuleValidationDiagnostic {
  valid: boolean;
  error?: string | null;
  missing_metrics: string[];
  warnings: string[];
}

export interface RuleValidationResponse {
  valid: boolean;
  formula_results: Record<string, RuleValidationDiagnostic>;
  required_metrics: string[];
  warnings: string[];
}

export interface RuleBacktestRequest {
  account_id: number;
  date_from: string;
  date_to: string;
  nm_id?: number | null;
  sample_limit?: number;
}

export interface RuleBacktestResponse {
  rule_version_id: number;
  account_id: number;
  date_from: string;
  date_to: string;
  matched_count: number;
  evaluated_count: number;
  sample_issues: JsonObject[];
  total_impact_amount?: number | string | null;
  warnings: string[];
  missing_metric_stats: Record<string, number>;
  test_run_id?: number | null;
}

export function fetchProblemRuleMetrics() {
  return api<MetricCatalogItem[]>("/admin/problem-rules/metrics");
}

export function fetchProblemDefinitions() {
  return api<ProblemDefinition[]>("/admin/problem-rules/definitions");
}

export function createProblemDefinition(payload: ProblemDefinitionCreatePayload) {
  return api<ProblemDefinition>("/admin/problem-rules/definitions", { method: "POST", body: payload });
}

export function fetchProblemDefinition(id: number) {
  return api<ProblemDefinitionDetail>(`/admin/problem-rules/definitions/${id}`);
}

export function updateProblemDefinition(id: number, payload: ProblemDefinitionUpdatePayload) {
  return api<ProblemDefinition>(`/admin/problem-rules/definitions/${id}`, { method: "PATCH", body: payload });
}

export function createProblemRuleVersion(definitionId: number, payload: ProblemRuleVersionCreatePayload) {
  return api<ProblemRuleVersion>(`/admin/problem-rules/definitions/${definitionId}/versions`, { method: "POST", body: payload });
}

export function validateProblemRuleVersion(versionId: number, payload?: Partial<ProblemRuleVersionCreatePayload>) {
  return api<RuleValidationResponse>(`/admin/problem-rules/versions/${versionId}/validate`, {
    method: "POST",
    body: payload ?? {},
  });
}

export function backtestProblemRuleVersion(versionId: number, payload: RuleBacktestRequest) {
  return api<RuleBacktestResponse>(`/admin/problem-rules/versions/${versionId}/backtest`, {
    method: "POST",
    body: payload,
  });
}

export function publishProblemRuleVersion(versionId: number, payload: { override?: boolean; override_reason?: string | null }) {
  return api<ProblemRuleVersion>(`/admin/problem-rules/versions/${versionId}/publish`, {
    method: "POST",
    body: payload,
  });
}

export function pauseProblemRuleVersion(versionId: number) {
  return api<ProblemRuleVersion>(`/admin/problem-rules/versions/${versionId}/pause`, { method: "POST" });
}

export function archiveProblemRuleVersion(versionId: number) {
  return api<ProblemRuleVersion>(`/admin/problem-rules/versions/${versionId}/archive`, { method: "POST" });
}
