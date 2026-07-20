export const PROBLEM_SEVERITY_LABELS: Record<string, string> = {
  critical: "Критично",
  high: "Высокий риск",
  medium: "Средний риск",
  low: "Низкий риск",
};

export const PROBLEM_STATUS_LABELS: Record<string, string> = {
  open: "Открыто",
  new: "Новая",
  acknowledged: "Принята",
  in_progress: "В работе",
  done: "Выполнено",
  postponed: "Отложено",
  snoozed: "Отложено",
  ignored: "Отклонено",
  dismissed: "Отклонено",
  rejected: "Отклонено",
  blocked: "Заблокировано",
  resolved: "Решено",
  closed: "Закрыто",
  test_only: "Тестовое правило",
};

export const PROBLEM_TRUST_LABELS: Record<string, string> = {
  confirmed: "Подтверждено",
  provisional: "Предварительно",
  estimated: "Оценка",
  opportunity: "Возможность",
  blocked: "Не хватает данных",
  test_only: "Тестовое правило",
  high: "Высокая уверенность",
  medium: "Средняя уверенность",
  low: "Низкая уверенность",
  final: "Финально",
  trusted: "Доверенные данные",
  data_blocked: "Данные заблокированы",
};

export const PROBLEM_IMPACT_LABELS: Record<string, string> = {
  loss: "Убыток",
  risk: "Риск",
  warning: "Предупреждение",
  "blocked cash": "Замороженные деньги",
  opportunity: "Возможность роста",
  "data blocker": "Блокер данных",
  confirmed_loss: "Подтверждённый убыток",
  probable_loss: "Вероятный убыток",
  probable_risk: "Вероятный риск",
  blocked_cash: "Замороженные деньги",
  blocked_revenue: "Заблокированная выручка",
  lost_sales_risk: "Риск потери продаж",
  estimated_opportunity: "Оценочная возможность",
  data_blocker: "Блокер данных",
  data_blocked: "Данные заблокированы",
  system_warning: "Системное предупреждение",
  informational: "Информация",
  test_only: "Тестовое правило",
};

export const PROBLEM_RESULT_LABELS: Record<string, string> = {
  pending_data: "ждём данных",
  improved: "есть улучшение",
  worse: "стало хуже",
  neutral: "без изменений",
  not_enough_data: "нет данных",
};

export const PROBLEM_ACTION_LABELS: Record<string, string> = {
  create_task: "Создать задачу",
  assign: "Назначить",
  recheck: "Перепроверить",
  trigger_recheck: "Перепроверить",
  dismiss: "Отклонить",
  open_data_fix: "Открыть исправление данных",
  data_fix: "Открыть исправление данных",
  open_price_review: "Проверить цену",
  review_price: "Проверить цену",
  pricing_review: "Проверить цену",
  open_promo_planner: "Настроить промо",
  promo_planner: "Настроить промо",
  review_promo: "Настроить промо",
  safe_promo: "Настроить промо",
  reduce_promo: "Снизить промо",
  bundle: "Собрать комплект",
  run_checker: "Проверить карточку",
  check_card_quality: "Проверить карточку",
  review_content: "Проверить карточку",
  upload_cost: "Загрузить себестоимость",
  review_cost: "Загрузить себестоимость",
  map_sku: "Сопоставить SKU",
  classify_expense: "Классифицировать расход",
  open_supply_planner: "Открыть поставки",
  open_ads_dashboard: "Открыть рекламу",
  open_product: "Открыть товар",
  open_results: "Открыть результаты",
  review_ads: "Открыть рекламу",
  pause_ads: "Открыть рекламу",
  lower_ads: "Открыть рекламу",
  review_bids: "Открыть рекламу",
  plan_supply: "Открыть поставки",
  review_reputation: "Открыть отзывы",
  reply_review: "Ответить на отзыв",
  reply_question: "Ответить на вопрос",
};

export const PROBLEM_CODE_LABELS: Record<string, string> = {
  missing_cost_blocks_profit: "Нет себестоимости",
  negative_unit_profit: "Товар продаётся в минус",
  overstock_slow_moving: "Пересток и медленные продажи",
  low_stock_risk: "Риск низкого остатка",
  ads_spend_without_profit: "Реклама съедает прибыль",
  ads_spend_no_orders: "Реклама без заказов",
  promo_not_profitable: "Промо уводит товар в минус",
  price_below_safe_margin: "Цена ниже безопасной маржи",
  low_conversion_card: "Низкая конверсия карточки",
  high_return_rate: "Высокий процент возвратов",
  high_ad_drr: "Высокий ДРР рекламы",
  high_ad_cpo: "Высокая стоимость заказа",
  low_ads_ctr: "Низкий CTR рекламы",
  ads_stockout_risk: "Реклама ведёт к дефициту",
  stockout_now_with_recent_orders: "Нет остатка, спрос есть",
  stockout_risk_14d: "Риск дефицита за 14 дней",
  storage_cost_pressure: "Дорогое хранение остатка",
  no_sales_with_views: "Просмотры без заказов",
  price_offer_blocks_conversion: "Цена тормозит конверсию",
  raise_price_possible_high_demand: "Цена может защитить остаток",
  negative_reviews_need_reply: "Негативные отзывы ждут ответа",
  questions_need_reply: "Вопросы ждут ответа",
  low_product_rating: "Низкий рейтинг товара",
  dead_stock: "Риск зависшего остатка",
  fast_stock_depletion: "Товар быстро заканчивается",
  missing_manual_cost: "Не хватает себестоимости",
  supplier_cost_coverage_below_threshold: "Низкое покрытие себестоимости",
  seller_other_expense_missing: "Не заполнены прочие расходы",
  manual_cost_ambiguous_match: "Конфликт сопоставления себестоимости",
  manual_cost_unresolved_sku: "Себестоимость не привязана к SKU",
  unmatched_sku: "SKU не сопоставлен",
  unmatched_sku_detected: "SKU не сопоставлен",
  expense_unclassified: "Расход без категории",
  unclassified_finance_expense: "Расход без категории",
  finance_reconciliation_mismatch: "Расхождение финансовой сверки",
  sale_without_finance: "Продажа без финансовой строки",
  finance_without_sale: "Финансовая строка без продажи",
  missing_chrt_id: "Не хватает связи карточки",
  stock_snapshot_missing: "Не хватает снимка остатков",
  stocks_task_failed: "Ошибка синхронизации остатков",
  ad_spend_without_sku: "Реклама не привязана к SKU",
  expense_ad_double_count_risk: "Риск двойного учёта рекламы",
};

export const PROBLEM_GROUP_LABELS: Record<string, string> = {
  profitability: "Прибыльность",
  stock: "Остатки",
  price: "Цена",
  ads_promo: "Реклама и промо",
  card_quality: "Качество карточки",
  data_blockers: "Блокеры данных",
  system_checks: "Системные проверки",
};

export const PROBLEM_EMPTY_STATE_COPY: Record<string, { title: string; body: string }> = {
  sync_required: {
    title: "Нужна синхронизация",
    body: "Данные по товару ещё не обновлены. Без свежих продаж, остатков и финансов платформа не может проверить проблему. Запустите синхронизацию или дождитесь следующего обновления.",
  },
  no_data: {
    title: "Нет данных",
    body: "За выбранный период нет исходных строк. Платформа не видит продаж, остатков или финансовых фактов для проверки. Выберите другой период или обновите данные.",
  },
  no_issues: {
    title: "Проблем не найдено",
    body: "Открытых проблем по товару нет. Проверка прошла по доступным данным. Продолжайте следить за товаром после новых продаж и синхронизаций.",
  },
  data_missing: {
    title: "Не хватает данных",
    body: "Часть метрик отсутствует. Поэтому платформа пока не может подтвердить проблему или посчитать влияние. Заполните недостающие данные и запустите проверку снова.",
  },
  missing_data: {
    title: "Не хватает данных",
    body: "Часть метрик отсутствует. Поэтому платформа пока не может подтвердить проблему или посчитать влияние. Заполните недостающие данные и запустите проверку снова.",
  },
  module_disabled: {
    title: "Модуль отключён",
    body: "Проверка этого типа сейчас отключена для аккаунта. Поэтому результат не строится. Включите модуль в настройках или обратитесь к администратору.",
  },
  beta_module: {
    title: "Бета-модуль",
    body: "Этот сигнал ещё в бета-режиме. Продавцу он скрыт, пока правило не готово. Администратор может проверить его и опубликовать позже.",
  },
};

export const PROBLEM_ANSWER_LABELS = {
  whatHappened: "Что произошло?",
  why: "Почему платформа так решила?",
  impact: "На что влияет?",
  trust: "Это факт или оценка?",
  nextStep: "Что сделать сейчас?",
  canFixHere: "Можно исправить здесь?",
  recheck: "Как проверим повторно?",
  result: "Результат после действия",
} as const;

export const EVIDENCE_BUTTON_LABEL = "Как посчитано?";

const UNKNOWN_LABEL = "Не указано";

type SellerProblemSeededCopy = {
  title: string;
  why: string;
  nextStep: string;
  recheckRule: string;
};

type SellerProblemTemplateVars = Record<string, string | number | null | undefined>;

export const SEEDED_PROBLEM_SELLER_COPY: Record<string, SellerProblemSeededCopy> = {
  missing_cost_blocks_profit: {
    title: "Нет себестоимости для товара {nm_id}",
    why: "За 30 дней есть выручка {revenue_30d}, но себестоимость не заполнена. Поэтому прибыль и маржа по товару пока не считаются надёжно.",
    nextStep: "Загрузите или сопоставьте себестоимость, затем запустите повторную проверку прибыльности.",
    recheckRule: "Загрузите или сопоставьте себестоимость, затем перепроверьте товар после обновления выручки.",
  },
  negative_unit_profit: {
    title: "Товар {nm_id} продаётся в минус",
    why: "Прибыль на единицу: {unit_profit}, маржа: {margin_pct}%. Минимальная безопасная маржа: 10%.",
    nextStep: "Проверьте цену, себестоимость, рекламу, промо и логистику. Не снижайте цену без проверки безопасной маржи.",
    recheckRule: "Перепроверьте после изменения цены, себестоимости, рекламы, промо, логистики или маржи.",
  },
  overstock_slow_moving: {
    title: "Пересток и медленные продажи по товару {nm_id}",
    why: "Остаток: {stock_qty}, запас в днях: {days_of_stock}, средние продажи за 14 дней: {avg_daily_sales_14d} шт./день.",
    nextStep: "Проверьте безопасное промо, цену, комплект, рекламу или качество карточки. Скидку можно запускать только после проверки маржи.",
    recheckRule: "Перепроверьте после обновления остатков, скорости продаж или себестоимости.",
  },
  low_stock_risk: {
    title: "Риск низкого остатка по товару {nm_id}",
    why: "Запаса осталось на {days_of_stock} дней при средних продажах за 7 дней {avg_daily_sales_7d} шт./день.",
    nextStep: "Запланируйте поставку или пополнение. Если поставить товар быстро нельзя, снизьте промо или рекламу, чтобы не уйти в дефицит.",
    recheckRule: "Перепроверьте после обновления остатков, поставки или скорости продаж.",
  },
  ads_spend_without_profit: {
    title: "Реклама съедает прибыль по товару {nm_id}",
    why: "Расход на рекламу за 7 дней: {ad_spend_7d}; прибыль на единицу после рекламы: {unit_profit_after_ads}.",
    nextStep: "Снизьте или приостановите рекламу, проверьте качество карточки, ставки и цену.",
    recheckRule: "Перепроверьте после изменения рекламных расходов, ставок, цены или прибыли.",
  },
  ads_spend_no_orders: {
    title: "Реклама по товару {nm_id} тратит бюджет без заказов",
    why: "Расход на рекламу за 7 дней: {ad_spend_7d}, заказов за 7 дней: {orders_7d}.",
    nextStep: "Проверьте кампанию, ставки, поисковые кластеры, карточку и цену. Сначала откройте рекламный review.",
    recheckRule: "Перепроверьте после изменения ставки, бюджета, кластера, цены, карточки или после обновления рекламной статистики.",
  },
  promo_not_profitable: {
    title: "Промо уводит товар {nm_id} в минус",
    why: "Расход на промо: {promo_spend_30d}, прибыль на единицу: {unit_profit}, маржа: {margin_pct}%.",
    nextStep: "Снизьте или остановите промо, проверьте цену и убедитесь, что скидка сохраняет безопасную маржу.",
    recheckRule: "Перепроверьте после изменения промо, цены, себестоимости или маржи.",
  },
  price_below_safe_margin: {
    title: "Цена ниже безопасной маржи по товару {nm_id}",
    why: "Текущая эффективная цена: {price_after_discount}; маржа: {margin_pct}%. Минимальная безопасная маржа: 10%.",
    nextStep: "Проверьте цену и поднимите её до безопасного уровня, если экономика товара заполнена полностью.",
    recheckRule: "Перепроверьте после изменения цены, себестоимости, комиссий или маржи.",
  },
  low_conversion_card: {
    title: "Карточка товара {nm_id} получает просмотры, но плохо конвертирует",
    why: "Просмотры за 30 дней: {views_30d}, конверсия в заказ: {conversion_rate}%, заказы: {orders_30d}.",
    nextStep: "Проверьте название, главное фото, характеристики, цену, отзывы и качество рекламного трафика.",
    recheckRule: "Перепроверьте после правки карточки, цены, рекламы или после обновления аналитики карточки.",
  },
  high_return_rate: {
    title: "Высокий процент возвратов по товару {nm_id}",
    why: "Продажи за 30 дней: {sales_30d}, возвратность: {return_rate}%, выручка: {revenue_30d}.",
    nextStep: "Проверьте карточку, размерную сетку, фото, описание, качество товара и ожидания покупателя.",
    recheckRule: "Перепроверьте после правки карточки, размерной сетки, описания или после обновления продаж и возвратов.",
  },
  high_ad_drr: {
    title: "Высокий ДРР рекламы по товару {nm_id}",
    why: "Расход на рекламу за 7 дней: {ad_spend_7d}, выручка за 7 дней: {revenue_7d}. ДРР выше безопасного порога 25%.",
    nextStep: "Проверьте кампанию, ставки, карточку и цену. Снижайте расход только после проверки маржи и качества трафика.",
    recheckRule: "Перепроверьте после изменения рекламы, цены, карточки или обновления продаж.",
  },
  high_ad_cpo: {
    title: "Высокая стоимость заказа из рекламы по товару {nm_id}",
    why: "CPO за 7 дней: {ad_cpo_7d}, расход: {ad_spend_7d}, рекламных заказов: {ad_orders_7d}.",
    nextStep: "Проверьте ставки, кластеры, карточку и цену. Если CPO не окупается, снизьте ставку или перенесите бюджет.",
    recheckRule: "Перепроверьте после изменения ставок, кластера, карточки или цены.",
  },
  low_ads_ctr: {
    title: "Низкий CTR рекламы по товару {nm_id}",
    why: "Показы рекламы за 7 дней: {ad_views_7d}, клики: {ad_clicks_7d}, CTR: {ad_ctr_7d}%.",
    nextStep: "Проверьте главное фото, цену, позицию, ставку и релевантность кластера.",
    recheckRule: "Перепроверьте после правки фото, ставки, позиции, кластера или цены.",
  },
  ads_stockout_risk: {
    title: "Реклама ведёт спрос к дефициту по товару {nm_id}",
    why: "Расход на рекламу за 7 дней: {ad_spend_7d}, запаса осталось на {days_of_stock} дней.",
    nextStep: "Запланируйте поставку или временно снизьте рекламный спрос, чтобы не уйти в out-of-stock.",
    recheckRule: "Перепроверьте после обновления остатков, поставки или изменения рекламы.",
  },
  stockout_now_with_recent_orders: {
    title: "Товар {nm_id} уже без остатка, но спрос есть",
    why: "Текущий остаток: {stock_qty}, заказов за 7 дней: {orders_7d}.",
    nextStep: "Срочно проверьте остатки и поставку. Если остаток реально ноль, создайте пополнение и уберите лишний спрос.",
    recheckRule: "Перепроверьте после обновления остатков или создания поставки.",
  },
  stockout_risk_14d: {
    title: "Товар {nm_id} закончится в ближайшие 14 дней",
    why: "Запаса осталось на {days_of_stock} дней, средние продажи за 14 дней: {avg_daily_sales_14d} шт./день.",
    nextStep: "Запланируйте пополнение заранее. Если поставка не успевает, снижайте промо или рекламу до прихода товара.",
    recheckRule: "Перепроверьте после обновления остатков, поставки или скорости продаж.",
  },
  storage_cost_pressure: {
    title: "Остаток товара {nm_id} создаёт давление по хранению",
    why: "Остаток: {stock_qty}, запас в днях: {days_of_stock}, хранение на единицу: {storage_fee_per_unit}.",
    nextStep: "Проверьте безопасную распродажу, комплект, карточку или перераспределение. Скидку запускайте только после проверки маржи.",
    recheckRule: "Перепроверьте после изменения остатков, хранения, продаж или безопасной распродажи.",
  },
  no_sales_with_views: {
    title: "Карточка товара {nm_id} получает просмотры, но заказов нет",
    why: "Просмотры за 30 дней: {views_30d}, заказов за 30 дней: {orders_30d}.",
    nextStep: "Проверьте оффер: фото, название, характеристики, цену, отзывы и рекламный трафик.",
    recheckRule: "Перепроверьте после правки карточки, цены, рекламы или обновления аналитики.",
  },
  price_offer_blocks_conversion: {
    title: "Цена или оффер тормозит конверсию товара {nm_id}",
    why: "Маржа: {margin_pct}%, просмотры: {views_30d}, конверсия: {conversion_rate}%.",
    nextStep: "Проверьте цену относительно оффера. Если маржа высокая, протестируйте безопасную цену или улучшите карточку.",
    recheckRule: "Перепроверьте после изменения цены, карточки, рекламы или обновления аналитики.",
  },
  raise_price_possible_high_demand: {
    title: "Можно защитить остаток ценой по товару {nm_id}",
    why: "Заказов за 7 дней: {orders_7d}, запаса осталось на {days_of_stock} дней, маржа: {margin_pct}%.",
    nextStep: "Проверьте price review: при высоком спросе и низком запасе можно поднять цену или снизить промо.",
    recheckRule: "Перепроверьте после изменения цены, промо, рекламы, поставки или обновления остатков.",
  },
  negative_reviews_need_reply: {
    title: "Негативные отзывы по товару {nm_id} ждут ответа",
    why: "Негативных отзывов за 30 дней: {negative_reviews_30d}, без ответа: {unanswered_negative_reviews_30d}.",
    nextStep: "Откройте репутацию, подготовьте корректный ответ и создайте задачу, если нужен разбор качества товара.",
    recheckRule: "Перепроверьте после ответа на отзывы или обновления репутации.",
  },
  questions_need_reply: {
    title: "Вопросы покупателей по товару {nm_id} ждут ответа",
    why: "Вопросов без ответа за 30 дней: {unanswered_questions_30d}.",
    nextStep: "Ответьте на вопросы покупателей. Если вопрос повторяется, улучшите карточку товара.",
    recheckRule: "Перепроверьте после ответа на вопросы или обновления репутации.",
  },
  low_product_rating: {
    title: "Низкий рейтинг товара {nm_id}",
    why: "Средний рейтинг за 30 дней: {avg_rating_30d}, негативных отзывов: {negative_reviews_30d}.",
    nextStep: "Разберите причины негативных отзывов, проверьте качество товара, карточку, размеры и ожидания покупателя.",
    recheckRule: "Перепроверьте после ответа на отзывы, правки карточки, проверки качества или обновления репутации.",
  },
  dead_stock: {
    title: "Риск зависшего остатка по товару {nm_id}",
    why: "Остаток: {stock_qty}, продажи за 30 дней: {sales_30d}, запас в днях: {days_of_stock}.",
    nextStep: "Проверьте карточку, рекламу, комплекты и безопасный сценарий распродажи до запуска скидки.",
    recheckRule: "Перепроверьте после обновления остатков, продаж или себестоимости.",
  },
  fast_stock_depletion: {
    title: "Товар {nm_id} быстро заканчивается",
    why: "Запаса осталось на {days_of_stock} дней при средних продажах за 7 дней {avg_daily_sales_7d} шт./день.",
    nextStep: "Срочно запланируйте пополнение. Если поставка невозможна, снизьте промо или рекламу, чтобы избежать дефицита.",
    recheckRule: "Перепроверьте после обновления остатков, поставки или скорости продаж.",
  },
};

function normalizedKey(value: unknown): string {
  return String(value ?? "").trim().toLowerCase();
}

function hasCyrillic(value: string): boolean {
  return /[А-Яа-яЁё]/.test(value);
}

function looksLikeEnglishSellerCopy(value: string): boolean {
  const text = value.trim();
  return Boolean(text && !hasCyrillic(text) && /[A-Za-z]/.test(text));
}

function shouldUseSeededSellerCopy(code: unknown, value: unknown): boolean {
  const key = normalizedKey(code);
  if (!SEEDED_PROBLEM_SELLER_COPY[key]) return false;
  const text = String(value ?? "").trim();
  return !text || looksLikeEnglishSellerCopy(text);
}

export function renderSeededProblemSellerTemplate(
  template: string,
  vars: SellerProblemTemplateVars = {},
): string {
  return template
    .replace(/\{([^}]+)\}/g, (_match, key: string) => {
      const value = vars[key];
      if (value === undefined || value === null || value === "") {
        return key === "nm_id" ? "" : "нет данных";
      }
      return String(value);
    })
    .replace(/\s+([,.%])/g, "$1")
    .replace(/\s{2,}/g, " ")
    .trim();
}

export function seededProblemSellerTitle(
  code: unknown,
  rawTitle: unknown,
  vars?: SellerProblemTemplateVars,
): string | null {
  const key = normalizedKey(code);
  if (!shouldUseSeededSellerCopy(key, rawTitle)) return null;
  return renderSeededProblemSellerTemplate(SEEDED_PROBLEM_SELLER_COPY[key].title, vars);
}

export function seededProblemSellerWhy(
  code: unknown,
  rawWhy: unknown,
  vars?: SellerProblemTemplateVars,
): string | null {
  const key = normalizedKey(code);
  if (!shouldUseSeededSellerCopy(key, rawWhy)) return null;
  return renderSeededProblemSellerTemplate(SEEDED_PROBLEM_SELLER_COPY[key].why, vars);
}

export function seededProblemSellerNextStep(
  code: unknown,
  rawNextStep: unknown,
  vars?: SellerProblemTemplateVars,
): string | null {
  const key = normalizedKey(code);
  if (!shouldUseSeededSellerCopy(key, rawNextStep)) return null;
  return renderSeededProblemSellerTemplate(SEEDED_PROBLEM_SELLER_COPY[key].nextStep, vars);
}

export function seededProblemSellerRecheckRule(
  code: unknown,
  rawRecheckRule: unknown,
  vars?: SellerProblemTemplateVars,
): string | null {
  const key = normalizedKey(code);
  if (!shouldUseSeededSellerCopy(key, rawRecheckRule)) return null;
  return renderSeededProblemSellerTemplate(SEEDED_PROBLEM_SELLER_COPY[key].recheckRule, vars);
}

export function problemSeverityLabel(value: unknown): string {
  const key = normalizedKey(value);
  return PROBLEM_SEVERITY_LABELS[key] ?? UNKNOWN_LABEL;
}

export function problemStatusLabel(value: unknown): string {
  const key = normalizedKey(value);
  return PROBLEM_STATUS_LABELS[key] ?? (key ? "Статус не распознан" : "—");
}

export function problemTrustLabel(value: unknown): string {
  const key = normalizedKey(value);
  return PROBLEM_TRUST_LABELS[key] ?? (key ? "Предварительно" : "—");
}

export function problemImpactLabel(value: unknown): string {
  const key = normalizedKey(value).replaceAll(" ", "_");
  const original = normalizedKey(value);
  return PROBLEM_IMPACT_LABELS[original] ?? PROBLEM_IMPACT_LABELS[key] ?? (key ? "Риск" : "—");
}

export function problemActionLabel(code: unknown): string {
  const key = normalizedKey(code);
  return PROBLEM_ACTION_LABELS[key] ?? "Действие";
}

export function problemCodeLabel(code: unknown): string {
  const key = normalizedKey(code);
  return PROBLEM_CODE_LABELS[key] ?? (key ? "Проверка данных" : "Проблема");
}

export function problemGroupLabel(key: unknown): string {
  const normalized = normalizedKey(key);
  return PROBLEM_GROUP_LABELS[normalized] ?? "Группа проблем";
}

export function problemRecheckStatusLabel(value: unknown): string {
  const key = normalizedKey(value);
  if (key === "ok" || key === "success" || key === "resolved") return "обновлено";
  if (key === "error" || key === "failed") return "ошибка";
  if (key === "pending") return "ожидает проверки";
  return key ? "статус проверки" : "—";
}

export function problemResultStatusLabel(value: unknown): string {
  const key = normalizedKey(value);
  return PROBLEM_RESULT_LABELS[key] ?? (key ? "ждём данных" : "—");
}
