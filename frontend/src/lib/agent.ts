import { api } from "./api";
import { API_ENDPOINTS } from "./endpoints";

export type AgentIntent =
  | "help"
  | "admin_answer"
  | "product_search"
  | "product_details"
  | "stock_export"
  | "title_update"
  | "page_explain"
  | "reputation_agent"
  | "scenario_create"
  | "pricing_agent"
  | "insights_report"
  | "strategy_advice"
  | "module_navigate"
  | "open_logistics"
  | "open_action_center"
  | "open_checker"
  | "open_pricing"
  | "open_stock_control"
  | "open_money"
  | "api_action";

export type AgentActionType =
  | "answer"
  | "navigate"
  | "open_product_picker"
  | "open_title_editor"
  | "open_preview_dialog"
  | "download_file"
  | "create_manual_task"
  | "api_request";

export interface AgentMessageRequest {
  account_id: number;
  message: string;
  intent?: AgentIntent | null;
  selected_nm_id?: number | null;
  new_title?: string | null;
  context?: Record<string, unknown>;
}

export interface AgentToolSpec {
  name: string;
  intent: AgentIntent;
  title: string;
  description: string;
  required_args: string[];
  write_policy: string;
  input_schema: Record<string, unknown>;
}

export interface AgentToolsResponse {
  protocol: "finance-agent-tools-v1";
  tools: AgentToolSpec[];
  modules: Record<string, Record<string, string>>;
  api_actions?: Record<string, Record<string, unknown>>;
  direct_marketplace_writes: boolean;
}

export interface AgentToolCallRequest {
  account_id: number;
  tool_name: string;
  arguments?: Record<string, unknown>;
  context?: Record<string, unknown>;
}

export interface AgentMcpRequest {
  jsonrpc?: "2.0";
  id?: number | string | null;
  method: "initialize" | "tools/list" | "tools/call";
  params?: Record<string, unknown>;
}

export interface AgentMcpResponse {
  jsonrpc: "2.0";
  id?: number | string | null;
  result?: Record<string, unknown> | null;
  error?: Record<string, unknown> | null;
}

export interface AgentProductRef {
  nm_id: number;
  vendor_code?: string | null;
  title?: string | null;
  brand?: string | null;
  subject_name?: string | null;
  thumbnail_url?: string | null;
}

export interface AgentUIAction {
  type: AgentActionType;
  title: string;
  description?: string | null;
  href?: string | null;
  method?: string | null;
  confirm_required?: boolean;
  payload?: Record<string, unknown>;
}

export interface AgentMessageResponse {
  status: "ok" | "needs_input" | "blocked" | "error";
  mode: "ai" | "ai_fallback";
  intent: AgentIntent;
  message: string;
  actions: AgentUIAction[];
  products: AgentProductRef[];
  suggestions: string[];
  warnings: string[];
  audit?: Record<string, unknown>;
}

export interface AgentScenarioRead {
  id: number;
  account_id: number;
  name: string;
  description?: string | null;
  scenario_type: string;
  status: string;
  approval_policy: string;
  auto_execute_enabled: boolean;
  scope_json: Record<string, unknown>;
  schedule_json: Record<string, unknown>;
  guardrails_json: Record<string, unknown>;
  actions_json: Record<string, unknown>[];
  next_run_at?: string | null;
  last_run_at?: string | null;
  last_run_status?: string | null;
  created_at: string;
  updated_at: string;
}

export interface AgentScenarioListResponse {
  status: "ok" | "empty";
  total: number;
  limit: number;
  offset: number;
  items: AgentScenarioRead[];
}

export interface AgentScenarioRunRead {
  id: number;
  account_id: number;
  scenario_id: number;
  trigger: string;
  status: string;
  dry_run: boolean;
  actions_preview_json: Record<string, unknown>[];
  actions_executed: number;
  actions_blocked: number;
  output_json: Record<string, unknown>;
  estimated_cost_usd: string | number;
  created_at: string;
  updated_at: string;
}

export interface AgentScenarioRunListResponse {
  status: "ok" | "empty";
  total: number;
  limit: number;
  offset: number;
  items: AgentScenarioRunRead[];
}

export interface AgentFinanceSummary {
  status: "ok";
  account_id: number;
  scenarios_total: number;
  active_scenarios: number;
  runs_total: number;
  runs_last_30d: number;
  failed_runs_last_30d: number;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  estimated_cost_usd: string | number;
  ledger_items: Record<string, unknown>[];
}

export function sendAgentMessage(payload: AgentMessageRequest) {
  return api<AgentMessageResponse>(API_ENDPOINTS.portal.agentMessage, {
    method: "POST",
    body: payload,
  });
}

export function fetchAgentTools(accountId: number) {
  return api<AgentToolsResponse>(
    `${API_ENDPOINTS.portal.agentTools}?account_id=${encodeURIComponent(String(accountId))}`,
  );
}

export function callAgentTool(payload: AgentToolCallRequest) {
  return api<AgentMessageResponse>(API_ENDPOINTS.portal.agentToolCall, {
    method: "POST",
    body: payload,
  });
}

export function callAgentMcp(accountId: number, payload: AgentMcpRequest) {
  return api<AgentMcpResponse>(
    `${API_ENDPOINTS.portal.agentMcp}?account_id=${encodeURIComponent(String(accountId))}`,
    {
      method: "POST",
      body: { jsonrpc: "2.0", ...payload },
    },
  );
}

export function createAgentManualTask(payload: Record<string, unknown>) {
  return api<unknown>(API_ENDPOINTS.portal.agentManualTask, {
    method: "POST",
    body: payload,
  });
}

export function fetchAgentScenarios(accountId: number) {
  return api<AgentScenarioListResponse>(
    `${API_ENDPOINTS.portal.agentScenarios}?account_id=${encodeURIComponent(String(accountId))}`,
  );
}

export function fetchAgentScenarioRuns(accountId: number, scenarioId?: number) {
  const params = new URLSearchParams({ account_id: String(accountId) });
  if (scenarioId) params.set("scenario_id", String(scenarioId));
  return api<AgentScenarioRunListResponse>(
    `${API_ENDPOINTS.portal.agentScenarioRuns}?${params.toString()}`,
  );
}

export function fetchAgentFinance(accountId: number) {
  return api<AgentFinanceSummary>(
    `${API_ENDPOINTS.portal.agentFinance}?account_id=${encodeURIComponent(String(accountId))}`,
  );
}
