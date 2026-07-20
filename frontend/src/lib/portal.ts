// @ts-nocheck
// Thin typed client for /portal/* (Seller Portal AI Operator).
// All requests pass account_id from the active account context.

import { api, apiList } from "./api";
import type { JsonObject, JsonValue, Paginated } from "./api";
import { API_ENDPOINTS } from "./endpoints";
import type { EvidenceLedger } from "./evidence";
import type { MoneyTrustInfo } from "./money-trust";
import { proxyWbImageUrl as resolveWbImageUrl } from "./wb-images";
export type { PortalModuleHealth } from "./modules-health";
export {
  fetchModulesHealth,
  useModuleStatus,
  useModuleVisible,
  useModulesHealth,
} from "./modules-health";

// ─── Loose types — backend shape may evolve ───────────────────────────
export interface ReputationRuntimeFields {
  runtime_mode?: "local" | "external_adapter" | "disabled" | string;
  dangerous_actions_enabled?: boolean;
  publish_enabled?: boolean;
  auto_publish_enabled?: boolean;
  chat_send_enabled?: boolean;
  reviews_sync_status?: string;
  questions_sync_status?: string;
  chats_sync_status?: string;
  backlog_status?: string;
  automation_status?: string;
  last_error?: string | null;
}

export type ReputationSummary = ReputationRuntimeFields &
  Record<string, unknown>;
export type ReputationSettings = ReputationRuntimeFields &
  Record<string, unknown>;
export type ReputationInboxResponse =
  | {
      items?: Array<Record<string, unknown>>;
      total?: number;
      [k: string]: unknown;
    }
  | Array<Record<string, unknown>>;
export type ReputationAnalytics = Record<string, unknown>;

export interface PortalDoctor {
  headline?: string | null;
  business_status?: string | null;
  money_at_risk_amount?: number | null;
  top_sections?: unknown[];
  today_plan_summary?: unknown;
  today_plan?: unknown[];
  unavailable_sources?: unknown[];
  [k: string]: unknown;
}

export type PortalActionSourceModule =
  | "finance"
  | "data_quality"
  | "costs"
  | "checker"
  | "stockops"
  | "grouping"
  | "grouping_beta"
  | "reputation"
  | "claims"
  | "photo"
  | "experiments"
  | "problem_engine"
  | "manual"
  | string;

export type PortalActionPriority = "P0" | "P1" | "P2" | "P3" | "P4" | string;
export type PortalActionSeverity =
  | "critical"
  | "high"
  | "medium"
  | "low"
  | string;
export type PortalActionStatus =
  | "new"
  | "acknowledged"
  | "in_progress"
  | "done"
  | "postponed"
  | "ignored"
  | "blocked"
  | "resolved"
  | "dismissed"
  | "reopened"
  | string;
export type PortalActionEvidenceState =
  | "full_evidence"
  | "partial_evidence"
  | "missing_evidence"
  | "read_only_signal"
  | string;
export type PortalActionSourceStatus =
  | "fresh"
  | "stale"
  | "missing"
  | "not_configured"
  | string;
export interface PortalActionDataFreshness {
  required_sources?: string[];
  source_status?: PortalActionSourceStatus;
  last_synced_at?: string | null;
  blocking_sources?: string[];
  freshness_notes?: string[];
  [key: string]: unknown;
}
export type PortalActionSolveStepStatus =
  | "ready"
  | "available"
  | "blocked"
  | "waiting_for_data"
  | "done"
  | string;
export interface PortalActionSolveMapStep {
  step_id?: string;
  order?: number;
  title?: string;
  description?: string;
  status?: PortalActionSolveStepStatus;
  action_code?: string | null;
  target_href?: string | null;
  required_metrics?: string[];
  blocking_reason?: string | null;
  completion_signal?: string | null;
  [key: string]: unknown;
}
export interface PortalActionSolveMap {
  title?: string;
  summary?: string;
  steps?: PortalActionSolveMapStep[];
  [key: string]: unknown;
}
export type PortalActionReviewStatus =
  | "new"
  | "in_progress"
  | "review"
  | "closed"
  | "dismissed"
  | string;

export interface PortalAction {
  id: string;
  external_id?: string | null;
  action_id?: number | null;
  source: string;
  source_module: PortalActionSourceModule;
  source_id?: string | null;
  account_id?: number | null;
  action_type: string;
  detector_code?: string | null;
  title: string;
  priority: PortalActionPriority;
  severity: PortalActionSeverity;
  status: PortalActionStatus;
  reason?: string;
  next_step?: string;
  expected_effect_amount?: number | null;
  expected_impact_amount?: number | null;
  priority_score?: number | null;
  confidence?: "high" | "medium" | "low" | string;
  nm_id?: number | null;
  sku_id?: number | null;
  created_at?: string | null;
  assigned_to_user_id?: number | null;
  deadline_at?: string | null;
  review_status?: PortalActionReviewStatus;
  last_comment?: string | null;
  last_status_changed_at?: string | null;
  last_actor_user_id?: number | null;
  status_reason?: string | null;
  is_overdue?: boolean;
  due_in_hours?: number | null;
  sla_state?: "ok" | "due_soon" | "overdue" | "no_deadline" | string;
  closed_at?: string | null;
  dismissed_at?: string | null;
  linked_entity?: JsonObject & {
    sku_id?: number;
    nm_id?: number;
    vendor_code?: string;
  };
  payload?: JsonObject & {
    code?: string;
    beta?: boolean;
    vendor_code?: string;
    problem_code?: string;
    detector_code?: string;
    issue_code?: string;
    checker_problem_bridge?: boolean;
    problem_ux_contract?: boolean;
    content_quality_signal?: boolean;
    bridge_kind?: string;
    allowed_actions?: JsonValue;
    evidence_ledger?: JsonValue;
    price_safety?: JsonValue;
    data_freshness?: JsonValue;
    solve_map?: JsonValue;
  };
  raw?: JsonObject & {
    code?: string;
    evidence?: JsonValue;
    data_freshness?: JsonValue;
    solve_map?: JsonValue;
  };
  evidence_ledger?: EvidenceLedger | null;
  evidence_state?: PortalActionEvidenceState | null;
  data_freshness?: PortalActionDataFreshness | null;
  solve_map?: PortalActionSolveMap | null;
  allowed_actions?: string[];
  money_trust?: MoneyTrustInfo | null;
  source_references?: JsonObject[];
  recheck_rule?: string | null;
  impact_type?: string | null;
  trust_state?: string | null;
  source_sync_state?:
    | "source_updated"
    | "shadow_only"
    | "shadow_updated"
    | "unknown"
    | string;
  can_execute?: boolean;
  can_update_status?: boolean;
  can_update?: boolean;
  can_update_reason?: string | null;
  guided_fix?: JsonObject & {
    route_key?: string;
    label?: string;
    href?: string;
  };
}

export interface PortalAssignableUser {
  id: number;
  email: string;
  full_name: string;
  display_name: string;
  role: string;
  is_active: boolean;
  is_superuser: boolean;
}

export interface PortalManualActionProduct {
  nm_id: number;
  sku_id?: number | null;
  title?: string | null;
  vendor_code?: string | null;
  photo_url?: string | null;
}

export interface PortalManualActionCreatePayload {
  account_id: number;
  title: string;
  description?: string | null;
  task_kind?: string;
  priority?: "P0" | "P1" | "P2" | "P3" | "P4";
  assigned_to_user_id: number;
  deadline_at: string;
  products: PortalManualActionProduct[];
}

export type AllowedActionCode =
  | "create_task"
  | "assign"
  | "recheck"
  | "trigger_recheck"
  | "dismiss"
  | "open_data_fix"
  | "data_fix"
  | "open_price_review"
  | "review_price"
  | "pricing_review"
  | "open_promo_planner"
  | "promo_planner"
  | "review_promo"
  | "safe_promo"
  | "reduce_promo"
  | "bundle"
  | "run_checker"
  | "check_card_quality"
  | "review_content"
  | "upload_cost"
  | "review_cost"
  | "map_sku"
  | "review_ads"
  | "pause_ads"
  | "lower_ads"
  | "review_bids"
  | "plan_supply"
  | string;

export interface DynamicProblemAction extends PortalAction {
  source_module: "problem_engine";
  problem_instance_id?: number | null;
  problem_code?: string | null;
  impact_type?: string | null;
  trust_state?: string | null;
  allowed_actions?: AllowedActionCode[];
}

export type ProblemResultStatus =
  | "pending_data"
  | "improved"
  | "worse"
  | "neutral"
  | "not_enough_data";

export interface ProblemStatusHistoryItem {
  event_type?: string | null;
  old_status?: string | null;
  new_status?: string | null;
  status?: string | null;
  comment?: string | null;
  created_at?: string | null;
  created_by?: number | null;
}

export interface ProblemResultEvent {
  id: string;
  account_id: number;
  action_id?: number | null;
  problem_instance_id?: number | null;
  problem_code?: string | null;
  source_module: string;
  source_id?: string | null;
  external_id?: string | null;
  nm_id?: number | null;
  sku_id?: number | null;
  event_type: string;
  outcome?:
    | "improved"
    | "worse"
    | "neutral"
    | "pending"
    | "blocked"
    | "not_enough_data"
    | string;
  comparison?: JsonObject;
  product_identity?: JsonObject;
  before_snapshot?: JsonObject;
  after_snapshot?: JsonObject;
  snapshot_day?: number | null;
  message?: string | null;
  payload?: JsonObject;
  confidence?: string | null;
  calculation_note?: string | null;
  created_by?: number | null;
  created_at?: string | null;
  warnings?: string[];
}

export interface ProblemResultSummary {
  status: ProblemResultStatus;
  before_snapshot: JsonObject;
  current_snapshot: JsonObject;
  after_snapshot: JsonObject;
  comparison: JsonObject | string | null;
  metrics: JsonObject;
  finance_windows: JsonObject;
  status_history: ProblemStatusHistoryItem[];
  calculation_note?: string | null;
  disclaimer?: string | null;
  confidence?: string | null;
  events: ProblemResultEvent[];
}

export type PortalResultEventsPage = Paginated<ProblemResultEvent> & {
  status?: string;
  summary?: JsonObject;
  by_module?: JsonObject;
  by_outcome?: JsonObject;
  recent_events?: ProblemResultEvent[];
  pending_followups?: JsonObject[];
  finance_windows?: JsonObject;
  disclaimer?: string | null;
  unavailable_sources?: string[];
};

export interface PortalProductRow {
  nm_id: number;
  sku_id?: number | null;
  title?: string | null;
  vendor_code?: string | null;
  article?: string | null;
  name?: string | null;
  photo?: string | null;
  photo_url?: string | null;
  thumbnail?: string | null;
  thumbnail_url?: string | null;
  main_photo_url?: string | null;
  image_url?: string | null;
  brand?: string | null;
  subject_name?: string | null;
  revenue?: number | null;
  for_pay?: number | null;
  estimated_profit?: number | null;
  profit?: number | null;
  margin?: number | null;
  ads_spend?: number | null;
  stock_qty?: number | null;
  cost_state?: string;
  stock_state?: string;
  card_quality_state?: string;
  card_quality_score?: number | null;
  card_quality_issue_count?: number;
  card_quality_photo_count?: number | null;
  card_quality_analyzed_at?: string | null;
  reputation_state?: string;
  cases_state?: string;
  stock_summary?: JsonObject | null;
  data_trust_state?: string | null;
  open_actions_count?: number;
  top_action?: PortalAction | null;
  status?: string;
  trust_state?: string;
  priority_score?: number | null;
  money?: JsonObject | null;
  stock?: JsonObject | null;
  ads?: JsonObject | null;
  next_action?: PortalAction | null;
  raw?: JsonObject;
  business_status?: string | null;
  money_at_risk_amount?: number | null;
  priority?: string | null;
  next_action_title?: string | null;
  evidence_ledger?: EvidenceLedger | null;
  money_trust?: MoneyTrustInfo | null;
}

export type PortalActionsPage = Paginated<PortalAction> & {
  unavailable_sources?: string[];
};

export type PortalProductsPage = Paginated<PortalProductRow> & {
  summary?: JsonObject;
  unavailable_sources?: string[];
};

export interface CardQualityProductRow {
  account_id: number;
  nm_id: number;
  title?: string | null;
  vendor_code?: string | null;
  brand?: string | null;
  subject_name?: string | null;
  thumbnail_url?: string | null;
  photos_count?: number | null;
  video_count?: number | null;
  source_updated_at?: string | null;
  updated_at?: string | null;
  score?: number | null;
  status?: string | null;
  analyzed_at?: string | null;
  source_revision?: string | null;
  issue_count?: number;
  actionable_issue_count?: number;
  critical_issue_count?: number;
  warning_issue_count?: number;
  ai_issue_count?: number;
  no_solution_ai_issue_count?: number;
  top_issue_title?: string | null;
  top_issue_category?: string | null;
  top_issue_severity?: string | null;
  top_issue_source?: string | null;
  top_issue_recommended_fix?: string | null;
  analysis_available?: boolean;
}

export type CardQualityProductsPage = Paginated<CardQualityProductRow> & {
  summary?: JsonObject;
};

export interface CardQualityFixedFileStatus {
  has_fixed_file: boolean;
  total: number;
  total_cards?: number;
  total_brands?: number;
  total_subjects?: number;
  total_characteristics?: number;
  last_updated_at?: string | null;
}

export interface CardQualityFixedFileEntry {
  id: number;
  account_id: number;
  nm_id: number;
  brand?: string | null;
  subject_name?: string | null;
  char_name: string;
  fixed_value: string;
  created_by_user_id?: number | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export type CardQualityFixedFileEntriesPage =
  Paginated<CardQualityFixedFileEntry> & {
    status?: "ok" | string;
    summary?: CardQualityFixedFileStatus | null;
  };

export type CardQualityFixedFileEntryPayload = Partial<
  Pick<
    CardQualityFixedFileEntry,
    "nm_id" | "brand" | "subject_name" | "char_name" | "fixed_value"
  >
>;

export interface PortalOverviewRead {
  account?: JsonObject | null;
  date_range?: JsonObject;
  date_from?: string | null;
  date_to?: string | null;
  money_summary?: JsonObject | null;
  data_trust?: JsonObject | null;
  data_blockers?: JsonObject | null;
  cost_status?: JsonObject;
  doctor_summary?: JsonObject;
  top_problems?: JsonObject[];
  operator_actions?: JsonObject[];
  product_risks?: JsonObject[];
  reputation?: JsonObject;
  claims?: JsonObject;
  top_actions?: PortalAction[];
  top_products?: PortalProductRow[];
  module_health: JsonObject;
  unavailable_sources?: string[];
}

export interface PortalDataBlock {
  status?: string;
  data?: JsonObject | unknown[] | null;
  message?: string | null;
  evidence_ledger?: EvidenceLedger | null;
}

export interface PortalProduct360Read {
  nm_id: number;
  overview_diagnosis?: PortalDataBlock;
  identity?: PortalDataBlock;
  money?: PortalDataBlock;
  costs?: PortalDataBlock;
  ads?: PortalDataBlock;
  stock?: PortalDataBlock;
  pricing?: PortalDataBlock;
  data_quality?: PortalDataBlock;
  quality?: PortalDataBlock;
  card_quality?: PortalDataBlock;
  reputation?: PortalDataBlock;
  claims?: PortalDataBlock;
  photo_studio?: PortalDataBlock;
  experiments?: PortalDataBlock;
  grouping?: PortalDataBlock;
  grouping_beta?: PortalDataBlock;
  business_issues?: PortalDataBlock;
  actions?: PortalAction[];
  history?: PortalDataBlock;
  result_history?: PortalDataBlock;
  next_best_action?: PortalAction | null;
  module_health?: JsonObject | null;
  stock_summary?: JsonObject;
  ads_summary?: JsonObject;
  data_issues?: JsonObject[];
  finance?: JsonObject;
  unavailable_sources?: string[];
  raw?: JsonObject;
  evidence_ledger?: Record<string, EvidenceLedger>;
}

export interface PortalDataReadinessRead {
  account_id: number;
  operational_status: JsonObject;
  final_profit_status: JsonObject;
  cost_status: JsonObject;
  sources?: JsonObject[];
  blockers?: Array<
    JsonObject & {
      evidence_ledger?: EvidenceLedger | null;
      money_trust?: MoneyTrustInfo | null;
    }
  >;
  warnings?: string[];
  sync_status: JsonObject;
  next_steps?: JsonObject[];
  evidence_ledger?: Record<string, EvidenceLedger>;
}

export interface CardQualityIssueRead {
  id: number;
  account_id: number;
  nm_id: number;
  snapshot_id?: number | null;
  issue_code: string;
  category: string;
  severity: string;
  title: string;
  business_explanation?: string | null;
  recommended_fix?: string | null;
  field_name?: string | null;
  current_value_json?: unknown;
  expected_value_json?: unknown;
  suggested_value?: string | null;
  alternatives_json?: unknown[];
  status: string;
  fingerprint: string;
  suggestion_kind: string;
  has_confirmed_suggestion: boolean;
  is_user_actionable: boolean;
  evidence_ledger?: EvidenceLedger | null;
  money_trust?: MoneyTrustInfo | null;
  [k: string]: unknown;
}

export interface CardQualityIssueApplyPreview {
  issue_id: number;
  nm_id: number;
  field_path?: string | null;
  current_value?: unknown;
  fixed_value?: unknown;
  diff?: JsonObject;
  can_apply_to_wb?: boolean;
  requires_confirm?: boolean;
  blocked_reason?: string | null;
  wb_write_status?: "preview_ready" | "blocked" | string;
  audit?: JsonObject;
}

export interface CardQualityIssueFixResponse {
  status:
    | "fixed_local"
    | "confirmation_required"
    | "submitted_to_wb"
    | "applied_to_wb"
    | "blocked"
    | "wb_submit_failed"
    | string;
  issue: CardQualityIssueRead;
  preview?: CardQualityIssueApplyPreview | null;
  apply_result?: JsonObject | null;
  wb_write_status?:
    | "not_requested"
    | "confirmation_required"
    | "submitted_waiting_validation"
    | "blocked"
    | "failed"
    | string;
  message?: string | null;
}

export type CardQualityIssuesPage = Paginated<CardQualityIssueRead> & {
  status?: "ok" | string;
  summary?: JsonObject;
  evidence_ledger?: Record<string, EvidenceLedger>;
};

// ─── Fetchers ─────────────────────────────────────────────────────────
// All portal fetchers REQUIRE account_id; callers must gate with
// `enabled: !!activeAccountId` in React Query. To make accidental misuse
// loud, the fetchers throw early instead of issuing a request without it.
function requireAcc(accountId?: number | null): { account_id: number } {
  if (accountId == null) {
    throw new Error(
      "portal: account_id is required (no active account selected)",
    );
  }
  return { account_id: accountId };
}

const ngAcc = (accountId?: number | null) =>
  accountId != null ? { account_id: accountId } : {};

type DateRange = { dateFrom?: string; dateTo?: string };
const dateQ = (r?: DateRange) =>
  r
    ? {
        ...(r.dateFrom ? { date_from: r.dateFrom } : {}),
        ...(r.dateTo ? { date_to: r.dateTo } : {}),
      }
    : {};

export const fetchDoctor = (
  accountId: number | null | undefined,
  range?: DateRange,
) =>
  api<PortalDoctor>(API_ENDPOINTS.portal.doctor, {
    query: { ...requireAcc(accountId), ...dateQ(range) },
  });

export const fetchPortalActions = (
  accountId: number | null | undefined,
  extra?: Record<string, any>,
  range?: DateRange,
) =>
  api<PortalActionsPage>(API_ENDPOINTS.portal.actions, {
    query: {
      ...requireAcc(accountId),
      ...dateQ(range),
      include_payload: false,
      ...(extra ?? {}),
    },
  });

export async function fetchAllPortalActions(
  accountId: number | null | undefined,
  extra?: Record<string, any>,
  range?: DateRange,
): Promise<PortalActionsPage> {
  const pageSize = 200;
  const baseExtra = { ...(extra ?? {}) };
  delete baseExtra.offset;
  const first = await fetchPortalActions(
    accountId,
    { ...baseExtra, limit: pageSize, offset: 0 },
    range,
  );
  const total = Number(first.total ?? first.items?.length ?? 0);
  const firstItems = Array.isArray(first.items) ? first.items : [];
  if (total <= firstItems.length) {
    return {
      ...first,
      total,
      limit: firstItems.length,
      offset: 0,
      items: firstItems,
    };
  }

  const offsets: number[] = [];
  for (let offset = pageSize; offset < total; offset += pageSize) {
    offsets.push(offset);
  }
  const pages = await Promise.all(
    offsets.map((offset) =>
      fetchPortalActions(
        accountId,
        { ...baseExtra, limit: pageSize, offset },
        range,
      ),
    ),
  );
  const items = [
    ...firstItems,
    ...pages.flatMap((page) => (Array.isArray(page.items) ? page.items : [])),
  ];
  const unavailable = new Set<string>();
  for (const page of [first, ...pages]) {
    for (const source of page.unavailable_sources ?? [])
      unavailable.add(String(source));
  }
  return {
    ...first,
    total: Math.max(total, items.length),
    limit: items.length,
    offset: 0,
    items,
    unavailable_sources: [...unavailable],
  };
}

export const analyzeProductCardQuality = (
  nmId: number | string,
  accountId: number | null | undefined,
  payload: { force?: boolean } = {},
) =>
  api<any>(API_ENDPOINTS.portal.cardQualityProductAnalyze(nmId), {
    method: "POST",
    body: { ...requireAcc(accountId), ...payload },
  });

export const analyzeAccountCardQuality = (
  accountId: number | null | undefined,
  payload: { force?: boolean; limit?: number } = {},
) =>
  api<any>(API_ENDPOINTS.portal.cardQualityAnalyze, {
    method: "POST",
    body: { ...requireAcc(accountId), ...payload },
  });

export const recheckProductCardQuality = (
  nmId: number | string,
  accountId: number | null | undefined,
  payload: { force?: boolean } = {},
) =>
  api<any>(API_ENDPOINTS.portal.cardQualityProductRecheck(nmId), {
    method: "POST",
    query: requireAcc(accountId),
    body: { ...payload },
  });

export const fetchProductQuality = (
  nmId: number | string,
  accountId: number | null | undefined,
) =>
  api<any>(API_ENDPOINTS.portal.productQuality(nmId), {
    query: requireAcc(accountId),
  });

export const updateCardQualityIssueStatus = (
  issueId: number | string,
  accountId: number | null | undefined,
  payload: {
    status:
      | "new"
      | "in_progress"
      | "done"
      | "postponed"
      | "ignored"
      | "blocked"
      | "resolved";
    reason?: string | null;
    fixed_value?: string | null;
    postponed_until?: string | null;
  },
) =>
  api<any>(API_ENDPOINTS.portal.cardQualityIssueStatus(issueId), {
    method: "PATCH",
    query: requireAcc(accountId),
    body: payload,
  });

export const previewCardQualityIssueApply = (
  issueId: number | string,
  accountId: number | null | undefined,
  payload: { fixed_value?: string | null } = {},
) =>
  api<CardQualityIssueApplyPreview>(
    API_ENDPOINTS.portal.cardQualityIssuePreview(issueId),
    {
      method: "POST",
      query: requireAcc(accountId),
      body: payload,
    },
  );

export const fixCardQualityIssue = (
  issueId: number | string,
  accountId: number | null | undefined,
  payload: {
    fixed_value?: string | null;
    apply_to_wb?: boolean;
    confirm?: boolean;
    reason?: string | null;
  },
) =>
  api<CardQualityIssueFixResponse>(
    API_ENDPOINTS.portal.cardQualityIssueFix(issueId),
    {
      method: "POST",
      query: requireAcc(accountId),
      body: payload,
    },
  );

export const acceptCardQualityIssueLocal = (
  issueId: number | string,
  accountId: number | null | undefined,
  payload: { fixed_value?: string | null; reason?: string | null } = {},
) =>
  api<CardQualityIssueFixResponse>(
    API_ENDPOINTS.portal.cardQualityIssueAcceptLocal(issueId),
    {
      method: "POST",
      query: requireAcc(accountId),
      body: payload,
    },
  );

export const markCardQualityIssueFixed = (
  issueId: number | string,
  accountId: number | null | undefined,
  payload: { fixed_value?: string | null; reason?: string | null } = {},
) =>
  api<CardQualityIssueRead>(
    API_ENDPOINTS.portal.cardQualityIssueMarkFixed(issueId),
    {
      method: "POST",
      query: requireAcc(accountId),
      body: payload,
    },
  );

export const saveCardQualityIssueDraft = (
  issueId: number | string,
  accountId: number | null | undefined,
  payload: { fixed_value?: string | null; reason?: string | null } = {},
) =>
  api<CardQualityIssueRead>(
    API_ENDPOINTS.portal.cardQualityIssueDraft(issueId),
    {
      method: "POST",
      query: requireAcc(accountId),
      body: payload,
    },
  );

export const applyCardQualityIssueWb = (
  issueId: number | string,
  accountId: number | null | undefined,
  payload: {
    fixed_value?: string | null;
    confirm?: boolean;
    reason?: string | null;
  },
) =>
  api<CardQualityIssueFixResponse>(
    API_ENDPOINTS.portal.cardQualityIssueApplyWb(issueId),
    {
      method: "POST",
      query: requireAcc(accountId),
      body: payload,
    },
  );

export const recheckCardQualityIssue = (
  issueId: number | string,
  accountId: number | null | undefined,
) =>
  api<CardQualityIssueRead>(
    API_ENDPOINTS.portal.cardQualityIssueRecheck(issueId),
    {
      method: "POST",
      query: requireAcc(accountId),
      body: {},
    },
  );

export const fetchCardQualityIssuesGrouped = (
  accountId: number | null | undefined,
  payload: {
    bucket?: "actionable" | "human_check" | "media" | "all";
    limit?: number;
  } = {},
) =>
  api<any>(API_ENDPOINTS.portal.cardQualityIssuesGrouped, {
    query: {
      ...requireAcc(accountId),
      bucket: payload.bucket ?? "actionable",
      limit: payload.limit ?? 200,
    },
  });

export const fetchNextCardQualityIssue = (
  accountId: number | null | undefined,
  payload: {
    after?: number | string | null;
    nm_id?: number | string | null;
    severity?: string | null;
    bucket?: "actionable" | "human_check" | "media" | "all";
  } = {},
) =>
  api<any | null>(API_ENDPOINTS.portal.cardQualityIssueQueueNext, {
    query: {
      ...requireAcc(accountId),
      ...(payload.after != null ? { after: payload.after } : {}),
      ...(payload.nm_id != null ? { nm_id: payload.nm_id } : {}),
      ...(payload.severity ? { severity: payload.severity } : {}),
      bucket: payload.bucket ?? "actionable",
    },
  });

export const fetchCardQualityQueueProgress = (
  accountId: number | null | undefined,
  payload: {
    severity?: string | null;
    bucket?: "actionable" | "human_check" | "media" | "all";
  } = {},
) =>
  api<any>(API_ENDPOINTS.portal.cardQualityIssueQueueProgress, {
    query: {
      ...requireAcc(accountId),
      ...(payload.severity ? { severity: payload.severity } : {}),
      bucket: payload.bucket ?? "actionable",
    },
  });

export const fetchCardQualityFixedFileStatus = (
  accountId: number | null | undefined,
) =>
  api<CardQualityFixedFileStatus>(
    API_ENDPOINTS.portal.cardQualityFixedFileStatus,
    {
      query: requireAcc(accountId),
    },
  );

export const fetchCardQualityFixedFileEntries = (
  accountId: number | null | undefined,
  extra?: {
    limit?: number;
    offset?: number;
    search?: string;
    nm_id?: number | string | null;
    brand?: string;
    subject_name?: string;
    char_name?: string;
    sort_by?: string;
    sort_dir?: "asc" | "desc" | string;
  },
) =>
  api<CardQualityFixedFileEntriesPage>(
    API_ENDPOINTS.portal.cardQualityFixedFile,
    {
      query: { ...requireAcc(accountId), ...(extra ?? {}) },
    },
  );

export const uploadCardQualityFixedFile = (
  accountId: number | null | undefined,
  file: File,
  replaceAll = false,
) => {
  const formData = new FormData();
  formData.append("file", file);
  return api<any>(API_ENDPOINTS.portal.cardQualityFixedFileUpload, {
    method: "POST",
    query: { ...requireAcc(accountId), replace_all: replaceAll },
    formData,
  });
};

export const createCardQualityFixedFileEntry = (
  accountId: number | null | undefined,
  payload: CardQualityFixedFileEntryPayload,
) =>
  api<CardQualityFixedFileEntry>(API_ENDPOINTS.portal.cardQualityFixedFile, {
    method: "POST",
    query: requireAcc(accountId),
    body: payload,
  });

export const updateCardQualityFixedFileEntry = (
  accountId: number | null | undefined,
  entryId: number | string,
  payload: CardQualityFixedFileEntryPayload,
) =>
  api<CardQualityFixedFileEntry>(
    API_ENDPOINTS.portal.cardQualityFixedFileEntry(entryId),
    {
      method: "PATCH",
      query: requireAcc(accountId),
      body: payload,
    },
  );

export const deleteCardQualityFixedFileEntry = (
  accountId: number | null | undefined,
  entryId: number | string,
) =>
  api<any>(API_ENDPOINTS.portal.cardQualityFixedFileEntry(entryId), {
    method: "DELETE",
    query: requireAcc(accountId),
  });

export const clearCardQualityFixedFile = (
  accountId: number | null | undefined,
) =>
  api<any>(API_ENDPOINTS.portal.cardQualityFixedFile, {
    method: "DELETE",
    query: requireAcc(accountId),
  });

export const downloadCardQualityFixedFile = async (
  accountId: number | null | undefined,
  extra?: {
    search?: string;
    nm_id?: number | string | null;
    brand?: string;
    subject_name?: string;
    char_name?: string;
    sort_by?: string;
    sort_dir?: "asc" | "desc" | string;
  },
) => {
  const response = await api<Response>(
    API_ENDPOINTS.portal.cardQualityFixedFileExport,
    {
      raw: true,
      query: { ...requireAcc(accountId), ...(extra ?? {}) },
    },
  );
  const blob = await response.blob();
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "card-quality-fixed-file.xlsx";
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.URL.revokeObjectURL(url);
};

export const fetchCardQualityProducts = (
  accountId: number | null | undefined,
  extra?: Record<string, any>,
) =>
  api<CardQualityProductsPage>(API_ENDPOINTS.portal.cardQualityProducts, {
    query: { ...requireAcc(accountId), ...(extra ?? {}) },
  }).then(normalizeCardQualityProducts);

function normalizeCardQualityProducts(
  res: CardQualityProductsPage,
): CardQualityProductsPage {
  return {
    ...res,
    items: (res.items ?? []).map((row) => ({
      ...row,
      thumbnail_url: proxyWbImageUrl(row.thumbnail_url ?? null),
    })),
  };
}

export const fetchPortalProducts = (
  accountId: number | null | undefined,
  extra?: Record<string, any>,
  range?: DateRange,
) =>
  api<PortalProductsPage>(API_ENDPOINTS.portal.products, {
    query: {
      ...requireAcc(accountId),
      ...dateQ(range),
      include_action_payload: false,
      include_raw: false,
      include_row_details: false,
      ...(extra ?? {}),
    },
  }).then(normalizePortalProducts);

function normalizePortalProducts(res: PortalProductsPage): PortalProductsPage {
  return { ...res, items: (res.items ?? []).map(normalizePortalProductImages) };
}

function normalizePortalProductImages(row: PortalProductRow): PortalProductRow {
  const next: PortalProductRow = { ...row };
  const raw = firstImageUrl(
    next.thumbnail,
    next.thumbnail_url,
    next.main_photo_url,
    next.image_url,
    next.photo_url,
    next.photo,
    firstImageFromArray(next.photos),
    firstImageFromArray(next.images),
  );
  const display = proxyWbImageUrl(raw);
  if (display) {
    next.thumbnail = display;
    next.thumbnail_url = display;
    next.main_photo_url = display;
    next.image_url = display;
    next.photo_url = display;
    next.photo = display;
  }
  return next;
}

function firstImageUrl(...values: unknown[]): string | null {
  for (const value of values) {
    if (typeof value === "string" && value.trim()) return value.trim();
  }
  return null;
}

function firstImageFromArray(value: unknown): string | null {
  if (!Array.isArray(value)) return null;
  for (const item of value) {
    if (typeof item === "string" && item.trim()) return item.trim();
    if (item && typeof item === "object") {
      const obj = item as Record<string, unknown>;
      const url = firstImageUrl(
        obj.big,
        obj.canonical_url,
        obj.url,
        obj.full,
        obj.photo,
        obj.src,
        obj.c516x688,
        obj.square,
        obj.c246x328,
        obj.tm,
      );
      if (url) return url;
    }
  }
  return null;
}

function proxyWbImageUrl(src: string | null): string | null {
  return resolveWbImageUrl(src);
}

export const fetchProduct360 = (
  nmId: number | string,
  accountId: number | null | undefined,
  range?: DateRange,
) =>
  api<PortalProduct360Read>(API_ENDPOINTS.portal.product360(nmId), {
    query: {
      ...requireAcc(accountId),
      ...dateQ(range),
      history_limit: 6,
      actions_limit: 8,
      claims_limit: 6,
      include_reputation_items: false,
      include_action_payload: false,
      include_raw: false,
    },
  });

export const fetchPortalDataReadiness = (
  accountId: number | null | undefined,
  range?: DateRange,
) =>
  api<PortalDataReadinessRead>(API_ENDPOINTS.portalExtras.dataReadiness, {
    query: { ...requireAcc(accountId), ...dateQ(range) },
  });

export const fetchCardQualityIssues = (
  accountId: number | null | undefined,
  extra?: Record<string, any>,
) =>
  api<CardQualityIssuesPage>(API_ENDPOINTS.portal.cardQualityIssues, {
    query: { ...requireAcc(accountId), ...(extra ?? {}) },
  });

export const fetchProductGrouping = (
  nmId: number | string,
  accountId: number | null | undefined,
) =>
  api<any>(API_ENDPOINTS.portal.productGrouping(nmId), {
    query: requireAcc(accountId),
  });

export type FetchResultsParams = {
  action_id?: number | string | null;
  problem_instance_id?: number | string | null;
  problem_code?: string | null;
  nm_id?: number | string | null;
  source_module?: string | null;
  event_type?: string | null;
  result_status?: string | null;
  trust_state?: string | null;
  impact_type?: string | null;
  date_from?: string | null;
  date_to?: string | null;
  search?: string | null;
  limit?: number;
  offset?: number;
};

export const fetchResults = (
  accountId: number | null | undefined,
  extra?: FetchResultsParams & Record<string, any>,
) =>
  api<PortalResultEventsPage>(API_ENDPOINTS.portal.results, {
    query: { ...requireAcc(accountId), ...(extra ?? {}) },
  });

export const fetchProblemResults = (
  problemInstanceId: number | string,
  extra?: Pick<FetchResultsParams, "limit" | "offset">,
) =>
  api<PortalResultEventsPage>(
    API_ENDPOINTS.portal.problemResults(problemInstanceId),
    {
      query: extra ?? {},
    },
  );

export const fetchActionResults = (
  actionId: number | string,
  extra?: Record<string, any>,
) =>
  api<any>(API_ENDPOINTS.portal.actionResults(actionId), {
    query: extra ?? {},
  });

export const fetchAssignableUsers = (accountId: number | null | undefined) =>
  api<PortalAssignableUser[]>(API_ENDPOINTS.portal.assignableUsers, {
    query: requireAcc(accountId),
  });

export const fetchReputationSummary = (accountId: number | null | undefined) =>
  api<any>(API_ENDPOINTS.portal.reputationSummary, {
    query: requireAcc(accountId),
  });

export const fetchReputationInbox = (
  accountId: number | null | undefined,
  extra?: Record<string, any>,
) =>
  api<any>(API_ENDPOINTS.portal.reputationInbox, {
    query: { ...requireAcc(accountId), ...(extra ?? {}) },
  });

export const fetchReputationAnalytics = (
  accountId: number | null | undefined,
  extra?: Record<string, any>,
) =>
  api<any>(API_ENDPOINTS.portal.reputationAnalytics, {
    query: { ...requireAcc(accountId), ...(extra ?? {}) },
  });

export const fetchReputationDrafts = (
  accountId: number | null | undefined,
  extra?: Record<string, any>,
) =>
  api<any>(API_ENDPOINTS.portal.reputationDrafts, {
    query: { ...requireAcc(accountId), ...(extra ?? {}) },
  });

export const approveAllReputationDrafts = (
  accountId: number | null | undefined,
  limit = 200,
) =>
  api<any>(API_ENDPOINTS.portal.reputationDraftApproveAll, {
    method: "POST",
    query: { ...requireAcc(accountId), limit },
    body: {},
  });

export const fetchReputationChats = (
  accountId: number | null | undefined,
  extra?: Record<string, any>,
) =>
  api<any>(API_ENDPOINTS.portal.reputationChats, {
    query: { ...requireAcc(accountId), ...(extra ?? {}) },
  });

export const fetchReputationChatEvents = (
  chatId: number | string,
  accountId: number | null | undefined,
) =>
  api<any>(API_ENDPOINTS.portal.reputationChatEvents(chatId), {
    query: requireAcc(accountId),
  });

export const createReputationChatDraft = (
  chatId: number | string,
  accountId: number | null | undefined,
  payload: {
    draft_type?: string | null;
    text?: string | null;
    payload?: Record<string, any>;
  } = {},
) =>
  api<any>(API_ENDPOINTS.portal.reputationChatDraft(chatId), {
    method: "POST",
    query: requireAcc(accountId),
    body: payload,
  });

export const fetchCases = (
  accountId: number | null | undefined,
  extra?: Record<string, any>,
) =>
  apiList<any>(API_ENDPOINTS.portal.cases, {
    query: { ...requireAcc(accountId), ...(extra ?? {}) },
  });

export const fetchClaimCandidates = (
  accountId: number | null | undefined,
  extra?: Record<string, any>,
) =>
  apiList<any>(API_ENDPOINTS.portal.claimCandidates, {
    query: { ...requireAcc(accountId), ...(extra ?? {}) },
  });

export const fetchCaseDetail = (
  id: number | string,
  accountId?: number | null,
) => api<any>(API_ENDPOINTS.portal.caseDetail(id), { query: ngAcc(accountId) });

export const fetchOverview = (accountId?: number | null) =>
  api<PortalOverviewRead>(API_ENDPOINTS.portal.overview, {
    query: ngAcc(accountId),
  });

export const fetchReputationSettings = (accountId?: number | null) =>
  api<any>(API_ENDPOINTS.portal.reputationSettings, {
    query: ngAcc(accountId),
  });

export const fetchReputationBrands = (accountId?: number | null) =>
  api<any>(API_ENDPOINTS.portal.reputationBrands, {
    query: ngAcc(accountId),
  });

export const fetchReputationLearning = (accountId?: number | null) =>
  api<any>(API_ENDPOINTS.portal.reputationLearning, {
    query: ngAcc(accountId),
  });

export const toggleReputationLearning = (
  accountId: number | null | undefined,
  enabled: boolean,
) =>
  api<any>(API_ENDPOINTS.portal.reputationLearningToggle, {
    method: "POST",
    query: requireAcc(accountId),
    body: { enabled },
  });

export const updateReputationPrompts = (
  accountId: number | null | undefined,
  payload: Record<string, unknown>,
) =>
  api<any>(API_ENDPOINTS.portal.reputationPrompts, {
    method: "PUT",
    query: requireAcc(accountId),
    body: payload,
  });

export const applyReputationLearning = (
  accountId: number | null | undefined,
  payload: Record<string, unknown>,
) =>
  api<any>(API_ENDPOINTS.portal.reputationLearningApply, {
    method: "POST",
    query: requireAcc(accountId),
    body: payload,
  });

export const deleteReputationLearningEntry = (
  accountId: number | null | undefined,
  entryId: number | string,
) =>
  api<any>(API_ENDPOINTS.portal.reputationLearningEntry(entryId), {
    method: "DELETE",
    query: requireAcc(accountId),
  });

export const resetReputationLearning = (accountId: number | null | undefined) =>
  api<any>(API_ENDPOINTS.portal.reputationLearningReset, {
    method: "POST",
    query: requireAcc(accountId),
    body: {},
  });

export const fetchReputationProductInsights = (
  accountId: number | null | undefined,
  nmId: number | string,
) =>
  api<any>(API_ENDPOINTS.portal.reputationProductInsights(nmId), {
    query: requireAcc(accountId),
  });

export const updateReputationSettings = (
  accountId: number | null | undefined,
  payload: Record<string, unknown>,
) =>
  api<any>(API_ENDPOINTS.portal.reputationSettings, {
    method: "PUT",
    query: requireAcc(accountId),
    body: payload,
  });

export const syncReputation = (accountId: number | null | undefined) =>
  api<any>(API_ENDPOINTS.portal.reputationSync, {
    method: "POST",
    query: requireAcc(accountId),
  });

export const createReputationDraft = (
  itemId: number | string,
  accountId: number | null | undefined,
  payload: {
    draft_type?: string | null;
    text?: string | null;
    force_ai?: boolean;
    payload?: Record<string, any>;
  } = {},
) =>
  api<any>(API_ENDPOINTS.portal.reputationDraft(itemId), {
    method: "POST",
    query: requireAcc(accountId),
    body: payload,
  });

export const approveReputationDraft = (
  draftId: number | string,
  accountId: number | null | undefined,
) =>
  api<any>(API_ENDPOINTS.portal.reputationDraftApprove(draftId), {
    method: "POST",
    query: requireAcc(accountId),
    body: {},
  });

export const regenerateReputationDraft = (
  draftId: number | string,
  accountId: number | null | undefined,
  payload: {
    reason?: string | null;
    force_ai?: boolean;
    payload?: Record<string, any>;
  } = {},
) =>
  api<any>(API_ENDPOINTS.portal.reputationDraftRegenerate(draftId), {
    method: "POST",
    query: requireAcc(accountId),
    body: payload,
  });

export const rejectReputationDraft = (
  draftId: number | string,
  accountId: number | null | undefined,
  payload: { reason?: string | null; payload?: Record<string, any> } = {},
) =>
  api<any>(API_ENDPOINTS.portal.reputationDraftReject(draftId), {
    method: "POST",
    query: requireAcc(accountId),
    body: payload,
  });

export const publishReputationDraft = (
  draftId: number | string,
  accountId: number | null | undefined,
  payload: {
    confirm: boolean;
    text?: string | null;
    payload?: Record<string, any>;
  },
) =>
  api<any>(API_ENDPOINTS.portal.reputationDraftPublish(draftId), {
    method: "POST",
    query: requireAcc(accountId),
    body: payload,
  });

export const markReputationNoReply = (
  itemId: number | string,
  accountId: number | null | undefined,
  payload: {
    confirm: boolean;
    reason?: string | null;
    payload?: Record<string, any>;
  },
) =>
  api<any>(API_ENDPOINTS.portal.reputationNoReply(itemId), {
    method: "POST",
    query: requireAcc(accountId),
    body: payload,
  });

export const fetchReputationAdminProviderStatus = (
  accountId: number | null | undefined,
) =>
  api<any>(API_ENDPOINTS.portal.reputationAdminProviderStatus, {
    query: requireAcc(accountId),
  });

export const fetchReputationAdminPromptDebug = (
  accountId: number | null | undefined,
  itemId: number | string,
) =>
  api<any>(API_ENDPOINTS.portal.reputationAdminPromptDebug, {
    query: { ...requireAcc(accountId), item_id: itemId },
  });

export const probeReputationAdminPrompt = (
  accountId: number | null | undefined,
  itemId: number | string,
  payload: Record<string, unknown> = { dry_run: true },
) =>
  api<any>(API_ENDPOINTS.portal.reputationAdminPromptProbe, {
    method: "POST",
    query: { ...requireAcc(accountId), item_id: itemId },
    body: payload,
  });

export const fetchReputationAdminGenerationLogs = (
  accountId: number | null | undefined,
  extra?: Record<string, any>,
) =>
  api<any>(API_ENDPOINTS.portal.reputationAdminGenerationLogs, {
    query: { ...requireAcc(accountId), ...(extra ?? {}) },
  });

export const fetchReputationAdminGenerationLogDetail = (
  accountId: number | null | undefined,
  logId: number | string,
) =>
  api<any>(API_ENDPOINTS.portal.reputationAdminGenerationLogDetail(logId), {
    query: requireAcc(accountId),
  });

// ─── Mutations ────────────────────────────────────────────────────────
export const updateActionBySource = (payload: {
  source_module: string;
  source_id: string;
  status: PortalActionStatus;
  account_id?: number | null;
  comment?: string;
  status_reason?: string | null;
  assigned_to_user_id?: number | null;
  deadline_at?: string | null;
  review_status?: PortalActionReviewStatus | null;
  event_type?:
    | "status_change"
    | "dismiss"
    | "assign"
    | "comment"
    | "recheck"
    | string
    | null;
}) => {
  const { account_id, ...body } = payload;
  return api<any>(API_ENDPOINTS.portal.actionUpdateBySource, {
    method: "PATCH",
    query: ngAcc(account_id),
    body: { ...body, ...(account_id != null ? { account_id } : {}) },
  });
};

export const recheckProblemInstance = (
  problemId: number | string,
  accountId?: number | null,
) =>
  api<any>(API_ENDPOINTS.portal.problemRecheck(problemId), {
    method: "POST",
    query: ngAcc(accountId),
  });

export const updateActionById = (
  id: number | string,
  payload: {
    status: PortalActionStatus;
    comment?: string;
    status_reason?: string | null;
    account_id?: number | null;
    assigned_to_user_id?: number | null;
    deadline_at?: string | null;
    review_status?: PortalActionReviewStatus | null;
    event_type?:
      | "status_change"
      | "dismiss"
      | "assign"
      | "comment"
      | "recheck"
      | string
      | null;
  },
) =>
  api<any>(API_ENDPOINTS.portal.actionUpdate(id), {
    method: "PATCH",
    body: payload,
  });

export const createManualPortalAction = (
  payload: PortalManualActionCreatePayload,
) =>
  api<PortalAction>(API_ENDPOINTS.portal.manualActionCreate, {
    method: "POST",
    body: payload,
  });

export const previewGrouping = (
  accountId: number | null | undefined,
  payload: {
    nm_id?: number | string | null;
    preset_key?: string | null;
    recommendation_scenario_id?: number | null;
    custom_config?: Record<string, any>;
  } = {},
) => {
  const nmId =
    payload.nm_id == null || payload.nm_id === ""
      ? null
      : Number(payload.nm_id);
  if (nmId != null && !Number.isFinite(nmId)) {
    throw new Error("grouping: nm_id must be numeric");
  }
  return api<any>(API_ENDPOINTS.portal.groupingPreview, {
    method: "POST",
    body: {
      account_id: requireAcc(accountId).account_id,
      ...payload,
      nm_id: nmId,
      custom_config: payload.custom_config ?? {},
    },
  });
};

export const updateGroupingCandidateStatus = (
  candidateId: number | string,
  accountId: number | null | undefined,
  payload: {
    status:
      | "new"
      | "reviewing"
      | "accepted"
      | "rejected"
      | "postponed"
      | "expired";
    reason?: string | null;
  },
) =>
  api<any>(API_ENDPOINTS.portal.groupingCandidateStatus(candidateId), {
    method: "PATCH",
    query: requireAcc(accountId),
    body: payload,
  });

export const createCaseFromSignal = (payload: {
  account_id?: number | null;
  [k: string]: any;
}) =>
  api<any>(API_ENDPOINTS.portal.caseFromSignal, {
    method: "POST",
    body: payload,
  });

export const createClaimCase = (
  accountId: number | null | undefined,
  payload: { account_id?: number | null; [k: string]: any },
) =>
  api<any>(API_ENDPOINTS.portal.cases, {
    method: "POST",
    body: { ...payload, account_id: requireAcc(accountId).account_id },
  });

export const startClaimScan = (
  accountId: number | null | undefined,
  payload: {
    detector_types?: string[];
    date_from?: string | null;
    date_to?: string | null;
    force?: boolean;
  } = {},
) =>
  api<any>(API_ENDPOINTS.portal.claimsScans, {
    method: "POST",
    body: {
      account_id: requireAcc(accountId).account_id,
      detector_types: payload.detector_types ?? ["all"],
      ...payload,
    },
  });

export const createCaseFromCandidate = (
  candidateId: number | string,
  accountId: number | null | undefined,
) =>
  api<any>(API_ENDPOINTS.portal.claimCandidateCreateCase(candidateId), {
    method: "POST",
    query: requireAcc(accountId),
    body: {},
  });

export const extractClaimQrImage = (
  accountId: number | null | undefined,
  file: File,
) => {
  const formData = new FormData();
  formData.append("file", file);
  return api<any>(API_ENDPOINTS.portal.claimsQrExtract, {
    method: "POST",
    query: requireAcc(accountId),
    formData,
  });
};

export const extractClaimMedia = (
  accountId: number | null | undefined,
  files: File[],
) => {
  const formData = new FormData();
  files.forEach((file) => formData.append("files", file));
  return api<any>(API_ENDPOINTS.portal.claimsMediaExtract, {
    method: "POST",
    query: requireAcc(accountId),
    formData,
  });
};

export const lookupClaimOrder = (
  accountId: number | null | undefined,
  orderFields: Record<string, unknown>,
) =>
  api<any>(API_ENDPOINTS.portal.claimsOrderLookup, {
    method: "POST",
    body: {
      account_id: requireAcc(accountId).account_id,
      order_fields: orderFields,
    },
  });

export const fetchClaimSupportCategories = (
  accountId: number | null | undefined,
) =>
  api<any>(API_ENDPOINTS.portal.claimsSupportCategories, {
    query: requireAcc(accountId),
  });

export const generateClaimAppealDraft = (
  accountId: number | null | undefined,
  payload: {
    category: string;
    subcategory: string;
    order_fields?: Record<string, unknown>;
    defect_description?: string;
    operator_note?: string;
    video_url?: string | null;
  },
) =>
  api<any>(API_ENDPOINTS.portal.claimsAppealDraft, {
    method: "POST",
    body: { ...payload, account_id: requireAcc(accountId).account_id },
  });

export const proofCheckCase = (
  id: number | string,
  payload: { account_id?: number | null; [k: string]: any } = {},
) =>
  api<any>(API_ENDPOINTS.portal.caseProofCheck(id), {
    method: "POST",
    body: payload,
  });

export const generateClaimDraft = (
  id: number | string,
  payload: { [k: string]: any } = {},
) =>
  api<any>(API_ENDPOINTS.portal.caseGenerateDraft(id), {
    method: "POST",
    body: { draft_type: "support_appeal", language: "ru", ...payload },
  });

export const submitCase = (
  id: number | string,
  payload: {
    account_id?: number | null;
    confirm?: boolean;
    [k: string]: any;
  } = {},
) =>
  api<any>(API_ENDPOINTS.portal.caseSubmit(id), {
    method: "POST",
    body: payload,
  });
