import type { ActionCenterItem } from "@/lib/action-center-contract";
import type { ActionCenterSortKey } from "@/lib/action-center-filters";

export type ActionCenterGroup = {
  key: string;
  items: ActionCenterItem[];
  priority?: string | null;
  problem_code?: string | null;
  source_module?: string | null;
  title?: string | null;
  total_impact_amount?: number | null;
};

const ACTION_CENTER_PRIORITY_ORDER: Record<string, number> = {
  P0: 0,
  P1: 1,
  P2: 2,
  P3: 3,
  P4: 4,
  p0: 0,
  critical: 0,
  high: 1,
  medium: 2,
  low: 3,
};

export function groupActionCenterItems(
  items: ActionCenterItem[],
  sortBy: ActionCenterSortKey = "priority",
): ActionCenterGroup[] {
  const groups = new Map<string, ActionCenterGroup>();
  const order: string[] = [];
  for (const action of items) {
    const problemCode = String(action.problem_code ?? action.issue_code ?? "")
      .trim()
      .toLowerCase();
    const sourceModule = String(action.source_module ?? "").trim().toLowerCase();
    const key = problemCode
      ? `${sourceModule || "unknown"}|problem:${problemCode}`
      : `${action.action_type ?? action.title ?? ""}|${action.short_explanation ?? action.reason ?? ""}|${action.priority ?? ""}`;
    if (!groups.has(key)) {
      groups.set(key, {
        key,
        items: [],
        priority: action.priority,
        problem_code: problemCode || null,
        source_module: action.source_module ?? null,
        title: action.title ?? null,
        total_impact_amount: null,
      });
      order.push(key);
    }
    const group = groups.get(key)!;
    group.items.push(action);
    if (typeof action.money_impact_amount === "number" && Number.isFinite(action.money_impact_amount)) {
      group.total_impact_amount = (group.total_impact_amount ?? 0) + action.money_impact_amount;
    }
  }
  const list = order.map((key) => groups.get(key)!);
  if (sortBy === "priority") {
    list.sort((left, right) => {
      const leftPriority = ACTION_CENTER_PRIORITY_ORDER[left.priority ?? ""] ?? 9;
      const rightPriority = ACTION_CENTER_PRIORITY_ORDER[right.priority ?? ""] ?? 9;
      return leftPriority - rightPriority;
    });
  }
  return list;
}

export function actionCenterRowIdentity(
  action: ActionCenterItem,
  index: number,
  parentKey: string,
): string {
  return `${parentKey}:${action.source_module ?? "x"}:${action.source_id ?? action.action_id ?? action.id ?? index}`;
}
