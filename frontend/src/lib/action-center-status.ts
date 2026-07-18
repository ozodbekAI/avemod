import {
  actionCenterImpactBucketForItem,
  actionCenterResultPageForItem,
  type ActionCenterItem,
} from "@/lib/action-center-contract";
import type { PortalResultEventsPage } from "@/lib/portal";
import { problemStatusLabel } from "@/lib/problem-ux-copy";
import { STATUSES, type DeskFilter, type ImpactBucketKey, ISSUE_TEXT_PATTERNS, IMPACT_BUCKETS } from "@/lib/action-center-labels";
import { guidedFixHref } from "@/lib/action-center-actions";
import { normalizeText } from "@/lib/action-center-utils";
import {
  resultStatusFromSummary,
  resultSummaryFromAction,
  type ProblemRowResultStatus,
} from "@/lib/action-center-results";

const SYSTEM_HANDLED_ACTION_CODES = new Set([
  "finance_reconciliation_mismatch",
  "finance_without_sale",
  "sale_without_finance",
  "order_without_sale_or_return",
]);

const CLOSED_ACTION_STATUSES = new Set([
  "done",
  "resolved",
  "closed",
  "ignored",
  "dismissed",
  "rejected",
]);

const RESULT_READY_STATUSES = new Set(["improved", "worse", "neutral"]);

export function actionCode(a: ActionCenterItem): string {
  return String(
    a.detector_code ?? a.problem_code ?? a.issue_code ?? a.action_type ?? "",
  )
    .trim()
    .toLowerCase();
}

export function problemCode(a: ActionCenterItem): string {
  return String(a.problem_code ?? a.detector_code ?? a.action_type ?? "")
    .trim()
    .toLowerCase();
}

export function isDynamicProblemAction(a: ActionCenterItem): boolean {
  return a.source_kind === "problem_engine";
}

export function isCheckerProblemBridge(a: ActionCenterItem): boolean {
  return a.source_kind === "checker" && a.is_problem_like;
}

export function isProblemLikeAction(a: ActionCenterItem): boolean {
  return a.is_problem_like;
}

export function dynamicProblemInstanceId(a: ActionCenterItem): number | null {
  return a.problem_instance_id;
}

export function actionAllowedActions(a: ActionCenterItem): string[] {
  return a.allowed_actions;
}

export function statusOptionsForAction(
  a: ActionCenterItem,
): typeof STATUSES {
  if (!isProblemLikeAction(a)) return STATUSES;
  const allowed = new Set(actionAllowedActions(a));
  const filtered = STATUSES.filter(
    (status) => status.value !== "ignored" || allowed.has("dismiss"),
  );
  const current = String(a.status ?? "").trim();
  if (current && !filtered.some((status) => status.value === current)) {
    const known = STATUSES.find((status) => status.value === current);
    return known
      ? [...filtered, known]
      : [...filtered, { value: current, label: problemStatusLabel(current) }];
  }
  return filtered;
}

export function isSystemHandledAction(a: ActionCenterItem): boolean {
  if (normalizeText(a.source_module) === "manual" || a.source_kind === "manual") {
    return false;
  }
  const code = actionCode(a);
  if (SYSTEM_HANDLED_ACTION_CODES.has(code)) return true;
  if (
    code.includes("finance") ||
    code.includes("sync") ||
    code.includes("scheduler") ||
    code.includes("task")
  ) {
    return true;
  }
  const href = String(guidedFixHref(a) ?? "");
  if (
    href.includes("finance_reconciliation_mismatch") ||
    href.includes("finance_without_sale") ||
    href.includes("sale_without_finance")
  ) {
    return true;
  }
  const text =
    `${a.title ?? ""} ${a.summary ?? ""} ${a.reason ?? ""} ${a.short_explanation ?? ""}`.toLowerCase();
  return text.includes("сумма продажи") && text.includes("отчете wb");
}

export function isClaimsAction(a: ActionCenterItem): boolean {
  return a.is_claims;
}

export function isBetaAction(a: ActionCenterItem): boolean {
  return a.is_beta || a.is_test_only;
}

export function isTestOnlyProblem(a: ActionCenterItem): boolean {
  return a.is_test_only;
}

export function actionMatchesIssueCode(
  a: ActionCenterItem,
  issueCode: string,
): boolean {
  const code = normalizeText(issueCode);
  if (!code) return true;
  const text = [
    actionCode(a),
    a.title,
    a.reason,
    a.summary,
    a.short_explanation,
    a.source_module,
    a.guided_fix?.href,
    a.guided_fix?.route_key,
    a.issue_code,
    a.problem_code,
    a.detector_code,
  ]
    .map(normalizeText)
    .join(" ");
  if (text.includes(code)) return true;
  return (ISSUE_TEXT_PATTERNS[code] ?? []).some((pattern) =>
    text.includes(pattern),
  );
}

export function normalizedStatus(value: unknown): string {
  return normalizeText(value).replaceAll(" ", "_");
}

export function isClosedAction(a: ActionCenterItem): boolean {
  return CLOSED_ACTION_STATUSES.has(normalizedStatus(a.status));
}

export function isUrgentAction(a: ActionCenterItem): boolean {
  if (isClosedAction(a)) return false;
  const priority = normalizeText(a.priority);
  const severity = normalizeText(a.severity);
  return (
    priority === "p0" ||
    priority === "p1" ||
    severity === "critical" ||
    severity === "high"
  );
}

export function isOverdueAction(a: ActionCenterItem, now: Date): boolean {
  void now;
  return !isClosedAction(a) && a.is_overdue === true;
}

export function isUnassignedAction(a: ActionCenterItem): boolean {
  return a.assigned_to_user_id == null;
}

export function isSameLocalDay(a: Date, b: Date): boolean {
  return (
    a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate()
  );
}

export function isDueTodayAction(a: ActionCenterItem, now: Date): boolean {
  if (isClosedAction(a) || !a.deadline_at) return false;
  const deadline = new Date(a.deadline_at);
  return !Number.isNaN(deadline.getTime()) && isSameLocalDay(deadline, now);
}

export function isDueTomorrowAction(a: ActionCenterItem, now: Date): boolean {
  if (!a.deadline_at) return false;
  const deadline = new Date(a.deadline_at);
  if (Number.isNaN(deadline.getTime())) return false;
  const tomorrow = new Date(now);
  tomorrow.setDate(tomorrow.getDate() + 1);
  return isSameLocalDay(deadline, tomorrow);
}

export function effectiveResultStatus(
  a: ActionCenterItem,
  problemResultsPage?: PortalResultEventsPage | null,
): ProblemRowResultStatus {
  const page = isDynamicProblemAction(a)
    ? actionCenterResultPageForItem(a, problemResultsPage)
    : null;
  return resultStatusFromSummary(resultSummaryFromAction(a, page));
}

export function hasResultAction(
  a: ActionCenterItem,
  problemResultsPage?: PortalResultEventsPage | null,
): boolean {
  return RESULT_READY_STATUSES.has(
    effectiveResultStatus(a, problemResultsPage),
  );
}

export function waitsForRecheckAction(
  a: ActionCenterItem,
  problemResultsPage?: PortalResultEventsPage | null,
): boolean {
  if (!a.can_recheck) return false;
  if (hasResultAction(a, problemResultsPage)) return false;
  const status = normalizedStatus(a.status);
  return (
    status === "done" ||
    status === "resolved" ||
    status === "in_progress" ||
    a.result_status === "pending_data" ||
    a.result_status === "not_enough_data"
  );
}

export function isAssignedToCurrentUser(
  a: ActionCenterItem,
  userId: number | null,
): boolean {
  return userId != null && a.assigned_to_user_id === userId;
}

export function isDataBlockerAction(a: ActionCenterItem): boolean {
  const impact = normalizeText(a.impact_type ?? a.money_trust?.impact_kind);
  const trust = normalizeText(a.trust_state ?? a.money_trust?.state);
  return (
    impact === "data_blocker" ||
    impact === "data_blocked" ||
    impact === "system_warning" ||
    trust === "blocked"
  );
}

export function impactBucketForAction(
  a: ActionCenterItem,
): ImpactBucketKey | null {
  return actionCenterImpactBucketForItem(a);
}

export function summarizeImpact(items: ActionCenterItem[]) {
  const base = Object.fromEntries(
    IMPACT_BUCKETS.map((bucket) => [
      bucket.key,
      { amount: 0, count: 0, hasMoney: false },
    ]),
  ) as Record<
    ImpactBucketKey,
    { amount: number; count: number; hasMoney: boolean }
  >;
  for (const item of items) {
    const bucket = impactBucketForAction(item);
    if (!bucket) continue;
    const amount =
      typeof item.money_impact_amount === "number"
        ? item.money_impact_amount
        : 0;
    base[bucket].count += 1;
    base[bucket].amount += amount;
    base[bucket].hasMoney ||= amount !== 0;
  }
  return base;
}

export function formatDeadline(
  a: ActionCenterItem,
  now: Date,
): { label: string; detail: string | null; overdue: boolean } {
  const value = a.deadline_at;
  if (!value) return { label: "Без срока", detail: null, overdue: false };
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return { label: value, detail: null, overdue: false };
  }
  const overdue = isOverdueAction(a, now);
  const timeLabel = date.toLocaleTimeString("ru-RU", {
    hour: "2-digit",
    minute: "2-digit",
  });
  const dateLabel = date.toLocaleDateString("ru-RU", {
    day: "2-digit",
    month: "2-digit",
  });
  const label = overdue
    ? "Просрочено"
    : isDueTodayAction(a, now)
      ? "Сегодня"
      : isDueTomorrowAction(a, now)
        ? "Завтра"
        : dateLabel;
  return {
    label,
    detail: timeLabel,
    overdue,
  };
}

export function assigneeLabel(
  a: ActionCenterItem,
  currentUserId: number | null,
): string {
  if (isAssignedToCurrentUser(a, currentUserId)) return "Я";
  return (
    a.assigned_to_user_name ??
    (a.assigned_to_user_id ? `ID ${a.assigned_to_user_id}` : "Не назначено")
  );
}

export function actionMatchesDeskFilter(
  a: ActionCenterItem,
  filter: DeskFilter,
  currentUserId: number | null,
  now: Date,
  problemResultsPage?: PortalResultEventsPage | null,
): boolean {
  if (filter === "all") return true;
  if (filter === "urgent") return isUrgentAction(a);
  if (filter === "mine") return isAssignedToCurrentUser(a, currentUserId);
  if (filter === "unassigned") return isUnassignedAction(a);
  if (filter === "overdue") return isOverdueAction(a, now);
  if (filter === "today") return isDueTodayAction(a, now);
  if (filter === "recheck") return waitsForRecheckAction(a, problemResultsPage);
  if (filter === "result") return hasResultAction(a, problemResultsPage);
  if (filter === "improved") {
    return effectiveResultStatus(a, problemResultsPage) === "improved";
  }
  if (filter === "worse") {
    return effectiveResultStatus(a, problemResultsPage) === "worse";
  }
  if (filter === "blockers") return isDataBlockerAction(a);
  return true;
}

export function roleRank(role: string | null | undefined): number {
  const ranks: Record<string, number> = {
    viewer: 0,
    operator: 1,
    manager: 2,
    admin: 3,
    superuser: 4,
  };
  return ranks[normalizeText(role)] ?? 0;
}

export function userAccountRole(
  user: {
    is_superuser?: boolean;
    accounts?: Array<{ id: number; role: string }>;
  } | null,
  accountId: number | null | undefined,
): string {
  if (user?.is_superuser) return "superuser";
  if (accountId == null) return "viewer";
  return (
    user?.accounts?.find((account) => Number(account.id) === Number(accountId))
      ?.role ?? "viewer"
  );
}

export function actionEvidenceLedger(a: ActionCenterItem) {
  return a.evidence_ledger;
}

export function actionRecheckRule(
  a: ActionCenterItem,
  ledger: ActionCenterItem["evidence_ledger"],
): string {
  return String(
    a.recheck_rule ??
      ledger?.recheck_rule ??
      "Обновите Центр действий после изменения статуса или данных источника.",
  );
}

export function actionProductIdentity(a: ActionCenterItem): string {
  return [
    a.nm_id ? `nm ${a.nm_id}` : null,
    a.vendor_code ? `арт. ${a.vendor_code}` : null,
  ]
    .filter(Boolean)
    .join(" / ");
}
