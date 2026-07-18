// Canonical Truth & Classification helper (Phase 12).
//
// The backend is now the single source of truth for:
//   - owner_type              (user / system / admin / business / mixed)
//   - fixability              (fix_in_platform / wait_for_sync / system_only / admin_only / business_decision / …)
//   - issue_nature            (data_blocker / sync_waiting / system_check / business_signal / finance_investigation / …)
//   - can_user_fix_inside_platform (boolean)
//   - is_manual_edit_allowed  (boolean)
//   - primary_action_code / primary_action_label / target_href / disabled_reason / recheck_mode
//
// The frontend MUST NOT override backend truth. This helper reads backend
// fields first and only falls back to code-based heuristics when the backend
// omits the field entirely.

import type { DataQualityIssue, MDataBlocker } from "@/lib/api";

export type OwnerKind = "user" | "system" | "admin" | "business" | "mixed" | "aggregate";
export type Fixability =
  | "fix_in_platform"
  | "fix_in_wb_cabinet"
  | "wait_for_sync"
  | "system_only"
  | "admin_only"
  | "business_decision"
  | "no_action";
export type IssueNature =
  | "data_blocker"
  | "sync_waiting"
  | "system_check"
  | "business_signal"
  | "finance_investigation"
  | "content_fix"
  | "wait_for_wb_report";

export const ISSUE_NATURE_LABEL: Record<string, string> = {
  data_blocker: "Блокер данных",
  sync_waiting: "Ждёт синхронизации",
  system_check: "Системная проверка",
  business_signal: "Бизнес-сигнал",
  finance_investigation: "Финансовая проверка",
  content_fix: "Правка карточки",
  wait_for_wb_report: "Ждём отчёт WB",
};

export const ISSUE_NATURE_TONE: Record<string, string> = {
  data_blocker:          "border-destructive/40 text-destructive",
  sync_waiting:          "border-amber-500/40 text-amber-700 dark:text-amber-300",
  system_check:          "border-blue-500/40 text-blue-700 dark:text-blue-300",
  business_signal:       "border-primary/40 text-primary",
  finance_investigation: "border-purple-500/40 text-purple-700 dark:text-purple-300",
  content_fix:           "border-emerald-500/40 text-emerald-700 dark:text-emerald-300",
  wait_for_wb_report:    "border-amber-500/40 text-amber-700 dark:text-amber-300",
};

export const FIXABILITY_SECTION: Record<string, string> = {
  fix_in_platform:    "can_fix_here",
  fix_in_wb_cabinet:  "can_fix_here",
  wait_for_sync:      "waiting_sync",
  system_only:        "system_check",
  admin_only:         "admin",
  business_decision:  "business_signal",
  no_action:          "waiting_sync",
};

// Sections used by the Data Fix page.
export const SECTION_LABEL: Record<string, string> = {
  can_fix_here:          "Можно исправить здесь",
  missing_data:          "Не хватает данных",
  waiting_sync:          "Ждёт синхронизации",
  system_check:          "Системные проверки",
  business_signal:       "Бизнес-сигналы",
  finance_investigation: "Финансовое расследование",
  admin:                 "Передано администратору",
};

type ClassifiableInput = {
  code?: string | null;
  owner_type?: string | null;
  fixability?: string | null;
  issue_nature?: string | null;
  can_user_fix_inside_platform?: boolean | null;
  is_manual_edit_allowed?: boolean | null;
  primary_action_code?: string | null;
  primary_action_label?: string | null;
  target_href?: string | null;
  disabled_reason?: string | null;
  recheck_mode?: string | null;
};

export function classifyIssue(input: ClassifiableInput | DataQualityIssue | MDataBlocker | null | undefined): {
  owner: OwnerKind;
  fixability: Fixability | null;
  nature: IssueNature | null;
  section: string;
  canUserFix: boolean;
  showApply: boolean;
  natureLabel: string | null;
  natureTone: string | null;
} {
  const i = (input ?? {}) as ClassifiableInput;
  const code = String(i.code ?? "").toLowerCase();

  // 1. Backend truth first
  const ownerBackend = (i.owner_type ?? null) as OwnerKind | null;
  const fixabilityBackend = (i.fixability ?? null) as Fixability | null;
  const natureBackend = (i.issue_nature ?? null) as IssueNature | null;
  const canUserFixBackend = i.can_user_fix_inside_platform;

  // 2. Fallbacks by code (only when backend omits)
  const owner: OwnerKind = ownerBackend ?? fallbackOwnerFromCode(code);
  const nature: IssueNature | null = natureBackend ?? fallbackNatureFromCode(code, owner);
  const fixability: Fixability | null =
    fixabilityBackend ?? fallbackFixabilityFromOwnerNature(owner, nature);
  const canUserFix =
    typeof canUserFixBackend === "boolean"
      ? canUserFixBackend
      : fixability === "fix_in_platform";

  // 3. Section for Data Fix layout
  let section = "waiting_sync";
  if (fixability && FIXABILITY_SECTION[fixability]) {
    section = FIXABILITY_SECTION[fixability];
  } else if (nature === "data_blocker") {
    section = "can_fix_here";
  } else if (nature === "sync_waiting") {
    section = "waiting_sync";
  } else if (nature === "system_check") {
    section = "system_check";
  } else if (nature === "business_signal") {
    section = "business_signal";
  } else if (nature === "finance_investigation") {
    section = "finance_investigation";
  } else if (owner === "admin") {
    section = "admin";
  } else if (owner === "user" || owner === "mixed") {
    section = "can_fix_here";
  }

  // 4. Apply/fix controls only visible when user can fix in-platform.
  const showApply = canUserFix && fixability === "fix_in_platform";

  return {
    owner,
    fixability,
    nature,
    section,
    canUserFix,
    showApply,
    natureLabel: nature ? ISSUE_NATURE_LABEL[nature] ?? null : null,
    natureTone: nature ? ISSUE_NATURE_TONE[nature] ?? null : null,
  };
}

function fallbackOwnerFromCode(code: string): OwnerKind {
  if (
    code.includes("finance_reconciliation") ||
    code.includes("without_sale") ||
    code.includes("without_finance") ||
    code.includes("sync") ||
    code.includes("scheduler") ||
    code.includes("task_failed") ||
    code.includes("missed_load")
  ) return "system";
  if (
    code.includes("manual_cost") ||
    code.includes("supplier_cost") ||
    code.includes("seller_other_expense") ||
    code.includes("title") ||
    code.includes("description") ||
    code.includes("characteristic") ||
    code.includes("media") ||
    code.includes("photo") ||
    code.includes("image")
  ) return "user";
  if (
    code.includes("business_decision") ||
    code.includes("price_review") ||
    code.includes("stock_decision")
  ) return "business";
  return "mixed";
}

function fallbackNatureFromCode(code: string, owner: OwnerKind): IssueNature | null {
  if (code.includes("stock_without_sales") || code.includes("sales_without_stock")) return "sync_waiting";
  if (code.includes("missing_chrt_id") || code.includes("card_mapping")) return "sync_waiting";
  if (code.includes("order_without_sale_or_return")) return "sync_waiting";
  if (code.includes("finance_reconciliation") || code.includes("without_sale") || code.includes("without_finance"))
    return "finance_investigation";
  if (code.includes("ads_allocation")) return "business_signal";
  if (code.includes("sync") || code.includes("task_failed") || code.includes("scheduler")) return "system_check";
  if (owner === "system") return "system_check";
  if (owner === "admin") return "system_check";
  if (owner === "business") return "business_signal";
  if (code.includes("manual_cost") || code.includes("supplier_cost") || code.includes("expense_unclassified")) return "data_blocker";
  if (code.includes("title") || code.includes("photo") || code.includes("image") || code.includes("description")) return "content_fix";
  return null;
}

function fallbackFixabilityFromOwnerNature(owner: OwnerKind, nature: IssueNature | null): Fixability | null {
  if (nature === "sync_waiting" || nature === "wait_for_wb_report") return "wait_for_sync";
  if (nature === "system_check") return "system_only";
  if (nature === "finance_investigation") return "admin_only";
  if (nature === "business_signal") return "business_decision";
  if (nature === "content_fix") return "fix_in_wb_cabinet";
  if (nature === "data_blocker") return "fix_in_platform";
  if (owner === "admin") return "admin_only";
  if (owner === "system") return "system_only";
  if (owner === "business") return "business_decision";
  if (owner === "user") return "fix_in_platform";
  return null;
}

// ─────────────────────────────────────────────────────────────────────────
// Primary action label — backend first, specific fallback by nature/code
// ─────────────────────────────────────────────────────────────────────────

type ActionResolveInput = ClassifiableInput & { next_screen_label?: string | null };

export function resolvePrimaryActionLabel(input: ActionResolveInput | null | undefined): string {
  const i = (input ?? {}) as ActionResolveInput;
  if (i.primary_action_label && String(i.primary_action_label).trim())
    return String(i.primary_action_label);
  const code = String(i.code ?? "").toLowerCase();
  const nature = (i.issue_nature ?? "") as string;

  // Specific fallbacks explicitly requested by product spec
  if (code.includes("ads_allocation")) return "Открыть рекламу в Деньгах";
  if (code.includes("finance_reconciliation")) return "Открыть сверку финансов";
  if (code.includes("stock_without_sales")) return "Открыть товар";
  if (code.includes("missing_chrt_id")) return "Запустить синхронизацию карточек";
  if (code.includes("sales_without_stock")) return "Запустить синхронизацию остатков";
  if (code.includes("order_without_sale_or_return")) return "Перепроверить после синхронизации";
  if (nature === "system_check" || nature === "admin_only")
    return "Создать задачу администратору";

  // Semantic next-screen label from backend, if provided
  if (i.next_screen_label && String(i.next_screen_label).trim())
    return String(i.next_screen_label);

  return "Открыть";
}

export function resolveTargetHref(input: ActionResolveInput | null | undefined, fallback?: string | null): string | null {
  const i = (input ?? {}) as ActionResolveInput;
  if (i.target_href && String(i.target_href).trim()) return String(i.target_href);
  return fallback ?? null;
}
