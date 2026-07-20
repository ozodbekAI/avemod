// Thin client for WB Data Core backend.
// Base URL precedence: localStorage override > VITE_API_BASE_URL env > built-in default.
// `/api/v1` is appended exactly once — never duplicated even if the env value
// already includes it.

import type { EvidenceLedger } from "./evidence";
import type { MoneyTrustInfo } from "./money-trust";

type RuntimeImportMeta = ImportMeta & {
  env?: {
    VITE_API_BASE_URL?: string;
    DEV?: boolean;
  };
};

const importMetaEnv =
  typeof import.meta !== "undefined"
    ? (import.meta as RuntimeImportMeta).env
    : undefined;
const RAW_ENV_BASE_URL = importMetaEnv?.VITE_API_BASE_URL || "";
const IS_DEV = Boolean(importMetaEnv?.DEV);
// Only use localhost when the browser itself is on localhost. In hosted previews
// (lovable.app, lovableproject.com, custom domains) the dev flag is true but
// 127.0.0.1:8000 is unreachable from the user's browser → "Failed to fetch".
const IS_LOCAL_HOST =
  typeof window !== "undefined" &&
  /^(localhost|127\.0\.0\.1|0\.0\.0\.0)$/.test(window.location.hostname);
const BUILT_IN_BASE_URL =
  IS_DEV && IS_LOCAL_HOST
    ? "http://localhost:8000/api/v1"
    : "https://finance.ozodbek-akramov.uz/api/v1";
const RAW_DEFAULT = RAW_ENV_BASE_URL || BUILT_IN_BASE_URL;

/** Normalize: strip trailing slashes and ensure exactly one `/api/v1` suffix. */
export function normalizeBaseUrl(raw: string): string {
  let u = (raw || "").trim().replace(/\/+$/, "");
  if (!u) return u;
  // collapse accidental duplicate /api/api, /api/v1/v1, or bare /api
  u = u.replace(/(\/api(\/v\d+)?)+$/i, "/api/v1");
  if (!/\/api\/v\d+$/i.test(u)) u += "/api/v1";
  return u;
}

const DEFAULT_BASE_URL = normalizeBaseUrl(RAW_DEFAULT);

const LS_BASE = "wb.api_base_url";
const LS_ACCESS = "wb.access_token";
const LS_REFRESH = "wb.refresh_token";
const LS_ACCOUNT = "wb.active_account_id";

export function getBaseUrl(): string {
  if (typeof window !== "undefined") {
    const override = getBaseUrlOverride();
    if (override) return override;
  }
  return DEFAULT_BASE_URL;
}

function getBaseUrlOverride(): string | null {
  if (typeof window === "undefined") return null;
  const override = localStorage.getItem(LS_BASE);
  return override ? normalizeBaseUrl(override) : null;
}

function clearBaseUrlOverride() {
  if (typeof window === "undefined") return;
  localStorage.removeItem(LS_BASE);
}

export function setBaseUrl(url: string) {
  if (typeof window === "undefined") return;
  const normalized = normalizeBaseUrl(url);
  if (!normalized) localStorage.removeItem(LS_BASE);
  else localStorage.setItem(LS_BASE, normalized);
}

export function getAccessToken() {
  return typeof window === "undefined" ? null : localStorage.getItem(LS_ACCESS);
}
export function getRefreshToken() {
  return typeof window === "undefined"
    ? null
    : localStorage.getItem(LS_REFRESH);
}
export function setTokens(access: string, refresh: string) {
  localStorage.setItem(LS_ACCESS, access);
  localStorage.setItem(LS_REFRESH, refresh);
}
export function clearTokens() {
  localStorage.removeItem(LS_ACCESS);
  localStorage.removeItem(LS_REFRESH);
}

export function getActiveAccountId(): number | null {
  if (typeof window === "undefined") return null;
  const v = localStorage.getItem(LS_ACCOUNT);
  return v ? Number(v) : null;
}
export function setActiveAccountId(id: number | null) {
  if (id == null) localStorage.removeItem(LS_ACCOUNT);
  else localStorage.setItem(LS_ACCOUNT, String(id));
}

export class ApiError extends Error {
  status: number;
  body: unknown;
  path?: string;
  constructor(status: number, message: string, body: unknown, path?: string) {
    super(message);
    this.status = status;
    this.body = body;
    this.path = path;
  }
}

type QueryScalar = string | number | boolean | null | undefined;
type ReqOpts = {
  method?: string;
  query?: Record<string, QueryScalar | ReadonlyArray<QueryScalar>>;
  body?: unknown;
  formData?: FormData;
  auth?: boolean;
  raw?: boolean;
  signal?: AbortSignal;
};

export type AgentApiSnapshot = {
  method: string;
  path: string;
  query?: Record<string, QueryScalar | ReadonlyArray<QueryScalar>>;
  status: number;
  received_at: string;
  summary: unknown;
};

const AGENT_API_SNAPSHOT_LIMIT = 30;
const AGENT_API_SECRET_TOKENS = [
  "api_key",
  "authorization",
  "credential",
  "encrypted_token",
  "jwt",
  "password",
  "refresh_token",
  "secret",
  "token",
];
const recentApiSnapshots: AgentApiSnapshot[] = [];

export function getRecentApiSnapshots(): AgentApiSnapshot[] {
  return JSON.parse(JSON.stringify(recentApiSnapshots)) as AgentApiSnapshot[];
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function isSecretKey(key: string) {
  const normalized = key.toLowerCase();
  return AGENT_API_SECRET_TOKENS.some((token) => normalized.includes(token));
}

function summarizeLeafForAgent(value: unknown): unknown {
  if (value === null || value === undefined) return value;
  if (["string", "number", "boolean"].includes(typeof value)) return value;
  if (Array.isArray(value)) return { type: "array", length: value.length };
  if (isRecord(value)) {
    return {
      type: "object",
      keys: Object.keys(value)
        .filter((key) => !isSecretKey(key))
        .slice(0, 16),
    };
  }
  return String(value);
}

function summarizeForAgent(value: unknown, depth = 0): unknown {
  if (value === null || value === undefined) return value;
  if (["string", "number", "boolean"].includes(typeof value)) return value;
  if (Array.isArray(value)) {
    return {
      type: "array",
      length: value.length,
      sample: value
        .slice(0, 4)
        .map((item) => summarizeForAgent(item, depth + 1)),
    };
  }
  if (!isRecord(value)) return String(value);
  if (depth >= 3) return summarizeLeafForAgent(value);

  const entries = Object.entries(value).filter(([key]) => !isSecretKey(key));
  const out: Record<string, unknown> = {};
  for (const [key, item] of entries.slice(0, 28)) {
    out[key] =
      depth >= 2
        ? summarizeLeafForAgent(item)
        : summarizeForAgent(item, depth + 1);
  }
  if (entries.length > 28) out.__omitted_keys = entries.length - 28;
  return out;
}

function recordApiSnapshot(
  path: string,
  opts: ReqOpts,
  status: number,
  payload: unknown,
) {
  if (typeof window === "undefined") return;
  if (path.includes("/portal/agent/") || path.includes("/auth/")) return;
  recentApiSnapshots.unshift({
    method: (opts.method ?? "GET").toUpperCase(),
    path,
    query: opts.query,
    status,
    received_at: new Date().toISOString(),
    summary: summarizeForAgent(payload),
  });
  if (recentApiSnapshots.length > AGENT_API_SNAPSHOT_LIMIT) {
    recentApiSnapshots.splice(AGENT_API_SNAPSHOT_LIMIT);
  }
}

let refreshPromise: Promise<boolean> | null = null;
async function tryRefresh(): Promise<boolean> {
  if (refreshPromise) return refreshPromise;
  const rt = getRefreshToken();
  if (!rt) return false;
  refreshPromise = (async () => {
    try {
      const res = await fetch(`${getBaseUrl()}/auth/refresh`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "ngrok-skip-browser-warning": "true",
        },
        body: JSON.stringify({ refresh_token: rt }),
      });
      if (!res.ok) return false;
      const data = (await res.json()) as {
        access_token: string;
        refresh_token: string;
      };
      setTokens(data.access_token, data.refresh_token);
      return true;
    } catch {
      return false;
    } finally {
      refreshPromise = null;
    }
  })();
  return refreshPromise;
}

// Bare backend paths that 404. These are UI routes, not API endpoints.
// Any code that hits the network with one of these is a bug — see
// API_ENDPOINTS in src/lib/endpoints.ts for the correct replacement.
const INVALID_API_PATHS = new Set<string>([
  "/money",
  "/cards",
  "/sku",
  "/data-fix",
  "/costs",
  "/finance",
  "/operations",
  "/pricing",
  "/purchase-plan",
  // Outdated/non-existent backend paths — see endpoints.ts for replacements.
  "/ads/summary", // → /ads/efficiency (+ /ads/stats, /ads/campaigns)
  "/catalog/cards", // → /products or /core-sku
  "/costs/coverage", // → /dashboard/data-health (cost coverage fields)
  "/dq/summary", // → /dq/issues/summary
  "/sync/status", // → /dashboard/data-health (+ /sync/runs, /sync/cursors)
]);

function assertValidApiPath(path: string) {
  if (!IS_DEV) return;
  const clean = (path.split("?")[0] || "").replace(/\/+$/, "");
  // Flag bare invalid roots, and "/cards/" / "/sku/" with no further segment.
  const segments = clean.split("/").filter(Boolean);
  const root = segments.length ? `/${segments[0]}` : "";
  if (INVALID_API_PATHS.has(clean)) {
    console.warn(
      `[api] Invalid API path "${path}" — this is a UI route, not a backend endpoint. ` +
        `Use API_ENDPOINTS from src/lib/endpoints.ts.`,
    );
  } else if ((root === "/cards" || root === "/sku") && segments.length === 1) {
    console.warn(
      `[api] Invalid API path "${path}" — did you mean /money/articles or /money/cards/{skuId}?`,
    );
  }
}

function buildUrl(
  path: string,
  query?: ReqOpts["query"],
  base = getBaseUrl(),
): string {
  assertValidApiPath(path);
  const url = new URL(`${base}${path.startsWith("/") ? path : `/${path}`}`);
  if (query) {
    for (const [k, v] of Object.entries(query)) {
      if (v === null || v === undefined || v === "") continue;
      if (Array.isArray(v)) {
        for (const item of v) {
          if (item === null || item === undefined || item === "") continue;
          url.searchParams.append(k, String(item));
        }
      } else {
        url.searchParams.set(k, String(v));
      }
    }
  }
  return url.toString();
}

function isAbortError(error: unknown): boolean {
  return (
    typeof DOMException !== "undefined" &&
    error instanceof DOMException &&
    error.name === "AbortError"
  );
}

async function doFetch(
  path: string,
  opts: ReqOpts,
  retried = false,
): Promise<Response> {
  const headers: Record<string, string> = {
    "ngrok-skip-browser-warning": "true",
  };
  if (!opts.formData) headers["Content-Type"] = "application/json";
  if (opts.auth !== false) {
    const t = getAccessToken();
    if (t) headers["Authorization"] = `Bearer ${t}`;
  }
  const requestInit: RequestInit = {
    method: opts.method ?? "GET",
    headers,
    body: opts.formData
      ? opts.formData
      : opts.body
        ? JSON.stringify(opts.body)
        : undefined,
    signal: opts.signal,
  };
  let res: Response;
  try {
    res = await fetch(buildUrl(path, opts.query), requestInit);
  } catch (error) {
    const override = getBaseUrlOverride();
    if (
      !retried &&
      override &&
      override !== DEFAULT_BASE_URL &&
      !isAbortError(error)
    ) {
      clearBaseUrlOverride();
      res = await fetch(
        buildUrl(path, opts.query, DEFAULT_BASE_URL),
        requestInit,
      );
    } else {
      throw error;
    }
  }

  // Single, deduped refresh attempt on 401. `retried` prevents a second
  // pass — no infinite refresh loop is possible from this code path.
  if (res.status === 401 && !retried && opts.auth !== false) {
    const ok = await tryRefresh();
    if (ok) return doFetch(path, opts, true);
  }
  return res;
}

/**
 * Hard-redirect to the login page and wipe local auth state.
 * Triggered when the refresh flow fails on a 401 response, so users do not
 * get stuck on a protected page that will never recover.
 */
function redirectToLogin() {
  if (typeof window === "undefined") return;
  const path = window.location.pathname + window.location.search;
  if (window.location.pathname === "/login") return;
  // Encode current location so login can return the user back.
  const next = encodeURIComponent(path);
  window.location.replace(`/login?redirect=${next}`);
}

// In-flight GET de-duplication. Multiple components calling api() for the
// same URL while a previous request is still in flight share one Response.
// Collapses the auth/me + accounts + modules/health stampede when several
// panels mount on the same route. No time-based TTL — TanStack Query owns
// caching; this just prevents concurrent identical fetches.
const inflightGets = new Map<string, Promise<unknown>>();

export async function api<T = unknown>(
  path: string,
  opts: ReqOpts = {},
): Promise<T> {
  const method = (opts.method ?? "GET").toUpperCase();
  const dedupable =
    method === "GET" && !opts.formData && !opts.body && !opts.raw;
  const key = dedupable
    ? `${method} ${buildUrl(path, opts.query)} auth=${opts.auth !== false}`
    : "";

  if (dedupable) {
    const existing = inflightGets.get(key);
    if (existing) return existing as Promise<T>;
  }

  const run = (async () => {
    const res = await doFetch(path, opts);
    if (opts.raw) {
      recordApiSnapshot(path, opts, res.status, {
        raw: true,
        content_type: res.headers.get("content-type") || null,
      });
      return res as unknown as T;
    }
    if (!res.ok) {
      let body: unknown = null;
      try {
        body = await res.json();
      } catch {
        try {
          body = await res.text();
        } catch {
          body = null;
        }
      }
      recordApiSnapshot(path, opts, res.status, body);
      const detail =
        body && typeof body === "object" && "detail" in body
          ? (body as { detail?: unknown }).detail
          : null;
      const msg =
        typeof detail === "string" ? detail : `Request failed (${res.status})`;
      if (res.status === 401 && opts.auth !== false) {
        clearTokens();
        redirectToLogin();
      }
      throw new ApiError(res.status, msg, body, path);
    }
    if (res.status === 204) {
      recordApiSnapshot(path, opts, res.status, null);
      return null as T;
    }
    const ct = res.headers.get("content-type") || "";
    if (ct.includes("application/json")) {
      const data = (await res.json()) as T;
      recordApiSnapshot(path, opts, res.status, data);
      return data;
    }
    const text = await res.text();
    recordApiSnapshot(path, opts, res.status, { text: text.slice(0, 2000) });
    return text as unknown as T;
  })();

  if (dedupable) {
    inflightGets.set(key, run);
    run.then(
      () => {
        if (inflightGets.get(key) === run) inflightGets.delete(key);
      },
      () => {
        if (inflightGets.get(key) === run) inflightGets.delete(key);
      },
    );
  }
  return run;
}

// Helper: fetch a list endpoint that may return either a bare array or a
// `{total, limit, offset, items}` paginated envelope. Always returns an array.
export async function apiList<T = unknown>(
  path: string,
  opts: ReqOpts = {},
): Promise<T[]> {
  const res = await api<T[] | Paginated<T> | null | undefined>(path, opts);
  if (!res) return [];
  if (Array.isArray(res)) return res;
  if (typeof res === "object" && Array.isArray((res as Paginated<T>).items))
    return (res as Paginated<T>).items;
  return [];
}

// Typed helpers
export interface Paginated<T> {
  total: number;
  limit: number;
  offset: number;
  items: T[];
}

export type JsonPrimitive = string | number | boolean | null;
export type JsonValue = JsonPrimitive | JsonObject | JsonValue[];
export interface JsonObject {
  [key: string]: JsonValue;
}

export interface WBAccount {
  id: number;
  name: string;
  seller_name: string | null;
  external_account_id: string | null;
  timezone: string;
  is_active: boolean;
  created_at: string;
}
export interface WBToken {
  id: number;
  account_id: number;
  category: string;
  comment: string | null;
  is_active: boolean;
  created_at: string;
}
export interface UserRead {
  id: number;
  email: string;
  full_name: string;
  is_active: boolean;
  is_superuser: boolean;
  created_at: string;
  roles?: string[];
  accounts?: Array<{ id: number; role: string }>;
  permissions?: string[];
}
export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type?: string;
}

export interface DashboardHealthIssueBucket {
  code: string;
  severity: string;
  count: number;
}
export interface DashboardHealthDomainStatus {
  domain: string;
  latest_status: string | null;
  latest_finished_at: string | null;
  last_successful_at: string | null;
  latest_error_text: string | null;
  cursor_status: string | null;
  cursor_last_synced_at: string | null;
}
export interface DashboardDataHealth {
  account_id: number;
  open_issues_total: number;
  failed_domains: string[];
  skipped_domains: string[];
  missed_days_count: number;
  missing_manual_cost_count: number;
  unmatched_sku_count: number;
  duplicate_srid_count: number;
  active_sku_count: number;
  active_sku_with_manual_cost_count: number;
  placeholder_manual_cost_count: number;
  revenue_rows_with_cost: number;
  revenue_rows_without_cost: number;
  revenue_with_cost: number;
  revenue_without_cost: number;
  sku_cost_coverage_percent: number | null;
  revenue_cost_coverage_percent: number | null;
  ad_cluster_rows: number;
  // Extended trust fields (added when backend exposes them; all optional so
  // the UI never invents values when missing).
  business_trusted?: boolean | null;
  trust_state?: string | null;
  financial_final?: boolean | null;
  supplier_confirmed_revenue_coverage_percent?: number | null;
  real_revenue_cost_coverage_percent?: number | null;
  real_manual_cost_count?: number | null;
  trusted_manual_cost_count?: number | null;
  cost_trust_policy?: string | null;
  financial_final_blockers_total?: number | null;
  ad_cluster_state?: string | null;
  ad_cluster_reason?: string | null;
  issue_buckets: DashboardHealthIssueBucket[];
  domains: DashboardHealthDomainStatus[];
  notes: string[];
  // ── Pulse-card observability (backend confirmation flags) — optional ─
  pulse?: Record<
    string,
    {
      checked?: boolean | null;
      has_data?: boolean | null;
      has_risk?: boolean | null;
      source_freshness?:
        | "fresh"
        | "stale"
        | "needs_sync"
        | "missing"
        | "confirmed"
        | string
        | null;
    }
  > | null;
}

export interface CoreSKUListItem {
  id: number;
  account_id: number;
  nm_id: number | null;
  vendor_code: string | null;
  supplier_article: string | null;
  barcode: string | null;
  chrt_id: number | null;
  size_id: number | null;
  tech_size: string | null;
  title: string | null;
  brand: string | null;
  subject_id: number | null;
  subject_name: string | null;
  is_active: boolean;
  status: string | null;
  comment: string | null;
  source_updated_at: string | null;
  current_price: number | null;
  current_discounted_price: number | null;
  seller_discount: number | null;
  club_discount: number | null;
  latest_quantity: number | null;
  latest_quantity_full: number | null;
  latest_in_way_to_client: number | null;
  latest_in_way_from_client: number | null;
  latest_stock_snapshot_at: string | null;
  latest_sale_date: string | null;
  manual_cost_id: number | null;
  cost_price: number | null;
  packaging_cost: number | null;
  inbound_logistics_cost: number | null;
  total_unit_cost: number | null;
  supplier: string | null;
  has_manual_cost: boolean;
  open_issue_count: number;
  has_open_issues: boolean;
  last_30d_sales_qty: number | null;
  last_30d_revenue: number | null;
}
export interface CoreSKUDetail {
  sku: CoreSKUListItem;
  recent_issue_codes: string[];
  warehouses: string[];
}

export interface SKUProfitabilityRow {
  sku_id: number;
  nm_id: number | null;
  vendor_code: string | null;
  barcode: string | null;
  title: string | null;
  brand: string | null;
  subject_name: string | null;
  finance_rows: number;
  gross_units: number;
  return_units: number;
  net_units: number;
  realized_revenue: number;
  for_pay: number;
  commission: number;
  acquiring_fee: number;
  logistics: number;
  paid_acceptance: number;
  storage: number;
  [k: string]: unknown;
}

export interface DataQualityIssue {
  id: number;
  account_id: number | null;
  domain: string;
  severity: string;
  code: string;
  entity_key?: string | null;
  entity_type?: string | null;
  entity_id?: number | null;
  sku_id: number | null;
  nm_id: number | null;
  source_table?: string | null;
  message: string;
  payload: JsonObject;
  detected_at: string;
  classification_status?: string | null;
  classification_reason?: string | null;
  age_bucket?: string | null;
  source_domains?: string[];
  candidate_sku_ids?: number[];
  vendor_code?: string | null;
  barcode?: string | null;
  status?: string;
  first_seen_at: string | null;
  last_seen_at: string | null;
  details?: Record<string, unknown> | null;
  resolved_at: string | null;
  mapped_sku_id?: number | null;
  financial_final_blocker?: boolean;
  financial_final_blocker_override?: boolean | null;
  effective_financial_final_blocker?: boolean;
  business_impact?: string;
  recommended_fix?: string;
  simple_reason?: string;
  first_action?: string;
  step_by_step?: string[];
  success_check?: string[];
  next_screen_path?: string;
  next_screen_label?: string;
  wait_or_fix_hint?: string;
  evidence_ledger?: EvidenceLedger | null;
  money_trust?: MoneyTrustInfo | null;
  resolver?: ProblemResolver | null;
  // ── Backend Truth & Classification (Phase 12) — all optional ─────────
  owner_type?: "user" | "system" | "admin" | "business" | "mixed" | null;
  fixability?:
    | "fix_in_platform"
    | "fix_in_wb_cabinet"
    | "wait_for_sync"
    | "system_only"
    | "admin_only"
    | "business_decision"
    | "no_action"
    | string
    | null;
  issue_nature?:
    | "data_blocker"
    | "sync_waiting"
    | "system_check"
    | "business_signal"
    | "finance_investigation"
    | "content_fix"
    | "wait_for_wb_report"
    | string
    | null;
  can_user_fix_inside_platform?: boolean | null;
  is_manual_edit_allowed?: boolean | null;
  primary_action_code?: string | null;
  primary_action_label?: string | null;
  target_href?: string | null;
  disabled_reason?: string | null;
  recheck_mode?: "auto_sync" | "manual" | "wait" | string | null;
}

export type DataQualityIssuesPage = Paginated<DataQualityIssue> & {
  computed_at?: string | null;
  cache_status?: string;
  data_version_hash?: string | null;
  evidence_ledger?: Record<string, EvidenceLedger>;
};

export type GuidedFixOwnerType =
  | "user"
  | "system"
  | "admin"
  | "mixed"
  | "business";
export type GuidedFixComponentType =
  | "upload_cost_file"
  | "map_sku"
  | "classify_expense"
  | "rerun_sync"
  | "open_finance_reconciliation"
  | "wait_for_wb_report"
  | "review_price"
  | "open_card_mapping"
  | "admin_investigation"
  | "cost_inline_editor"
  | "sku_mapping"
  | "expense_classification"
  | "stock_decision"
  | "sync_recheck"
  | "ads_allocation_status"
  | "card_mapping";
export type GuidedFixActionType =
  | "map_sku"
  | "classify_expense"
  | "mark_system_wait"
  | "mark_admin_investigation"
  | "trigger_recheck"
  | "mark_cost_upload_started"
  | "review_price";

export interface GuidedFixDefinition {
  owner_type: GuidedFixOwnerType;
  can_user_fix_inside_platform: boolean;
  fix_component_type: GuidedFixComponentType;
  required_inputs: string[];
  affected_rows_query: Record<string, unknown>;
  preview_before_change: Record<string, unknown>;
  apply_action: Record<string, unknown>;
  recheck_query: Record<string, unknown>;
  success_state: Record<string, unknown>;
  failure_state: Record<string, unknown>;
  safety_notes: string[];
}

export type ProblemResolverOwnerType = "user" | "system" | "admin" | "business";
export type ProblemResolverKind =
  | "inline_table"
  | "inline_form"
  | "task_decision"
  | "system_status"
  | "readonly_signal";
export type ProblemResolverComponentType =
  | "cost_inline_editor"
  | "sku_mapping"
  | "expense_classification"
  | "stock_decision"
  | "sync_recheck"
  | "ads_allocation_status"
  | "admin_investigation"
  | "price_review"
  | "card_mapping";

export interface ProblemResolverAction {
  action_type: string;
  label: string;
  description?: string;
  payload?: Record<string, unknown>;
}

export interface ProblemResolver {
  owner_type: ProblemResolverOwnerType;
  resolver_kind: ProblemResolverKind;
  component_type: ProblemResolverComponentType;
  required_inputs: string[];
  safe_actions: ProblemResolverAction[];
  blocked_actions: string[];
  success_check: string[];
  recheck_rule?: string;
  affected_rows_endpoint?: string;
  guided_action_endpoint?: string;
  can_close_in_modal: boolean;
  title?: string;
  description?: string;
}

export interface GuidedFixSourceFact {
  label: string;
  value?: unknown;
  unit?: string | null;
  source_table?: string | null;
  source_endpoint?: string | null;
  date_range?: string | null;
  filters?: Record<string, unknown>;
  row_count?: number | null;
  sample_rows?: Record<string, unknown>[];
}

export interface DataQualityResolutionContext {
  issue: DataQualityIssue;
  definition: GuidedFixDefinition;
  resolver?: ProblemResolver | null;
  affected_rows: Record<string, unknown>[];
  affected_rows_total: number;
  affected_rows_limit: number;
  affected_rows_offset: number;
  affected_rows_export_endpoint?: string | null;
  source_facts: GuidedFixSourceFact[];
  suggested_fix_action: Record<string, unknown>;
  recheck_rule: string;
  audit_history: Record<string, unknown>[];
  safe_to_apply: boolean;
  dynamic_problem_instance?: {
    id: number;
    problem_code: string;
    status: string;
    source_module: string;
    source_id: string;
    action_center_source_module: string;
    action_center_source_id: string;
    impact_type?: string | null;
    trust_state?: string | null;
    evidence_ledger?: EvidenceLedger | null;
    [key: string]: unknown;
  } | null;
}

export interface GuidedFixActionRequest {
  action_type: GuidedFixActionType;
  inputs?: Record<string, unknown>;
  comment?: string | null;
}

export interface GuidedFixActionResponse {
  status: "ok" | "blocked" | "error";
  message: string;
  context: DataQualityResolutionContext;
}

export interface DataQualityIssueSummaryRow {
  code?: string;
  severity?: string;
  count?: number;
  evidence_ledger?: EvidenceLedger | null;
  money_trust?: MoneyTrustInfo | null;
  [k: string]: unknown;
}

export interface DataQualityIssueSummaryResponse {
  items?: DataQualityIssueSummaryRow[];
  open_issues_total?: number;
  all_open_issues_total?: number;
  blocking_open_issues_total?: number;
  financial_final_blockers_total?: number;
  by_severity?: Record<string, number>;
  by_issue_type?: Record<string, number>;
  by_source_table?: Record<string, number>;
  by_group?: Record<string, number>;
  by_group_blocking?: Record<string, number>;
  by_group_all_open?: Record<string, number>;
  evidence_ledger?: Record<string, EvidenceLedger>;
}

export interface SyncRun {
  id: number;
  account_id: number;
  domain: string;
  trigger: string;
  status: string;
  is_backfill: boolean;
  started_at: string;
  finished_at: string | null;
  details: Record<string, unknown>;
  error_text: string | null;
}

export interface MartReconciliationRow {
  account_id: number;
  nm_id: number | null;
  date: string;
  units_sold: number | null;
  units_returned: number | null;
  sales_revenue: number | null;
  finance_revenue: number | null;
  diff_revenue: number | null;
  diff_units: number | null;
  [k: string]: unknown;
}

export interface ManualCostRow {
  id: number;
  account_id: number;
  nm_id: number | null;
  vendor_code: string | null;
  barcode: string | null;
  cost_price: number | null;
  packaging_cost: number | null;
  inbound_logistics_cost: number | null;
  seller_other_expense: number | null;
  cost_source: string | null;
  cost_truth_level: string | null;
  supplier: string | null;
  valid_from: string | null;
  valid_to: string | null;
  [k: string]: unknown;
}

export interface ManualCostUpload {
  id: number;
  account_id: number;
  filename: string | null;
  status: string;
  rows_total: number | null;
  rows_valid?: number | null;
  rows_invalid?: number | null;
  rows_committed: number | null;
  uploaded_at: string | null;
  imported_at?: string | null;
  created_at?: string | null;
  confirmed_at: string | null;
  summary?: Record<string, unknown> | null;
  [k: string]: unknown;
}

export interface SyncCursor {
  id: number;
  account_id: number;
  domain: string;
  cursor_key: string | null;
  last_synced_at: string | null;
  status: string | null;
  details: Record<string, unknown> | null;
}

// Generic row shape — many list endpoints share account/nm/date fields.
export type Row = Record<string, unknown> & {
  id?: number;
  account_id?: number;
  nm_id?: number | null;
  vendor_code?: string | null;
  barcode?: string | null;
  date?: string | null;
  created_at?: string | null;
};

// ============================================================
// Money Management types — per README_FRONTEND_LOVABLE_MONEY_MANAGEMENT.md
// ============================================================

export type DataTrustStateT = "trusted" | "test_only" | "data_blocked";
export type ConfidenceT = "high" | "medium" | "low";

export interface DataTrustInfo {
  state: DataTrustStateT;
  trust_state?: string;
  business_trusted: boolean;
  operational_trusted?: boolean;
  financial_final?: boolean;
  can_generate_business_actions: boolean;
  confidence: ConfidenceT;
  cost_trust_policy?: string | null;
  supplier_confirmed_revenue_coverage_percent?: number;
  operator_baseline_revenue_coverage_percent?: number;
  trusted_revenue_cost_coverage_percent?: number;
  financial_final_blockers_total?: number;
  final_profit_blockers_total?: number;
  all_open_issues_total?: number;
  blocking_open_issues_total?: number;
  blocked_reasons: string[];
  human_message?: string;
}

export interface MoneyFlowItem {
  key: string;
  label?: string;
  amount: number | null;
  confidence?: ConfidenceT;
  reason?: string | null;
}

export interface RiskItem {
  code: string;
  title: string;
  business_impact?: string;
  affected_amount?: number | null;
  affected_count?: number | null;
  cta?: { label: string; href: string } | null;
  priority?: "critical" | "high" | "medium" | "low";
}

export interface NextAction {
  id?: number | string;
  action_type: string;
  priority: "critical" | "high" | "medium" | "low";
  title?: string;
  what_to_do?: string;
  why?: string;
  how_to_fix?: string[];
  expected_effect_amount?: number | null;
  confidence?: ConfidenceT;
  status?: string;
  is_data_fix?: boolean;
  linked_sku_id?: number | null;
  linked_nm_id?: number | null;
  source_period?: { from: string; to: string } | null;
}

export interface MoneyKpis {
  revenue?: number | null;
  net_profit?: number | null;
  margin_percent?: number | null;
  wb_balance?: number | null;
  stock_value?: number | null;
  ad_spend?: number | null;
  wb_expenses?: number | null;
  data_blockers_count?: number | null;
  evidence_ledger?: Record<string, EvidenceLedger>;
  [k: string]:
    | number
    | string
    | Record<string, EvidenceLedger>
    | null
    | undefined;
}

export interface MoneySummary {
  meta: {
    account_id: number;
    date_from: string;
    date_to: string;
    currency: string;
    generated_at: string;
    data_trust: DataTrustInfo;
  };
  answer: {
    business_status: string;
    title: string;
    short_text: string;
    main_problem?: string | null;
    main_next_step?: string | null;
  };
  kpis: MoneyKpis;
  money_flow?: {
    incoming?: MoneyFlowItem[];
    outgoing?: MoneyFlowItem[];
    cash_and_stock?: MoneyFlowItem[];
  };
  risk_summary?: {
    critical_count: number;
    risks: RiskItem[];
  };
  top_cards?: Record<string, unknown[]>;
  next_actions?: NextAction[];
  evidence_ledger?: Record<string, EvidenceLedger>;
}

export interface MoneyCardRow {
  sku_id: number | null;
  nm_id: number | null;
  vendor_code: string | null;
  barcode: string | null;
  title: string | null;
  brand: string | null;
  subject_name: string | null;
  business_verdict: {
    status: string;
    label?: string;
    short_text?: string;
    confidence: ConfidenceT;
  };
  money: {
    revenue: number | null;
    profit_after_ads: number | null;
    profit_before_ads: number | null;
    margin_percent: number | null;
    roi_percent: number | null;
    cogs: number | null;
    wb_expenses: number | null;
    ad_spend: number | null;
    stock_value: number | null;
  };
  stock: {
    stock_qty: number | null;
    days_of_stock: number | null;
    status: string;
    in_transit_qty: number | null;
  };
  price: {
    current_price: number | null;
    current_discounted_price: number | null;
    break_even_price: number | null;
    target_margin_price: number | null;
    safe_price_gap: number | null;
    status: string;
  };
  ads: {
    ad_spend: number | null;
    drr_percent: number | null;
    status: string;
  };
  data_trust: DataTrustInfo;
  next_action: NextAction | null;
  priority_score: number;
}

// ============================================================
// Etap 3 — /api/v1/money/* and /settings/business endpoint types
// ============================================================

export interface MMeta {
  account_id: number;
  date_from: string;
  date_to: string;
  currency: string;
  generated_at: string;
  data_trust: DataTrustInfo;
}

export interface MAnswer {
  business_status: string;
  title: string;
  short_text: string;
  main_problem?: string | null;
  main_next_step?: string | null;
}

export interface MMoneyFlowItem {
  code: string;
  label: string;
  amount: number;
  direction: "in" | "out" | "asset" | string;
  confidence: ConfidenceT;
  reason?: string;
}

export interface MRisk {
  code: string;
  title: string;
  business_impact?: string;
  priority?: "critical" | "high" | "medium" | "low" | string;
  affected_amount?: number | null;
  affected_count?: number | null;
  cta?: { label: string; href: string } | null;
  evidence_ledger?: EvidenceLedger | null;
  money_trust?: MoneyTrustInfo | null;
  resolver?: ProblemResolver | null;
}

export interface MTopCard {
  sku_id: number;
  nm_id: number | null;
  vendor_code: string | null;
  title: string | null;
  revenue: number;
  net_profit: number;
  stock_value: number;
  priority_score: number;
  status: string;
  evidence_ledger?: EvidenceLedger | null;
  money_trust?: MoneyTrustInfo | null;
}

export interface MNextAction {
  id: number;
  action_type: string;
  action_group: "business" | "data_fix" | string;
  priority: "critical" | "high" | "medium" | "low" | string;
  status: string;
  title: string;
  what_to_do: string;
  why: string;
  how_to_fix: string[];
  expected_effect_amount: number;
  required_cash: number;
  recommended_qty: number;
  unit_cost: number;
  current_stock: number;
  days_of_stock: number;
  lead_time_days: number;
  safety_days: number;
  confidence: ConfidenceT;
  deadline_hint: string;
  linked_entity: { sku_id: number; nm_id: number; vendor_code: string };
  blocked_reasons: string[];
  evidence_ledger?: EvidenceLedger | null;
  money_trust?: MoneyTrustInfo | null;
}

export interface MMoneySummary {
  computed_at?: string | null;
  cache_status?: string;
  data_version_hash?: string | null;
  meta: MMeta;
  trust?: DataTrustInfo | null;
  answer: MAnswer;
  store_answer?: Record<string, unknown>;
  revenue_sources?: Record<string, unknown>;
  finance_reconciliation?: Record<string, unknown>;
  cost_coverage?: Record<string, unknown>;
  quality?: Record<string, unknown>;
  expenses?: Record<string, unknown>;
  expense_breakdown?: Record<string, unknown> | null;
  profit_cascade?: Record<string, unknown> | null;
  kpis: {
    revenue: number;
    finance_confirmed_revenue: number;
    finance_reconciliation_operational_revenue: number;
    finance_difference_amount: number;
    finance_difference_percent: number;
    finance_reconciliation_status: string;
    supplier_cost_confirmed_revenue: number;
    supplier_cost_confirmed_revenue_percent: number;
    for_pay: number;
    net_profit_after_ads: number;
    margin_percent: number;
    roi_percent: number;
    cash_on_wb: number;
    available_for_withdraw: number;
    wb_expenses_total: number;
    direct_wb_expenses: number;
    stock_value: number;
    overstock_value: number;
    in_transit_value: number;
    stock_value_confidence: ConfidenceT;
    stock_value_reason: string;
    ad_spend: number;
    ad_spend_operational: number;
    ad_spend_finance: number;
    ad_spend_final: number;
    ad_spend_source: string;
    ad_spend_delta: number;
    ads_source_spend: number;
    ads_allocated_spend: number;
    ads_unallocated_spend: number;
    ads_allocation_status: string;
    seller_cogs: number;
    seller_other_expense: number;
    total_seller_expenses: number;
    total_seller_costs: number;
    unallocated_expenses: number;
    negative_profit_sku_count: number;
    blocked_data_sku_count: number;
    evidence_ledger?: Record<string, EvidenceLedger>;
    [k: string]: number | string | Record<string, EvidenceLedger> | undefined;
  };
  money_flow: {
    incoming: MMoneyFlowItem[];
    outgoing: MMoneyFlowItem[];
    cash_and_stock: MMoneyFlowItem[];
  };
  risk_summary: { critical_count: number; risks: MRisk[] };
  top_cards: {
    profitable: MTopCard[];
    loss_making: MTopCard[];
    stock_risk: MTopCard[];
    data_blocked: MTopCard[];
  };
  next_actions: MNextAction[];
  evidence_ledger?: Record<string, EvidenceLedger>;
}

export interface MCardItem {
  sku_id: number;
  nm_id: number | null;
  vendor_code: string | null;
  barcode: string | null;
  title: string | null;
  brand: string | null;
  subject_name: string | null;
  business_verdict: {
    status: string;
    label: string;
    short_text: string;
    confidence: ConfidenceT;
  };
  money: {
    revenue: number;
    for_pay: number;
    wb_expenses: {
      commission: number;
      acquiring_fee: number;
      wb_logistics?: number;
      wb_logistics_rebill?: number;
      logistics: number;
      paid_acceptance: number;
      storage: number;
      penalties: number;
      deductions: number;
      additional_payments: number;
      direct?: number;
      account_level?: number;
      account_level_logistics?: number;
      allocated_overhead?: number;
      unallocated?: number;
      unallocated_logistics?: number;
      logistics_mapping_status?: string;
      reason?: string;
      status: string;
    };
    ads: {
      spend: number;
      source_spend: number;
      allocated_spend: number;
      unallocated_spend: number;
      drr_percent: number;
      drr_percent_source: number;
      status: string;
      allocation_status: string;
      profit_allocation_status: string;
    };
    cogs: {
      unit_cost: number;
      estimated_cogs: number;
      truth_level: string;
      supplier_confirmed: boolean;
    };
    profit: {
      before_ads: number;
      after_ads: number;
      margin_after_ads_percent: number;
      roi_after_ads_percent: number;
      confidence: ConfidenceT;
    };
    wb_expenses_total: number;
    stock_value: number;
  };
  operations: {
    orders_count: number;
    cancelled_orders_count: number;
    cancel_rate_percent: number;
    sales_count: number;
    returns_count: number;
    return_rate_percent: number;
    net_units: number;
    issue: string;
  };
  stock: {
    quantity: number;
    quantity_full: number;
    stock_value: number;
    stock_value_confidence: ConfidenceT;
    stock_value_reason: string;
    days_of_stock: number;
    stock_status: string;
    in_transit_qty: number;
    in_transit_value: number;
  };
  price: {
    current_price: number;
    current_discounted_price: number;
    discount: number;
    break_even_price: number;
    break_even_price_final: number;
    break_even_price_estimated: number;
    target_margin_price: number;
    target_margin_price_final: number;
    target_margin_price_estimated: number;
    safe_price_gap: number;
    safe_price_gap_final: number;
    safe_price_gap_estimated: number;
    status: string;
    confidence: ConfidenceT;
    price_source: string;
    not_computable_reason: string;
  };
  ads: { spend: number; drr_percent: number; status: string };
  next_action: MNextAction | null;
  priority_score: number;
}

export interface MCardsResponse {
  total: number;
  limit: number;
  offset: number;
  summary: {
    profitable_count: number;
    loss_count: number;
    data_blocked_count: number;
    stock_risk_count: number;
    overstock_count: number;
    ad_risk_count: number;
    price_risk_count: number;
  };
  items: MCardItem[];
}

export interface MCardDetail {
  meta: MMeta;
  identity: {
    sku_id: number;
    nm_id: number;
    vendor_code: string;
    barcode: string;
    title: string;
    brand: string;
    subject_name: string;
  };
  answer: {
    status: string;
    title: string;
    short_text: string;
    decision: string;
    main_next_step: string;
    main_reason?: string;
  };
  money: MCardItem["money"];
  operations: MCardItem["operations"];
  funnel: {
    open_count: number;
    cart_count: number;
    order_count: number;
    buyout_count: number;
    cart_conversion_percent: number;
    order_conversion_percent: number;
    buyout_rate_percent: number;
    issue: string;
  };
  stock: MCardItem["stock"];
  price: MCardItem["price"];
  reconciliation: {
    mart_matches_article: boolean;
    mart_matches_finance: boolean;
    finance_matches_operational: boolean;
    revenue_matches_mart: boolean;
    mart_revenue_total: number;
    article_revenue_total: number;
    finance_report_revenue_total: number;
    difference_amount: number;
    difference_ratio_percent: number;
    status: string;
    mismatch_reason: string;
    root_cause_candidates: string[];
    next_debug_endpoint: string;
    business_effect: string;
  };
  problems: Array<{
    code: string;
    severity: string;
    title: string;
    business_impact: string;
    fix_hint: string;
  }>;
  next_actions: MNextAction[];
  // Article-level extras (present when called via /money/articles/{nm_id})
  article_summary?: {
    nm_id: number;
    title: string | null;
    revenue: number;
    profit_before_ads: number;
    ads_source_spend: number;
    profit_after_ads: number;
    stock_qty: number;
    stock_value: number;
    cancel_rate_percent: number;
    return_rate_percent: number;
    decision: string;
  };
  variant_breakdown?: Array<{
    sku_id: number | null;
    barcode: string | null;
    vendor_code: string | null;
    title: string | null;
    revenue: number;
    stock_qty: number;
    stock_value: number;
    allocated_ads_spend: number;
    source_ads_spend: number;
    net_profit_after_source_ads: number;
    next_action: MNextAction | null;
  }>;
  finality?: { state: DataTrustStateT; reason?: string };
}

export interface MArticleRow {
  nm_id: number;
  vendor_code?: string | null;
  title: string | null;
  brand: string | null;
  subject_name: string | null;
  variant_count: number;
  business_verdict: {
    status: string;
    label: string;
    short_text: string;
    confidence: ConfidenceT;
  };
  money_answer?: {
    status: string;
    title: string;
    short_text: string;
    decision: string;
    main_next_step: string;
  };
  money: MCardItem["money"] & {
    finance_confirmed_revenue?: number | null;
    finance_diff_amount?: number | null;
    finance_diff_percent?: number | null;
    owner_profit_after_overhead?: number | null;
  };
  stock: MCardItem["stock"] & { overstock_value?: number | null };
  operations?: {
    cancel_rate_percent?: number | null;
    return_rate_percent?: number | null;
  };
  ads: {
    spend: number;
    source_spend: number;
    allocated_spend: number;
    unallocated_spend: number;
    drr_percent: number;
    drr_percent_source: number;
    status: string;
    allocation_status: string;
  };
  finality?: { state: DataTrustStateT; reason?: string };
  profit_finality?: {
    state: "final" | "provisional" | "blocked" | string;
    reason?: string;
  };
  cost_finality?: {
    state: "final" | "provisional" | "blocked" | string;
    reason?: string;
  };
  finance_finality?: {
    state: "final" | "provisional" | "blocked" | string;
    reason?: string;
  };
  data_trust?: { state: DataTrustStateT; human_message?: string };
  flags?: {
    finance_mismatch?: boolean;
    supplier_cost_not_confirmed?: boolean;
    ads_risk?: boolean;
    overstock?: boolean;
    reorder_risk?: boolean;
    data_fix_required?: boolean;
  };
  next_action: MNextAction | null;
  priority_score: number;
}

export interface MArticlesResponse {
  total: number;
  limit: number;
  offset: number;
  summary: {
    profitable_count: number;
    loss_count: number;
    data_blocked_count: number;
    stock_risk_count: number;
    overstock_count: number;
    provisional_count: number;
    economically_profitable_count?: number;
    economically_loss_count?: number;
    final_profitable_count?: number;
    final_loss_count?: number;
    finance_mismatch_count?: number;
    ads_risk_count?: number;
  };
  items: MArticleRow[];
}

export interface MActionsResponse {
  total: number;
  limit: number;
  offset: number;
  summary: {
    critical: number;
    high: number;
    medium: number;
    low: number;
    business_actions_count: number;
    data_fix_actions_count: number;
  };
  groups: {
    data_fix_actions: MNextAction[];
    business_actions: MNextAction[];
  };
  items: MNextAction[];
}

export interface MDataBlocker {
  code: string;
  priority: "critical" | "high" | "medium" | "low" | string;
  title: string;
  affected_sku_count: number;
  affected_revenue: number;
  affected_amount?: number;
  current_value: number;
  required_value: number;
  unit: string;
  business_impact: string;
  how_to_fix: string[];
  related_endpoints: string[];
  exact_next_endpoint?: string;
  // ── Operator-facing fields (backend may or may not send them) ────────────
  simple_reason?: string | null;
  first_action?: string | null;
  success_check?: string[] | null;
  wait_or_fix_hint?: string | null;
  next_screen_path?: string | null;
  next_screen_label?: string | null;
  calculation_title?: string | null;
  calculation_formula?: string | null;
  calculation_inputs?: Array<{
    label?: string;
    value?: unknown;
    unit?: string;
    source?: string;
  }> | null;
  source_endpoints?: string[] | null;
  evidence_ledger?: EvidenceLedger | null;
  money_trust?: MoneyTrustInfo | null;
  resolver?: ProblemResolver | null;
  // ── Backend Truth & Classification (Phase 12) — optional ─────────────
  owner_type?: "user" | "system" | "admin" | "business" | "mixed" | null;
  fixability?: string | null;
  issue_nature?: string | null;
  can_user_fix_inside_platform?: boolean | null;
  is_manual_edit_allowed?: boolean | null;
  primary_action_code?: string | null;
  primary_action_label?: string | null;
  target_href?: string | null;
  disabled_reason?: string | null;
  recheck_mode?: string | null;
  // ── Pulse-card observability (backend confirmation flags) ────────────
  checked?: boolean | null;
  has_data?: boolean | null;
  has_risk?: boolean | null;
  source_freshness?: string | null;
}

export interface MDataBlockersResponse {
  computed_at?: string | null;
  cache_status?: string;
  data_version_hash?: string | null;
  meta: MMeta;
  overall_state: DataTrustStateT;
  overall_message?: string | null;
  can_generate_business_actions: boolean;
  blockers_count?: number;
  warnings_count?: number;
  open_issue_summary?: Record<string, number>;
  data_quality_summary?: {
    global_blockers_total?: number;
    financial_final_blockers_total?: number;
    open_issues_total?: number;
    all_open_issues_total?: number;
    blocking_open_issues_total?: number;
    critical_total?: number;
    error_total?: number;
    warning_total?: number;
    info_total?: number;
    message?: string;
    [k: string]: unknown;
  };
  blockers: MDataBlocker[];
  warnings?: MDataBlocker[];
  evidence_ledger?: Record<string, EvidenceLedger>;
}

export interface MFilters {
  date_presets: Array<{ key: string; label: string }>;
  card_statuses: Array<{ key: string; label: string }>;
  trust_states: Array<{ key: string; label: string }>;
  action_types: Array<{ key: string; label: string }>;
  brands: Array<{ key: string; label: string }>;
  subjects: Array<{ key: string; label: string }>;
  sort_options: Array<{ key: string; label: string }>;
  presets: Array<{ key: string; label: string }>;
}

export interface BusinessSettings {
  target_margin_rate: number;
  target_roi_percent: number;
  lead_time_days: number;
  safety_days: number;
  overstock_threshold_days: number;
  oos_threshold_days: number;
  min_profit_threshold: number;
  ad_drr_threshold_percent: number;
  pack_multiple: number;
  cost_trust_policy: "supplier_only" | "operator_baseline" | "mixed" | string;
  issue_aging: { pending_days: number; warning_days: number };
}
export interface BusinessSettingsResponse {
  account_id: number;
  settings: BusinessSettings;
  updated_at: string | null;
  comment: string | null;
}
