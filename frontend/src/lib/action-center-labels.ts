import { ACTION_CENTER_SAVED_VIEWS, type ActionCenterView } from "@/lib/action-center-filters";

export const PRIO_COLORS: Record<string, string> = {
  P0: "bg-destructive/15 text-destructive border-destructive/30",
  P1: "bg-warning/15 text-warning border-warning/30",
  P2: "bg-primary/10 text-primary border-primary/30",
  P3: "bg-muted text-muted-foreground border-border",
  P4: "bg-muted text-muted-foreground border-border",
  p0: "bg-destructive/15 text-destructive border-destructive/30",
  critical: "bg-destructive/15 text-destructive border-destructive/30",
  high: "bg-warning/15 text-warning border-warning/30",
  medium: "bg-primary/10 text-primary border-primary/30",
  low: "bg-muted text-muted-foreground border-border",
};

export const STATUSES: { value: string; label: string }[] = [
  { value: "new", label: "Новые" },
  { value: "in_progress", label: "В работе" },
  { value: "done", label: "Выполнено" },
  { value: "postponed", label: "Отложено" },
  { value: "ignored", label: "Отклонено" },
  { value: "blocked", label: "Заблокировано" },
];

export const SOURCE_MODULES: { value: string; label: string }[] = [
  { value: "finance", label: "Финансы" },
  { value: "data_quality", label: "Качество данных" },
  { value: "costs", label: "Себестоимость" },
  { value: "checker", label: "Проверка карточек" },
  { value: "problem_engine", label: "Динамические проблемы" },
  { value: "manual", label: "Вручную" },
  { value: "stockops", label: "Остатки" },
  { value: "grouping_beta", label: "Группировка" },
  { value: "reputation", label: "Репутация" },
  { value: "claims", label: "Претензии" },
  { value: "photo", label: "Фото" },
  { value: "experiments", label: "Эксперименты" },
];

export const PROBLEM_CODE_FILTERS: { value: string; label: string }[] = [
  { value: "missing_cost_blocks_profit", label: "Нет себестоимости" },
  { value: "negative_unit_profit", label: "Отрицательная прибыль" },
  { value: "overstock_slow_moving", label: "Залежавшийся остаток" },
  { value: "low_stock_risk", label: "Риск дефицита" },
  { value: "ads_spend_without_profit", label: "Реклама без прибыли" },
  { value: "promo_not_profitable", label: "Промо без прибыли" },
  { value: "price_below_safe_margin", label: "Цена ниже безопасной" },
  { value: "dead_stock", label: "Мертвый остаток" },
  { value: "fast_stock_depletion", label: "Быстрое исчерпание" },
];

export const TRUST_STATE_FILTERS: { value: string; label: string }[] = [
  { value: "confirmed", label: "Подтверждено" },
  { value: "provisional", label: "Предварительно" },
  { value: "estimated", label: "Оценка" },
  { value: "opportunity", label: "Возможность" },
  { value: "blocked", label: "Заблокировано" },
  { value: "test_only", label: "Тест" },
];

export const IMPACT_TYPE_FILTERS: { value: string; label: string }[] = [
  { value: "confirmed_loss", label: "Подтвержденный убыток" },
  { value: "probable_loss", label: "Вероятный убыток" },
  { value: "blocked_cash", label: "Замороженные деньги" },
  { value: "lost_sales_risk", label: "Риск потери продаж" },
  { value: "opportunity", label: "Возможность" },
  { value: "data_blocker", label: "Блокер данных" },
  { value: "system_warning", label: "Системное предупреждение" },
];

export type DeskFilter = ActionCenterView;

export const DESK_FILTERS = ACTION_CENTER_SAVED_VIEWS;

export const SEVERITY_FILTERS: { value: string; label: string }[] = [
  { value: "critical", label: "Критичная" },
  { value: "high", label: "Высокая" },
  { value: "medium", label: "Средняя" },
  { value: "low", label: "Низкая" },
];

export const ASSIGNEE_FILTERS: { value: string; label: string }[] = [
  { value: "all", label: "Все ответственные" },
  { value: "me", label: "Назначены мне" },
  { value: "unassigned", label: "Без ответственного" },
];

export const SLA_FILTERS: { value: string; label: string }[] = [
  { value: "all", label: "Любой срок" },
  { value: "today", label: "Срок сегодня" },
  { value: "due_soon", label: "Скоро срок" },
  { value: "overdue", label: "Просрочены" },
  { value: "ok", label: "В сроке" },
  { value: "no_deadline", label: "Без срока" },
];

export const RESULT_STATUS_FILTERS: { value: string; label: string }[] = [
  { value: "all", label: "Любой результат" },
  { value: "pending_data", label: "Ждём данных" },
  { value: "improved", label: "Есть улучшение" },
  { value: "worse", label: "Стало хуже" },
  { value: "neutral", label: "Без изменений" },
  { value: "not_enough_data", label: "Нет данных" },
];

export type EmptyStateKind =
  | "sync_required"
  | "no_data"
  | "no_issues"
  | "data_missing"
  | "module_disabled"
  | "beta_module"
  | "error";

export const ACTION_CENTER_EMPTY_STATES: Record<
  EmptyStateKind,
  { title: string; body: string; action: string }
> = {
  sync_required: {
    title: "Нужна синхронизация",
    body: "Подключите или обновите данные, чтобы платформа смогла найти проблемы.",
    action:
      "Запустите синхронизацию или дождитесь ближайшего обновления данных.",
  },
  no_data: {
    title: "Нет данных",
    body: "По выбранным фильтрам данных пока нет.",
    action:
      "Расширьте период, сбросьте фильтры или проверьте подключение источников.",
  },
  no_issues: {
    title: "Проблем не найдено",
    body: "По текущим фильтрам активных проблем нет.",
    action:
      "Вернитесь после следующей синхронизации или снимите фильтры, чтобы увидеть все задачи.",
  },
  data_missing: {
    title: "Не хватает данных",
    body: "Платформа не может подтвердить расчёт без недостающих данных.",
    action:
      "Заполните недостающие справочники, себестоимость или связи SKU и запустите проверку снова.",
  },
  module_disabled: {
    title: "Модуль отключён",
    body: "Этот раздел недоступен для текущего аккаунта или роли.",
    action: "Включите модуль в настройках или обратитесь к администратору.",
  },
  beta_module: {
    title: "Бета-модуль",
    body: "Этот сигнал доступен только в бета-режиме или для администратора.",
    action:
      "Администратор может включить показ бета/тестовых сигналов на этой странице.",
  },
  error: {
    title: "Не удалось загрузить данные",
    body: "Проверьте подключение или повторите попытку.",
    action:
      "Данные не изменены — платформа просто не смогла ответить. Попробуйте обновить страницу.",
  },
};

export const ACTION_CENTER_EMPTY_STATE_VARIANT: Record<
  EmptyStateKind,
  "needs_sync" | "no_data" | "no_problems" | "missing_data" | "disabled" | "beta" | "error"
> = {
  sync_required: "needs_sync",
  no_data: "no_data",
  no_issues: "no_problems",
  data_missing: "missing_data",
  module_disabled: "disabled",
  beta_module: "beta",
  error: "error",
};

export const PRIORITIES = ["P0", "P1", "P2", "P3", "P4"];

export function sourceModuleLabel(value: string | null | undefined): string {
  if (!value) return "—";
  return (
    SOURCE_MODULES.find((item) => item.value === value)?.label ??
    value.replaceAll("_", " ")
  );
}

export function sourceSyncStateLabel(value: string | null | undefined): string {
  const key = String(value ?? "unknown")
    .trim()
    .toLowerCase();
  const labels: Record<string, string> = {
    source_updated: "Источник обновлён",
    shadow_updated: "Обновлено в Центре действий",
    shadow_only: "Только состояние Центра действий",
    unknown: "Неизвестно",
  };
  return labels[key] ?? key.replaceAll("_", " ");
}

export function canUpdateReasonLabel(value: string | null | undefined): string {
  const key = String(value ?? "")
    .trim()
    .toLowerCase();
  const labels: Record<string, string> = {
    create_case_first: "Сначала создайте кейс претензии.",
    read_only_recommendation: "Рекомендация только для чтения.",
    external_reputation_recommendation:
      "Рекомендация репутации: подготовьте черновик и подтверждайте публикацию вручную.",
    generated_recommendation_not_persisted:
      "Сгенерированная рекомендация ещё не сохранена как задача.",
    data_quality_issue_requires_source_workflow:
      "Обновите проблему через исходный процесс исправления данных.",
    cost_issue_requires_cost_upload_or_mapping:
      "Загрузите или сопоставьте себестоимость в разделе себестоимости.",
    checker_setup_or_external_issue_requires_source_workflow:
      "Обновите проблему через проверку карточки.",
    finance_recommendation_without_persisted_action_id:
      "Финансовая рекомендация пока доступна только для просмотра.",
    problem_instance_requires_dynamic_engine_workflow:
      "Динамическая проблема обновляется через связанный рабочий процесс.",
  };
  if (!key) return "Только рекомендация";
  if (labels[key]) return labels[key];
  if (key.endsWith("_stored_as_action_center_shadow")) {
    return "Статус сохранён в Центре действий, исходная система не обновлена напрямую.";
  }
  if (key.endsWith("_source_not_found_or_not_directly_mutable")) {
    return "Исходная запись не найдена или не поддерживает прямое обновление.";
  }
  return key.replaceAll("_", " ");
}

export function priorityLabel(value: string | null | undefined): string {
  const key = String(value ?? "")
    .trim()
    .toLowerCase();
  const labels: Record<string, string> = {
    p0: "Критично",
    critical: "Критично",
    p1: "Высокий",
    high: "Высокий",
    p2: "Средний",
    medium: "Средний",
    p3: "Низкий",
    low: "Низкий",
    p4: "Когда будет время",
  };
  return labels[key] ?? String(value ?? "—");
}

export const ISSUE_FOCUS_LABELS: Record<string, string> = {
  ads_overallocated_to_profitability:
    "Рекламные расходы привязаны к прибыли с риском двойного учета",
  ads_not_allocated_to_profitability:
    "Рекламные расходы не полностью привязаны к прибыли",
  stock_without_sales: "Есть остатки без продаж",
  sales_without_stock: "Есть продажи без подтвержденного остатка",
  missing_chrt_id: "Есть варианты без идентификатора размера",
  missing_manual_cost: "Не хватает себестоимости",
  seller_other_expense_missing: "Не хватает прочих расходов",
  unmatched_sku: "SKU не привязан",
};

export const ISSUE_TEXT_PATTERNS: Record<string, string[]> = {
  ads_overallocated_to_profitability: [
    "ads_overallocated_to_profitability",
    "переаллокац",
    "двойного учета",
    "двойного учёта",
    "overallocated",
  ],
  ads_not_allocated_to_profitability: [
    "ads_not_allocated_to_profitability",
    "не распредел",
    "unallocated",
  ],
  stock_without_sales: [
    "stock_without_sales",
    "остатки без продаж",
    "остаток без продаж",
    "излиш",
    "overstock",
    "frozen",
  ],
  sales_without_stock: [
    "sales_without_stock",
    "продажи без подтвержденного остатка",
    "продажи без подтверждённого остатка",
    "дефицит",
    "shortage",
    "out_of_stock",
  ],
  missing_chrt_id: [
    "missing_chrt_id",
    "идентификатор размера",
    "chrt",
    "размер",
  ],
  missing_manual_cost: ["missing_manual_cost", "себестоимость"],
  seller_other_expense_missing: [
    "seller_other_expense_missing",
    "прочие расходы",
  ],
  unmatched_sku: ["unmatched_sku", "sku не привязан", "перепривяз"],
};

export function issueFocusLabel(code: string): string {
  return ISSUE_FOCUS_LABELS[code] ?? code.replaceAll("_", " ");
}

export function unavailableLabel(value: unknown): string {
  const key = String(value ?? "").trim();
  const match = SOURCE_MODULES.find((m) => m.value === key);
  return match?.label ?? key;
}

export type ImpactBucketKey =
  | "confirmed_loss"
  | "probable_risk"
  | "blocked_cash"
  | "opportunity"
  | "data_blocker";

export const IMPACT_BUCKETS: {
  key: ImpactBucketKey;
  label: string;
  tone: string;
}[] = [
  {
    key: "confirmed_loss",
    label: "Подтверждённый убыток",
    tone: "border-destructive/30 bg-destructive/5 text-destructive",
  },
  {
    key: "probable_risk",
    label: "Вероятный риск",
    tone: "border-amber-500/35 bg-amber-500/10 text-amber-800 dark:text-amber-300",
  },
  {
    key: "blocked_cash",
    label: "Замороженные деньги",
    tone: "border-orange-500/35 bg-orange-500/10 text-orange-800 dark:text-orange-300",
  },
  {
    key: "opportunity",
    label: "Возможность роста",
    tone: "border-sky-500/30 bg-sky-500/10 text-sky-700 dark:text-sky-300",
  },
  {
    key: "data_blocker",
    label: "Блокеры данных",
    tone: "border-slate-500/30 bg-slate-500/10 text-slate-700 dark:text-slate-300",
  },
];
