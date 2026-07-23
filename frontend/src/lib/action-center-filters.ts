import type { ActionCenterItem } from "@/lib/action-center-contract";
import type { ProblemResultStatus } from "@/lib/portal";

export type ActionCenterView =
  | "all"
  | "urgent"
  | "today"
  | "mine"
  | "unassigned"
  | "overdue"
  | "blockers"
  | "recheck"
  | "result"
  | "improved"
  | "worse";

export type ActionCenterSortKey =
  | "priority"
  | "money_impact"
  | "deadline"
  | "last_seen_at"
  | "last_status_changed_at"
  | "result_status";

export type ActionCenterSlaFilter =
  | "all"
  | "ok"
  | "due_soon"
  | "overdue"
  | "no_deadline"
  | "today";

export type ActionCenterResultFilter = "all" | ProblemResultStatus;

export type ActionCenterFilterState = {
  view: ActionCenterView;
  q: string;
  status: string;
  source_module: string;
  severity: string;
  priority: string;
  trust_state: string;
  impact_type: string;
  problem_code: string;
  assignee: string;
  sla: ActionCenterSlaFilter;
  result_status: ActionCenterResultFilter;
  include_beta: boolean;
  sort: ActionCenterSortKey;
};

export type ActionCenterDigestResultEvent = {
  event_type?: string | null;
  outcome?: string | null;
  payload?: Record<string, unknown> | null;
  comparison?: Record<string, unknown> | null;
  after_snapshot?: Record<string, unknown> | null;
  confidence?: string | null;
  created_at?: string | null;
};

export type ActionCenterDailyDigest = {
  newToday: number;
  dueToday: number;
  overdue: number;
  recheckCompleted: number;
  resultImproved: number;
  resultWorse: number;
};

export type ActionCenterWeeklySummary = {
  closedTasks: number;
  reopenedTasks: number;
  confirmedMeasuredOutcomes: number;
  estimatedOpportunitiesHandled: number;
};

export const ACTION_CENTER_DEFAULT_FILTERS: ActionCenterFilterState = {
  view: "all",
  q: "",
  status: "all",
  source_module: "all",
  severity: "all",
  priority: "all",
  trust_state: "all",
  impact_type: "all",
  problem_code: "all",
  assignee: "all",
  sla: "all",
  result_status: "all",
  include_beta: false,
  sort: "priority",
};

export const ACTION_CENTER_SAVED_VIEWS: Array<{
  value: ActionCenterView;
  label: string;
}> = [
  { value: "all", label: "Все" },
  { value: "urgent", label: "Срочные" },
  { value: "mine", label: "Мои задачи" },
  { value: "unassigned", label: "Без ответственного" },
  { value: "overdue", label: "Просрочено" },
  { value: "blockers", label: "Блокеры данных" },
  { value: "recheck", label: "Ждёт перепроверки" },
  { value: "result", label: "Есть результат" },
  { value: "worse", label: "Стало хуже" },
];

export const ACTION_CENTER_SORT_OPTIONS: Array<{
  value: ActionCenterSortKey;
  label: string;
}> = [
  { value: "priority", label: "Приоритет" },
  { value: "money_impact", label: "Денежный эффект" },
  { value: "deadline", label: "Срок" },
  { value: "last_seen_at", label: "Последнее появление" },
  { value: "last_status_changed_at", label: "Изменение статуса" },
  { value: "result_status", label: "Результат" },
];

const VIEW_VALUES = new Set<ActionCenterView>(
  ACTION_CENTER_SAVED_VIEWS.map((item) => item.value),
);

const SORT_VALUES = new Set<ActionCenterSortKey>(
  ACTION_CENTER_SORT_OPTIONS.map((item) => item.value),
);

const SLA_VALUES = new Set<ActionCenterSlaFilter>([
  "all",
  "ok",
  "due_soon",
  "overdue",
  "no_deadline",
  "today",
]);

const RESULT_VALUES = new Set<ActionCenterResultFilter>([
  "all",
  "pending_data",
  "improved",
  "worse",
  "neutral",
  "not_enough_data",
]);

const CLOSED_STATUSES = new Set([
  "done",
  "resolved",
  "closed",
  "ignored",
  "dismissed",
  "rejected",
]);

const RESULT_READY_STATUSES = new Set<ProblemResultStatus>([
  "improved",
  "worse",
  "neutral",
]);

const PRIO_ORDER: Record<string, number> = {
  p0: 0,
  critical: 0,
  p1: 1,
  high: 1,
  p2: 2,
  medium: 2,
  p3: 3,
  low: 3,
  p4: 4,
};

const RESULT_ORDER: Record<string, number> = {
  worse: 0,
  improved: 1,
  neutral: 2,
  pending_data: 3,
  not_enough_data: 4,
};

function text(value: unknown): string {
  return String(value ?? "")
    .trim()
    .toLowerCase();
}

function firstString(
  search: Record<string, unknown>,
  ...keys: string[]
): string {
  for (const key of keys) {
    const value = search[key];
    if (typeof value === "string" && value.trim()) return value.trim();
  }
  return "";
}

function normalizedOption(value: string, fallback = "all"): string {
  return value.trim() || fallback;
}

function normalizedView(value: string): ActionCenterView {
  return VIEW_VALUES.has(value as ActionCenterView)
    ? (value as ActionCenterView)
    : ACTION_CENTER_DEFAULT_FILTERS.view;
}

function normalizedSort(value: string): ActionCenterSortKey {
  return SORT_VALUES.has(value as ActionCenterSortKey)
    ? (value as ActionCenterSortKey)
    : ACTION_CENTER_DEFAULT_FILTERS.sort;
}

function normalizedSla(value: string): ActionCenterSlaFilter {
  return SLA_VALUES.has(value as ActionCenterSlaFilter)
    ? (value as ActionCenterSlaFilter)
    : ACTION_CENTER_DEFAULT_FILTERS.sla;
}

function normalizedResult(value: string): ActionCenterResultFilter {
  return RESULT_VALUES.has(value as ActionCenterResultFilter)
    ? (value as ActionCenterResultFilter)
    : ACTION_CENTER_DEFAULT_FILTERS.result_status;
}

function boolFromSearch(value: unknown): boolean {
  if (value === true) return true;
  if (typeof value !== "string") return false;
  return ["1", "true", "yes"].includes(value.trim().toLowerCase());
}

export function actionCenterStateFromSearch(
  search: Record<string, unknown>,
): ActionCenterFilterState {
  const source = firstString(search, "source_module", "source");
  const code = firstString(search, "problem_code", "code");
  return {
    view: normalizedView(firstString(search, "view")),
    q: firstString(search, "q"),
    status: normalizedOption(firstString(search, "status")),
    source_module: normalizedOption(source),
    severity: normalizedOption(firstString(search, "severity")),
    priority: normalizedOption(firstString(search, "priority")),
    trust_state: normalizedOption(firstString(search, "trust_state")),
    impact_type: normalizedOption(firstString(search, "impact_type")),
    problem_code: normalizedOption(code),
    assignee: normalizedOption(firstString(search, "assignee")),
    sla: normalizedSla(firstString(search, "sla")),
    result_status: normalizedResult(firstString(search, "result_status")),
    include_beta: boolFromSearch(search.beta ?? search.include_beta),
    sort: normalizedSort(firstString(search, "sort")),
  };
}

export function actionCenterSearchFromState(
  state: ActionCenterFilterState,
): Record<string, string | undefined> {
  return {
    view:
      state.view !== ACTION_CENTER_DEFAULT_FILTERS.view
        ? state.view
        : undefined,
    q: state.q.trim() ? state.q.trim() : undefined,
    status: state.status !== "all" ? state.status : undefined,
    source_module:
      state.source_module !== "all" ? state.source_module : undefined,
    severity: state.severity !== "all" ? state.severity : undefined,
    priority: state.priority !== "all" ? state.priority : undefined,
    trust_state: state.trust_state !== "all" ? state.trust_state : undefined,
    impact_type: state.impact_type !== "all" ? state.impact_type : undefined,
    problem_code: state.problem_code !== "all" ? state.problem_code : undefined,
    assignee: state.assignee !== "all" ? state.assignee : undefined,
    sla: state.sla !== "all" ? state.sla : undefined,
    result_status:
      state.result_status !== "all" ? state.result_status : undefined,
    beta: state.include_beta ? "1" : undefined,
    sort:
      state.sort !== ACTION_CENTER_DEFAULT_FILTERS.sort
        ? state.sort
        : undefined,
  };
}

export function actionCenterQuickSearchText(item: ActionCenterItem): string {
  return [
    item.title,
    item.short_explanation,
    item.reason,
    item.summary,
    item.next_step,
    item.nm_id,
    item.vendor_code,
    item.problem_code,
    item.detector_code,
    item.issue_code,
    item.action_type,
    item.entity_id,
    item.assigned_to_user_name,
    item.assigned_to_user_id,
  ]
    .map(text)
    .filter(Boolean)
    .join(" ");
}

export function actionCenterMatchesSearch(
  item: ActionCenterItem,
  query: string,
): boolean {
  const q = text(query);
  if (!q) return true;
  return actionCenterQuickSearchText(item).includes(q);
}

export function actionCenterStatusIsClosed(item: ActionCenterItem): boolean {
  return CLOSED_STATUSES.has(text(item.status).replaceAll(" ", "_"));
}

export function actionCenterIsUrgent(item: ActionCenterItem): boolean {
  if (actionCenterStatusIsClosed(item)) return false;
  const priority = text(item.priority);
  const severity = text(item.severity);
  return (
    priority === "p0" ||
    priority === "p1" ||
    severity === "critical" ||
    severity === "high"
  );
}

export function actionCenterIsDataBlocker(item: ActionCenterItem): boolean {
  const impact = text(item.impact_type ?? item.money_trust?.impact_kind);
  const trust = text(item.trust_state ?? item.money_trust?.state);
  return (
    impact === "data_blocker" ||
    impact === "data_blocked" ||
    impact === "system_warning" ||
    trust === "blocked"
  );
}

function isSameLocalDay(a: Date, b: Date): boolean {
  return (
    a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate()
  );
}

function isWithinDays(
  value: string | null | undefined,
  now: Date,
  days: number,
): boolean {
  if (!value) return false;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return false;
  const diffMs = now.getTime() - date.getTime();
  return diffMs >= 0 && diffMs <= days * 24 * 60 * 60 * 1000;
}

function eventCreatedToday(
  event: ActionCenterDigestResultEvent,
  now: Date,
): boolean {
  if (!event.created_at) return false;
  const date = new Date(event.created_at);
  return !Number.isNaN(date.getTime()) && isSameLocalDay(date, now);
}

function eventNotificationType(event: ActionCenterDigestResultEvent): string {
  return text(event.payload?.notification_type);
}

function eventOutcome(event: ActionCenterDigestResultEvent): string {
  return text(
    event.outcome ??
      event.payload?.outcome ??
      event.comparison?.outcome ??
      event.payload?.comparison?.outcome,
  );
}

function hasMeasuredComparison(event: ActionCenterDigestResultEvent): boolean {
  const comparison = event.comparison ?? event.payload?.comparison;
  const metrics =
    comparison && typeof comparison === "object" ? comparison.metrics : null;
  if (
    metrics &&
    typeof metrics === "object" &&
    Object.keys(metrics).length > 0
  ) {
    return true;
  }
  const after = event.after_snapshot ?? event.payload?.after_snapshot;
  return Boolean(
    after && typeof after === "object" && Object.keys(after).length > 0,
  );
}

export function actionCenterIsDueToday(
  item: ActionCenterItem,
  now: Date,
): boolean {
  if (actionCenterStatusIsClosed(item) || !item.deadline_at) return false;
  const deadline = new Date(item.deadline_at);
  return !Number.isNaN(deadline.getTime()) && isSameLocalDay(deadline, now);
}

export function actionCenterIsOverdue(item: ActionCenterItem): boolean {
  return !actionCenterStatusIsClosed(item) && item.is_overdue === true;
}

function priorityRank(item: ActionCenterItem): number {
  return (
    PRIO_ORDER[text(item.priority)] ??
    PRIO_ORDER[text(item.severity)] ??
    Number.MAX_SAFE_INTEGER
  );
}

function moneyRank(item: ActionCenterItem): number {
  return typeof item.money_impact_amount === "number"
    ? Math.abs(item.money_impact_amount)
    : -1;
}

function dateRank(
  value: string | null | undefined,
  missingLast = true,
): number {
  if (!value) return missingLast ? Number.MAX_SAFE_INTEGER : 0;
  const time = new Date(value).getTime();
  if (Number.isNaN(time)) return missingLast ? Number.MAX_SAFE_INTEGER : 0;
  return time;
}

export function actionCenterMatchesView(
  item: ActionCenterItem,
  view: ActionCenterView,
  context: {
    currentUserId?: number | null;
    now?: Date;
    resultStatus?: ProblemResultStatus;
    waitsForRecheck?: boolean;
  } = {},
): boolean {
  const now = context.now ?? new Date();
  const resultStatus = context.resultStatus ?? item.result_status;
  if (view === "all") return true;
  if (view === "urgent") return actionCenterIsUrgent(item);
  if (view === "mine") {
    return (
      context.currentUserId != null &&
      item.assigned_to_user_id === context.currentUserId
    );
  }
  if (view === "unassigned") return item.assigned_to_user_id == null;
  if (view === "overdue") return actionCenterIsOverdue(item);
  if (view === "today") return actionCenterIsDueToday(item, now);
  if (view === "blockers") return actionCenterIsDataBlocker(item);
  if (view === "recheck") return context.waitsForRecheck === true;
  if (view === "result") return RESULT_READY_STATUSES.has(resultStatus);
  if (view === "improved") return resultStatus === "improved";
  if (view === "worse") return resultStatus === "worse";
  return true;
}

export function actionCenterMatchesFilters(
  item: ActionCenterItem,
  state: ActionCenterFilterState,
  context: {
    currentUserId?: number | null;
    now?: Date;
    resultStatus?: ProblemResultStatus;
    waitsForRecheck?: boolean;
  } = {},
): boolean {
  if (!actionCenterMatchesSearch(item, state.q)) return false;
  if (state.status !== "all" && text(item.status) !== state.status)
    return false;
  if (
    state.source_module !== "all" &&
    text(item.source_module) !== state.source_module
  )
    return false;
  if (state.severity !== "all" && text(item.severity) !== state.severity)
    return false;
  if (state.priority !== "all" && text(item.priority) !== state.priority)
    return false;
  if (
    state.trust_state !== "all" &&
    text(item.trust_state) !== state.trust_state
  )
    return false;
  if (
    state.impact_type !== "all" &&
    text(item.impact_type) !== state.impact_type
  )
    return false;
  if (
    state.problem_code !== "all" &&
    text(item.problem_code ?? item.detector_code ?? item.action_type) !==
      state.problem_code
  )
    return false;
  if (state.assignee === "me") {
    if (
      context.currentUserId == null ||
      item.assigned_to_user_id !== context.currentUserId
    )
      return false;
  } else if (state.assignee === "unassigned") {
    if (item.assigned_to_user_id != null) return false;
  } else if (state.assignee !== "all") {
    if (String(item.assigned_to_user_id ?? "") !== state.assignee) return false;
  }
  if (state.sla === "today") {
    if (!actionCenterIsDueToday(item, context.now ?? new Date())) return false;
  } else if (state.sla !== "all" && item.sla_state !== state.sla) {
    return false;
  }
  const resultStatus = context.resultStatus ?? item.result_status;
  if (state.result_status !== "all" && resultStatus !== state.result_status)
    return false;
  return actionCenterMatchesView(item, state.view, {
    ...context,
    resultStatus,
  });
}

export function actionCenterShouldHideBetaSignal(
  isBetaOrTestOnly: boolean,
  context: { canUseBeta?: boolean; includeBeta?: boolean },
): boolean {
  return (
    isBetaOrTestOnly &&
    !(context.canUseBeta === true && context.includeBeta === true)
  );
}

export function actionCenterMatchesProblemInstanceDeepLink(
  item: Pick<ActionCenterItem, "problem_instance_id">,
  problemInstanceId: unknown,
): boolean {
  const normalized = text(problemInstanceId);
  if (!normalized) return true;
  const id = item.problem_instance_id;
  return id != null && String(id).trim() === normalized;
}

export function sortActionCenterItems(
  items: ActionCenterItem[],
  sort: ActionCenterSortKey,
  context: {
    resultStatus?: (item: ActionCenterItem) => ProblemResultStatus;
  } = {},
): ActionCenterItem[] {
  return [...items].sort((left, right) => {
    if (sort === "money_impact") {
      return (
        moneyRank(right) - moneyRank(left) ||
        priorityRank(left) - priorityRank(right)
      );
    }
    if (sort === "deadline") {
      return dateRank(left.deadline_at) - dateRank(right.deadline_at);
    }
    if (sort === "last_seen_at") {
      const leftDate = dateRank(left.last_seen_at ?? left.created_at, false);
      const rightDate = dateRank(right.last_seen_at ?? right.created_at, false);
      return rightDate - leftDate;
    }
    if (sort === "last_status_changed_at") {
      return (
        dateRank(right.last_status_changed_at, false) -
        dateRank(left.last_status_changed_at, false)
      );
    }
    if (sort === "result_status") {
      const leftStatus = context.resultStatus?.(left) ?? left.result_status;
      const rightStatus = context.resultStatus?.(right) ?? right.result_status;
      return (
        (RESULT_ORDER[leftStatus] ?? 99) - (RESULT_ORDER[rightStatus] ?? 99) ||
        priorityRank(left) - priorityRank(right)
      );
    }
    return (
      priorityRank(left) - priorityRank(right) ||
      dateRank(left.deadline_at) - dateRank(right.deadline_at)
    );
  });
}

export function buildActionCenterDailyDigest(
  items: ActionCenterItem[],
  resultEvents: ActionCenterDigestResultEvent[] = [],
  now = new Date(),
): ActionCenterDailyDigest {
  const todayEvents = resultEvents.filter((event) =>
    eventCreatedToday(event, now),
  );
  return {
    newToday: items.filter((item) =>
      isWithinDays(item.created_at ?? item.last_seen_at, now, 1),
    ).length,
    dueToday: items.filter((item) => actionCenterIsDueToday(item, now)).length,
    overdue: items.filter(actionCenterIsOverdue).length,
    recheckCompleted: todayEvents.filter((event) => {
      const type = text(event.event_type);
      return (
        type === "recheck_result" ||
        eventNotificationType(event) === "recheck_completed"
      );
    }).length,
    resultImproved: todayEvents.filter((event) => {
      const type = eventNotificationType(event);
      return type === "result_improved" || eventOutcome(event) === "improved";
    }).length,
    resultWorse: todayEvents.filter((event) => {
      const type = eventNotificationType(event);
      return type === "result_worsened" || eventOutcome(event) === "worse";
    }).length,
  };
}

export function buildActionCenterWeeklySummary(
  items: ActionCenterItem[],
  resultEvents: ActionCenterDigestResultEvent[] = [],
  now = new Date(),
): ActionCenterWeeklySummary {
  const weekEvents = resultEvents.filter((event) =>
    isWithinDays(event.created_at, now, 7),
  );
  return {
    closedTasks: items.filter(
      (item) =>
        actionCenterStatusIsClosed(item) &&
        isWithinDays(
          item.last_status_changed_at ?? item.last_seen_at ?? item.created_at,
          now,
          7,
        ),
    ).length,
    reopenedTasks:
      items.filter(
        (item) =>
          text(item.status) === "reopened" &&
          isWithinDays(
            item.last_status_changed_at ?? item.last_seen_at ?? item.created_at,
            now,
            7,
          ),
      ).length +
      weekEvents.filter((event) => {
        const type = text(event.event_type);
        return (
          type === "reopened" ||
          eventNotificationType(event) === "issue_reopened"
        );
      }).length,
    confirmedMeasuredOutcomes: weekEvents.filter((event) => {
      const outcome = eventOutcome(event);
      return (
        ["improved", "worse", "neutral"].includes(outcome) &&
        hasMeasuredComparison(event) &&
        event.payload?.saved_money_claimed !== true
      );
    }).length,
    estimatedOpportunitiesHandled: items.filter((item) => {
      const opportunity =
        text(item.impact_type) === "opportunity" ||
        text(item.trust_state) === "opportunity" ||
        text(item.money_trust?.state) === "opportunity";
      return (
        opportunity &&
        actionCenterStatusIsClosed(item) &&
        isWithinDays(
          item.last_status_changed_at ?? item.last_seen_at ?? item.created_at,
          now,
          7,
        )
      );
    }).length,
  };
}
