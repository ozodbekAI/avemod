// UX словарь. Переводит технические коды бэкенда в бизнес-язык.

export type CardStatus =
  | "data_blocked"
  | "profitable"
  | "profitable_scale"
  | "protect_stock"
  | "loss"
  | "loss_making"
  | "overstock"
  | "price_risk"
  | "ad_risk"
  | "watch"
  | "new_card"
  | "stock_risk"
  | "provisional"
  | "SCALE"
  | "STOP_PURCHASE"
  | "PROTECT_STOCK"
  | "DATA_BLOCKED";

export type DataTrustState = "trusted" | "test_only" | "data_blocked";
export type Confidence = "high" | "medium" | "low";

export const CARD_STATUS_COPY: Record<
  string,
  {
    title: string;
    subtitle: string;
    tone: "success" | "warning" | "danger" | "info" | "muted";
  }
> = {
  // backend keys
  data_blocked: {
    title: "Сначала почините данные",
    subtitle: "Рекомендация по карточке пока заблокирована",
    tone: "danger",
  },
  profitable: {
    title: "Прибыльная",
    subtitle: "Карточка зарабатывает деньги",
    tone: "success",
  },
  profitable_scale: {
    title: "Можно масштабировать",
    subtitle: "Прибыльная, показатели хорошие",
    tone: "success",
  },
  protect_stock: {
    title: "Берегите остаток",
    subtitle: "Прибыльная, но остатков мало",
    tone: "warning",
  },
  stock_risk: {
    title: "Риск остатков",
    subtitle: "Может закончиться",
    tone: "warning",
  },
  loss: {
    title: "Убыточная",
    subtitle: "Карточка тянет прибыль вниз",
    tone: "danger",
  },
  loss_making: {
    title: "Убыточная",
    subtitle: "Карточка тянет прибыль вниз",
    tone: "danger",
  },
  overstock: {
    title: "Заморожен остаток",
    subtitle: "Товар медленно оборачивается",
    tone: "warning",
  },
  price_risk: {
    title: "Риск по цене",
    subtitle: "Цена ставит прибыль под угрозу",
    tone: "warning",
  },
  ad_risk: {
    title: "Риск по рекламе",
    subtitle: "Реклама может съедать прибыль",
    tone: "warning",
  },
  watch: {
    title: "Наблюдение",
    subtitle: "Резких действий не требуется",
    tone: "info",
  },
  provisional: {
    title: "Предварительный анализ",
    subtitle: "Цифры приблизительные",
    tone: "info",
  },
  new_card: {
    title: "Новая карточка",
    subtitle: "Идёт сбор данных",
    tone: "info",
  },
  // upper-case verdict keys (top_cards/business_verdict)
  SCALE: {
    title: "Масштабировать",
    subtitle: "Карточка прибыльная",
    tone: "success",
  },
  STOP_PURCHASE: {
    title: "Не закупать заново",
    subtitle: "Карточка убыточная",
    tone: "danger",
  },
  PROTECT_STOCK: {
    title: "Берегите остаток",
    subtitle: "Прибыльная, но остатков мало",
    tone: "warning",
  },
  DATA_BLOCKED: {
    title: "Сначала почините данные",
    subtitle: "Решение заблокировано",
    tone: "danger",
  },
};

export const ACTION_COPY: Record<string, string> = {
  FIX_COST_TRUST: "Подтвердить реальную себестоимость",
  MAP_UNMATCHED_SKU: "Связать SKU",
  FIX_STOCK_SYNC: "Починить синхронизацию остатков",
  RECONCILE_FINANCE: "Сверить расхождение с финансами",
  RECONCILIATION_REVIEW: "Проверить расхождение WB-отчёта",
  FIX_AD_ALLOCATION: "Привязать рекламу к карточкам",
  FIX_PRICE_MAPPING: "Починить привязку цены",
  DATA_FIX_REQUIRED: "Сначала исправить данные",
  REORDER: "Дозаказать товар",
  DO_NOT_REORDER: "Не закупать повторно",
  LIQUIDATE_STOCK: "Распланировать распродажу остатка",
  PRICE_REVIEW: "Проверить цену",
  PRICE_INCREASE_REVIEW: "Проверить повышение цены",
  AD_REVIEW: "Проверить рекламу",
  AD_PAUSE_REVIEW: "Проверить остановку рекламы",
  SCALE_AD: "Масштабировать рекламу",
  PAUSE_AD: "Поставить рекламу на паузу",
  CONTENT_REVIEW: "Проверить контент карточки",
};

export const DATA_FIX_ACTION_TYPES = new Set([
  "FIX_COST_TRUST",
  "MAP_UNMATCHED_SKU",
  "FIX_STOCK_SYNC",
  "RECONCILE_FINANCE",
  "FIX_AD_ALLOCATION",
  "FIX_PRICE_MAPPING",
]);

export interface BlockerInfo {
  title: string;
  description: string;
  how_to_fix: string;
  cta_label: string;
  cta_to: string;
}

export const BLOCKER_INFO: Record<string, BlockerInfo> = {
  supplier_cost_coverage_below_threshold: {
    title: "Нет подтверждённой себестоимости",
    description:
      "По части карточек нет реальной закупочной цены — прибыль и ROI считаются неточно.",
    how_to_fix:
      "Загрузите файл с себестоимостью поставщика или укажите её вручную.",
    cta_label: "Открыть себестоимость",
    cta_to: "/costs",
  },
  missing_manual_cost: {
    title: "По карточке нет себестоимости",
    description:
      "Для этой карточки не загружена реальная себестоимость поставщика.",
    how_to_fix: "Загрузите себестоимость на странице «Себестоимость».",
    cta_label: "Открыть себестоимость",
    cta_to: "/costs",
  },
  finance_not_confirmed: {
    title: "Финансовый отчёт ещё не подтверждён",
    description: "WB финансы по этой карточке ещё не пришли или не сверены.",
    how_to_fix:
      "Система автоматически дождётся или перезапустит сверку. Ручных действий от пользователя нет.",
    cta_label: "Открыть финансы",
    cta_to: "/finance",
  },
  failed_sync_domains: {
    title: "Синхронизация с Wildberries сбоит",
    description:
      "Один из источников данных (продажи, остатки, реклама) не синхронизируется.",
    how_to_fix:
      "Проверьте журнал синхронизаций и перезапустите упавшие домены.",
    cta_label: "Перейти к синхронизациям",
    cta_to: "/operations",
  },
  unmatched_sku_detected: {
    title: "SKU не связаны с карточками",
    description: "В отчётах есть товары, которые не привязаны к карточкам.",
    how_to_fix: "Откройте качество данных и сопоставьте отсутствующие SKU.",
    cta_label: "Открыть качество данных",
    cta_to: "/data-fix",
  },
  latest_stocks_not_completed: {
    title: "Остатки не обновлены до конца",
    description:
      "Последняя выгрузка остатков не завершилась — цифры могут быть неполными.",
    how_to_fix: "Запустите повторную синхронизацию остатков.",
    cta_label: "Перейти к синхронизациям",
    cta_to: "/operations",
  },
  open_blocking_dq_issues: {
    title: "Открытые блокеры качества данных",
    description:
      "Есть незакрытые проблемы качества данных уровня error / critical.",
    how_to_fix: "Откройте журнал проблем и закройте критические инциденты.",
    cta_label: "Открыть журнал проблем",
    cta_to: "/data-fix",
  },
  finance_reconciliation_mismatch: {
    title: "Идёт автоматическая сверка финансов WB",
    description:
      "Система проверяет расхождение между операционными данными и отчётом WB.",
    how_to_fix:
      "Пользователь ничего не исправляет вручную. Если автосверка не закроет проблему, её разбирает администратор.",
    cta_label: "Открыть финансы",
    cta_to: "/finance",
  },
  ads_not_allocated: {
    title: "Реклама не привязана к карточкам",
    description:
      "Расходы на рекламу не распределены по карточкам, прибыль считается без них.",
    how_to_fix: "Привяжите рекламные кампании к карточкам.",
    cta_label: "Открыть рекламу",
    cta_to: "/ads",
  },
  not_allocated_to_sku: {
    title: "Расход не привязан к SKU",
    description:
      "Этот расход есть на уровне аккаунта, но не распределён по карточкам.",
    how_to_fix:
      "Проверьте категорию расхода и правила распределения; системную сверку не подгоняйте вручную.",
    cta_label: "Открыть расходы",
    cta_to: "/expenses",
  },
  price_not_mapped: {
    title: "Цена не привязана",
    description: "Для части карточек нет актуальной цены.",
    how_to_fix: "Загрузите или подтвердите цены в модуле цен.",
    cta_label: "Открыть цены",
    cta_to: "/pricing",
  },
  cost_not_confirmed: {
    title: "Себестоимость не подтверждена",
    description:
      "Без подтверждённой себестоимости break-even и target-margin не считаются.",
    how_to_fix: "Подтвердите реальную себестоимость поставщика.",
    cta_label: "Открыть себестоимость",
    cta_to: "/costs",
  },
  estimated_from_operator_baseline_cost: {
    title: "Оценка по операторской себестоимости",
    description:
      "Расчёт сделан по базовой операторской себестоимости, а не подтверждённой.",
    how_to_fix: "Подтвердите реальную себестоимость поставщика.",
    cta_label: "Открыть себестоимость",
    cta_to: "/costs",
  },
  stock_value_not_computable: {
    title: "Стоимость остатка не посчитана",
    description:
      "По карточке есть остаток, но себестоимость для его оценки не подтверждена.",
    how_to_fix: "Подтвердите себестоимость поставщика.",
    cta_label: "Открыть себестоимость",
    cta_to: "/costs",
  },
};

// Коды проблем качества данных (DQ) — человеческое описание для пользователя.
export const DQ_CODE_COPY: Record<
  string,
  { title: string; description: string }
> = {
  order_without_sale_or_return: {
    title: "Заказ без продажи и возврата",
    description:
      "Есть заказы, по которым нет ни продажи, ни возврата. Возможно, отчёт WB ещё не закрыт или товар «застрял» на складе.",
  },
  sales_without_stock: {
    title: "Продажа без остатка",
    description:
      "Зафиксированы продажи, когда по нашим данным остатка не было. Похоже на расхождение синхронизации остатков с WB.",
  },
  stock_without_sales: {
    title: "Остаток без движения",
    description:
      "Остаток есть, но продаж нет за период. Возможно, карточка не показывается покупателям.",
  },
  return_without_sale: {
    title: "Возврат без продажи",
    description:
      "Возврат пришёл, но исходной продажи в данных нет — расхождение с финотчётом WB.",
  },
  negative_stock: {
    title: "Отрицательный остаток",
    description:
      "Расчётный остаток ушёл в минус — продали больше, чем числилось на складе.",
  },
  missing_cost: {
    title: "Нет себестоимости",
    description:
      "Для этого SKU не подтверждена себестоимость, прибыль считается предварительно.",
  },
  price_missing: {
    title: "Нет цены",
    description: "Цена не привязана к карточке — расчёты по марже невозможны.",
  },
  unmatched_sku: {
    title: "SKU не связан с карточкой",
    description: "SKU есть в отчётах, но не привязан к карточке в каталоге.",
  },
};

export function humanizeDqCode(code: string): {
  title: string;
  description: string;
} {
  return (
    DQ_CODE_COPY[code] ||
    DQ_CODE_COPY[code?.toLowerCase?.()] || {
      title: code?.replace(/_/g, " ") || "Неизвестная проблема",
      description:
        "Технический код от бэкенда. Если повторяется часто — сообщите команде данных.",
    }
  );
}

export const BLOCKED_REASON_COPY: Record<string, string> = Object.fromEntries(
  Object.entries(BLOCKER_INFO).map(([k, v]) => [k, v.title]),
);

export const TRUST_STATE_COPY: Record<
  DataTrustState,
  { label: string; tone: "success" | "warning" | "danger" }
> = {
  trusted: { label: "Доверенные данные", tone: "success" },
  test_only: { label: "Предварительный режим", tone: "warning" },
  data_blocked: { label: "Сначала почините данные", tone: "danger" },
};

export const CONFIDENCE_COPY: Record<
  Confidence,
  { label: string; tone: "success" | "warning" | "danger" }
> = {
  high: { label: "Высокая точность", tone: "success" },
  medium: { label: "Приблизительно", tone: "warning" },
  low: { label: "Низкая точность", tone: "danger" },
};

export const PRIORITY_COPY: Record<
  string,
  { label: string; tone: "danger" | "warning" | "info" | "muted" }
> = {
  critical: { label: "Критично", tone: "danger" },
  high: { label: "Высокий", tone: "warning" },
  medium: { label: "Средний", tone: "info" },
  low: { label: "Низкий", tone: "muted" },
};

export const ADS_STATUS_COPY: Record<string, string> = {
  linked: "Реклама привязана к прибыли",
  article_level_only: "Реклама на уровне артикула",
  not_allocated: "Реклама не распределена по карточкам",
  not_allocated_to_profitability: "Реклама не учтена в прибыли",
  sync_failed: "Ошибка синхронизации рекламы",
  stale_with_rate_limit: "Данные устарели (WB 429)",
  no_ads: "Нет рекламы",
};

export const COST_TRUTH_COPY: Record<
  string,
  { label: string; tone: "success" | "warning" | "danger" | "muted" }
> = {
  supplier_confirmed: {
    label: "Подтверждённая себестоимость",
    tone: "success",
  },
  operator_baseline: { label: "Операторская себестоимость", tone: "warning" },
  placeholder: { label: "Тестовая себестоимость", tone: "danger" },
  missing: { label: "Нет себестоимости", tone: "danger" },
  "": { label: "Нет данных", tone: "muted" },
};

export const PRICE_STATUS_COPY: Record<
  string,
  { label: string; tone: "success" | "warning" | "danger" | "info" | "muted" }
> = {
  ready: { label: "Готово", tone: "success" },
  safe: { label: "Цена безопасна", tone: "success" },
  estimated_safe: { label: "Цена безопасна (оценка)", tone: "info" },
  risk: { label: "Риск по цене", tone: "warning" },
  below_break_even: { label: "Ниже безубыточности", tone: "danger" },
  not_computable: { label: "Не посчитано", tone: "muted" },
};

export const STOCK_STATUS_COPY: Record<
  string,
  { label: string; tone: "success" | "warning" | "danger" | "muted" }
> = {
  ok: { label: "Остаток в норме", tone: "success" },
  low: { label: "Мало остатка", tone: "warning" },
  out: { label: "Закончился", tone: "danger" },
  overstock: { label: "Сверхзапас", tone: "warning" },
  "": { label: "Нет данных", tone: "muted" },
};

// Раздельные «честные» лейблы блоков
export const HONEST_LABELS = {
  operational_analysis: "Операционный анализ",
  provisional_profit: "Предварительная прибыль",
  finance_not_closed: "Финансы не закрыты",
  supplier_cost_unconfirmed: "Себестоимость не подтверждена поставщиком",
  needs_review: "Требует проверки",
  todo_today: "Что сделать сегодня",
} as const;

// Технический бэкенд-код -> бизнес-фраза.
export const BUSINESS_STATUS_COPY: Record<
  string,
  {
    label: string;
    tone: "success" | "warning" | "danger" | "info" | "muted";
    hint?: string;
  }
> = {
  // finance_reconciliation_status
  ok: { label: "Финансы сходятся", tone: "success" },
  matched: { label: "Финансы сходятся", tone: "success" },
  partial: {
    label: "Финансы сходятся частично",
    tone: "warning",
    hint: "Часть операций ещё не подтверждена WB",
  },
  mismatch: {
    label: "Финансы не сходятся",
    tone: "warning",
    hint: "Есть расхождение между продажами и финотчётом",
  },
  critical_mismatch: {
    label: "Финансы не сходятся",
    tone: "danger",
    hint: "Крупное расхождение — прибыль предварительная",
  },
  not_available: { label: "Финотчёт ещё не пришёл", tone: "muted" },

  // business_status
  accepted: { label: "Данные приняты", tone: "success" },
  accepted_with_warnings: {
    label: "Можно работать, но есть предупреждения",
    tone: "warning",
  },
  provisional: {
    label: "Предварительно",
    tone: "warning",
    hint: "Цифры приблизительные",
  },
  data_blocked: { label: "Сначала исправить данные", tone: "danger" },

  // cost truth level
  supplier_confirmed: {
    label: "Себестоимость подтверждена поставщиком",
    tone: "success",
  },
  operator_baseline: {
    label: "Операторская себестоимость, не поставщик",
    tone: "warning",
    hint: "Расчёт прибыли — предварительный",
  },
  placeholder: { label: "Плейсхолдер себестоимости", tone: "danger" },
  missing: { label: "Нет себестоимости", tone: "danger" },

  // profit finality / trust_state
  final: { label: "Прибыль финальная", tone: "success" },
  blocked: { label: "Сначала исправить данные", tone: "danger" },
  trusted: { label: "Доверенные данные", tone: "success" },
  operational_trusted: {
    label: "Операционно доверенные",
    tone: "success",
    hint: "Решения можно принимать, финал ещё не подтверждён",
  },
  operational_final: { label: "Операционно подтверждено", tone: "success" },
  operational_provisional: {
    label: "Операционно предварительно",
    tone: "warning",
    hint: "Можно управлять, финальная прибыль предварительная",
  },
  financial_final: { label: "Финансово подтверждено", tone: "success" },
  financial_provisional: { label: "Финансово предварительно", tone: "warning" },
  preliminary: { label: "Предварительно", tone: "warning" },
  test_only: { label: "Предварительный режим", tone: "warning" },
  needs_review: { label: "Нужна проверка", tone: "warning" },
};

export function humanizeBusinessStatus(code: string | null | undefined): {
  label: string;
  tone: "success" | "warning" | "danger" | "info" | "muted";
  hint?: string;
} {
  if (!code) return { label: "—", tone: "muted" };
  return (
    BUSINESS_STATUS_COPY[code] ||
    BUSINESS_STATUS_COPY[code.toLowerCase()] || { label: code, tone: "muted" }
  );
}

export function humanizeBlockedReason(code: string): string {
  return BLOCKED_REASON_COPY[code] || code;
}
export function humanizeAction(code: string): string {
  if (!code) return "";
  return (
    ACTION_COPY[code] ||
    ACTION_COPY[code.toUpperCase()] ||
    code.replace(/_/g, " ")
  );
}
export function humanizeAdsStatus(code: string): string {
  return ADS_STATUS_COPY[code] || code;
}

/**
 * Hide raw backend/config error strings from end users.
 * Returns a user-safe message per module, or null when the raw message
 * looks technical (URLs, env keys, "is not configured", stack-like strings).
 */
export function humanizeModuleMessage(
  module: "checker" | "reputation" | "claims" | string,
  rawMessage?: string | null,
): string | null {
  const fallback: Record<string, string> = {
    checker:
      "Проверка карточек не подключена. Качество карточки появится после настройки модуля.",
    reputation: "Модуль репутации не подключён.",
    claims: "Модуль претензий отключён.",
  };
  const fb = fallback[module] ?? null;
  if (!rawMessage || typeof rawMessage !== "string") return fb;
  const msg = rawMessage.trim();
  if (!msg) return fb;
  const technical =
    /(_base_url|_url|_token|_key|env|http[s]?:\/\/|is not configured|unavailable|not implemented|null|undefined|traceback|\bENOENT\b|\b500\b|stacktrace)/i;
  if (technical.test(msg)) return fb;
  // Looks like a sentence written for humans (Cyrillic or reasonably short).
  if (/[А-Яа-яЁё]/.test(msg) || msg.length <= 120) return msg;
  return fb;
}
export function isDataFixAction(code: string): boolean {
  if (!code) return false;
  return (
    DATA_FIX_ACTION_TYPES.has(code) ||
    DATA_FIX_ACTION_TYPES.has(code.toUpperCase())
  );
}
