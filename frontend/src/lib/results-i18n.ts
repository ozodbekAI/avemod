// Human-facing translations for /portal/results payloads.
// Goal: no snake_case primary text, no English internals.
// Raw keys are kept available for a small muted tooltip when callers want it.

export const MODULE_LABELS: Record<string, string> = {
  claims: "Претензии",
  action_center: "Центр действий",
  doctor: "Диагностика прибыли legacy",
  profit_doctor: "Диагностика прибыли legacy",
  reputation: "Репутация",
  checker: "Качество карточек",
  stockops: "Остатки",
  pricing: "Цены",
  ads: "Реклама",
  finance: "Финансы",
  grouping: "Группировка",
  result_tracking: "Отслеживание результата",
  problem_engine: "Проблемы товара",
};

// Common totals/summary keys — translate to Russian labels.
export const TOTALS_LABELS: Record<string, string> = {
  events_count:            "Событий",
  events_total:            "Событий",
  improved_count:          "Улучшилось",
  worse_count:             "Стало хуже",
  neutral_count:           "Без изменений",
  pending_count:           "Ожидает проверки",
  blocked_count:           "Заблокировано",
  not_enough_data_count:   "Недостаточно данных",
  total_delta_amount:      "Суммарный эффект",
  total_effect_amount:     "Суммарный эффект",
  positive_amount:         "Положительный эффект",
  negative_amount:         "Отрицательный эффект",
  confidence:              "Уверенность",
  audit_count:             "Тестовых событий",
};

export function humanizeTotalsKey(k: string): string {
  if (TOTALS_LABELS[k]) return TOTALS_LABELS[k];
  return k.replace(/[_\-]+/g, " ").replace(/^\w/, (c) => c.toUpperCase());
}

export const OUTCOME_LABELS: Record<string, string> = {
  improved: "Улучшилось",
  worse: "Стало хуже",
  neutral: "Без изменений",
  pending: "Ожидает проверки",
  blocked: "Заблокировано",
  not_enough_data: "Недостаточно данных",
};

export const EVENT_TYPE_LABELS: Record<string, string> = {
  // generic action lifecycle
  local_action_status_updated:        "Статус действия изменён",
  action_status_updated:              "Статус действия изменён",
  action_completed:                   "Действие выполнено",
  action_started:                     "Действие начато",
  status_changed:                     "Статус изменён",
  action_done:                        "Действие выполнено",
  action_postponed:                   "Действие отложено",
  action_ignored:                     "Действие пропущено",

  // result tracking
  before_snapshot:                    "Снимок «до» сохранён",
  after_snapshot:                     "Снимок «после» сохранён",
  recheck_result:                     "Повторная проверка",
  measured_comparison:                "Измеренное сравнение",
  result_evaluated:                   "Результат оценён",

  // claims factory
  claim_submitted:                    "Претензия отправлена",
  claim_resolved:                     "Претензия закрыта",
  claim_rejected:                     "Претензия отклонена",
  claim_draft_generated:              "Черновик обращения создан",
  draft_generated:                    "Черновик обращения создан",
  case_created_from_signal:           "Обращение создано из сигнала",
  proof_checked:                      "Проверка доказательств выполнена",
  evidence_attached:                  "Доказательство добавлено",
  submit_blocked_confirmation_required: "Подача заблокирована: требуется подтверждение",

  // reputation
  review_replied:                     "Ответ на отзыв",
  question_replied:                   "Ответ на вопрос",

  // operations
  price_changed:                      "Цена изменена",
  stock_replenished:                  "Остатки пополнены",
  card_fixed:                         "Карточка исправлена",
  doctor_recommendation:              "Рекомендация legacy-диагностики прибыли",
};

// Snippets that may appear inside free-form messages / warnings / tags.
export const TERM_LABELS: Record<string, string> = {
  causality_not_claimed:                "Корреляция, не доказанная причинность",
  not_enough_data:                      "Недостаточно данных",
  before_snapshot:                      "снимок «до»",
  after_snapshot:                       "снимок «после»",
  proof_checked:                        "проверка доказательств выполнена",
  local_action_status_updated:          "статус действия изменён",
  submit_blocked_confirmation_required: "подача заблокирована: требуется подтверждение",
};

// Whole-sentence English notes that the backend may emit verbatim.
const SENTENCE_REPLACEMENTS: Array<[RegExp, string]> = [
  [/result events?\s+do not prove causation\.?/gi,
    "Сравнение показывает связь по данным после действия, но не доказывает причинность само по себе."],
  [/correlation,?\s*not guaranteed causality\.?/gi,
    "Сравнение показывает связь по данным после действия, но не доказывает причинность само по себе."],
  [/correlation only;?\s*result events? do not prove causation\.?/gi,
    "Сравнение показывает связь по данным после действия, но не доказывает причинность само по себе."],
  [/correlation does not imply causation\.?/gi,
    "Сравнение показывает связь по данным после действия, но не доказывает причинность само по себе."],
  [/local action center status (was )?updated\.?\s*(no external marketplace operation was performed\.?)?/gi,
    "Статус действия изменён. Изменений на маркетплейсе не было."],
  [/no external marketplace operation was performed\.?/gi,
    "Изменений на маркетплейсе не было."],
  [/not enough data( to evaluate)?\.?/gi, "Недостаточно данных для оценки."],
  [/^\s*blocked\s*$/i, "Заблокировано"],
  [/^\s*not[_ ]enough[_ ]data\s*$/i, "Недостаточно данных"],
];

/** Replace technical tokens inside an arbitrary message string. */
export function translateTerm(s: string): string {
  if (!s) return s;
  let out = s;
  for (const [re, repl] of SENTENCE_REPLACEMENTS) out = out.replace(re, repl);
  for (const [k, v] of Object.entries(TERM_LABELS)) {
    if (out === k) return v;
    out = out.replace(new RegExp(`\\b${k}\\b`, "g"), v);
  }
  return out;
}

/** snake_case / kebab-case → Sentence case fallback for unknown keys. */
function sentenceCase(raw: string): string {
  const clean = raw.replace(/[_\-]+/g, " ").trim().toLowerCase();
  return clean.charAt(0).toUpperCase() + clean.slice(1);
}

export function humanizeModule(k?: string | null): string {
  if (!k) return "—";
  return MODULE_LABELS[k] ?? sentenceCase(k);
}

export function humanizeOutcome(k?: string | null): string | null {
  if (!k) return null;
  return OUTCOME_LABELS[k] ?? translateTerm(k);
}

/**
 * Returns { label, raw } so callers can show `label` as primary text
 * and `raw` in a small muted tooltip for support/debug.
 */
export function humanizeEventType(k?: string | null): { label: string; raw: string | null } {
  if (!k) return { label: "Событие", raw: null };
  const mapped = EVENT_TYPE_LABELS[k];
  if (mapped) return { label: mapped, raw: k };
  // Looks technical (contains _ or all-lowercase ascii) → sentence-case + keep raw for tooltip.
  if (/[_\-]/.test(k) || /^[a-z0-9]+$/i.test(k)) {
    return { label: sentenceCase(k), raw: k };
  }
  return { label: k, raw: null };
}

export function humanizeMessage(s?: string | null): string | null {
  if (!s) return null;
  return translateTerm(s);
}

export function sellerSafeMessage(s: unknown, fallback: string): string {
  if (!(s instanceof Error) && typeof s !== "string") return fallback;
  const raw = typeof s === "string" ? s : s.message;
  const translated = humanizeMessage(raw);
  if (!translated) return fallback;
  return /[a-z]{3,}/.test(translated) ? fallback : translated;
}
