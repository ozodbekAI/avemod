// @ts-nocheck
import type { UserRead } from "@/lib/api";
import { evidenceFrom, type EvidenceLedger } from "@/lib/evidence";
import {
  isSellerVisibleMoneyTrust,
  moneyTrustFrom,
  type MoneyTrustInfo,
} from "@/lib/money-trust";
import type {
  AllowedActionCode as PortalAllowedActionCode,
  PortalAction,
  PortalActionEvidenceState,
  PortalActionPriority,
  PortalActionSeverity,
  PortalActionSourceModule,
  PortalActionStatus,
  PortalResultEventsPage,
  ProblemResultEvent,
  ProblemResultStatus,
} from "@/lib/portal";
import {
  problemResultEvents,
  problemResultStatusFromSummary,
  problemResultSummaryFromPage,
} from "@/lib/problem-results";
import type {
  AllowedActionCode,
  ImpactType,
  JsonRecord,
  PriceSafetyContract,
  ProblemResultSummary,
  SellerProblemContract,
} from "@/lib/problem-contracts";
import {
  problemImpactLabel,
  problemStatusLabel,
  seededProblemSellerNextStep,
  seededProblemSellerRecheckRule,
  seededProblemSellerTitle,
  seededProblemSellerWhy,
} from "@/lib/problem-ux-copy";
import { actionCenterWorkScreenHref } from "@/lib/action-center-routing";

type AssignableUserLike = UserRead & {
  display_name?: string | null;
  role?: string | null;
};

type PortalActionAdapterFields = PortalAction & {
  problem_code?: unknown;
  problem_instance_id?: unknown;
  solve_map?: unknown;
  sla_state?: unknown;
  due_in_hours?: unknown;
  is_overdue?: unknown;
  money_impact_amount?: unknown;
  money_impact_currency?: unknown;
  summary?: unknown;
};

export type ActionCenterSourceKind =
  | "problem_engine"
  | "checker"
  | "finance"
  | "data_quality"
  | "costs"
  | "manual"
  | "legacy"
  | "beta";

export type ActionCenterEvidenceState =
  | "full_evidence"
  | "partial_evidence"
  | "missing_evidence"
  | "read_only_signal";

export type ActionCenterSourceStatus =
  | "fresh"
  | "stale"
  | "missing"
  | "not_configured";

export type ActionCenterDataFreshness = {
  required_sources: string[];
  source_status: ActionCenterSourceStatus;
  last_synced_at: string | null;
  blocking_sources: string[];
  freshness_notes: string[];
};

export type ActionCenterAllowedActionCode = AllowedActionCode;

export type ActionCenterSolveStepStatus =
  | "ready"
  | "available"
  | "blocked"
  | "waiting_for_data"
  | "done";

export type ActionCenterSolveMapStep = {
  step_id: string;
  order: number;
  title: string;
  description: string;
  status: ActionCenterSolveStepStatus;
  action_code: ActionCenterAllowedActionCode | null;
  target_href: string | null;
  required_metrics: string[];
  blocking_reason: string | null;
  completion_signal: string | null;
};

export type ActionCenterSolveMap = {
  title: string;
  summary: string;
  steps: ActionCenterSolveMapStep[];
};

export type ActionCenterAllowedActionItem = {
  code: ActionCenterAllowedActionCode;
  original_code: string;
  enabled: boolean;
  disabled_reason: string | null;
  requires_preview: boolean;
  requires_diff: boolean;
  requires_confirm: boolean;
  requires_audit: boolean;
  is_dangerous: boolean;
};

export type ActionCenterHistoryItem = {
  event_type?: string | null;
  old_status?: string | null;
  new_status?: string | null;
  status?: string | null;
  comment?: string | null;
  created_at?: string | null;
  created_by?: number | null;
};

export type ActionCenterHistorySummary = {
  total: number;
  latest_label: string | null;
  latest_at: string | null;
  items: ActionCenterHistoryItem[];
};

export interface ActionCenterItem {
  id: string;
  account_id: number | null;
  action_id: number | null;
  source: string | null;
  source_module: PortalActionSourceModule | null;
  source_id: string | null;
  source_kind: ActionCenterSourceKind;
  source_sync_state?: string | null;
  action_type: string;
  created_at: string | null;
  last_seen_at: string | null;
  entity_type: string | null;
  entity_id: string | number | null;
  nm_id: number | null;
  sku_id: number | null;
  vendor_code: string | null;
  title: string;
  short_explanation: string;
  reason: string;
  summary?: string | null;
  next_step?: string | null;
  severity: PortalActionSeverity | null;
  priority: PortalActionPriority | null;
  status: PortalActionStatus;
  status_label: string;
  trust_state: string | null;
  impact_type: ImpactType | string | null;
  money_impact_amount: number | null;
  money_impact_currency: string | null;
  expected_impact_amount?: number | null;
  expected_effect_amount?: number | null;
  confidence: string | null;
  problem_code: string | null;
  detector_code: string | null;
  issue_code: string | null;
  data_freshness: ActionCenterDataFreshness;
  solve_map: ActionCenterSolveMap | null;
  evidence_ledger: EvidenceLedger | null;
  evidence_state: ActionCenterEvidenceState;
  money_trust: MoneyTrustInfo;
  allowed_actions: ActionCenterAllowedActionCode[];
  allowed_action_items: ActionCenterAllowedActionItem[];
  guided_fix?: PortalAction["guided_fix"];
  can_update: boolean;
  can_update_reason: string | null;
  can_recheck: boolean;
  can_assign: boolean;
  can_set_deadline: boolean;
  is_beta: boolean;
  is_test_only: boolean;
  is_read_only: boolean;
  is_problem_like: boolean;
  is_seller_visible: boolean;
  is_claims: boolean;
  result_status: ProblemResultStatus;
  result_summary: ProblemResultSummary | JsonRecord | null;
  latest_result_event: ProblemResultEvent | null;
  price_safety: PriceSafetyContract | null;
  needs_price_safety: boolean;
  assigned_to_user_id: number | null;
  assigned_to_user_name: string | null;
  deadline_at: string | null;
  is_overdue: boolean;
  due_in_hours: number | null;
  sla_state: "ok" | "due_soon" | "overdue" | "no_deadline";
  last_comment: string | null;
  last_status_changed_at: string | null;
  history_summary: ActionCenterHistorySummary;
  recheck_rule: string;
  problem_instance_id: number | null;
  payload?: JsonRecord;
  raw?: JsonRecord;
  linked_entity?: JsonRecord;
}

export type ActionCenterImpactBucketKey =
  | "confirmed_loss"
  | "probable_risk"
  | "blocked_cash"
  | "opportunity"
  | "data_blocker";

type AdaptActionCenterOptions = {
  resultPage?: PortalResultEventsPage | null;
  users?: AssignableUserLike[] | null;
  now?: Date | string | null;
};

const BETA_SOURCE_MODULES = new Set([
  "grouping_beta",
  "reputation",
  "claims",
  "photo",
  "stockops",
  "experiments",
]);

const VALID_EVIDENCE_STATES = new Set<ActionCenterEvidenceState>([
  "full_evidence",
  "partial_evidence",
  "missing_evidence",
  "read_only_signal",
]);

const VALID_SOURCE_STATUSES = new Set<ActionCenterSourceStatus>([
  "fresh",
  "stale",
  "missing",
  "not_configured",
]);

const SAFE_WITH_MISSING_EVIDENCE_ACTIONS = new Set([
  "assign",
  "create_task",
  "dismiss",
  "map_sku",
  "open_data_fix",
  "open_results",
  "upload_cost",
  "recheck",
  "trigger_recheck",
]);

const ACTION_CENTER_ALLOWED_ACTIONS = new Set<ActionCenterAllowedActionCode>([
  "create_task",
  "assign",
  "recheck",
  "dismiss",
  "open_data_fix",
  "open_price_review",
  "open_promo_planner",
  "open_supply_planner",
  "open_ads_dashboard",
  "run_checker",
  "upload_cost",
  "map_sku",
  "classify_expense",
  "open_product",
  "open_results",
]);

const ACTION_CENTER_ACTION_ALIASES: Record<
  string,
  ActionCenterAllowedActionCode
> = {
  trigger_recheck: "recheck",
  data_fix: "open_data_fix",
  open_costs: "upload_cost",
  review_cost: "upload_cost",
  cost_review: "upload_cost",
  price_review: "open_price_review",
  review_price: "open_price_review",
  pricing_review: "open_price_review",
  promo_planner: "open_promo_planner",
  review_promo: "open_promo_planner",
  review_promotion: "open_promo_planner",
  safe_promo: "open_promo_planner",
  reduce_promo: "open_promo_planner",
  bundle: "open_promo_planner",
  plan_supply: "open_supply_planner",
  supply_review: "open_supply_planner",
  reduce_ads: "open_ads_dashboard",
  review_ads: "open_ads_dashboard",
  ads_review: "open_ads_dashboard",
  pause_ads: "open_ads_dashboard",
  lower_ads: "open_ads_dashboard",
  review_bids: "open_ads_dashboard",
  check_card_quality: "run_checker",
  review_content: "run_checker",
  content_check: "run_checker",
  mark_admin_investigation: "create_task",
  admin_investigation: "create_task",
  mark_system_wait: "recheck",
  wb_price_change: "open_price_review",
  wb_content_apply: "run_checker",
  promotion_create: "open_promo_planner",
  promotion_creation: "open_promo_planner",
  promotion_start: "open_promo_planner",
  promotion_stop: "open_promo_planner",
  ad_bid_change: "open_ads_dashboard",
};

const DANGEROUS_WRITE_ACTIONS = new Set([
  "wb_price_change",
  "wb_content_apply",
  "promotion_create",
  "promotion_creation",
  "promotion_start",
  "promotion_stop",
  "ad_bid_change",
]);

const PRICE_SAFETY_ACTIONS = new Set<ActionCenterAllowedActionCode>([
  "open_price_review",
  "open_promo_planner",
]);

const FRESHNESS_SENSITIVE_ACTIONS = new Set<ActionCenterAllowedActionCode>([
  "open_price_review",
  "open_promo_planner",
  "open_ads_dashboard",
]);

const PRICE_SAFETY_PROBLEM_CODES = new Set([
  "overstock_slow_moving",
  "dead_stock",
  "negative_unit_profit",
  "promo_not_profitable",
  "price_below_safe_margin",
]);

function isRecord(value: unknown): value is JsonRecord {
  return !!value && typeof value === "object" && !Array.isArray(value);
}

function compactRecord(value: unknown): JsonRecord {
  return isRecord(value) ? value : {};
}

function hasKeys(value: unknown): boolean {
  return isRecord(value) && Object.keys(value).length > 0;
}

function normalizeEvidenceState(
  value: unknown,
): ActionCenterEvidenceState | null {
  const state = normalizeText(value);
  return VALID_EVIDENCE_STATES.has(state as ActionCenterEvidenceState)
    ? (state as ActionCenterEvidenceState)
    : null;
}

function normalizeText(value: unknown): string {
  return String(value ?? "")
    .trim()
    .toLowerCase();
}

function firstText(...values: unknown[]): string | null {
  for (const value of values) {
    if (typeof value === "string" && value.trim()) return value.trim();
    if (typeof value === "number" && Number.isFinite(value)) {
      return String(value);
    }
  }
  return null;
}

function firstNumber(...values: unknown[]): number | null {
  for (const value of values) {
    if (typeof value === "number" && Number.isFinite(value)) return value;
    if (typeof value === "string" && value.trim()) {
      const parsed = Number(value);
      if (Number.isFinite(parsed)) return parsed;
    }
  }
  return null;
}

function firstId(...values: unknown[]): string | number | null {
  for (const value of values) {
    if (typeof value === "number" && Number.isFinite(value)) return value;
    if (typeof value === "string" && value.trim()) return value.trim();
  }
  return null;
}

function sellerCopyVarsFrom(
  action: PortalAction,
  payload: JsonRecord,
  raw: JsonRecord,
  linked: JsonRecord,
): Record<string, string | number | null | undefined> {
  const keys = [
    "nm_id",
    "revenue_30d",
    "unit_profit",
    "margin_pct",
    "stock_qty",
    "days_of_stock",
    "avg_daily_sales_14d",
    "avg_daily_sales_7d",
    "ad_spend_7d",
    "unit_profit_after_ads",
    "promo_spend_30d",
    "price_after_discount",
    "sales_30d",
  ];
  return Object.fromEntries(
    keys.map((key) => [
      key,
      firstText(
        (action as JsonRecord)[key],
        linked[key],
        payload[key],
        raw[key],
      ) ??
        firstNumber(
          (action as JsonRecord)[key],
          linked[key],
          payload[key],
          raw[key],
        ),
    ]),
  ) as Record<string, string | number | null | undefined>;
}

function normalizedCode(value: unknown): string | null {
  const code = normalizeText(value);
  return code || null;
}

function allowedActionsFrom(...values: unknown[]): PortalAllowedActionCode[] {
  for (const value of values) {
    if (Array.isArray(value)) {
      return value
        .map((item) => String(item).trim())
        .filter(Boolean) as PortalAllowedActionCode[];
    }
    if (typeof value === "string" && value.trim()) {
      return value
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean) as PortalAllowedActionCode[];
    }
  }
  return [];
}

function canonicalActionCode(
  value: unknown,
): ActionCenterAllowedActionCode | null {
  const raw = normalizeText(value);
  if (!raw) return null;
  const code = ACTION_CENTER_ACTION_ALIASES[raw] ?? raw;
  return ACTION_CENTER_ALLOWED_ACTIONS.has(
    code as ActionCenterAllowedActionCode,
  )
    ? (code as ActionCenterAllowedActionCode)
    : null;
}

function canonicalAllowedActionsFrom(
  rawActions: PortalAllowedActionCode[],
  action: PortalAction,
): Array<{ code: ActionCenterAllowedActionCode; original: string }> {
  const pairs: Array<{
    code: ActionCenterAllowedActionCode;
    original: string;
  }> = [];
  for (const rawAction of rawActions) {
    const original = normalizeText(rawAction);
    const code = canonicalActionCode(original);
    if (!code || pairs.some((item) => item.code === code)) continue;
    pairs.push({ code, original: original || code });
  }
  if (!pairs.length) {
    const routeKey = normalizeText(action.guided_fix?.route_key);
    const actionType = normalizeText(action.action_type);
    const inferred =
      routeKey === "data_fix"
        ? "open_data_fix"
        : routeKey === "costs"
          ? "upload_cost"
          : routeKey === "product"
            ? "open_product"
            : routeKey === "checker"
              ? "run_checker"
              : routeKey === "stock_control"
                ? "open_supply_planner"
                : routeKey === "ads"
                  ? "open_ads_dashboard"
                  : canonicalActionCode(actionType);
    if (inferred)
      pairs.push({ code: inferred, original: actionType || inferred });
  }
  return pairs;
}

function normalizeUnavailableReason(value: unknown): string | null {
  if (typeof value !== "string" || !value.trim()) return null;
  const raw = value.trim();
  const code = normalizeText(raw).replaceAll("-", "_").replaceAll(" ", "_");
  if (
    code.includes("wb_api") ||
    code.includes("api_permission") ||
    code.includes("permission_denied") ||
    code.includes("no_permission")
  ) {
    return "Нет прав WB API";
  }
  if (code.includes("module_disabled") || code.includes("disabled_module")) {
    return "Модуль отключён";
  }
  if (
    code.includes("missing_data") ||
    code.includes("data_incomplete") ||
    code.includes("not_enough_data")
  ) {
    return "Не хватает данных";
  }
  if (code.includes("admin") || code.includes("superuser")) {
    return "Действие доступно только администратору";
  }
  return raw;
}

function lookupActionReason(
  code: ActionCenterAllowedActionCode,
  original: string,
  payload: JsonRecord,
  raw: JsonRecord,
): string | null {
  const sources = [
    payload.action_unavailable_reasons,
    payload.unavailable_actions,
    payload.disabled_actions,
    raw.action_unavailable_reasons,
    raw.unavailable_actions,
    raw.disabled_actions,
  ];
  for (const source of sources) {
    const record = compactRecord(source);
    const reason = normalizeUnavailableReason(
      record[code] ??
        record[original] ??
        record[String(code)] ??
        record[String(original)],
    );
    if (reason) return reason;
  }
  const missingPermissions = [
    payload.missing_permissions,
    payload.required_permissions_missing,
    raw.missing_permissions,
    raw.required_permissions_missing,
  ].flatMap((value) => (Array.isArray(value) ? value : []));
  if (missingPermissions.some((item) => normalizeText(item).includes("wb"))) {
    return "Нет прав WB API";
  }
  if (payload.wb_api_permission === false || raw.wb_api_permission === false) {
    return "Нет прав WB API";
  }
  if (
    payload.module_disabled === true ||
    raw.module_disabled === true ||
    normalizeText(payload.module_status ?? raw.module_status).includes(
      "disabled",
    )
  ) {
    return "Модуль отключён";
  }
  if (
    payload.requires_admin === true ||
    raw.requires_admin === true ||
    payload.admin_only === true ||
    raw.admin_only === true
  ) {
    return "Действие доступно только администратору";
  }
  return normalizeUnavailableReason(
    payload.disabled_reason ??
      payload.can_update_reason ??
      raw.disabled_reason ??
      raw.can_update_reason,
  );
}

function priceSafetyRecord(
  payload: JsonRecord,
  raw: JsonRecord,
  ledger: EvidenceLedger | null,
): JsonRecord {
  return compactRecord(
    payload.price_safety ??
      raw.price_safety ??
      compactRecord(payload.calculation_snapshot).price_safety ??
      compactRecord(raw.calculation_snapshot).price_safety ??
      ledger?.price_safety,
  );
}

function priceSafetyContractFrom(
  payload: JsonRecord,
  raw: JsonRecord,
  ledger: EvidenceLedger | null,
): PriceSafetyContract | null {
  const safety = priceSafetyRecord(payload, raw, ledger);
  return hasKeys(safety) ? (safety as PriceSafetyContract) : null;
}

function listFromUnknown(value: unknown): string[] {
  if (Array.isArray(value)) {
    return value.map((item) => String(item ?? "").trim()).filter(Boolean);
  }
  if (typeof value === "string" && value.trim()) return [value.trim()];
  return [];
}

function normalizeSourceStatus(
  value: unknown,
): ActionCenterSourceStatus | null {
  const status = normalizeText(value).replaceAll("-", "_");
  return VALID_SOURCE_STATUSES.has(status as ActionCenterSourceStatus)
    ? (status as ActionCenterSourceStatus)
    : null;
}

function sourceKeyFromText(value: unknown): string | null {
  const text = normalizeText(value).replaceAll("-", "_");
  if (!text) return null;
  if (
    text.includes("stock") ||
    text.includes("остат") ||
    text.includes("inventory")
  ) {
    return "stocks";
  }
  if (
    text.includes("sales") ||
    text.includes("sale_") ||
    text.includes("orders") ||
    text.includes("order_") ||
    text.includes("sku_daily") ||
    text.includes("продаж") ||
    text.includes("заказ")
  ) {
    return "sales";
  }
  if (
    text.includes("cost") ||
    text.includes("cogs") ||
    text.includes("unit_cost") ||
    text.includes("manual_cost") ||
    text.includes("себестоим")
  ) {
    return "costs";
  }
  if (
    text.includes("price") ||
    text.includes("pricing") ||
    text.includes("цен")
  ) {
    return "prices";
  }
  if (
    text.includes("finance") ||
    text.includes("realization") ||
    text.includes("report") ||
    text.includes("финанс")
  ) {
    return "finance";
  }
  if (
    text.includes("ads") ||
    text.includes("advert") ||
    text.includes("реклам")
  ) {
    return "ads";
  }
  if (
    text.includes("promo") ||
    text.includes("promotion") ||
    text.includes("акци")
  ) {
    return "promotions";
  }
  if (
    text.includes("checker") ||
    text.includes("card") ||
    text.includes("content") ||
    text.includes("карточ")
  ) {
    return "cards";
  }
  return null;
}

function uniqueSourceKeys(values: unknown[]): string[] {
  const keys: string[] = [];
  for (const value of values) {
    const key = sourceKeyFromText(value);
    if (key && !keys.includes(key)) keys.push(key);
  }
  return keys;
}

function sourceKeysFromRecords(records: unknown[]): string[] {
  const values: unknown[] = [];
  records.forEach((item) => {
    const record = compactRecord(item);
    values.push(
      record.source,
      record.source_table,
      record.table,
      record.source_endpoint,
      record.wb_endpoint,
      record.metric_code,
      record.label,
    );
  });
  return uniqueSourceKeys(values);
}

function inferredRequiredSources(problemCode: string | null): string[] {
  const code = normalizeText(problemCode);
  if (code === "low_stock_risk" || code === "fast_stock_depletion") {
    return ["stocks", "sales"];
  }
  if (code === "missing_cost_blocks_profit") return ["costs"];
  if (code === "negative_unit_profit") return ["sales", "finance", "costs"];
  if (
    code === "overstock_slow_moving" ||
    code === "dead_stock" ||
    code === "promo_not_profitable"
  ) {
    return ["stocks", "sales"];
  }
  if (code === "price_below_safe_margin") return ["prices", "costs"];
  if (code === "ads_spend_without_profit") return ["ads", "sales", "costs"];
  if (code === "card_quality_issue") return ["cards"];
  return [];
}

function freshnessStatusFromBlocks(
  blockingSources: string[],
): ActionCenterSourceStatus {
  return blockingSources.length > 0 ? "missing" : "fresh";
}

function sourceFreshnessFrom(
  action: PortalAction,
  payload: JsonRecord,
  raw: JsonRecord,
  ledger: EvidenceLedger | null,
  problemCode: string | null,
  priceSafety: PriceSafetyContract | null,
): ActionCenterDataFreshness {
  const adapted = action as PortalActionAdapterFields & {
    data_freshness?: unknown;
  };
  const explicit = compactRecord(
    adapted.data_freshness ??
      payload.data_freshness ??
      raw.data_freshness ??
      payload.source_freshness ??
      raw.source_freshness,
  );
  const explicitRequired = [
    ...listFromUnknown(explicit.required_sources),
    ...listFromUnknown(explicit.requiredSources),
  ];
  const ledgerSources = [
    ...sourceKeysFromRecords(
      Array.isArray(ledger?.source_references) ? ledger.source_references : [],
    ),
    ...sourceKeysFromRecords(
      Array.isArray(ledger?.input_facts) ? ledger.input_facts : [],
    ),
  ];
  const requiredSources = Array.from(
    new Set(
      [
        ...explicitRequired.map(
          (item) => sourceKeyFromText(item) ?? normalizeText(item),
        ),
        ...ledgerSources,
        ...inferredRequiredSources(problemCode),
      ].filter(Boolean),
    ),
  );
  const missingSourceKeys = uniqueSourceKeys([
    ...listFromUnknown(ledger?.missing_data),
    ...listFromUnknown(ledger?.calculation_warnings),
    ...listFromUnknown(payload.missing_data),
    ...listFromUnknown(raw.missing_data),
    ...listFromUnknown(payload.missing_metrics),
    ...listFromUnknown(raw.missing_metrics),
    ...listFromUnknown(priceSafety?.missing_required_metrics),
  ]);
  const explicitBlocking = [
    ...listFromUnknown(explicit.blocking_sources),
    ...listFromUnknown(explicit.blockingSources),
  ].map((item) => sourceKeyFromText(item) ?? normalizeText(item));
  const blockingSources = Array.from(
    new Set([...explicitBlocking, ...missingSourceKeys].filter(Boolean)),
  );
  const lastSyncedAt =
    firstText(
      explicit.last_synced_at,
      explicit.lastSyncedAt,
      payload.last_synced_at,
      raw.last_synced_at,
      ...(Array.isArray(ledger?.source_references)
        ? ledger.source_references.map((ref) =>
            firstText(ref.loaded_at, ref.updated_at),
          )
        : []),
    ) ?? null;
  const sourceStatus =
    normalizeSourceStatus(explicit.source_status) ??
    normalizeSourceStatus(explicit.status) ??
    normalizeSourceStatus(payload.source_status) ??
    normalizeSourceStatus(raw.source_status) ??
    freshnessStatusFromBlocks(blockingSources);
  const freshnessNotes = [
    ...listFromUnknown(explicit.freshness_notes),
    ...listFromUnknown(explicit.notes),
  ];
  if (sourceStatus !== "fresh" && freshnessNotes.length === 0) {
    freshnessNotes.push(
      sourceStatus === "stale"
        ? "Источник устарел: выводы предварительные до новой синхронизации."
        : "Источник не готов: доказательства и денежное влияние заблокированы до синхронизации.",
    );
  }
  return {
    required_sources: requiredSources,
    source_status: sourceStatus,
    last_synced_at: lastSyncedAt,
    blocking_sources: blockingSources,
    freshness_notes: freshnessNotes,
  };
}

export function dataFreshnessBlocksAction(
  freshness: ActionCenterDataFreshness | null | undefined,
): boolean {
  if (!freshness) return false;
  return (
    freshness.source_status !== "fresh" ||
    (Array.isArray(freshness.blocking_sources) &&
      freshness.blocking_sources.length > 0)
  );
}

export function dataFreshnessStatusLabel(
  freshness: ActionCenterDataFreshness | null | undefined,
): string {
  if (!freshness) return "Данные предварительные";
  if (
    freshness.source_status === "fresh" &&
    !dataFreshnessBlocksAction(freshness)
  ) {
    return "Данные свежие";
  }
  if (freshness.source_status === "stale") return "Нужна синхронизация";
  if (freshness.source_status === "missing") return "Нужна синхронизация";
  if (freshness.source_status === "not_configured")
    return "Источник не подключён";
  return "Данные предварительные";
}

export function actionCenterSourceFreshnessLabel(
  value: string | null | undefined,
): string {
  const key = normalizeText(value);
  const labels: Record<string, string> = {
    stocks: "Остатки",
    stock: "Остатки",
    sales: "Продажи и заказы",
    orders: "Заказы",
    finance: "Финансы WB",
    costs: "Себестоимость",
    cost: "Себестоимость",
    prices: "Цены",
    price: "Цены",
    ads: "Реклама",
    cards: "Карточки",
    promotions: "Акции WB",
  };
  return labels[key] ?? (value ? value.replaceAll("_", " ") : "Источник");
}

export function dataFreshnessBlockingLabel(
  freshness: ActionCenterDataFreshness | null | undefined,
): string {
  if (!freshness) return "Данные предварительные";
  const sources =
    freshness.blocking_sources.length > 0
      ? freshness.blocking_sources
      : freshness.required_sources;
  const sourceText = sources
    .map((source) => actionCenterSourceFreshnessLabel(source))
    .join(", ");
  const label = dataFreshnessStatusLabel(freshness);
  return sourceText ? `${label}: ${sourceText}` : label;
}

const VALID_SOLVE_STEP_STATUSES = new Set<ActionCenterSolveStepStatus>([
  "ready",
  "available",
  "blocked",
  "waiting_for_data",
  "done",
]);

const CORE_SOLVE_MAP_CODES = new Set([
  "missing_cost_blocks_profit",
  "negative_unit_profit",
  "overstock_slow_moving",
  "low_stock_risk",
  "ads_spend_without_profit",
  "card_quality_issue",
]);

function normalizeSolveStepStatus(value: unknown): ActionCenterSolveStepStatus {
  const status = normalizeText(value).replaceAll("-", "_");
  return VALID_SOLVE_STEP_STATUSES.has(status as ActionCenterSolveStepStatus)
    ? (status as ActionCenterSolveStepStatus)
    : "available";
}

function solveMapHrefForAction(
  code: ActionCenterAllowedActionCode | null,
  nmId: number | null,
  problemInstanceId: number | null,
): string | null {
  return actionCenterWorkScreenHref(code, {
    problem_instance_id: problemInstanceId,
    nm_id: nmId,
  });
}

function solveMapActionReason(
  code: ActionCenterAllowedActionCode | null,
  allowedActionItems: ActionCenterAllowedActionItem[],
  freshness: ActionCenterDataFreshness,
  priceSafety: PriceSafetyContract | null,
  priceSafetyRequired = false,
): string | null {
  if (priceSafetyRequired) {
    const safety = compactRecord(priceSafety);
    const missing = Array.isArray(safety.missing_required_metrics)
      ? safety.missing_required_metrics
      : [];
    const status = normalizeText(safety.status);
    if (
      !hasKeys(safety) ||
      missing.length > 0 ||
      ["data_incomplete", "not_enough_data", "missing"].includes(status) ||
      safety.can_recommend_price_decrease === false
    ) {
      return "Не хватает данных для безопасной цены или промо.";
    }
  }
  if (!code) return null;
  const item = allowedActionItems.find((candidate) => candidate.code === code);
  if (item?.disabled_reason) return item.disabled_reason;
  if (!item && code !== "recheck")
    return "Действие не разрешено текущим правилом.";
  if (
    ["open_price_review", "open_promo_planner", "open_ads_dashboard"].includes(
      code,
    ) &&
    dataFreshnessBlocksAction(freshness)
  ) {
    return dataFreshnessStatusLabel(freshness);
  }
  return null;
}

function solveMapStepFromSpec({
  stepId,
  order,
  title,
  description,
  actionCode,
  nmId,
  requiredMetrics = [],
  completionSignal,
  allowedActionItems,
  freshness,
  priceSafety,
  problemInstanceId,
  priceSafetyRequired = false,
  forceStatus,
}: {
  stepId: string;
  order: number;
  title: string;
  description: string;
  actionCode?: ActionCenterAllowedActionCode | null;
  nmId: number | null;
  requiredMetrics?: string[];
  completionSignal?: string | null;
  allowedActionItems: ActionCenterAllowedActionItem[];
  freshness: ActionCenterDataFreshness;
  priceSafety: PriceSafetyContract | null;
  problemInstanceId: number | null;
  priceSafetyRequired?: boolean;
  forceStatus?: ActionCenterSolveStepStatus;
}): ActionCenterSolveMapStep {
  const blockingReason = solveMapActionReason(
    actionCode ?? null,
    allowedActionItems,
    freshness,
    priceSafety,
    priceSafetyRequired,
  );
  const status =
    forceStatus ??
    (blockingReason === dataFreshnessStatusLabel(freshness)
      ? "waiting_for_data"
      : blockingReason
        ? "blocked"
        : actionCode
          ? "available"
          : "ready");
  return {
    step_id: stepId,
    order,
    title,
    description,
    status,
    action_code: actionCode ?? null,
    target_href: solveMapHrefForAction(
      actionCode ?? null,
      nmId,
      problemInstanceId,
    ),
    required_metrics: requiredMetrics,
    blocking_reason: blockingReason,
    completion_signal: completionSignal ?? null,
  };
}

function buildSolveMapFromProblemCode(
  problemCode: string | null,
  allowedActionItems: ActionCenterAllowedActionItem[],
  freshness: ActionCenterDataFreshness,
  priceSafety: PriceSafetyContract | null,
  nmId: number | null,
  problemInstanceId: number | null,
): ActionCenterSolveMap | null {
  const code = normalizeText(problemCode);
  if (!CORE_SOLVE_MAP_CODES.has(code)) return null;
  const waitingForData = dataFreshnessBlocksAction(freshness);
  const evidenceStatus: ActionCenterSolveStepStatus = waitingForData
    ? "waiting_for_data"
    : "ready";
  const specs: Record<
    string,
    {
      title: string;
      summary: string;
      metrics: string[];
      steps: Array<{
        stepId: string;
        title: string;
        description: string;
        actionCode?: ActionCenterAllowedActionCode | null;
        metrics?: string[];
        completionSignal?: string;
        priceSafetyRequired?: boolean;
      }>;
    }
  > = {
    missing_cost_blocks_profit: {
      title: "Карта решения: себестоимость",
      summary:
        "Откройте исправление данных, загрузите или сопоставьте себестоимость и перепроверьте прибыльность.",
      metrics: ["cost_price", "manual_cost"],
      steps: [
        {
          stepId: "open_data_fix",
          title: "Открыть исправление данных",
          description: "Перейдите к строкам, где не хватает себестоимости.",
          actionCode: "open_data_fix",
          metrics: ["cost_price"],
          completionSignal: "Строка с товаром открыта в исправлении данных.",
        },
        {
          stepId: "upload_cost",
          title: "Загрузить или сопоставить себестоимость",
          description:
            "Загрузите стоимость или сопоставьте SKU, если стоимость есть в другом справочнике.",
          actionCode: "upload_cost",
          metrics: ["cost_price", "sku_mapping"],
          completionSignal: "Стоимость заполнена или SKU сопоставлен.",
        },
        {
          stepId: "recheck_profit",
          title: "Перепроверить прибыльность",
          description:
            "Запустите повторную проверку после загрузки себестоимости.",
          actionCode: "recheck",
          metrics: ["unit_profit", "cost_price"],
          completionSignal: "Прибыльность рассчитана с себестоимостью.",
        },
      ],
    },
    negative_unit_profit: {
      title: "Карта решения: отрицательная маржа",
      summary:
        "Разберите цену, себестоимость, рекламу и промо, затем откройте пересмотр цены и перепроверьте маржу.",
      metrics: [
        "unit_profit",
        "price",
        "cost_price",
        "ads_spend",
        "promo_spend",
      ],
      steps: [
        {
          stepId: "breakdown",
          title: "Проверить разбор цены, себестоимости, рекламы и промо",
          description: "Сверьте, какая часть делает маржу отрицательной.",
          metrics: [
            "unit_profit",
            "price",
            "cost_price",
            "ads_spend",
            "promo_spend",
          ],
          completionSignal: "Причина отрицательной маржи понятна.",
        },
        {
          stepId: "price_review",
          title: "Открыть пересмотр цены",
          description: "Проверьте цену и безопасную маржу перед изменениями.",
          actionCode: "open_price_review",
          metrics: ["price", "cost_price", "margin_pct"],
          completionSignal: "Цена или план исправления маржи выбран.",
        },
        {
          stepId: "recheck_margin",
          title: "Перепроверить маржу",
          description:
            "Повторите проверку после изменения цены, затрат, рекламы или промо.",
          actionCode: "recheck",
          metrics: ["unit_profit", "margin_pct"],
          completionSignal: "Маржа пересчитана после действия.",
        },
      ],
    },
    overstock_slow_moving: {
      title: "Карта решения: медленный остаток",
      summary:
        "Проверьте безопасность цены, затем используйте промо/цену при подтверждённой марже или улучшите карточку через проверку.",
      metrics: [
        "stock_qty",
        "days_of_stock",
        "sales_velocity",
        "cost_price",
        "min_margin",
      ],
      steps: [
        {
          stepId: "price_safety",
          title: "Проверить безопасность цены и промо",
          description:
            "Убедитесь, что снижение цены или промо не уводит товар в минус.",
          metrics: ["cost_price", "min_margin", "price"],
          completionSignal: "Безопасность цены понятна.",
          priceSafetyRequired: true,
        },
        {
          stepId: "promo_or_price",
          title: "Открыть план промо или цены",
          description:
            "Если маржа безопасна, спланируйте промо или пересмотр цены для ускорения продаж.",
          actionCode: "open_promo_planner",
          metrics: ["cost_price", "min_margin", "sales_velocity"],
          completionSignal: "Промо или цена запланированы безопасно.",
          priceSafetyRequired: true,
        },
        {
          stepId: "checker_review",
          title: "Запустить проверку карточки",
          description:
            "Если цена небезопасна, проверьте контент карточки как альтернативный путь ускорения продаж.",
          actionCode: "run_checker",
          metrics: ["card_quality_score", "sales_velocity"],
          completionSignal: "Карточка проверена и улучшения зафиксированы.",
        },
        {
          stepId: "recheck_stock",
          title: "Перепроверить дни остатка и скорость продаж",
          description:
            "После действия проверьте, меняются ли дни остатка и скорость продаж.",
          actionCode: "recheck",
          metrics: ["days_of_stock", "sales_velocity"],
          completionSignal: "Скорость продаж и дни остатка пересчитаны.",
        },
      ],
    },
    low_stock_risk: {
      title: "Карта решения: риск низкого остатка",
      summary:
        "Проверьте запас, откройте план поставки, назначьте владельца и срок или снизьте промо/рекламу, затем перепроверьте дни остатка.",
      metrics: ["stock_qty", "days_of_stock", "orders_7d", "sales_velocity"],
      steps: [
        {
          stepId: "supply_plan",
          title: "Открыть поставки",
          description:
            "Перейдите в план поставок и создайте пополнение, владельца или срок.",
          actionCode: "open_supply_planner",
          metrics: ["stock_qty", "days_of_stock", "orders_7d"],
          completionSignal: "План пополнения, владелец или срок зафиксированы.",
        },
        {
          stepId: "demand_control",
          title: "Снизить промо или рекламу",
          description:
            "Если поставка не успевает, уменьшите стимулы спроса до восстановления остатка.",
          actionCode: "open_promo_planner",
          metrics: ["days_of_stock", "promo_calendar"],
          completionSignal:
            "Спрос временно ограничен или причина передана владельцу.",
        },
        {
          stepId: "recheck_stock_days",
          title: "Перепроверить дни остатка",
          description:
            "Повторите проверку после обновления остатков, заказов или плана поставки.",
          actionCode: "recheck",
          metrics: ["days_of_stock", "stock_qty"],
          completionSignal: "Дни остатка пересчитаны.",
        },
      ],
    },
    ads_spend_without_profit: {
      title: "Карта решения: реклама без прибыли",
      summary:
        "Откройте рекламу, снизьте или поставьте кампанию на паузу либо улучшите карточку, затем перепроверьте прибыль после рекламы.",
      metrics: ["ad_spend", "unit_profit_after_ads", "orders_7d", "cost_price"],
      steps: [
        {
          stepId: "ads_dashboard",
          title: "Открыть рекламный кабинет",
          description: "Найдите кампанию, которая тратит бюджет без прибыли.",
          actionCode: "open_ads_dashboard",
          metrics: ["ad_spend", "unit_profit_after_ads"],
          completionSignal: "Ставка, бюджет или статус кампании изменены.",
        },
        {
          stepId: "checker_review",
          title: "Запустить проверку карточки",
          description:
            "Если реклама не конвертирует, проверьте карточку и исправьте контент.",
          actionCode: "run_checker",
          metrics: ["card_quality_score", "conversion_rate"],
          completionSignal: "Карточка проверена или улучшения созданы.",
        },
        {
          stepId: "recheck_ads_profit",
          title: "Перепроверить прибыль после рекламы",
          description:
            "Повторите проверку после новых данных по рекламе, заказам и себестоимости.",
          actionCode: "recheck",
          metrics: ["unit_profit_after_ads", "ad_spend"],
          completionSignal: "Прибыль после рекламы пересчитана.",
        },
      ],
    },
    card_quality_issue: {
      title: "Карта решения: качество карточки",
      summary:
        "Откройте проверку карточки, посмотрите diff, примените локальную правку или отправьте в WB с подтверждением и перепроверьте качество.",
      metrics: [
        "card_quality_score",
        "photos",
        "description",
        "characteristics",
      ],
      steps: [
        {
          stepId: "checker",
          title: "Открыть проверку карточки",
          description:
            "Перейдите в карточку проверки и посмотрите найденные проблемы.",
          actionCode: "run_checker",
          metrics: ["card_quality_score"],
          completionSignal: "Проверка карточки открыта.",
        },
        {
          stepId: "preview_diff",
          title: "Посмотреть diff перед применением",
          description:
            "Сравните текущую карточку и предлагаемую правку перед записью.",
          metrics: ["card_quality_score"],
          completionSignal: "Diff просмотрен.",
        },
        {
          stepId: "apply_or_local_fix",
          title: "Сохранить локально или отправить в WB с подтверждением",
          description:
            "Сначала сохраните локальную правку; запись в WB требует предпросмотра и подтверждения.",
          actionCode: "run_checker",
          metrics: ["wb_content_diff"],
          completionSignal:
            "Правка сохранена локально или отправлена в WB после подтверждения.",
        },
        {
          stepId: "recheck_card",
          title: "Перепроверить качество карточки",
          description:
            "Повторите проверку после локальной правки или ответа WB.",
          actionCode: "recheck",
          metrics: ["card_quality_score"],
          completionSignal: "Качество карточки пересчитано.",
        },
      ],
    },
  };
  const spec = specs[code];
  return {
    title: spec.title,
    summary: spec.summary,
    steps: [
      solveMapStepFromSpec({
        stepId: "evidence",
        order: 1,
        title: "Проверить доказательства",
        description:
          "Откройте «Как посчитано?» и проверьте формулу, факты, источники и свежесть данных.",
        requiredMetrics: spec.metrics,
        completionSignal: "Доказательства и источники понятны.",
        allowedActionItems,
        freshness,
        priceSafety,
        problemInstanceId,
        forceStatus: evidenceStatus,
        nmId,
      }),
      ...spec.steps.map((step, index) => {
        let actionCode = step.actionCode ?? null;
        const allowedCodes = new Set(
          allowedActionItems.map((item) => item.code),
        );
        if (
          code === "low_stock_risk" &&
          step.stepId === "demand_control" &&
          !allowedCodes.has("open_promo_planner") &&
          allowedCodes.has("open_ads_dashboard")
        ) {
          actionCode = "open_ads_dashboard";
        }
        if (
          code === "overstock_slow_moving" &&
          step.stepId === "promo_or_price" &&
          !allowedCodes.has("open_promo_planner") &&
          allowedCodes.has("open_price_review")
        ) {
          actionCode = "open_price_review";
        }
        return solveMapStepFromSpec({
          stepId: step.stepId,
          order: index + 2,
          title: step.title,
          description: step.description,
          actionCode,
          requiredMetrics: step.metrics ?? [],
          completionSignal: step.completionSignal ?? null,
          allowedActionItems,
          freshness,
          priceSafety,
          problemInstanceId,
          priceSafetyRequired: step.priceSafetyRequired === true,
          nmId,
        });
      }),
    ],
  };
}

function solveMapFromUnknown(
  value: unknown,
  allowedActionItems: ActionCenterAllowedActionItem[],
  freshness: ActionCenterDataFreshness,
  priceSafety: PriceSafetyContract | null,
  nmId: number | null,
  problemInstanceId: number | null,
): ActionCenterSolveMap | null {
  const record = compactRecord(value);
  const rawSteps = Array.isArray(record.steps) ? record.steps : [];
  const steps = rawSteps
    .map((item, index) => {
      const step = compactRecord(item);
      const actionCode = canonicalActionCode(step.action_code);
      const blockingReason = firstText(step.blocking_reason);
      const computedHref = solveMapHrefForAction(
        actionCode,
        nmId,
        problemInstanceId,
      );
      const explicitHref = firstText(step.target_href);
      const targetHref =
        actionCode && problemInstanceId != null
          ? (computedHref ?? explicitHref)
          : (explicitHref ?? computedHref);
      const title = firstText(step.title);
      if (!title) return null;
      return {
        step_id:
          firstText(step.step_id, `step_${index + 1}`) ?? `step_${index + 1}`,
        order: firstNumber(step.order) ?? index + 1,
        title,
        description: firstText(step.description) ?? "",
        status: normalizeSolveStepStatus(step.status),
        action_code: actionCode,
        target_href: targetHref,
        required_metrics: listFromUnknown(step.required_metrics),
        blocking_reason: blockingReason,
        completion_signal: firstText(step.completion_signal),
      } satisfies ActionCenterSolveMapStep;
    })
    .filter(Boolean) as ActionCenterSolveMapStep[];
  if (!steps.length) return null;
  const freshnessBlocked = dataFreshnessBlocksAction(freshness);
  const freshnessReason = dataFreshnessStatusLabel(freshness);
  return {
    title: firstText(record.title) ?? "Карта решения",
    summary: firstText(record.summary) ?? "",
    steps: steps
      .map((step) => {
        if (step.step_id === "evidence") {
          if (!freshnessBlocked)
            return step.status === "waiting_for_data"
              ? { ...step, status: "ready", blocking_reason: null }
              : step;
          return {
            ...step,
            status: "waiting_for_data",
            blocking_reason: step.blocking_reason ?? freshnessReason,
          };
        }
        if (!step.action_code) return step;
        const item = allowedActionItems.find(
          (candidate) => candidate.code === step.action_code,
        );
        if (!item?.disabled_reason && step.blocking_reason) return step;
        const inferredReason = solveMapActionReason(
          step.action_code,
          allowedActionItems,
          freshness,
          priceSafety,
          false,
        );
        if (!inferredReason) return step;
        return {
          ...step,
          status:
            inferredReason === dataFreshnessStatusLabel(freshness)
              ? "waiting_for_data"
              : "blocked",
          blocking_reason: inferredReason,
        };
      })
      .sort((a, b) => a.order - b.order),
  };
}

function hasMissingCostSignal(
  payload: JsonRecord,
  raw: JsonRecord,
  ledger: EvidenceLedger | null,
  priceSafety: PriceSafetyContract | null,
): boolean {
  const values = [
    ...listFromUnknown(priceSafety?.missing_required_metrics),
    ...listFromUnknown(ledger?.missing_data),
    ...listFromUnknown(ledger?.calculation_warnings),
    ...listFromUnknown(payload.missing_data),
    ...listFromUnknown(raw.missing_data),
    ...listFromUnknown(payload.missing_metrics),
    ...listFromUnknown(raw.missing_metrics),
  ];
  return values.some((value) => {
    const normalized = normalizeText(value);
    return (
      normalized.includes("cost_price") ||
      normalized.includes("unit_cost") ||
      normalized.includes("manual_cost") ||
      normalized.includes("себестоим")
    );
  });
}

function actionNeedsPriceSafety(
  code: ActionCenterAllowedActionCode,
  original: string,
  action: PortalAction,
  payload: JsonRecord,
  raw: JsonRecord,
): boolean {
  if (!PRICE_SAFETY_ACTIONS.has(code)) return false;
  const adapted = action as PortalActionAdapterFields;
  const problemCode = normalizeText(
    adapted.problem_code ??
      payload.problem_code ??
      raw.problem_code ??
      action.detector_code ??
      action.action_type,
  );
  return (
    PRICE_SAFETY_PROBLEM_CODES.has(problemCode) ||
    [
      "safe_promo",
      "review_promo",
      "reduce_promo",
      "review_price",
      "pricing_review",
    ].includes(original)
  );
}

function priceSafetyDisabledReason(
  code: ActionCenterAllowedActionCode,
  original: string,
  action: PortalAction,
  payload: JsonRecord,
  raw: JsonRecord,
  ledger: EvidenceLedger | null,
): string | null {
  if (!actionNeedsPriceSafety(code, original, action, payload, raw))
    return null;
  const safety = priceSafetyRecord(payload, raw, ledger);
  if (!hasKeys(safety)) return "Не хватает данных";
  const missing = safety.missing_required_metrics;
  if (Array.isArray(missing) && missing.length > 0) return "Не хватает данных";
  const status = normalizeText(safety.status);
  if (status === "data_incomplete" || status === "not_enough_data") {
    return "Не хватает данных";
  }
  const adapted = action as PortalActionAdapterFields;
  const problemCode = normalizeText(
    adapted.problem_code ??
      payload.problem_code ??
      raw.problem_code ??
      action.detector_code ??
      action.action_type,
  );
  const priceDecreaseProblem =
    problemCode === "overstock_slow_moving" ||
    problemCode === "dead_stock" ||
    problemCode === "promo_not_profitable";
  if (
    (code === "open_promo_planner" || priceDecreaseProblem) &&
    safety.can_recommend_price_decrease !== true
  ) {
    return "Не хватает данных";
  }
  return null;
}

function freshnessDisabledReason(
  code: ActionCenterAllowedActionCode,
  original: string,
  freshness: ActionCenterDataFreshness,
): string | null {
  if (!dataFreshnessBlocksAction(freshness)) return null;
  if (
    FRESHNESS_SENSITIVE_ACTIONS.has(code) ||
    DANGEROUS_WRITE_ACTIONS.has(original)
  ) {
    return dataFreshnessStatusLabel(freshness);
  }
  return null;
}

export function actionCenterImpactBucketForItem(
  item: Pick<ActionCenterItem, "impact_type" | "trust_state" | "money_trust">,
): ActionCenterImpactBucketKey | null {
  const kind = normalizeText(item.money_trust?.impact_kind ?? item.impact_type);
  const trust = normalizeText(item.money_trust?.state ?? item.trust_state);
  if (kind === "confirmed_loss") {
    return item.money_trust?.show_as_confirmed_money === true
      ? "confirmed_loss"
      : "probable_risk";
  }
  if (kind === "blocked_cash" || kind === "blocked_revenue")
    return "blocked_cash";
  if (
    kind === "opportunity" ||
    kind === "estimated_opportunity" ||
    trust === "opportunity"
  ) {
    return "opportunity";
  }
  if (
    kind === "data_blocker" ||
    kind === "data_blocked" ||
    kind === "system_warning" ||
    kind === "test_only" ||
    trust === "blocked" ||
    trust === "test_only"
  ) {
    return "data_blocker";
  }
  if (kind === "informational" && trust === "confirmed") return null;
  return "probable_risk";
}

function boolFromAny(...values: unknown[]): boolean {
  return values.some(
    (value) => value === true || normalizeText(value) === "true",
  );
}

function actionItemsFrom(
  pairs: Array<{ code: ActionCenterAllowedActionCode; original: string }>,
  action: PortalAction,
  payload: JsonRecord,
  raw: JsonRecord,
  ledger: EvidenceLedger | null,
  freshness: ActionCenterDataFreshness,
  evidenceState: ActionCenterEvidenceState,
  canUpdate: boolean,
): ActionCenterAllowedActionItem[] {
  return pairs.map(({ code, original }) => {
    const dangerous = DANGEROUS_WRITE_ACTIONS.has(original);
    const requiresPreview = boolFromAny(
      payload.requires_preview,
      raw.requires_preview,
      payload.preview_required,
      raw.preview_required,
      dangerous,
    );
    const requiresDiff = boolFromAny(
      payload.requires_diff,
      raw.requires_diff,
      payload.diff_required,
      raw.diff_required,
      dangerous,
    );
    const requiresConfirm = boolFromAny(
      payload.requires_confirm,
      raw.requires_confirm,
      payload.requires_confirmation,
      raw.requires_confirmation,
      payload.confirm_required,
      raw.confirm_required,
      dangerous,
    );
    const requiresAudit = boolFromAny(
      payload.requires_audit,
      raw.requires_audit,
      payload.audit_required,
      raw.audit_required,
      dangerous,
    );
    const disabledReason =
      lookupActionReason(code, original, payload, raw) ??
      freshnessDisabledReason(code, original, freshness) ??
      priceSafetyDisabledReason(code, original, action, payload, raw, ledger) ??
      (evidenceState === "missing_evidence" &&
      !SAFE_WITH_MISSING_EVIDENCE_ACTIONS.has(code)
        ? "Не хватает данных"
        : null) ??
      (!canUpdate && !["recheck", "open_results", "open_product"].includes(code)
        ? "Действие доступно только администратору"
        : null);
    return {
      code,
      original_code: original || code,
      enabled: !disabledReason,
      disabled_reason: disabledReason,
      requires_preview: requiresPreview,
      requires_diff: requiresDiff,
      requires_confirm: requiresConfirm,
      requires_audit: requiresAudit,
      is_dangerous: dangerous,
    };
  });
}

function isSyntheticEvidenceFallback(ledger: EvidenceLedger | null): boolean {
  if (!ledger) return false;
  const formulaCode = normalizeText(ledger.formula_code);
  return (
    ledger.is_synthetic === true || formulaCode.startsWith("portal_action.")
  );
}

function evidenceHasFacts(ledger: EvidenceLedger | null): boolean {
  return Array.isArray(ledger?.input_facts) && ledger.input_facts.length > 0;
}

function evidenceHasFormula(ledger: EvidenceLedger | null): boolean {
  return Boolean(
    firstText(ledger?.formula_human, ledger?.formula_code, ledger?.formula_id),
  );
}

function evidenceStateWithFreshness(
  state: ActionCenterEvidenceState,
  freshness: ActionCenterDataFreshness,
): ActionCenterEvidenceState {
  if (!dataFreshnessBlocksAction(freshness)) return state;
  if (state === "read_only_signal") return state;
  if (
    freshness.source_status === "missing" ||
    freshness.source_status === "not_configured"
  ) {
    return "missing_evidence";
  }
  return state === "full_evidence" ? "partial_evidence" : state;
}

function moneyTrustWithFreshness(
  trust: MoneyTrustInfo,
  freshness: ActionCenterDataFreshness,
): MoneyTrustInfo {
  if (!dataFreshnessBlocksAction(freshness)) return trust;
  const blocked =
    freshness.source_status === "missing" ||
    freshness.source_status === "not_configured";
  const nextTrust = blocked ? "blocked" : "provisional";
  const confirmedImpact = normalizeText(trust.impact_kind) === "confirmed_loss";
  return {
    ...trust,
    state:
      normalizeText(trust.state) === "confirmed" || blocked
        ? nextTrust
        : trust.state,
    impact_kind: confirmedImpact ? "probable_risk" : trust.impact_kind,
    display_label: confirmedImpact
      ? "Данные предварительные"
      : trust.display_label,
    amount_label: confirmedImpact ? "Вероятный риск" : trust.amount_label,
    show_as_confirmed_money: false,
    reason:
      trust.reason ||
      "Источник требует синхронизации, поэтому денежное влияние предварительное.",
    evidence_trust_state: blocked ? "blocked" : "provisional",
    impact_trust_state: nextTrust,
    saved_money_claimed: false,
  };
}

function evidenceHasSourceDetails(ledger: EvidenceLedger | null): boolean {
  if (!ledger) return false;
  const refs = Array.isArray(ledger.source_references)
    ? ledger.source_references
    : [];
  if (
    refs.some((ref) =>
      Boolean(
        firstText(
          ref.source_table,
          ref.table,
          ref.source_endpoint,
          ref.wb_endpoint,
          ref.loaded_at,
        ) ??
        firstNumber(ref.row_count) ??
        firstText(
          ref.date_range?.from,
          ref.date_range?.to,
          ref.date_range?.start,
          ref.date_range?.end,
        ),
      ),
    )
  ) {
    return true;
  }
  const facts = Array.isArray(ledger.input_facts) ? ledger.input_facts : [];
  return facts.some((fact) =>
    Boolean(
      firstText(
        fact.source,
        fact.source_table,
        fact.source_endpoint,
        fact.date_range?.from,
        fact.date_range?.to,
        fact.date_range?.start,
        fact.date_range?.end,
      ) ?? firstNumber(fact.row_count),
    ),
  );
}

function missingEvidenceActionIsSafe(
  sourceKind: ActionCenterSourceKind,
  allowedActions: PortalAllowedActionCode[] | ActionCenterAllowedActionCode[],
): boolean {
  if (sourceKind === "manual") return true;
  if (!allowedActions.length) return false;
  return allowedActions.every((action) =>
    SAFE_WITH_MISSING_EVIDENCE_ACTIONS.has(normalizeText(action)),
  );
}

function deriveEvidenceState(
  action: PortalAction,
  payload: JsonRecord,
  raw: JsonRecord,
  ledger: EvidenceLedger | null,
  sourceKind: ActionCenterSourceKind,
  canUpdate: boolean,
): ActionCenterEvidenceState {
  const backendState = normalizeEvidenceState(
    (action as { evidence_state?: PortalActionEvidenceState | null })
      .evidence_state,
  );
  if (backendState) return backendState;
  const payloadState = normalizeEvidenceState(payload.evidence_state);
  if (payloadState) return payloadState;
  const rawState = normalizeEvidenceState(raw.evidence_state);
  if (rawState) return rawState;

  if (!ledger) {
    return canUpdate ? "missing_evidence" : "read_only_signal";
  }
  const synthetic = isSyntheticEvidenceFallback(ledger);
  const hasFormula = evidenceHasFormula(ledger);
  const hasFacts = evidenceHasFacts(ledger);
  const hasSource = evidenceHasSourceDetails(ledger);
  const hasMissing =
    Array.isArray(ledger.missing_data) && ledger.missing_data.length > 0;
  const hasWarnings =
    Array.isArray(ledger.calculation_warnings) &&
    ledger.calculation_warnings.length > 0;

  if (!canUpdate && (sourceKind === "beta" || synthetic)) {
    return "read_only_signal";
  }
  if (!hasFormula && !hasFacts && !hasSource) {
    return canUpdate ? "missing_evidence" : "read_only_signal";
  }
  if (
    synthetic ||
    !hasFormula ||
    !hasFacts ||
    !hasSource ||
    hasMissing ||
    hasWarnings
  ) {
    return "partial_evidence";
  }
  return "full_evidence";
}

function sourceKindFrom(
  action: PortalAction,
  payload: JsonRecord,
  raw: JsonRecord,
): ActionCenterSourceKind {
  const module = normalizeText(action.source_module);
  const adapted = action as PortalActionAdapterFields;
  const problemInstanceId =
    adapted.problem_instance_id ??
    payload.problem_instance_id ??
    raw.problem_instance_id;
  if (module === "problem_engine" || problemInstanceId != null) {
    return "problem_engine";
  }
  if (module === "checker") return "checker";
  if (module === "finance") return "finance";
  if (module === "data_quality") return "data_quality";
  if (module === "costs") return "costs";
  if (module === "manual") return "manual";
  if (BETA_SOURCE_MODULES.has(module) || payload.beta === true) return "beta";
  return "legacy";
}

function problemInstanceIdFrom(
  action: PortalAction,
  payload: JsonRecord,
  raw: JsonRecord,
): number | null {
  const adapted = action as PortalActionAdapterFields;
  const sourceTail = String(action.source_id ?? "")
    .split(":")
    .pop();
  const value = firstNumber(
    adapted.problem_instance_id,
    payload.problem_instance_id,
    raw.problem_instance_id,
    sourceTail,
  );
  return value != null && value > 0 ? value : null;
}

function isCheckerProblemBridge(
  action: PortalAction,
  payload: JsonRecord,
): boolean {
  return (
    action.source_module === "checker" &&
    (payload.checker_problem_bridge === true ||
      payload.problem_ux_contract === true ||
      payload.content_quality_signal === true ||
      normalizeText(action.action_type) === "card_quality_fix")
  );
}

function isClaimsAction(action: PortalAction, payload: JsonRecord): boolean {
  if (action.source_module === "claims") return true;
  if (action.guided_fix?.route_key === "claims") return true;
  const type = normalizeText(action.action_type);
  const payloadType = normalizeText(payload.action_type ?? payload.code);
  return (
    type.includes("claim") ||
    payloadType.includes("claim") ||
    type === "create_claim_case"
  );
}

function embeddedResultSummary(
  payload: JsonRecord,
  raw: JsonRecord,
): JsonRecord {
  return compactRecord(payload.result_summary ?? raw.result_summary);
}

function canonicalResultSummary(
  resultPage?: PortalResultEventsPage | null,
): ProblemResultSummary | null {
  if (!resultPage) return null;
  const summary = problemResultSummaryFromPage(resultPage);
  return summary.events.length > 0 || hasKeys(resultPage.summary)
    ? summary
    : null;
}

function historyItemsFrom(
  summary: unknown,
  payload: JsonRecord,
  raw: JsonRecord,
): ActionCenterHistoryItem[] {
  const source =
    compactRecord(summary).status_history ??
    payload.status_history ??
    payload.history ??
    raw.status_history ??
    raw.history ??
    [];
  if (!Array.isArray(source)) return [];
  return source
    .map((item) => {
      const record = compactRecord(item);
      if (!hasKeys(record)) return null;
      return {
        event_type: firstText(record.event_type, record.type),
        old_status: firstText(record.old_status),
        new_status: firstText(record.new_status),
        status: firstText(record.status),
        comment: firstText(record.comment, record.message),
        created_at: firstText(record.created_at, record.at, record.ts),
        created_by: firstNumber(record.created_by, record.user_id),
      };
    })
    .filter(Boolean) as ActionCenterHistoryItem[];
}

function historySummaryFrom(
  items: ActionCenterHistoryItem[],
): ActionCenterHistorySummary {
  const latest = items
    .slice()
    .reverse()
    .find((item) => item.created_at || item.new_status || item.status);
  const latestStatus =
    latest?.new_status ?? latest?.status ?? latest?.event_type;
  return {
    total: items.length,
    latest_label: latestStatus ? problemStatusLabel(latestStatus) : null,
    latest_at: latest?.created_at ?? null,
    items,
  };
}

function resultStatusFrom(
  canonical: ProblemResultSummary | null,
  embedded: JsonRecord,
): ProblemResultStatus {
  if (canonical) return canonical.status;
  return problemResultStatusFromSummary(embedded);
}

function userNameFrom(
  userId: number | null,
  users?: AssignableUserLike[] | null,
): string | null {
  if (userId == null || !users?.length) return null;
  const user = users.find((item) => item.id === userId);
  if (!user) return null;
  return (
    user.display_name ||
    user.full_name ||
    user.email ||
    `Пользователь ${user.id}`
  );
}

function nowFromOptions(value: Date | string | null | undefined): Date {
  if (value instanceof Date) return value;
  if (typeof value === "string" && value.trim()) {
    const parsed = new Date(value);
    if (!Number.isNaN(parsed.getTime())) return parsed;
  }
  return new Date();
}

function slaFromDeadline(
  deadlineAt: string | null,
  status: string,
  action: PortalAction,
  payload: JsonRecord,
  raw: JsonRecord,
  now: Date,
): {
  is_overdue: boolean;
  due_in_hours: number | null;
  sla_state: "ok" | "due_soon" | "overdue" | "no_deadline";
} {
  const adapted = action as PortalActionAdapterFields;
  const backendState = firstText(
    adapted.sla_state,
    payload.sla_state,
    raw.sla_state,
  );
  const backendDue = firstNumber(
    adapted.due_in_hours,
    payload.due_in_hours,
    raw.due_in_hours,
  );
  const backendOverdue =
    adapted.is_overdue ?? payload.is_overdue ?? raw.is_overdue;
  if (
    backendState &&
    ["ok", "due_soon", "overdue", "no_deadline"].includes(backendState)
  ) {
    return {
      is_overdue:
        typeof backendOverdue === "boolean"
          ? backendOverdue
          : backendState === "overdue",
      due_in_hours: backendDue,
      sla_state: backendState as "ok" | "due_soon" | "overdue" | "no_deadline",
    };
  }
  if (!deadlineAt) {
    return { is_overdue: false, due_in_hours: null, sla_state: "no_deadline" };
  }
  const deadline = new Date(deadlineAt);
  if (Number.isNaN(deadline.getTime())) {
    return { is_overdue: false, due_in_hours: null, sla_state: "no_deadline" };
  }
  const dueInHours = (deadline.getTime() - now.getTime()) / 3_600_000;
  const closed = [
    "done",
    "resolved",
    "closed",
    "ignored",
    "dismissed",
    "rejected",
  ].includes(normalizeText(status));
  const overdue = dueInHours < 0 && !closed;
  return {
    is_overdue: overdue,
    due_in_hours: Math.round(dueInHours * 100) / 100,
    sla_state: overdue
      ? "overdue"
      : closed
        ? "ok"
        : dueInHours <= 24
          ? "due_soon"
          : "ok",
  };
}

export function adaptActionCenterItem(
  action: PortalAction,
  options: AdaptActionCenterOptions = {},
): ActionCenterItem {
  const adapted = action as PortalActionAdapterFields;
  const payload = compactRecord(action.payload);
  const raw = compactRecord(action.raw);
  const linked = compactRecord(action.linked_entity);
  const sourceKind = sourceKindFrom(action, payload, raw);
  const problemLike =
    sourceKind === "problem_engine" || isCheckerProblemBridge(action, payload);
  const problemInstanceId = problemInstanceIdFrom(action, payload, raw);
  const problemCode = normalizedCode(
    adapted.problem_code ??
      payload.problem_code ??
      raw.problem_code ??
      action.detector_code ??
      (sourceKind === "problem_engine" ? action.action_type : null),
  );
  const evidenceLedger = evidenceFrom(
    action.evidence_ledger,
    payload.evidence_ledger,
    raw.evidence_ledger,
    raw.evidence,
  );
  const priceSafety = priceSafetyContractFrom(payload, raw, evidenceLedger);
  const dataFreshness = sourceFreshnessFrom(
    action,
    payload,
    raw,
    evidenceLedger,
    problemCode,
    priceSafety,
  );
  let moneyTrust = moneyTrustFrom(
    action.money_trust,
    payload.money_trust,
    evidenceLedger?.money_trust,
  );
  const rawAllowedActions = allowedActionsFrom(
    action.allowed_actions,
    payload.allowed_actions,
    raw.allowed_actions,
  );
  const allowedActionPairs = canonicalAllowedActionsFrom(
    rawAllowedActions,
    action,
  );
  const allowedActions = allowedActionPairs.map((item) => item.code);
  const actionId = firstNumber(action.action_id, action.id);
  const hasUpdateTarget =
    (!!action.source_module && action.source_id != null) || actionId != null;
  const updateFlag = action.can_update ?? action.can_update_status;
  const baseCanUpdate =
    hasUpdateTarget && (updateFlag === undefined ? true : updateFlag === true);
  const evidenceState = evidenceStateWithFreshness(
    deriveEvidenceState(
      action,
      payload,
      raw,
      evidenceLedger,
      sourceKind,
      baseCanUpdate,
    ),
    dataFreshness,
  );
  const evidenceBlocksAction =
    evidenceState === "missing_evidence" &&
    baseCanUpdate &&
    !missingEvidenceActionIsSafe(sourceKind, allowedActions);
  const canUpdate = baseCanUpdate && !evidenceBlocksAction;
  const allowedActionItems = actionItemsFrom(
    allowedActionPairs,
    action,
    payload,
    raw,
    evidenceLedger,
    dataFreshness,
    evidenceState,
    canUpdate,
  );
  const beta =
    sourceKind === "beta" ||
    payload.beta === true ||
    BETA_SOURCE_MODULES.has(normalizeText(action.source_module));
  const testOnly =
    normalizeText(action.status) === "test_only" ||
    normalizeText(action.trust_state ?? payload.trust_state) === "test_only" ||
    moneyTrust.state === "test_only" ||
    payload.test_only === true;
  const embeddedSummary = embeddedResultSummary(payload, raw);
  const canonicalSummary = canonicalResultSummary(options.resultPage);
  const resultEvents = options.resultPage
    ? problemResultEvents(options.resultPage)
    : (canonicalSummary?.events ?? []);
  const resultSummary =
    canonicalSummary ?? (hasKeys(embeddedSummary) ? embeddedSummary : null);
  const historyItems = historyItemsFrom(resultSummary, payload, raw);
  const historySummary = historySummaryFrom(historyItems);
  const assignedToUserId = firstNumber(action.assigned_to_user_id);
  const now = nowFromOptions(options.now);
  let trustState = firstText(
    action.trust_state,
    payload.trust_state,
    raw.trust_state,
    moneyTrust.impact_trust_state,
    moneyTrust.state,
    evidenceLedger?.confidence,
  );
  let impactType = firstText(
    action.impact_type,
    payload.impact_type,
    raw.impact_type,
    evidenceLedger?.impact_type,
    moneyTrust.impact_kind,
  );
  const moneyAmount = firstNumber(
    adapted.money_impact_amount,
    action.expected_impact_amount,
    action.expected_effect_amount,
    payload.money_impact_amount,
    payload.expected_impact_amount,
    payload.expected_effect_amount,
    raw.money_impact_amount,
  );
  const status = (firstText(action.status, payload.status, raw.status) ??
    "new") as PortalActionStatus;
  const deadlineAt = firstText(
    action.deadline_at,
    payload.deadline_at,
    raw.deadline_at,
  );
  const sla = slaFromDeadline(deadlineAt, status, action, payload, raw, now);
  const issueCode = normalizedCode(
    payload.issue_code ??
      payload.dq_code ??
      raw.issue_code ??
      raw.dq_code ??
      payload.code ??
      raw.code,
  );
  const missingCostBlocksNegativeProfit =
    problemCode === "negative_unit_profit" &&
    hasMissingCostSignal(payload, raw, evidenceLedger, priceSafety);
  if (missingCostBlocksNegativeProfit) {
    moneyTrust = {
      ...moneyTrust,
      state: "blocked",
      impact_kind: "data_blocker",
      display_label: "Не хватает данных",
      amount_label: "Не хватает данных",
      show_as_confirmed_money: false,
      reason: "Не хватает себестоимости: прибыль нельзя посчитать надёжно.",
      evidence_trust_state: "blocked",
      impact_trust_state: "blocked",
      saved_money_claimed: false,
    };
  }
  const stockRiskProblem =
    problemCode === "low_stock_risk" || problemCode === "fast_stock_depletion";
  if (
    stockRiskProblem &&
    (normalizeText(impactType) === "confirmed_loss" ||
      normalizeText(moneyTrust.impact_kind) === "confirmed_loss")
  ) {
    impactType = "lost_sales_risk";
    trustState =
      normalizeText(trustState) === "estimated" ? "estimated" : "provisional";
    moneyTrust = {
      ...moneyTrust,
      state: trustState,
      impact_kind: "lost_sales_risk",
      display_label: "Риск потери продаж",
      amount_label: "Риск потери продаж",
      show_as_confirmed_money: false,
      evidence_trust_state:
        moneyTrust.evidence_trust_state ?? evidenceLedger?.confidence ?? null,
      impact_trust_state: trustState,
      saved_money_claimed: false,
    };
  }
  const blockedCashProblem =
    problemCode === "overstock_slow_moving" || problemCode === "dead_stock";
  if (
    blockedCashProblem &&
    ["", "confirmed_loss", "opportunity"].includes(normalizeText(impactType))
  ) {
    impactType = "blocked_cash";
    trustState = "estimated";
    moneyTrust = {
      ...moneyTrust,
      state: "estimated",
      impact_kind: "blocked_cash",
      display_label: "Замороженные деньги",
      amount_label: "Замороженные деньги",
      show_as_confirmed_money: false,
      evidence_trust_state:
        moneyTrust.evidence_trust_state ?? evidenceLedger?.confidence ?? null,
      impact_trust_state: "estimated",
      saved_money_claimed: false,
    };
  }
  moneyTrust = moneyTrustWithFreshness(moneyTrust, dataFreshness);
  if (dataFreshnessBlocksAction(dataFreshness)) {
    const freshnessTrust =
      firstText(moneyTrust.impact_trust_state, moneyTrust.state) ??
      "provisional";
    if (normalizeText(trustState) === "confirmed") {
      trustState = freshnessTrust;
    }
    if (normalizeText(impactType) === "confirmed_loss") {
      impactType = moneyTrust.impact_kind;
    }
  }
  const needsPriceSafety = Boolean(
    (problemCode && PRICE_SAFETY_PROBLEM_CODES.has(problemCode)) ||
    allowedActionPairs.some((item) =>
      actionNeedsPriceSafety(item.code, item.original, action, payload, raw),
    ),
  );
  const detectorCode = normalizedCode(
    action.detector_code ??
      payload.detector_code ??
      raw.detector_code ??
      problemCode,
  );
  const sellerCopyVars = sellerCopyVarsFrom(action, payload, raw, linked);
  const sellerProblemCode = missingCostBlocksNegativeProfit
    ? "missing_cost_blocks_profit"
    : problemCode;
  const rawTitle = firstText(action.title, payload.title, raw.title);
  const title =
    seededProblemSellerTitle(sellerProblemCode, rawTitle, sellerCopyVars) ??
    rawTitle ??
    "Действие";
  const rawShortExplanation =
    firstText(
      action.reason,
      adapted.summary,
      payload.reason,
      payload.summary,
      raw.reason,
      raw.summary,
    ) ?? "";
  const shortExplanation =
    seededProblemSellerWhy(
      sellerProblemCode,
      rawShortExplanation,
      sellerCopyVars,
    ) ?? rawShortExplanation;
  const rawNextStep = firstText(
    action.next_step,
    payload.next_step,
    raw.next_step,
  );
  const nextStep =
    seededProblemSellerNextStep(
      sellerProblemCode,
      rawNextStep,
      sellerCopyVars,
    ) ?? rawNextStep;
  const rawRecheckRule =
    firstText(
      action.recheck_rule,
      evidenceLedger?.recheck_rule_human,
      evidenceLedger?.recheck_rule,
      payload.recheck_rule,
      raw.recheck_rule,
    ) ?? null;
  const recheckRule =
    seededProblemSellerRecheckRule(
      sellerProblemCode,
      rawRecheckRule,
      sellerCopyVars,
    ) ??
    rawRecheckRule ??
    "Обновите Центр действий после изменения статуса или данных источника.";
  const lastStatusChangedAt =
    firstText(
      payload.last_status_changed_at,
      raw.last_status_changed_at,
      historySummary.latest_at,
      action.closed_at,
      action.dismissed_at,
      action.created_at,
    ) ?? null;
  const nmId = firstNumber(
    action.nm_id,
    linked.nm_id,
    payload.nm_id,
    raw.nm_id,
  );
  const solveMap =
    solveMapFromUnknown(
      adapted.solve_map ?? payload.solve_map ?? raw.solve_map,
      allowedActionItems,
      dataFreshness,
      priceSafety,
      nmId,
      problemInstanceId,
    ) ??
    buildSolveMapFromProblemCode(
      sellerProblemCode,
      allowedActionItems,
      dataFreshness,
      priceSafety,
      nmId,
      problemInstanceId,
    );

  return {
    id: String(
      action.id ?? action.external_id ?? action.source_id ?? actionId ?? "",
    ),
    account_id: firstNumber(
      action.account_id,
      payload.account_id,
      raw.account_id,
    ),
    action_id: actionId,
    source: firstText(action.source),
    source_module: action.source_module ?? null,
    source_id: action.source_id == null ? null : String(action.source_id),
    source_kind: sourceKind,
    source_sync_state: action.source_sync_state ?? null,
    action_type:
      firstText(action.action_type, payload.action_type, payload.code) ?? "",
    created_at: firstText(
      action.created_at,
      payload.created_at,
      raw.created_at,
    ),
    last_seen_at: firstText(
      payload.last_seen_at,
      raw.last_seen_at,
      payload.last_seen,
      raw.last_seen,
      action.created_at,
    ),
    entity_type: firstText(
      linked.entity_type,
      payload.entity_type,
      raw.entity_type,
      problemInstanceId != null ? "problem_instance" : null,
    ),
    entity_id: firstId(
      linked.entity_id,
      payload.entity_id,
      raw.entity_id,
      problemInstanceId,
      action.source_id,
    ),
    nm_id: nmId,
    sku_id: firstNumber(
      action.sku_id,
      linked.sku_id,
      payload.sku_id,
      raw.sku_id,
    ),
    vendor_code: firstText(
      action.vendor_code,
      linked.vendor_code,
      payload.vendor_code,
      raw.vendor_code,
    ),
    title,
    short_explanation: shortExplanation,
    reason: shortExplanation,
    summary: firstText(adapted.summary, payload.summary, raw.summary),
    next_step: nextStep,
    severity: firstText(
      action.severity,
      payload.severity,
      raw.severity,
    ) as PortalActionSeverity | null,
    priority: firstText(
      action.priority,
      payload.priority,
      raw.priority,
    ) as PortalActionPriority | null,
    status,
    status_label: problemStatusLabel(status),
    trust_state: missingCostBlocksNegativeProfit ? "blocked" : trustState,
    impact_type: missingCostBlocksNegativeProfit ? "data_blocker" : impactType,
    money_impact_amount: missingCostBlocksNegativeProfit ? null : moneyAmount,
    money_impact_currency: firstText(
      adapted.money_impact_currency,
      payload.money_impact_currency,
      raw.money_impact_currency,
      moneyAmount != null ? "RUB" : null,
    ),
    expected_impact_amount: missingCostBlocksNegativeProfit
      ? null
      : firstNumber(action.expected_impact_amount),
    expected_effect_amount: missingCostBlocksNegativeProfit
      ? null
      : firstNumber(action.expected_effect_amount),
    confidence: firstText(
      action.confidence,
      payload.confidence,
      raw.confidence,
    ),
    problem_code: problemCode,
    detector_code: detectorCode,
    issue_code: issueCode,
    data_freshness: dataFreshness,
    solve_map: solveMap,
    evidence_ledger: evidenceLedger,
    evidence_state: evidenceState,
    money_trust: moneyTrust,
    allowed_actions: allowedActions,
    allowed_action_items: allowedActionItems,
    guided_fix: action.guided_fix,
    can_update: canUpdate,
    can_update_reason: evidenceBlocksAction
      ? "Недостаточно доказательств: задача доступна только для просмотра."
      : (firstText(
          action.can_update_reason,
          payload.can_update_reason,
          raw.can_update_reason,
        ) ?? (canUpdate ? null : "Только рекомендация")),
    can_recheck:
      !problemLike ||
      allowedActions.includes("recheck") ||
      allowedActionItems.some(
        (item) => item.code === "recheck" && item.enabled,
      ),
    can_assign: canUpdate,
    can_set_deadline: canUpdate,
    is_beta: beta,
    is_test_only: testOnly,
    is_read_only: !canUpdate,
    is_problem_like: problemLike,
    is_seller_visible: isSellerVisibleMoneyTrust(
      action.money_trust,
      payload.money_trust,
      evidenceLedger?.money_trust,
    ),
    is_claims: isClaimsAction(action, payload),
    result_status: resultStatusFrom(canonicalSummary, embeddedSummary),
    result_summary: resultSummary,
    latest_result_event: resultEvents[0] ?? null,
    price_safety: priceSafety,
    needs_price_safety: needsPriceSafety,
    assigned_to_user_id: assignedToUserId,
    assigned_to_user_name: userNameFrom(assignedToUserId, options.users),
    deadline_at: deadlineAt,
    is_overdue: sla.is_overdue,
    due_in_hours: sla.due_in_hours,
    sla_state: sla.sla_state,
    last_comment: firstText(
      action.last_comment,
      payload.last_comment,
      raw.last_comment,
    ),
    last_status_changed_at: lastStatusChangedAt,
    history_summary: historySummary,
    recheck_rule: recheckRule,
    problem_instance_id: problemInstanceId,
    payload,
    raw,
    linked_entity: linked,
  };
}

export function adaptActionCenterItems(
  actions: PortalAction[],
  options: AdaptActionCenterOptions = {},
): ActionCenterItem[] {
  return actions.map((action) => adaptActionCenterItem(action, options));
}

export function portalActionToActionCenterItem(
  action: PortalAction,
  options: AdaptActionCenterOptions = {},
): ActionCenterItem {
  return adaptActionCenterItem(action, options);
}

export function portalResultPageToProblemResultSummary(
  page?: PortalResultEventsPage | null,
): ProblemResultSummary {
  return problemResultSummaryFromPage(page) as ProblemResultSummary;
}

function actionCenterCanFixHere(item: ActionCenterItem): boolean {
  if (item.can_update) return true;
  return item.allowed_actions.some((code) =>
    [
      "open_data_fix",
      "open_price_review",
      "open_promo_planner",
      "open_supply_planner",
      "open_ads_dashboard",
      "run_checker",
      "upload_cost",
      "map_sku",
      "classify_expense",
      "open_product",
      "open_results",
    ].includes(code),
  );
}

function sellerResultFromItem(
  item: ActionCenterItem,
): SellerProblemContract["result"] {
  if (!item.result_summary && item.result_status === "pending_data")
    return null;
  const summary = compactRecord(item.result_summary);
  const amount = firstNumber(
    summary.measured_effect_amount,
    summary.result_amount,
    compactRecord(summary.comparison).amount,
  );
  return {
    status: item.result_status,
    detail:
      firstText(
        summary.message,
        summary.calculation_note,
        summary.disclaimer,
      ) ??
      "После действия платформа сравнит данные «до» и «после». Это корреляция, а не доказанная причинность.",
    amount,
  };
}

export function product360ProblemToActionCenterLink(
  problem: ActionCenterItem | SellerProblemContract,
): NonNullable<SellerProblemContract["actionCenterSearch"]> {
  if ("actionCenterSearch" in problem && problem.actionCenterSearch) {
    return problem.actionCenterSearch;
  }
  if ("source_module" in problem) {
    return {
      source: problem.source_module ?? "problem_engine",
      ...(problem.source_id != null
        ? { source_id: String(problem.source_id) }
        : {}),
      code:
        problem.problem_code ??
        problem.detector_code ??
        problem.action_type ??
        "",
      ...(problem.nm_id != null ? { nm_id: String(problem.nm_id) } : {}),
      ...(problem.source_module === "problem_engine" &&
      problem.problem_instance_id != null
        ? { problem_instance_id: String(problem.problem_instance_id) }
        : {}),
    };
  }
  return {};
}

export type ProblemResultsSearch = {
  action_id?: string;
  source_module?: string;
  problem_instance_id?: string;
  problem_code?: string;
  nm_id?: string;
};

export function actionCenterItemToResultsSearch(
  item: ActionCenterItem,
): ProblemResultsSearch {
  return {
    ...(item.action_id != null ? { action_id: String(item.action_id) } : {}),
    ...(item.source_module === "problem_engine"
      ? { source_module: "problem_engine" }
      : {}),
    ...(item.problem_instance_id != null
      ? { problem_instance_id: String(item.problem_instance_id) }
      : {}),
    ...(item.problem_code ? { problem_code: item.problem_code } : {}),
    ...(item.nm_id != null ? { nm_id: String(item.nm_id) } : {}),
  };
}

export function actionCenterItemToSellerProblemContract(
  item: ActionCenterItem,
  options: {
    result?: SellerProblemContract["result"];
  } = {},
): SellerProblemContract {
  const amount = item.money_impact_amount;
  const canFixHere = actionCenterCanFixHere(item);
  return {
    id: item.problem_instance_id ?? item.id,
    title: item.title || "Проблема товара",
    why:
      item.short_explanation ||
      item.reason ||
      item.evidence_ledger?.formula_human ||
      "Платформа нашла проблему по подключённым операционным данным.",
    impactText:
      amount == null
        ? problemImpactLabel(item.impact_type)
        : `${problemImpactLabel(item.impact_type)}: ${amount}`,
    impactAmount: amount,
    trustState: item.trust_state ?? item.money_trust.state,
    impactType: item.impact_type ?? item.money_trust.impact_kind,
    severity: item.severity ?? item.priority ?? "medium",
    status: item.status,
    nextStep:
      item.next_step ||
      "Откройте рекомендованный сценарий и выполните безопасное действие.",
    canFixHere,
    canFixHereText: canFixHere
      ? "Да, используйте действия в этой карточке."
      : "Не напрямую. Исправьте исходные данные или дождитесь синхронизации.",
    recheckRule: item.recheck_rule,
    result: options.result ?? sellerResultFromItem(item),
    showResultBlock:
      Boolean(options.result) ||
      Boolean(item.result_summary) ||
      ["in_progress", "done", "resolved"].includes(normalizeText(item.status)),
    evidenceLedger: item.evidence_ledger,
    evidenceQuality:
      item.evidence_state === "full_evidence" ? "full" : "partial",
    allowedActions: item.allowed_actions,
    sourceLabel: item.source_module,
    moneyTrust: item.money_trust,
    actionCenterSearch: product360ProblemToActionCenterLink(item),
    priceSafety: item.price_safety,
    needsPriceSafety: item.needs_price_safety,
  };
}

export function actionCenterResultPageForItem(
  item: ActionCenterItem,
  page?: PortalResultEventsPage | null,
): PortalResultEventsPage | null {
  const events = problemResultEvents(page);
  if (!page || !events.length) return null;
  const code = item.problem_code ?? item.detector_code;
  const matched = events.filter((event) => {
    if (
      item.problem_instance_id != null &&
      event.problem_instance_id === item.problem_instance_id
    ) {
      return true;
    }
    if (
      code &&
      event.problem_code === code &&
      (item.nm_id == null || event.nm_id === item.nm_id)
    ) {
      return true;
    }
    return false;
  });
  if (!matched.length) return null;
  return {
    ...page,
    items: matched,
    recent_events: matched,
    total: matched.length,
  };
}
