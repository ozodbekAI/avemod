import {
  actionCenterItemToResultsSearch,
  type ActionCenterAllowedActionItem,
  type ActionCenterItem,
  type ActionCenterSolveMapStep,
} from "@/lib/action-center-contract";
import { actionCenterWorkScreenHref } from "@/lib/action-center-routing";
import { problemActionLabel } from "@/lib/problem-ux-copy";

export type RenderableAction = ActionCenterAllowedActionItem & {
  label: string;
  href: string;
  external: boolean;
};

export type ActionDraft = {
  status: string;
  assigned_to_user_id: string;
  deadline_at: string;
  last_comment: string;
};

export type RecheckResult = {
  status: "ok" | "error";
  checkedAt: string;
  message: string;
};

const ROUTE_KEY_MAP: Record<string, (a: ActionCenterItem) => string | null> = {
  data_fix: () => "/data-fix",
  costs: () => "/costs",
  product: (a) => (a.nm_id ? `/products/${a.nm_id}` : null),
  claims: () => "/claims",
  reputation: () => "/reputation",
  photo: (a) =>
    a.nm_id
      ? `/photo-studio?nm_id=${a.nm_id}&source=action_center`
      : "/photo-studio?source=action_center",
};

const CODE_HREF_MAP: Record<string, string> = {
  missing_manual_cost: "/costs?focus=missing-costs",
  seller_other_expense_missing: "/costs?focus=other-expenses",
  manual_cost_ambiguous_match: "/costs?focus=relink-sku",
  manual_cost_unresolved_sku: "/costs?focus=relink-sku",
  unmatched_sku: "/data-fix?code=unmatched_sku",
  expense_unclassified: "/data-fix?code=expense_unclassified",
  ads_overallocated_to_profitability:
    "/ads?focus=allocation&rowFilter=overallocated_or_unallocated",
  ads_not_allocated_to_profitability:
    "/ads?focus=allocation&rowFilter=overallocated_or_unallocated",
  stock_without_sales: "/stock-control?tab=return",
  sales_without_stock: "/stock-control?tab=supply",
  missing_chrt_id: "/data-fix?code=missing_chrt_id",
};

export function numericActionId(a: ActionCenterItem): number | null {
  return a.action_id;
}

export function toDatetimeLocal(value?: string | null): string {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toISOString().slice(0, 16);
}

export function fromDatetimeLocal(value: string): string | null {
  if (!value) return null;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date.toISOString();
}

export function parseOptionalUserId(value: string): number | null {
  if (!value.trim()) return null;
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : null;
}

export function initialDraft(a: ActionCenterItem): ActionDraft {
  return {
    status: String(a.status && a.status !== "open" ? a.status : "new"),
    assigned_to_user_id:
      a.assigned_to_user_id == null ? "" : String(a.assigned_to_user_id),
    deadline_at: toDatetimeLocal(a.deadline_at),
    last_comment: a.last_comment ?? "",
  };
}

export function allowedActionLabel(code: string): string {
  return problemActionLabel(code);
}

export function resultsHrefForAction(a: ActionCenterItem): string {
  const search = actionCenterItemToResultsSearch(a);
  const params = new URLSearchParams();
  if (search.action_id) params.set("action_id", search.action_id);
  if (search.source_module) params.set("source_module", search.source_module);
  if (search.problem_instance_id) {
    params.set("problem_instance_id", search.problem_instance_id);
  }
  if (search.problem_code) params.set("problem_code", search.problem_code);
  if (search.nm_id) params.set("nm_id", search.nm_id);
  const query = params.toString();
  return query ? `/results?${query}` : "/results";
}

export function allowedActionHref(
  code: string,
  a: ActionCenterItem,
): string | null {
  if (code === "open_results" && !a.problem_instance_id) return resultsHrefForAction(a);
  const contextualHref = actionCenterWorkScreenHref(code, {
    action_id: a.action_id,
    problem_instance_id: a.problem_instance_id,
    nm_id: a.nm_id,
  });
  if (contextualHref) return contextualHref;
  if (code === "classify_expense") return "/data-fix?code=expense_unclassified";
  if (code === "open_results") return resultsHrefForAction(a);
  if (code === "create_task") return null;
  if (code === "assign" || code === "recheck" || code === "dismiss") {
    return null;
  }
  return null;
}

export function actionItemHref(
  item: ActionCenterAllowedActionItem,
  a: ActionCenterItem,
): string | null {
  return allowedActionHref(item.code, a);
}

export function guidedFixHref(a: ActionCenterItem): string | null {
  const fix = a.guided_fix;
  if (fix?.href) return fix.href;
  if (fix?.route_key && ROUTE_KEY_MAP[fix.route_key]) {
    return ROUTE_KEY_MAP[fix.route_key](a);
  }
  const code = String(
    a.issue_code ?? a.problem_code ?? a.action_type ?? "",
  ).toLowerCase();
  if (code && CODE_HREF_MAP[code]) return CODE_HREF_MAP[code];
  return null;
}

export function guidedFixLabel(a: ActionCenterItem): string {
  const raw = String(a.guided_fix?.label ?? "").trim();
  const normalized = raw.toLowerCase();
  if (!raw) return "Исправить";
  if (normalized === "open data fix") return "Открыть починку данных";
  if (normalized === "open finance") return "Открыть финансы";
  if (normalized === "open costs") return "Открыть себестоимость";
  return raw;
}

export function renderableActionFromItem(
  item: ActionCenterAllowedActionItem,
  a: ActionCenterItem,
): RenderableAction | null {
  const href = actionItemHref(item, a);
  if (!href) return null;
  return {
    ...item,
    label: allowedActionLabel(item.code),
    href,
    external: !href.startsWith("/"),
  };
}

function solveMapStepIsReady(step: ActionCenterSolveMapStep): boolean {
  return step.status === "available" || step.status === "ready";
}

function solveMapStepIsBlocked(step: ActionCenterSolveMapStep): boolean {
  return step.status === "blocked" || step.status === "waiting_for_data";
}

function renderableActionFromSolveMapStep(
  step: ActionCenterSolveMapStep,
  a: ActionCenterItem,
): RenderableAction | null {
  if (!step.action_code || step.action_code === "open_product") return null;
  const href = step.target_href ?? allowedActionHref(step.action_code, a);
  if (!href) return null;
  const actionItem = a.allowed_action_items.find(
    (item) => item.code === step.action_code,
  );
  const enabled = solveMapStepIsReady(step) && (actionItem?.enabled ?? true);
  return {
    code: step.action_code,
    original_code: actionItem?.original_code ?? step.action_code,
    enabled,
    disabled_reason:
      step.blocking_reason ?? actionItem?.disabled_reason ?? null,
    requires_preview: actionItem?.requires_preview ?? false,
    requires_diff: actionItem?.requires_diff ?? false,
    requires_confirm: actionItem?.requires_confirm ?? false,
    requires_audit: actionItem?.requires_audit ?? false,
    is_dangerous: actionItem?.is_dangerous ?? false,
    label: step.title || allowedActionLabel(step.action_code),
    href,
    external: !href.startsWith("/"),
  };
}

export function actionRequirementText(
  item: ActionCenterAllowedActionItem,
): string | null {
  const requirements = [
    item.requires_preview ? "предпросмотр" : null,
    item.requires_diff ? "сравнение изменений" : null,
    item.requires_confirm ? "подтверждение" : null,
    item.requires_audit ? "аудит" : null,
  ].filter(Boolean);
  return requirements.length
    ? `Перед применением: ${requirements.join(", ")}.`
    : null;
}

export function primaryActionForItem(a: ActionCenterItem): RenderableAction | null {
  const solveMapAction =
    a.solve_map?.steps
      .slice()
      .sort((left, right) => left.order - right.order)
      .map((step) => renderableActionFromSolveMapStep(step, a))
      .find((item): item is RenderableAction => !!item && item.enabled) ?? null;
  if (solveMapAction) return solveMapAction;
  return (
    a.allowed_action_items
      .map((item) => renderableActionFromItem(item, a))
      .find(
        (item): item is RenderableAction =>
          !!item && item.enabled && item.code !== "open_product",
      ) ??
    a.allowed_action_items
      .map((item) => renderableActionFromItem(item, a))
      .find((item): item is RenderableAction => !!item && item.enabled) ??
    null
  );
}

export function primaryDisabledActionForItem(
  a: ActionCenterItem,
): RenderableAction | null {
  const solveMapAction =
    a.solve_map?.steps
      .slice()
      .sort((left, right) => left.order - right.order)
      .filter(solveMapStepIsBlocked)
      .map((step) => renderableActionFromSolveMapStep(step, a))
      .find((item): item is RenderableAction => !!item && !item.enabled) ?? null;
  if (solveMapAction) return solveMapAction;
  return (
    a.allowed_action_items
      .map((item) => renderableActionFromItem(item, a))
      .find((item): item is RenderableAction => !!item && !item.enabled) ?? null
  );
}
