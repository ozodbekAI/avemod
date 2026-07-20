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

export function createAgentManualTask(payload: Record<string, unknown>) {
  return api<unknown>(API_ENDPOINTS.portal.agentManualTask, {
    method: "POST",
    body: payload,
  });
}
