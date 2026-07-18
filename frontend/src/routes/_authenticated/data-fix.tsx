// /data-fix — operator-facing "fix blockers step by step" screen.
//
// Primary data source: GET /money/data-blockers
// Supporting:          GET /dashboard/data-health, GET /dq/issues/summary
//
// The page is designed for a non-technical operator. It answers, in order:
//   1. Что не так?
//   2. Почему так получилось?
//   3. С чего начать?
//   4. Пошагово: что сделать?
//   5. Как понять, что починилось?
//   6. Когда можно просто подождать?
//
// All backend jargon (payload / source_table / classification_status / raw
// endpoint paths) is hidden by default and only shown in a small "технический
// маршрут" line at the bottom of each card.

import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useEffect, useState } from "react";
import type { ReactNode } from "react";
import {
  AlertTriangle, CheckCircle2, ShieldAlert, RefreshCw, ArrowRight,
  ListChecks, Hourglass, Wrench, Info, ChevronRight,
} from "lucide-react";

import {
  api,
  type DataQualityIssue,
  type DataQualityIssuesPage,
  type DataQualityIssueSummaryResponse,
  type DashboardDataHealth,
  type MDataBlocker,
  type MDataBlockersResponse,
} from "@/lib/api";
import { fetchDataBlockers } from "@/lib/money-endpoints";
import { useAccounts } from "@/lib/account-context";
import { useDateRange } from "@/lib/date-range-context";
import { API_ENDPOINTS, buildBizQuery } from "@/lib/endpoints";

import { PageShell, PageHeader } from "@/components/PageShell";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Skeleton } from "@/components/ui/skeleton";
import { EndpointError } from "@/components/EndpointError";
import { EmptyState } from "@/components/shell/EmptyState";

import { EvidenceButton, EvidenceDrawer } from "@/components/EvidenceDrawer";
import { MoneyTrustBadge } from "@/components/MoneyTrustBadge";
import { formatMoney, formatNumber } from "@/lib/format";
import { evidenceFrom } from "@/lib/evidence";
import { moneyTrustFrom } from "@/lib/money-trust";
import { humanizeBusinessStatus } from "@/lib/copy";
import { problemCodeLabel } from "@/lib/problem-ux-copy";
import { OperationalFinalBanner } from "@/components/money-ui/OperationalFinalBanner";
import { DataFixWorkbench } from "@/components/data-fix/DataFixWorkbench";
import { DataFixMobileCard } from "@/components/data-fix/DataFixMobileCard";
import { DataDependencyNotice } from "@/components/data-health/DataCoveragePanel";
import { ActionCenterReturnLink } from "@/components/action-center/ActionCenterReturnLink";
import { appendActionCenterProblemHistory } from "@/lib/action-center-task-history";
import { routeSearchText } from "@/lib/action-center-routing";
import { useIsMobile } from "@/hooks/use-mobile";


// ─── Route ───────────────────────────────────────────────────────────────
type DataFixSearch = {
  financial_final_blocker?: boolean;
  only_open?: boolean;
  severity?: string;
  code?: string;
  problem_instance_id?: string;
  nm_id?: string;
};

export const Route = createFileRoute("/_authenticated/data-fix")({
  component: DataFixPage,
  validateSearch: (s: Record<string, unknown>): DataFixSearch => ({
    financial_final_blocker:
      s.financial_final_blocker === true || s.financial_final_blocker === "true" ? true
      : s.financial_final_blocker === false || s.financial_final_blocker === "false" ? false
      : undefined,
    only_open:
      s.only_open === true || s.only_open === "true" ? true
      : s.only_open === false || s.only_open === "false" ? false
      : undefined,
    severity:
      typeof s.severity === "string" ? s.severity
      : Array.isArray(s.severity) ? (s.severity as unknown[]).join(",")
      : undefined,
    code: routeSearchText(s.code),
    problem_instance_id: routeSearchText(s.problem_instance_id),
    nm_id: routeSearchText(s.nm_id),
  }),
  errorComponent: ({ error, reset }) => <EndpointError error={error} reset={reset} />,
});

// ─── Static fallbacks for non-tech copy ──────────────────────────────────
type CodeMeta = {
  simple_reason: string;
  first_action: string;
  how_to_fix: string[];
  success_check: string[];
  wait_or_fix_hint?: string;
  owner_kind?: "user" | "system" | "admin" | "mixed" | "aggregate";
  owner_title?: string;
  owner_message?: string;
  next_screen_path: string;
  next_screen_label: string;
};

const CODE_META: Record<string, CodeMeta> = {
  missing_manual_cost: {
    simple_reason: "Для части карточек не загружена реальная себестоимость поставщика — прибыль считается на оценочной.",
    first_action: "Откройте экран «Себестоимость» и загрузите xlsx с колонками nm_id, sku, cost.",
    how_to_fix: [
      "Откройте экран «Себестоимость».",
      "Найдите карточку без cost_price.",
      "Загрузите файл от поставщика или впишите себестоимость вручную.",
      "Сохраните / подтвердите импорт.",
      "Вернитесь сюда и нажмите «Обновить».",
    ],
    success_check: [
      "У карточки появилась подтверждённая себестоимость.",
      "Блокер исчез из этого списка.",
    ],
    next_screen_path: "/costs",
    next_screen_label: "Открыть себестоимость",
  },
  manual_cost_ambiguous_match: {
    simple_reason: "Один файл себестоимости подходит к нескольким SKU — система не знает, какой выбрать.",
    first_action: "Откройте «Себестоимость» → вкладка «Конфликты».",
    how_to_fix: [
      "Откройте «Себестоимость» → вкладка «Конфликты».",
      "По каждой строке выберите правильный SKU вручную.",
      "Или перезагрузите файл с явным sku_id.",
    ],
    success_check: ["Конфликт пропал из вкладки.", "Себестоимость присвоилась нужному SKU."],
    next_screen_path: "/costs",
    next_screen_label: "Решить конфликты",
  },
  manual_cost_unresolved_sku: {
    simple_reason: "В файле себестоимости есть строки, которые не привязались ни к одному SKU каталога.",
    first_action: "Скачайте список непривязанных строк и проверьте nm_id / sku.",
    how_to_fix: [
      "Откройте «Себестоимость» → «Не привязано».",
      "Скачайте список.",
      "Проверьте nm_id / sku в файле против каталога.",
      "Загрузите исправленный xlsx.",
    ],
    success_check: ["Список непривязанных строк опустел."],
    next_screen_path: "/costs",
    next_screen_label: "Открыть себестоимость",
  },
  sale_without_finance: {
    simple_reason: "Продажа уже произошла, но финансовая строка от WB по ней ещё не пришла. Это системная задержка сверки, а не ручная задача продавца.",
    first_action: "Ничего вручную исправлять не нужно: система дождётся финансового отчёта WB и повторит сверку.",
    how_to_fix: [
      "Система ждёт следующую загрузку финансов WB.",
      "После загрузки она повторно сопоставит продажу с финансовой строкой.",
      "Если строка не закроется автоматически, её разберёт администратор по синхронизации и сопоставлению.",
    ],
    success_check: [
      "Финансовая строка появилась и системная сверка закрылась.",
    ],
    owner_kind: "system",
    owner_title: "Это системная сверка",
    owner_message: "Пользователь не должен менять продажи или суммы вручную. Исправление происходит через синхронизацию финансов WB и сопоставление строк.",
    wait_or_fix_hint: "Если продажа свежая, это нормальная задержка финансов WB.",
    next_screen_path: "/finance",
    next_screen_label: "Открыть финансы",
  },
  finance_reconciliation_mismatch: {
    simple_reason: "Это не ошибка, которую продавец должен чинить вручную. Система сравнила операционную выручку с финансовым отчётом WB и нашла расхождение.",
    first_action: "Сначала проверьте, завершена ли загрузка финансового отчёта WB за этот период. Если отчёт свежий или неполный — это задача синхронизации, а не ручной правки пользователя.",
    how_to_fix: [
      "Откройте «Финансы WB» и посмотрите блок сверки: операционная выручка против финотчёта WB.",
      "Если период ещё не закрыт WB или отчёт пришёл не полностью, дождитесь следующей загрузки.",
      "Если период закрыт, запустите повторную синхронизацию финансового отчёта.",
      "Если после повторной синхронизации расхождение осталось, это задача администратора или разработчика: проверить импорт финансов WB, сопоставление продаж, дедупликацию и формулу сверки.",
      "Пользователь не должен менять продажи или суммы вручную, чтобы «подогнать» отчёт.",
    ],
    success_check: [
      "После повторной загрузки финансового отчёта статус сверки стал «сошлось».",
      "Системная сверка закрылась.",
      "Пользователь не видит это как ручную задачу.",
    ],
    owner_kind: "system",
    owner_title: "Это системный блокер",
    owner_message: "Продавец может только проверить период и запросить повторную синхронизацию. Причина исправляется в системной загрузке данных: импорт финансов WB, сопоставление продаж с отчётом, дедупликация и формулы сверки.",
    wait_or_fix_hint: "Если данные свежие или период WB ещё открыт, корректнее подождать закрытия отчёта и следующей синхронизации.",
    next_screen_path: "/finance",
    next_screen_label: "Проверить сверку",
  },
  finance_without_sale: {
    simple_reason: "В финансовом отчёте WB есть строка, для которой у нас ещё не сопоставилась соответствующая продажа. Это системная задача синхронизации и сопоставления.",
    first_action: "Ничего вручную исправлять не нужно: система повторит загрузку продаж и заказов, затем заново сопоставит строки.",
    how_to_fix: [
      "Система повторяет загрузку продаж и заказов.",
      "После обновления она заново сопоставляет SRID/дату/карточку.",
      "Если строка остаётся несопоставленной, это задача администратора интеграции.",
    ],
    success_check: ["Строка финотчёта автоматически сопоставилась с продажей."],
    owner_kind: "system",
    owner_title: "Это системная сверка",
    owner_message: "Пользователь не должен вручную подгонять продажи под финансовый отчёт. Исправление происходит через системную синхронизацию и сопоставление.",
    next_screen_path: "/finance",
    next_screen_label: "Открыть Финансы",
  },
  unmatched_sku: {
    simple_reason: "В продажах, остатках или себестоимости есть строка с товарным идентификатором, который система не смогла сопоставить с карточкой каталога. Из-за этого деньги или остатки могут попасть не в тот товар.",
    first_action: "Начните с экрана «Себестоимость» → блок «Перепривязать SKU»: найдите строку по nm_id, артикулу продавца или баркоду и запустите перепривязку.",
    how_to_fix: [
      "Откройте «Себестоимость» и найдите блок «Перепривязать SKU».",
      "В таблице проверьте проблемные строки по nm_id, артикулу продавца и баркоду.",
      "Если ошибка пришла из файла себестоимости, исправьте файл: укажите корректные nm_id, barcode и vendor_code.",
      "Загрузите исправленный файл, подтвердите предпросмотр и нажмите «Перепривязать SKU».",
      "Если строки остались после перепривязки, передайте их администратору: нужно проверить правила сопоставления или импорт каталога.",
    ],
    success_check: [
      "В списке «Перепривязать SKU» нет строк по этому nm_id / SKU / баркоду.",
      "Несвязанных SKU стало 0.",
      "После обновления данные по выручке, остаткам и себестоимости попали в правильную карточку.",
    ],
    next_screen_path: "/costs",
    next_screen_label: "Перепривязать SKU",
  },
  expense_unclassified: {
    simple_reason: "Расходная строка WB пришла, но категория расхода не распознана автоматически.",
    first_action: "Откройте «Деньги» → блок «Расходы без категории» и присвойте категорию.",
    how_to_fix: [
      "Откройте «Деньги» → «Расходы без категории».",
      "Для каждой строки выберите категорию из списка.",
      "Нажмите «Сохранить».",
    ],
    success_check: ["Все расходы получили категорию."],
    next_screen_path: "/money",
    next_screen_label: "Открыть Деньги",
  },
  stocks_task_failed: {
    simple_reason: "Задача синхронизации остатков упала — текущий остаток не подтверждён.",
    first_action: "Откройте «Админка» → «Синхронизация» и перезапустите загрузку остатков.",
    how_to_fix: [
      "Откройте «Админка» → «Синхронизация».",
      "Выберите домен «Остатки».",
      "Найдите последний запуск со статусом ошибки.",
      "Нажмите «Перезапустить».",
      "Если ошибка повторилась, передайте администратору домен, дату и короткую причину ошибки.",
    ],
    success_check: ["Синхронизация остатков завершилась успешно."],
    next_screen_path: "/admin",
    next_screen_label: "Открыть синхронизацию",
  },
  no_main_photo: {
    simple_reason: "У карточки отсутствует главное фото — товар плохо ранжируется и слабо конвертит.",
    first_action: "Откройте фотостудию — мы создадим проект и подтянем доступные исходники WB.",
    how_to_fix: [
      "Откройте фотостудию для этого артикула.",
      "Загрузите готовое фото или создайте новый вариант.",
      "Одобрите версию и скачайте файл.",
      "Загрузите файл в личный кабинет Wildberries вручную.",
    ],
    success_check: ["В фотостудии есть одобренная версия.", "Главное фото обновлено в WB."],
    next_screen_path: "/photo-studio",
    next_screen_label: "Открыть фотостудию",
  },
  few_photos: {
    simple_reason: "Слишком мало фотографий — покупатели не видят товар с разных ракурсов.",
    first_action: "Откройте фотостудию и добавьте недостающие ракурсы.",
    how_to_fix: [
      "Откройте проект в фотостудии.",
      "Загрузите дополнительные кадры или сгенерируйте варианты.",
      "Одобрите готовые версии.",
      "Загрузите в WB вручную.",
    ],
    success_check: ["Количество фото в карточке выросло.", "Фотостудия показывает «Готово»."],
    next_screen_path: "/photo-studio",
    next_screen_label: "Открыть фотостудию",
  },
  duplicate_images: {
    simple_reason: "Несколько изображений карточки дублируют друг друга — это снижает доверие.",
    first_action: "Откройте фотостудию и подготовьте уникальные кадры.",
    how_to_fix: [
      "Откройте фотостудию.",
      "Создайте варианты с разным фоном/композицией.",
      "Одобрите и скачайте версии.",
      "Замените дубли в WB вручную.",
    ],
    success_check: ["Дубли пропали из карточки."],
    next_screen_path: "/photo-studio",
    next_screen_label: "Открыть фотостудию",
  },
  main_image_issue: {
    simple_reason: "С главным изображением что-то не так — низкое качество, неподходящий фон или композиция.",
    first_action: "Откройте фотостудию и подготовьте новое главное фото.",
    how_to_fix: [
      "Откройте фотостудию для артикула.",
      "Выберите исходник и операцию (фон, обрезка, улучшение).",
      "Одобрите итоговую версию.",
      "Замените главное фото в WB вручную.",
    ],
    success_check: ["Главное фото обновлено и одобрено внутри фотостудии."],
    next_screen_path: "/photo-studio",
    next_screen_label: "Открыть фотостудию",
  },
  title_missing: {
    simple_reason: "У карточки нет названия — покупатель и поиск WB не понимают, что продаётся.",
    first_action: "Откройте карточку товара и подготовьте нормальное название.",
    how_to_fix: [
      "Откройте карточку товара.",
      "Сформулируйте название с типом товара, брендом и ключевым отличием.",
      "Обновите название в кабинете WB вручную.",
      "Запустите повторную проверку качества карточки.",
    ],
    success_check: ["Оценка карточки выросла.", "Блокер по названию исчез."],
    next_screen_path: "/products",
    next_screen_label: "Открыть товары",
  },
  title_too_short: {
    simple_reason: "Название слишком короткое и плохо объясняет товар.",
    first_action: "Добавьте в название тип товара, материал или назначение.",
    how_to_fix: [
      "Откройте карточку товара.",
      "Проверьте, понятно ли название без фото.",
      "Добавьте важные свойства без спама и повторов.",
      "Обновите название в WB вручную.",
    ],
    success_check: ["Название стало информативным.", "Проверка качества больше не показывает проблему title."],
    next_screen_path: "/products",
    next_screen_label: "Открыть товары",
  },
  title_too_long: {
    simple_reason: "Название перегружено — его трудно быстро прочитать.",
    first_action: "Сократите название до товара и нескольких важных характеристик.",
    how_to_fix: [
      "Откройте карточку товара.",
      "Уберите повторы, лишние знаки и второстепенные слова.",
      "Оставьте понятный товарный смысл.",
      "Обновите название в WB вручную.",
    ],
    success_check: ["Название читается без обрезки.", "Блокер title исчез после повторной проверки."],
    next_screen_path: "/products",
    next_screen_label: "Открыть товары",
  },
  title_repeated_words: {
    simple_reason: "В названии повторяются слова — карточка выглядит как спам.",
    first_action: "Уберите повторяющиеся слова из названия.",
    how_to_fix: [
      "Откройте карточку товара.",
      "Сравните повторяющиеся слова и оставьте одно корректное упоминание.",
      "Обновите название в WB вручную.",
    ],
    success_check: ["Название стало естественным.", "Повторная проверка не показывает проблему title."],
    next_screen_path: "/products",
    next_screen_label: "Открыть товары",
  },
  title_excessive_punctuation_caps: {
    simple_reason: "Название выглядит агрессивно из-за caps lock или лишней пунктуации.",
    first_action: "Перепишите название обычным регистром и без лишних знаков.",
    how_to_fix: [
      "Откройте карточку товара.",
      "Замените caps lock на обычный регистр.",
      "Уберите лишние знаки препинания.",
      "Обновите название в WB вручную.",
    ],
    success_check: ["Название выглядит аккуратно.", "Проверка больше не показывает проблему оформления title."],
    next_screen_path: "/products",
    next_screen_label: "Открыть товары",
  },
  title_equals_vendor_code: {
    simple_reason: "Название совпадает с артикулом продавца и не объясняет товар покупателю.",
    first_action: "Замените технический артикул на понятное товарное название.",
    how_to_fix: [
      "Откройте карточку товара.",
      "Возьмите артикул только как внутреннюю подсказку.",
      "Напишите название товара человеческим языком.",
      "Обновите название в WB вручную.",
    ],
    success_check: ["Название больше не совпадает с vendor_code.", "Проверка качества стала чище."],
    next_screen_path: "/products",
    next_screen_label: "Открыть товары",
  },
  description_missing: {
    simple_reason: "Описание отсутствует — покупатель не видит состав, назначение и ограничения товара.",
    first_action: "Добавьте описание с реальными свойствами товара.",
    how_to_fix: [
      "Откройте карточку товара.",
      "Соберите факты о материале, комплектации, уходе и сценариях использования.",
      "Добавьте описание в WB вручную.",
      "Запустите повторную проверку качества.",
    ],
    success_check: ["Описание заполнено.", "Блокер description исчез."],
    next_screen_path: "/products",
    next_screen_label: "Открыть товары",
  },
  description_too_short: {
    simple_reason: "Описание слишком короткое и не закрывает вопросы покупателя.",
    first_action: "Расширьте описание реальными деталями товара.",
    how_to_fix: [
      "Откройте карточку товара.",
      "Добавьте материал, назначение, комплектацию, уход и ограничения.",
      "Не добавляйте выдуманные преимущества.",
      "Обновите описание в WB вручную.",
    ],
    success_check: ["Описание стало содержательным.", "Проверка больше не показывает description_too_short."],
    next_screen_path: "/products",
    next_screen_label: "Открыть товары",
  },
  description_duplicates_title: {
    simple_reason: "Описание повторяет название и не добавляет полезной информации.",
    first_action: "Напишите отдельное описание вместо копии названия.",
    how_to_fix: [
      "Откройте карточку товара.",
      "Оставьте название кратким, а описание используйте для деталей.",
      "Обновите описание в WB вручную.",
    ],
    success_check: ["Описание отличается от названия.", "Блокер description исчез."],
    next_screen_path: "/products",
    next_screen_label: "Открыть товары",
  },
  description_no_useful_details: {
    simple_reason: "В описании мало конкретики о товаре.",
    first_action: "Добавьте факты, которые помогают покупателю выбрать товар.",
    how_to_fix: [
      "Откройте карточку товара.",
      "Добавьте характеристики, комплектность, уход и сценарии использования.",
      "Обновите описание в WB вручную.",
    ],
    success_check: ["Описание содержит конкретные детали.", "Повторная проверка не показывает проблему description."],
    next_screen_path: "/products",
    next_screen_label: "Открыть товары",
  },
  characteristics_missing: {
    simple_reason: "У карточки нет характеристик — фильтры и сравнение товара работают хуже.",
    first_action: "Заполните доступные характеристики в кабинете WB.",
    how_to_fix: [
      "Откройте карточку товара.",
      "Проверьте предмет товара и доступные поля характеристик.",
      "Заполните важные поля в WB вручную.",
      "Запустите повторную проверку качества.",
    ],
    success_check: ["Характеристики появились.", "Блокер characteristics исчез."],
    next_screen_path: "/products",
    next_screen_label: "Открыть товары",
  },
  characteristic_value_empty: {
    simple_reason: "В одной из характеристик пустое значение.",
    first_action: "Заполните пустое значение или удалите лишнюю характеристику.",
    how_to_fix: [
      "Откройте карточку товара.",
      "Найдите характеристику без значения.",
      "Заполните её реальным значением в WB вручную.",
    ],
    success_check: ["Пустых характеристик не осталось.", "Проверка characteristics стала чище."],
    next_screen_path: "/products",
    next_screen_label: "Открыть товары",
  },
  high_value_characteristics_missing: {
    simple_reason: "Не заполнены базовые характеристики вроде цвета, материала, размера или комплектации.",
    first_action: "Добавьте ключевые характеристики, которые важны для выбора товара.",
    how_to_fix: [
      "Откройте карточку товара.",
      "Проверьте поля цвета, материала, размера, пола и комплектации.",
      "Заполните применимые поля в WB вручную.",
    ],
    success_check: ["Базовые характеристики заполнены.", "Проверка качества больше не показывает этот блокер."],
    next_screen_path: "/products",
    next_screen_label: "Открыть товары",
  },
  media_no_images: {
    simple_reason: "У карточки нет фотографий — она не готова к нормальной продаже.",
    first_action: "Откройте фотостудию и подготовьте главное фото.",
    how_to_fix: [
      "Откройте фотостудию для товара.",
      "Загрузите или подготовьте главное фото.",
      "Одобрите версию и скачайте файл.",
      "Загрузите фото в WB вручную.",
    ],
    success_check: ["У карточки появилось главное фото.", "Проверка media больше не критичная."],
    next_screen_path: "/photo-studio",
    next_screen_label: "Открыть фотостудию",
  },
  media_too_few_images: {
    simple_reason: "Фотографий мало — покупатель не видит товар с разных сторон.",
    first_action: "Добавьте дополнительные ракурсы в фотостудии.",
    how_to_fix: [
      "Откройте фотостудию для товара.",
      "Подготовьте общий вид, детали, материал и размер.",
      "Одобрите версии и загрузите их в WB вручную.",
    ],
    success_check: ["Фото стало не меньше трёх.", "Проверка media больше не показывает media_too_few_images."],
    next_screen_path: "/photo-studio",
    next_screen_label: "Открыть фотостудию",
  },
  media_duplicate_urls: {
    simple_reason: "В карточке повторяются фото, которые не дают покупателю новой информации.",
    first_action: "Замените дубли на разные ракурсы товара.",
    how_to_fix: [
      "Откройте фотостудию.",
      "Подготовьте уникальные кадры.",
      "Замените дубли в WB вручную.",
    ],
    success_check: ["Повторов фото не осталось.", "Проверка media стала чище."],
    next_screen_path: "/photo-studio",
    next_screen_label: "Открыть фотостудию",
  },
  media_invalid_url: {
    simple_reason: "В карточке есть некорректная ссылка на изображение — возможно, медиа синхронизировались не полностью.",
    first_action: "Пересинхронизируйте карточку или проверьте фото в WB.",
    how_to_fix: [
      "Откройте карточку товара и проверьте список фото.",
      "Если фото есть в WB, запустите синхронизацию карточек.",
      "Если фото сломано в WB, замените его вручную.",
    ],
    success_check: ["Ссылки на фото корректны.", "media_invalid_url исчез после повторной проверки."],
    next_screen_path: "/photo-studio",
    next_screen_label: "Открыть фотостудию",
  },
  price_jump: {
    simple_reason: "Платформа зафиксировала резкое изменение цены. Это не ошибка данных — это сигнал перепроверить решение.",
    first_action: "Откройте страницу цен и проверьте: планировалось ли такое изменение и корректна ли минимальная безопасная цена.",
    how_to_fix: [
      "Откройте раздел цен по этому товару.",
      "Сравните текущую цену с целевой и минимально безопасной ценой.",
      "Если цена задана WB или акцией — уточните причину.",
      "При необходимости откорректируйте цену в кабинете WB вручную.",
    ],
    success_check: [
      "Цена соответствует плановому диапазону.",
      "Платформа больше не показывает резкий скачок.",
    ],
    owner_kind: "user",
    owner_title: "Цена не меняется автоматически",
    owner_message: "Платформа только показывает резкое изменение и предлагает проверить его. Никакие цены не меняются автоматически.",
    next_screen_path: "/pricing",
    next_screen_label: "Проверить цену",
  },
  missing_cost_blocks_profit: {
    simple_reason: "Без себестоимости платформа не может посчитать прибыль и маржу по этой карточке.",
    first_action: "Загрузите себестоимость или заполните её в таблице.",
    how_to_fix: [
      "Откройте раздел «Себестоимость».",
      "Загрузите файл поставщика или впишите себестоимость вручную.",
      "Сохраните изменения и запустите повторную проверку.",
    ],
    success_check: ["У карточки появилась подтверждённая себестоимость.", "Расчёт прибыли и маржи разблокирован."],
    owner_kind: "user",
    next_screen_path: "/costs",
    next_screen_label: "Загрузить себестоимость",
  },
};

// Spec mentions /discrepancies and /health — they're aliases for screens that
// already exist in this app.
const PATH_ALIASES: Record<string, string> = {
  "/discrepancies": "/data-fix",
  "/health": "/dashboard",
};

const STATIC_FIRST_CODES = new Set([
  "finance_reconciliation_mismatch",
  "finance_without_sale",
  "sale_without_finance",
]);

const BLOCKER_TO_ISSUE_CODES: Record<string, string[]> = {
  unmatched_sku_detected: ["unmatched_sku"],
  supplier_cost_coverage_below_threshold: [
    "missing_manual_cost",
    "seller_other_expense_missing",
    "manual_cost_unresolved_sku",
    "manual_cost_ambiguous_match",
  ],
  ads_not_allocated_to_profitability: ["ad_spend_without_sku"],
  ads_overallocated_to_profitability: ["expense_ad_double_count_risk"],
};

const EXACT_OWNER: Record<string, Pick<CodeMeta, "owner_kind" | "owner_title" | "owner_message">> = {
  latest_stocks_not_completed: {
    owner_kind: "system",
    owner_title: "Ответственный: система / администратор",
    owner_message: "Это не ручная правка цифр. Нужно дождаться завершенной загрузки остатков или перезапустить синхронизацию.",
  },
  failed_sync_domains: {
    owner_kind: "admin",
    owner_title: "Ответственный: система / администратор",
    owner_message: "Проблема в загрузке источников данных. Пользователь не должен менять суммы вручную; нужно перезапустить sync или открыть админ-разбор.",
  },
  open_blocking_dq_issues: {
    owner_kind: "aggregate",
    owner_title: "Это сводный блокер",
    owner_message: "Его нужно раскрывать на конкретные задачи ниже: себестоимость, SKU, расходы, синхронизация или админ-разбор.",
  },
  finance_reconciliation_mismatch: {
    owner_kind: "system",
    owner_title: "Ответственный: система / администратор",
    owner_message: "WB финансовые факты нельзя подгонять вручную. Сначала повторяется загрузка и сверка, затем при необходимости подключается администратор.",
  },
  sale_without_finance: {
    owner_kind: "system",
    owner_title: "Ответственный: система",
    owner_message: "Чаще всего это задержка финансового отчета WB. Пользователь ничего вручную не исправляет.",
  },
  finance_without_sale: {
    owner_kind: "system",
    owner_title: "Ответственный: система",
    owner_message: "Это сопоставление отчета WB с продажами/заказами. Исправление идет через синхронизацию и re-check.",
  },
  ads_overallocated_to_profitability: {
    owner_kind: "admin",
    owner_title: "Ответственный: администратор",
    owner_message: "Это риск формулы или маппинга рекламы. Пользователь не должен вручную менять рекламные расходы.",
  },
};

function issueLookupCodesForBlocker(code?: string | null): string[] {
  const normalized = String(code || "").trim().toLowerCase();
  if (!normalized) return [];
  return Array.from(new Set([...(BLOCKER_TO_ISSUE_CODES[normalized] ?? []), normalized]));
}

function issueForBlocker(blocker: MDataBlocker, issueByCode: Map<string, DataQualityIssue>): DataQualityIssue | null {
  for (const code of issueLookupCodesForBlocker(blocker.code)) {
    const issue = issueByCode.get(code);
    if (issue) return issue;
  }
  return null;
}

function ownershipForCode(code: string): Pick<CodeMeta, "owner_kind" | "owner_title" | "owner_message"> {
  const exact = EXACT_OWNER[code];
  if (exact) return exact;
  if (
    code.includes("finance") ||
    code.includes("sync") ||
    code.includes("task") ||
    code.includes("scheduler") ||
    code.includes("missed_load")
  ) {
    return {
      owner_kind: "system",
      owner_title: "Ответственный: система / администратор",
      owner_message: "Пользователь не должен вручную менять суммы. Сначала проверяется синхронизация и импорт, затем при необходимости администратор разбирает правила загрузки WB и сверки данных.",
    };
  }
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
  ) {
    return {
      owner_kind: "user",
      owner_title: "Ответственный: оператор / продавец",
      owner_message: "Эта проблема закрывается вводом реальных бизнес-данных или заполнением карточки в кабинете WB.",
    };
  }
  if (
    code.includes("unmatched") ||
    code.includes("expense") ||
    code.includes("stock") ||
    code.includes("barcode") ||
    code.includes("vendor_code") ||
    code.includes("chrt")
  ) {
    return {
      owner_kind: "mixed",
      owner_title: "Ответственный: оператор + администратор",
      owner_message: "Оператор проверяет проблему и запускает привязку или повторную синхронизацию. Если через текущие экраны она не закрывается, администратор проверяет правила сопоставления и импорта.",
    };
  }
  return {
    owner_kind: "mixed",
    owner_title: "Ответственный: нужно уточнить",
    owner_message: "Сначала откройте рекомендованный экран. Если там нет понятного действия для исправления, передайте проблему администратору на проверку импорта и сопоставления данных.",
  };
}

function routeInstruction(path: string, code?: string | null): string {
  const normalizedCode = String(code || "").toLowerCase();
  if (path.startsWith("/costs") && path.includes("focus=missing-costs")) {
    return "Экран: Себестоимость → рабочая таблица. Фильтр «Нет себестоимости» включится автоматически: впишите цену в «Себестоимость», при необходимости заполните «Прочие расходы» и нажмите «Сохранить изменения».";
  }
  if (path.startsWith("/costs") && path.includes("focus=other-expenses")) {
    return "Экран: Себестоимость → рабочая таблица. Фильтр «Нет прочих расходов» включится автоматически: впишите сумму в «Прочие расходы» или поставьте 0, затем нажмите «Сохранить изменения».";
  }
  if (path.startsWith("/costs") && path.includes("focus=relink-sku")) {
    return "Экран: Себестоимость → блок «Перепривязать SKU». Проверьте nm_id, артикул и баркод, затем нажмите «Перепривязать SKU».";
  }
  if (path.startsWith("/costs") && normalizedCode.includes("unmatched_sku")) {
    return "Экран: Себестоимость → блок «Перепривязать SKU». Проверьте nm_id, артикул и баркод в таблице, затем загрузите исправленный файл или нажмите «Перепривязать SKU».";
  }
  if (path.startsWith("/costs")) return "Экран: Себестоимость. Загрузите нужный файл, проверьте предпросмотр и подтвердите импорт.";
  if (path.startsWith("/finance")) return "Экран: Финансы WB. Сначала проверьте сверку и финансовый отчёт, затем запустите повторную синхронизацию или передайте проблему администратору.";
  if (path.startsWith("/money")) return "Экран: Деньги. Откройте детализацию расходов или рекламы и найдите строку, из-за которой появилась проблема.";
  if (path.startsWith("/data-fix")) return "Экран: Починка данных. Начните с первого критичного блокера в списке ниже и выполните его шаги.";
  if (path.startsWith("/products")) return "Экран: Товары. Откройте карточку и заполните рекомендованное поле контента в кабинете WB.";
  if (path.startsWith("/photo-studio")) return "Экран: Фотостудия. Подготовьте нужное изображение, подтвердите его и загрузите в кабинет WB.";
  if (path.startsWith("/admin") || path.startsWith("/dashboard")) return "Экран: Админка → Синхронизация. Найдите проблемный домен и запустите повторную загрузку.";
  return "Откройте рекомендованный экран и выполните первое действие, указанное в блокере.";
}

function isSystemHandledBlocker(blocker: MDataBlocker): boolean {
  const backendOwner = (blocker as any).owner_type as string | null | undefined;
  const backendFix = (blocker as any).fixability as string | null | undefined;
  const backendNature = (blocker as any).issue_nature as string | null | undefined;
  if (backendOwner === "system" || backendOwner === "admin") return true;
  if (backendFix === "system_only" || backendFix === "admin_only" || backendFix === "wait_for_sync") return true;
  if (backendNature === "system_check" || backendNature === "sync_waiting" || backendNature === "finance_investigation") return true;
  const owner = ownershipForCode(String(blocker.code || "").toLowerCase()).owner_kind;
  return owner === "system" || owner === "admin" || owner === "aggregate";
}


function resolvePath(p?: string | null): string {
  if (!p) return "/dashboard";
  return PATH_ALIASES[p] ?? p;
}

function normalizeNextScreenPath(code: string, path?: string | null): string {
  const resolved = resolvePath(path);
  if (resolved === "/costs") {
    if (code === "seller_other_expense_missing") {
      return "/costs?focus=other-expenses";
    }
    if (
      code === "missing_manual_cost" ||
      code === "supplier_cost_coverage_below_threshold"
    ) {
      return "/costs?focus=missing-costs";
    }
    if (code === "unmatched_sku_detected" || code === "unmatched_sku" || code.includes("unresolved_sku")) {
      return "/costs?focus=relink-sku";
    }
  }
  return resolved;
}

function linkPropsForPath(path: string): { to: string; search?: Record<string, string> } {
  const [pathname, query = ""] = path.split("?");
  const search = Object.fromEntries(new URLSearchParams(query).entries());
  return Object.keys(search).length > 0
    ? { to: pathname, search }
    : { to: pathname };
}

function metaFor(b: MDataBlocker): CodeMeta {
  const code = (b.code ?? "").toLowerCase();
  const metaCode = code === "unmatched_sku_detected" ? "unmatched_sku" : code;
  const fb = CODE_META[metaCode];
  const staticFirst = STATIC_FIRST_CODES.has(code);
  const ownership = fb?.owner_kind ? {
    owner_kind: fb.owner_kind,
    owner_title: fb.owner_title,
    owner_message: fb.owner_message,
  } : ownershipForCode(code);
  // Prefer backend-provided fields, then static fallback, then generic copy.
  return {
    simple_reason: (staticFirst ? fb?.simple_reason || b.simple_reason : b.simple_reason || fb?.simple_reason) || b.business_impact || "Проверьте детали ниже.",
    first_action: (staticFirst ? fb?.first_action || b.first_action : b.first_action || fb?.first_action) || (b.how_to_fix?.[0] ?? "Откройте экран ниже и следуйте подсказкам."),
    how_to_fix: (staticFirst ? fb?.how_to_fix : b.how_to_fix && b.how_to_fix.length > 0 ? b.how_to_fix : fb?.how_to_fix) ?? [],
    success_check: (staticFirst ? fb?.success_check : b.success_check && b.success_check.length > 0 ? b.success_check : fb?.success_check) ?? [
      "Блокер пропал из этого списка.",
    ],
    wait_or_fix_hint: (staticFirst ? fb?.wait_or_fix_hint ?? b.wait_or_fix_hint : b.wait_or_fix_hint ?? fb?.wait_or_fix_hint) ?? undefined,
    owner_kind: ownership.owner_kind,
    owner_title: ownership.owner_title,
    owner_message: ownership.owner_message,
    next_screen_path: normalizeNextScreenPath(code, staticFirst ? fb?.next_screen_path || b.next_screen_path : b.next_screen_path || fb?.next_screen_path),
    next_screen_label: (staticFirst ? fb?.next_screen_label || b.next_screen_label : b.next_screen_label || fb?.next_screen_label) || "Перейти к починке",
  };
}

// SSR-safe date format: avoid locale-dependent output that diverges between
// server and client (Node uses ICU defaults; the browser uses the user's
// locale → hydration mismatch). Produces "YYYY-MM-DD HH:mm" in UTC.
function formatGeneratedAt(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())} ${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())} UTC`;
}

// ─── Visual helpers ──────────────────────────────────────────────────────
const PRIO_STYLE: Record<string, { badge: string; bar: string; icon: string }> = {
  critical: { badge: "bg-destructive/15 text-destructive border-destructive/30", bar: "bg-destructive", icon: "text-destructive" },
  high:     { badge: "bg-warning/15 text-warning border-warning/30",              bar: "bg-warning",     icon: "text-warning" },
  medium:   { badge: "bg-primary/10 text-primary border-primary/30",              bar: "bg-primary",     icon: "text-primary" },
  low:      { badge: "bg-muted text-muted-foreground border-border",              bar: "bg-muted-foreground", icon: "text-muted-foreground" },
};
const PRIO_LABEL: Record<string, string> = {
  critical: "Критично", high: "Важно", medium: "Средне", low: "Низкое",
};

function KpiTile({
  label, value, tone = "default", hint,
}: { label: string; value: React.ReactNode; tone?: "default" | "danger" | "warning" | "success"; hint?: string }) {
  const toneCls =
    tone === "danger"  ? "border-destructive/40 bg-destructive/5" :
    tone === "warning" ? "border-warning/40 bg-warning/5" :
    tone === "success" ? "border-emerald-500/40 bg-emerald-500/5" :
    "";
  return (
    <Card className={toneCls}>
      <CardContent className="p-4">
        <div className="text-xs uppercase tracking-wide text-muted-foreground">{label}</div>
        <div className="text-2xl font-semibold mt-1">{value}</div>
        {hint ? <div className="text-xs text-muted-foreground mt-1">{hint}</div> : null}
      </CardContent>
    </Card>
  );
}

function SummaryCard({
  label,
  value,
  hint,
  tone = "default",
  active,
  onClick,
  disabled,
}: {
  label: string;
  value: number;
  hint: string;
  tone?: "default" | "danger" | "warning" | "success";
  active?: boolean;
  onClick?: () => void;
  disabled?: boolean;
}) {
  const toneCls =
    tone === "danger" ? "border-destructive/40 bg-destructive/5" :
    tone === "warning" ? "border-warning/40 bg-warning/5" :
    tone === "success" ? "border-emerald-500/40 bg-emerald-500/5" :
    "";
  const ringCls = active ? "ring-2 ring-primary" : "";
  const clickCls = disabled ? "opacity-70 cursor-default" : "cursor-pointer hover:border-primary/40";
  return (
    <Card
      className={`${toneCls} ${ringCls} ${clickCls} transition-colors`}
      role={disabled ? undefined : "button"}
      tabIndex={disabled ? -1 : 0}
      onClick={disabled ? undefined : onClick}
      onKeyDown={(e) => {
        if (disabled || !onClick) return;
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onClick(); }
      }}
    >
      <CardContent className="p-4">
        <div className="text-[11px] uppercase tracking-wide text-muted-foreground">{label}</div>
        <div className="text-2xl font-semibold mt-1 tabular-nums">{value}</div>
        <div className="text-[11px] text-muted-foreground mt-1 leading-snug">{hint}</div>
      </CardContent>
    </Card>
  );
}


function valueFromAny(obj: any, keys: string[]): string | number | null {
  for (const key of keys) {
    const value = obj?.[key];
    if (typeof value === "string" && value.trim()) return value;
    if (typeof value === "number" && Number.isFinite(value)) return value;
  }
  return null;
}

function blockerSamples(blocker: MDataBlocker): Array<Record<string, unknown>> {
  const inputs = blocker.calculation_inputs ?? [];
  if (inputs.length === 0) return [];
  const sample: Record<string, unknown> = {};
  for (const input of inputs) {
    if (!input.label) continue;
    sample[input.label] = input.value ?? input.unit ?? input.source ?? null;
  }
  return Object.keys(sample).length > 0 ? [sample] : [];
}

function UnmatchedSkuGuide({ blocker }: { blocker: MDataBlocker }) {
  const samples = blockerSamples(blocker);
  const rows = samples;

  return (
    <section className="rounded-md border border-amber-500/30 bg-amber-500/5 p-3 space-y-2">
      <div className="text-[11px] uppercase tracking-wide text-amber-700 dark:text-amber-300 font-semibold flex items-center gap-1.5">
        <Wrench className="h-3.5 w-3.5" /> Где именно искать
      </div>
      <div className="text-sm leading-relaxed">
        Откройте <b>Себестоимость → Перепривязать SKU</b> и фильтруйте строку по этим полям: сначала <b>nm_id</b>, затем <b>SKU</b>, <b>баркод</b> и <b>артикул продавца</b>.
      </div>
      {rows.length > 0 ? (
        <div className="grid gap-2">
          {rows.map((row, index) => {
            const nmId = valueFromAny(row, ["nm_id", "nmId"]);
            const skuId = valueFromAny(row, ["sku_id", "skuId", "sku"]);
            const barcode = valueFromAny(row, ["barcode", "bar_code"]);
            const vendorCode = valueFromAny(row, ["vendor_code", "vendorCode", "article", "sa_name"]);
            const source = valueFromAny(row, ["source", "source_table", "source_module", "source_name", "table"]);
            return (
              <div key={index} className="grid grid-cols-2 md:grid-cols-5 gap-2 rounded border bg-background/70 p-2 text-xs">
                <div><span className="text-muted-foreground">nm_id</span><div className="font-mono">{nmId ?? "—"}</div></div>
                <div><span className="text-muted-foreground">SKU</span><div className="font-mono">{skuId ?? "—"}</div></div>
                <div><span className="text-muted-foreground">Баркод</span><div className="font-mono">{barcode ?? "—"}</div></div>
                <div><span className="text-muted-foreground">Артикул</span><div className="font-mono">{vendorCode ?? "—"}</div></div>
                <div><span className="text-muted-foreground">Источник</span><div>{source ?? "продажи / остатки / себестоимость"}</div></div>
              </div>
            );
          })}
        </div>
      ) : (
        <div className="text-xs text-muted-foreground">
          В ответе API нет конкретной строки-примера. Поэтому начните с общего списка «Перепривязать SKU» и сортируйте по последним проблемным строкам.
        </div>
      )}
    </section>
  );
}

function GuidedWorkflowCard({
  icon,
  title,
  body,
  footer,
  tone = "default",
}: {
  icon: ReactNode;
  title: string;
  body: string;
  footer?: string;
  tone?: "default" | "primary";
}) {
  return (
    <section className={`rounded-md border p-3 ${tone === "primary" ? "border-primary/30 bg-primary/5" : "bg-background"}`}>
      <div className={`text-[11px] uppercase tracking-wide font-semibold flex items-center gap-1.5 ${tone === "primary" ? "text-primary" : "text-muted-foreground"}`}>
        {icon} {title}
      </div>
      <p className="text-sm mt-1 leading-relaxed">{body}</p>
      {footer ? (
        <div className="mt-2 rounded border bg-background/70 px-2.5 py-2 text-xs text-muted-foreground">
          <span className="font-medium text-foreground">Где искать: </span>
          {footer}
        </div>
      ) : null}
    </section>
  );
}

function ActionButtonsGuide({
  meta,
  workbenchLabel,
  hasWorkbench,
}: {
  meta: CodeMeta;
  workbenchLabel: string;
  hasWorkbench: boolean;
}) {
  const owner = meta.owner_kind ?? "mixed";
  const manualHint =
    owner === "system"
      ? "Это не ручная правка чисел: мастер покажет статус, re-check или передачу администратору."
      : owner === "admin"
      ? "Мастер откроет разбор и позволит передать задачу администратору без изменения сумм."
      : owner === "aggregate"
      ? "Мастер разложит общий блокер на конкретные причины."
      : "Мастер откроет конкретные строки и покажет, что именно заполнить или выбрать.";
  return (
    <section className="rounded-md border bg-primary/5 border-primary/25 p-3">
      <div className="text-[11px] uppercase tracking-wide text-primary font-semibold flex items-center gap-1.5">
        <Wrench className="h-3.5 w-3.5" /> Какие кнопки нажимать
      </div>
      <ol className="mt-2 space-y-2 text-sm">
        {hasWorkbench ? (
          <li className="flex gap-2">
            <span className="shrink-0 inline-flex h-5 w-5 items-center justify-center rounded-full bg-primary/15 text-primary text-[11px] font-semibold">1</span>
            <span>
              Нажмите <b>{workbenchLabel}</b>. {manualHint}
            </span>
          </li>
        ) : null}
        <li className="flex gap-2">
          <span className="shrink-0 inline-flex h-5 w-5 items-center justify-center rounded-full bg-primary/15 text-primary text-[11px] font-semibold">{hasWorkbench ? 2 : 1}</span>
          <span>
            Нажмите <b>{meta.next_screen_label}</b>, если нужно открыть исходный экран: {routeInstruction(meta.next_screen_path)}.
          </span>
        </li>
        <li className="flex gap-2">
          <span className="shrink-0 inline-flex h-5 w-5 items-center justify-center rounded-full bg-primary/15 text-primary text-[11px] font-semibold">{hasWorkbench ? 3 : 2}</span>
          <span>
            После исправления нажмите <b>Обновить</b> или дождитесь автоматической перепроверки. Платформа пересчитает проблему и уберет её из списка, если условие выполнено.
          </span>
        </li>
      </ol>
    </section>
  );
}

// ─── Blocker card ────────────────────────────────────────────────────────
function BlockerCard({
  blocker,
  index,
  highlight,
  issue,
  onOpenWorkbench,
}: {
  blocker: MDataBlocker;
  index: number;
  highlight?: boolean;
  issue?: DataQualityIssue | null;
  onOpenWorkbench?: (issue: DataQualityIssue, blocker: MDataBlocker) => void;
}) {
  const [evidenceOpen, setEvidenceOpen] = useState(false);
  const m = metaFor(blocker);
  const ledger = evidenceFrom(blocker.evidence_ledger);
  const moneyTrust = moneyTrustFrom(blocker.money_trust, ledger?.money_trust);
  const revenueOnlyBlocked = moneyTrust.impact_kind === "blocked_revenue" || ((blocker.affected_amount ?? 0) === 0 && (blocker.affected_revenue ?? 0) > 0);
  const prio = (blocker.priority ?? "medium").toLowerCase();
  const style = PRIO_STYLE[prio] ?? PRIO_STYLE.medium;
  const workbenchLabel =
    m.owner_kind === "system" ? "Проверить статус"
    : m.owner_kind === "admin" ? "Открыть разбор"
    : m.owner_kind === "aggregate" ? "Разобрать причины"
    : "Исправить здесь";
  const showStats =
    (blocker.affected_sku_count ?? 0) > 0 ||
    (blocker.affected_revenue ?? 0) > 0;
  const showCurrentRequired =
    (blocker.current_value ?? 0) !== 0 ||
    (blocker.required_value ?? 0) !== 0 ||
    !!blocker.unit;

  return (
    <>
    <Card id={`blocker-${blocker.code}`} className={`relative overflow-hidden scroll-mt-24 transition-shadow ${highlight ? "ring-2 ring-primary shadow-lg" : ""}`}>
      <div className={`absolute left-0 top-0 bottom-0 w-1.5 ${style.bar}`} />
      <CardHeader className="pl-6">
        <div className="flex items-start justify-between gap-3 flex-wrap">
          <div className="space-y-1.5 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <Badge variant="outline" className="text-[10px] font-mono">№{index + 1}</Badge>
              <Badge variant="outline" className={`text-[10px] uppercase ${style.badge}`}>
                {PRIO_LABEL[prio] ?? prio}
              </Badge>
              <MoneyTrustBadge trust={moneyTrust} />
              <span className="text-[11px] text-muted-foreground">Блокер #{index + 1}</span>
            </div>
            <CardTitle className="text-base leading-snug">{blocker.title}</CardTitle>
            {blocker.business_impact ? (
              <CardDescription className="text-sm">{blocker.business_impact}</CardDescription>
            ) : null}
          </div>
          <div className="flex shrink-0 flex-wrap justify-end gap-2">
            {issue && onOpenWorkbench ? (
              <Button size="sm" variant="outline" onClick={() => onOpenWorkbench(issue, blocker)}>
                <Wrench className="h-3.5 w-3.5 mr-1.5" />
                {workbenchLabel}
              </Button>
            ) : null}
            {ledger ? (
              <EvidenceButton ledger={ledger} onClick={() => setEvidenceOpen(true)} />
            ) : null}
            <Button asChild size="sm">
              <Link {...(linkPropsForPath(m.next_screen_path) as any)}>
                {m.next_screen_label} <ArrowRight className="h-3.5 w-3.5 ml-1.5" />
              </Link>
            </Button>
          </div>
        </div>
      </CardHeader>

      <CardContent className="pl-6 space-y-4">
        {showStats ? (
          <div className={`grid grid-cols-2 ${showCurrentRequired ? "sm:grid-cols-4" : "sm:grid-cols-2"} gap-2 text-xs`}>
            <div className="rounded-md border bg-muted/30 px-2.5 py-2">
              <div className="text-muted-foreground">Затронуто SKU</div>
              <div className="font-semibold text-sm">{formatNumber(blocker.affected_sku_count ?? 0)}</div>
            </div>
            <div className="rounded-md border bg-muted/30 px-2.5 py-2">
              <div className="text-muted-foreground">{revenueOnlyBlocked ? "Выручка без подтверждения" : "Затронутая выручка"}</div>
              <div className="font-semibold text-sm">{formatMoney(blocker.affected_revenue ?? 0)}</div>
              {revenueOnlyBlocked ? <div className="text-[10px] text-muted-foreground">это не подтвержденная потеря денег</div> : null}
            </div>
            {showCurrentRequired ? (
              <>
                <div className="rounded-md border bg-muted/30 px-2.5 py-2">
                  <div className="text-muted-foreground">Сейчас</div>
                  <div className="font-semibold text-sm">
                    {formatNumber(blocker.current_value ?? 0)}{blocker.unit ? ` ${blocker.unit}` : ""}
                  </div>
                </div>
                <div className="rounded-md border bg-muted/30 px-2.5 py-2">
                  <div className="text-muted-foreground">Нужно</div>
                  <div className="font-semibold text-sm">
                    {formatNumber(blocker.required_value ?? 0)}{blocker.unit ? ` ${blocker.unit}` : ""}
                  </div>
                </div>
              </>
            ) : null}
          </div>
        ) : null}

        <BlockerCalculation blocker={blocker} />

        <div className="grid gap-3 lg:grid-cols-2">
          <GuidedWorkflowCard
            icon={<Info className="h-3.5 w-3.5" />}
            title="1. Что произошло"
            body={m.simple_reason}
          />
          <GuidedWorkflowCard
            icon={<ChevronRight className="h-3.5 w-3.5" />}
            title="2. С чего начать"
            body={m.first_action}
            footer={routeInstruction(m.next_screen_path, blocker.code)}
            tone="primary"
          />
        </div>

        {m.owner_kind ? (
          <section className={`rounded-md border p-3 ${
            m.owner_kind === "system"
              ? "border-blue-500/30 bg-blue-500/5"
              : m.owner_kind === "user"
              ? "border-emerald-500/30 bg-emerald-500/5"
              : "border-amber-500/30 bg-amber-500/5"
          }`}>
            <div className={`text-[11px] uppercase tracking-wide font-semibold flex items-center gap-1.5 ${
              m.owner_kind === "system"
                ? "text-blue-700 dark:text-blue-300"
                : m.owner_kind === "user"
                ? "text-emerald-700 dark:text-emerald-300"
                : "text-amber-700 dark:text-amber-300"
            }`}>
              <ShieldAlert className="h-3.5 w-3.5" /> {m.owner_title}
            </div>
            <p className="text-sm mt-1 leading-relaxed">{m.owner_message}</p>
          </section>
        ) : null}

        {String(blocker.code ?? "").toLowerCase().includes("unmatched_sku") ? (
          <UnmatchedSkuGuide blocker={blocker} />
        ) : null}

        {/* 3. Сделайте по шагам */}
        {m.how_to_fix.length > 0 ? (
          <section className="rounded-md border bg-background p-3">
            <div className="text-[11px] uppercase tracking-wide text-muted-foreground font-medium flex items-center gap-1.5">
              <ListChecks className="h-3.5 w-3.5" /> 3. Исправьте по шагам
            </div>
            <ol className="mt-2 space-y-1.5 text-sm">
              {m.how_to_fix.map((step, i) => (
                <li key={i} className="flex gap-2">
                  <span className="shrink-0 inline-flex h-5 w-5 items-center justify-center rounded-full bg-primary/15 text-primary text-[11px] font-semibold">
                    {i + 1}
                  </span>
                  <span className="leading-relaxed">{step}</span>
                </li>
              ))}
            </ol>
          </section>
        ) : null}

        {/* 4. Как понять, что готово */}
        {m.success_check.length > 0 ? (
          <section className="rounded-md border border-emerald-500/30 bg-emerald-500/5 p-3">
            <div className="text-[11px] uppercase tracking-wide text-emerald-700 dark:text-emerald-300 font-semibold flex items-center gap-1.5">
              <CheckCircle2 className="h-3.5 w-3.5" /> Как понять, что всё готово
            </div>
            <ul className="mt-1.5 space-y-1 text-sm">
              {m.success_check.map((s, i) => (
                <li key={i} className="flex gap-2">
                  <CheckCircle2 className="h-3.5 w-3.5 mt-0.5 text-emerald-600 shrink-0" />
                  <span>{s}</span>
                </li>
              ))}
            </ul>
          </section>
        ) : null}

        {/* 5. Когда можно подождать */}
        {m.wait_or_fix_hint ? (
          <section className="rounded-md border border-amber-500/30 bg-amber-500/5 p-3">
            <div className="text-[11px] uppercase tracking-wide text-amber-700 dark:text-amber-300 font-semibold flex items-center gap-1.5">
              <Hourglass className="h-3.5 w-3.5" /> Когда можно просто подождать
            </div>
            <p className="text-sm mt-1 leading-relaxed">{m.wait_or_fix_hint}</p>
          </section>
        ) : null}

        <ActionButtonsGuide
          meta={m}
          workbenchLabel={workbenchLabel}
          hasWorkbench={Boolean(issue && onOpenWorkbench)}
        />

        {/* Action buttons */}
        <div className="flex flex-wrap gap-2 pt-1">
          {issue && onOpenWorkbench && (blocker as any).can_user_fix_inside_platform !== false ? (
            <Button size="sm" variant="outline" onClick={() => onOpenWorkbench(issue, blocker)}>
              <Wrench className="h-3.5 w-3.5 mr-1.5" />
              {workbenchLabel}
            </Button>
          ) : null}
          <Button asChild size="sm" variant="default">
            <Link {...(linkPropsForPath((blocker as any).target_href ?? m.next_screen_path) as any)}>
              {(blocker as any).primary_action_label ?? m.next_screen_label} <ArrowRight className="h-3.5 w-3.5 ml-1.5" />
            </Link>
          </Button>


        </div>

        {/* Technical footer (collapsed for support/admin, hidden from the normal owner flow) */}
        {blocker.exact_next_endpoint || (blocker.related_endpoints?.length ?? 0) > 0 ? (
          <details className="pt-2 border-t text-[11px] text-muted-foreground">
            <summary className="cursor-pointer select-none">Детали для поддержки</summary>
            <div className="mt-1 font-mono text-[10px]">
              {blocker.exact_next_endpoint ?? blocker.related_endpoints?.[0]}
            </div>
          </details>
        ) : null}
      </CardContent>
    </Card>
    <EvidenceDrawer
      open={evidenceOpen}
      onOpenChange={setEvidenceOpen}
      ledger={ledger}
      title={blocker.title}
    />
    </>
  );
}

function SystemStatusCard({
  blocker,
  index,
  issue,
  onOpenWorkbench,
}: {
  blocker: MDataBlocker;
  index: number;
  issue?: DataQualityIssue | null;
  onOpenWorkbench?: (issue: DataQualityIssue, blocker: MDataBlocker) => void;
}) {
  const m = metaFor(blocker);
  const label =
    m.owner_kind === "admin" ? "Админ"
    : m.owner_kind === "aggregate" ? "Сводный блокер"
    : "Система";
  return (
    <Card className="border-dashed bg-muted/20">
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between gap-3 flex-wrap">
          <div className="space-y-1.5 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <Badge variant="outline" className="text-[10px] font-mono">#{index + 1}</Badge>
              <Badge variant="secondary" className="text-[10px]">{label}</Badge>
              <Badge variant="outline" className="text-[10px]" title={`Код: ${blocker.code}`}>
                {problemCodeLabel(blocker.code)}
              </Badge>
            </div>
            <CardTitle className="text-base leading-snug">{blocker.title}</CardTitle>
            <CardDescription>{m.simple_reason}</CardDescription>
          </div>
          <div className="flex flex-wrap gap-2">
            {issue && onOpenWorkbench ? (
              <Button size="sm" variant="outline" onClick={() => onOpenWorkbench(issue, blocker)}>
                <Wrench className="h-3.5 w-3.5 mr-1.5" />
                Проверить статус
              </Button>
            ) : null}
            <Button asChild size="sm" variant="outline">
              <Link {...(linkPropsForPath(m.next_screen_path) as any)}>
                {m.next_screen_label} <ArrowRight className="h-3.5 w-3.5 ml-1.5" />
              </Link>
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {m.owner_message ? (
          <div className="rounded-md border bg-background/70 p-3 text-sm text-muted-foreground">
            {m.owner_message}
          </div>
        ) : null}
        {m.wait_or_fix_hint ? (
          <div className="rounded-md border border-amber-500/30 bg-amber-500/5 p-3 text-sm">
            {m.wait_or_fix_hint}
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}

function BlockerCalculation({ blocker }: { blocker: MDataBlocker }) {
  const inputs = Array.isArray(blocker.calculation_inputs) ? blocker.calculation_inputs : [];
  const endpoints = Array.isArray(blocker.source_endpoints) && blocker.source_endpoints.length > 0
    ? blocker.source_endpoints
    : [blocker.exact_next_endpoint, ...(blocker.related_endpoints ?? [])].filter(Boolean);
  if (!blocker.calculation_title && !blocker.calculation_formula && inputs.length === 0 && endpoints.length === 0) {
    return null;
  }
  return (
    <section className="rounded-md border bg-muted/25 p-3">
      <div className="text-[11px] uppercase tracking-wide text-muted-foreground font-medium flex items-center gap-1.5">
        <Info className="h-3.5 w-3.5" /> Откуда взялось и как посчитано
      </div>
      {blocker.calculation_title ? (
        <p className="text-sm mt-1 font-medium leading-relaxed">{blocker.calculation_title}</p>
      ) : null}
      {blocker.calculation_formula ? (
        <div className="mt-2 rounded border bg-background/70 px-2.5 py-2 text-[11px] text-muted-foreground font-mono break-words">
          {blocker.calculation_formula}
        </div>
      ) : null}
      {inputs.length > 0 ? (
        <div className="mt-2 grid gap-2 sm:grid-cols-2">
          {inputs.map((row, i) => (
            <div key={i} className="rounded-md border bg-background/60 px-2.5 py-2">
              <div className="text-[11px] text-muted-foreground">{row.label ?? "Показатель"}</div>
              <div className="font-semibold text-sm tabular-nums">{formatCalculationValue(row.value, row.unit)}</div>
              {row.source ? <div className="text-[10px] text-muted-foreground mt-0.5 break-words">{row.source}</div> : null}
            </div>
          ))}
        </div>
      ) : null}
      {endpoints.length > 0 ? (
        <details className="mt-2 text-[11px] text-muted-foreground">
          <summary className="cursor-pointer select-none">Технические источники для поддержки</summary>
          <div className="mt-1 space-y-1">
            {endpoints.slice(0, 6).map((endpoint, i) => (
              <div key={i} className="font-mono text-[10px] rounded bg-background/80 px-2 py-1 break-words">{endpoint}</div>
            ))}
          </div>
        </details>
      ) : null}
    </section>
  );
}

function formatCalculationValue(value: unknown, unit?: string) {
  if (typeof value === "number" && Number.isFinite(value)) {
    if (unit === "RUB") return formatMoney(value);
    return `${formatNumber(value)}${unit ? ` ${unit}` : ""}`;
  }
  if (value == null || value === "") return "—";
  return `${String(value)}${unit ? ` ${unit}` : ""}`;
}

// ─── Main page ───────────────────────────────────────────────────────────
function DataFixPage() {
  const { activeId } = useAccounts();
  const { from: dateFrom, to: dateTo } = useDateRange();
  const qc = useQueryClient();
  const routeSearch = Route.useSearch();
  const { code: focusCode } = routeSearch;
  const isMobile = useIsMobile();


  const blockersQ = useQuery({
    queryKey: ["money-data-blockers", activeId, dateFrom, dateTo],
    enabled: !!activeId,
    queryFn: () => fetchDataBlockers({ accountId: activeId!, dateFrom, dateTo }) as Promise<MDataBlockersResponse>,
  });

  const healthQ = useQuery({
    queryKey: ["dashboard-data-health", activeId, dateFrom, dateTo],
    enabled: !!activeId,
    queryFn: () => api<DashboardDataHealth>(API_ENDPOINTS.dashboard.dataHealth, {
      query: buildBizQuery({ accountId: activeId, dateFrom, dateTo }),
    }),
    retry: false,
  });

  const dqSummaryQ = useQuery<DataQualityIssueSummaryResponse | null>({
    queryKey: ["dq-issues-summary", activeId, dateFrom, dateTo],
    enabled: !!activeId,
    staleTime: 60_000,
    retry: false,
    queryFn: async ({ signal }) => {
      try {
        return await api<DataQualityIssueSummaryResponse>(API_ENDPOINTS.dq.summary, {
          query: buildBizQuery({ accountId: activeId, dateFrom, dateTo }),
          signal,
        });
      } catch (e: any) {
        if (e?.status === 404 || e?.status === 501) return null;
        throw e;
      }
    },
  });

  const dqIssuesQ = useQuery<DataQualityIssuesPage | null>({
    queryKey: ["dq-issues-for-data-fix", activeId],
    enabled: !!activeId,
    staleTime: 30_000,
    retry: false,
    queryFn: async ({ signal }) => {
      try {
        return await api<DataQualityIssuesPage>(API_ENDPOINTS.dq.issues, {
          query: { account_id: activeId!, only_open: true, limit: 200 },
          signal,
        });
      } catch (e: any) {
        if (e?.status === 404 || e?.status === 501) return null;
        throw e;
      }
    },
  });

  const [workbenchSelection, setWorkbenchSelection] = useState<{
    issue: DataQualityIssue;
    blocker: MDataBlocker;
  } | null>(null);

  const data = blockersQ.data;
  const blockers = useMemo<MDataBlocker[]>(
    () => (Array.isArray(data?.blockers) ? data!.blockers : []),
    [data],
  );
  const warnings = useMemo<MDataBlocker[]>(
    () => (Array.isArray(data?.warnings) ? data.warnings : []),
    [data],
  );
  const userBlockers = useMemo<MDataBlocker[]>(
    () => blockers.filter((item) => !isSystemHandledBlocker(item)),
    [blockers],
  );
  const systemBlockers = useMemo<MDataBlocker[]>(
    () => blockers.filter(isSystemHandledBlocker),
    [blockers],
  );

  const sortedBlockers = useMemo(() => {
    const order: Record<string, number> = { critical: 0, high: 1, medium: 2, low: 3 };
    return [...userBlockers].sort((a, b) => (order[a.priority] ?? 9) - (order[b.priority] ?? 9));
  }, [userBlockers]);

  const blockersCount = userBlockers.length;
  const systemBlockersCount = systemBlockers.length;
  const warningsCount = data?.warnings_count ?? warnings.length;
  const issueByCode = useMemo(() => {
    const map = new Map<string, DataQualityIssue>();
    for (const issue of dqIssuesQ.data?.items ?? []) {
      const code = String(issue.code ?? "").toLowerCase();
      if (!code || map.has(code)) continue;
      map.set(code, issue);
    }
    return map;
  }, [dqIssuesQ.data]);

  // DQ summary: "X типа блокеров / Y проблем"
  const dq = dqSummaryQ.data;
  const dqTotalIssues: number =
    Number(dq?.financial_final_blockers_total ?? dq?.blocking_open_issues_total ?? dq?.open_issues_total ?? NaN);
  const dqBlockerTypes: number = (() => {
    const byGroup = dq?.by_group ?? dq?.by_issue_type ?? null;
    if (byGroup && typeof byGroup === "object") return Object.keys(byGroup).length;
    return Number.NaN;
  })();
  const financialFinalBlockers =
    Number.isFinite(dqTotalIssues)
      ? dqTotalIssues
      : (data?.data_quality_summary?.financial_final_blockers_total ?? blockers.length);
  const canGenerate = data?.can_generate_business_actions ?? true;
  const overallState = String(data?.overall_state ?? "—");
  const overallMessage = data?.overall_message;

  const heroTone: "danger" | "warning" | "success" =
    overallState === "data_blocked" || blockersCount > 0 ? "danger" :
    overallState === "accepted_with_warnings" || warningsCount > 0 || systemBlockersCount > 0 ? "warning" :
    "success";

  const handleRefresh = () => {
    qc.invalidateQueries({ queryKey: ["money-data-blockers"] });
    qc.invalidateQueries({ queryKey: ["dashboard-data-health"] });
    qc.invalidateQueries({ queryKey: ["dq-issues-summary"] });
    qc.invalidateQueries({ queryKey: ["dq-issues-for-data-fix"] });
  };

  // Deep-link: scroll to ?code=... blocker once data lands.
  useEffect(() => {
    if (!focusCode || sortedBlockers.length === 0) return;
    const el = document.getElementById(`blocker-${focusCode}`);
    if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [focusCode, sortedBlockers.length]);

  const [category, setCategory] = useState<string>("all");
  const [search, setSearch] = useState<string>("");

  const matchesCategoryFn = (b: MDataBlocker, cat: string): boolean => {
    if (cat === "all") return true;
    const code = String(b.code ?? "").toLowerCase();
    const ownerKind = metaFor(b).owner_kind;
    switch (cat) {
      case "can_fix_here":
        return ownerKind !== "system" && ownerKind !== "admin" && ownerKind !== "aggregate";
      case "missing_data":
        return /missing|no_|not_set|empty|coverage_below/.test(code) || b.priority === "critical";
      case "cost":
        return /cost/.test(code);
      case "sku_map":
        return /sku|barcode|vendor|chrt|unmatched|mapping/.test(code) && !/cost/.test(code);
      case "expense":
        return /expense|ad_spend|ad_/.test(code);
      case "finance":
        return /finance|reconciliation|sale_without|without_sale/.test(code);
      case "system":
        return isSystemHandledBlocker(b) || ownerKind === "system" || ownerKind === "admin";
      case "resolved":
      case "pending_recheck":
        // Backend only returns open blockers; these buckets are naturally empty.
        return false;
      default:
        return true;
    }
  };

  // Counts for the 6 required summary cards (over all blockers, not filtered).
  const summaryCounts = useMemo(() => {
    const all = [...blockers];
    return {
      profitBlockers: sortedBlockers.length,
      missingCost: all.filter((b) => matchesCategoryFn(b, "cost")).length,
      needsMapping: all.filter((b) => matchesCategoryFn(b, "sku_map")).length,
      canFixHere: all.filter(
        (b) => matchesCategoryFn(b, "can_fix_here") && !isSystemHandledBlocker(b),
      ).length,
      needsSync: all.filter(
        (b) =>
          /sync|scheduler|missed_load|latest_stocks|sale_without|without_sale/.test(
            String(b.code ?? "").toLowerCase(),
          ),
      ).length,
      systemChecks: systemBlockers.length,
    };
  }, [blockers, sortedBlockers.length, systemBlockers.length]);

  const filteredBlockers = useMemo(() => {
    const term = search.trim().toLowerCase();
    return sortedBlockers.filter((b) => {
      if (!matchesCategoryFn(b, category)) return false;
      if (!term) return true;
      return [b.title, b.business_impact, b.code].some((v) =>
        String(v ?? "").toLowerCase().includes(term),
      );
    });
  }, [sortedBlockers, category, search]);


  return (
    <PageShell>
      <PageHeader
        title="Качество данных"
        description="Блокеры и ошибки данных, которые мешают точным расчётам прибыли, маржи, остатков и рисков."
        actions={
          <div className="flex flex-wrap gap-2">
            <Button asChild variant="outline" size="sm">
              <Link to="/results">Открыть результаты</Link>
            </Button>
            <Button asChild variant="outline" size="sm">
              <Link to="/action-center">Что требует внимания</Link>
            </Button>
            <Button variant="outline" size="sm" onClick={handleRefresh} disabled={blockersQ.isFetching}>
              <RefreshCw className={`h-4 w-4 mr-1.5 ${blockersQ.isFetching ? "animate-spin" : ""}`} />
              Обновить
            </Button>
          </div>
        }
      />

      <div className="space-y-6">
      <ActionCenterReturnLink
        problem_instance_id={routeSearch.problem_instance_id}
        nm_id={routeSearch.nm_id}
        code={routeSearch.code}
      />
      <DataDependencyNotice accountId={activeId} domains={["sales", "orders", "finance", "stocks", "ads", "prices", "product_cards"]} />
      {/* Two separated statuses: operational vs final profit */}
      {activeId && (
        <OperationalFinalBanner
          operational_trusted={(healthQ.data as any)?.operational_trusted ?? (healthQ.data as any)?.business_trusted ?? null}
          financial_final={(healthQ.data as any)?.financial_final ?? null}
          final_blockers_total={financialFinalBlockers}
          showDataFixLink={false}
        />
      )}

      {/* Hero summary banner */}
      {blockersQ.isLoading ? (
        <Skeleton className="h-28 w-full" />
      ) : blockersQ.isError ? (
        <Alert variant="destructive">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>Не удалось загрузить блокеры</AlertTitle>
          <AlertDescription>Попробуйте обновить страницу.</AlertDescription>
        </Alert>
      ) : heroTone === "success" ? (
        <Alert className="border-emerald-500/40 bg-emerald-500/5">
          <CheckCircle2 className="h-5 w-5 text-emerald-600" />
          <AlertTitle className="text-emerald-800 dark:text-emerald-200">
            Сейчас критичных проблем не найдено
          </AlertTitle>
          <AlertDescription>
            Можно переходить к бизнес-действиям. Финальная прибыль доверенная.
          </AlertDescription>
        </Alert>
      ) : (
        <Alert variant={heroTone === "danger" ? "destructive" : "default"}
               className={heroTone === "warning" ? "border-warning/40 bg-warning/5" : ""}>
          {blockersCount > 0 ? <ShieldAlert className="h-5 w-5" /> : <RefreshCw className="h-5 w-5" />}
          <AlertTitle>
            {blockersCount > 0
              ? "Финальную прибыль пока считать рано"
              : systemBlockersCount > 0
              ? "Идёт автоматическая сверка данных"
              : "Можно работать, но финальная прибыль — предварительная"}
          </AlertTitle>
          <AlertDescription className="space-y-1">
            <div>
              {blockersCount > 0
                ? `Есть ${blockersCount} проблема, которую можно закрыть вручную. Откройте список ниже и выполните шаги.`
                : systemBlockersCount > 0
                ? "Ручных действий от пользователя нет. Система сама перепроверяет финансовые данные WB и синхронизацию; если расхождение останется, это уйдёт в админскую проверку."
                : (overallMessage ?? `Есть ${warningsCount} предупреждений. Их можно закрыть, когда будет время.`)}
            </div>
            <div className="text-xs">
              {systemBlockersCount > 0 && blockersCount === 0
                ? "Подгонять суммы вручную нельзя: это внутреннее расхождение импорта/сверки."
                : canGenerate
                ? "Бизнес-действия разрешены — но цифры могут уточниться после починки."
                : "Бизнес-рекомендации заблокированы, пока не закрыты критичные блокеры."}
            </div>
          </AlertDescription>
        </Alert>
      )}

      {/* 6 summary cards — click to filter */}
      <div className="grid grid-cols-2 lg:grid-cols-3 gap-3">
        <SummaryCard
          label="Блокеры прибыли"
          value={summaryCounts.profitBlockers}
          hint="Мешают расчёту прибыли и маржи"
          tone={summaryCounts.profitBlockers > 0 ? "danger" : "success"}
          active={category === "all"}
          onClick={() => setCategory("all")}
        />
        <SummaryCard
          label="Не хватает себестоимости"
          value={summaryCounts.missingCost}
          hint="Без cost не считаются прибыль и маржа"
          tone={summaryCounts.missingCost > 0 ? "danger" : "success"}
          active={category === "cost"}
          onClick={() => setCategory("cost")}
        />
        <SummaryCard
          label="Требует сопоставления"
          value={summaryCounts.needsMapping}
          hint="SKU / артикул / баркод не привязаны"
          tone={summaryCounts.needsMapping > 0 ? "warning" : "success"}
          active={category === "sku_map"}
          onClick={() => setCategory("sku_map")}
        />
        <SummaryCard
          label="Можно исправить здесь"
          value={summaryCounts.canFixHere}
          hint="Внутри платформы, без админа"
          tone={summaryCounts.canFixHere > 0 ? "warning" : "success"}
          active={category === "can_fix_here"}
          onClick={() => setCategory("can_fix_here")}
        />
        <SummaryCard
          label="Требует синхронизации"
          value={summaryCounts.needsSync}
          hint="Ждём загрузку или отчёт WB"
          tone={summaryCounts.needsSync > 0 ? "warning" : "success"}
          active={false}
          onClick={() => setCategory("all")}
          disabled
        />
        <SummaryCard
          label="Системные проверки"
          value={summaryCounts.systemChecks}
          hint="Правит система / администратор"
          tone={summaryCounts.systemChecks > 0 ? "warning" : "success"}
          active={category === "system"}
          onClick={() => setCategory("system")}
        />
      </div>


      {/* Optional: small trust line from /dashboard/data-health */}
      {healthQ.data ? (
        <div className="text-xs text-muted-foreground flex flex-wrap gap-x-4 gap-y-1">
          <span>Статус доверия: <b className="text-foreground">{(healthQ.data as any).trust_state ? humanizeBusinessStatus((healthQ.data as any).trust_state).label : "—"}</b></span>
          <span>Финальная сверка: <b className="text-foreground">{(healthQ.data as any).financial_final ? "готова" : "не готова"}</b></span>
          {(healthQ.data as any).open_issues_total != null ? (
            <span>Открытых проблем: <b className="text-foreground">{(healthQ.data as any).open_issues_total}</b></span>
          ) : null}
          <Link to="/dashboard" className="text-primary hover:underline ml-auto">Открыть проверку данных →</Link>
        </div>
      ) : null}

      {/* Manual blockers */}
      <section className="space-y-3">
        <div className="flex items-center gap-2">
          <Wrench className="h-4 w-4 text-destructive" />
          <h2 className="text-lg font-semibold">Ручные блокеры</h2>
          <Badge variant="outline">{filteredBlockers.length} из {sortedBlockers.length}</Badge>
        </div>
        <p className="text-sm text-muted-foreground">
          Здесь только то, что пользователь реально может закрыть: себестоимость, SKU, категории расходов или другие бизнес-данные.
        </p>

        {/* Category chips — per spec */}
        <div className="flex flex-wrap gap-2">
          {[
            { id: "all", label: "Все" },
            { id: "can_fix_here", label: "Можно исправить здесь" },
            { id: "missing_data", label: "Не хватает данных" },
            { id: "cost", label: "Себестоимость" },
            { id: "sku_map", label: "Сопоставление SKU" },
            { id: "expense", label: "Расходы" },
            { id: "finance", label: "Финансы" },
            { id: "system", label: "Системные" },
            { id: "resolved", label: "Уже исправлено" },
            { id: "pending_recheck", label: "Ждёт перепроверки" },
          ].map((c) => (
            <Button
              key={c.id}
              type="button"
              size="sm"
              variant={category === c.id ? "default" : "outline"}
              onClick={() => setCategory(c.id)}
            >
              {c.label}
            </Button>
          ))}
        </div>


        {/* Search */}
        <input
          type="search"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Найти по названию, коду или последствиям…"
          className="w-full rounded-md border bg-background px-3 py-2 text-sm"
        />

        {blockersQ.isLoading ? (
          <div className="space-y-3">
            <Skeleton className="h-64 w-full" />
            <Skeleton className="h-64 w-full" />
          </div>
        ) : blockersQ.isError ? (
          <EmptyState variant="error" onRetry={handleRefresh} />
        ) : sortedBlockers.length === 0 ? (
          <EmptyState
            variant="no_problems"
            title="Проблем не найдено"
            hint={systemBlockersCount > 0
              ? "Есть только системная сверка. Пользователю ничего исправлять не нужно."
              : "По текущим фильтрам активных проблем нет."}
          />
        ) : filteredBlockers.length === 0 ? (
          <EmptyState
            variant="no_data"
            title="Нет данных по фильтрам"
            hint="Измените категорию или очистите поиск."
            action={
              <Button size="sm" variant="outline" onClick={() => { setCategory("all"); setSearch(""); }}>
                Сбросить фильтры
              </Button>
            }
          />
        ) : isMobile ? (
          <div className="space-y-2.5">
            {filteredBlockers.map((b, i) => {
              const m = metaFor(b);
              return (
                <DataFixMobileCard
                  key={`m-${b.code}-${i}`}
                  blocker={b}
                  issue={issueForBlocker(b, issueByCode)}
                  onOpenWorkbench={(issue, blocker) =>
                    setWorkbenchSelection({ issue, blocker })
                  }
                  ownerKind={m.owner_kind}
                  nextScreenPath={m.next_screen_path}
                  nextScreenLabel={m.next_screen_label}
                />
              );
            })}
          </div>
        ) : (
          filteredBlockers.map((b, i) => (
            <BlockerCard
              key={`${b.code}-${i}`}
              blocker={b}
              index={i}
              highlight={focusCode === b.code}
              issue={issueForBlocker(b, issueByCode)}
              onOpenWorkbench={(issue, blocker) => setWorkbenchSelection({ issue, blocker })}
            />
          ))
        )}

      </section>


      {systemBlockers.length > 0 ? (
        <section className="space-y-3">
          <div className="flex items-center gap-2">
            <RefreshCw className="h-4 w-4 text-warning" />
            <h2 className="text-lg font-semibold">Системные проверки</h2>
            <Badge variant="outline">{systemBlockers.length}</Badge>
          </div>
          <Alert className="border-warning/40 bg-warning/5">
            <Info className="h-4 w-4" />
            <AlertTitle>Здесь не нужно вручную менять суммы</AlertTitle>
            <AlertDescription>
              Эти проблемы закрываются через sync, отчет WB, формулу или админскую проверку. Пользователь только смотрит статус, запускает повторную проверку или передает в разбор.
            </AlertDescription>
          </Alert>
          {systemBlockers.map((b, i) => (
            <SystemStatusCard
              key={`system-${b.code}-${i}`}
              blocker={b}
              index={i}
              issue={issueForBlocker(b, issueByCode)}
              onOpenWorkbench={(issue, blocker) => setWorkbenchSelection({ issue, blocker })}
            />
          ))}
        </section>
      ) : null}

      {/* Warnings */}
      {warnings.length > 0 ? (
        <section className="space-y-3">
          <div className="flex items-center gap-2">
            <AlertTriangle className="h-4 w-4 text-warning" />
            <h2 className="text-lg font-semibold">Предупреждения</h2>
            <Badge variant="outline">{warnings.length}</Badge>
          </div>
          {warnings.map((w, i) => (
            <BlockerCard
              key={`w-${w.code}-${i}`}
              blocker={w}
              index={i}
              issue={issueForBlocker(w, issueByCode)}
              onOpenWorkbench={(issue, blocker) => setWorkbenchSelection({ issue, blocker })}
            />
          ))}
        </section>
      ) : null}

      <div className="text-[11px] text-muted-foreground text-center pt-2">
        Данные обновлены из проверки качества
        {data?.meta?.generated_at ? ` · обновлено ${formatGeneratedAt(data.meta.generated_at)}` : ""}
      </div>
      </div>
      <DataFixWorkbench
        open={!!workbenchSelection}
        issueId={workbenchSelection?.issue.id ?? null}
        fallbackBlocker={workbenchSelection?.blocker ?? null}
        onOpenChange={(nextOpen) => {
          if (!nextOpen) setWorkbenchSelection(null);
        }}
        onChanged={handleRefresh}
        onLocalActionSaved={(payload) =>
          appendActionCenterProblemHistory({
            accountId: activeId,
            problemInstanceId: routeSearch.problem_instance_id,
            comment: `Исправление данных: ${payload.action_type}`,
          })
        }
      />
    </PageShell>
  );
}
