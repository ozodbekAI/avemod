// @ts-nocheck
import { Link, useNavigate } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import {
  Activity,
  AlertCircle,
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  BarChart3,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  ClipboardCheck,
  ClipboardList,
  Clock3,
  Database,
  ExternalLink,
  Eye,
  FileText,
  Gauge,
  ListChecks,
  Loader2,
  Lock,
  MessageSquare,
  PackageSearch,
  Play,
  Plus,
  RefreshCw,
  RotateCw,
  Search,
  ShieldCheck,
  SkipForward,
  SlidersHorizontal,
  Sparkles,
  TrendingDown,
  TrendingUp,
  UserRound,
  X,
} from "lucide-react";
import { toast } from "sonner";

import { EndpointError } from "@/components/EndpointError";
import {
  fetchDataSyncStatus,
  type DataSyncStatusResponse,
} from "@/components/data-health/DataCoveragePanel";
import { NoAccountSelected } from "@/components/portal/NoAccountSelected";
import { PageHeader, PageShell } from "@/components/PageShell";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { Progress } from "@/components/ui/progress";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { useAccounts } from "@/lib/account-context";
import { useAuth } from "@/lib/auth-context";
import { useDateRange } from "@/lib/date-range-context";
import { api } from "@/lib/api";
import { API_ENDPOINTS } from "@/lib/endpoints";
import { formatMoney, formatMoneyCompact, formatNumber } from "@/lib/format";
import { proxyWbImageUrl as resolveWbImageUrl } from "@/lib/wb-images";
import {
  adaptActionCenterItem,
  dataFreshnessBlocksAction,
  dataFreshnessBlockingLabel,
  type ActionCenterItem,
  type ActionCenterSolveMapStep,
} from "@/lib/action-center-contract";
import {
  ACTION_CENTER_DEFAULT_FILTERS,
  ACTION_CENTER_SAVED_VIEWS,
  ACTION_CENTER_SORT_OPTIONS,
  actionCenterMatchesFilters,
  actionCenterSearchFromState,
  actionCenterShouldHideBetaSignal,
  sortActionCenterItems,
  type ActionCenterFilterState,
} from "@/lib/action-center-filters";
import {
  IMPACT_TYPE_FILTERS,
  PRIORITIES,
  SEVERITY_FILTERS,
  SOURCE_MODULES,
  STATUSES,
  TRUST_STATE_FILTERS,
  priorityLabel,
  sourceModuleLabel,
} from "@/lib/action-center-labels";
import {
  assigneeLabel,
  dynamicProblemInstanceId,
  formatDeadline,
  isContentQualityOpportunityAction,
  isBetaAction,
  isClosedAction,
  isDataBlockerAction,
  isDynamicProblemAction,
  isOverdueAction,
  isSystemHandledAction,
  isTestOnlyProblem,
  isUrgentAction,
  roleRank,
  userAccountRole,
  waitsForRecheckAction,
} from "@/lib/action-center-status";
import {
  guidedFixHref,
  guidedFixLabel,
  primaryActionForItem,
  primaryDisabledActionForItem,
  resultsHrefForAction,
} from "@/lib/action-center-actions";
import { extractActions, normalizeText } from "@/lib/action-center-utils";
import {
  problemCodeLabel,
  problemImpactLabel,
  problemResultStatusLabel,
  problemStatusLabel,
  problemTrustLabel,
} from "@/lib/problem-ux-copy";
import {
  createManualPortalAction,
  fetchActionCenterCapabilities,
  fixCardQualityIssue,
  fetchPortalProducts,
  previewCardQualityIssueApply,
  recheckProblemInstance,
  updateManualTaskItem,
  type PortalActionCenterCapabilityDomain,
  type PortalAssignableUser,
  type PortalProductRow,
} from "@/lib/portal";
import {
  fetchCostsMissing,
  saveInlineCosts,
  type CostsMissingItem,
} from "@/lib/money-endpoints";
import { useActionCenterData } from "@/hooks/action-center/useActionCenterData";
import {
  useActionCenterFilters,
  type ActionCenterSearch,
} from "@/hooks/action-center/useActionCenterFilters";
import { useActionCenterMutations } from "@/hooks/action-center/useActionCenterMutations";

const MAX_QUEUE_ITEMS = 80;

const CLOSED_STATUSES = new Set([
  "done",
  "resolved",
  "closed",
  "ignored",
  "dismissed",
  "rejected",
]);

const COMPLETED_TASK_STATUSES = new Set(["done", "resolved", "closed"]);

const DEACTIVATED_TASK_STATUSES = new Set([
  "postponed",
  "ignored",
  "dismissed",
  "rejected",
]);

const ACTIVE_TASK_QUERY_STATUS =
  "new,acknowledged,in_progress,postponed,blocked,reopened";
const COMPLETED_TASK_QUERY_STATUS = "done,resolved";
const DEACTIVATED_TASK_QUERY_STATUS = "ignored,dismissed";

type TaskBoardMode = "active" | "completed" | "deactivated";

type ManualTaskProgressItem = {
  id?: number | string | null;
  item_key?: string | null;
  status?: "pending" | "done" | "skipped" | string | null;
  nm_id?: number | null;
  sku_id?: number | null;
  vendor_code?: string | null;
  title?: string | null;
  photo_url?: string | null;
  last_comment?: string | null;
};

type ManualTaskProgress = {
  total: number;
  done: number;
  skipped: number;
  pending: number;
  percent: number;
  items: ManualTaskProgressItem[];
};

const EMPTY_MANUAL_TASK_PROGRESS: ManualTaskProgress = {
  total: 0,
  done: 0,
  skipped: 0,
  pending: 0,
  percent: 0,
  items: [],
};

const STATUS_TONE: Record<string, string> = {
  new: "border-sky-500/30 bg-sky-500/10 text-sky-700 dark:text-sky-300",
  in_progress:
    "border-amber-500/35 bg-amber-500/10 text-amber-800 dark:text-amber-300",
  done: "border-emerald-500/35 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
  resolved:
    "border-emerald-500/35 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
  ignored: "border-muted bg-muted text-muted-foreground",
  blocked: "border-red-500/35 bg-red-500/10 text-red-700 dark:text-red-300",
  postponed:
    "border-violet-500/35 bg-violet-500/10 text-violet-700 dark:text-violet-300",
};

const PRIORITY_TONE: Record<string, string> = {
  P0: "border-red-500/40 bg-red-500/10 text-red-700 dark:text-red-300",
  P1: "border-orange-500/40 bg-orange-500/10 text-orange-700 dark:text-orange-300",
  P2: "border-sky-500/35 bg-sky-500/10 text-sky-700 dark:text-sky-300",
  P3: "border-border bg-muted text-muted-foreground",
  P4: "border-border bg-muted text-muted-foreground",
};

const ACTION_LABELS: Record<string, string> = {
  open_price_review: "Открыть проверку цены",
  review_price: "Проверить цену",
  pricing_review: "Проверить цену",
  open_data_fix: "Открыть исправление данных",
  data_fix: "Исправить данные",
  review_cost: "Заполнить себестоимость",
  upload_cost: "Загрузить себестоимость",
  map_sku: "Сопоставить SKU",
  classify_expense: "Разнести расход",
  open_ads_dashboard: "Открыть рекламу",
  review_ads: "Проверить рекламу",
  pause_ads: "Остановить рекламу",
  lower_ads: "Снизить рекламу",
  review_bids: "Проверить ставки",
  open_promo_planner: "Открыть промо",
  promo_planner: "Проверить промо",
  review_promo: "Проверить промо",
  reduce_promo: "Снизить промо",
  open_supply_planner: "Открыть поставки",
  plan_supply: "Запланировать поставку",
  run_checker: "Проверить карточку",
  check_card_quality: "Проверить карточку",
  review_content: "Проверить карточку",
  recheck: "Запустить перепроверку",
  open_product: "Открыть товар",
  open_results: "Открыть результаты",
  manual_review: "Выполнить задачу",
  manual_title_update: "Изменить название",
  manual_content_update: "Улучшить карточку",
  manual_photo_update: "Проверить фото",
  manual_price_check: "Проверить цену",
  manual_other: "Выполнить вручную",
};

// Reputation remains a beta action source:
// { value: "reputation", label: "Репутация" }
// reputation: () => "/reputation"
// external_reputation_recommendation: подготовьте черновик, проверьте canUpdateReasonLabel и публикуйте только после ручного подтверждения.
// Checker evidence contract: EvidenceDrawer, EvidenceButton, Перепроверить,
// checker-product-quality, ActionCenterHistoryTimeline, source_sync_state,
// can_update_reason, updateActionBySource.

const MANUAL_TASK_PRESETS = [
  {
    key: "title_update",
    label: "Название",
    hint: "Смысл, поиск WB, понятное название",
    title: "Изменить название товара",
    description:
      "Проверьте текущее название, подготовьте понятное название и обновите карточку.",
    icon: <FileText className="h-4 w-4" />,
    tone: "border-sky-500/30 bg-sky-500/5 text-sky-900 dark:text-sky-100",
  },
  {
    key: "content_update",
    label: "Карточка",
    hint: "Описание и характеристики",
    title: "Улучшить карточку товара",
    description:
      "Проверить описание, характеристики и визуальную подачу товара.",
    icon: <Sparkles className="h-4 w-4" />,
    tone: "border-emerald-500/30 bg-emerald-500/5 text-emerald-900 dark:text-emerald-100",
  },
  {
    key: "photo_update",
    label: "Фото",
    hint: "Главное и доп. фото",
    title: "Проверить фото товара",
    description:
      "Проверить главное фото и дополнительные изображения, подготовить замену при необходимости.",
    icon: <Eye className="h-4 w-4" />,
    tone: "border-violet-500/30 bg-violet-500/5 text-violet-900 dark:text-violet-100",
  },
  {
    key: "price_check",
    label: "Цена",
    hint: "Цена, скидка, маржа",
    title: "Проверить цену товара",
    description: "Проверить цену, скидку и безопасную маржу перед изменениями.",
    icon: <Gauge className="h-4 w-4" />,
    tone: "border-amber-500/30 bg-amber-500/5 text-amber-900 dark:text-amber-100",
  },
  {
    key: "other",
    label: "Другое",
    hint: "Своя инструкция",
    title: "Ручная задача по товару",
    description: "",
    icon: <ListChecks className="h-4 w-4" />,
    tone: "border-border bg-muted/25 text-foreground",
  },
];

function norm(value: unknown): string {
  return normalizeText(value).replaceAll(" ", "_");
}

function hasCyrillicText(value: unknown): boolean {
  return /[А-Яа-яЁё]/.test(String(value ?? ""));
}

function isClosedStatus(value: unknown): boolean {
  return CLOSED_STATUSES.has(norm(value));
}

function taskBoardModeForItem(item: ActionCenterItem): TaskBoardMode {
  const status = norm(item.status);
  if (DEACTIVATED_TASK_STATUSES.has(status)) return "deactivated";
  if (COMPLETED_TASK_STATUSES.has(status) || isClosedAction(item)) {
    return "completed";
  }
  return "active";
}

function taskBoardModeTitle(mode: TaskBoardMode): string {
  if (mode === "completed") return "Выполненные";
  if (mode === "deactivated") return "Деактивированные";
  return "Активные";
}

function taskBoardModeHint(mode: TaskBoardMode): string {
  if (mode === "completed") {
    return "История закрытых задач. При ошибке можно вернуть задачу в активные.";
  }
  if (mode === "deactivated") {
    return "Отложенные и неактуальные задачи не мешают текущей очереди.";
  }
  return "Задачи, которые можно брать в работу и закрывать по очереди.";
}

function compactDate(value?: string | null): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleDateString("ru-RU", {
    day: "2-digit",
    month: "short",
  });
}

function compactDateTime(value?: string | null): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString("ru-RU", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatValue(value: unknown, unit?: string | null): string {
  if (value == null || value === "") return "—";
  if (typeof value === "number") {
    if (unit === "RUB" || unit === "₽") return formatMoney(value);
    if (unit === "%" || unit === "percent") return `${formatNumber(value)}%`;
    return formatNumber(value);
  }
  if (
    typeof value === "string" &&
    value.trim() &&
    !Number.isNaN(Number(value))
  ) {
    const numeric = Number(value);
    if (unit === "RUB" || unit === "₽") return formatMoney(numeric);
    if (unit === "%" || unit === "percent") return `${formatNumber(numeric)}%`;
    return formatNumber(numeric);
  }
  if (typeof value === "boolean") return value ? "да" : "нет";
  return String(value);
}

function humanMetricLabel(value: unknown): string {
  const key = norm(value);
  const labels: Record<string, string> = {
    unit_profit: "Прибыль на единицу",
    margin_pct: "Маржа",
    cost_price: "Себестоимость",
    price: "Цена",
    price_current: "Текущая цена",
    price_after_discount: "Цена после скидки",
    sales_30d: "Продажи за 30 дней",
    stock_qty: "Остаток",
    days_of_stock: "Запас в днях",
    avg_daily_sales_7d: "Средние продажи 7 дней",
    avg_daily_sales_14d: "Средние продажи 14 дней",
    ad_spend_7d: "Реклама за 7 дней",
    promo_spend_30d: "Промо за 30 дней",
    commission: "Комиссия",
    logistics_cost: "Логистика",
  };
  return labels[key] ?? String(value ?? "Факт").replaceAll("_", " ");
}

function formatFactValue(fact: any): string {
  const metric = norm(fact?.metric_code ?? fact?.label);
  const unit = fact?.unit;
  if (metric.includes("margin") || metric.endsWith("_pct") || unit === "%") {
    return formatValue(fact?.value, "%");
  }
  if (
    metric.includes("price") ||
    metric.includes("profit") ||
    metric.includes("cost") ||
    metric.includes("spend") ||
    metric.includes("revenue")
  ) {
    return formatValue(fact?.value, "₽");
  }
  return formatValue(fact?.value, unit);
}

function humanStatusLabel(value: unknown): string {
  const key = norm(value);
  const labels: Record<string, string> = {
    open: "Открыта",
    new: "Новая",
    acknowledged: "Принята",
    in_progress: "В работе",
    done: "Выполнена",
    resolved: "Решена",
    closed: "Закрыта",
    ignored: "Пропущена",
    dismissed: "Отклонена",
    rejected: "Отклонена",
    blocked: "Заблокирована",
    postponed: "Отложена",
    snoozed: "Отложена",
  };
  return labels[key] ?? problemStatusLabel(key);
}

function humanResultLabel(value: unknown): string {
  const key = norm(value);
  const labels: Record<string, string> = {
    pending_data: "Ждём данные",
    improved: "Улучшение есть",
    worse: "Стало хуже",
    neutral: "Без изменений",
    not_enough_data: "Не хватает данных",
  };
  return labels[key] ?? problemResultStatusLabel(key);
}

function humanActionLabel(value: unknown): string {
  const key = norm(value);
  const fallback = String(value ?? "")
    .replaceAll("_", " ")
    .trim();
  return ACTION_LABELS[key] ?? (fallback || "Открыть действие");
}

function savedViewLabel(value: unknown): string {
  const key = String(value ?? "all");
  return (
    ACTION_CENTER_SAVED_VIEWS.find((view) => view.value === key)?.label ??
    "Все задачи"
  );
}

function problemTitle(item: ActionCenterItem): string {
  if (norm(item.source_module) === "manual") return item.title;
  const codeLabel = problemCodeLabel(actionCode(item));
  return codeLabel && codeLabel !== "Проверка данных" ? codeLabel : item.title;
}

function objectLabel(item: ActionCenterItem): string {
  return (
    [item.nm_id ? `nm ${item.nm_id}` : null, item.vendor_code]
      .filter(Boolean)
      .join(" / ") || "Объект не указан"
  );
}

function itemProductTitle(item: ActionCenterItem): string {
  const payload = itemPayload(item);
  const raw =
    typeof item.raw === "object" && item.raw
      ? (item.raw as Record<string, unknown>)
      : {};
  return (
    firstString(
      item.product_title,
      item.product_name,
      item.subject_name,
      item.card_title,
      payload.product_title,
      payload.product_name,
      payload.subject_name,
      payload.card_title,
      payload.title,
      raw.product_title,
      raw.product_name,
      raw.subject_name,
      raw.card_title,
      item.vendor_code,
    ) ||
    objectLabel(item) ||
    problemTitle(item)
  );
}

function actionModeLabel(item: ActionCenterItem): string {
  const mode = actionExecutionMode(item);
  if (mode === "execute") return "Можно применить";
  if (mode === "inline") return "Исправить здесь";
  if (mode === "manual") return "Назначить";
  if (mode === "blocked") return "Заполнить данные";
  if (mode === "decision") return "Открыть действие";
  return "Проверить";
}

function firstString(...values: unknown[]): string | null {
  for (const value of values) {
    if (typeof value === "string" && value.trim()) return value.trim();
  }
  return null;
}

function firstArrayImage(value: unknown): string | null {
  if (!Array.isArray(value)) return null;
  for (const item of value) {
    if (typeof item === "string" && item.trim()) return item.trim();
    if (item && typeof item === "object") {
      const obj = item as Record<string, unknown>;
      const url = firstString(
        obj.c516x688,
        obj.big,
        obj.c246x328,
        obj.square,
        obj.url,
        obj.photo,
        obj.src,
        obj.tm,
        obj.thumbnail,
        obj.preview,
      );
      if (url) return url;
    }
  }
  return null;
}

function wbBasketHostNumber(vol: number): number {
  const ranges: Array<[number, number]> = [
    [143, 1],
    [287, 2],
    [431, 3],
    [719, 4],
    [1007, 5],
    [1061, 6],
    [1115, 7],
    [1169, 8],
    [1313, 9],
    [1601, 10],
    [1655, 11],
    [1919, 12],
    [2045, 13],
    [2189, 14],
    [2405, 15],
    [2621, 16],
    [2837, 17],
    [3053, 18],
    [3269, 19],
    [3485, 20],
    [3701, 21],
    [3917, 22],
    [4133, 23],
    [4349, 24],
    [4565, 25],
    [4877, 26],
    [5193, 27],
    [5509, 28],
    [5825, 29],
    [6141, 30],
  ];
  return ranges.find(([maxVol]) => vol <= maxVol)?.[1] ?? 30;
}

function wbBasketHost(vol: number): string {
  const basket = wbBasketHostNumber(vol);
  return `basket-${String(basket).padStart(2, "0")}.wbbasket.ru`;
}

function wbImageCandidates(nmId: string | number | null | undefined): string[] {
  const n = Number(nmId);
  if (!Number.isFinite(n) || n <= 0) return [];
  const vol = Math.floor(n / 100000);
  const part = Math.floor(n / 1000);
  const predictedHosts = [
    wbBasketHostNumber(vol),
    Math.ceil(vol / 280),
    Math.round(vol / 280),
    Math.ceil(vol / 275),
    Math.ceil(vol / 300),
  ]
    .filter((value) => Number.isFinite(value) && value >= 1 && value <= 80)
    .map((value) => Math.trunc(value));
  return [...new Set(predictedHosts)].map(
    (basket) =>
      `https://basket-${String(basket).padStart(2, "0")}.wbbasket.ru/vol${vol}/part${part}/${n}/images/c246x328/1.webp`,
  );
}

function proxyWbImageUrl(src: string | null): string | null {
  return resolveWbImageUrl(src);
}

function imageCandidateList(
  sources: unknown[],
  nmId: string | number | null | undefined,
): string[] {
  const direct = sources.filter(
    (value): value is string => typeof value === "string" && value.trim() !== "",
  );
  return [
    ...new Set(
      [...direct, ...wbImageCandidates(nmId)]
        .map((value) => proxyWbImageUrl(value.trim()))
        .filter((value): value is string => Boolean(value)),
    ),
  ];
}

function itemImageCandidates(item: ActionCenterItem | null): string[] {
  if (!item) return [];
  const payload = itemPayload(item);
  const raw =
    typeof item.raw === "object" && item.raw
      ? (item.raw as Record<string, unknown>)
      : {};
  const sources = [
    item.image_url,
    item.photo_url,
    item.photo,
    item.thumbnail,
    payload.image_url,
    payload.photo_url,
    payload.photo,
    payload.thumbnail,
    payload.main_photo_url,
    firstArrayImage(payload.photos),
    firstArrayImage(payload.images),
    raw.image_url,
    raw.photo_url,
    raw.photo,
    raw.thumbnail,
    firstArrayImage(raw.photos),
    firstArrayImage(raw.images),
  ];
  return imageCandidateList(sources, item.nm_id);
}

function rowImageCandidates(row: CostsMissingItem | null): string[] {
  if (!row) return [];
  const obj = row as Record<string, unknown>;
  const sources = [
    obj.image_url,
    obj.photo_url,
    obj.photo,
    obj.thumbnail,
    obj.main_photo_url,
    firstArrayImage(obj.photos),
    firstArrayImage(obj.images),
  ];
  return imageCandidateList(sources, row.nm_id);
}

function productRowImageCandidates(row: PortalProductRow | null): string[] {
  if (!row) return [];
  const obj = row as Record<string, unknown>;
  const sources = [
    obj.image_url,
    obj.photo_url,
    obj.photo,
    obj.thumbnail,
    obj.thumbnail_url,
    obj.main_photo_url,
    firstArrayImage(obj.photos),
    firstArrayImage(obj.images),
  ];
  return imageCandidateList(sources, row.nm_id);
}

function ProductThumb({
  candidates,
  label,
  className = "h-16 w-16",
}: {
  candidates: string[];
  label: string;
  className?: string;
}) {
  const uniqueCandidates = useMemo(
    () => [...new Set(candidates.filter(Boolean))],
    [candidates],
  );
  const [idx, setIdx] = useState(0);

  useEffect(() => {
    setIdx(0);
  }, [uniqueCandidates.join("|")]);

  const baseClass = `relative shrink-0 overflow-hidden rounded-md border bg-muted shadow-sm ${className}`;
  if (!uniqueCandidates.length || idx >= uniqueCandidates.length) {
    return (
      <div
        className={`${baseClass} flex items-center justify-center text-muted-foreground`}
      >
        <PackageSearch className="h-5 w-5" />
      </div>
    );
  }

  return (
    <div className={baseClass}>
      <img
        key={uniqueCandidates[idx]}
        src={uniqueCandidates[idx]}
        alt={label}
        loading="lazy"
        referrerPolicy="no-referrer"
        className="h-full w-full object-cover"
        onError={() => setIdx((value) => value + 1)}
      />
    </div>
  );
}

function asLooseRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function itemPayload(item: ActionCenterItem): Record<string, unknown> {
  return {
    ...asLooseRecord(item.raw),
    ...asLooseRecord(item.payload),
  };
}

function numberFromUnknown(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string") {
    const parsed = Number(value.replace(/\s/g, "").replace(",", "."));
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function moneyFromUnknown(value: unknown): number {
  const parsed = numberFromUnknown(value);
  return parsed == null ? 0 : Math.abs(parsed);
}

function missingCostRevenue(row: CostsMissingItem | null | undefined): number {
  return moneyFromUnknown(row?.affected_revenue);
}

function sortMissingCostRows(rows: CostsMissingItem[]): CostsMissingItem[] {
  return [...rows].sort((a, b) => {
    const revenueDelta = missingCostRevenue(b) - missingCostRevenue(a);
    if (revenueDelta) return revenueDelta;
    return String(costRowLabel(a)).localeCompare(String(costRowLabel(b)), "ru");
  });
}

function isManualTask(item: ActionCenterItem | null): boolean {
  return (
    norm(item?.source_module) === "manual" ||
    Boolean(item && itemPayload(item).manual_task)
  );
}

function manualTaskActionId(item: ActionCenterItem): number | null {
  if (typeof item.action_id === "number" && Number.isFinite(item.action_id)) {
    return item.action_id;
  }
  const match = String(item.id ?? "").match(/^unified:(\d+)$/);
  if (!match) return null;
  const parsed = Number(match[1]);
  return Number.isFinite(parsed) ? parsed : null;
}

function manualTaskProgress(item: ActionCenterItem): ManualTaskProgress {
  const payload = itemPayload(item);
  const rawProgress = payload.manual_task_progress;
  if (
    !rawProgress ||
    typeof rawProgress !== "object" ||
    Array.isArray(rawProgress)
  ) {
    return EMPTY_MANUAL_TASK_PROGRESS;
  }
  const progress = rawProgress as Record<string, unknown>;
  const items = Array.isArray(progress.items)
    ? progress.items.map((entry) => asLooseRecord(entry))
    : [];
  const done = numberFromUnknown(progress.done) ?? 0;
  const skipped = numberFromUnknown(progress.skipped) ?? 0;
  const total = numberFromUnknown(progress.total) ?? items.length;
  return {
    total,
    done,
    skipped,
    pending:
      numberFromUnknown(progress.pending) ??
      Math.max(total - done - skipped, 0),
    percent:
      numberFromUnknown(progress.percent) ??
      (total ? Math.round((done / total) * 100) : 0),
    items: items.map((entry) => ({
      id: firstString(entry.id) ?? numberFromUnknown(entry.id),
      item_key: firstString(entry.item_key),
      status: firstString(entry.status, "pending"),
      nm_id: numberFromUnknown(entry.nm_id),
      sku_id: numberFromUnknown(entry.sku_id),
      vendor_code: firstString(entry.vendor_code),
      title: firstString(entry.title),
      photo_url: firstString(entry.photo_url),
      last_comment: firstString(entry.last_comment),
    })),
  };
}

function manualTaskProducts(item: ActionCenterItem): PortalProductRow[] {
  const payload = itemPayload(item);
  const rows = Array.isArray(payload.selected_products)
    ? payload.selected_products
    : [];
  return rows
    .map((entry) => {
      const row = asLooseRecord(entry);
      return {
        nm_id: Number(row.nm_id),
        sku_id: numberFromUnknown(row.sku_id),
        title: firstString(row.title, row.name),
        vendor_code: firstString(row.vendor_code, row.article),
        photo_url: firstString(row.photo_url, row.image_url, row.thumbnail),
        thumbnail: firstString(row.thumbnail, row.photo_url, row.image_url),
        manual_task_item_key: firstString(
          row.manual_task_item_key,
          row.item_key,
        ),
      };
    })
    .filter(
      (row) => Number.isFinite(row.nm_id) && row.nm_id > 0,
    ) as PortalProductRow[];
}

function productRowTitle(row: PortalProductRow | null): string {
  if (!row) return "Товар";
  return (
    firstString(row.title, row.name, row.vendor_code, row.article) ||
    `nm ${row.nm_id}`
  );
}

function productRowSubtitle(row: PortalProductRow | null): string {
  if (!row) return "";
  return [
    row.nm_id ? `nm ${row.nm_id}` : null,
    row.vendor_code || row.article,
    row.subject_name,
  ]
    .filter(Boolean)
    .join(" / ");
}

function toDateTimeLocalValue(date: Date): string {
  const pad = (value: number) => String(value).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function defaultManualDeadline(): string {
  const date = new Date();
  date.setDate(date.getDate() + 2);
  date.setHours(18, 0, 0, 0);
  return toDateTimeLocalValue(date);
}

function dateTimeLocalToIso(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toISOString();
}

function postponeUntilIso(days: number): string {
  const date = new Date();
  date.setDate(date.getDate() + days);
  date.setHours(10, 0, 0, 0);
  return date.toISOString();
}

function parseMoneyDraft(value: string, optional = false): number | null {
  const trimmed = String(value ?? "")
    .replace(/\s/g, "")
    .replace(",", ".")
    .trim();
  if (!trimmed) return optional ? 0 : null;
  const parsed = Number(trimmed);
  if (!Number.isFinite(parsed) || parsed < 0) return null;
  return Math.round(parsed * 100) / 100;
}

const INLINE_COST_CODES = new Set([
  "missing_cost_blocks_profit",
  "missing_manual_cost",
  "seller_other_expense_missing",
]);

const INLINE_CARD_TEXT_CODES = new Set([
  "title_missing",
  "no_title",
  "title_too_short",
  "title_too_long",
  "title_policy_violation",
  "title_repeated_words",
  "title_excessive_punctuation_caps",
  "title_equals_vendor_code",
  "description_missing",
  "no_description",
  "description_too_short",
  "description_too_long",
  "description_policy_violation",
  "description_duplicates_title",
  "description_no_useful_details",
]);

const INLINE_SKU_MAPPING_CODES = new Set([
  "unmatched_sku",
  "manual_cost_unresolved_sku",
  "manual_cost_ambiguous_match",
  "sku_mapping",
  "map_sku",
]);

function isInlineCostAction(item: ActionCenterItem): boolean {
  const payload = itemPayload(item);
  const text = [
    actionCode(item),
    payload.code,
    payload.issue_code,
    payload.problem_code,
    item.title,
  ]
    .map(norm)
    .join(" ");
  return (
    [...INLINE_COST_CODES].some((code) => text.includes(code)) ||
    text.includes("себесто")
  );
}

function dataQualityIssueId(item: ActionCenterItem): number | null {
  const payload = itemPayload(item);
  const ledger =
    payload.evidence_ledger ?? item.evidence_ledger ?? payload.evidence ?? {};
  const sourceRefs = [
    ...(Array.isArray(payload.source_references)
      ? payload.source_references
      : []),
    ...(Array.isArray(ledger.source_references)
      ? ledger.source_references
      : []),
  ];
  const dataQualityRef = sourceRefs.find(
    (ref: any) =>
      String(ref?.source_table ?? ref?.table ?? "").includes(
        "data_quality_issues",
      ) && numberFromUnknown(ref?.primary_key ?? ref?.id),
  );
  return numberFromUnknown(
    payload.data_quality_issue_id ??
      payload.dq_issue_id ??
      payload.issue_id ??
      payload.issueId ??
      ledger?.data_fix?.issue_id ??
      ledger?.data_fix?.data_quality_issue_id ??
      dataQualityRef?.primary_key ??
      dataQualityRef?.id ??
      payload.id ??
      (String(item.source ?? "").includes("data_quality")
        ? item.source_id
        : null),
  );
}

function isInlineSkuMappingAction(item: ActionCenterItem): boolean {
  const payload = itemPayload(item);
  const text = [
    actionCode(item),
    payload.code,
    payload.issue_code,
    payload.problem_code,
    payload.fix_component_type,
    item.title,
    item.description,
    item.reason,
  ]
    .map(norm)
    .join(" ");
  return (
    Boolean(dataQualityIssueId(item)) &&
    ([...INLINE_SKU_MAPPING_CODES].some((code) => text.includes(code)) ||
      (text.includes("sku") &&
        (text.includes("сопостав") ||
          text.includes("mapping") ||
          text.includes("unmatched"))))
  );
}

function skuCandidates(item: ActionCenterItem): number[] {
  const payload = itemPayload(item);
  const raw =
    payload.candidate_sku_ids ??
    payload.sku_candidates ??
    payload.candidates ??
    payload.suggested_sku_ids ??
    [];
  const values = Array.isArray(raw)
    ? raw
    : Array.isArray(raw?.items)
      ? raw.items
      : [];
  return [
    ...new Set(
      values
        .map((value) => numberFromUnknown(value?.sku_id ?? value?.id ?? value))
        .filter(Boolean),
    ),
  ];
}

function cardQualityIssueId(item: ActionCenterItem): number | null {
  const payload = itemPayload(item);
  return numberFromUnknown(
    payload.issue_id ??
      payload.id ??
      (String(item.source ?? "").includes("card_quality")
        ? item.source_id
        : null),
  );
}

function cardTextField(item: ActionCenterItem): "title" | "description" | null {
  const payload = itemPayload(item);
  const field = norm(
    payload.field_path ??
      payload.field_name ??
      payload.category ??
      payload.type,
  );
  const code = norm(actionCode(item) || payload.issue_code || payload.code);
  if (field.includes("title") || code.includes("title") || code === "no_title")
    return "title";
  if (
    field.includes("description") ||
    code.includes("description") ||
    code === "no_description"
  )
    return "description";
  return null;
}

function isInlineCardTextAction(item: ActionCenterItem): boolean {
  const payload = itemPayload(item);
  const code = norm(actionCode(item) || payload.issue_code || payload.code);
  return Boolean(
    cardQualityIssueId(item) &&
    cardTextField(item) &&
    INLINE_CARD_TEXT_CODES.has(code),
  );
}

function costRowKey(row: CostsMissingItem, index: number): string {
  return String(row.sku_id ?? row.nm_id ?? index);
}

function costRowLabel(row: CostsMissingItem | null): string {
  if (!row) return "Товар";
  return (
    [
      row.nm_id ? `nm ${row.nm_id}` : null,
      row.vendor_code,
      row.product_title,
      row.tech_size ? `размер ${row.tech_size}` : null,
    ]
      .filter(Boolean)
      .join(" / ") || `SKU ${row.sku_id ?? "—"}`
  );
}

function invalidateInlineResolverQueries(
  queryClient: ReturnType<typeof useQueryClient>,
) {
  queryClient.invalidateQueries({ queryKey: ["portal-actions"] });
  queryClient.invalidateQueries({ queryKey: ["dq-resolution-context"] });
  queryClient.invalidateQueries({ queryKey: ["dq-issues-for-data-fix"] });
  queryClient.invalidateQueries({ queryKey: ["costs-missing"] });
  queryClient.invalidateQueries({ queryKey: ["costs-rows"] });
  queryClient.invalidateQueries({ queryKey: ["costs-unresolved"] });
  queryClient.invalidateQueries({ queryKey: ["dashboard-data-health"] });
  queryClient.invalidateQueries({ queryKey: ["money-data-blockers"] });
  queryClient.invalidateQueries({ queryKey: ["dash-data-blockers"] });
  queryClient.invalidateQueries({ queryKey: ["dq-issues-summary"] });
  queryClient.invalidateQueries({ queryKey: ["portal-problem-results"] });
  queryClient.invalidateQueries({ queryKey: ["portal-card-quality-issues"] });
  queryClient.invalidateQueries({ queryKey: ["portal-card-quality-grouped"] });
}

function priorityRank(item: ActionCenterItem): number {
  if (isContentQualityOpportunityAction(item)) {
    return 3;
  }
  const priority = norm(item.priority).toUpperCase();
  const severity = norm(item.severity);
  if (priority === "P0" || severity === "critical") return 0;
  if (priority === "P1" || severity === "high") return 1;
  if (priority === "P2" || severity === "medium") return 2;
  if (priority === "P3" || severity === "low") return 3;
  return 4;
}

function actionCode(item: ActionCenterItem): string {
  return String(
    item.problem_code ??
      item.detector_code ??
      item.issue_code ??
      item.action_type ??
      "",
  );
}

function emptyActionExecutionSummary(): ActionExecutionSummary {
  return {
    execute: 0,
    inline: 0,
    decision: 0,
    manual: 0,
    blocked: 0,
    signal: 0,
  };
}

function actionExecutionMode(item: ActionCenterItem): ActionExecutionMode {
  if (isClosedAction(item)) return "signal";
  const primary = primaryActionForItem(item);
  const disabled = primaryDisabledActionForItem(item);
  const guided = item.guided_fix ?? {};
  const guidedStatus = norm(guided.status);
  const source = norm(item.source_module);
  const code = norm(actionCode(item));
  if (hasInlineResolution(item)) return "inline";
  if (dataFreshnessBlocksAction(item.data_freshness)) return "blocked";
  if (item.can_execute === true) return "execute";
  if (source === "manual" || code.includes("manual_task")) return "manual";
  if (
    isDataBlockerAction(item) ||
    item.evidence_state === "missing_evidence" ||
    ["missing", "not_configured"].includes(
      norm(item.data_freshness?.source_status),
    )
  ) {
    return "blocked";
  }
  if (
    guidedStatus === "not_configured" ||
    guidedStatus === "disabled" ||
    guidedStatus === "missing_wb_write" ||
    disabled
  ) {
    return "manual";
  }
  if (primary?.enabled) {
    return "decision";
  }
  return "signal";
}

function actionExecutionSummary(
  items: ActionCenterItem[],
): ActionExecutionSummary {
  const summary = emptyActionExecutionSummary();
  for (const item of items) {
    summary[actionExecutionMode(item)] += 1;
  }
  return summary;
}

function actionImpactAmount(item: ActionCenterItem): number {
  return moneyFromUnknown(
    item.expected_effect_amount ??
      item.expected_impact_amount ??
      item.money_impact_amount,
  );
}

function businessCaseKey(item: ActionCenterItem): string | null {
  const payload = itemPayload(item);
  const raw =
    typeof item.raw === "object" && item.raw
      ? (item.raw as Record<string, unknown>)
      : {};
  const linked =
    typeof item.linked_entity === "object" && item.linked_entity
      ? (item.linked_entity as Record<string, unknown>)
      : {};
  const nmId = numberFromUnknown(
    item.nm_id ?? payload.nm_id ?? raw.nm_id ?? linked.nm_id,
  );
  if (nmId) return `nm:${nmId}`;
  const skuId = numberFromUnknown(
    item.sku_id ?? payload.sku_id ?? raw.sku_id ?? linked.sku_id,
  );
  if (skuId) return `sku:${skuId}`;
  if (item.entity_type && item.entity_id != null) {
    return `${norm(item.entity_type)}:${String(item.entity_id)}`;
  }
  const vendor = firstString(
    item.vendor_code,
    payload.vendor_code,
    raw.vendor_code,
    linked.vendor_code,
  );
  if (vendor) return `vendor:${vendor}`;
  return null;
}

function isAggregateMissingCostImpact(item: ActionCenterItem): boolean {
  return (
    isMissingCostProblem(item) &&
    numberFromUnknown(item.nm_id) == null &&
    actionImpactAmount(item) > 0
  );
}

function dedupedImpactSummary(items: ActionCenterItem[]): {
  value: number;
  raw: number;
  overlap: number;
  objects: number;
} {
  const hasAggregateMissingCost = items.some(isAggregateMissingCostImpact);
  const byObject = new Map<string, number>();
  let raw = 0;
  for (const item of items) {
    if (isClosedAction(item)) continue;
    if (
      hasAggregateMissingCost &&
      isMissingCostProblem(item) &&
      !isAggregateMissingCostImpact(item)
    ) {
      continue;
    }
    const amount = actionImpactAmount(item);
    raw += amount;
    if (!amount) continue;
    const key = businessCaseKey(item) ?? `action:${item.id}`;
    byObject.set(key, Math.max(byObject.get(key) ?? 0, amount));
  }
  const value = Array.from(byObject.values()).reduce(
    (sum, amount) => sum + amount,
    0,
  );
  return {
    value,
    raw,
    overlap: Math.max(0, raw - value),
    objects: byObject.size,
  };
}

function buildBusinessCases(items: ActionCenterItem[]): ActionBusinessCase[] {
  const byObject = new Map<string, ActionCenterItem[]>();
  for (const item of items) {
    if (isClosedAction(item)) continue;
    const key = businessCaseKey(item) ?? `action:${item.id}`;
    const bucket = byObject.get(key) ?? [];
    bucket.push(item);
    byObject.set(key, bucket);
  }
  const cases: ActionBusinessCase[] = [];
  for (const [key, bucket] of byObject.entries()) {
    const sortedBucket = sortByBusinessPriority(bucket);
    const mainItem = sortedBucket[0];
    const counts = new Map<string, number>();
    let rawSignalMoney = 0;
    let money = 0;
    for (const item of sortedBucket) {
      const amount = actionImpactAmount(item);
      rawSignalMoney += amount;
      money = Math.max(money, amount);
      const code = actionCode(item) || item.action_type || "unknown";
      counts.set(code, (counts.get(code) ?? 0) + 1);
    }
    cases.push({
      key,
      title: problemTitle(mainItem),
      objectLabel: objectLabel(mainItem),
      mainItem,
      items: sortedBucket,
      groupKey: problemGroupKey(mainItem),
      count: sortedBucket.length,
      money,
      rawSignalMoney,
      urgent: sortedBucket.some(isUrgentAction),
      blocker: sortedBucket.some(isDataBlockerAction),
      execution: actionExecutionSummary(sortedBucket),
      topCodes: Array.from(counts.entries())
        .sort((a, b) => b[1] - a[1])
        .slice(0, 3)
        .map(([code, count]) => ({
          code,
          label: problemCodeLabel(code) || code.replaceAll("_", " "),
          count,
        })),
    });
  }
  return cases.sort((a, b) => {
    const rankDelta =
      actionBusinessPriorityRank(a.mainItem) - actionBusinessPriorityRank(b.mainItem);
    if (rankDelta) return rankDelta;
    const groupRankDelta =
      problemGroupBusinessRank(a.groupKey) - problemGroupBusinessRank(b.groupKey);
    if (groupRankDelta) return groupRankDelta;
    if (b.money !== a.money) return b.money - a.money;
    if (b.count !== a.count) return b.count - a.count;
    return priorityRank(a.mainItem) - priorityRank(b.mainItem);
  });
}

function signalCountLabel(count: number): string {
  if (count === 1) return "1 сигнал";
  if (count > 1 && count < 5) return `${count} сигнала`;
  return `${count} сигналов`;
}

function businessCaseDisplayTitle(caseItem: ActionBusinessCase): string {
  if (caseItem.count <= 1) return caseItem.title;
  const labels = caseItem.topCodes.map((code) => code.label).filter(Boolean);
  return labels.length ? labels.slice(0, 2).join(" + ") : caseItem.title;
}

function businessCaseSubtitle(caseItem: ActionBusinessCase): string {
  const labels = caseItem.topCodes
    .map((code) => `${code.label}${code.count > 1 ? ` · ${code.count}` : ""}`)
    .filter(Boolean);
  if (caseItem.count > 1 && labels.length) return labels.join(" / ");
  const item = caseItem.mainItem;
  return (
    item.short_explanation ||
    item.reason ||
    problemCodeLabel(actionCode(item))
  );
}

function buildBusinessCaseGroups(cases: ActionBusinessCase[]): ProblemGroupSummary[] {
  return PROBLEM_GROUP_ORDER.map((key) => {
    const caseItems = cases.filter((item) => item.groupKey === key);
    if (!caseItems.length) return null;
    const execution = emptyActionExecutionSummary();
    const codeCounts = new Map<string, number>();
    const items = caseItems.flatMap((item) => item.items);
    for (const item of caseItems) {
      for (const mode of Object.keys(execution) as ActionExecutionMode[]) {
        execution[mode] += item.execution[mode] ?? 0;
      }
      for (const code of item.topCodes) {
        codeCounts.set(code.code, (codeCounts.get(code.code) ?? 0) + code.count);
      }
    }
    const cfg = PROBLEM_GROUP_CONFIG[key];
    return {
      key,
      ...cfg,
      items,
      open: caseItems.length,
      closed: 0,
      urgent: caseItems.filter((item) => item.urgent).length,
      blockers: caseItems.filter((item) => item.blocker).length,
      actionable: caseItems.filter(
        (item) => item.execution.execute + item.execution.inline > 0,
      ).length,
      execution,
      money: caseItems.reduce((sum, item) => sum + item.money, 0),
      progress: 0,
      topCodes: Array.from(codeCounts.entries())
        .map(([code, count]) => ({
          code,
          label: problemCodeLabel(code) || code.replaceAll("_", " "),
          count,
        }))
        .sort((a, b) => b.count - a.count)
        .slice(0, 3),
    } satisfies ProblemGroupSummary;
  }).filter(Boolean) as ProblemGroupSummary[];
}

function isActionable(item: ActionCenterItem): boolean {
  if (isClosedAction(item)) return false;
  if (isContentQualityOpportunityAction(item)) return false;
  const mode = actionExecutionMode(item);
  return mode === "execute" || mode === "inline";
}

function problemPlaybook(item: ActionCenterItem): Array<{
  step_id: string;
  title: string;
  description: string;
  completion_signal: string;
  preferred_href?: "result" | "work";
}> {
  const code = norm(actionCode(item));
  const subject = objectLabel(item);
  if (
    [
      "negative_unit_profit",
      "price_below_safe_margin",
      "promo_not_profitable",
      "price_offer_blocks_conversion",
      "raise_price_possible_high_demand",
      "price_increase_review",
    ].includes(code)
  ) {
    return [
      {
        step_id: "check_price_inputs",
        title: "Проверить цену и экономику",
        description: `Откройте ${subject}. Сверьте текущую WB-цену, скидку, себестоимость, комиссию, логистику, рекламу и промо. Если цена выглядит неверной, сначала обновите синхронизацию цен.`,
        completion_signal: "Цена и все расходы совпадают с WB/учётом",
        preferred_href: "result",
      },
      {
        step_id: "set_safe_price",
        title: "Выставить безопасную цену или убрать убыточную скидку",
        description:
          "Откройте экран проверки цены. Поднимите цену до безопасной маржи или уменьшите скидку/промо. Не меняйте цену, если себестоимость или комиссии ещё не подтверждены.",
        completion_signal: "Новая цена не уводит товар в минус",
        preferred_href: "work",
      },
      {
        step_id: "recheck_profit",
        title: "Перепроверить прибыль",
        description:
          "Запустите перепроверку. Закрывайте задачу только когда маржа стала положительной и данные свежие.",
        completion_signal: "Проблема исчезла или стала понятна причина",
        preferred_href: "result",
      },
    ];
  }
  if (
    [
      "missing_cost_blocks_profit",
      "missing_manual_cost",
      "supplier_cost_coverage_below_threshold",
      "manual_cost_unresolved_sku",
      "manual_cost_ambiguous_match",
      "fix_cost_trust",
    ].includes(code)
  ) {
    return [
      {
        step_id: "find_cost_gap",
        title: "Найти, чего не хватает в себестоимости",
        description: `Проверьте ${subject}: есть ли SKU, поставщик, цена закупки, упаковка и дополнительные расходы. Без этого прибыль будет считаться неправильно.`,
        completion_signal: "Понятно, какая себестоимость или связь отсутствует",
        preferred_href: "result",
      },
      {
        step_id: "fill_cost",
        title: "Заполнить или сопоставить себестоимость",
        description:
          "Откройте экран себестоимости. Загрузите цену закупки или привяжите товар к правильному SKU/поставщику.",
        completion_signal: "Себестоимость сохранена и привязана к товару",
        preferred_href: "work",
      },
      {
        step_id: "recheck_cost",
        title: "Пересчитать прибыль",
        description:
          "Запустите перепроверку, чтобы Центр действий пересчитал прибыль, маржу и связанные проблемы.",
        completion_signal: "Прибыль пересчитана на свежих данных",
        preferred_href: "result",
      },
    ];
  }
  if (code === "missing_chrt_id") {
    return [
      {
        step_id: "check_variant_mapping",
        title: "Проверить связь размера с карточкой",
        description: `Сверьте ${subject}: nmID, размер, chrt_id и внутренний SKU. Без chrt_id аналитика по размерам и остаткам будет неполной.`,
        completion_signal: "Понятно, какой вариант карточки потерял связь",
        preferred_href: "result",
      },
      {
        step_id: "refresh_card_mapping",
        title: "Обновить карточки или передать на mapping",
        description:
          "Откройте исправление данных. Если связи нет после синхронизации карточек, назначьте администратору проверку каталога.",
        completion_signal:
          "Карточка синхронизирована или mapping взят в работу",
        preferred_href: "work",
      },
      {
        step_id: "recheck_variant_mapping",
        title: "Перепроверить аналитику размеров",
        description:
          "После обновления карточек запустите перепроверку, чтобы остатки и продажи снова связались с вариантом товара.",
        completion_signal: "chrt_id появился или причина зафиксирована",
        preferred_href: "result",
      },
    ];
  }
  if (
    [
      "unmatched_sku",
      "unmatched_sku_detected",
      "ad_spend_without_sku",
    ].includes(code)
  ) {
    return [
      {
        step_id: "identify_sku",
        title: "Найти правильный SKU",
        description: `Сверьте ${subject} с артикулом, размером, chrt_id и карточкой WB. Нужно понять, к какому внутреннему SKU относится товар.`,
        completion_signal: "Правильный SKU найден",
        preferred_href: "result",
      },
      {
        step_id: "map_sku",
        title: "Привязать SKU",
        description:
          "Откройте исправление данных и сохраните связь товара с SKU. Если есть конфликт, выберите единственный правильный вариант.",
        completion_signal: "SKU привязан без конфликта",
        preferred_href: "work",
      },
      {
        step_id: "recheck_mapping",
        title: "Обновить расчёты",
        description:
          "Запустите перепроверку, чтобы расходы, продажи и прибыль собрались на правильный SKU.",
        completion_signal: "Проблема сопоставления исчезла",
        preferred_href: "result",
      },
    ];
  }
  if (
    [
      "ads_spend_without_profit",
      "ad_pause_review",
      "expense_ad_double_count_risk",
      "high_ad_drr",
      "high_ad_cpo",
      "low_ads_ctr",
      "ads_stockout_risk",
    ].includes(code)
  ) {
    return [
      {
        step_id: "check_ads_loss",
        title: "Понять, какая реклама съедает прибыль",
        description:
          "Сверьте расход, продажи, маржу и кампанию. Отдельно проверьте, не считается ли реклама дважды.",
        completion_signal: "Понятна кампания или расход, который создаёт риск",
        preferred_href: "result",
      },
      {
        step_id: "adjust_ads",
        title: "Снизить риск по рекламе",
        description:
          "Откройте рекламу. Снизьте ставки, остановите убыточную кампанию или исправьте привязку расхода к SKU.",
        completion_signal: "Реклама больше не перекрывает прибыль",
        preferred_href: "work",
      },
      {
        step_id: "recheck_ads",
        title: "Перепроверить после обновления расходов",
        description:
          "После обновления рекламных данных запустите перепроверку и закройте задачу, если экономика стала нормальной.",
        completion_signal: "Расходы и прибыль пересчитаны",
        preferred_href: "result",
      },
    ];
  }
  if (code === "ads_spend_no_orders") {
    return [
      {
        step_id: "check_ads_no_orders",
        title: "Найти рекламу без заказов",
        description:
          "Сверьте расход, заказы, кампанию, ставку, кластер и карточку. Сначала нужно понять: проблема в трафике, карточке или цене.",
        completion_signal:
          "Понятна кампания или кластер, который тратит бюджет",
        preferred_href: "result",
      },
      {
        step_id: "ads_review",
        title: "Открыть рекламный review",
        description:
          "Проверьте ставки и бюджет. Если карточка или цена слабые, сначала исправьте их, затем возвращайтесь к рекламе.",
        completion_signal: "Выбран безопасный план по рекламе",
        preferred_href: "work",
      },
      {
        step_id: "recheck_ads_orders",
        title: "Перепроверить заказы",
        description:
          "После обновления рекламной статистики запустите перепроверку и закройте задачу, если появились заказы или расход снизился.",
        completion_signal: "Расход больше не идёт без заказов",
        preferred_href: "result",
      },
    ];
  }
  if (
    [
      "low_conversion_card",
      "no_sales_with_views",
      "card_content_review",
    ].includes(code)
  ) {
    return [
      {
        step_id: "check_conversion",
        title: "Понять, почему просмотры не дают заказы",
        description:
          "Сверьте фото, title, характеристики, цену, отзывы и источник трафика. Это возможность роста, не подтверждённый убыток.",
        completion_signal: "Понятна главная гипотеза низкой конверсии",
        preferred_href: "result",
      },
      {
        step_id: "fix_card_conversion",
        title: "Улучшить карточку или цену",
        description:
          "Запустите проверку карточки, исправьте title/фото/характеристики или откройте цену, если товар проигрывает по офферу.",
        completion_signal: "Изменение сохранено или поставлено ответственному",
        preferred_href: "work",
      },
      {
        step_id: "recheck_conversion",
        title: "Перепроверить конверсию",
        description:
          "После обновления аналитики проверьте, выросла ли конверсия или нужно создать новую ручную задачу.",
        completion_signal: "Конверсия стала нормальной или есть следующий план",
        preferred_href: "result",
      },
    ];
  }
  if (code === "high_return_rate") {
    return [
      {
        step_id: "check_return_reason",
        title: "Найти причину возвратов",
        description:
          "Проверьте размерную сетку, фото, описание, характеристики, качество товара и ожидания покупателя.",
        completion_signal:
          "Понятна причина, из-за которой покупатели возвращают товар",
        preferred_href: "result",
      },
      {
        step_id: "fix_return_cause",
        title: "Исправить ожидания в карточке",
        description:
          "Обновите фото, описание, размеры или создайте задачу ответственному, если нужна проверка качества товара.",
        completion_signal: "Карточка или задача по качеству обновлена",
        preferred_href: "work",
      },
      {
        step_id: "recheck_returns",
        title: "Перепроверить возвратность",
        description:
          "После новых продаж и возвратов запустите перепроверку и закройте задачу, если процент возвратов снизился.",
        completion_signal: "Возвратность снизилась или есть ручной план",
        preferred_href: "result",
      },
    ];
  }
  if (
    [
      "negative_reviews_need_reply",
      "questions_need_reply",
      "low_product_rating",
    ].includes(code)
  ) {
    return [
      {
        step_id: "read_reputation_signal",
        title: "Прочитать отзыв или вопрос",
        description:
          "Откройте репутацию и проверьте текст, рейтинг, категорию негатива и связь с карточкой товара.",
        completion_signal: "Понятно, что именно беспокоит покупателя",
        preferred_href: "result",
      },
      {
        step_id: "reply_or_assign_quality",
        title: "Ответить или назначить разбор",
        description:
          "Подготовьте ответ покупателю. Если причина в качестве товара, размерах или описании, создайте ручную задачу ответственному.",
        completion_signal: "Ответ готов или задача по причине создана",
        preferred_href: "work",
      },
      {
        step_id: "recheck_reputation",
        title: "Перепроверить репутацию",
        description:
          "После ответа или обновления репутации запустите перепроверку и закройте задачу, если сигнал исчез.",
        completion_signal: "Отзыв/вопрос обработан или есть план исправления",
        preferred_href: "result",
      },
    ];
  }
  if (
    [
      "overstock_slow_moving",
      "dead_stock",
      "storage_cost_pressure",
      "liquidate_stock",
      "do_not_reorder",
      "stock_without_sales",
    ].includes(code)
  ) {
    return [
      {
        step_id: "check_stock_reason",
        title: "Понять причину зависшего остатка",
        description:
          "Проверьте остаток, продажи за 30 дней, цену, карточку, рекламу и отзывы. Не запускайте скидку без проверки маржи.",
        completion_signal: "Понятно, почему товар не продаётся",
        preferred_href: "result",
      },
      {
        step_id: "choose_stock_action",
        title: "Выбрать безопасное действие",
        description:
          "Откройте остатки или план закупок. Зафиксируйте: не дозаказывать, распродать, снизить цену/запустить промо или улучшить карточку. Скидку применяйте только после проверки маржи.",
        completion_signal: "Выбран сценарий, который не создаёт убыток",
        preferred_href: "work",
      },
      {
        step_id: "recheck_stock",
        title: "Проверить динамику",
        description:
          "Перепроверьте после обновления продаж и остатков. Закрывайте задачу, когда скорость продаж стала нормальной.",
        completion_signal: "Остаток начал двигаться или выбран ручной план",
        preferred_href: "result",
      },
    ];
  }
  if (
    [
      "low_stock_risk",
      "fast_stock_depletion",
      "stockout_now_with_recent_orders",
      "stockout_risk_14d",
      "reorder",
      "protect_stock",
      "sales_without_stock",
    ].includes(code)
  ) {
    return [
      {
        step_id: "check_depletion",
        title: "Проверить, на сколько дней хватит остатка",
        description:
          "Сверьте текущий остаток, средние продажи и ближайшие поставки. Убедитесь, что остатки свежие.",
        completion_signal: "Понятна дата риска дефицита",
        preferred_href: "result",
      },
      {
        step_id: "plan_supply",
        title: "Запланировать пополнение или снизить спрос",
        description:
          "Откройте поставки. Создайте план пополнения, выберите склад/количество или временно снизьте промо и рекламу, если поставка не успевает.",
        completion_signal:
          "Есть план поставки или временное ограничение спроса",
        preferred_href: "work",
      },
      {
        step_id: "recheck_supply",
        title: "Проверить остатки после обновления",
        description:
          "Запустите перепроверку после обновления остатков или создания поставки.",
        completion_signal: "Риск дефицита исчез или взят в работу",
        preferred_href: "result",
      },
    ];
  }
  if (
    [
      "expense_unclassified",
      "unclassified_finance_expense",
      "seller_other_expense_missing",
    ].includes(code)
  ) {
    return [
      {
        step_id: "find_expense",
        title: "Найти расход без категории",
        description:
          "Откройте финансовую строку и проверьте сумму, дату, назначение и связь с товаром или заказом.",
        completion_signal: "Понятно, к какой категории относится расход",
        preferred_href: "result",
      },
      {
        step_id: "classify_expense",
        title: "Разнести расход",
        description:
          "Выберите категорию расхода и сохраните. Если расход относится к товару, проверьте связь с SKU.",
        completion_signal: "Расход классифицирован",
        preferred_href: "work",
      },
      {
        step_id: "recheck_money",
        title: "Пересчитать финансы",
        description:
          "Запустите перепроверку, чтобы расход попал в прибыль и отчёты.",
        completion_signal: "Финансы пересчитаны",
        preferred_href: "result",
      },
    ];
  }
  if (["stock_snapshot_missing", "stocks_task_failed"].includes(code)) {
    return [
      {
        step_id: "check_sync",
        title: "Проверить синхронизацию остатков",
        description:
          "Посмотрите, когда последний раз обновлялись остатки и какая ошибка пришла от источника.",
        completion_signal: "Понятна причина отсутствия остатков",
        preferred_href: "result",
      },
      {
        step_id: "run_sync",
        title: "Обновить остатки",
        description:
          "Запустите синхронизацию остатков или исправьте подключение источника.",
        completion_signal: "Остатки обновились",
        preferred_href: "work",
      },
      {
        step_id: "recheck_stock_sync",
        title: "Перепроверить связанные проблемы",
        description:
          "После обновления остатков запустите перепроверку Центра действий.",
        completion_signal: "Проблемы по остаткам пересчитаны",
        preferred_href: "result",
      },
    ];
  }
  return [
    {
      step_id: "understand",
      title: "Проверить причину",
      description:
        item.short_explanation ||
        item.reason ||
        `Откройте ${objectLabel(item)} и проверьте факты, по которым платформа создала задачу.`,
      completion_signal: "Причина понятна",
      preferred_href: "result",
    },
    {
      step_id: "fix",
      title:
        humanActionLabel(primaryActionForItem(item)?.code) ||
        guidedFixLabel(item),
      description:
        item.next_step || "Откройте рабочий экран и внесите исправление.",
      completion_signal: "Исправление сохранено",
      preferred_href: "work",
    },
    {
      step_id: "close",
      title: "Перепроверить и закрыть",
      description:
        "Запустите перепроверку. Закрывайте задачу только если проблема исчезла или есть понятное ручное решение.",
      completion_signal: "Статус обновлён",
      preferred_href: "result",
    },
  ];
}

function fallbackSolveSteps(
  item: ActionCenterItem,
): ActionCenterSolveMapStep[] {
  const primary = primaryActionForItem(item);
  const disabled = primaryDisabledActionForItem(item);
  const href = primary?.href ?? guidedFixHref(item) ?? disabled?.href ?? null;
  const resultHref = resultsHrefForAction(item);
  const blockedReason =
    disabled?.disabled_reason ??
    (item.data_freshness?.blocking_sources?.length
      ? dataFreshnessBlockingLabel(item.data_freshness)
      : null);
  return problemPlaybook(item).map((step, index) => {
    const isFixStep = step.preferred_href === "work";
    const isFirst = index === 0;
    const isLast = index === 2;
    return {
      step_id: step.step_id,
      order: index + 1,
      title: step.title,
      description: step.description,
      status:
        isLast && isClosedAction(item)
          ? "done"
          : isFixStep && blockedReason
            ? "blocked"
            : isFirst && item.evidence_state === "missing_evidence"
              ? "waiting_for_data"
              : "available",
      action_code:
        isLast && item.can_recheck ? "recheck" : (primary?.code ?? null),
      action_label: isLast
        ? "Перепроверить"
        : isFixStep
          ? humanActionLabel(primary?.code) || guidedFixLabel(item)
          : "Открыть детали",
      target_href: step.preferred_href === "work" ? href : resultHref,
      required_metrics: [],
      blocking_reason:
        isFixStep && blockedReason
          ? blockedReason
          : isFirst && item.evidence_state === "missing_evidence"
            ? "Не хватает доказательств для расчёта"
            : null,
      completion_signal: step.completion_signal,
    };
  });
}

function solveSteps(item: ActionCenterItem): ActionCenterSolveMapStep[] {
  const playbook = problemPlaybook(item);
  const steps = item.solve_map?.steps?.length
    ? item.solve_map.steps
    : fallbackSolveSteps(item);
  return [...steps]
    .sort((a, b) => Number(a.order ?? 0) - Number(b.order ?? 0))
    .map((step, index) => {
      const local = playbook[index];
      const localizedTitle = hasCyrillicText(step.title)
        ? step.title
        : (local?.title ?? humanActionLabel(step.action_code));
      const localizedDescription = hasCyrillicText(step.description)
        ? step.description
        : (local?.description ??
          "Откройте рабочий экран и выполните действие по задаче.");
      const localizedCompletion = hasCyrillicText(step.completion_signal)
        ? step.completion_signal
        : (local?.completion_signal ?? "Изменение сохранено и проверено");
      return {
        ...step,
        title: localizedTitle,
        description: localizedDescription,
        completion_signal: localizedCompletion,
        action_label: step.action_label || humanActionLabel(step.action_code),
      };
    });
}

function stepDone(step: ActionCenterSolveMapStep): boolean {
  return step.status === "done";
}

function stepBlocked(step: ActionCenterSolveMapStep): boolean {
  return step.status === "blocked" || step.status === "waiting_for_data";
}

function moduleAccent(module?: string | null): string {
  const value = norm(module);
  if (value === "data_quality" || value === "costs") return "bg-amber-500";
  if (value === "problem_engine") return "bg-sky-500";
  if (value === "checker") return "bg-violet-500";
  if (value === "finance") return "bg-emerald-500";
  if (value === "stockops") return "bg-cyan-500";
  return "bg-slate-400";
}

function modulePanelTone(module?: string | null): string {
  const value = norm(module);
  if (value === "data_quality" || value === "costs") {
    return "border-amber-500/35 bg-amber-500/5";
  }
  if (value === "problem_engine") {
    return "border-sky-500/35 bg-sky-500/5";
  }
  if (value === "checker") {
    return "border-violet-500/35 bg-violet-500/5";
  }
  if (value === "finance") {
    return "border-emerald-500/35 bg-emerald-500/5";
  }
  if (value === "stockops") {
    return "border-cyan-500/35 bg-cyan-500/5";
  }
  return "border-border bg-muted/30";
}

function moduleTextTone(module?: string | null): string {
  const value = norm(module);
  if (value === "data_quality" || value === "costs")
    return "text-amber-700 dark:text-amber-300";
  if (value === "problem_engine") return "text-sky-700 dark:text-sky-300";
  if (value === "checker") return "text-violet-700 dark:text-violet-300";
  if (value === "finance") return "text-emerald-700 dark:text-emerald-300";
  if (value === "stockops") return "text-cyan-700 dark:text-cyan-300";
  return "text-muted-foreground";
}

function priorityRailTone(item: ActionCenterItem): string {
  const priority = String(item.priority ?? item.severity ?? "P3").toUpperCase();
  if (priority === "P0") return "bg-red-500";
  if (priority === "P1") return "bg-orange-500";
  if (priority === "P2") return "bg-sky-500";
  return moduleAccent(item.source_module);
}

function actionStateLabel(item: ActionCenterItem): string {
  if (isClosedAction(item)) return "Закрыто";
  const mode = actionExecutionMode(item);
  if (mode === "execute") return "Можно применить";
  if (mode === "inline") return "Исправить здесь";
  if (mode === "blocked") return "Нужны данные";
  if (isOverdueAction(item, new Date())) return "Просрочено";
  if (mode === "decision") return "Нужно решение";
  if (mode === "manual") return "Ручной шаг";
  return "Наблюдение";
}

function actionStateTone(item: ActionCenterItem): string {
  if (isClosedAction(item))
    return "border-emerald-500/35 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300";
  const mode = actionExecutionMode(item);
  if (mode === "blocked")
    return "border-amber-500/35 bg-amber-500/10 text-amber-800 dark:text-amber-300";
  if (mode === "execute" || mode === "inline")
    return "border-emerald-500/35 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300";
  if (isOverdueAction(item, new Date())) {
    return "border-red-500/35 bg-red-500/10 text-red-700 dark:text-red-300";
  }
  if (mode === "decision")
    return "border-sky-500/35 bg-sky-500/10 text-sky-700 dark:text-sky-300";
  return "border-border bg-muted text-muted-foreground";
}

function evidenceLabel(value?: string | null): string {
  if (value === "full_evidence") return "полное";
  if (value === "partial_evidence") return "частичное";
  if (value === "read_only_signal") return "только просмотр";
  return "нет";
}

function stepStatusLabel(step: ActionCenterSolveMapStep): string {
  if (step.status === "waiting_for_data") return "ждёт данных";
  if (step.status === "blocked") return "заблокировано";
  if (step.status === "done") return "готово";
  return "можно делать";
}

function solveProgress(item: ActionCenterItem): {
  total: number;
  done: number;
  percent: number;
} {
  const steps = solveSteps(item);
  const total = steps.length || 1;
  const done = steps.filter(stepDone).length;
  return {
    total,
    done,
    percent: Math.round((done / total) * 100),
  };
}

type ProblemGroupKey =
  | "manual_tasks"
  | "data_blockers"
  | "profitability"
  | "price"
  | "stock"
  | "ads_promo"
  | "card_quality"
  | "reputation"
  | "system_checks"
  | "other";

type ProblemGroupSummary = {
  key: ProblemGroupKey;
  title: string;
  subtitle: string;
  actionLabel: string;
  icon: React.ReactNode;
  tone: string;
  items: ActionCenterItem[];
  open: number;
  closed: number;
  urgent: number;
  blockers: number;
  actionable: number;
  execution: ActionExecutionSummary;
  money: number;
  progress: number;
  topCodes: Array<{ code: string; label: string; count: number }>;
};

type ActionExecutionMode =
  | "execute"
  | "inline"
  | "decision"
  | "manual"
  | "blocked"
  | "signal";

type ActionExecutionSummary = Record<ActionExecutionMode, number>;

type ActionBusinessCase = {
  key: string;
  title: string;
  objectLabel: string;
  mainItem: ActionCenterItem;
  items: ActionCenterItem[];
  groupKey: ProblemGroupKey;
  count: number;
  money: number;
  rawSignalMoney: number;
  urgent: boolean;
  blocker: boolean;
  execution: ActionExecutionSummary;
  topCodes: Array<{ code: string; label: string; count: number }>;
};

type ProblemGroupMoneyOverrides = {
  missingCostRevenue?: number | null;
};

const PROBLEM_GROUP_ORDER: ProblemGroupKey[] = [
  "data_blockers",
  "profitability",
  "stock",
  "price",
  "ads_promo",
  "manual_tasks",
  "reputation",
  "card_quality",
  "system_checks",
  "other",
];

const PROBLEM_GROUP_BUSINESS_RANK: Record<ProblemGroupKey, number> = {
  data_blockers: 0,
  profitability: 1,
  stock: 2,
  price: 3,
  ads_promo: 4,
  manual_tasks: 5,
  reputation: 6,
  card_quality: 7,
  system_checks: 8,
  other: 9,
};

function problemGroupBusinessRank(key: ProblemGroupKey): number {
  return PROBLEM_GROUP_BUSINESS_RANK[key] ?? 99;
}

function actionBusinessPriorityRank(item: ActionCenterItem): number {
  const groupRank = problemGroupBusinessRank(problemGroupKey(item)) * 1000;
  const mode = actionExecutionMode(item);
  const modeRank =
    mode === "inline"
      ? 0
      : mode === "execute"
        ? 1
        : mode === "blocked"
          ? 2
          : mode === "decision"
            ? 3
            : mode === "manual"
              ? 4
              : 5;
  const urgentRank = isUrgentAction(item) ? 0 : 50;
  const contentPenalty = isContentQualityOpportunityAction(item) ? 250 : 0;
  return groupRank + modeRank * 10 + urgentRank + contentPenalty;
}

function sortByBusinessPriority(items: ActionCenterItem[]): ActionCenterItem[] {
  return [...items].sort((left, right) => {
    const rankDelta =
      actionBusinessPriorityRank(left) - actionBusinessPriorityRank(right);
    if (rankDelta) return rankDelta;
    const moneyDelta =
      moneyFromUnknown(right.money_impact_amount) -
      moneyFromUnknown(left.money_impact_amount);
    if (moneyDelta) return moneyDelta;
    return priorityRank(left) - priorityRank(right);
  });
}

function normalizeProblemGroupKey(value: unknown): ProblemGroupKey | null {
  const key = norm(value);
  return PROBLEM_GROUP_ORDER.includes(key as ProblemGroupKey)
    ? (key as ProblemGroupKey)
    : null;
}

const PROBLEM_GROUP_CONFIG: Record<
  ProblemGroupKey,
  {
    title: string;
    subtitle: string;
    actionLabel: string;
    tone: string;
    icon: React.ReactNode;
  }
> = {
  manual_tasks: {
    title: "Ручные задачи",
    subtitle:
      "Созданные оператором задачи по выбранным товарам, срокам и ответственным.",
    actionLabel: "Открыть задачи",
    tone: "border-teal-500/35 bg-teal-500/5",
    icon: <ListChecks className="h-4 w-4" />,
  },
  data_blockers: {
    title: "Данные и себестоимость",
    subtitle:
      "Сначала закрываем блокеры: себестоимость, SKU, расходы, синхронизации.",
    actionLabel: "Исправлять данные",
    tone: "border-amber-500/35 bg-amber-500/5",
    icon: <Database className="h-4 w-4" />,
  },
  profitability: {
    title: "Прибыль и маржа",
    subtitle: "Товары в минус, низкая маржа и риск потери денег.",
    actionLabel: "Разобрать прибыль",
    tone: "border-red-500/35 bg-red-500/5",
    icon: <TrendingDown className="h-4 w-4" />,
  },
  price: {
    title: "Цена и скидки",
    subtitle: "Безопасная цена, скидки и проверка перед изменениями.",
    actionLabel: "Проверить цены",
    tone: "border-sky-500/35 bg-sky-500/5",
    icon: <Gauge className="h-4 w-4" />,
  },
  stock: {
    title: "Остатки и поставки",
    subtitle: "Пересток, дефицит, быстрый расход и план пополнения.",
    actionLabel: "Разобрать остатки",
    tone: "border-cyan-500/35 bg-cyan-500/5",
    icon: <PackageSearch className="h-4 w-4" />,
  },
  ads_promo: {
    title: "Реклама и продвижение",
    subtitle: "Кампании, ставки и бюджеты, которые влияют на прибыль.",
    actionLabel: "Настроить рекламу",
    tone: "border-violet-500/35 bg-violet-500/5",
    icon: <BarChart3 className="h-4 w-4" />,
  },
  card_quality: {
    title: "Карточки товаров",
    subtitle: "Контент, фото, характеристики и качество карточки.",
    actionLabel: "Улучшить карточки",
    tone: "border-emerald-500/35 bg-emerald-500/5",
    icon: <FileText className="h-4 w-4" />,
  },
  reputation: {
    title: "Отзывы и вопросы",
    subtitle: "Негативные отзывы, вопросы покупателей и рейтинг товара.",
    actionLabel: "Ответить покупателям",
    tone: "border-pink-500/35 bg-pink-500/5",
    icon: <MessageSquare className="h-4 w-4" />,
  },
  system_checks: {
    title: "Сверки системы",
    subtitle: "Расхождения в данных, которые нужно перепроверить.",
    actionLabel: "Проверить систему",
    tone: "border-slate-500/35 bg-slate-500/5",
    icon: <ShieldCheck className="h-4 w-4" />,
  },
  other: {
    title: "Прочее",
    subtitle: "Редкие задачи, которые не попали в основные группы.",
    actionLabel: "Разобрать",
    tone: "border-border bg-muted/20",
    icon: <ListChecks className="h-4 w-4" />,
  },
};

const TASK_DOMAIN_CATALOG: Record<
  ProblemGroupKey,
  {
    direction: string;
    short: string;
    taskTypes: string[];
    workflow: string[];
    doneSignal: string;
  }
> = {
  manual_tasks: {
    direction: "Операционные поручения",
    short: "Ручные задачи по товарам, срокам и исполнителям.",
    taskTypes: [
      "изменить название",
      "проверить фото",
      "обновить карточку",
      "ручная проверка цены",
    ],
    workflow: ["выбрать товары", "дать результат", "назначить срок"],
    doneSignal: "исполнитель отметил задачу выполненной",
  },
  data_blockers: {
    direction: "Финансы и данные",
    short:
      "Блокеры расчёта прибыли: себестоимость, SKU, расходы, синхронизации.",
    taskTypes: [
      "заполнить себестоимость",
      "связать SKU",
      "обновить связь размера",
      "разнести расход",
      "обновить источник",
    ],
    workflow: ["найти строку", "исправить здесь", "пересчитать"],
    doneSignal: "прибыль и отчёты пересчитались на свежих данных",
  },
  profitability: {
    direction: "Финансы",
    short: "Минусовая экономика, низкая маржа и риск потери денег.",
    taskTypes: [
      "товар в минус",
      "низкая маржа",
      "промо съело прибыль",
      "реклама дороже прибыли",
    ],
    workflow: ["проверить факты", "убрать причину", "перепроверить маржу"],
    doneSignal: "товар больше не уходит в минус или есть ручное решение",
  },
  price: {
    direction: "Цена и скидки",
    short: "Безопасная цена, скидки и изменения после проверки.",
    taskTypes: [
      "проверить цену WB",
      "поднять до безопасной",
      "убрать опасную скидку",
      "проверить промо",
    ],
    workflow: ["сверить цену", "посчитать безопасную", "отправить на проверку"],
    doneSignal: "цена не ломает минимальную безопасную маржу",
  },
  stock: {
    direction: "Логистика и склад",
    short: "Дефицит, пересток, медленные продажи и план пополнения.",
    taskTypes: [
      "риск out-of-stock",
      "пересток",
      "низкая оборачиваемость",
      "план поставки",
      "не дозаказывать",
      "защитить остаток",
    ],
    workflow: [
      "оценить остаток",
      "выбрать склад/поставку",
      "проверить динамику",
    ],
    doneSignal: "есть план поставки или безопасный план распродажи",
  },
  ads_promo: {
    direction: "Продвижение",
    short: "Реклама, ставки, бюджеты и промо, которые влияют на прибыль.",
    taskTypes: [
      "снизить ставку",
      "остановить кампанию",
      "проверить DRR",
      "проверить промо",
    ],
    workflow: [
      "найти кампанию",
      "поменять ставку/бюджет",
      "проверить результат",
    ],
    doneSignal: "расходы не перекрывают прибыль",
  },
  card_quality: {
    direction: "Контент",
    short: "Название, описание, характеристики, фото и качество карточки.",
    taskTypes: [
      "добавить название",
      "заполнить характеристики",
      "улучшить фото",
      "исправить описание",
    ],
    workflow: ["открыть карточку", "исправить поле", "перепроверить"],
    doneSignal: "карточка проходит проверку качества",
  },
  reputation: {
    direction: "Отзывы и вопросы",
    short: "Негативные отзывы, вопросы покупателей и рейтинг товара.",
    taskTypes: [
      "ответить на отзыв",
      "ответить на вопрос",
      "разобрать негатив",
      "проверить рейтинг",
    ],
    workflow: ["прочитать отзыв", "ответить или назначить", "перепроверить"],
    doneSignal:
      "ответ опубликован или причина негативного рейтинга взята в работу",
  },
  system_checks: {
    direction: "Контроль",
    short: "Расхождения сверок и качество данных.",
    taskTypes: [
      "финальная сверка",
      "продажа без финансов",
      "финансы без продажи",
      "ошибка синка",
    ],
    workflow: ["понять источник", "обновить данные", "перепроверить"],
    doneSignal: "контрольная сверка больше не показывает расхождение",
  },
  other: {
    direction: "Разбор",
    short: "Редкие задачи, которые ещё не вошли в основные направления.",
    taskTypes: ["проверить причину", "назначить владельца", "закрыть вручную"],
    workflow: ["понять задачу", "решить или назначить", "закрыть"],
    doneSignal: "есть понятный итог задачи",
  },
};

type ScenarioCoverageStatus = "live" | "partial" | "missing";
type ScenarioCoverageMode = "platform" | "review" | "manual" | "planned";

type V1ScenarioCoverageItem = {
  id: string;
  group: ProblemGroupKey;
  title: string;
  status: ScenarioCoverageStatus;
  mode: ScenarioCoverageMode;
  codes: string[];
};

const ACTION_CENTER_V1_SCENARIO_CATALOG: V1ScenarioCoverageItem[] = [
  {
    id: "data_sync_stale",
    group: "data_blockers",
    title: "Источник данных устарел или не загрузился",
    status: "partial",
    mode: "manual",
    codes: ["sync_failed", "import_failed", "source_stale"],
  },
  {
    id: "missing_cost",
    group: "data_blockers",
    title: "Не хватает себестоимости",
    status: "live",
    mode: "platform",
    codes: [
      "missing_cost_blocks_profit",
      "missing_manual_cost",
      "supplier_cost_coverage_below_threshold",
      "fix_cost_trust",
    ],
  },
  {
    id: "conflicting_cost",
    group: "data_blockers",
    title: "Себестоимость конфликтует или неоднозначна",
    status: "partial",
    mode: "platform",
    codes: ["cost_conflict", "cost_ambiguous", "cost_fix"],
  },
  {
    id: "sku_unmapped",
    group: "data_blockers",
    title: "SKU, баркод или размер не сопоставлен",
    status: "live",
    mode: "platform",
    codes: ["unmatched_sku", "missing_chrt_id", "sku_mapping"],
  },
  {
    id: "finance_sales_mismatch",
    group: "system_checks",
    title: "Продажи, заказы и финальный отчёт не сходятся",
    status: "partial",
    mode: "manual",
    codes: [
      "finance_reconciliation_mismatch",
      "sale_without_finance",
      "finance_without_sale",
      "order_without_sale_or_return",
    ],
  },
  {
    id: "ads_spend_not_linked",
    group: "data_blockers",
    title: "Рекламный расход не привязан к товару",
    status: "partial",
    mode: "manual",
    codes: ["ad_spend_without_sku", "ads_spend_not_linked"],
  },
  {
    id: "negative_unit_profit",
    group: "profitability",
    title: "Товар продаётся в минус",
    status: "live",
    mode: "review",
    codes: ["negative_unit_profit"],
  },
  {
    id: "low_margin",
    group: "profitability",
    title: "Маржа ниже безопасного минимума",
    status: "live",
    mode: "review",
    codes: ["price_below_safe_margin"],
  },
  {
    id: "profit_dropped_wow",
    group: "profitability",
    title: "Прибыль резко упала к прошлому периоду",
    status: "missing",
    mode: "planned",
    codes: ["profit_dropped_wow", "profit_drop_period"],
  },
  {
    id: "commission_increase_profit_drop",
    group: "profitability",
    title: "Комиссия выросла и съела прибыль",
    status: "missing",
    mode: "planned",
    codes: ["commission_increase_profit_drop"],
  },
  {
    id: "logistics_storage_profit_drop",
    group: "profitability",
    title: "Логистика или хранение ухудшили прибыль",
    status: "partial",
    mode: "manual",
    codes: ["storage_cost_pressure", "logistics_profit_drop"],
  },
  {
    id: "returns_buyout_unprofitable",
    group: "profitability",
    title: "Возвраты или выкуп делают товар невыгодным",
    status: "partial",
    mode: "manual",
    codes: ["high_return_rate", "buyout_drop_unprofitable"],
  },
  {
    id: "ads_made_unprofitable",
    group: "profitability",
    title: "Реклама сделала карточку убыточной",
    status: "live",
    mode: "review",
    codes: ["ads_spend_without_profit"],
  },
  {
    id: "promo_unsafe_profitability",
    group: "profitability",
    title: "Промо или скидка ломает экономику",
    status: "live",
    mode: "review",
    codes: ["promo_not_profitable"],
  },
  {
    id: "stockout_forecast",
    group: "stock",
    title: "Скоро закончится товар",
    status: "live",
    mode: "manual",
    codes: ["stockout_risk_14d", "fast_stock_depletion", "low_stock_risk"],
  },
  {
    id: "high_demand_low_stock",
    group: "stock",
    title: "Высокий спрос при низком остатке",
    status: "live",
    mode: "review",
    codes: ["raise_price_possible_high_demand"],
  },
  {
    id: "sales_no_confirmed_stock",
    group: "stock",
    title: "Продажи есть, подтверждённого остатка нет",
    status: "live",
    mode: "manual",
    codes: ["stockout_now_with_recent_orders"],
  },
  {
    id: "overstock",
    group: "stock",
    title: "Пересток и замороженные деньги",
    status: "live",
    mode: "manual",
    codes: ["overstock_slow_moving", "storage_cost_pressure"],
  },
  {
    id: "dead_stock",
    group: "stock",
    title: "Остаток лежит без продаж",
    status: "live",
    mode: "manual",
    codes: ["dead_stock"],
  },
  {
    id: "stock_no_sales",
    group: "stock",
    title: "Есть остаток, но продаж нет",
    status: "partial",
    mode: "manual",
    codes: ["dead_stock", "no_sales_with_views"],
  },
  {
    id: "do_not_reorder",
    group: "stock",
    title: "Не дозаказывать слабую карточку",
    status: "partial",
    mode: "manual",
    codes: ["do_not_reorder", "no_sales_with_views"],
  },
  {
    id: "regional_distribution",
    group: "stock",
    title: "Неправильное распределение по регионам",
    status: "missing",
    mode: "planned",
    codes: ["regional_distribution_gap"],
  },
  {
    id: "size_color_imbalance",
    group: "stock",
    title: "Дисбаланс цветов или размеров",
    status: "missing",
    mode: "planned",
    codes: ["size_color_imbalance"],
  },
  {
    id: "price_below_safe_min",
    group: "price",
    title: "Цена ниже безопасного минимума",
    status: "live",
    mode: "review",
    codes: ["price_below_safe_margin"],
  },
  {
    id: "raise_price_low_stock",
    group: "price",
    title: "Поднять цену при высоком спросе и низком остатке",
    status: "live",
    mode: "review",
    codes: ["raise_price_possible_high_demand"],
  },
  {
    id: "high_price_conversion_drop",
    group: "price",
    title: "Цена или оффер просадили конверсию",
    status: "live",
    mode: "review",
    codes: ["price_offer_blocks_conversion"],
  },
  {
    id: "promo_unsafe_price",
    group: "price",
    title: "Промо небезопасно для маржи",
    status: "live",
    mode: "review",
    codes: ["promo_not_profitable"],
  },
  {
    id: "wrong_discount_ladder",
    group: "price",
    title: "Базовая цена или скидочная лестница некорректна",
    status: "missing",
    mode: "planned",
    codes: ["wrong_discount_ladder"],
  },
  {
    id: "post_price_change_sales_worse",
    group: "price",
    title: "После изменения цены продажи ухудшились",
    status: "missing",
    mode: "planned",
    codes: ["post_price_change_sales_worse"],
  },
  {
    id: "ad_spend_no_orders",
    group: "ads_promo",
    title: "Реклама тратит деньги без заказов",
    status: "live",
    mode: "review",
    codes: ["ads_spend_no_orders"],
  },
  {
    id: "ads_profit_negative",
    group: "ads_promo",
    title: "Реклама перекрывает прибыль",
    status: "live",
    mode: "review",
    codes: ["ads_spend_without_profit"],
  },
  {
    id: "high_ad_drr",
    group: "ads_promo",
    title: "ДРР выше безопасного порога",
    status: "live",
    mode: "review",
    codes: ["high_ad_drr"],
  },
  {
    id: "high_ad_cpo",
    group: "ads_promo",
    title: "CPO слишком высокий",
    status: "live",
    mode: "review",
    codes: ["high_ad_cpo"],
  },
  {
    id: "low_ads_ctr",
    group: "ads_promo",
    title: "CTR рекламы слишком низкий",
    status: "live",
    mode: "manual",
    codes: ["low_ads_ctr"],
  },
  {
    id: "ads_near_stockout",
    group: "ads_promo",
    title: "Реклама ведёт трафик на почти пустой остаток",
    status: "live",
    mode: "review",
    codes: ["ads_stockout_risk"],
  },
  {
    id: "profitable_campaign_underfunded",
    group: "ads_promo",
    title: "Прибыльная кампания недофинансирована",
    status: "missing",
    mode: "planned",
    codes: ["profitable_campaign_underfunded"],
  },
  {
    id: "views_traffic_drop",
    group: "card_quality",
    title: "Просмотры или трафик резко упали",
    status: "missing",
    mode: "planned",
    codes: ["views_traffic_drop"],
  },
  {
    id: "search_card_ctr_drop",
    group: "card_quality",
    title: "CTR поиска или карточки упал",
    status: "partial",
    mode: "manual",
    codes: ["low_ads_ctr", "search_card_ctr_drop"],
  },
  {
    id: "add_to_cart_conversion_drop",
    group: "card_quality",
    title: "Конверсия в корзину упала",
    status: "missing",
    mode: "planned",
    codes: ["add_to_cart_conversion_drop"],
  },
  {
    id: "cart_to_order_drop",
    group: "card_quality",
    title: "Конверсия из корзины в заказ упала",
    status: "missing",
    mode: "planned",
    codes: ["cart_to_order_drop"],
  },
  {
    id: "buyout_down_returns_up",
    group: "card_quality",
    title: "Выкуп падает или возвраты растут",
    status: "partial",
    mode: "manual",
    codes: ["high_return_rate", "buyout_down_returns_up"],
  },
  {
    id: "missing_card_content",
    group: "card_quality",
    title: "Не заполнены title, описание или обязательные характеристики",
    status: "live",
    mode: "platform",
    codes: [
      "card_quality_issue",
      "title_too_short",
      "no_title",
      "title_missing",
      "no_description",
      "description_missing",
      "missing_required_characteristic",
    ],
  },
  {
    id: "missing_search_queries",
    group: "card_quality",
    title: "Не хватает поисковых запросов",
    status: "missing",
    mode: "planned",
    codes: ["missing_search_queries"],
  },
  {
    id: "weak_media",
    group: "card_quality",
    title: "Слабое фото, видео или первая картинка",
    status: "partial",
    mode: "platform",
    codes: [
      "no_photos",
      "few_photos",
      "media_no_images",
      "media_too_few_images",
    ],
  },
  {
    id: "card_cannibalization",
    group: "card_quality",
    title: "Похожие карточки каннибализируют продажи",
    status: "missing",
    mode: "planned",
    codes: ["card_cannibalization"],
  },
  {
    id: "rating_drop",
    group: "reputation",
    title: "Рейтинг товара просел",
    status: "partial",
    mode: "manual",
    codes: ["low_product_rating", "rating_drop"],
  },
  {
    id: "negative_review_topic_spike",
    group: "reputation",
    title: "В негативных отзывах появился повторяющийся повод",
    status: "partial",
    mode: "manual",
    codes: ["negative_reviews_need_reply", "negative_review_topic_spike"],
  },
  {
    id: "repeated_defect_batch_size",
    group: "reputation",
    title: "Повторяется дефект по партии, цвету или размеру",
    status: "missing",
    mode: "planned",
    codes: ["repeated_defect_batch_size"],
  },
];

function problemGroupKey(item: ActionCenterItem): ProblemGroupKey {
  const source = norm(item.source_module);
  const code = norm(actionCode(item));
  const impact = norm(item.impact_type);
  const trust = norm(item.trust_state ?? item.money_trust?.state);
  const title = norm(item.title);
  const text = `${source} ${code} ${impact} ${trust} ${title}`;
  if (source === "manual" || text.includes("manual_task")) {
    return "manual_tasks";
  }
  if (
    code === "fix_cost_trust" ||
    code === "missing_chrt_id" ||
    code === "ad_spend_without_sku" ||
    impact === "data_blocker" ||
    impact === "data_blocked" ||
    trust === "blocked" ||
    source.includes("cost") ||
    text.includes("missing_cost") ||
    text.includes("manual_cost") ||
    text.includes("cost_trust") ||
    text.includes("cost_missing") ||
    text.includes("unmatched_sku") ||
    text.includes("sku_mapping") ||
    text.includes("unclassified") ||
    text.includes("expense") ||
    text.includes("blocker") ||
    text.includes("sync_failed") ||
    text.includes("import_failed")
  ) {
    return "data_blockers";
  }
  if (
    code === "price_increase_review" ||
    text.includes("price") ||
    text.includes("discount")
  ) {
    return "price";
  }
  if (
    code === "ad_pause_review" ||
    code.startsWith("ad_") ||
    code.startsWith("ads_") ||
    text.includes("ads") ||
    text.includes("promo") ||
    text.includes("ad_spend") ||
    text.includes("campaign") ||
    text.includes("bid")
  ) {
    return "ads_promo";
  }
  if (
    code === "card_content_review" ||
    text.includes("checker") ||
    text.includes("card_quality") ||
    text.includes("card_content") ||
    text.includes("content_quality") ||
    text.includes("content_review") ||
    text.includes("conversion") ||
    text.includes("views") ||
    text.includes("return_rate")
  ) {
    return "card_quality";
  }
  if (
    code === "liquidate_stock" ||
    code === "do_not_reorder" ||
    code === "protect_stock" ||
    code === "reorder" ||
    code === "stock_without_sales" ||
    code === "sales_without_stock" ||
    text.includes("stock") ||
    text.includes("overstock") ||
    text.includes("depletion") ||
    text.includes("storage") ||
    text.includes("logistics") ||
    text.includes("supply") ||
    text.includes("reorder")
  ) {
    return "stock";
  }
  if (
    text.includes("profit") ||
    text.includes("margin") ||
    text.includes("loss") ||
    text.includes("убыт") ||
    text.includes("минус") ||
    text.includes("приб")
  ) {
    return "profitability";
  }
  if (
    source.includes("reputation") ||
    source.includes("claims") ||
    code.includes("negative_review") ||
    code.includes("question") ||
    code.includes("rating") ||
    text.includes("feedback") ||
    text.includes("отзыв") ||
    text.includes("вопрос") ||
    text.includes("рейтинг")
  ) {
    return "reputation";
  }
  if (
    text.includes("reconciliation") ||
    text.includes("sale_without_finance") ||
    text.includes("finance_without_sale") ||
    impact === "system_warning"
  ) {
    return "system_checks";
  }
  return "other";
}

function isMissingCostProblem(item: ActionCenterItem): boolean {
  const text = `${norm(actionCode(item))} ${norm(item.source_module)} ${norm(item.title)} ${norm(item.reason)}`;
  return (
    text.includes("missing_cost") ||
    text.includes("cost_missing") ||
    text.includes("missing_manual_cost")
  );
}

function problemGroupMoney(
  key: ProblemGroupKey,
  items: ActionCenterItem[],
  overrides: ProblemGroupMoneyOverrides,
): number {
  const computedMoney = items.reduce(
    (sum, item) => sum + moneyFromUnknown(item.money_impact_amount),
    0,
  );
  if (
    key !== "data_blockers" ||
    overrides.missingCostRevenue == null ||
    !items.some(isMissingCostProblem)
  ) {
    return computedMoney;
  }
  const nonMissingCostMoney = items.reduce(
    (sum, item) =>
      isMissingCostProblem(item)
        ? sum
        : sum + moneyFromUnknown(item.money_impact_amount),
    0,
  );
  return nonMissingCostMoney + moneyFromUnknown(overrides.missingCostRevenue);
}

function applyActionDisplayMoney(
  items: ActionCenterItem[],
  overrides: ProblemGroupMoneyOverrides,
): ActionCenterItem[] {
  if (!overrides.missingCostRevenue) return items;
  return items.map((item) => {
    const isAggregateMissingCost =
      isMissingCostProblem(item) &&
      moneyFromUnknown(item.money_impact_amount) === 0 &&
      numberFromUnknown(item.nm_id) == null;
    if (!isAggregateMissingCost) return item;
    return {
      ...item,
      money_impact_amount: overrides.missingCostRevenue,
    };
  });
}

function buildProblemGroups(
  items: ActionCenterItem[],
  overrides: ProblemGroupMoneyOverrides = {},
): ProblemGroupSummary[] {
  return PROBLEM_GROUP_ORDER.map((key) => {
    const groupItems = items.filter((item) => problemGroupKey(item) === key);
    const open = groupItems.filter((item) => !isClosedAction(item)).length;
    const closed = groupItems.length - open;
    const urgent = groupItems.filter(
      (item) => !isClosedAction(item) && isUrgentAction(item),
    ).length;
    const blockers = groupItems.filter(
      (item) => !isClosedAction(item) && isDataBlockerAction(item),
    ).length;
    const execution = actionExecutionSummary(
      groupItems.filter((item) => !isClosedAction(item)),
    );
    const actionable = groupItems.filter(isActionable).length;
    const money = problemGroupMoney(key, groupItems, overrides);
    const counts = new Map<string, number>();
    for (const item of groupItems) {
      const code = actionCode(item) || "unknown";
      counts.set(code, (counts.get(code) ?? 0) + 1);
    }
    const topCodes = [...counts.entries()]
      .map(([code, count]) => ({ code, label: problemCodeLabel(code), count }))
      .sort((a, b) => b.count - a.count)
      .slice(0, 3);
    const cfg = PROBLEM_GROUP_CONFIG[key];
    return {
      key,
      ...cfg,
      items: sortByBusinessPriority(groupItems),
      open,
      closed,
      urgent,
      blockers,
      actionable,
      execution,
      money,
      progress: groupItems.length
        ? Math.round((closed / groupItems.length) * 100)
        : 100,
      topCodes,
    };
  })
    .filter((group) => group.items.length > 0)
    .sort((a, b) => {
      const groupRankDelta =
        problemGroupBusinessRank(a.key) - problemGroupBusinessRank(b.key);
      if (groupRankDelta) return groupRankDelta;
      if (b.urgent !== a.urgent) return b.urgent - a.urgent;
      if (b.money !== a.money) return b.money - a.money;
      if (b.open !== a.open) return b.open - a.open;
      return 0;
    });
}

function EmptyLoader() {
  return (
    <PageShell>
      <div className="space-y-4">
        <Skeleton className="h-20 w-full" />
        <div className="grid gap-4 lg:grid-cols-[360px_1fr]">
          <Skeleton className="h-[560px] w-full" />
          <Skeleton className="h-[560px] w-full" />
        </div>
      </div>
    </PageShell>
  );
}

function MetricTile({
  label,
  value,
  hint,
  icon,
  tone = "neutral",
}: {
  label: string;
  value: string | number;
  hint?: string;
  icon: React.ReactNode;
  tone?: "neutral" | "danger" | "warning" | "success" | "info";
}) {
  const toneClass =
    tone === "danger"
      ? "border-red-500/30 bg-red-500/5 text-red-950 dark:text-red-100"
      : tone === "warning"
        ? "border-amber-500/30 bg-amber-500/5 text-amber-950 dark:text-amber-100"
        : tone === "success"
          ? "border-emerald-500/30 bg-emerald-500/5 text-emerald-950 dark:text-emerald-100"
          : tone === "info"
            ? "border-sky-500/30 bg-sky-500/5 text-sky-950 dark:text-sky-100"
            : "border-border bg-card";
  const iconClass =
    tone === "danger"
      ? "bg-red-500/10 text-red-700 dark:text-red-300"
      : tone === "warning"
        ? "bg-amber-500/10 text-amber-700 dark:text-amber-300"
        : tone === "success"
          ? "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300"
          : tone === "info"
            ? "bg-sky-500/10 text-sky-700 dark:text-sky-300"
            : "bg-muted text-muted-foreground";
  return (
    <div
      className={`relative overflow-hidden rounded-md border p-4 shadow-sm ${toneClass}`}
    >
      <div
        className={`absolute inset-x-0 top-0 h-0.5 ${
          tone === "danger"
            ? "bg-red-500"
            : tone === "warning"
              ? "bg-amber-500"
              : tone === "success"
                ? "bg-emerald-500"
                : tone === "info"
                  ? "bg-sky-500"
                  : "bg-border"
        }`}
      />
      <div className="flex items-start justify-between gap-2">
        <div className="space-y-1">
          <div className="text-xs text-muted-foreground">{label}</div>
          <div className="min-w-0 break-words text-xl font-semibold leading-tight tracking-tight">
            {value}
          </div>
        </div>
        <div
          className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-md ${iconClass}`}
        >
          {icon}
        </div>
      </div>
      {hint ? (
        <div className="mt-2 text-xs text-muted-foreground">{hint}</div>
      ) : null}
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const key = norm(status);
  return (
    <Badge
      variant="outline"
      className={`text-[10px] ${STATUS_TONE[key] ?? "border-border bg-muted text-muted-foreground"}`}
    >
      {humanStatusLabel(key)}
    </Badge>
  );
}

function PriorityBadge({ item }: { item: ActionCenterItem }) {
  const priority = String(item.priority ?? item.severity ?? "P3").toUpperCase();
  return (
    <Badge
      variant="outline"
      className={`text-[10px] ${PRIORITY_TONE[priority] ?? PRIORITY_TONE.P3}`}
    >
      {priorityLabel(priority)}
    </Badge>
  );
}

function QueueItem({
  item,
  index,
  selected,
  currentUserId,
  onSelect,
}: {
  item: ActionCenterItem;
  index: number;
  selected: boolean;
  currentUserId: number | null;
  onSelect: () => void;
}) {
  const primary = primaryActionForItem(item);
  const closed = isClosedAction(item);
  const images = itemImageCandidates(item);
  return (
    <button
      type="button"
      onClick={onSelect}
      aria-current={selected ? "true" : undefined}
      className={`group relative w-full overflow-hidden rounded-md border p-3 pl-4 text-left transition-all ${
        selected
          ? "border-primary bg-background ring-2 ring-primary/15"
          : "border-border bg-card hover:border-primary/35 hover:bg-background"
      } ${closed ? "opacity-70" : ""}`}
    >
      <div
        className={`absolute inset-y-0 left-0 w-1 ${priorityRailTone(item)}`}
      />
      <div className="flex items-start gap-3">
        <div className="relative shrink-0">
          <ProductThumb
            candidates={images}
            label={problemTitle(item)}
            className="h-11 w-9"
          />
          <span className="absolute -left-1 -top-1 flex h-5 min-w-5 items-center justify-center rounded-md border bg-background px-1 text-[10px] font-semibold text-muted-foreground shadow-sm">
            {String(index + 1).padStart(2, "0")}
          </span>
        </div>
        <div className="min-w-0 flex-1 space-y-1.5">
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0">
              <div className="line-clamp-2 text-sm font-semibold leading-snug">
                {problemTitle(item)}
              </div>
              <div className="mt-1 flex flex-wrap items-center gap-1.5">
                <PriorityBadge item={item} />
                <StatusBadge status={item.status} />
                {item.nm_id ? (
                  <Badge variant="outline" className="text-[10px]">
                    nm {item.nm_id}
                  </Badge>
                ) : null}
              </div>
            </div>
            {selected ? (
              <ChevronRight className="mt-1 h-4 w-4 shrink-0 text-primary" />
            ) : null}
          </div>
          <div className="line-clamp-2 text-xs text-muted-foreground">
            {item.short_explanation ||
              item.reason ||
              item.next_step ||
              problemCodeLabel(actionCode(item))}
          </div>
          <div className="flex items-center justify-between gap-2 text-[11px]">
            <span className="truncate">
              {primary?.code ? humanActionLabel(primary.code) : "Открыть"}
            </span>
            {typeof item.money_impact_amount === "number" ? (
              <span className="shrink-0 text-muted-foreground">
                {formatMoney(Math.abs(item.money_impact_amount))}
              </span>
            ) : null}
          </div>
        </div>
      </div>
    </button>
  );
}

function StepIcon({ step }: { step: ActionCenterSolveMapStep }) {
  if (stepDone(step)) {
    return (
      <span className="flex h-7 w-7 items-center justify-center rounded-full bg-emerald-500/15 text-emerald-700 dark:text-emerald-300">
        <Check className="h-4 w-4" />
      </span>
    );
  }
  if (step.status === "waiting_for_data") {
    return (
      <span className="flex h-7 w-7 items-center justify-center rounded-full bg-amber-500/15 text-amber-700 dark:text-amber-300">
        <Database className="h-4 w-4" />
      </span>
    );
  }
  if (step.status === "blocked") {
    return (
      <span className="flex h-7 w-7 items-center justify-center rounded-full bg-red-500/15 text-red-700 dark:text-red-300">
        <Lock className="h-4 w-4" />
      </span>
    );
  }
  return (
    <span className="flex h-7 w-7 items-center justify-center rounded-full bg-sky-500/15 text-sky-700 dark:text-sky-300">
      <Play className="h-4 w-4" />
    </span>
  );
}

function WorkButton({
  href,
  label,
  variant = "default",
}: {
  href: string | null | undefined;
  label: string;
  variant?: "default" | "outline" | "secondary";
}) {
  if (!href) {
    return (
      <Button size="sm" variant={variant} disabled>
        <Lock className="h-3.5 w-3.5" />
        {label}
      </Button>
    );
  }
  if (href.startsWith("/")) {
    return (
      <Button asChild size="sm" variant={variant}>
        <Link to={href}>
          {label}
          <ArrowRight className="h-3.5 w-3.5" />
        </Link>
      </Button>
    );
  }
  return (
    <Button asChild size="sm" variant={variant}>
      <a href={href} target="_blank" rel="noreferrer">
        {label}
        <ExternalLink className="h-3.5 w-3.5" />
      </a>
    </Button>
  );
}

function TaskLifecycleActions({
  item,
  busy,
  onStatus,
  onDoneNext,
  onNext,
  showDone = true,
}: {
  item: ActionCenterItem;
  busy: boolean;
  onStatus: (
    item: ActionCenterItem,
    status: string,
    next?: boolean,
    options?: { deadline_at?: string; comment?: string },
  ) => void;
  onDoneNext: (item: ActionCenterItem) => void;
  onNext: () => void;
  showDone?: boolean;
}) {
  const mode = taskBoardModeForItem(item);
  const closed = mode !== "active" || isClosedAction(item);
  const canUpdate = item.can_update !== false;
  const inProgress = norm(item.status) === "in_progress";

  if (mode !== "active") {
    return (
      <div className="flex flex-wrap items-center gap-2 rounded-md border bg-card p-2 shadow-sm">
        <Button
          size="sm"
          variant="outline"
          className="h-9 rounded-md"
          disabled={busy || !canUpdate}
          onClick={() =>
            onStatus(item, "reopened", true, {
              comment: "Возвращено в активные задачи из Центра действий",
            })
          }
        >
          <RotateCw className="h-3.5 w-3.5" />
          Вернуть в активные
        </Button>
        <Button
          size="sm"
          variant="ghost"
          className="h-9 rounded-md"
          onClick={onNext}
        >
          Следующая
          <ArrowRight className="h-3.5 w-3.5" />
        </Button>
      </div>
    );
  }

  return (
    <div className="flex flex-wrap items-center gap-2 rounded-md border bg-card p-2 shadow-sm">
      <Button
        size="sm"
        variant="outline"
        className="h-9 rounded-md"
        disabled={closed || busy || !canUpdate || inProgress}
        onClick={() =>
          onStatus(item, "in_progress", false, {
            comment: "Взято в работу из Центра действий",
          })
        }
      >
        <Play className="h-3.5 w-3.5" />В работу
      </Button>
      {showDone ? (
        <Button
          size="sm"
          className="h-9 rounded-md shadow-sm"
          disabled={closed || busy || !canUpdate}
          onClick={() =>
            onStatus(item, "done", true, {
              deadline_at: postponeUntilIso(1),
              comment:
                "Выполнено из Центра действий. Скрыто из активной очереди до следующей ежедневной проверки.",
            })
          }
        >
          <CheckCircle2 className="h-3.5 w-3.5" />
          Готово на 1 день
        </Button>
      ) : null}
      <Popover>
        <PopoverTrigger asChild>
          <Button
            size="sm"
            variant="outline"
            className="h-9 rounded-md"
            disabled={closed || busy || !canUpdate}
          >
            <Clock3 className="h-3.5 w-3.5" />
            Отложить
            <ChevronDown className="h-3.5 w-3.5" />
          </Button>
        </PopoverTrigger>
        <PopoverContent align="start" className="w-64 p-2">
          <div className="mb-2 px-1 text-xs text-muted-foreground">
            Уберите задачу из активной очереди до нужного дня.
          </div>
          {[1, 3, 7].map((days) => (
            <Button
              key={days}
              type="button"
              variant="ghost"
              className="h-9 w-full justify-start rounded-md"
              onClick={() =>
                onStatus(item, "postponed", true, {
                  deadline_at: postponeUntilIso(days),
                  comment: `Отложено на ${days} дн. из Центра действий`,
                })
              }
            >
              На {days} {days === 1 ? "день" : days < 5 ? "дня" : "дней"}
            </Button>
          ))}
        </PopoverContent>
      </Popover>
      <Button
        size="sm"
        variant="outline"
        className="h-9 rounded-md"
        disabled={closed || busy || !canUpdate}
        onClick={() =>
          onStatus(item, "ignored", true, {
            comment: "Деактивировано как неактуальная задача",
          })
        }
      >
        <SkipForward className="h-3.5 w-3.5" />
        Неактуально
      </Button>
      <Button
        size="sm"
        variant="ghost"
        className="h-9 rounded-md"
        onClick={onNext}
      >
        Следующая
        <ArrowRight className="h-3.5 w-3.5" />
      </Button>
    </div>
  );
}

function SolveMap({ item }: { item: ActionCenterItem }) {
  const steps = solveSteps(item);
  const completed = steps.filter(stepDone).length;
  const percent = steps.length
    ? Math.round((completed / steps.length) * 100)
    : 100;
  const summary = hasCyrillicText(item.solve_map?.summary)
    ? item.solve_map?.summary
    : "Выполните шаги сверху вниз: сначала проверка, затем исправление, потом перепроверка.";
  return (
    <div className="overflow-hidden rounded-md border bg-card shadow-sm">
      <div className="border-b bg-muted/10 px-4 py-3">
        <div className="flex items-center justify-between gap-3">
          <div>
            <div className="flex items-center gap-2 text-sm font-semibold">
              <ListChecks className="h-4 w-4 text-primary" />
              Порядок решения
            </div>
            <div className="text-xs text-muted-foreground">{summary}</div>
          </div>
          <div className="min-w-[128px] text-right">
            <div className="text-sm font-semibold">
              {completed}/{steps.length}
            </div>
            <Progress value={percent} className="mt-1 h-1.5" />
          </div>
        </div>
      </div>
      <div className="divide-y">
        {steps.map((step, index) => (
          <div
            key={step.step_id ?? index}
            className="relative grid gap-3 px-4 py-3 sm:grid-cols-[32px_1fr_auto]"
          >
            {index < steps.length - 1 ? (
              <div className="absolute bottom-0 left-[31px] top-11 w-px bg-border" />
            ) : null}
            <div className="relative z-10">
              <span
                className={`flex h-7 w-7 items-center justify-center rounded-full border text-[11px] font-semibold ${
                  stepDone(step)
                    ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300"
                    : stepBlocked(step)
                      ? "border-amber-500/35 bg-amber-500/10 text-amber-800 dark:text-amber-300"
                      : "border-sky-500/30 bg-sky-500/10 text-sky-700 dark:text-sky-300"
                }`}
              >
                {index + 1}
              </span>
            </div>
            <div className="min-w-0 space-y-1">
              <div className="flex flex-wrap items-center gap-2">
                <div className="text-sm font-medium leading-tight">
                  {step.title}
                </div>
                <Badge
                  variant="outline"
                  className={`text-[10px] ${
                    stepDone(step)
                      ? "border-emerald-500/35 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300"
                      : stepBlocked(step)
                        ? "border-amber-500/35 bg-amber-500/10 text-amber-800 dark:text-amber-300"
                        : "border-sky-500/35 bg-sky-500/10 text-sky-700 dark:text-sky-300"
                  }`}
                >
                  {stepStatusLabel(step)}
                </Badge>
              </div>
              <div className="mt-1 text-xs text-muted-foreground">
                {step.description}
              </div>
              {step.blocking_reason ? (
                <div className="mt-2 rounded-md border border-amber-500/25 bg-amber-500/10 px-2 py-1.5 text-xs text-amber-800 dark:text-amber-200">
                  {step.blocking_reason}
                </div>
              ) : null}
              {step.completion_signal ? (
                <div className="text-[11px] text-muted-foreground">
                  Готово, когда:{" "}
                  <span className="font-medium text-foreground">
                    {step.completion_signal}
                  </span>
                </div>
              ) : null}
              {step.required_metrics?.length ? (
                <div className="mt-2 flex flex-wrap gap-1">
                  {step.required_metrics.slice(0, 4).map((metric) => (
                    <Badge
                      key={metric}
                      variant="secondary"
                      className="text-[10px]"
                    >
                      {humanMetricLabel(metric)}
                    </Badge>
                  ))}
                </div>
              ) : null}
            </div>
            {step.target_href ? (
              <WorkButton
                href={step.target_href}
                label={
                  step.action_code === "recheck"
                    ? "Перепроверить"
                    : step.action_label || "Открыть"
                }
                variant="outline"
              />
            ) : null}
          </div>
        ))}
      </div>
    </div>
  );
}

function DataFreshness({ item }: { item: ActionCenterItem }) {
  const freshness = item.data_freshness;
  const status = freshness?.source_status ?? "missing";
  const tone =
    status === "fresh"
      ? "border-emerald-500/35 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300"
      : status === "stale"
        ? "border-amber-500/35 bg-amber-500/10 text-amber-800 dark:text-amber-300"
        : "border-red-500/35 bg-red-500/10 text-red-700 dark:text-red-300";
  return (
    <div className="rounded-md border bg-card p-4 shadow-sm">
      <div className="mb-3 flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 text-sm font-semibold">
          <Database className="h-4 w-4" />
          Данные расчёта
        </div>
        <Badge variant="outline" className={`text-[10px] ${tone}`}>
          {status === "fresh"
            ? "свежие"
            : status === "stale"
              ? "устарели"
              : status === "not_configured"
                ? "не настроено"
                : "не хватает"}
        </Badge>
      </div>
      <div className="space-y-3 text-xs">
        <div className="rounded-md border bg-muted/25 px-3 py-2">
          <div className="text-[11px] text-muted-foreground">
            Последняя синхронизация
          </div>
          <div className="mt-0.5 font-medium">
            {compactDateTime(freshness?.last_synced_at)}
          </div>
        </div>
        <div className="rounded-md border bg-muted/25 px-3 py-2">
          <div className="text-[11px] text-muted-foreground">Источники</div>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {(freshness?.required_sources ?? []).slice(0, 8).map((source) => (
              <Badge
                key={source}
                variant="secondary"
                className="max-w-full truncate text-[10px]"
              >
                {source}
              </Badge>
            ))}
            {!(freshness?.required_sources ?? []).length ? (
              <span className="text-muted-foreground">Источник не указан</span>
            ) : null}
          </div>
        </div>
        {freshness?.blocking_sources?.length ? (
          <Alert className="border-amber-500/40 bg-amber-500/5 py-2">
            <AlertCircle className="h-4 w-4" />
            <AlertTitle className="text-xs">Нужно обновить данные</AlertTitle>
            <AlertDescription className="text-xs">
              {dataFreshnessBlockingLabel(freshness)}
            </AlertDescription>
          </Alert>
        ) : null}
      </div>
    </div>
  );
}

function EvidencePanel({ item }: { item: ActionCenterItem }) {
  const ledger = item.evidence_ledger;
  const facts = ledger?.input_facts ?? [];
  const refs = ledger?.source_references ?? [];
  const formulaText = readableFormulaText(
    ledger?.formula_human ||
      ledger?.formula_id ||
      item.reason ||
      item.short_explanation ||
      "",
  );
  return (
    <div className="rounded-md border bg-card p-4 shadow-sm">
      <div className="mb-3 flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 text-sm font-semibold">
          <FileText className="h-4 w-4" />
          Почему найдено
        </div>
        <Badge variant="outline" className="text-[10px]">
          доказательства: {evidenceLabel(item.evidence_state)}
        </Badge>
      </div>
      <div className="space-y-3">
        <div
          className={`rounded-md border px-3 py-2 ${modulePanelTone(item.source_module)}`}
        >
          <div className="mb-1 flex items-center gap-1.5 text-[11px] font-medium uppercase text-muted-foreground">
            <Eye className="h-3 w-3" />
            Расчёт
          </div>
          <div className="text-sm leading-relaxed">
            {formulaText ||
              "Формула пока не передана; показаны причина, факты и доступные источники расчёта."}
          </div>
        </div>
        <div className="grid gap-2 sm:grid-cols-2">
          <Fact
            label="Тип проблемы"
            value={problemCodeLabel(actionCode(item))}
            sub={actionCode(item) || null}
          />
          <Fact
            label="Основное действие"
            value={humanActionLabel(primaryActionForItem(item)?.code)}
          />
          <Fact label="Модуль" value={sourceModuleLabel(item.source_module)} />
          <Fact
            label="Данные"
            value={problemTrustLabel(
              String(
                item.trust_state ?? item.money_trust?.state ?? "provisional",
              ),
            )}
          />
        </div>
        {facts.length ? (
          <div className="space-y-2">
            <div className="text-xs font-medium text-muted-foreground">
              Факты расчёта
            </div>
            <div className="grid gap-2 md:grid-cols-2">
              {facts.slice(0, 6).map((fact, idx) => (
                <Fact
                  key={`${fact.label ?? fact.metric_code ?? idx}`}
                  label={humanMetricLabel(
                    fact.label || fact.metric_code || `Факт ${idx + 1}`,
                  )}
                  value={formatFactValue(fact)}
                  sub={
                    fact.source_table ||
                    fact.source_endpoint ||
                    fact.source ||
                    null
                  }
                />
              ))}
            </div>
          </div>
        ) : null}
        {refs.length ? (
          <div className="space-y-2">
            <div className="text-xs font-medium text-muted-foreground">
              Источники расчёта
            </div>
            <div className="flex flex-wrap gap-1.5">
              {refs.slice(0, 8).map((ref, idx) => (
                <Badge key={idx} variant="outline" className="text-[10px]">
                  {ref.source_table ||
                    ref.table ||
                    ref.source_endpoint ||
                    `source ${idx + 1}`}
                </Badge>
              ))}
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}

function readableFormulaText(value: unknown): string {
  const raw = String(value ?? "").trim();
  if (!raw) return "";
  const dataFixMatch = raw.match(
    /^Open Data Fix issue `([^`]+)` maps to dynamic problem `([^`]+)`\.$/i,
  );
  if (dataFixMatch) {
    return `Открытая проверка данных «${problemCodeLabel(dataFixMatch[1])}» создала задачу «${problemCodeLabel(dataFixMatch[2])}».`;
  }
  return raw;
}

function Fact({
  label,
  value,
  sub,
}: {
  label: string;
  value: string;
  sub?: string | null;
}) {
  return (
    <div className="min-w-0 rounded-md border bg-muted/20 px-3 py-2">
      <div className="text-[11px] text-muted-foreground">{label}</div>
      <div className="mt-0.5 break-words text-sm font-semibold leading-snug">
        {value}
      </div>
      {sub ? (
        <div className="mt-1 truncate text-[10px] text-muted-foreground">
          {sub}
        </div>
      ) : null}
    </div>
  );
}

function SignalCell({
  label,
  value,
  icon,
  tone = "neutral",
  sub,
}: {
  label: string;
  value: string;
  icon: React.ReactNode;
  tone?: "neutral" | "danger" | "warning" | "success" | "info";
  sub?: string | null;
}) {
  const toneClass =
    tone === "danger"
      ? "bg-red-500/10 text-red-700 dark:text-red-300"
      : tone === "warning"
        ? "bg-amber-500/10 text-amber-700 dark:text-amber-300"
        : tone === "success"
          ? "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300"
          : tone === "info"
            ? "bg-sky-500/10 text-sky-700 dark:text-sky-300"
            : "bg-muted text-muted-foreground";
  return (
    <div className="min-w-0 rounded-md border bg-background px-3 py-2">
      <div className="flex items-start gap-2">
        <span
          className={`mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-md ${toneClass}`}
        >
          {icon}
        </span>
        <div className="min-w-0">
          <div className="text-[11px] text-muted-foreground">{label}</div>
          <div className="break-words text-sm font-semibold leading-snug">
            {value}
          </div>
        </div>
      </div>
      {sub ? (
        <div className="mt-1 break-words pl-8 text-[11px] text-muted-foreground">
          {sub}
        </div>
      ) : null}
    </div>
  );
}

function decisionMetricValue(item: ActionCenterItem): number | null {
  const payload = itemPayload(item);
  return (
    numberFromUnknown(item.money_impact_amount) ??
    numberFromUnknown(item.expected_effect_amount) ??
    numberFromUnknown(item.expected_impact_amount) ??
    numberFromUnknown(payload.money_impact_amount) ??
    numberFromUnknown(payload.primary_amount) ??
    numberFromUnknown(payload.expected_cash_release) ??
    numberFromUnknown(payload.affected_stock_value) ??
    numberFromUnknown(payload.protected_revenue)
  );
}

function actionDecisionPlan(item: ActionCenterItem): {
  title: string;
  subtitle: string;
  objective: string;
  steps: Array<{ title: string; description: string; done: string }>;
  outcomes: string[];
  caution: string;
  workLabel: string;
  doneComment: string;
  tone: "neutral" | "danger" | "warning" | "success" | "info";
  icon: React.ReactNode;
} {
  const code = norm(actionCode(item));
  const subject = objectLabel(item);
  if (["ad_pause_review", "ads_spend_without_profit"].includes(code)) {
    return {
      title: "Что сделать: рекламная утечка денег",
      subtitle:
        "Реклама не должна тратить бюджет, пока чистая прибыль по товару не стала положительной.",
      objective:
        "Найдите кампании, которые ведут на этот nm, и временно ограничьте расход: пауза, снижение ставки или бюджета. Если причина в цене/карточке, создайте или выполните соседнюю задачу перед усилением рекламы.",
      steps: [
        {
          title: "Найти кампании по товару",
          description:
            "Откройте рекламу и отфильтруйте кампании по nm, артикулу или названию товара. Если campaign_id нет в задаче, ищите именно по товару.",
          done: "Понятно, какие кампании тратят деньги на этот товар",
        },
        {
          title: "Остановить утечку",
          description:
            "Если чистая прибыль не положительная, поставьте кампанию на паузу или снизьте ставку/дневной бюджет до безопасного уровня. Не усиливайте рекламу, пока цена, маржа и карточка не проверены.",
          done: "Расход ограничен или зафиксировано, что активной кампании нет",
        },
        {
          title: "Перепроверить после синка рекламы",
          description:
            "После обновления рекламной статистики запустите пересчёт. Закрывайте задачу только если расход больше не съедает прибыль.",
          done: "DRR/расход и прибыль пересчитаны",
        },
      ],
      outcomes: [
        "Кампании по nm поставлены на паузу",
        "Ставка или бюджет снижены",
        "Активной кампании не найдено",
        "Нужна правка цены или карточки перед рекламой",
      ],
      caution:
        "Автоматическое изменение рекламы отсюда пока не выполняется. Зафиксируйте решение и запустите повторную проверку.",
      workLabel: "Открыть рекламу по товару",
      doneComment:
        "Рекламная утечка разобрана: кампания найдена, расход ограничен или зафиксирован следующий шаг.",
      tone: "danger",
      icon: <BarChart3 className="h-4 w-4" />,
    };
  }
  if (code === "price_increase_review" || code.includes("price")) {
    return {
      title: "Что сделать: безопасная цена",
      subtitle:
        "Цена меняется только после проверки себестоимости, комиссии, логистики, рекламы и минимальной маржи.",
      objective:
        "Сверьте текущую цену с безопасной. Если расчёт доверенный, подготовьте изменение цены или скидки. Если данных по себестоимости/комиссии не хватает, сначала закройте data blocker.",
      steps: [
        {
          title: "Проверить основу расчёта",
          description:
            "Сравните цену WB, скидку, себестоимость, комиссию, логистику, рекламу и промо. Не меняйте цену, если ключевые расходы предварительные.",
          done: "Понятно, можно ли доверять безопасной цене",
        },
        {
          title: "Выбрать ценовое действие",
          description:
            "Поднять цену, уменьшить скидку или не менять цену, если рынок/данные не подтверждают действие. Изменение должно сохранять минимальную безопасную маржу.",
          done: "Выбран безопасный ценовой сценарий",
        },
        {
          title: "Пересчитать прибыль",
          description:
            "После изменения цены или отказа от изменения запустите перепроверку, чтобы обновить маржу и связанные задачи.",
          done: "Маржа пересчитана",
        },
      ],
      outcomes: [
        "Цена поднята до безопасного уровня",
        "Скидка/промо уменьшены",
        "Сначала нужна себестоимость или комиссия",
        "Изменение цены отклонено вручную",
      ],
      caution:
        "Автоматическая запись цены в WB не включена. Экран даёт safe review и фиксирует решение оператора.",
      workLabel: "Открыть цену товара",
      doneComment:
        "Ценовой review выполнен: безопасная цена проверена и выбран сценарий.",
      tone: "warning",
      icon: <Gauge className="h-4 w-4" />,
    };
  }
  if (
    [
      "missing_cost_blocks_profit",
      "missing_manual_cost",
      "supplier_cost_coverage_below_threshold",
      "manual_cost_unresolved_sku",
      "manual_cost_ambiguous_match",
      "fix_cost_trust",
    ].includes(code)
  ) {
    return {
      title: "Что сделать: себестоимость",
      subtitle:
        "Пока себестоимость не заполнена, прибыль и окупаемость считаются ненадёжно.",
      objective:
        "Найдите строку товара, внесите цену закупки и прочие расходы. Если прочих расходов нет, укажите 0. После сохранения система перейдёт к следующей строке.",
      steps: [
        {
          title: "Понять задачу",
          description:
            "Проверьте товар, SKU, размер и период, по которому нет себестоимости.",
          done: "Понятно, по какому товару нужны цифры",
        },
        {
          title: "Выполнить или назначить",
          description:
            "Заполните себестоимость здесь или назначьте задачу ответственному, если цифр пока нет.",
          done: "Себестоимость внесена или есть ответственный",
        },
        {
          title: "Перепроверить",
          description:
            "После изменения данных запустите пересчёт и закройте задачу.",
          done: "Прибыль пересчитана",
        },
      ],
      outcomes: [
        "Себестоимость заполнена",
        "Расходы за единицу заполнены",
        "Назначен ответственный",
        "Строка пропущена до уточнения",
      ],
      caution:
        "Перед сохранением проверьте, что сумма относится к выбранному товару и размеру.",
      workLabel: "Заполнить себестоимость",
      doneComment:
        "Себестоимость заполнена или передана ответственному, задача продвинута дальше.",
      tone: "warning",
      icon: <Database className="h-4 w-4" />,
    };
  }
  if (
    [
      "liquidate_stock",
      "do_not_reorder",
      "stock_without_sales",
      "dead_stock",
      "overstock_slow_moving",
    ].includes(code)
  ) {
    return {
      title: "Что сделать: зависший остаток",
      subtitle:
        "Сначала защищаем деньги: не закупать лишнее и выбрать безопасный сценарий разгрузки.",
      objective:
        "Проверьте остаток, продажи, маржу и карточку. Затем выберите бизнес-решение: не дозаказывать, распродать безопасной скидкой, улучшить карточку или запустить аккуратное промо.",
      steps: [
        {
          title: "Понять причину остатка",
          description:
            "Сверьте количество, дни без продаж, скорость продаж, цену, карточку, отзывы и рекламу. Не запускайте скидку без проверки маржи.",
          done: "Понятно, почему остаток не движется",
        },
        {
          title: "Выбрать действие по остатку",
          description:
            "Для убыточного SKU остановите повторную закупку. Для перестока выберите распродажу, промо, комплект, правку карточки или ручную задачу ответственному.",
          done: "Выбран план, который не создаёт новый убыток",
        },
        {
          title: "Проверить динамику",
          description:
            "После продаж, промо или правки карточки пересчитайте остатки. Закрывайте задачу, когда план зафиксирован или остаток начал двигаться.",
          done: "План по остатку записан",
        },
      ],
      outcomes: [
        "Не дозаказывать этот SKU",
        "Запустить безопасную распродажу/промо",
        "Исправить карточку перед скидкой",
        "Создать ручную задачу закупкам/контенту",
      ],
      caution:
        "StockOps write пока не настроен. Платформа показывает решение и фиксирует его в очереди, а не создаёт поставку/промо в WB автоматически.",
      workLabel: "Открыть остатки/товар",
      doneComment:
        "Решение по остатку принято: повторная закупка, распродажа или следующий ответственный зафиксированы.",
      tone: "info",
      icon: <PackageSearch className="h-4 w-4" />,
    };
  }
  if (["reorder", "protect_stock", "sales_without_stock"].includes(code)) {
    return {
      title: "Что сделать: пополнение или защита остатка",
      subtitle:
        "Товар может закончиться или продажи идут без подтверждённого остатка.",
      objective:
        "Проверьте свежесть остатков, товар в пути, скорость продаж и ближайшую поставку. Если остатка не хватит, создайте план пополнения или временно снизьте спрос.",
      steps: [
        {
          title: "Проверить доступность",
          description:
            "Сверьте текущий остаток, продажи за последние дни, товар в пути и дату обновления stock sync.",
          done: "Понятно, когда товар закончится",
        },
        {
          title: "Запланировать действие",
          description:
            "Создайте план поставки, защитите остаток от лишней рекламы/промо или назначьте ответственному проверить склад.",
          done: "Есть план поставки или ограничение спроса",
        },
        {
          title: "Перепроверить после обновления",
          description: "После синка остатков или поставки пересчитайте задачу.",
          done: "Риск дефицита снят или взят в работу",
        },
      ],
      outcomes: [
        "План поставки создан",
        "Остаток защищён, спрос временно снижен",
        "Ждём свежий stock sync",
        "Назначена ручная проверка склада",
      ],
      caution:
        "Поставка в WB не создаётся автоматически из этого экрана. Здесь фиксируется план и контрольный recheck.",
      workLabel: "Открыть поставки/остатки",
      doneComment: "План по пополнению или защите остатка зафиксирован.",
      tone: "info",
      icon: <PackageSearch className="h-4 w-4" />,
    };
  }
  if (code === "missing_chrt_id") {
    return {
      title: "Что сделать: связь размера с карточкой",
      subtitle:
        "chrt_id должен прийти из WB карточек или доверенного mapping, руками менять WB-факты нельзя.",
      objective:
        "Запустите или дождитесь синхронизации карточек. Если после синка chrt_id не появился, передайте администратору mapping карточки/размера.",
      steps: [
        {
          title: "Проверить вариант",
          description:
            "Сверьте nmID, vendor code, размер и внутренний SKU. Убедитесь, что карточка есть в актуальном WB каталоге.",
          done: "Понятно, какой размер потерял связь",
        },
        {
          title: "Обновить карточки",
          description:
            "Запустите card sync или назначьте администратору проверку mapping. Не вводите chrt_id вручную без доверенного источника.",
          done: "Синхронизация или admin mapping запущены",
        },
        {
          title: "Перепроверить",
          description: "После обновления карточек пересчитайте Action Center.",
          done: "Связь появилась или причина зафиксирована",
        },
      ],
      outcomes: [
        "Запущен sync карточек",
        "Передано на admin mapping",
        "Карточка/размер больше не актуальны",
        "Ждём свежие WB данные",
      ],
      caution:
        "Это data-warning, а не поле для ручной продажи. Исправление должно прийти из WB sync или админского mapping.",
      workLabel: "Открыть data/admin",
      doneComment:
        "Проверка chrt_id обработана: sync/mapping запущен или причина зафиксирована.",
      tone: "warning",
      icon: <Database className="h-4 w-4" />,
    };
  }
  if (code === "card_content_review" || code.includes("qualification")) {
    return {
      title: "Что сделать: контент карточки",
      subtitle:
        "Нужно понять, что мешает карточке продавать или попадать в фильтры WB.",
      objective:
        "Проверьте title, описание, обязательные характеристики, фото, цену и конверсию. Если нужно изменить поле, откройте checker/card quality и примените правку после preview.",
      steps: [
        {
          title: "Проверить контент и фильтры",
          description:
            "Сверьте название, описание, характеристики, фото и обязательные WB поля.",
          done: "Понятно, какое поле или гипотеза слабые",
        },
        {
          title: "Подготовить правку",
          description:
            "Сформируйте изменение title/описания/характеристики или назначьте контент-ответственного.",
          done: "Правка готова или назначена",
        },
        {
          title: "Перепроверить качество",
          description:
            "После сохранения или назначения запустите проверку карточки.",
          done: "Карточка проходит проверку или есть ручной план",
        },
      ],
      outcomes: [
        "Поле карточки исправлено",
        "Создана ручная задача контенту",
        "Нужно проверить цену/рекламу вместо контента",
        "Правка отклонена после preview",
      ],
      caution:
        "Публикация в WB должна идти через preview и подтверждение. Если write недоступен, фиксируйте ручную задачу.",
      workLabel: "Открыть проверку карточки",
      doneComment:
        "Контент карточки проверен: правка применена, назначена или отклонена.",
      tone: "success",
      icon: <FileText className="h-4 w-4" />,
    };
  }
  if (
    [
      "sale_without_finance",
      "finance_without_sale",
      "order_without_sale_or_return",
    ].includes(code)
  ) {
    return {
      title: "Что сделать: системная сверка",
      subtitle:
        "Это контроль данных WB, обычно без ручной продажи или изменения фактов.",
      objective:
        "Проверьте свежесть sync и дождитесь финального отчёта WB. Если расхождение повторяется после обновления, передайте на технический разбор импорта/сопоставления.",
      steps: [
        {
          title: "Проверить источник",
          description:
            "Сверьте, какие данные пришли: продажи, заказы, финальный отчёт WB и время последнего sync.",
          done: "Понятно, это задержка WB или ошибка импорта",
        },
        {
          title: "Дождаться или обновить sync",
          description:
            "Если отчёт WB ещё не пришёл, задачу не надо решать руками. Если sync устарел, запустите обновление.",
          done: "Источник обновлён или поставлен в ожидание",
        },
        {
          title: "Перепроверить сверку",
          description: "После sync или финального отчёта пересчитайте задачу.",
          done: "Расхождение исчезло или передано администратору",
        },
      ],
      outcomes: [
        "Ожидаем финальный отчёт WB",
        "Запущен sync продаж/финансов",
        "Передано на admin import check",
        "Расхождение подтверждено как нормальная задержка",
      ],
      caution:
        "Финальные WB факты не редактируются вручную. Здесь только контроль, ожидание sync и техническая проверка.",
      workLabel: "Открыть результаты",
      doneComment:
        "Системная сверка обработана: источник обновлён, ожидание или техразбор зафиксированы.",
      tone: "neutral",
      icon: <ShieldCheck className="h-4 w-4" />,
    };
  }
  return {
    title: "Что сделать: разбор задачи",
    subtitle:
      "Платформа показывает причину, доказательства и следующий шаг. Зафиксируйте решение, чтобы очередь двигалась дальше.",
    objective:
      item.next_step ||
      item.reason ||
      "Проверьте доказательства, выполните рабочее действие или назначьте ответственного.",
    steps: [
      {
        title: "Понять задачу",
        description:
          item.reason ||
          "Откройте детали проверки и посмотрите, какие данные создали задачу.",
        done: "Причина понятна",
      },
      {
        title: "Выполнить или назначить",
        description:
          item.next_step ||
          "Выполните доступный шаг или создайте ручную задачу ответственному.",
        done: "Есть действие или ответственный",
      },
      {
        title: "Перепроверить",
        description:
          "После изменения данных запустите пересчёт и закройте задачу.",
        done: "Результат понятен",
      },
    ],
    outcomes: [
      "Исправлено в платформе",
      "Назначено ответственному",
      "Ждём данные/sync",
      "Неактуально",
    ],
    caution:
      "Если действие меняет WB, применяйте его только после preview и подтверждения.",
    workLabel: "Открыть рабочий экран",
    doneComment: "Задача разобрана в Action Center, решение зафиксировано.",
    tone: "neutral",
    icon: <ListChecks className="h-4 w-4" />,
  };
}

function actionDecisionFacts(item: ActionCenterItem): Array<{
  label: string;
  value: string;
  tone?: "neutral" | "danger" | "warning" | "success" | "info";
}> {
  const payload = itemPayload(item);
  const facts: Array<{
    label: string;
    value: string;
    tone?: "neutral" | "danger" | "warning" | "success" | "info";
  }> = [];
  if (item.nm_id) facts.push({ label: "Товар", value: `nm ${item.nm_id}` });
  if (item.sku_id) facts.push({ label: "SKU", value: String(item.sku_id) });
  const metric = decisionMetricValue(item);
  if (metric != null && metric !== 0) {
    facts.push({
      label: "Эффект/риск",
      value: formatMoney(Math.abs(metric)),
      tone: metric < 0 ? "danger" : "warning",
    });
  }
  const quantity = firstString(payload.quantityFull, payload.quantity);
  if (quantity) facts.push({ label: "Остаток", value: quantity, tone: "info" });
  const daysSince = firstString(payload.daysSinceLastSale);
  if (daysSince) {
    facts.push({
      label: "Без продаж",
      value: `${daysSince} дн.`,
      tone: "warning",
    });
  }
  const priceSafety =
    payload.price_safety && typeof payload.price_safety === "object"
      ? (payload.price_safety as Record<string, unknown>)
      : null;
  const minSafePrice = numberFromUnknown(priceSafety?.min_safe_price);
  if (minSafePrice != null) {
    facts.push({
      label: "Мин. безопасная цена",
      value: formatMoney(minSafePrice),
      tone: "warning",
    });
  }
  const maxDiscount = numberFromUnknown(priceSafety?.max_safe_discount_pct);
  if (maxDiscount != null) {
    facts.push({
      label: "Макс. скидка",
      value: `${formatNumber(maxDiscount)}%`,
      tone: "info",
    });
  }
  const trust = norm(item.trust_state ?? item.money_trust?.state);
  if (trust) {
    facts.push({
      label: "Данные",
      value: problemTrustLabel(trust),
      tone: trust === "blocked" ? "danger" : "neutral",
    });
  }
  const evidence = evidenceLabel(item.evidence_state);
  facts.push({ label: "Доказательства", value: evidence });
  return facts.slice(0, 8);
}

function ActionDecisionResolutionPanel({
  item,
  href,
  workLabel,
  busy,
  onStatus,
  onDoneNext,
  onNext,
}: {
  item: ActionCenterItem;
  href: string | null;
  workLabel: string;
  busy: boolean;
  onStatus: (
    item: ActionCenterItem,
    status: string,
    next?: boolean,
    options?: { deadline_at?: string; comment?: string },
  ) => void;
  onDoneNext: (item: ActionCenterItem) => void;
  onNext: () => void;
}) {
  const plan = actionDecisionPlan(item);
  const facts = actionDecisionFacts(item);
  const [outcome, setOutcome] = useState(plan.outcomes[0] || "");
  const [comment, setComment] = useState("");

  useEffect(() => {
    setOutcome(plan.outcomes[0] || "");
    setComment("");
  }, [item.id]);

  const finalComment = [
    plan.doneComment,
    outcome ? `Итог: ${outcome}.` : null,
    comment.trim() ? `Комментарий: ${comment.trim()}` : null,
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <div className="overflow-hidden rounded-md border bg-card shadow-sm">
      <div className="border-b bg-muted/15 px-4 py-3">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
          <div className="flex min-w-0 items-start gap-3">
            <span
              className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-md ${
                plan.tone === "danger"
                  ? "bg-red-500/10 text-red-700 dark:text-red-300"
                  : plan.tone === "warning"
                    ? "bg-amber-500/10 text-amber-700 dark:text-amber-300"
                    : plan.tone === "success"
                      ? "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300"
                      : plan.tone === "info"
                        ? "bg-sky-500/10 text-sky-700 dark:text-sky-300"
                        : "bg-muted text-muted-foreground"
              }`}
            >
              {plan.icon}
            </span>
            <div className="min-w-0">
              <div className="text-base font-semibold">{plan.title}</div>
              <div className="mt-1 max-w-3xl text-sm text-muted-foreground">
                {plan.subtitle}
              </div>
            </div>
          </div>
          <WorkButton href={href} label={plan.workLabel || workLabel} />
        </div>
      </div>

      <div className="grid gap-4 p-4 xl:grid-cols-[minmax(0,1fr)_300px]">
        <div className="space-y-4">
          <div className="rounded-md border bg-background p-4">
            <div className="text-sm font-semibold">Что нужно сделать</div>
            <div className="mt-2 text-sm leading-relaxed text-muted-foreground">
              {plan.objective}
            </div>
          </div>

          <div className="rounded-md border bg-background p-4">
            <div className="mb-3 text-sm font-semibold">Порядок выполнения</div>
            <div className="space-y-3">
              {plan.steps.map((step, index) => (
                <div
                  key={step.title}
                  className="grid grid-cols-[30px_1fr] gap-3 rounded-md border bg-muted/10 p-3"
                >
                  <span
                    className={`flex h-7 w-7 items-center justify-center rounded-full border text-xs font-semibold ${
                      index === 0
                        ? "border-primary/35 bg-primary/10 text-primary"
                        : "border-border bg-background text-muted-foreground"
                    }`}
                  >
                    {index + 1}
                  </span>
                  <div className="min-w-0">
                    <div className="text-sm font-semibold">{step.title}</div>
                    <div className="mt-1 text-xs leading-relaxed text-muted-foreground">
                      {step.description}
                    </div>
                    <div className="mt-2 rounded-md bg-background px-2 py-1 text-[11px] font-medium text-muted-foreground">
                      Готово, когда: {step.done}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          <Alert className="border-amber-500/35 bg-amber-500/5">
            <AlertTriangle className="h-4 w-4" />
            <AlertTitle>Важно перед закрытием</AlertTitle>
            <AlertDescription>{plan.caution}</AlertDescription>
          </Alert>
        </div>

        <div className="space-y-4">
          <div className="rounded-md border bg-background p-4">
            <div className="text-sm font-semibold">Факты по задаче</div>
            <div className="mt-3 grid gap-2">
              {facts.map((fact) => (
                <MetricTile
                  key={fact.label}
                  label={fact.label}
                  value={fact.value}
                  icon={<ClipboardCheck className="h-4 w-4" />}
                  tone={fact.tone || "neutral"}
                />
              ))}
            </div>
          </div>

          <div className="rounded-md border bg-background p-4">
            <div className="text-sm font-semibold">Итог решения</div>
            <div className="mt-3 flex flex-wrap gap-2">
              {plan.outcomes.map((value) => (
                <Button
                  key={value}
                  type="button"
                  size="sm"
                  variant={outcome === value ? "default" : "outline"}
                  onClick={() => setOutcome(value)}
                >
                  {value}
                </Button>
              ))}
            </div>
            <Textarea
              className="mt-3"
              value={comment}
              onChange={(event) => setComment(event.target.value)}
              rows={3}
              placeholder="Комментарий для истории задачи"
            />
          </div>

          <div className="rounded-md border bg-card p-3">
            <div className="grid gap-2">
              <Button
                size="sm"
                variant="outline"
                className="h-10 justify-start"
                disabled={busy || item.can_update === false}
                onClick={() =>
                  onStatus(item, "in_progress", false, {
                    comment: `Взято в работу: ${outcome || plan.title}`,
                  })
                }
              >
                <Play className="h-3.5 w-3.5" />В работу
              </Button>
              <Button
                size="sm"
                className="h-10 justify-start shadow-sm"
                disabled={busy || item.can_update === false}
                onClick={() =>
                  onStatus(item, "done", true, {
                    deadline_at: postponeUntilIso(1),
                    comment: finalComment,
                  })
                }
              >
                <CheckCircle2 className="h-3.5 w-3.5" />
                Записать итог и далее
              </Button>
              <TaskLifecycleActions
                item={item}
                busy={busy}
                onStatus={onStatus}
                onDoneNext={onDoneNext}
                onNext={onNext}
                showDone={false}
              />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function InlineResolutionPanel({
  item,
  accountId,
  dateFrom,
  dateTo,
  onChanged,
  onRecheck,
  onNext,
}: {
  item: ActionCenterItem;
  accountId: number | null | undefined;
  dateFrom?: string | null;
  dateTo?: string | null;
  onChanged: () => Promise<void> | void;
  onRecheck: (item: ActionCenterItem) => void;
  onNext: () => void;
}) {
  if (isInlineCostAction(item)) {
    return (
      <CostInlineResolution
        item={item}
        accountId={accountId}
        dateFrom={dateFrom}
        dateTo={dateTo}
        onChanged={onChanged}
        onRecheck={onRecheck}
        onNext={onNext}
      />
    );
  }
  if (isInlineCardTextAction(item)) {
    return (
      <CardTextInlineResolution
        item={item}
        accountId={accountId}
        onChanged={onChanged}
        onRecheck={onRecheck}
        onNext={onNext}
      />
    );
  }
  if (isInlineSkuMappingAction(item)) {
    return (
      <SkuMappingInlineResolution
        item={item}
        onChanged={onChanged}
        onRecheck={onRecheck}
        onNext={onNext}
      />
    );
  }
  return null;
}

function hasInlineResolution(item: ActionCenterItem): boolean {
  return (
    isInlineCostAction(item) ||
    isInlineCardTextAction(item) ||
    isInlineSkuMappingAction(item)
  );
}

function SkuMappingInlineResolution({
  item,
  onChanged,
  onRecheck,
  onNext,
}: {
  item: ActionCenterItem;
  onChanged: () => Promise<void> | void;
  onRecheck: (item: ActionCenterItem) => void;
  onNext: () => void;
}) {
  const queryClient = useQueryClient();
  const payload = itemPayload(item);
  const issueId = dataQualityIssueId(item);
  const candidates = skuCandidates(item);
  const sourceDomains = Array.isArray(payload.sourceDomains)
    ? payload.sourceDomains.map((value) => String(value))
    : [];
  const issueCode = norm(
    actionCode(item) || payload.code || payload.issue_code,
  );
  const hasNoSkuCandidate =
    issueCode === "unmatched_sku" && candidates.length === 0;
  const isSupplyOnlyArchived =
    hasNoSkuCandidate &&
    norm(payload.sourceKind) === "source_level" &&
    sourceDomains.map((value) => norm(value)).join(",") === "supplies" &&
    ["missing_nm_id", "source_level_missing_nm_id"].includes(
      norm(payload.classificationReason),
    );
  const [skuId, setSkuId] = useState("");
  const [reason, setReason] = useState("");

  useEffect(() => {
    const initial = numberFromUnknown(
      payload.mapped_sku_id ?? payload.sku_id ?? candidates[0],
    );
    setSkuId(initial ? String(initial) : "");
    setReason("");
  }, [item.id]);

  const numericSkuId = numberFromUnknown(skuId);
  const canSave = Boolean(issueId && numericSkuId && numericSkuId > 0);

  const saveMapping = useMutation({
    mutationFn: async () => {
      if (!issueId || !numericSkuId) {
        throw new Error("Укажите SKU, к которому нужно привязать строку.");
      }
      return api(API_ENDPOINTS.dq.guidedAction(issueId), {
        method: "POST",
        body: {
          action_type: "map_sku",
          inputs: {
            mapped_sku_id: numericSkuId,
            reason: reason.trim() || "Связано из Action Center",
          },
          comment: reason.trim() || "SKU связан из Action Center",
        },
      });
    },
    onSuccess: async (result: any) => {
      toast.success(
        result?.message ||
          "SKU связан. Запустите перепроверку, чтобы обновить очередь.",
      );
      invalidateInlineResolverQueries(queryClient);
      await onChanged?.();
      onNext();
    },
    onError: (error: any) =>
      toast.error(error?.message ?? "Не удалось связать SKU"),
  });

  const triggerRecheck = useMutation({
    mutationFn: async () => {
      if (!issueId) throw new Error("Нет issue id для перепроверки.");
      return api(API_ENDPOINTS.dq.guidedAction(issueId), {
        method: "POST",
        body: {
          action_type: "trigger_recheck",
          inputs: { source: "action_center_sku_mapping" },
          comment:
            "Перепроверка запрошена из Action Center после связывания SKU.",
        },
      });
    },
    onSuccess: async (result: any) => {
      toast.success(result?.message || "Перепроверка запрошена");
      invalidateInlineResolverQueries(queryClient);
      await onChanged?.();
    },
    onError: (error: any) =>
      toast.error(error?.message ?? "Не удалось запустить перепроверку"),
  });

  return (
    <div className="overflow-hidden rounded-md border bg-card shadow-sm">
      <div className="border-b bg-sky-500/5 px-4 py-3">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <div className="flex items-center gap-2 text-sm font-semibold">
              <PackageSearch className="h-4 w-4 text-sky-700 dark:text-sky-300" />
              {hasNoSkuCandidate
                ? "Проверить каталог SKU"
                : "Исправить здесь: связать SKU"}
            </div>
            <div className="mt-1 text-xs text-muted-foreground">
              {hasNoSkuCandidate
                ? "Для этой строки нет подходящего SKU в каталоге платформы. Ручной ввод внутреннего ID здесь не поможет."
                : "Привяжите строку продаж, остатков или себестоимости к правильному SKU. Суммы WB не меняются."}
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {issueId ? (
              <Badge variant="outline">проверка {issueId}</Badge>
            ) : null}
            {item.nm_id ? (
              <Badge variant="secondary">nm {item.nm_id}</Badge>
            ) : null}
          </div>
        </div>
      </div>

      <div className="p-4">
        <div className="space-y-4">
          <div className="rounded-md border bg-muted/20 p-3">
            <div className="text-xs text-muted-foreground">
              Проблемная строка
            </div>
            <div className="mt-1 text-sm font-semibold">
              {objectLabel(item)}
            </div>
            <div className="mt-1 text-xs text-muted-foreground">
              {item.reason ||
                item.short_explanation ||
                "Система не смогла надежно понять, к какому SKU относится строка."}
            </div>
          </div>

          {candidates.length ? (
            <div className="space-y-2">
              <Label>Возможные SKU</Label>
              <div className="flex flex-wrap gap-2">
                {candidates.slice(0, 8).map((candidate) => (
                  <Button
                    key={candidate}
                    type="button"
                    size="sm"
                    variant={
                      String(candidate) === skuId ? "default" : "outline"
                    }
                    onClick={() => setSkuId(String(candidate))}
                  >
                    SKU {candidate}
                  </Button>
                ))}
              </div>
            </div>
          ) : hasNoSkuCandidate ? (
            <Alert className="border-amber-500/35 bg-amber-500/5">
              <AlertTriangle className="h-4 w-4" />
              <AlertTitle>
                {isSupplyOnlyArchived
                  ? "Это старая строка поставки"
                  : "В каталоге нет SKU для выбора"}
              </AlertTitle>
              <AlertDescription>
                {isSupplyOnlyArchived
                  ? "В WB поставках есть nm, но такой карточки и внутреннего SKU уже нет в каталоге. Эту задачу не нужно исправлять вручную: после обновления Action Center она уйдёт из очереди."
                  : "Сначала нужно обновить каталог товаров или дождаться синхронизации карточек. После этого нажмите «Перепроверить»."}
              </AlertDescription>
            </Alert>
          ) : null}

          {!hasNoSkuCandidate ? (
            <div className="grid gap-3 sm:grid-cols-[minmax(0,240px)_1fr]">
              <div className="space-y-1.5">
                <Label htmlFor={`ac-sku-${item.id}`}>Правильный SKU</Label>
                <Input
                  id={`ac-sku-${item.id}`}
                  inputMode="numeric"
                  value={skuId}
                  onChange={(event) => setSkuId(event.target.value)}
                  placeholder="Например 123456789"
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor={`ac-sku-reason-${item.id}`}>
                  Почему это правильная связь
                </Label>
                <Textarea
                  id={`ac-sku-reason-${item.id}`}
                  value={reason}
                  onChange={(event) => setReason(event.target.value)}
                  rows={2}
                  placeholder="Например: совпадает nm_id, размер, артикул продавца или баркод"
                />
              </div>
            </div>
          ) : null}

          <div className="flex flex-wrap items-center gap-2">
            {!hasNoSkuCandidate ? (
              <Button
                size="sm"
                onClick={() => saveMapping.mutate()}
                disabled={!canSave || saveMapping.isPending}
              >
                {saveMapping.isPending ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <CheckCircle2 className="h-3.5 w-3.5" />
                )}
                Готово, далее
              </Button>
            ) : null}
            <Button
              size="sm"
              variant="outline"
              onClick={() => triggerRecheck.mutate()}
              disabled={!issueId || triggerRecheck.isPending}
            >
              {triggerRecheck.isPending ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <RotateCw className="h-3.5 w-3.5" />
              )}
              Перепроверить
            </Button>
            <Button size="sm" variant="ghost" onClick={onNext}>
              Далее
              <ArrowRight className="h-3.5 w-3.5" />
            </Button>
          </div>
          {!issueId ? (
            <div className="text-xs text-muted-foreground">
              У задачи нет ID проверки качества данных. Откройте исправление
              данных, чтобы получить контекст строки.
            </div>
          ) : !hasNoSkuCandidate && !canSave ? (
            <div className="text-xs text-muted-foreground">
              Для сохранения нужен числовой SKU. Если не уверены, сначала
              откройте товар или строку в данных.
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}

function CostInlineResolution({
  item,
  accountId,
  dateFrom,
  dateTo,
  onChanged,
  onRecheck,
  onNext,
}: {
  item: ActionCenterItem;
  accountId: number | null | undefined;
  dateFrom?: string | null;
  dateTo?: string | null;
  onChanged: () => Promise<void> | void;
  onRecheck: (item: ActionCenterItem) => void;
  onNext: () => void;
}) {
  const queryClient = useQueryClient();
  const [index, setIndex] = useState(0);
  const [drafts, setDrafts] = useState<
    Record<string, { cost: string; other: string }>
  >({});
  const [supplierConfirmed, setSupplierConfirmed] = useState(false);
  const itemNmId = numberFromUnknown(item.nm_id);

  useEffect(() => {
    setIndex(0);
    setDrafts({});
    setSupplierConfirmed(false);
  }, [item.id]);

  const missingCostsQ = useQuery({
    queryKey: [
      "action-center-inline-missing-costs",
      accountId,
      item.id,
      itemNmId,
      dateFrom,
      dateTo,
    ],
    enabled: !!accountId,
    queryFn: () =>
      fetchCostsMissing(accountId!, {
        limit: 200,
        offset: 0,
        dateFrom: dateFrom ?? undefined,
        dateTo: dateTo ?? undefined,
        onlyRevenue: false,
      }),
    staleTime: 20_000,
  });

  const rows = useMemo(() => {
    const allRows = sortMissingCostRows(missingCostsQ.data?.items ?? []);
    if (!itemNmId) return allRows;
    const filtered = sortMissingCostRows(
      allRows.filter((row) => numberFromUnknown(row.nm_id) === itemNmId),
    );
    return filtered.length ? filtered : allRows;
  }, [itemNmId, missingCostsQ.data]);
  const totalMissingRows = Number(
    missingCostsQ.data?.total ?? rows.length ?? 0,
  );
  const missingCostSummaryRevenue = moneyFromUnknown(
    missingCostsQ.data?.summary?.affected_revenue,
  );
  const revenueRows = rows.filter((row) => missingCostRevenue(row) > 0).length;

  useEffect(() => {
    if (index >= rows.length) setIndex(Math.max(0, rows.length - 1));
  }, [index, rows.length]);

  const current = rows[Math.min(index, Math.max(rows.length - 1, 0))] ?? null;
  const currentImages = useMemo(() => {
    const rowImages = rowImageCandidates(current);
    return rowImages.length ? rowImages : itemImageCandidates(item);
  }, [current, item]);
  const currentKey = current ? costRowKey(current, index) : "";
  const currentStep = rows.length ? `${index + 1}/${rows.length}` : "0/0";
  const draft = drafts[currentKey] ?? { cost: "", other: "" };
  const filledCount = rows.filter(
    (row, rowIndex) =>
      parseMoneyDraft(drafts[costRowKey(row, rowIndex)]?.cost ?? "") != null,
  ).length;
  const costValue = parseMoneyDraft(draft.cost);
  const otherValue = parseMoneyDraft(draft.other, true);
  const canSave = Boolean(
    accountId && current?.sku_id && costValue != null && otherValue != null,
  );

  const updateDraft = (patch: Partial<{ cost: string; other: string }>) => {
    if (!currentKey) return;
    setDrafts((prev) => ({
      ...prev,
      [currentKey]: {
        cost: prev[currentKey]?.cost ?? "",
        other: prev[currentKey]?.other ?? "",
        ...patch,
      },
    }));
  };

  const saveCost = useMutation({
    mutationFn: async () => {
      if (
        !accountId ||
        !current?.sku_id ||
        costValue == null ||
        otherValue == null
      ) {
        throw new Error("Заполните себестоимость и прочие расходы.");
      }
      return saveInlineCosts({
        account_id: accountId,
        rows: [
          {
            sku_id: current.sku_id,
            cost_price: costValue,
            seller_other_expense: otherValue,
            supplier: "OPERATOR_TRUSTED_COST",
            valid_from: dateFrom ?? undefined,
            is_supplier_confirmed: supplierConfirmed,
            comment:
              "Заполнено из Action Center: встроенное исправление себестоимости",
          },
        ],
      });
    },
    onSuccess: async () => {
      toast.success("Себестоимость сохранена. Пересчёт запущен.");
      invalidateInlineResolverQueries(queryClient);
      await onChanged?.();
      if (index < rows.length - 1) {
        setIndex((value) => value + 1);
      } else {
        onNext();
      }
    },
    onError: (error: any) =>
      toast.error(error?.message ?? "Не удалось сохранить себестоимость"),
  });

  return (
    <div className="overflow-hidden rounded-md border bg-card shadow-sm">
      <div className="border-b bg-amber-500/5 px-4 py-3">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <div className="flex items-center gap-2 text-sm font-semibold">
              <Database className="h-4 w-4 text-amber-700 dark:text-amber-300" />
              Заполнить себестоимость
            </div>
            <div className="mt-1 text-xs text-muted-foreground">
              Внесите цену закупки и прочие расходы. После сохранения система
              перейдёт к следующему товару.
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="outline">
              {missingCostsQ.isLoading
                ? "Загружаем строки"
                : `${totalMissingRows || rows.length || 0} строк`}
            </Badge>
            {missingCostSummaryRevenue ? (
              <Badge
                variant="outline"
                className="border-red-500/30 bg-red-500/5 text-red-700 dark:text-red-300"
              >
                {formatMoney(missingCostSummaryRevenue)} выручки
              </Badge>
            ) : null}
            {revenueRows ? (
              <Badge variant="secondary">{revenueRows} с продажами</Badge>
            ) : null}
            <Badge variant="outline">{filledCount} заполнено</Badge>
          </div>
        </div>
      </div>

      {missingCostsQ.isLoading ? (
        <div className="space-y-4 p-4">
          <div className="flex items-center gap-2 rounded-md border bg-muted/20 p-3 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" />
            Загружаем список товаров без себестоимости...
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-10 w-full" />
          </div>
        </div>
      ) : !current ? (
        <div className="p-4">
          <Alert className="border-emerald-500/35 bg-emerald-500/5">
            <CheckCircle2 className="h-4 w-4" />
            <AlertTitle>Строки без себестоимости не найдены</AlertTitle>
            <AlertDescription>
              Возможно, данные уже исправлены. Запустите перепроверку, чтобы
              обновить очередь.
            </AlertDescription>
          </Alert>
          <div className="mt-3 flex flex-wrap gap-2">
            <Button size="sm" variant="outline" onClick={() => onRecheck(item)}>
              <RotateCw className="h-3.5 w-3.5" />
              Перепроверить
            </Button>
            <Button size="sm" variant="outline" asChild>
              <Link
                to="/results"
                search={{
                  problem_instance_id: item.problem_instance_id
                    ? String(item.problem_instance_id)
                    : undefined,
                }}
              >
                Открыть в результатах
                <ArrowRight className="h-3.5 w-3.5" />
              </Link>
            </Button>
            <Button size="sm" variant="ghost" onClick={onNext}>
              Далее
              <ArrowRight className="h-3.5 w-3.5" />
            </Button>
          </div>
        </div>
      ) : (
        <div className="p-4">
          <div className="space-y-4">
            <div className="rounded-md border bg-gradient-to-b from-background to-muted/20 p-3 shadow-sm">
              <div className="flex gap-3">
                <ProductThumb
                  candidates={currentImages}
                  label={costRowLabel(current)}
                  className="h-20 w-16 sm:h-24 sm:w-20"
                />
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge
                      variant="default"
                      className="bg-primary/10 text-primary hover:bg-primary/10"
                    >
                      {currentStep}
                    </Badge>
                    <Badge variant="outline">SKU {current.sku_id}</Badge>
                    {current.nm_id ? (
                      <Badge variant="secondary">nm {current.nm_id}</Badge>
                    ) : null}
                    {current.tech_size ? (
                      <Badge variant="outline">
                        Размер {current.tech_size}
                      </Badge>
                    ) : null}
                  </div>
                  <div className="mt-2 line-clamp-2 text-base font-semibold leading-snug">
                    {costRowLabel(current)}
                  </div>
                  <div className="mt-1 text-xs text-muted-foreground">
                    Блокирует расчёт прибыли в выбранном периоде на сумму{" "}
                    <span className="font-semibold text-foreground">
                      {missingCostRevenue(current)
                        ? formatMoney(missingCostRevenue(current))
                        : "без продаж за период"}
                    </span>
                  </div>
                </div>
              </div>
            </div>

            <div className="grid gap-3 lg:grid-cols-2">
              <div className="space-y-1.5">
                <Label htmlFor={`ac-cost-${item.id}`}>
                  Себестоимость за единицу
                </Label>
                <Input
                  id={`ac-cost-${item.id}`}
                  inputMode="decimal"
                  value={draft.cost}
                  onChange={(event) =>
                    updateDraft({ cost: event.target.value })
                  }
                  placeholder="Например 450"
                  className="h-11 text-base"
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor={`ac-other-${item.id}`}>
                  Прочие расходы за единицу
                </Label>
                <Input
                  id={`ac-other-${item.id}`}
                  inputMode="decimal"
                  value={draft.other}
                  onChange={(event) =>
                    updateDraft({ other: event.target.value })
                  }
                  placeholder="Если нет расходов, 0"
                  className="h-11 text-base"
                />
              </div>
            </div>

            <div className="flex flex-col gap-3 rounded-md border bg-background px-3 py-3 sm:flex-row sm:items-center sm:justify-between">
              <label className="flex min-w-0 items-center gap-2 text-sm">
                <Checkbox
                  checked={supplierConfirmed}
                  onCheckedChange={(checked) =>
                    setSupplierConfirmed(checked === true)
                  }
                />
                <span className="text-muted-foreground">
                  Цифры проверены
                </span>
              </label>

              <div className="flex flex-wrap items-center gap-2 sm:justify-end">
                <Button
                  onClick={() => saveCost.mutate()}
                  disabled={!canSave || saveCost.isPending}
                  className="h-10 min-w-[150px] shadow-sm"
                >
                  {saveCost.isPending ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <CheckCircle2 className="h-4 w-4" />
                  )}
                  Готово, далее
                </Button>
                <Button className="h-10" variant="outline" onClick={onNext}>
                  Пропустить
                  <ArrowRight className="h-4 w-4" />
                </Button>
              </div>
            </div>
            {!canSave ? (
              <div className="rounded-md bg-muted/40 px-3 py-2 text-xs text-muted-foreground">
                Для сохранения нужна себестоимость числом 0 или больше. Если
                прочих расходов нет, поставьте 0.
              </div>
            ) : null}
          </div>
        </div>
      )}
    </div>
  );
}

function CardTextInlineResolution({
  item,
  accountId,
  onChanged,
  onRecheck,
  onNext,
}: {
  item: ActionCenterItem;
  accountId: number | null | undefined;
  onChanged: () => Promise<void> | void;
  onRecheck: (item: ActionCenterItem) => void;
  onNext: () => void;
}) {
  const queryClient = useQueryClient();
  const payload = itemPayload(item);
  const issueId = cardQualityIssueId(item);
  const field = cardTextField(item) ?? "title";
  const [draft, setDraft] = useState("");
  const [preview, setPreview] = useState<any | null>(null);

  useEffect(() => {
    setDraft(
      String(
        payload.fixed_value ??
          payload.suggested_value ??
          payload.ai_suggested_value ??
          "",
      ),
    );
    setPreview(null);
  }, [item.id]);

  const localSave = useMutation({
    mutationFn: () => {
      if (!issueId || !accountId || !draft.trim())
        throw new Error("Заполните текст исправления.");
      return fixCardQualityIssue(issueId, accountId, {
        fixed_value: draft.trim(),
        apply_to_wb: false,
        reason: "fixed_locally_from_action_center",
      });
    },
    onSuccess: async () => {
      toast.success("Правка сохранена локально в платформе");
      invalidateInlineResolverQueries(queryClient);
      await onChanged?.();
      onNext();
    },
    onError: (error: any) =>
      toast.error(error?.message ?? "Не удалось сохранить правку"),
  });

  const previewMutation = useMutation({
    mutationFn: () => {
      if (!issueId || !accountId || !draft.trim())
        throw new Error("Заполните текст исправления.");
      return previewCardQualityIssueApply(issueId, accountId, {
        fixed_value: draft.trim(),
      });
    },
    onSuccess: (result) => {
      setPreview(result);
      toast.success("Предпросмотр WB готов. Карточка WB ещё не изменена.");
    },
    onError: (error: any) =>
      toast.error(error?.message ?? "Не удалось подготовить предпросмотр"),
  });

  const applyWb = useMutation({
    mutationFn: () => {
      if (!issueId || !accountId || !draft.trim())
        throw new Error("Заполните текст исправления.");
      if (preview && preview.can_apply_to_wb === false) {
        throw new Error(
          preview.blocked_reason ||
            "Это изменение нельзя отправить в WB автоматически.",
        );
      }
      return fixCardQualityIssue(issueId, accountId, {
        fixed_value: draft.trim(),
        apply_to_wb: true,
        confirm: true,
        reason: "wb_submit_from_action_center_after_preview",
      });
    },
    onSuccess: async () => {
      toast.success(
        "Правка отправлена в WB. Ожидаем валидацию и перепроверку.",
      );
      invalidateInlineResolverQueries(queryClient);
      await onChanged?.();
      onNext();
    },
    onError: (error: any) =>
      toast.error(error?.message ?? "Не удалось отправить в WB"),
  });

  const currentValue = String(
    payload.current_value ?? payload.current_value_json ?? "",
  );
  const previewBefore =
    preview?.diff?.before ?? preview?.current_value ?? currentValue;
  const previewAfter = preview?.diff?.after ?? preview?.fixed_value ?? draft;
  const busy =
    localSave.isPending || previewMutation.isPending || applyWb.isPending;
  const canSend = Boolean(draft.trim()) && !!issueId && !!accountId;
  const previewBlocked = Boolean(
    preview?.blocked_reason || preview?.can_apply_to_wb === false,
  );

  return (
    <div className="overflow-hidden rounded-md border bg-card shadow-sm">
      <div className="border-b bg-emerald-500/5 px-4 py-3">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <div className="flex items-center gap-2 text-sm font-semibold">
              <FileText className="h-4 w-4 text-emerald-700 dark:text-emerald-300" />
              Исправить здесь:{" "}
              {field === "title" ? "название карточки" : "описание карточки"}
            </div>
            <div className="mt-1 text-xs text-muted-foreground">
              Сначала сохраните локально или посмотрите diff. WB меняется только
              после отдельного подтверждения.
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <Badge variant="outline">проверка {issueId ?? "—"}</Badge>
            {item.nm_id ? (
              <Badge variant="secondary">nm {item.nm_id}</Badge>
            ) : null}
          </div>
        </div>
      </div>

      <div className="space-y-4 p-4">
        <div className="grid gap-3 lg:grid-cols-2">
          <div className="rounded-md border bg-muted/20 p-3">
            <div className="text-xs font-medium text-muted-foreground">
              Сейчас
            </div>
            <div className="mt-2 min-h-12 whitespace-pre-wrap break-words text-sm">
              {currentValue || "Пусто"}
            </div>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor={`ac-card-text-${item.id}`}>
              {field === "title" ? "Новое название" : "Новое описание"}
            </Label>
            {field === "title" ? (
              <Input
                id={`ac-card-text-${item.id}`}
                value={draft}
                onChange={(event) => {
                  setDraft(event.target.value);
                  setPreview(null);
                }}
                placeholder="Например: Джемпер женский хлопковый базовый"
              />
            ) : (
              <Textarea
                id={`ac-card-text-${item.id}`}
                rows={5}
                value={draft}
                onChange={(event) => {
                  setDraft(event.target.value);
                  setPreview(null);
                }}
                placeholder="Опишите товар фактами: материал, назначение, комплектация, уход."
              />
            )}
            <div className="text-xs text-muted-foreground">
              {field === "title"
                ? "Название должно быть понятным покупателю и не состоять только из артикула."
                : "Описание должно опираться на факты карточки, без неподтверждённых обещаний."}
            </div>
          </div>
        </div>

        {preview ? (
          <div
            className={`rounded-md border p-3 text-sm ${previewBlocked ? "border-amber-500/40 bg-amber-500/10" : "bg-muted/20"}`}
          >
            <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
              <div className="font-medium">Предпросмотр изменений WB</div>
              <Badge variant={previewBlocked ? "outline" : "secondary"}>
                {previewBlocked
                  ? "WB отправка заблокирована"
                  : "Можно отправлять"}
              </Badge>
            </div>
            <div className="grid gap-2 lg:grid-cols-2">
              <Fact label="Было" value={String(previewBefore || "Пусто")} />
              <Fact label="Станет" value={String(previewAfter || "Пусто")} />
            </div>
            {preview.blocked_reason ? (
              <div className="mt-2 text-xs text-amber-800 dark:text-amber-200">
                {preview.blocked_reason}
              </div>
            ) : null}
          </div>
        ) : null}

        <div className="flex flex-wrap items-center gap-2">
          <Button
            size="sm"
            onClick={() => localSave.mutate()}
            disabled={!canSend || busy}
          >
            {localSave.isPending ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <CheckCircle2 className="h-3.5 w-3.5" />
            )}
            Готово, далее
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={() => previewMutation.mutate()}
            disabled={!canSend || busy}
          >
            {previewMutation.isPending ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Search className="h-3.5 w-3.5" />
            )}
            Предпросмотр WB
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={() => applyWb.mutate()}
            disabled={!canSend || busy || !preview || previewBlocked}
          >
            {applyWb.isPending ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <ShieldCheck className="h-3.5 w-3.5" />
            )}
            Отправить в WB
          </Button>
          <Button size="sm" variant="ghost" onClick={onNext}>
            Далее
            <ArrowRight className="h-3.5 w-3.5" />
          </Button>
        </div>

        {!canSend ? (
          <div className="text-xs text-muted-foreground">
            Введите исправленный текст. Без текста платформа не будет закрывать
            задачу и не отправит изменение в WB.
          </div>
        ) : null}
      </div>
    </div>
  );
}

function ManualTaskResolutionPanel({
  item,
  busy,
  onStatus,
  onDoneNext,
  onNext,
}: {
  item: ActionCenterItem;
  busy: boolean;
  onStatus: (
    item: ActionCenterItem,
    status: string,
    next?: boolean,
    options?: { deadline_at?: string; comment?: string },
  ) => void;
  onDoneNext: (item: ActionCenterItem) => void;
  onNext: () => void;
}) {
  const queryClient = useQueryClient();
  const payload = itemPayload(item);
  const products = manualTaskProducts(item);
  const progress = manualTaskProgress(item);
  const progressItems = Array.isArray(progress.items) ? progress.items : [];
  const actionId = manualTaskActionId(item);
  const closed = isClosedAction(item);
  const instructions = firstString(
    payload.instructions,
    item.reason,
    item.short_explanation,
  );
  const inProgress = norm(item.status) === "in_progress";
  const deadline = formatDeadline(item, new Date());
  const displayProducts = products.length
    ? products
    : [
        {
          nm_id: item.nm_id ?? 0,
          title: item.title,
          vendor_code: item.vendor_code,
          photo_url: firstString(
            payload.photo_url,
            payload.image_url,
            payload.thumbnail,
          ),
        } as PortalProductRow,
      ];
  const productKey = (product: PortalProductRow, index: number) =>
    firstString(
      product.manual_task_item_key,
      progressItems[index]?.item_key,
      `product-${index + 1}`,
    );
  const progressStatusByKey = useMemo(() => {
    const map = new Map<string, string>();
    progressItems.forEach((entry, index: number) => {
      const key = firstString(entry.item_key, `product-${index + 1}`);
      if (key) map.set(key, norm(entry.status || "pending"));
    });
    return map;
  }, [progressItems]);
  const progressSignature = useMemo(
    () =>
      displayProducts
        .map((product, index) => {
          const key = productKey(product, index);
          return `${key}:${progressStatusByKey.get(key) || "pending"}`;
        })
        .join("|"),
    [displayProducts, progressStatusByKey],
  );
  const [checkedProducts, setCheckedProducts] = useState<Set<string>>(
    () => new Set(),
  );
  useEffect(() => {
    const doneKeys = displayProducts
      .map((product, index) => productKey(product, index))
      .filter((key) => progressStatusByKey.get(key) === "done");
    setCheckedProducts(new Set(doneKeys));
  }, [item.id, progressSignature]);
  const itemMutation = useMutation({
    mutationFn: ({
      itemKey,
      status,
    }: {
      itemKey: string;
      status: "pending" | "done" | "skipped";
    }) => {
      if (actionId == null) {
        throw new Error("У ручной задачи нет action_id");
      }
      return updateManualTaskItem(actionId, itemKey, {
        account_id: item.account_id,
        status,
        comment:
          status === "done"
            ? "Товар отмечен готовым в ручной задаче."
            : "Товар возвращён в работу в ручной задаче.",
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["portal-actions"] });
      queryClient.invalidateQueries({ queryKey: ["portal-action-results"] });
    },
    onError: () => {
      toast.error("Не удалось сохранить прогресс по товару");
      queryClient.invalidateQueries({ queryKey: ["portal-actions"] });
    },
  });
  const checkedCount = checkedProducts.size;
  const allChecked =
    displayProducts.length > 0 && checkedCount >= displayProducts.length;
  const toggleProductDone = (key: string, checked: boolean) => {
    if (closed || item.can_update === false || itemMutation.isPending) return;
    setCheckedProducts((prev) => {
      const next = new Set(prev);
      if (checked) next.add(key);
      else next.delete(key);
      return next;
    });
    itemMutation.mutate({
      itemKey: key,
      status: checked ? "done" : "pending",
    });
  };
  const markSelectedDone = () => {
    if (allChecked || displayProducts.length <= 1) {
      onStatus(item, "done", true, {
        deadline_at: postponeUntilIso(1),
        comment:
          "Выполнено из Центра действий. Скрыто из активной очереди до следующей ежедневной проверки.",
      });
      return;
    }
    onStatus(item, "in_progress", false, {
      comment: `Прогресс сохранён по ${checkedCount} из ${displayProducts.length} товаров. Задача оставлена в работе.`,
    });
    toast.success("Прогресс сохранён. Задача осталась в работе.");
  };
  return (
    <div className="overflow-hidden rounded-xl border bg-card shadow-sm">
      <div className="border-b bg-muted/20 px-4 py-4">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div className="flex min-w-0 items-start gap-3">
            <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-primary text-primary-foreground shadow-sm">
              <ListChecks className="h-5 w-5" />
            </span>
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-1.5">
                <Badge
                  variant="outline"
                  className="rounded-full border-teal-500/35 bg-teal-500/10 text-teal-800 dark:text-teal-200"
                >
                  ручная задача
                </Badge>
                <StatusBadge status={item.status} />
                <PriorityBadge item={item} />
              </div>
              <div className="mt-2 text-lg font-semibold leading-tight">
                {item.title}
              </div>
              <div className="mt-1 max-w-3xl text-sm text-muted-foreground">
                {instructions ||
                  "Ответственный должен выполнить задачу по выбранным товарам и закрыть её в Центре действий."}
              </div>
            </div>
          </div>
          <div className="grid shrink-0 grid-cols-2 gap-2 text-xs sm:min-w-[320px]">
            <div className="rounded-lg border bg-background px-3 py-2">
              <div className="flex items-center gap-1.5 text-muted-foreground">
                <UserRound className="h-3.5 w-3.5" />
                Ответственный
              </div>
              <div className="mt-1 truncate font-semibold">
                {item.assigned_to_user_name || "Не назначен"}
              </div>
            </div>
            <div className="rounded-lg border bg-background px-3 py-2">
              <div className="flex items-center gap-1.5 text-muted-foreground">
                <Clock3 className="h-3.5 w-3.5" />
                Срок
              </div>
              <div className="mt-1 truncate font-semibold">
                {deadline.detail
                  ? `${deadline.label}, ${deadline.detail}`
                  : deadline.label}
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="grid gap-4 p-4 xl:grid-cols-[minmax(0,1fr)_300px]">
        <div className="space-y-4">
          <div className="rounded-xl border bg-background p-4">
            <div className="mb-3 flex items-center justify-between gap-3">
              <div>
                <div className="text-sm font-semibold">Что нужно сделать</div>
                <div className="text-xs text-muted-foreground">
                  Короткий brief для исполнителя.
                </div>
              </div>
              <Badge variant="secondary" className="rounded-full">
                {checkedCount}/{displayProducts.length} готово
              </Badge>
            </div>
            <div className="rounded-lg border bg-muted/20 p-3">
              <div className="whitespace-pre-wrap text-sm leading-relaxed">
                {instructions || item.title}
              </div>
            </div>
          </div>

          <div className="rounded-xl border bg-background p-4">
            <div className="mb-3 flex items-center justify-between gap-3">
              <div>
                <div className="text-sm font-semibold">Товары</div>
                <div className="text-xs text-muted-foreground">
                  Объекты, по которым создана задача.
                </div>
              </div>
              <Badge variant="outline" className="rounded-full">
                {displayProducts.length} товар
              </Badge>
            </div>
            <div className="max-h-[360px] space-y-2 overflow-y-auto pr-1">
              {displayProducts.map((product, index) => {
                const key = productKey(product, index);
                const checked = checkedProducts.has(key);
                return (
                  <label
                    key={key}
                    className={`group flex min-w-0 cursor-pointer items-center gap-3 rounded-lg border p-2 transition-colors ${
                      checked
                        ? "border-emerald-500/35 bg-emerald-500/5"
                        : "bg-card hover:border-primary/35"
                    }`}
                  >
                    <Checkbox
                      checked={checked}
                      disabled={
                        closed ||
                        item.can_update === false ||
                        itemMutation.isPending
                      }
                      onCheckedChange={(value) =>
                        toggleProductDone(key, value === true)
                      }
                    />
                    <ProductThumb
                      candidates={productRowImageCandidates(product)}
                      label={productRowTitle(product)}
                      className="h-16 w-12 rounded-lg"
                    />
                    <div className="min-w-0 flex-1">
                      <div className="line-clamp-2 text-sm font-semibold leading-snug">
                        {productRowTitle(product)}
                      </div>
                      <div className="mt-1 truncate text-xs text-muted-foreground">
                        {productRowSubtitle(product)}
                      </div>
                    </div>
                    {itemMutation.isPending ? (
                      <Loader2 className="h-4 w-4 shrink-0 animate-spin text-muted-foreground" />
                    ) : checked ? (
                      <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-600" />
                    ) : null}
                  </label>
                );
              })}
            </div>
          </div>
        </div>

        <div className="space-y-4">
          <div className="rounded-xl border bg-background p-4">
            <div className="text-sm font-semibold">Ход выполнения</div>
            <div className="mt-2">
              <div className="flex items-center justify-between text-xs">
                <span className="text-muted-foreground">Товары готовы</span>
                <span className="font-semibold">
                  {checkedCount}/{displayProducts.length}
                </span>
              </div>
              <Progress
                value={
                  displayProducts.length
                    ? Math.round((checkedCount / displayProducts.length) * 100)
                    : 0
                }
                className="mt-1 h-1.5"
              />
            </div>
            <div className="mt-3 space-y-3">
              {[
                {
                  title: "Принять задачу",
                  text: "Ответственный понимает, что нужно сделать.",
                  done: inProgress || closed,
                },
                {
                  title: "Выполнить работу",
                  text: "Изменить title, фото, цену или выполнить свою инструкцию.",
                  done: checkedCount > 0 || closed,
                },
                {
                  title: "Закрыть",
                  text: "Отметить результат, чтобы задача ушла из очереди.",
                  done: closed,
                },
              ].map((step, index) => (
                <div
                  key={step.title}
                  className="grid grid-cols-[28px_1fr] gap-3"
                >
                  <span
                    className={`flex h-7 w-7 items-center justify-center rounded-full border text-xs font-semibold ${
                      step.done
                        ? "border-emerald-500/35 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300"
                        : index === 0
                          ? "border-primary/35 bg-primary/10 text-primary"
                          : "border-border bg-muted/30 text-muted-foreground"
                    }`}
                  >
                    {step.done ? <Check className="h-3.5 w-3.5" /> : index + 1}
                  </span>
                  <div className="min-w-0">
                    <div className="text-sm font-semibold">{step.title}</div>
                    <div className="text-xs text-muted-foreground">
                      {step.text}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="rounded-xl border bg-card p-3">
            <div className="mb-2 text-xs text-muted-foreground">
              {displayProducts.length > 1
                ? "Частичный прогресс сохранится по товарам. Чтобы закрыть задачу, отметьте все товары."
                : "Закройте задачу, когда товар реально исправлен."}
            </div>
            <div className="grid gap-2">
              <Button
                size="sm"
                className="h-10 justify-start rounded-xl shadow-sm"
                disabled={
                  closed ||
                  busy ||
                  itemMutation.isPending ||
                  !item.can_update ||
                  (!checkedCount && displayProducts.length > 1)
                }
                onClick={markSelectedDone}
              >
                <CheckCircle2 className="h-3.5 w-3.5" />
                {allChecked || displayProducts.length <= 1
                  ? "Готово на 1 день"
                  : "Записать прогресс"}
              </Button>
              <TaskLifecycleActions
                item={item}
                busy={busy}
                onStatus={onStatus}
                onDoneNext={onDoneNext}
                onNext={onNext}
                showDone={false}
              />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

type ProblemDetailTab = "action" | "analysis" | "history" | "related";

function ProblemDetailTabs({
  value,
  onChange,
}: {
  value: ProblemDetailTab;
  onChange: (value: ProblemDetailTab) => void;
}) {
  const tabs: Array<{ value: ProblemDetailTab; label: string }> = [
    { value: "analysis", label: "Анализ" },
    { value: "action", label: "Рекомендации" },
    { value: "history", label: "История" },
    { value: "related", label: "Связанные товары" },
  ];
  return (
    <div className="flex gap-1 overflow-x-auto border-b px-4 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
      {tabs.map((tab) => {
        const active = value === tab.value;
        return (
          <button
            key={tab.value}
            type="button"
            onClick={() => onChange(tab.value)}
            className={`relative h-11 shrink-0 px-3 text-sm font-semibold transition-colors ${
              active
                ? "text-primary"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            {tab.label}
            {active ? (
              <span className="absolute inset-x-2 bottom-0 h-0.5 rounded-full bg-primary" />
            ) : null}
          </button>
        );
      })}
    </div>
  );
}

function ProblemDetailMetric({
  label,
  value,
  tone = "neutral",
}: {
  label: string;
  value: React.ReactNode;
  tone?: "neutral" | "danger" | "warning" | "success" | "info";
}) {
  const toneClass =
    tone === "danger"
      ? "text-red-700 dark:text-red-300"
      : tone === "warning"
        ? "text-amber-800 dark:text-amber-300"
        : tone === "success"
          ? "text-emerald-700 dark:text-emerald-300"
          : tone === "info"
            ? "text-sky-700 dark:text-sky-300"
            : "text-foreground";
  return (
    <div className="min-w-0 border-l px-3 first:border-l-0">
      <div className="truncate text-[11px] text-muted-foreground">{label}</div>
      <div className={`mt-1 truncate text-sm font-semibold ${toneClass}`}>
        {value}
      </div>
    </div>
  );
}

function ProblemDetailHeader({
  item,
  tab,
  onTabChange,
  onNext,
  hasNext,
}: {
  item: ActionCenterItem;
  tab: ProblemDetailTab;
  onTabChange: (value: ProblemDetailTab) => void;
  onNext: () => void;
  hasNext: boolean;
}) {
  const facts = actionDecisionFacts(item);
  const progress = solveProgress(item);
  const money = moneyFromUnknown(item.money_impact_amount);
  const primary = primaryActionForItem(item);
  const nextLabel = primary?.code
    ? humanActionLabel(primary.code)
    : guidedFixLabel(item) || actionModeLabel(item);
  const deadline = formatDeadline(item, new Date());
  const metricFacts = [
    {
      label: "Товар",
      value: objectLabel(item),
      tone: "neutral",
    },
    {
      label: "Эффект/риск",
      value: money ? formatMoney(money) : "—",
      tone: money ? "danger" : "neutral",
    },
    {
      label: "Следующий шаг",
      value: nextLabel,
      tone: isDataBlockerAction(item) ? "warning" : "info",
    },
    {
      label: "Срок",
      value: deadline.detail
        ? `${deadline.label}, ${deadline.detail}`
        : deadline.label,
      tone: isOverdueAction(item) ? "danger" : "neutral",
    },
    ...(facts.length
      ? facts
          .filter((fact) => fact.label !== "Эффект/риск")
          .slice(0, 1)
          .map((fact) => ({
            label: fact.label,
            value: fact.value,
            tone: fact.tone ?? "neutral",
          }))
      : []),
  ].slice(0, 5);
  return (
    <section className="overflow-hidden rounded-md border bg-card shadow-sm">
      <div className="px-4 py-4">
        <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
          <div className="flex min-w-0 items-start gap-4">
            <ProductThumb
              candidates={itemImageCandidates(item)}
              label={itemProductTitle(item)}
              className="h-24 w-20"
            />
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-1.5">
                <PriorityBadge item={item} />
                <Badge
                  variant="outline"
                  className={`rounded-full text-[10px] ${actionStateTone(item)}`}
                >
                  {actionModeLabel(item)}
                </Badge>
                <StatusBadge status={item.status} />
                {item.nm_id ? (
                  <Badge variant="outline" className="rounded-full text-[10px]">
                    nm {item.nm_id}
                  </Badge>
                ) : null}
              </div>
              <h2 className="mt-2 text-xl font-semibold leading-tight">
                {problemTitle(item)}
              </h2>
              <div className="mt-1 max-w-3xl text-sm text-muted-foreground">
                {item.short_explanation ||
                  item.reason ||
                  item.next_step ||
                  problemCodeLabel(actionCode(item))}
              </div>
              <div className="mt-3 flex min-w-0 flex-wrap items-center gap-2 text-xs">
                <span className="rounded-full bg-muted px-2.5 py-1 font-medium">
                  {itemProductTitle(item)}
                </span>
                <span className="rounded-full bg-muted px-2.5 py-1 text-muted-foreground">
                  {objectLabel(item)}
                </span>
              </div>
            </div>
          </div>
          <Button
            size="sm"
            variant="ghost"
            disabled={!hasNext}
            onClick={onNext}
            className="self-start"
          >
            Далее
            <ArrowRight className="h-3.5 w-3.5" />
          </Button>
        </div>

        <div className="mt-4 overflow-hidden rounded-md border bg-muted/10">
          <div className="grid divide-y sm:grid-cols-2 sm:divide-x sm:divide-y-0 xl:grid-cols-5">
            {metricFacts.map((fact) => (
              <ProblemDetailMetric
                key={fact.label}
                label={fact.label}
                value={fact.value}
                tone={fact.tone}
              />
            ))}
          </div>
          <div className="flex items-center gap-3 border-t px-3 py-2">
            <Progress value={progress.percent} className="h-1.5 flex-1" />
            <span className="w-10 text-right text-xs font-semibold">
              {progress.percent}%
            </span>
          </div>
        </div>
      </div>
      <ProblemDetailTabs value={tab} onChange={onTabChange} />
    </section>
  );
}

function MiniTrendChart({ tone = "info" }: { tone?: "info" | "danger" }) {
  const stroke = tone === "danger" ? "#dc2626" : "#0f766e";
  return (
    <div className="h-32 rounded-md border bg-background p-3">
      <svg viewBox="0 0 320 96" className="h-full w-full" role="img">
        <defs>
          <linearGradient
            id="action-center-mini-fill"
            x1="0"
            x2="0"
            y1="0"
            y2="1"
          >
            <stop offset="0%" stopColor={stroke} stopOpacity="0.22" />
            <stop offset="100%" stopColor={stroke} stopOpacity="0.02" />
          </linearGradient>
        </defs>
        <path
          d="M8 76 L48 62 L88 66 L128 48 L168 38 L208 44 L248 30 L312 22 L312 92 L8 92 Z"
          fill="url(#action-center-mini-fill)"
        />
        <path
          d="M8 76 L48 62 L88 66 L128 48 L168 38 L208 44 L248 30 L312 22"
          fill="none"
          stroke={stroke}
          strokeLinecap="round"
          strokeWidth="4"
        />
        <path
          d="M8 62 L312 62"
          fill="none"
          stroke="#ef4444"
          strokeDasharray="8 8"
          strokeWidth="2"
        />
      </svg>
    </div>
  );
}

function ActionPreviewPanel({ item }: { item: ActionCenterItem }) {
  const plan = actionDecisionPlan(item);
  const metric = decisionMetricValue(item);
  const resultMoney = metric == null ? 0 : Math.abs(metric);
  const mode = actionExecutionMode(item);
  return (
    <div className="overflow-hidden rounded-md border bg-card shadow-sm">
      <div className="border-b px-4 py-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="text-xs font-semibold uppercase text-muted-foreground">
              Рекомендованное действие
            </div>
            <div className="mt-1 flex flex-wrap items-center gap-2">
              <div className="text-lg font-semibold">{plan.workLabel}</div>
              <Badge
                variant="outline"
                className="rounded-full border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300"
              >
                лучший вариант
              </Badge>
            </div>
          </div>
          <Badge variant="outline" className="rounded-full">
            {actionModeLabel(item)}
          </Badge>
        </div>
      </div>
      <div className="grid gap-4 p-4 xl:grid-cols-2">
        <div className="rounded-md border bg-background p-4">
          <div className="mb-3 text-sm font-semibold">План действия</div>
          <div className="grid gap-3">
            {plan.steps.slice(0, 4).map((step, index) => (
              <div key={step.title} className="grid grid-cols-[28px_1fr] gap-3">
                <span className="flex h-7 w-7 items-center justify-center rounded-full bg-primary/10 text-xs font-semibold text-primary">
                  {index + 1}
                </span>
                <div className="min-w-0">
                  <div className="text-sm font-semibold">{step.title}</div>
                  <div className="mt-0.5 line-clamp-2 text-xs text-muted-foreground">
                    {step.description}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
        <div className="rounded-md border bg-background p-4">
          <div className="mb-3 text-sm font-semibold">Ожидаемый результат</div>
          <div className="space-y-2">
            <ProblemDetailMetric
              label="Финансовый эффект"
              value={
                resultMoney ? formatMoney(resultMoney) : "будет после пересчёта"
              }
              tone={resultMoney ? "success" : "neutral"}
            />
            <ProblemDetailMetric
              label="Режим выполнения"
              value={
                mode === "execute"
                  ? "Можно применить"
                  : mode === "inline"
                    ? "Исправление здесь"
                    : "Нужен шаг"
              }
              tone={
                mode === "execute" || mode === "inline" ? "success" : "warning"
              }
            />
            <ProblemDetailMetric
              label="Контроль"
              value="Проверка после обновления"
              tone="info"
            />
          </div>
          <div className="mt-4">
            <MiniTrendChart tone={plan.tone === "danger" ? "danger" : "info"} />
          </div>
        </div>
      </div>
    </div>
  );
}

function ProblemAnalysisPanel({ item }: { item: ActionCenterItem }) {
  const plan = actionDecisionPlan(item);
  const facts = actionDecisionFacts(item);
  const progress = solveProgress(item);
  return (
    <div className="grid gap-4 xl:grid-cols-2">
      <div className="rounded-md border bg-card p-4 shadow-sm">
        <div className="mb-3 text-sm font-semibold">Скорость и риск</div>
        <MiniTrendChart tone={plan.tone === "danger" ? "danger" : "info"} />
        <div className="mt-3 grid gap-2 sm:grid-cols-2">
          {facts.slice(0, 4).map((fact) => (
            <Fact
              key={fact.label}
              label={fact.label}
              value={fact.value}
              sub={null}
            />
          ))}
          {!facts.length ? (
            <Fact
              label="Сигнал"
              value={problemCodeLabel(actionCode(item))}
              sub={actionCode(item)}
            />
          ) : null}
        </div>
      </div>
      <div className="grid gap-4">
        <div className="rounded-md border bg-card p-4 shadow-sm">
          <div className="text-sm font-semibold">Корневая причина</div>
          <div className="mt-2 text-sm leading-relaxed text-muted-foreground">
            {plan.objective}
          </div>
        </div>
        <div className="rounded-md border bg-card p-4 shadow-sm">
          <div className="flex items-center justify-between gap-3">
            <div className="text-sm font-semibold">Рекомендация</div>
            <Badge variant="outline" className="rounded-full">
              {progress.done}/{progress.total}
            </Badge>
          </div>
          <div className="mt-2 text-sm leading-relaxed text-muted-foreground">
            {plan.subtitle}
          </div>
          <Progress value={progress.percent} className="mt-3 h-1.5" />
        </div>
      </div>
    </div>
  );
}

function ProblemHistoryPanel({ item }: { item: ActionCenterItem }) {
  const deadline = formatDeadline(item, new Date());
  return (
    <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_320px]">
      <EvidencePanel item={item} />
      <div className="space-y-4">
        <DataFreshness item={item} />
        <div className="rounded-md border bg-card p-4 shadow-sm">
          <div className="text-sm font-semibold">История состояния</div>
          <div className="mt-3 space-y-2 text-sm text-muted-foreground">
            <div className="rounded-md border bg-background px-3 py-2">
              Текущий статус:{" "}
              <span className="font-semibold text-foreground">
                {humanStatusLabel(item.status)}
              </span>
            </div>
            <div className="rounded-md border bg-background px-3 py-2">
              Результат:{" "}
              <span className="font-semibold text-foreground">
                {humanResultLabel(item.result_status)}
              </span>
            </div>
            <div className="rounded-md border bg-background px-3 py-2">
              Срок:{" "}
              <span className="font-semibold text-foreground">
                {deadline.detail
                  ? `${deadline.label}, ${deadline.detail}`
                  : deadline.label}
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function ProblemRelatedPanel({ item }: { item: ActionCenterItem }) {
  const plan = actionDecisionPlan(item);
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <div className="rounded-md border bg-card p-4 shadow-sm">
        <div className="text-sm font-semibold">Связанный товар</div>
        <div className="mt-3 flex gap-3">
          <ProductThumb
            candidates={itemImageCandidates(item)}
            label={itemProductTitle(item)}
            className="h-20 w-16"
          />
          <div className="min-w-0">
            <div className="line-clamp-2 text-sm font-semibold">
              {itemProductTitle(item)}
            </div>
            <div className="mt-1 text-xs text-muted-foreground">
              {objectLabel(item)}
            </div>
            <div className="mt-2 flex flex-wrap gap-1.5">
              <Badge variant="outline" className="rounded-full text-[10px]">
                {sourceModuleLabel(item.source_module)}
              </Badge>
              <Badge variant="outline" className="rounded-full text-[10px]">
                {problemCodeLabel(actionCode(item))}
              </Badge>
            </div>
          </div>
        </div>
      </div>
      <div className="rounded-md border bg-card p-4 shadow-sm">
        <div className="text-sm font-semibold">Что проверять рядом</div>
        <div className="mt-3 space-y-2">
          {plan.steps.map((step, index) => (
            <div key={step.title} className="grid grid-cols-[24px_1fr] gap-2">
              <span className="flex h-6 w-6 items-center justify-center rounded-full bg-muted text-xs font-semibold text-muted-foreground">
                {index + 1}
              </span>
              <div className="text-sm text-muted-foreground">
                <span className="font-semibold text-foreground">
                  {step.title}
                </span>{" "}
                {step.done}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function ActionSuccessPanel({
  item,
  hasNext,
  onNext,
}: {
  item: ActionCenterItem;
  hasNext: boolean;
  onNext: () => void;
}) {
  return (
    <div className="rounded-md border bg-card p-8 text-center shadow-sm">
      <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-full bg-emerald-500/10 text-emerald-700 dark:text-emerald-300">
        <CheckCircle2 className="h-8 w-8" />
      </div>
      <div className="mt-4 text-xl font-semibold">
        Действие выполнено успешно
      </div>
      <div className="mx-auto mt-2 max-w-md text-sm text-muted-foreground">
        {problemTitle(item)} закрыта в очереди. После следующей ежедневной
        проверки Action Center подтвердит результат на свежих данных.
      </div>
      <div className="mt-5 flex flex-wrap justify-center gap-2">
        <Button size="sm" onClick={onNext} disabled={!hasNext}>
          Следующая задача
          <ArrowRight className="h-3.5 w-3.5" />
        </Button>
        <Button asChild size="sm" variant="outline">
          <Link
            to="/results"
            search={{
              problem_instance_id: item.problem_instance_id
                ? String(item.problem_instance_id)
                : undefined,
            }}
          >
            Открыть результаты
            <BarChart3 className="h-3.5 w-3.5" />
          </Link>
        </Button>
      </div>
    </div>
  );
}

function FocusPanel({
  item,
  accountId,
  dateFrom,
  dateTo,
  busy,
  currentUserId,
  onStatus,
  onDoneNext,
  onRecheck,
  onChanged,
  onNext,
  hasNext,
}: {
  item: ActionCenterItem | null;
  accountId: number | null | undefined;
  dateFrom?: string | null;
  dateTo?: string | null;
  busy: string | null;
  currentUserId: number | null;
  onStatus: (
    item: ActionCenterItem,
    status: string,
    next?: boolean,
    options?: { deadline_at?: string; comment?: string },
  ) => void;
  onDoneNext: (item: ActionCenterItem) => void;
  onRecheck: (item: ActionCenterItem) => void;
  onChanged: () => Promise<void> | void;
  onNext: () => void;
  hasNext: boolean;
}) {
  const [tab, setTab] = useState<ProblemDetailTab>("action");
  useEffect(() => {
    setTab("action");
  }, [item?.id]);

  if (!item) {
    return (
      <div className="flex min-h-[420px] items-center justify-center rounded-md border bg-card p-8 text-center shadow-sm">
        <div className="max-w-sm space-y-3">
          <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-md bg-emerald-500/10 text-emerald-700 dark:text-emerald-300">
            <ShieldCheck className="h-6 w-6" />
          </div>
          <div className="text-lg font-semibold">
            По текущему фильтру проблем нет
          </div>
          <div className="text-sm text-muted-foreground">
            Снимите фильтр или дождитесь следующей синхронизации.
          </div>
        </div>
      </div>
    );
  }
  const primary = primaryActionForItem(item);
  const href = primary?.href ?? guidedFixHref(item) ?? null;
  const workLabel = primary?.code
    ? humanActionLabel(primary.code)
    : guidedFixLabel(item);
  const closed = isClosedAction(item);
  const mutationBusy = busy?.startsWith(item.id);
  const inline = hasInlineResolution(item);
  const manualTask = isManualTask(item);
  const resolution = manualTask ? (
    <ManualTaskResolutionPanel
      item={item}
      busy={Boolean(mutationBusy)}
      onStatus={onStatus}
      onDoneNext={onDoneNext}
      onNext={onNext}
    />
  ) : inline ? (
    <InlineResolutionPanel
      item={item}
      accountId={accountId}
      dateFrom={dateFrom}
      dateTo={dateTo}
      onChanged={onChanged}
      onRecheck={onRecheck}
      onNext={onNext}
    />
  ) : (
    <ActionDecisionResolutionPanel
      item={item}
      href={href}
      workLabel={workLabel || "Открыть"}
      busy={Boolean(mutationBusy)}
      onStatus={onStatus}
      onDoneNext={onDoneNext}
      onNext={onNext}
    />
  );
  return (
    <div className="space-y-4">
      <ProblemDetailHeader
        item={item}
        tab={tab}
        onTabChange={setTab}
        onNext={onNext}
        hasNext={hasNext}
      />

      {tab === "action" ? (
        <div className="space-y-4">
          {closed ? (
            <ActionSuccessPanel item={item} hasNext={hasNext} onNext={onNext} />
          ) : (
            <ActionPreviewPanel item={item} />
          )}
          {resolution}
        </div>
      ) : tab === "analysis" ? (
        <ProblemAnalysisPanel item={item} />
      ) : tab === "history" ? (
        <ProblemHistoryPanel item={item} />
      ) : (
        <ProblemRelatedPanel item={item} />
      )}
    </div>
  );
}

function ReferenceProblemDetailPage({
  item,
  group,
  accountId,
  dateFrom,
  dateTo,
  busy,
  onBack,
  onStatus,
  onDoneNext,
  onRecheck,
  onChanged,
  onNext,
  hasNext,
}: {
  item: ActionCenterItem | null;
  group: ProblemGroupSummary | null;
  accountId: number | null | undefined;
  dateFrom?: string | null;
  dateTo?: string | null;
  busy: string | null;
  onBack: () => void;
  onStatus: (
    item: ActionCenterItem,
    status: string,
    next?: boolean,
    options?: { deadline_at?: string; comment?: string },
  ) => void;
  onDoneNext: (item: ActionCenterItem) => void;
  onRecheck: (item: ActionCenterItem) => void;
  onChanged: () => Promise<void> | void;
  onNext: () => void;
  hasNext: boolean;
}) {
  const [tab, setTab] = useState<ProblemDetailTab>("analysis");

  useEffect(() => {
    setTab("analysis");
  }, [item?.id]);

  if (!item) {
    return (
      <div className="mx-auto flex min-h-[520px] w-full max-w-[1120px] items-center justify-center rounded-md border bg-card p-8 text-center shadow-sm">
        <div className="max-w-sm space-y-3">
          <CheckCircle2 className="mx-auto h-12 w-12 text-emerald-600" />
          <div className="text-lg font-semibold">Задач в группе нет</div>
          <div className="text-sm text-muted-foreground">
            Вернитесь к списку действий или обновите очередь.
          </div>
          <Button variant="outline" onClick={onBack}>
            <ArrowLeft className="h-4 w-4" />
            Назад
          </Button>
        </div>
      </div>
    );
  }

  const primary = primaryActionForItem(item);
  const href = primary?.href ?? guidedFixHref(item) ?? null;
  const workLabel = primary?.code
    ? humanActionLabel(primary.code)
    : guidedFixLabel(item);
  const closed = isClosedAction(item);
  const mutationBusy = busy?.startsWith(item.id);
  const inline = hasInlineResolution(item);
  const manualTask = isManualTask(item);
  const plan = actionDecisionPlan(item);
  const facts = actionDecisionFacts(item);
  const money = moneyFromUnknown(item.money_impact_amount);
  const deadline = formatDeadline(item, new Date());
  const statFacts = [
    {
      label: "Эффект/риск",
      value: money ? formatMoney(Math.abs(money)) : "—",
      tone: money ? "danger" : "neutral",
    },
    {
      label: "Следующий шаг",
      value: plan.workLabel,
      tone:
        actionExecutionMode(item) === "inline" ||
        actionExecutionMode(item) === "execute"
          ? "success"
          : "info",
    },
    {
      label: "Срок",
      value: deadline.detail
        ? `${deadline.label}, ${deadline.detail}`
        : deadline.label,
      tone: isOverdueAction(item) ? "danger" : "neutral",
    },
    ...facts
      .filter((fact) => !["Эффект/риск", "Товар"].includes(fact.label))
      .slice(0, 2)
      .map((fact) => ({
        label: fact.label,
        value: fact.value,
        tone: fact.tone ?? "neutral",
      })),
  ].slice(0, 5);
  const resolution = manualTask ? (
    <ManualTaskResolutionPanel
      item={item}
      busy={Boolean(mutationBusy)}
      onStatus={onStatus}
      onDoneNext={onDoneNext}
      onNext={onNext}
    />
  ) : inline ? (
    <InlineResolutionPanel
      item={item}
      accountId={accountId}
      dateFrom={dateFrom}
      dateTo={dateTo}
      onChanged={onChanged}
      onRecheck={onRecheck}
      onNext={onNext}
    />
  ) : (
    <ActionDecisionResolutionPanel
      item={item}
      href={href}
      workLabel={workLabel || "Открыть"}
      busy={Boolean(mutationBusy)}
      onStatus={onStatus}
      onDoneNext={onDoneNext}
      onNext={onNext}
    />
  );

  return (
    <div className="mx-auto w-full max-w-[1120px] space-y-4">
      <section className="overflow-hidden rounded-md border bg-card shadow-sm">
        <div className="flex flex-col gap-3 border-b px-5 py-4 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex min-w-0 flex-wrap items-center gap-3">
            <Button variant="ghost" size="sm" onClick={onBack}>
              <ArrowLeft className="h-4 w-4" />
              Назад
            </Button>
            <PriorityBadge item={item} />
            <h1 className="min-w-0 text-xl font-semibold leading-tight">
              {problemTitle(item)}
            </h1>
          </div>
          <div className="flex flex-wrap gap-2">
            <Badge
              variant="outline"
              className={`rounded-full ${actionStateTone(item)}`}
            >
              {actionModeLabel(item)}
            </Badge>
            {group ? (
              <Badge variant="secondary" className="rounded-full">
                {group.title}
              </Badge>
            ) : null}
            <Button
              variant="ghost"
              size="sm"
              onClick={onNext}
              disabled={!hasNext}
            >
              Далее
              <ArrowRight className="h-4 w-4" />
            </Button>
          </div>
        </div>

        <div className="px-5 py-4">
          <div className="text-sm leading-relaxed text-muted-foreground">
            {item.short_explanation ||
              item.reason ||
              item.next_step ||
              problemCodeLabel(actionCode(item))}
          </div>

          <div className="mt-4 overflow-hidden rounded-md border bg-muted/10">
            <div className="grid gap-0 md:grid-cols-[260px_repeat(4,minmax(0,1fr))]">
              <div className="flex min-w-0 items-center gap-3 border-b p-4 md:border-b-0 md:border-r">
                <ProductThumb
                  candidates={itemImageCandidates(item)}
                  label={itemProductTitle(item)}
                  className="h-16 w-16 rounded-md"
                />
                <div className="min-w-0">
                  <div className="line-clamp-2 text-sm font-semibold">
                    {itemProductTitle(item)}
                  </div>
                  <div className="mt-1 truncate text-xs text-muted-foreground">
                    {objectLabel(item)}
                  </div>
                </div>
              </div>
              {statFacts.slice(0, 4).map((fact) => (
                <ProblemDetailMetric
                  key={fact.label}
                  label={fact.label}
                  value={fact.value}
                  tone={fact.tone}
                />
              ))}
            </div>
          </div>
        </div>
        <ProblemDetailTabs value={tab} onChange={setTab} />
      </section>

      {tab === "action" ? (
        <div className="space-y-4">
          {closed ? (
            <ActionSuccessPanel item={item} hasNext={hasNext} onNext={onNext} />
          ) : (
            <ActionPreviewPanel item={item} />
          )}
          {!closed ? resolution : null}
        </div>
      ) : tab === "analysis" ? (
        <ProblemAnalysisPanel item={item} />
      ) : tab === "history" ? (
        <ProblemHistoryPanel item={item} />
      ) : (
        <ProblemRelatedPanel item={item} />
      )}
    </div>
  );
}

function SummaryBar({
  mode,
  total,
  open,
  closed,
  urgent,
  overdue,
  actionable,
  blocked,
  moneyAtStake,
  filtered,
}: {
  mode: TaskBoardMode;
  total: number;
  open: number;
  closed: number;
  urgent: number;
  overdue: number;
  actionable: number;
  blocked: number;
  moneyAtStake: number;
  filtered: number;
}) {
  const percent =
    mode === "active"
      ? total > 0
        ? Math.round((closed / total) * 100)
        : 100
      : 100;
  const items = [
    {
      label:
        mode === "completed"
          ? "Выполнено"
          : mode === "deactivated"
            ? "Скрыто"
            : "Открыто",
      value: mode === "active" ? open : total,
      tone: "text-foreground",
    },
    {
      label: "Срочно",
      value: urgent,
      tone: urgent ? "text-red-700 dark:text-red-300" : "text-muted-foreground",
    },
    {
      label: "Просрочено",
      value: overdue,
      tone: overdue
        ? "text-red-700 dark:text-red-300"
        : "text-muted-foreground",
    },
    {
      label: "Требует решения",
      value: actionable,
      tone: "text-sky-700 dark:text-sky-300",
    },
    {
      label: "Блокеры",
      value: blocked,
      tone: blocked
        ? "text-amber-700 dark:text-amber-300"
        : "text-muted-foreground",
    },
    {
      label: "Оценка сигналов",
      value: moneyAtStake ? formatMoney(moneyAtStake) : "—",
      tone: moneyAtStake
        ? "text-red-700 dark:text-red-300"
        : "text-muted-foreground",
    },
    { label: "В выборке", value: filtered, tone: "text-muted-foreground" },
  ];
  return (
    <div className="rounded-md border bg-card px-4 py-3 shadow-sm">
      <div className="flex flex-col gap-3 xl:flex-row xl:items-center">
        <div className="min-w-[220px] xl:w-[260px]">
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-2 text-sm font-semibold">
              <Gauge className="h-4 w-4 text-primary" />
              {taskBoardModeTitle(mode)}
            </div>
            <span className="text-sm font-semibold">{percent}%</span>
          </div>
          <Progress value={percent} className="mt-2 h-1.5" />
        </div>
        <div className="grid min-w-0 flex-1 grid-cols-2 gap-x-4 gap-y-2 sm:grid-cols-4 xl:grid-cols-7">
          {items.map((item) => (
            <div key={item.label} className="min-w-0">
              <div className="truncate text-[11px] text-muted-foreground">
                {item.label}
              </div>
              <div className={`truncate text-sm font-semibold ${item.tone}`}>
                {item.value}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function GroupRowMetric({
  label,
  value,
  tone = "text-foreground",
}: {
  label: string;
  value: React.ReactNode;
  tone?: string;
}) {
  return (
    <div className="min-w-0">
      <div className="text-[10px] leading-tight text-muted-foreground lg:hidden">
        {label}
      </div>
      <div className={`mt-0.5 truncate text-sm font-semibold lg:mt-0 ${tone}`}>
        {value}
      </div>
    </div>
  );
}

function GroupHeaderMetric({
  label,
  value,
  tone = "text-foreground",
}: {
  label: string;
  value: React.ReactNode;
  tone?: string;
}) {
  return (
    <div className="rounded-md border bg-background px-3 py-2">
      <div className="truncate text-[11px] leading-tight text-muted-foreground">
        {label}
      </div>
      <div className={`mt-0.5 truncate text-sm font-semibold ${tone}`}>
        {value}
      </div>
    </div>
  );
}

function TaskMonitoringTabs({
  mode,
  counts,
  onChange,
}: {
  mode: TaskBoardMode;
  counts: Record<TaskBoardMode, number>;
  onChange: (mode: TaskBoardMode) => void;
}) {
  const tabs: Array<{
    value: TaskBoardMode;
    label: string;
    icon: React.ReactNode;
  }> = [
    {
      value: "active",
      label: "Активные",
      icon: <Activity className="h-4 w-4" />,
    },
    {
      value: "completed",
      label: "Выполненные",
      icon: <CheckCircle2 className="h-4 w-4" />,
    },
    {
      value: "deactivated",
      label: "Деактивированные",
      icon: <SkipForward className="h-4 w-4" />,
    },
  ];
  return (
    <div className="rounded-md border bg-card px-2 py-2 shadow-sm">
      <div className="flex gap-1 overflow-x-auto [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
        {tabs.map((tab) => {
          const active = mode === tab.value;
          return (
            <button
              key={tab.value}
              type="button"
              onClick={() => onChange(tab.value)}
              className={`flex h-9 shrink-0 items-center gap-2 rounded-md px-3 text-sm font-semibold transition-colors ${
                active
                  ? "bg-primary text-primary-foreground shadow-sm"
                  : "text-muted-foreground hover:bg-muted hover:text-foreground"
              }`}
            >
              {tab.icon}
              <span>{tab.label}</span>
              <span
                className={`rounded-full px-2 py-0.5 text-xs ${
                  active
                    ? "bg-primary-foreground/18 text-primary-foreground"
                    : "bg-muted text-foreground"
                }`}
              >
                {counts[tab.value] ?? 0}
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}

function CompactFilterPanel({
  filters,
  updateFilters,
  resetFilters,
  canUseBeta,
}: {
  filters: ActionCenterFilterState;
  updateFilters: (patch: Partial<ActionCenterFilterState>) => void;
  resetFilters: () => void;
  canUseBeta: boolean;
}) {
  const count = activeFilterCount(filters);
  return (
    <section className="overflow-hidden rounded-md border bg-card shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b bg-muted/10 px-4 py-3">
        <div className="flex min-w-0 items-center gap-3">
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md border bg-background text-primary">
            <SlidersHorizontal className="h-4 w-4" />
          </span>
          <div className="min-w-0">
            <div className="text-sm font-semibold">Фильтры и управление</div>
            <div className="truncate text-xs text-muted-foreground">
              {filters.q
                ? `Поиск: ${filters.q}`
                : count
                  ? `${count} активных фильтров`
                  : "Показаны все задачи выбранного режима"}
            </div>
          </div>
        </div>
        {count ? (
          <Badge variant="secondary" className="rounded-full">
            {count} активно
          </Badge>
        ) : (
          <Badge variant="outline" className="rounded-full">
            без ограничений
          </Badge>
        )}
      </div>
      <div className="p-3">
        <ActionCenterFilterDock
          filters={filters}
          updateFilters={updateFilters}
          resetFilters={resetFilters}
          canUseBeta={canUseBeta}
        />
      </div>
    </section>
  );
}

const DATA_HEALTH_DOMAIN_LABELS: Record<string, string> = {
  finance: "финансы",
  orders: "заказы",
  sales: "продажи",
  stocks: "остатки",
  stock: "остатки",
  ads: "реклама",
  advertising: "реклама",
  adverts: "реклама",
  prices: "цены",
  costs: "себестоимость",
  cost: "себестоимость",
  reputation: "репутация",
  logistics: "логистика",
};

function dataHealthDomainLabel(domain: unknown): string {
  const key = norm(domain);
  return DATA_HEALTH_DOMAIN_LABELS[key] ?? String(domain ?? "данные");
}

function dataHealthProblemLabel(row: any): string {
  const freshness = norm(row?.freshness_status);
  if (freshness === "failed" || norm(row?.status) === "failed") {
    return "ошибка";
  }
  if (freshness === "stale") return "устарели";
  if (freshness === "missing") return "нет данных";
  if (row?.permission_ok === false || row?.token_ok === false) {
    return "нет доступа";
  }
  return "проверить";
}

function dataHealthProblemDomains(
  status?: DataSyncStatusResponse | null,
): any[] {
  if (!status?.domains?.length) return [];
  return status.domains.filter((row) => {
    const freshness = norm(row.freshness_status);
    const state = norm(row.status);
    return (
      ["failed", "stale", "missing"].includes(freshness) ||
      ["failed", "error"].includes(state) ||
      row.permission_ok === false ||
      row.token_ok === false
    );
  });
}

function dataHealthWarningText(value: unknown): string {
  const text = String(value ?? "").trim();
  if (!text) return "";
  const lower = text.toLowerCase();
  if (lower.includes("money sources")) {
    return "Источники денег расходятся по времени. Эффект считается предварительным до синхронизации.";
  }
  if (lower.includes("finance") && lower.includes("orders")) {
    return "Финансы и заказы не синхронизированы за один период. Сначала обновите данные.";
  }
  if (lower.includes("429")) {
    return "WB временно ограничил часть запросов. Повторите синхронизацию позже.";
  }
  if (lower.includes("token")) {
    return "Для части источников не хватает доступа. Проверьте токены WB.";
  }
  return text;
}

function ActionCenterDataHealthBanner({
  status,
}: {
  status?: DataSyncStatusResponse | null;
}) {
  const badDomains = dataHealthProblemDomains(status);
  const alignment = norm(status?.data_alignment_status);
  const overall = norm(status?.overall_state);
  const warnings = status?.data_alignment_warnings ?? status?.warnings ?? [];
  const shouldShow =
    Boolean(status) &&
    (badDomains.length > 0 ||
      ["failed", "warning"].includes(overall) ||
      (alignment && !["aligned", "ok"].includes(alignment)));
  if (!shouldShow) return null;
  const shown = badDomains.slice(0, 5);
  return (
    <Alert className="border-amber-500/35 bg-amber-500/5">
      <AlertTriangle className="h-4 w-4 text-amber-700 dark:text-amber-300" />
      <AlertTitle>Данные частично ненадёжны</AlertTitle>
      <AlertDescription>
        <div className="mt-1 flex flex-wrap items-center gap-2 text-sm">
          <span>
            Action Center сейчас показывает рабочие сигналы. Финальный эффект
            подтверждается после синхронизации и перепроверки.
          </span>
          {alignment && alignment !== "aligned" ? (
            <Badge
              variant="outline"
              className="rounded-full border-amber-500/35 bg-background"
            >
              сверка: {alignment}
            </Badge>
          ) : null}
          {shown.map((row) => (
            <Badge
              key={`${row.domain}-${row.freshness_status}-${row.status}`}
              variant="outline"
              className="rounded-full border-amber-500/35 bg-background"
            >
              {dataHealthDomainLabel(row.domain)}: {dataHealthProblemLabel(row)}
            </Badge>
          ))}
          {badDomains.length > shown.length ? (
            <Badge variant="outline" className="rounded-full bg-background">
              ещё {badDomains.length - shown.length}
            </Badge>
          ) : null}
        </div>
        {warnings.length ? (
          <div className="mt-2 text-xs text-muted-foreground">
            {dataHealthWarningText(warnings[0])}
          </div>
        ) : null}
      </AlertDescription>
    </Alert>
  );
}

function BusinessCasesStrip({ cases }: { cases: ActionBusinessCase[] }) {
  if (!cases.length) return null;
  const rawSignalMoney = cases.reduce(
    (sum, item) => sum + item.rawSignalMoney,
    0,
  );
  const objectMoney = cases.reduce((sum, item) => sum + item.money, 0);
  const overlap = Math.max(0, rawSignalMoney - objectMoney);
  return (
    <section className="overflow-hidden rounded-md border bg-card shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-3 border-b bg-muted/15 px-3 py-2">
        <div>
          <div className="text-sm font-semibold">
            Связанные сигналы по товарам
          </div>
          <div className="text-xs text-muted-foreground">
            Если один товар попал в несколько проверок, работаем как с одним
            бизнес-кейсом и не складываем эффект вслепую.
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <Badge variant="outline" className="rounded-full">
            {cases.length} товаров
          </Badge>
          {overlap ? (
            <Badge
              variant="outline"
              className="rounded-full border-amber-500/35 bg-amber-500/10 text-amber-800 dark:text-amber-300"
            >
              пересечение {formatMoneyCompact(overlap)}
            </Badge>
          ) : null}
        </div>
      </div>
      <div className="grid divide-y md:grid-cols-3 md:divide-x md:divide-y-0">
        {cases.slice(0, 3).map((item) => (
          <div key={item.key} className="min-w-0 p-3">
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <div className="truncate text-sm font-semibold">
                  {item.objectLabel}
                </div>
                <div className="mt-0.5 line-clamp-2 text-xs text-muted-foreground">
                  {item.title}
                </div>
              </div>
              <Badge variant="secondary" className="shrink-0 rounded-full">
                {item.count}
              </Badge>
            </div>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {item.topCodes.map((code) => (
                <span
                  key={code.code}
                  className="rounded-full bg-muted px-2 py-0.5 text-[10px] font-medium text-muted-foreground"
                >
                  {code.label} · {code.count}
                </span>
              ))}
            </div>
            <div className="mt-2 text-xs text-muted-foreground">
              Эффект кейса до {formatMoneyCompact(item.money)}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

function scenarioCoverageStatusLabel(status: ScenarioCoverageStatus): string {
  return {
    live: "работает",
    partial: "частично",
    missing: "нет",
  }[status];
}

function scenarioCoverageModeLabel(mode: ScenarioCoverageMode): string {
  return {
    platform: "в платформе",
    review: "через review",
    manual: "ручной шаг",
    planned: "добавить",
  }[mode];
}

function scenarioCoverageStatusClass(status: ScenarioCoverageStatus): string {
  return {
    live: "border-emerald-500/35 bg-emerald-500/10 text-emerald-800 dark:text-emerald-200",
    partial:
      "border-amber-500/35 bg-amber-500/10 text-amber-800 dark:text-amber-200",
    missing:
      "border-slate-300 bg-slate-100 text-slate-600 dark:border-slate-700 dark:bg-slate-900/60 dark:text-slate-300",
  }[status];
}

function scenarioCoverageMatchesItem(
  scenario: V1ScenarioCoverageItem,
  item: ActionCenterItem,
): boolean {
  const payload = item.payload ?? {};
  const raw = item.raw ?? {};
  const text = [
    actionCode(item),
    item.action_type,
    item.detector_code,
    item.problem_code,
    item.issue_code,
    item.title,
    item.reason,
    item.source_module,
    payload.problem_code,
    payload.detector_code,
    payload.issue_code,
    payload.code,
    payload.category,
    payload.field_name,
    payload.field_path,
    raw.problem_code,
    raw.detector_code,
    raw.issue_code,
    raw.code,
    raw.category,
  ]
    .map(norm)
    .join(" ");
  return scenario.codes.some((code) => {
    const normalized = norm(code);
    return normalized && text.includes(normalized);
  });
}

function ScenarioCoveragePanel({
  items,
  groups,
}: {
  items: ActionCenterItem[];
  groups: ProblemGroupSummary[];
}) {
  const [expanded, setExpanded] = useState(false);
  const groupOpen = new Map(groups.map((group) => [group.key, group.open]));
  const scenarioRows = ACTION_CENTER_V1_SCENARIO_CATALOG.map((scenario) => ({
    ...scenario,
    active: items.filter((item) => scenarioCoverageMatchesItem(scenario, item))
      .length,
  }));
  const statusCounts = scenarioRows.reduce(
    (acc, scenario) => {
      acc[scenario.status] += 1;
      return acc;
    },
    { live: 0, partial: 0, missing: 0 } as Record<
      ScenarioCoverageStatus,
      number
    >,
  );
  const domainRows = PROBLEM_GROUP_ORDER.filter(
    (key) => key !== "manual_tasks" && key !== "other",
  )
    .map((key) => {
      const scenarios = scenarioRows.filter(
        (scenario) => scenario.group === key,
      );
      if (!scenarios.length) return null;
      const live = scenarios.filter(
        (scenario) => scenario.status === "live",
      ).length;
      const partial = scenarios.filter(
        (scenario) => scenario.status === "partial",
      ).length;
      const missing = scenarios.filter(
        (scenario) => scenario.status === "missing",
      ).length;
      return {
        key,
        scenarios,
        live,
        partial,
        missing,
        open: groupOpen.get(key) ?? 0,
      };
    })
    .filter(Boolean);
  const attentionRows = scenarioRows.filter(
    (scenario) => scenario.status !== "live" || scenario.active > 0,
  );

  return (
    <section className="overflow-hidden rounded-md border bg-card shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b bg-muted/15 px-3 py-2">
        <div className="flex min-w-0 items-center gap-2">
          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-primary/10 text-primary">
            <ClipboardCheck className="h-4 w-4" />
          </div>
          <div className="min-w-0">
            <div className="text-sm font-semibold">Покрытие сценариев V1</div>
            <div className="text-xs text-muted-foreground">
              48 бизнес-сценариев: что уже детектируется и где нужен следующий
              шаг в системе.
            </div>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          <Badge
            variant="outline"
            className={`rounded-full ${scenarioCoverageStatusClass("live")}`}
          >
            работает {statusCounts.live}
          </Badge>
          <Badge
            variant="outline"
            className={`rounded-full ${scenarioCoverageStatusClass("partial")}`}
          >
            частично {statusCounts.partial}
          </Badge>
          <Badge
            variant="outline"
            className={`rounded-full ${scenarioCoverageStatusClass("missing")}`}
          >
            нет {statusCounts.missing}
          </Badge>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="h-8 gap-1.5 px-2"
            onClick={() => setExpanded((value) => !value)}
            aria-expanded={expanded}
          >
            {expanded ? "Свернуть" : "Детали"}
            <ChevronDown
              className={`h-3.5 w-3.5 transition-transform ${expanded ? "rotate-180" : ""}`}
            />
          </Button>
        </div>
      </div>

      {expanded ? (
        <div className="border-t bg-muted/10 p-3">
          <div className="mb-3 grid divide-y overflow-hidden rounded-md border bg-card md:grid-cols-4 md:divide-x md:divide-y-0">
            {domainRows.map((row) => {
              const cfg = PROBLEM_GROUP_CONFIG[row.key];
              const readyPct = row.scenarios.length
                ? Math.round(
                    ((row.live + row.partial * 0.5) / row.scenarios.length) *
                      100,
                  )
                : 0;
              return (
                <div key={row.key} className="min-w-0 px-3 py-2">
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex min-w-0 items-center gap-2">
                      <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md border bg-background text-primary">
                        {cfg.icon}
                      </span>
                      <div className="min-w-0">
                        <div className="line-clamp-2 text-sm font-semibold leading-tight">
                          {cfg.title}
                        </div>
                        <div className="text-[11px] text-muted-foreground">
                          задач {formatNumber(row.open)}
                        </div>
                      </div>
                    </div>
                    <span className="text-xs font-semibold">{readyPct}%</span>
                  </div>
                  <Progress value={readyPct} className="mt-2 h-1" />
                  <div className="mt-2 flex flex-wrap gap-1">
                    <span className="rounded-full bg-emerald-500/10 px-1.5 py-0.5 text-[10px] font-medium text-emerald-700 dark:text-emerald-300">
                      {row.live}
                    </span>
                    <span className="rounded-full bg-amber-500/10 px-1.5 py-0.5 text-[10px] font-medium text-amber-700 dark:text-amber-300">
                      {row.partial}
                    </span>
                    <span className="rounded-full bg-muted px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground">
                      {row.missing}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
          <div className="grid gap-2 lg:grid-cols-2 xl:grid-cols-3">
            {attentionRows.map((scenario) => (
              <div
                key={scenario.id}
                className="flex min-w-0 items-start justify-between gap-3 rounded-md border bg-background px-3 py-2"
              >
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-1.5">
                    <Badge
                      variant="outline"
                      className={`rounded-full text-[10px] ${scenarioCoverageStatusClass(scenario.status)}`}
                    >
                      {scenarioCoverageStatusLabel(scenario.status)}
                    </Badge>
                    <Badge
                      variant="outline"
                      className="rounded-full text-[10px]"
                    >
                      {scenarioCoverageModeLabel(scenario.mode)}
                    </Badge>
                    {scenario.active ? (
                      <Badge
                        variant="secondary"
                        className="rounded-full text-[10px]"
                      >
                        сейчас {scenario.active}
                      </Badge>
                    ) : null}
                  </div>
                  <div className="mt-1 line-clamp-2 text-sm font-medium">
                    {scenario.title}
                  </div>
                  <div className="mt-1 truncate text-[11px] text-muted-foreground">
                    {PROBLEM_GROUP_CONFIG[scenario.group].title}
                  </div>
                </div>
                {scenario.status === "live" ? (
                  <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-600" />
                ) : scenario.status === "partial" ? (
                  <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-600" />
                ) : (
                  <Lock className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
                )}
              </div>
            ))}
          </div>
        </div>
      ) : null}
    </section>
  );
}

function ActionCenterMissionBar({
  mode,
  counts,
  open,
  urgent,
  execution,
  blocked,
  overdue,
  moneyAtStake,
  onModeChange,
}: {
  mode: TaskBoardMode;
  counts: Record<TaskBoardMode, number>;
  open: number;
  urgent: number;
  execution: ActionExecutionSummary;
  blocked: number;
  overdue: number;
  moneyAtStake: number;
  onModeChange: (mode: TaskBoardMode) => void;
}) {
  const total = Math.max(counts.active + counts.completed, open);
  const progress =
    total > 0 ? Math.round((counts.completed / total) * 100) : 100;
  const tabs: Array<{
    value: TaskBoardMode;
    label: string;
    icon: React.ReactNode;
  }> = [
    {
      value: "active",
      label: "В работе",
      icon: <Activity className="h-4 w-4" />,
    },
    {
      value: "completed",
      label: "Готово",
      icon: <CheckCircle2 className="h-4 w-4" />,
    },
    {
      value: "deactivated",
      label: "Скрыто",
      icon: <SkipForward className="h-4 w-4" />,
    },
  ];
  const needsUserStep = execution.decision + execution.manual;
  const signalOnly = execution.signal;
  return (
    <section className="overflow-hidden rounded-md border bg-card shadow-sm">
      <div className="flex flex-col gap-4 border-b px-4 py-4 xl:flex-row xl:items-center xl:justify-between">
        <div className="min-w-0">
          <div className="flex items-center gap-3">
            <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md border bg-primary/10 text-primary">
              <Gauge className="h-4 w-4" />
            </span>
            <div className="min-w-0">
              <div className="text-base font-semibold">Фокус на сегодня</div>
              <div className="text-sm text-muted-foreground">
                Закрывайте задачи по очереди: сначала блокеры данных, затем
                действия с деньгами, остатками, рекламой и карточками.
              </div>
            </div>
          </div>
        </div>
        <div className="flex w-full gap-1 rounded-md border bg-muted/20 p-1 sm:w-auto">
          {tabs.map((tab) => {
            const active = mode === tab.value;
            return (
              <button
                key={tab.value}
                type="button"
                onClick={() => onModeChange(tab.value)}
                className={`flex h-9 flex-1 items-center justify-center gap-2 rounded-md px-3 text-xs font-semibold transition-colors sm:flex-none ${
                  active
                    ? "bg-primary text-primary-foreground shadow-sm"
                    : "text-muted-foreground hover:bg-background hover:text-foreground"
                }`}
              >
                {tab.icon}
                <span>{tab.label}</span>
                <span
                  className={`rounded-full px-1.5 py-0.5 ${
                    active
                      ? "bg-primary-foreground/20"
                      : "bg-background text-foreground"
                  }`}
                >
                  {counts[tab.value] ?? 0}
                </span>
              </button>
            );
          })}
        </div>
      </div>
      <div className="grid divide-y sm:grid-cols-2 sm:divide-x sm:divide-y-0 xl:grid-cols-4">
        <OverviewStatCard
          label="Нужно решить"
          value={open}
          hint={`${urgent} срочно, ${overdue} просрочено`}
          icon={<AlertTriangle className="h-4 w-4" />}
          tone={urgent || overdue ? "danger" : "neutral"}
        />
        <OverviewStatCard
          label="Можно применить"
          value={execution.execute + execution.inline}
          hint={`${execution.inline} в этом экране, ${execution.execute} после проверки`}
          icon={<CheckCircle2 className="h-4 w-4" />}
          tone={execution.execute + execution.inline ? "success" : "neutral"}
        />
        <OverviewStatCard
          label="Нужно разобрать"
          value={needsUserStep + blocked}
          hint={`действие ${needsUserStep}, данные ${blocked}, проверить ${signalOnly}`}
          icon={<ClipboardList className="h-4 w-4" />}
          tone={blocked || needsUserStep ? "warning" : "neutral"}
        />
        <OverviewStatCard
          label="Оценка без дублей"
          value={moneyAtStake ? formatMoneyCompact(moneyAtStake) : "—"}
          hint="до финальной сверки WB"
          icon={<TrendingUp className="h-4 w-4" />}
          tone={moneyAtStake ? "danger" : "neutral"}
        />
      </div>
      <div className="flex flex-col gap-2 border-t bg-muted/10 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="text-sm font-medium">
          Прогресс очереди: <span className="font-semibold">{progress}%</span>
        </div>
        <div className="flex min-w-0 flex-1 items-center gap-3 sm:max-w-md">
          <Progress value={progress} className="h-2" />
          <span className="shrink-0 text-xs text-muted-foreground">
            {counts.completed} выполнено
          </span>
        </div>
      </div>
    </section>
  );
}

function MissionMetric({
  label,
  value,
  tone,
}: {
  label: string;
  value: React.ReactNode;
  tone: "danger" | "warning" | "success" | "muted";
}) {
  const toneClass =
    tone === "danger"
      ? "text-red-700 dark:text-red-300"
      : tone === "warning"
        ? "text-amber-800 dark:text-amber-300"
        : tone === "success"
          ? "text-emerald-700 dark:text-emerald-300"
          : "text-muted-foreground";
  return (
    <div className="rounded-md border bg-muted/15 px-3 py-2">
      <div className="text-[11px] font-medium text-muted-foreground">
        {label}
      </div>
      <div
        className={`mt-0.5 text-sm font-semibold leading-tight ${toneClass}`}
      >
        {value}
      </div>
    </div>
  );
}

function OverviewStatCard({
  label,
  value,
  hint,
  icon,
  tone = "neutral",
}: {
  label: string;
  value: React.ReactNode;
  hint: string;
  icon: React.ReactNode;
  tone?: "danger" | "warning" | "success" | "info" | "neutral";
}) {
  const toneClass =
    tone === "danger"
      ? "bg-red-500/10 text-red-700 dark:text-red-300"
      : tone === "warning"
        ? "bg-amber-500/10 text-amber-800 dark:text-amber-300"
        : tone === "success"
          ? "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300"
          : tone === "info"
            ? "bg-sky-500/10 text-sky-700 dark:text-sky-300"
            : "bg-muted text-muted-foreground";
  return (
    <div className="min-w-0 border-l px-4 py-3 first:border-l-0">
      <div className="flex items-start gap-3">
        <span
          className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-md ${toneClass}`}
        >
          {icon}
        </span>
        <div className="min-w-0">
          <div className="truncate text-2xl font-semibold leading-none tracking-tight">
            {value}
          </div>
          <div className="mt-1 truncate text-sm font-semibold">{label}</div>
          <div className="mt-0.5 line-clamp-2 text-xs text-muted-foreground">
            {hint}
          </div>
        </div>
      </div>
    </div>
  );
}

function MiniImpactDonut({
  groups,
}: {
  groups: ProblemGroupSummary[];
}) {
  const colors = [
    "#0f766e",
    "#dc2626",
    "#0891b2",
    "#2563eb",
    "#9333ea",
    "#ea580c",
    "#ec4899",
    "#64748b",
  ];
  const activeGroups = groups.filter((group) => group.open > 0);
  const total = activeGroups.reduce((sum, group) => sum + group.open, 0);
  const mainRows = activeGroups.slice(0, 8);
  const otherOpen = Math.max(
    0,
    total - mainRows.reduce((sum, group) => sum + group.open, 0),
  );
  const rows = [
    ...mainRows,
    ...(otherOpen
      ? [
          {
            ...PROBLEM_GROUP_CONFIG.other,
            key: "other" as ProblemGroupKey,
            items: [],
            open: otherOpen,
            closed: 0,
            urgent: 0,
            blockers: 0,
            actionable: 0,
            execution: emptyActionExecutionSummary(),
            money: 0,
            progress: 0,
            topCodes: [],
          },
        ]
      : []),
  ]
    .map((group, index) => ({
      ...group,
      color: colors[index % colors.length],
    }));
  let cursor = 0;
  const slices = rows.map((group) => {
    const start = cursor;
    const end = total ? start + (group.open / total) * 100 : start;
    cursor = end;
    return `${group.color} ${start}% ${end}%`;
  });
  const background = slices.length
    ? `conic-gradient(${slices.join(", ")})`
    : "var(--muted)";
  return (
    <div className="grid gap-4 sm:grid-cols-[120px_minmax(0,1fr)] sm:items-center">
      <div
        className="relative mx-auto h-28 w-28 rounded-full border shadow-inner"
        style={{ background }}
      >
        <div className="absolute inset-5 flex flex-col items-center justify-center rounded-full border bg-card text-center">
          <span className="text-lg font-semibold">{total}</span>
          <span className="text-[10px] text-muted-foreground">открыто</span>
        </div>
      </div>
      <div className="space-y-2">
        {rows.length ? (
          rows.map((group) => {
            const pct = total ? Math.round((group.open / total) * 100) : 0;
            return (
              <div
                key={group.key}
                className="grid grid-cols-[10px_minmax(0,1fr)_auto] items-center gap-2 text-xs"
              >
                <span
                  className="h-2.5 w-2.5 rounded-full"
                  style={{ backgroundColor: group.color }}
                />
                <span className="truncate text-muted-foreground">
                  {group.title}
                </span>
                <span className="font-semibold">{pct}%</span>
              </div>
            );
          })
        ) : (
          <div className="text-sm text-muted-foreground">Активных групп нет</div>
        )}
      </div>
    </div>
  );
}

function ActionCenterTodayOverview({
  items,
  groups,
  onOpenGroup,
}: {
  items: ActionCenterItem[];
  groups: ProblemGroupSummary[];
  onOpenGroup: (key: ProblemGroupKey) => void;
}) {
  const topItems = sortByBusinessPriority(
    items.filter((item) => !isClosedAction(item)),
  ).slice(0, 5);
  const distributionRows = groups.filter((group) => group.open > 0).slice(0, 7);
  if (!topItems.length && !distributionRows.length) return null;
  return (
    <section className="grid gap-4 xl:grid-cols-[minmax(0,1.55fr)_360px]">
      <div className="overflow-hidden rounded-md border bg-card shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b px-4 py-3">
          <div>
            <div className="text-base font-semibold">
              Топ действий на сегодня
            </div>
            <div className="text-xs text-muted-foreground">
              Первые задачи отсортированы по приоритету, блокерам и денежному
              риску.
            </div>
          </div>
          <Badge variant="outline" className="rounded-full">
            {topItems.length} в фокусе
          </Badge>
        </div>
        <div className="divide-y">
          {topItems.map((item) => {
            const groupKey = problemGroupKey(item);
            const cfg = PROBLEM_GROUP_CONFIG[groupKey];
            const money = moneyFromUnknown(item.money_impact_amount);
            return (
              <button
                key={item.id}
                type="button"
                onClick={() => onOpenGroup(groupKey)}
                className="grid w-full gap-3 px-4 py-3 text-left transition-colors hover:bg-muted/25 md:grid-cols-[118px_minmax(0,1fr)_220px_96px_32px] md:items-center"
              >
                <div className="flex flex-wrap items-center gap-1.5">
                  <PriorityBadge item={item} />
                  <Badge
                    variant="outline"
                    className={`rounded-full text-[10px] ${actionStateTone(item)}`}
                  >
                    {actionStateLabel(item)}
                  </Badge>
                </div>
                <div className="min-w-0">
                  <div className="line-clamp-1 text-sm font-semibold">
                    {problemTitle(item)}
                  </div>
                  <div className="mt-0.5 line-clamp-1 text-xs text-muted-foreground">
                    {item.short_explanation ||
                      item.reason ||
                      problemCodeLabel(actionCode(item))}
                  </div>
                </div>
                <div className="flex min-w-0 items-center gap-2 text-xs text-muted-foreground">
                  <span
                    className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-md border ${cfg.tone}`}
                  >
                    {cfg.icon}
                  </span>
                  <span className="min-w-0">
                    <span className="block truncate font-medium text-foreground">
                      {itemProductTitle(item)}
                    </span>
                    <span className="block truncate">{objectLabel(item)}</span>
                  </span>
                </div>
                <div
                  className={`text-sm font-semibold ${
                    money ? "text-red-700 dark:text-red-300" : "text-muted-foreground"
                  }`}
                >
                  {money ? formatMoneyCompact(money) : "—"}
                </div>
                <ChevronRight className="hidden h-4 w-4 text-muted-foreground md:block" />
              </button>
            );
          })}
        </div>
      </div>

      <div className="space-y-4">
        <div className="rounded-md border bg-card p-4 shadow-sm">
          <div className="mb-4 flex items-center justify-between gap-3">
            <div>
              <div className="text-sm font-semibold">Влияние по группам</div>
              <div className="text-xs text-muted-foreground">
                Где сейчас больше всего открытых задач.
              </div>
            </div>
            <BarChart3 className="h-4 w-4 text-primary" />
          </div>
          <MiniImpactDonut groups={groups} />
        </div>
        <div className="rounded-md border bg-card p-4 shadow-sm">
          <div className="mb-3 text-sm font-semibold">
            Распределение проблем
          </div>
          <div className="space-y-2">
            {distributionRows.map((group) => (
              <button
                key={group.key}
                type="button"
                onClick={() => onOpenGroup(group.key)}
                className="grid w-full grid-cols-[minmax(0,1fr)_auto] items-center gap-2 rounded-md px-2 py-1.5 text-left hover:bg-muted/30"
              >
                <span className="truncate text-xs text-muted-foreground">
                  {group.title}
                </span>
                <span className="text-xs font-semibold">{group.open}</span>
              </button>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}

function ReferenceStatCard({
  icon,
  value,
  label,
  hint,
  tone = "neutral",
}: {
  icon: React.ReactNode;
  value: React.ReactNode;
  label: string;
  hint: string;
  tone?: "neutral" | "danger" | "warning" | "success" | "info";
}) {
  const toneClass =
    tone === "danger"
      ? "bg-red-500/10 text-red-700 dark:text-red-300"
      : tone === "warning"
        ? "bg-amber-500/10 text-amber-800 dark:text-amber-300"
        : tone === "success"
          ? "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300"
          : tone === "info"
            ? "bg-sky-500/10 text-sky-700 dark:text-sky-300"
            : "bg-primary/10 text-primary";
  return (
    <div className="min-w-0 border-b px-5 py-4 sm:border-b-0 sm:border-r last:border-r-0">
      <div className="flex items-center gap-3">
        <span
          className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-full ${toneClass}`}
        >
          {icon}
        </span>
        <div className="min-w-0">
          <div className="text-2xl font-semibold leading-none tracking-normal">
            {value}
          </div>
          <div className="mt-1 text-sm font-semibold leading-tight">
            {label}
          </div>
          <div className="mt-0.5 line-clamp-1 text-xs text-muted-foreground">
            {hint}
          </div>
        </div>
      </div>
    </div>
  );
}

function ReferenceOverview({
  items,
  groups,
  counts,
  openCount,
  urgentCount,
  overdueCount,
  execution,
  blockerCount,
  moneyAtStake,
  moneyOverlap,
  dataHealthStatus,
  filters,
  updateFilters,
  resetFilters,
  canUseBeta,
  onOpenItem,
  onOpenGroup,
  onCreateManualTask,
  canAssignTasks,
  onRefresh,
}: {
  items: ActionCenterItem[];
  groups: ProblemGroupSummary[];
  counts: Record<TaskBoardMode, number>;
  openCount: number;
  urgentCount: number;
  overdueCount: number;
  execution: ActionExecutionSummary;
  blockerCount: number;
  moneyAtStake: number;
  moneyOverlap: number;
  dataHealthStatus?: DataSyncStatusResponse | null;
  filters: ActionCenterFilterState;
  updateFilters: (
    patch: Partial<ActionCenterFilterState>,
    options?: { groupKey?: ProblemGroupKey | null; replace?: boolean },
  ) => void;
  resetFilters: () => void;
  canUseBeta: boolean;
  onOpenItem: (item: ActionCenterItem) => void;
  onOpenGroup: (key: ProblemGroupKey) => void;
  onCreateManualTask: () => void;
  canAssignTasks: boolean;
  onRefresh: () => void;
}) {
  const [filtersOpen, setFiltersOpen] = useState(false);
  const openCandidates = items.filter((item) => !isClosedAction(item));
  const workCases = useMemo(
    () => buildBusinessCases(openCandidates),
    [openCandidates],
  );
  const topCases = workCases.slice(0, 7);
  const urgentCaseCount = workCases.filter((item) => item.urgent).length;
  const blockerCaseCount = workCases.filter((item) => item.blocker).length;
  const caseGroups = useMemo(
    () => buildBusinessCaseGroups(workCases),
    [workCases],
  );
  const activeGroups = caseGroups.filter((group) => group.open > 0);
  const readyCaseCount = workCases.filter(
    (item) => item.execution.execute + item.execution.inline > 0,
  ).length;
  const readySignalCount = execution.execute + execution.inline;
  const moneyHint = moneyOverlap
    ? "Без повторных сигналов, до сверки WB"
    : "По кейсам, до финальной сверки";
  return (
    <div className="mx-auto w-full max-w-[1280px] space-y-4">
      <section className="overflow-hidden rounded-md border bg-card shadow-sm">
        <div className="flex flex-col gap-4 border-b px-5 py-4 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <h1 className="text-2xl font-semibold leading-tight">
              Центр действий
            </h1>
            <div className="mt-1 text-sm text-muted-foreground">
              Ежедневный план действий для роста прибыли.
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button
              size="sm"
              onClick={onCreateManualTask}
              disabled={!canAssignTasks}
              title={
                canAssignTasks ? undefined : "Нужна роль оператора или выше"
              }
            >
              <Plus className="h-3.5 w-3.5" />
              Поставить задачу
            </Button>
            <Button size="sm" variant="outline" onClick={onRefresh}>
              <RefreshCw className="h-3.5 w-3.5" />
              Обновить
            </Button>
            <Button asChild size="sm" variant="outline">
              <Link to="/results">
                <BarChart3 className="h-3.5 w-3.5" />
                Результаты
              </Link>
            </Button>
          </div>
        </div>

        <div className="grid sm:grid-cols-2 xl:grid-cols-4">
          <ReferenceStatCard
            icon={<AlertTriangle className="h-5 w-5" />}
            value={topCases.length}
            label="В фокусе сегодня"
            hint={`${workCases.length} кейсов всего`}
            tone={urgentCaseCount || overdueCount ? "danger" : "neutral"}
          />
          <ReferenceStatCard
            icon={<CheckCircle2 className="h-5 w-5" />}
            value={readyCaseCount}
            label="Готово к выполнению"
            hint={`${readySignalCount} действий внутри кейсов`}
            tone={readyCaseCount ? "success" : "neutral"}
          />
          <ReferenceStatCard
            icon={<Database className="h-5 w-5" />}
            value={blockerCaseCount}
            label="Кейсы без данных"
            hint={`${blockerCount} сигналов требуют данных`}
            tone={blockerCaseCount ? "warning" : "neutral"}
          />
          <ReferenceStatCard
            icon={<TrendingUp className="h-5 w-5" />}
            value={moneyAtStake ? formatMoneyCompact(moneyAtStake) : "—"}
            label="Оценка без дублей"
            hint={moneyHint}
            tone={moneyAtStake ? "info" : "neutral"}
          />
        </div>
      </section>

      <ActionCenterDataHealthBanner status={dataHealthStatus} />

      <section className="grid gap-4 xl:grid-cols-[minmax(0,1.65fr)_340px]">
        <div className="overflow-hidden rounded-md border bg-card shadow-sm">
          <div className="flex flex-col gap-3 border-b px-5 py-4 md:flex-row md:items-center md:justify-between">
            <div>
              <div className="text-lg font-semibold">
                Топ кейсов на сегодня
              </div>
              <div className="text-sm text-muted-foreground">
                Один товар или объект показывается как один кейс, даже если
                внутри несколько сигналов.
              </div>
            </div>
            <div className="flex flex-wrap gap-2">
              <div className="relative w-full md:w-[280px]">
                <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
                <Input
                  value={filters.q}
                  onChange={(event) => updateFilters({ q: event.target.value })}
                  placeholder="Поиск товара или задачи"
                  className="h-9 rounded-md pl-9"
                />
              </div>
              <Button
                size="sm"
                variant={filtersOpen ? "default" : "outline"}
                onClick={() => setFiltersOpen((value) => !value)}
              >
                <SlidersHorizontal className="h-3.5 w-3.5" />
                Фильтры
              </Button>
            </div>
          </div>

          {filtersOpen ? (
            <div className="border-b bg-muted/15 px-5 py-3">
              <ActionCenterFilterDock
                filters={filters}
                updateFilters={updateFilters}
                resetFilters={resetFilters}
                canUseBeta={canUseBeta}
              />
            </div>
          ) : null}

          <div className="divide-y">
            {topCases.length ? (
              topCases.map((caseItem) => {
                const item = caseItem.mainItem;
                const money = caseItem.money;
                return (
                  <button
                    key={caseItem.key}
                    type="button"
                    onClick={() => onOpenItem(item)}
                    className="grid w-full gap-3 px-5 py-3 text-left transition-colors hover:bg-muted/25 md:grid-cols-[112px_minmax(0,1fr)_260px_120px_92px_28px] md:items-center"
                  >
                    <div className="flex flex-wrap gap-1.5">
                      <PriorityBadge item={item} />
                      {caseItem.count > 1 ? (
                        <Badge variant="outline" className="rounded-full text-[10px]">
                          {signalCountLabel(caseItem.count)}
                        </Badge>
                      ) : (
                        <Badge
                          variant="outline"
                          className={`rounded-full text-[10px] ${actionStateTone(item)}`}
                        >
                          {actionModeLabel(item)}
                        </Badge>
                      )}
                    </div>
                    <div className="min-w-0">
                      <div className="line-clamp-1 text-sm font-semibold">
                        {businessCaseDisplayTitle(caseItem)}
                      </div>
                      <div className="mt-0.5 line-clamp-1 text-xs text-muted-foreground">
                        {businessCaseSubtitle(caseItem)}
                      </div>
                    </div>
                    <div className="flex min-w-0 items-center gap-3">
                      <ProductThumb
                        candidates={itemImageCandidates(item)}
                        label={itemProductTitle(item)}
                        className="h-12 w-12 rounded-md"
                      />
                      <div className="min-w-0">
                        <div className="line-clamp-1 text-sm font-semibold">
                          {itemProductTitle(item)}
                        </div>
                        <div className="mt-0.5 truncate text-xs text-muted-foreground">
                          {objectLabel(item)}
                        </div>
                      </div>
                    </div>
                    <div
                      className={`text-sm font-semibold ${
                        money
                          ? "text-emerald-700 dark:text-emerald-300"
                          : "text-muted-foreground"
                      }`}
                    >
                      {money ? formatMoneyCompact(Math.abs(money)) : "—"}
                    </div>
                    <div className="text-xs font-medium text-muted-foreground">
                      {caseItem.count > 1
                        ? actionModeLabel(item)
                        : sourceModuleLabel(item.source_module)}
                    </div>
                    <ChevronRight className="hidden h-4 w-4 text-muted-foreground md:block" />
                  </button>
                );
              })
            ) : (
              <div className="flex min-h-[260px] items-center justify-center p-8 text-center">
                <div className="max-w-sm">
                  <CheckCircle2 className="mx-auto h-10 w-10 text-emerald-600" />
                  <div className="mt-3 text-base font-semibold">
                    Действий нет
                  </div>
                  <div className="mt-1 text-sm text-muted-foreground">
                    По текущим фильтрам всё закрыто.
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>

        <div className="space-y-4">
          <div className="rounded-md border bg-card p-5 shadow-sm">
            <div className="text-base font-semibold">
              Кейсы по категориям
            </div>
            <div className="mt-1 text-sm text-muted-foreground">
              Где сейчас больше всего сгруппированных проблем.
            </div>
            <div className="mt-5">
              <MiniImpactDonut groups={caseGroups} />
            </div>
          </div>

          <div className="rounded-md border bg-card p-5 shadow-sm">
            <div className="mb-3 flex items-center justify-between gap-2">
              <div className="text-base font-semibold">
                Распределение кейсов
              </div>
              <Badge variant="outline" className="rounded-full">
                {activeGroups.length}
              </Badge>
            </div>
            <div className="space-y-2">
              {activeGroups.slice(0, 8).map((group) => (
                <button
                  key={group.key}
                  type="button"
                  onClick={() => onOpenGroup(group.key)}
                  className="grid w-full grid-cols-[minmax(0,1fr)_auto] items-center gap-3 rounded-md px-2 py-2 text-left transition-colors hover:bg-muted/30"
                >
                  <span className="min-w-0">
                    <span className="block truncate text-sm font-medium">
                      {group.title}
                    </span>
                    <span className="block text-xs text-muted-foreground">
                      {group.urgent} срочно
                    </span>
                  </span>
                  <span className="text-sm font-semibold">{group.open}</span>
                </button>
              ))}
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}

function departmentRows(
  groups: ProblemGroupSummary[],
  domains?: PortalActionCenterCapabilityDomain[],
) {
  const groupByKey = new Map(groups.map((group) => [group.key, group]));
  const seen = new Set<ProblemGroupKey>();
  const rows = (domains ?? [])
    .map((domain) => {
      const key = normalizeProblemGroupKey(domain.key);
      if (!key) return null;
      seen.add(key);
      return { key, domain, group: groupByKey.get(key) ?? null };
    })
    .filter(Boolean) as Array<{
    key: ProblemGroupKey;
    domain: PortalActionCenterCapabilityDomain | null;
    group: ProblemGroupSummary | null;
  }>;
  for (const group of groups) {
    if (seen.has(group.key)) continue;
    rows.push({ key: group.key, domain: null, group });
  }
  return rows.sort((a, b) => {
    const groupRankDelta =
      problemGroupBusinessRank(a.key) - problemGroupBusinessRank(b.key);
    if (groupRankDelta) return groupRankDelta;
    const aOpen = a.group?.open ?? 0;
    const bOpen = b.group?.open ?? 0;
    if (bOpen !== aOpen) return bOpen - aOpen;
    return (a.domain?.priority ?? 99) - (b.domain?.priority ?? 99);
  });
}

function DepartmentHub({
  groups,
  domains,
  mode,
  onOpen,
}: {
  groups: ProblemGroupSummary[];
  domains?: PortalActionCenterCapabilityDomain[];
  mode: TaskBoardMode;
  onOpen: (key: ProblemGroupKey) => void;
}) {
  const rows = departmentRows(groups, domains);
  const firstActive = rows.find((row) => row.group?.items.length) ?? rows[0];
  const [focusedKey, setFocusedKey] = useState<ProblemGroupKey | null>(
    () => firstActive?.key ?? null,
  );
  useEffect(() => {
    if (!rows.length) {
      if (focusedKey) setFocusedKey(null);
      return;
    }
    if (!focusedKey || !rows.some((row) => row.key === focusedKey)) {
      setFocusedKey(firstActive?.key ?? rows[0].key);
    }
  }, [rows, focusedKey, firstActive]);
  const focusedRow =
    rows.find((row) => row.key === focusedKey) ?? firstActive ?? null;
  if (!rows.length) {
    return (
      <div className="flex min-h-[420px] items-center justify-center rounded-md border bg-card p-8 text-center shadow-sm">
        <div className="max-w-sm space-y-3">
          <ShieldCheck className="mx-auto h-10 w-10 text-emerald-600" />
          <div className="text-lg font-semibold">Задач нет</div>
          <div className="text-sm text-muted-foreground">
            В разделе «{taskBoardModeTitle(mode).toLowerCase()}» по текущим
            фильтрам ничего не осталось.
          </div>
        </div>
      </div>
    );
  }
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <div className="text-base font-semibold">Группы проблем</div>
          <div className="text-xs text-muted-foreground">
            Выберите участок работы. Справа сразу видно первый шаг, форму
            исправления или назначение.
          </div>
        </div>
        <Badge variant="outline" className="rounded-full">
          {rows.filter((row) => row.group?.items.length).length} активных
        </Badge>
      </div>
      <div className="grid gap-3 xl:grid-cols-[370px_minmax(0,1fr)] xl:items-start">
        <div className="overflow-hidden rounded-md border bg-card shadow-sm">
          <div className="border-b bg-muted/25 px-3 py-2 text-[11px] font-medium uppercase text-muted-foreground">
            Участки работы
          </div>
          <div className="divide-y">
            {rows.map((row) => (
              <DepartmentListRow
                key={row.key}
                row={row}
                active={focusedRow?.key === row.key}
                onFocus={() => {
                  setFocusedKey(row.key);
                  if (row.group?.items.length) onOpen(row.key);
                }}
              />
            ))}
          </div>
        </div>

        <DepartmentPreview
          row={focusedRow}
          mode={mode}
          onOpen={(key) => onOpen(key)}
        />
      </div>
    </div>
  );
}

function DepartmentListRow({
  row,
  active,
  onFocus,
}: {
  row: {
    key: ProblemGroupKey;
    domain: PortalActionCenterCapabilityDomain | null;
    group: ProblemGroupSummary | null;
  };
  active: boolean;
  onFocus: () => void;
}) {
  const cfg = PROBLEM_GROUP_CONFIG[row.key];
  const group = row.group;
  const open = group?.open ?? 0;
  const urgent = group?.urgent ?? 0;
  const progress = group?.progress ?? 0;
  const hasTasks = Boolean(group?.items.length);
  return (
    <button
      type="button"
      onClick={onFocus}
      className={`grid w-full grid-cols-[38px_minmax(0,1fr)_auto] items-center gap-3 px-3 py-3 text-left transition-colors ${
        active
          ? "bg-primary/7 ring-1 ring-inset ring-primary/25"
          : "hover:bg-muted/30"
      } ${hasTasks ? "" : "opacity-60"}`}
    >
      <span
        className={`flex h-9 w-9 items-center justify-center rounded-md border ${cfg.tone}`}
      >
        {cfg.icon}
      </span>
      <span className="min-w-0">
        <span className="flex min-w-0 items-center gap-2">
          <span className="truncate text-sm font-semibold">
            {cfg.title}
          </span>
          {group?.blockers ? (
            <span className="shrink-0 rounded-full bg-amber-500/10 px-1.5 py-0.5 text-[10px] font-semibold text-amber-800 dark:text-amber-300">
              {group.blockers}
            </span>
          ) : null}
        </span>
        <span className="mt-1 flex items-center gap-2">
          <Progress value={progress} className="h-1.5 flex-1" />
          <span className="w-8 text-right text-[11px] font-semibold text-muted-foreground">
            {progress}%
          </span>
        </span>
      </span>
      <span className="text-right">
        <span className="block text-sm font-semibold">{open}</span>
        <span
          className={`block text-[11px] ${urgent ? "text-red-700 dark:text-red-300" : "text-muted-foreground"}`}
        >
          {urgent} срочно
        </span>
      </span>
    </button>
  );
}

function DepartmentPreview({
  row,
  mode,
  onOpen,
}: {
  row: {
    key: ProblemGroupKey;
    domain: PortalActionCenterCapabilityDomain | null;
    group: ProblemGroupSummary | null;
  } | null;
  mode: TaskBoardMode;
  onOpen: (key: ProblemGroupKey) => void;
}) {
  if (!row) {
    return (
      <div className="flex min-h-[420px] items-center justify-center rounded-md border bg-card p-8 text-center shadow-sm">
        <div className="max-w-sm space-y-2">
          <ShieldCheck className="mx-auto h-10 w-10 text-emerald-600" />
          <div className="font-semibold">Нет групп для работы</div>
          <div className="text-sm text-muted-foreground">
            В режиме «{taskBoardModeTitle(mode).toLowerCase()}» задач нет.
          </div>
        </div>
      </div>
    );
  }
  const cfg = PROBLEM_GROUP_CONFIG[row.key];
  const catalog = TASK_DOMAIN_CATALOG[row.key];
  const group = row.group;
  const hasTasks = Boolean(group?.items.length);
  const firstOpen =
    group?.items.find((item) => !isClosedAction(item)) ??
    group?.items[0] ??
    null;
  const actionLabel = firstOpen
    ? humanActionLabel(primaryActionForItem(firstOpen)?.code)
    : catalog.workflow[0];
  const directFixCount =
    (group?.execution.execute ?? 0) + (group?.execution.inline ?? 0);
  return (
    <div className="h-fit overflow-hidden rounded-md border bg-card shadow-sm">
      <div className="border-b bg-muted/20 p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="flex min-w-0 items-start gap-3">
            <span
              className={`flex h-12 w-12 shrink-0 items-center justify-center rounded-md border ${cfg.tone}`}
            >
              {cfg.icon}
            </span>
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <h2 className="text-lg font-semibold leading-tight">
                  {cfg.title}
                </h2>
                {group?.blockers ? (
                  <Badge
                    variant="outline"
                    className="rounded-full border-amber-500/35 bg-amber-500/10 text-amber-800 dark:text-amber-300"
                  >
                    {group.blockers} блокер
                  </Badge>
                ) : null}
              </div>
              <div className="mt-1 max-w-2xl text-sm text-muted-foreground">
                {group?.subtitle || catalog.short}
              </div>
            </div>
          </div>
          <Button
            disabled={!hasTasks}
            onClick={() => onOpen(row.key)}
            className="shrink-0"
          >
            {hasTasks ? cfg.actionLabel : "Нет задач"}
            <ArrowRight className="h-3.5 w-3.5" />
          </Button>
        </div>
      </div>

      <div className="p-4">
        <div className="space-y-4">
          <div className="grid gap-2 sm:grid-cols-4">
            <MissionMetric
              label="Открыто"
              value={group?.open ?? 0}
              tone="muted"
            />
            <MissionMetric
              label="Срочно"
              value={group?.urgent ?? 0}
              tone={group?.urgent ? "danger" : "muted"}
            />
            <MissionMetric
              label="Можно применить"
              value={directFixCount}
              tone={directFixCount ? "success" : "muted"}
            />
            <MissionMetric
              label="Оценка сигналов"
              value={group?.money ? formatMoney(group.money) : "—"}
              tone={group?.money ? "danger" : "muted"}
            />
          </div>

          <div className="rounded-md border bg-muted/15 p-4">
            <div className="text-xs font-medium uppercase text-muted-foreground">
              Первый шаг
            </div>
            <div className="mt-1 text-base font-semibold">{actionLabel}</div>
            <div className="mt-1 text-sm text-muted-foreground">
              {firstOpen?.reason || catalog.short}
            </div>
          </div>

          <div className="rounded-md border bg-card p-4">
            <div className="mb-3 text-sm font-semibold">
              Порядок внутри группы
            </div>
            <div className="grid gap-2 md:grid-cols-3">
              {catalog.workflow.map((step, index) => (
                <div
                  key={step}
                  className="rounded-md border bg-muted/15 px-3 py-2"
                >
                  <div className="flex items-center gap-2">
                    <span className="flex h-6 w-6 items-center justify-center rounded-full bg-primary/10 text-xs font-semibold text-primary">
                      {index + 1}
                    </span>
                    <span className="text-sm font-semibold">{step}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function workspaceActionForGroup(
  group: ProblemGroupSummary,
  item: ActionCenterItem | null,
): { label: string; href?: string | null; disabled?: boolean }[] {
  const href = item
    ? (primaryActionForItem(item)?.href ?? guidedFixHref(item) ?? null)
    : null;
  if (group.key === "manual_tasks") {
    return [{ label: "Создать задачу", href: null }];
  }
  if (group.key === "data_blockers") {
    return [{ label: "Заполнить здесь", href }];
  }
  if (group.key === "price") {
    return [{ label: "Проверить цену", href: href ?? "/pricing" }];
  }
  if (group.key === "stock") {
    return [{ label: "Поставки и остатки", href: href ?? "/logistics" }];
  }
  if (group.key === "ads_promo") {
    return [{ label: "Открыть рекламу", href: href ?? "/ads" }];
  }
  if (group.key === "card_quality") {
    return [{ label: "Исправить карточку", href: href ?? "/cards" }];
  }
  if (group.key === "reputation") {
    return [{ label: "Подготовить ответ", href: href ?? "/reputation" }];
  }
  return [{ label: "Открыть действие", href }];
}

function DepartmentPlaybook({
  group,
  domain,
  selected,
  onCreateManualTask,
}: {
  group: ProblemGroupSummary;
  domain?: PortalActionCenterCapabilityDomain | null;
  selected: ActionCenterItem | null;
  onCreateManualTask?: () => void;
}) {
  const catalog = TASK_DOMAIN_CATALOG[group.key];
  const actions = workspaceActionForGroup(group, selected);
  return (
    <aside className="space-y-3 xl:sticky xl:top-4 xl:self-start">
      <div className="rounded-md border bg-card p-4 shadow-sm">
        <div className="text-sm font-semibold">Порядок работы</div>
        <div className="mt-3 space-y-3">
          {catalog.workflow.map((step, index) => (
            <div key={step} className="grid grid-cols-[28px_1fr] gap-3">
              <span
                className={`flex h-7 w-7 items-center justify-center rounded-full border text-xs font-semibold ${
                  index === 0
                    ? "border-primary/35 bg-primary/10 text-primary"
                    : "border-border bg-muted/25 text-muted-foreground"
                }`}
              >
                {index + 1}
              </span>
              <div className="min-w-0">
                <div className="text-sm font-semibold">{step}</div>
                <div className="text-xs text-muted-foreground">
                  {index === 0
                    ? catalog.short
                    : index === catalog.workflow.length - 1
                      ? catalog.doneSignal
                      : "Выполните доступный шаг или назначьте ответственного."}
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
      <div className="rounded-md border bg-card p-4 shadow-sm">
        <div className="text-sm font-semibold">Доступные действия</div>
        <div className="mt-3 grid gap-2">
          {actions.map((action) =>
            action.disabled ? (
              <Button
                key={action.label}
                variant="outline"
                className="justify-start"
                disabled
              >
                <Lock className="h-3.5 w-3.5" />
                {action.label}
              </Button>
            ) : action.href ? (
              <WorkButton
                key={action.label}
                href={action.href}
                label={action.label}
                variant="outline"
              />
            ) : (
              <Button
                key={action.label}
                variant="outline"
                className="justify-start"
                onClick={onCreateManualTask}
                disabled={!onCreateManualTask}
              >
                <Plus className="h-3.5 w-3.5" />
                {action.label}
              </Button>
            ),
          )}
        </div>
      </div>
    </aside>
  );
}

function DepartmentQueuePanel({
  queueItems,
  selected,
  selectedIndex,
  openCount,
  currentUserId,
  onSelect,
}: {
  queueItems: ActionCenterItem[];
  selected: ActionCenterItem | null;
  selectedIndex: number;
  openCount: number;
  currentUserId: number | null;
  onSelect: (id: string) => void;
}) {
  return (
    <div className="rounded-md border bg-card shadow-sm xl:sticky xl:top-4 xl:self-start">
      <div className="flex items-center justify-between gap-3 border-b px-4 py-3">
        <div>
          <div className="flex items-center gap-2 text-sm font-semibold">
            <ListChecks className="h-4 w-4 text-primary" />
            Очередь
          </div>
          <div className="text-xs text-muted-foreground">
            Осталось {openCount}
          </div>
        </div>
        <Badge variant="outline" className="rounded-full">
          {selectedIndex >= 0 ? selectedIndex + 1 : 0}/{queueItems.length}
        </Badge>
      </div>
      <ScrollArea className="max-h-[390px] xl:h-[calc(100vh-270px)] xl:max-h-none xl:min-h-[520px]">
        <div className="space-y-2 p-3">
          {queueItems.length ? (
            queueItems.map((item, index) => (
              <QueueItem
                key={item.id}
                item={item}
                index={index}
                selected={selected?.id === item.id}
                currentUserId={currentUserId}
                onSelect={() => onSelect(item.id)}
              />
            ))
          ) : (
            <div className="flex min-h-[280px] items-center justify-center rounded-md border border-dashed bg-muted/20 p-6 text-center">
              <div className="space-y-2">
                <CheckCircle2 className="mx-auto h-9 w-9 text-emerald-600" />
                <div className="font-semibold">Очередь пуста</div>
                <div className="text-sm text-muted-foreground">
                  В этой группе больше нет задач.
                </div>
              </div>
            </div>
          )}
        </div>
      </ScrollArea>
    </div>
  );
}

function DepartmentWorkspace({
  group,
  domain,
  mode,
  queueItems,
  selected,
  selectedIndex,
  openItems,
  urgentItems,
  actionableItems,
  blockerItems,
  currentUserId,
  accountId,
  dateFrom,
  dateTo,
  busy,
  recheckBusy,
  onClose,
  onSelect,
  onStatus,
  onDoneNext,
  onRecheck,
  onChanged,
  onNext,
  hasNext,
  onApplyGroupRecalculate,
  onCreateManualTask,
}: {
  group: ProblemGroupSummary;
  domain?: PortalActionCenterCapabilityDomain | null;
  mode: TaskBoardMode;
  queueItems: ActionCenterItem[];
  selected: ActionCenterItem | null;
  selectedIndex: number;
  openItems: ActionCenterItem[];
  urgentItems: ActionCenterItem[];
  actionableItems: ActionCenterItem[];
  blockerItems: ActionCenterItem[];
  currentUserId: number | null;
  accountId: number | null | undefined;
  dateFrom?: string | null;
  dateTo?: string | null;
  busy: string | null;
  recheckBusy: string | null;
  onClose: () => void;
  onSelect: (id: string) => void;
  onStatus: (
    item: ActionCenterItem,
    status: string,
    next?: boolean,
    options?: { deadline_at?: string; comment?: string },
  ) => void;
  onDoneNext: (item: ActionCenterItem) => void;
  onRecheck: (item: ActionCenterItem) => void;
  onChanged: () => Promise<void> | void;
  onNext: () => void;
  hasNext: boolean;
  onApplyGroupRecalculate: () => void;
  onCreateManualTask?: () => void;
}) {
  return (
    <div className="space-y-4">
      <div className="overflow-hidden rounded-md border bg-card shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b bg-muted/20 px-3 py-2">
          <button
            type="button"
            onClick={onClose}
            className="inline-flex h-8 items-center gap-1.5 rounded-md px-2 text-sm font-semibold text-muted-foreground transition-colors hover:bg-background hover:text-foreground"
          >
            <ArrowLeft className="h-3.5 w-3.5" />
            Группы
          </button>
          <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
            <span>{taskBoardModeTitle(mode)}</span>
            <ChevronRight className="h-3.5 w-3.5" />
            <span className="font-medium text-foreground">{group.title}</span>
          </div>
        </div>
        <div className="grid gap-4 px-4 py-4 xl:grid-cols-[minmax(0,1fr)_320px] xl:items-center">
          <div className="flex min-w-0 items-start gap-3">
            <span
              className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-md border ${group.tone}`}
            >
              {group.icon}
            </span>
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <h2 className="text-xl font-semibold leading-tight">
                  {domain?.title || group.title}
                </h2>
                <Badge variant="secondary" className="rounded-full">
                  Осталось {openItems.length}
                </Badge>
              </div>
              <div className="mt-1 max-w-3xl text-sm text-muted-foreground">
                {domain?.description || group.subtitle}
              </div>
              <div className="mt-3 flex flex-wrap gap-2">
                <Badge variant="outline" className="rounded-full">
                  Срочно {urgentItems.length}
                </Badge>
                <Badge variant="outline" className="rounded-full">
                  Можно применить{" "}
                  {group.execution.execute + group.execution.inline}
                </Badge>
                {group.money ? (
                  <Badge
                    variant="outline"
                    className="rounded-full border-red-500/35 bg-red-500/10 text-red-700 dark:text-red-300"
                  >
                    Оценка сигналов {formatMoney(group.money)}
                  </Badge>
                ) : null}
              </div>
            </div>
          </div>
          <div className="space-y-3">
            <div className="flex items-center gap-3">
              <Progress value={group.progress} className="h-2" />
              <span className="w-12 text-right text-sm font-semibold">
                {group.progress}%
              </span>
            </div>
            <div className="flex flex-wrap justify-start gap-2 xl:justify-end">
              <Button
                size="sm"
                onClick={onApplyGroupRecalculate}
                disabled={Boolean(recheckBusy)}
              >
                {recheckBusy ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <RotateCw className="h-3.5 w-3.5" />
                )}
                Пересчитать
              </Button>
              <Button size="sm" variant="outline" onClick={onClose}>
                <ArrowLeft className="h-3.5 w-3.5" />
                Все группы
              </Button>
            </div>
          </div>
        </div>
      </div>
      <div className="grid gap-4 xl:grid-cols-[320px_minmax(0,1fr)]">
        <DepartmentQueuePanel
          queueItems={queueItems}
          selected={selected}
          selectedIndex={selectedIndex}
          openCount={openItems.length}
          currentUserId={currentUserId}
          onSelect={onSelect}
        />
        <FocusPanel
          item={selected}
          accountId={accountId}
          dateFrom={dateFrom}
          dateTo={dateTo}
          busy={busy || recheckBusy}
          currentUserId={currentUserId}
          onStatus={onStatus}
          onDoneNext={onDoneNext}
          onRecheck={onRecheck}
          onChanged={onChanged}
          onNext={onNext}
          hasNext={hasNext}
        />
      </div>
    </div>
  );
}

function capabilityExecutionLabel(status: string): string {
  const key = norm(status);
  if (key === "ready") return "Готово";
  if (key === "preview_only") return "проверка";
  if (key === "manual") return "вручную";
  if (key === "missing_wb_write") return "нужна запись WB";
  if (key === "planned") return "в плане";
  return "проверить";
}

function capabilityExecutionTone(status: string): string {
  const key = norm(status);
  if (key === "ready")
    return "border-emerald-500/35 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300";
  if (key === "missing_wb_write")
    return "border-amber-500/35 bg-amber-500/10 text-amber-800 dark:text-amber-300";
  if (key === "preview_only")
    return "border-sky-500/35 bg-sky-500/10 text-sky-700 dark:text-sky-300";
  return "border-border bg-muted text-muted-foreground";
}

function capabilityDomainStats(
  domain?: PortalActionCenterCapabilityDomain | null,
) {
  const caps = domain?.capabilities ?? [];
  const detectReady = caps.filter(
    (item) => item.detect_status === "ready",
  ).length;
  const executeReady = caps.filter(
    (item) => item.execute_status === "ready",
  ).length;
  const wbWriteMissing = caps.filter(
    (item) => item.execute_status === "missing_wb_write",
  ).length;
  const preview = caps.filter(
    (item) => item.execute_status === "preview_only",
  ).length;
  const apiTracked = caps.filter(
    (item) => item.wb_tracking_status === "tracked",
  ).length;
  const apiPartial = caps.filter((item) =>
    ["partial", "write_gap"].includes(item.wb_tracking_status || ""),
  ).length;
  const apiGaps = caps.reduce(
    (total, item) =>
      total +
      (item.implementation_gaps?.length || 0) +
      (item.unknown_connector_ids?.length || 0),
    0,
  );
  return {
    total: caps.length,
    detectReady,
    executeReady,
    wbWriteMissing,
    preview,
    apiTracked,
    apiPartial,
    apiGaps,
  };
}

function TaskDomainCatalog({
  groups,
  domains,
  onOpen,
}: {
  groups: ProblemGroupSummary[];
  domains?: PortalActionCenterCapabilityDomain[];
  onOpen: (key: ProblemGroupKey) => void;
}) {
  const domainByKey = new Map(
    (domains ?? []).map((domain) => [domain.key, domain]),
  );
  const groupByKey = new Map(groups.map((group) => [group.key, group]));
  const rows = [
    ...(domains?.length
      ? domains
          .filter((domain) => normalizeProblemGroupKey(domain.key))
          .map((domain) => ({
            key: normalizeProblemGroupKey(domain.key)!,
            domain,
            group: groupByKey.get(normalizeProblemGroupKey(domain.key)!),
          }))
      : groups.map((group) => ({
          key: group.key,
          domain: domainByKey.get(group.key),
          group,
        }))),
  ].sort((a, b) => {
    const groupRankDelta =
      problemGroupBusinessRank(a.key) - problemGroupBusinessRank(b.key);
    if (groupRankDelta) return groupRankDelta;
    const aOpen = a.group?.open ?? 0;
    const bOpen = b.group?.open ?? 0;
    if (bOpen !== aOpen) return bOpen - aOpen;
    const aPriority = a.domain?.priority ?? PROBLEM_GROUP_ORDER.indexOf(a.key);
    const bPriority = b.domain?.priority ?? PROBLEM_GROUP_ORDER.indexOf(b.key);
    return aPriority - bPriority;
  });
  if (!rows.length) return null;
  return (
    <div className="rounded-md border bg-card shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b bg-muted/20 px-3 py-2">
        <div>
          <div className="text-sm font-semibold">Рабочие контуры</div>
          <div className="text-xs text-muted-foreground">
            Карта возможностей: что система уже находит, какие действия готовы,
            и где нужна запись в WB.
          </div>
        </div>
        <Badge variant="outline">{rows.length} контуров</Badge>
      </div>
      <div className="grid divide-y md:grid-cols-2 md:divide-x md:divide-y-0 xl:grid-cols-3">
        {rows.slice(0, 9).map(({ key, group, domain }) => {
          const cfg = PROBLEM_GROUP_CONFIG[key];
          const catalog = TASK_DOMAIN_CATALOG[key];
          const stats = capabilityDomainStats(domain);
          const canOpen = Boolean(group?.items?.length);
          const mainCapability = domain?.capabilities?.[0];
          return (
            <button
              key={key}
              type="button"
              onClick={() => canOpen && onOpen(key)}
              disabled={!canOpen}
              className={`group min-w-0 px-3 py-2.5 text-left transition-colors ${
                canOpen ? "hover:bg-muted/30" : "cursor-default opacity-75"
              }`}
            >
              <div className="flex items-start gap-2.5">
                <span
                  className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-md border ${cfg.tone}`}
                >
                  {cfg.icon}
                </span>
                <div className="min-w-0 flex-1">
                  <div className="flex min-w-0 items-center justify-between gap-2">
                    <div className="truncate text-sm font-semibold">
                      {domain?.title || catalog.direction}
                    </div>
                    <Badge
                      variant={canOpen ? "secondary" : "outline"}
                      className="h-5 rounded-full"
                    >
                      {canOpen ? `${group.open} задач` : "нет задач"}
                    </Badge>
                  </div>
                  <div className="mt-0.5 line-clamp-2 text-xs text-muted-foreground">
                    {domain?.first_step || catalog.short}
                  </div>
                  <div className="mt-2 flex min-w-0 flex-wrap gap-1.5">
                    <span className="rounded-full bg-muted px-2 py-0.5 text-[10px] font-medium text-muted-foreground">
                      ищет {stats.detectReady}/
                      {stats.total || catalog.taskTypes.length}
                    </span>
                    <span className="rounded-full bg-emerald-500/10 px-2 py-0.5 text-[10px] font-medium text-emerald-700 dark:text-emerald-300">
                      готово {stats.executeReady}
                    </span>
                    {stats.apiTracked ? (
                      <span className="rounded-full bg-teal-500/10 px-2 py-0.5 text-[10px] font-medium text-teal-700 dark:text-teal-300">
                        WB {stats.apiTracked}
                      </span>
                    ) : null}
                    {stats.apiPartial ? (
                      <span className="rounded-full bg-slate-500/10 px-2 py-0.5 text-[10px] font-medium text-slate-700 dark:text-slate-300">
                        проверка {stats.apiPartial}
                      </span>
                    ) : null}
                    {stats.preview ? (
                      <span className="rounded-full bg-sky-500/10 px-2 py-0.5 text-[10px] font-medium text-sky-700 dark:text-sky-300">
                        review {stats.preview}
                      </span>
                    ) : null}
                    {stats.wbWriteMissing ? (
                      <span className="rounded-full bg-amber-500/10 px-2 py-0.5 text-[10px] font-medium text-amber-800 dark:text-amber-300">
                        запись WB {stats.wbWriteMissing}
                      </span>
                    ) : null}
                    {stats.apiGaps ? (
                      <span className="rounded-full bg-rose-500/10 px-2 py-0.5 text-[10px] font-medium text-rose-700 dark:text-rose-300">
                        gap {stats.apiGaps}
                      </span>
                    ) : null}
                    {mainCapability ? (
                      <Badge
                        variant="outline"
                        className={`h-5 max-w-full truncate rounded-full px-1.5 text-[10px] ${capabilityExecutionTone(mainCapability.execute_status)}`}
                      >
                        {capabilityExecutionLabel(
                          mainCapability.execute_status,
                        )}
                      </Badge>
                    ) : null}
                  </div>
                </div>
                {canOpen ? (
                  <ChevronRight className="mt-1 h-4 w-4 shrink-0 text-muted-foreground transition-colors group-hover:text-primary" />
                ) : null}
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}

function GroupWorkBrief({ group }: { group: ProblemGroupSummary }) {
  const catalog = TASK_DOMAIN_CATALOG[group.key];
  if (!catalog) return null;
  return (
    <div className="grid gap-2 rounded-md border bg-card p-2 shadow-sm md:grid-cols-3">
      <div className="rounded-md bg-muted/25 px-3 py-2">
        <div className="text-[11px] font-medium uppercase text-muted-foreground">
          Направление
        </div>
        <div className="mt-1 text-sm font-semibold">{catalog.direction}</div>
        <div className="mt-0.5 text-xs text-muted-foreground">
          {catalog.short}
        </div>
      </div>
      <div className="rounded-md bg-muted/25 px-3 py-2">
        <div className="text-[11px] font-medium uppercase text-muted-foreground">
          Что решаем
        </div>
        <div className="mt-1 flex flex-wrap gap-1">
          {catalog.taskTypes.slice(0, 4).map((task) => (
            <Badge key={task} variant="secondary" className="text-[10px]">
              {task}
            </Badge>
          ))}
        </div>
      </div>
      <div className="rounded-md bg-muted/25 px-3 py-2">
        <div className="text-[11px] font-medium uppercase text-muted-foreground">
          Очередность
        </div>
        <div className="mt-1 flex flex-wrap items-center gap-1 text-xs">
          {catalog.workflow.map((step, index) => (
            <span key={step} className="flex items-center gap-1">
              <span className="rounded-full bg-background px-2 py-0.5 font-medium">
                {index + 1}. {step}
              </span>
              {index < catalog.workflow.length - 1 ? (
                <ChevronRight className="h-3 w-3 text-muted-foreground" />
              ) : null}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}

function ProblemGroupRow({
  group,
  mode,
  selected,
  onOpen,
}: {
  group: ProblemGroupSummary;
  mode: TaskBoardMode;
  selected?: boolean;
  onOpen: () => void;
}) {
  const firstOpen =
    group.items.find((item) => !isClosedAction(item)) ?? group.items[0];
  const primaryCount =
    mode === "active" ? group.open : group.items.length || group.open;
  const primaryLabel =
    mode === "completed"
      ? "Выполнено"
      : mode === "deactivated"
        ? "Скрыто"
        : "Открыто";
  const inAppCount = group.execution.execute + group.execution.inline;
  return (
    <button
      type="button"
      onClick={onOpen}
      className={`group grid w-full gap-1.5 border-b bg-card px-3 py-1.5 text-left transition-colors last:border-b-0 hover:bg-muted/35 lg:min-h-[56px] lg:grid-cols-[minmax(340px,1fr)_56px_56px_64px_104px_118px_150px] lg:items-center ${
        selected ? "bg-primary/5 ring-1 ring-inset ring-primary/25" : ""
      }`}
    >
      <div className="flex min-w-0 items-center gap-2.5">
        <span
          className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-md border ${group.tone}`}
        >
          {group.icon}
        </span>
        <div className="min-w-0">
          <div className="flex min-w-0 items-center gap-1.5">
            <div className="min-w-0 truncate text-sm font-semibold leading-tight">
              {group.title}
            </div>
            {group.blockers ? (
              <Badge
                variant="outline"
                className="h-5 shrink-0 rounded-full border-amber-500/35 bg-amber-500/10 px-1.5 text-[10px] text-amber-800 dark:text-amber-300"
              >
                {group.blockers} блокер
              </Badge>
            ) : null}
            <div className="hidden min-w-0 flex-1 items-center gap-1.5 xl:flex">
              {group.topCodes.length
                ? group.topCodes.slice(0, 2).map((item) => (
                    <Badge
                      key={item.code}
                      variant="secondary"
                      className="h-5 max-w-[140px] truncate rounded-full bg-muted/70 px-1.5 text-[9px]"
                    >
                      {item.label} · {item.count}
                    </Badge>
                  ))
                : null}
            </div>
          </div>
          <div className="mt-0.5 flex min-w-0 items-center gap-1.5 text-[11px] leading-tight text-muted-foreground">
            <span className="min-w-0 truncate">{group.subtitle}</span>
            <span className="hidden shrink-0 text-muted-foreground/70 lg:inline">
              ·
            </span>
            <span className="hidden min-w-0 truncate lg:inline">
              Шаг:{" "}
              {firstOpen
                ? humanActionLabel(primaryActionForItem(firstOpen)?.code)
                : group.actionLabel}
            </span>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 lg:contents">
        <GroupRowMetric label={primaryLabel} value={primaryCount} />
        <GroupRowMetric
          label="Срочно"
          value={group.urgent}
          tone={
            group.urgent
              ? "text-red-700 dark:text-red-300"
              : "text-muted-foreground"
          }
        />
        <GroupRowMetric
          label="Применить"
          value={inAppCount}
          tone={
            inAppCount
              ? "text-emerald-700 dark:text-emerald-300"
              : "text-muted-foreground"
          }
        />
        <GroupRowMetric
          label="Эффект"
          value={group.money ? formatMoney(group.money) : "—"}
          tone={
            group.money
              ? "text-red-700 dark:text-red-300"
              : "text-muted-foreground"
          }
        />
      </div>

      <div className="min-w-0 pr-2">
        <div className="flex items-center gap-2 text-[10px] text-muted-foreground">
          <span className="font-medium text-foreground">{group.progress}%</span>
          <span className="truncate">закрыто {group.closed}</span>
        </div>
        <Progress value={group.progress} className="mt-1 h-1" />
      </div>

      <div className="flex items-center justify-between gap-2 lg:justify-end">
        <span className="whitespace-nowrap rounded-full bg-primary/5 px-2 py-0.5 text-xs font-semibold text-primary transition-colors group-hover:bg-primary/10">
          {group.actionLabel}
        </span>
        <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground transition-colors group-hover:text-primary" />
      </div>
    </button>
  );
}

function ProblemGroupsOverview({
  groups,
  mode,
  onOpen,
}: {
  groups: ProblemGroupSummary[];
  mode: TaskBoardMode;
  onOpen: (key: ProblemGroupKey) => void;
}) {
  if (!groups.length) {
    return (
      <div className="flex min-h-[420px] items-center justify-center rounded-md border bg-card p-8 text-center shadow-sm">
        <div className="max-w-sm space-y-3">
          <ShieldCheck className="mx-auto h-10 w-10 text-emerald-600" />
          <div className="text-lg font-semibold">Групп проблем нет</div>
          <div className="text-sm text-muted-foreground">
            В разделе «{taskBoardModeTitle(mode).toLowerCase()}» по текущим
            фильтрам задач нет.
          </div>
        </div>
      </div>
    );
  }
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div>
          <div className="text-base font-semibold">Группы проблем</div>
          <div className="text-xs text-muted-foreground">
            {taskBoardModeHint(mode)}
          </div>
        </div>
        <Badge variant="outline">{groups.length} групп</Badge>
      </div>
      <div className="overflow-hidden rounded-md border bg-card shadow-sm">
        <div className="hidden border-b bg-muted/35 px-3 py-1.5 text-[10px] font-medium uppercase text-muted-foreground lg:grid lg:grid-cols-[minmax(340px,1fr)_56px_56px_64px_104px_118px_160px]">
          <span>Группа и первый шаг</span>
          <span>
            {mode === "completed"
              ? "Выполнено"
              : mode === "deactivated"
                ? "Скрыто"
                : "Открыто"}
          </span>
          <span>Срочно</span>
          <span>Применить</span>
          <span>Эффект</span>
          <span>Прогресс</span>
          <span className="text-right">Действие</span>
        </div>
        {groups.map((group) => (
          <ProblemGroupRow
            key={group.key}
            group={group}
            mode={mode}
            onOpen={() => onOpen(group.key)}
          />
        ))}
      </div>
    </div>
  );
}

function QueueProgress({
  total,
  open,
  closed,
  urgent,
  actionable,
  blocked,
}: {
  total: number;
  open: number;
  closed: number;
  urgent: number;
  actionable: number;
  blocked: number;
}) {
  const percent = total > 0 ? Math.round((closed / total) * 100) : 100;
  return (
    <div className="relative overflow-hidden rounded-md border bg-card p-4 shadow-sm">
      <div className="absolute inset-x-0 top-0 h-0.5 bg-primary" />
      <div className="flex items-center justify-between gap-3">
        <div>
          <div className="flex items-center gap-2 text-sm font-semibold">
            <Gauge className="h-4 w-4 text-primary" />
            Прогресс очереди
          </div>
          <div className="text-xs text-muted-foreground">
            Осталось {open} из {total}
          </div>
        </div>
        <div className="text-3xl font-semibold tracking-tight">{percent}%</div>
      </div>
      <Progress value={percent} className="mt-3 h-2" />
      <div className="mt-3 grid grid-cols-3 gap-2 text-[11px]">
        <div className="rounded-md bg-muted/40 px-2 py-1.5">
          <div className="text-muted-foreground">решить</div>
          <div className="font-semibold">{actionable}</div>
        </div>
        <div className="rounded-md bg-red-500/10 px-2 py-1.5 text-red-700 dark:text-red-300">
          <div className="opacity-80">срочно</div>
          <div className="font-semibold">{urgent}</div>
        </div>
        <div className="rounded-md bg-amber-500/10 px-2 py-1.5 text-amber-800 dark:text-amber-300">
          <div className="opacity-80">блок</div>
          <div className="font-semibold">{blocked}</div>
        </div>
      </div>
      <div className="mt-2 flex justify-between text-[11px] text-muted-foreground">
        <span>закрыто {closed}</span>
        <span>в работе {Math.max(total - open - closed, 0)}</span>
      </div>
    </div>
  );
}

function filterOptionLabel(
  value: string,
  items: Array<{ value: string; label: string }>,
  fallback: string,
): string {
  return items.find((item) => item.value === value)?.label ?? fallback;
}

function activeFilterCount(filters: ActionCenterFilterState): number {
  const defaults = ACTION_CENTER_DEFAULT_FILTERS;
  let count = 0;
  if (filters.q.trim()) count += 1;
  if (filters.view !== defaults.view) count += 1;
  if (filters.status !== defaults.status) count += 1;
  if (filters.source_module !== defaults.source_module) count += 1;
  if (filters.severity !== defaults.severity) count += 1;
  if (filters.priority !== defaults.priority) count += 1;
  if (filters.trust_state !== defaults.trust_state) count += 1;
  if (filters.impact_type !== defaults.impact_type) count += 1;
  if (filters.include_beta !== defaults.include_beta) count += 1;
  if (filters.sort !== defaults.sort) count += 1;
  return count;
}

function CommandFilter({
  label,
  value,
  onValueChange,
  items,
  placeholder,
  includeAll = true,
}: {
  label: string;
  value: string;
  onValueChange: (value: string) => void;
  items: Array<{ value: string; label: string }>;
  placeholder: string;
  includeAll?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const options = includeAll
    ? [{ value: "all", label: placeholder }, ...items]
    : items;
  const selected = filterOptionLabel(value, options, placeholder);
  const isActive = includeAll ? value !== "all" : false;
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          type="button"
          variant="outline"
          role="combobox"
          aria-expanded={open}
          className={`h-10 w-full justify-between rounded-md border-border/70 bg-background px-3 shadow-sm xl:w-[190px] ${
            isActive ? "border-primary/45 bg-primary/5 text-primary" : ""
          }`}
        >
          <span className="min-w-0 truncate text-left text-xs">
            <span className="font-medium text-muted-foreground">{label}</span>
            <span className="mx-1 text-muted-foreground/60">·</span>
            <span
              className={`font-semibold ${isActive ? "text-primary" : "text-foreground"}`}
            >
              {selected}
            </span>
          </span>
          <ChevronDown className="ml-2 h-3.5 w-3.5 shrink-0 text-muted-foreground" />
        </Button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-[270px] p-0">
        <Command>
          <CommandInput placeholder={`Найти: ${label.toLowerCase()}`} />
          <CommandList>
            <CommandEmpty>Ничего не найдено</CommandEmpty>
            <CommandGroup>
              {options.map((item) => {
                const active = item.value === value;
                return (
                  <CommandItem
                    key={item.value}
                    value={`${item.label} ${item.value}`}
                    onSelect={() => {
                      onValueChange(item.value);
                      setOpen(false);
                    }}
                  >
                    <Check
                      className={`h-4 w-4 ${active ? "opacity-100" : "opacity-0"}`}
                    />
                    <span className="truncate">{item.label}</span>
                  </CommandItem>
                );
              })}
            </CommandGroup>
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
}

function preciseFilterCount(filters: ActionCenterFilterState): number {
  const defaults = ACTION_CENTER_DEFAULT_FILTERS;
  let count = 0;
  if (filters.severity !== defaults.severity) count += 1;
  if (filters.impact_type !== defaults.impact_type) count += 1;
  if (filters.trust_state !== defaults.trust_state) count += 1;
  return count;
}

function MoreFiltersMenu({
  filters,
  updateFilters,
}: {
  filters: ActionCenterFilterState;
  updateFilters: (patch: Partial<ActionCenterFilterState>) => void;
}) {
  const count = preciseFilterCount(filters);
  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button
          type="button"
          variant="outline"
          className={`h-10 rounded-md border-border/70 px-3 shadow-sm ${
            count
              ? "border-primary/45 bg-primary/5 text-primary"
              : "bg-background"
          }`}
        >
          <SlidersHorizontal className="h-3.5 w-3.5" />
          Фильтры
          {count ? (
            <Badge
              variant="secondary"
              className="ml-1 h-5 rounded-full px-1.5 text-[10px]"
            >
              {count}
            </Badge>
          ) : null}
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-[320px] space-y-3 p-3">
        <div>
          <div className="text-sm font-semibold">Точные фильтры</div>
          <div className="text-xs text-muted-foreground">
            Используйте, когда нужно сузить очередь.
          </div>
        </div>
        <div className="flex flex-col gap-2">
          <CommandFilter
            label="Важность"
            value={filters.severity}
            onValueChange={(value) => updateFilters({ severity: value })}
            items={SEVERITY_FILTERS}
            placeholder="Вся важность"
          />
          <CommandFilter
            label="Эффект"
            value={filters.impact_type}
            onValueChange={(value) => updateFilters({ impact_type: value })}
            items={IMPACT_TYPE_FILTERS}
            placeholder="Любой эффект"
          />
          <CommandFilter
            label="Данные"
            value={filters.trust_state}
            onValueChange={(value) => updateFilters({ trust_state: value })}
            items={TRUST_STATE_FILTERS}
            placeholder="Любые данные"
          />
        </div>
      </PopoverContent>
    </Popover>
  );
}

function ActionCenterFilterDock({
  filters,
  updateFilters,
  resetFilters,
  canUseBeta,
}: {
  filters: ActionCenterFilterState;
  updateFilters: (patch: Partial<ActionCenterFilterState>) => void;
  resetFilters: () => void;
  canUseBeta: boolean;
}) {
  const count = activeFilterCount(filters);
  return (
    <div className="space-y-3">
      <div className="grid gap-3 xl:grid-cols-[minmax(320px,1fr)_auto] xl:items-start">
        <div className="relative min-w-0">
          <Search className="pointer-events-none absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
          <Input
            value={filters.q}
            onChange={(event) => updateFilters({ q: event.target.value })}
            placeholder="Поиск действия, товара, SKU, причины или кода"
            className="h-11 rounded-md border-border/70 bg-background pl-9 pr-9 text-sm shadow-sm"
          />
          {filters.q ? (
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className="absolute right-1 top-1.5 h-8 w-8"
              onClick={() => updateFilters({ q: "" })}
            >
              <X className="h-4 w-4" />
            </Button>
          ) : null}
        </div>

        <div className="grid gap-2 sm:grid-cols-2 xl:flex xl:justify-end">
          <CommandFilter
            label="Модуль"
            value={filters.source_module}
            onValueChange={(value) => updateFilters({ source_module: value })}
            items={SOURCE_MODULES}
            placeholder="Все модули"
          />
          <CommandFilter
            label="Статус"
            value={filters.status}
            onValueChange={(value) => updateFilters({ status: value })}
            items={STATUSES}
            placeholder="Все статусы"
          />
          <CommandFilter
            label="Приоритет"
            value={filters.priority}
            onValueChange={(value) => updateFilters({ priority: value })}
            items={PRIORITIES.map((item) => ({
              value: item,
              label: priorityLabel(item),
            }))}
            placeholder="Любой приоритет"
          />
          <CommandFilter
            label="Сортировка"
            value={filters.sort}
            onValueChange={(value) => updateFilters({ sort: value })}
            items={ACTION_CENTER_SORT_OPTIONS}
            placeholder="Сортировка"
            includeAll={false}
          />
        </div>
      </div>

      <div className="flex flex-col gap-3 border-t pt-3 2xl:flex-row 2xl:items-center 2xl:justify-between">
        <div className="flex min-w-0 items-center gap-2">
          <span className="hidden shrink-0 text-xs font-medium text-muted-foreground sm:inline">
            Быстрый вид
          </span>
          <div className="flex min-w-0 flex-1 gap-1.5 overflow-x-auto pb-0.5 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
            {ACTION_CENTER_SAVED_VIEWS.map((view) => {
              const active = filters.view === view.value;
              return (
                <Button
                  key={view.value}
                  type="button"
                  size="sm"
                  variant={active ? "default" : "outline"}
                  className={`h-8 shrink-0 rounded-full px-3 text-xs ${
                    active ? "shadow-sm" : "border-border/70 bg-background"
                  }`}
                  onClick={() => updateFilters({ view: view.value })}
                >
                  {view.label}
                </Button>
              );
            })}
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <MoreFiltersMenu filters={filters} updateFilters={updateFilters} />
          {canUseBeta ? (
            <Button
              size="sm"
              variant={filters.include_beta ? "default" : "outline"}
              className="h-9 rounded-md border-border/70"
              onClick={() =>
                updateFilters({ include_beta: !filters.include_beta })
              }
            >
              <Sparkles className="h-3.5 w-3.5" />
              Бета
            </Button>
          ) : null}
          <Button
            size="sm"
            variant="ghost"
            className="h-9 rounded-md px-3"
            onClick={resetFilters}
          >
            <X className="h-3.5 w-3.5" />
            Сбросить
            {count ? (
              <Badge
                variant="secondary"
                className="ml-1 h-5 rounded-full px-1.5 text-[10px]"
              >
                {count}
              </Badge>
            ) : null}
          </Button>
        </div>
      </div>
    </div>
  );
}

function ManualTaskStepper({
  productCount,
  hasTitle,
  assigneeName,
  deadline,
  reviewing = false,
}: {
  productCount: number;
  hasTitle: boolean;
  assigneeName: string | null;
  deadline: string;
  reviewing?: boolean;
}) {
  const steps = [
    {
      label: "Товары",
      value: productCount ? `${productCount} выбрано` : "выберите",
      done: productCount > 0,
      icon: <PackageSearch className="h-4 w-4" />,
    },
    {
      label: "Задача",
      value: hasTitle ? "описана" : "заполните",
      done: hasTitle,
      icon: <FileText className="h-4 w-4" />,
    },
    {
      label: "Ответственный",
      value: assigneeName || "назначьте",
      done: Boolean(assigneeName),
      icon: <UserRound className="h-4 w-4" />,
    },
    {
      label: "Срок",
      value: deadline ? "указан" : "укажите",
      done: Boolean(deadline),
      icon: <Clock3 className="h-4 w-4" />,
    },
    {
      label: "Проверка",
      value: reviewing ? "открыта" : "далее",
      done: reviewing,
      icon: <ClipboardCheck className="h-4 w-4" />,
    },
  ];
  return (
    <div className="flex gap-2 overflow-x-auto pb-1 [scrollbar-width:none] sm:grid sm:grid-cols-5 sm:overflow-visible sm:pb-0 [&::-webkit-scrollbar]:hidden">
      {steps.map((step, index) => (
        <div
          key={step.label}
          className={`relative min-w-[132px] overflow-hidden rounded-lg border px-2.5 py-1.5 sm:min-w-0 sm:px-3 sm:py-2 ${
            step.done
              ? "border-primary/30 bg-primary/5"
              : "border-border bg-muted/20"
          }`}
        >
          {index < steps.length - 1 ? (
            <div className="absolute right-[-18px] top-1/2 hidden h-px w-9 bg-border sm:block" />
          ) : null}
          <div className="flex items-center gap-2">
            <span
              className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-md sm:h-7 sm:w-7 ${
                step.done
                  ? "bg-primary text-primary-foreground"
                  : "bg-background text-muted-foreground"
              }`}
            >
              {step.done ? (
                <Check className="h-3.5 w-3.5 sm:h-4 sm:w-4" />
              ) : (
                step.icon
              )}
            </span>
            <div className="min-w-0">
              <div className="truncate text-xs font-semibold">{step.label}</div>
              <div className="truncate text-[11px] text-muted-foreground">
                {step.value}
              </div>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

function ManualPresetButton({
  item,
  active,
  onClick,
}: {
  item: (typeof MANUAL_TASK_PRESETS)[number];
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`group min-w-0 rounded-lg border p-3 text-left transition-all hover:-translate-y-0.5 hover:border-primary/45 hover:shadow-sm ${
        active
          ? "border-primary bg-primary/5 ring-1 ring-primary/20"
          : "border-border bg-background"
      }`}
    >
      <div className="flex items-start gap-3">
        <span
          className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border ${item.tone}`}
        >
          {item.icon}
        </span>
        <span className="min-w-0">
          <span className="block truncate text-sm font-semibold">
            {item.label}
          </span>
          <span className="mt-0.5 block truncate text-xs text-muted-foreground">
            {item.hint}
          </span>
        </span>
      </div>
    </button>
  );
}

function ManualProductPickRow({
  product,
  active,
  onToggle,
}: {
  product: PortalProductRow;
  active: boolean;
  onToggle: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onToggle}
      className={`group grid min-w-0 grid-cols-[48px_minmax(0,1fr)_32px] items-center gap-3 rounded-lg border bg-background p-2 text-left transition-all hover:border-primary/40 hover:shadow-sm ${
        active
          ? "border-primary bg-primary/5 ring-1 ring-primary/20"
          : "border-border"
      }`}
    >
      <ProductThumb
        candidates={productRowImageCandidates(product)}
        label={productRowTitle(product)}
        className="h-[62px] w-12 rounded-lg"
      />
      <div className="min-w-0">
        <div className="line-clamp-2 text-sm font-semibold leading-snug">
          {productRowTitle(product)}
        </div>
        <div className="mt-1 truncate text-xs text-muted-foreground">
          {productRowSubtitle(product)}
        </div>
        <div className="mt-2 flex flex-wrap gap-1">
          {typeof product.revenue === "number" ? (
            <Badge
              variant="outline"
              className="h-5 rounded-full px-2 text-[10px]"
            >
              {formatMoney(product.revenue)}
            </Badge>
          ) : null}
          {typeof product.open_actions_count === "number" &&
          product.open_actions_count > 0 ? (
            <Badge
              variant="outline"
              className="h-5 rounded-full px-2 text-[10px]"
            >
              задач {product.open_actions_count}
            </Badge>
          ) : null}
        </div>
      </div>
      <span
        className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full border transition-colors ${
          active
            ? "border-primary bg-primary text-primary-foreground"
            : "border-border bg-muted/30 text-muted-foreground group-hover:bg-primary/10 group-hover:text-primary"
        }`}
      >
        {active ? <Check className="h-4 w-4" /> : <Plus className="h-4 w-4" />}
      </span>
    </button>
  );
}

function ManualTaskSummaryPanel({
  selectedProducts,
  title,
  description,
  selectedUserName,
  deadline,
  priority,
}: {
  selectedProducts: PortalProductRow[];
  title: string;
  description: string;
  selectedUserName: string | null;
  deadline: string;
  priority: string;
}) {
  const previewProducts = selectedProducts.slice(0, 8);
  return (
    <div className="mx-auto w-full max-w-5xl p-4 sm:p-5">
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_320px]">
        <div className="space-y-4">
          <div className="rounded-md border bg-card p-4 shadow-sm">
            <div className="mb-3 flex items-center justify-between gap-3">
              <div className="text-xs font-semibold uppercase text-muted-foreground">
                Brief
              </div>
              <Badge variant="secondary" className="rounded-full px-3 py-1">
                {priority}
              </Badge>
            </div>
            <div className="text-lg font-semibold leading-tight">
              {title.trim() || "Название задачи не заполнено"}
            </div>
            <div className="mt-3 whitespace-pre-wrap rounded-md border bg-muted/25 p-4 text-sm leading-relaxed">
              {description.trim() || "Инструкция не заполнена"}
            </div>
          </div>

          <div className="rounded-md border bg-card p-4 shadow-sm">
            <div className="mb-3 flex items-center justify-between gap-3">
              <div>
                <div className="text-sm font-semibold">Товары</div>
                <div className="text-xs text-muted-foreground">
                  Объекты, по которым будет создана задача.
                </div>
              </div>
              <Badge variant="outline" className="rounded-full">
                {selectedProducts.length}
              </Badge>
            </div>
            {previewProducts.length ? (
              <div className="grid gap-2 sm:grid-cols-2">
                {previewProducts.map((product) => (
                  <div
                    key={product.nm_id}
                    className="flex min-w-0 items-center gap-3 rounded-md border bg-background p-2"
                  >
                    <ProductThumb
                      candidates={productRowImageCandidates(product)}
                      label={productRowTitle(product)}
                      className="h-16 w-12 rounded-lg"
                    />
                    <div className="min-w-0">
                      <div className="line-clamp-2 text-sm font-semibold leading-snug">
                        {productRowTitle(product)}
                      </div>
                      <div className="mt-1 truncate text-xs text-muted-foreground">
                        {productRowSubtitle(product)}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="rounded-xl border border-dashed bg-background p-6 text-center text-sm text-muted-foreground">
                Сначала выберите товар
              </div>
            )}
            {selectedProducts.length > previewProducts.length ? (
              <div className="mt-3 text-xs text-muted-foreground">
                Ещё {selectedProducts.length - previewProducts.length} товаров
              </div>
            ) : null}
          </div>
        </div>

        <div className="space-y-4">
          <div className="rounded-md border bg-card p-4 shadow-sm">
            <div className="text-sm font-semibold">Исполнение</div>
            <div className="mt-3 space-y-2">
              <div className="rounded-md border bg-background px-3 py-3">
                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                  <UserRound className="h-3.5 w-3.5" />
                  Ответственный
                </div>
                <div className="mt-1 truncate text-sm font-semibold">
                  {selectedUserName || "Не выбран"}
                </div>
              </div>
              <div className="rounded-md border bg-background px-3 py-3">
                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                  <Clock3 className="h-3.5 w-3.5" />
                  Срок
                </div>
                <div className="mt-1 truncate text-sm font-semibold">
                  {deadline ? compactDateTime(deadline) : "Не указан"}
                </div>
              </div>
              <div className="rounded-md border bg-background px-3 py-3">
                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                  <Gauge className="h-3.5 w-3.5" />
                  Приоритет
                </div>
                <div className="mt-1 text-sm font-semibold">{priority}</div>
              </div>
            </div>
          </div>

          <div className="rounded-md border bg-muted/20 p-4">
            <div className="text-sm font-semibold">Что произойдёт дальше</div>
            <div className="mt-3 space-y-3">
              {[
                "Задача появится в группе «Ручные задачи».",
                "Исполнитель увидит brief, товары, срок и кнопки выполнения.",
                "После закрытия задача уйдёт из очереди.",
              ].map((item, index) => (
                <div
                  key={item}
                  className="grid grid-cols-[24px_1fr] gap-2 text-sm"
                >
                  <span className="flex h-6 w-6 items-center justify-center rounded-full bg-primary/10 text-xs font-semibold text-primary">
                    {index + 1}
                  </span>
                  <span className="text-muted-foreground">{item}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function ManualTaskEditFooter({
  canSubmit,
  createDisabledReason,
  onCancel,
  onNext,
}: {
  canSubmit: boolean;
  createDisabledReason: string;
  onCancel: () => void;
  onNext: () => void;
}) {
  return (
    <div className="shrink-0 border-t bg-card px-4 py-3">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0 flex-1 text-xs text-muted-foreground">
          {canSubmit ? "Следующий шаг: проверка задачи." : createDisabledReason}
        </div>
        <div className="flex gap-2">
          <Button
            type="button"
            variant="outline"
            className="h-10 rounded-xl"
            onClick={onCancel}
          >
            Отмена
          </Button>
          <Button
            type="button"
            className="h-10 rounded-xl shadow-sm"
            onClick={onNext}
            disabled={!canSubmit}
          >
            Далее
            <ArrowRight className="h-4 w-4" />
          </Button>
        </div>
      </div>
    </div>
  );
}

function ManualTaskReviewFooter({
  onBack,
  onCreate,
  isCreating,
}: {
  onBack: () => void;
  onCreate: () => void;
  isCreating: boolean;
}) {
  return (
    <div className="shrink-0 border-t bg-card px-4 py-3">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0 flex-1 text-xs text-muted-foreground">
          Проверьте данные. После подтверждения задача попадёт в очередь.
        </div>
        <div className="flex gap-2">
          <Button
            type="button"
            variant="outline"
            className="h-10 rounded-xl"
            onClick={onBack}
            disabled={isCreating}
          >
            <ArrowLeft className="h-4 w-4" />
            Назад
          </Button>
          <Button
            type="button"
            className="h-10 rounded-xl shadow-sm"
            onClick={onCreate}
            disabled={isCreating}
          >
            {isCreating ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <CheckCircle2 className="h-4 w-4" />
            )}
            Далее
          </Button>
        </div>
      </div>
    </div>
  );
}

function ManualTaskDialog({
  open,
  onOpenChange,
  accountId,
  dateFrom,
  dateTo,
  users,
  currentUserId,
  onCreated,
}: {
  open: boolean;
  onOpenChange: (value: boolean) => void;
  accountId: number | null | undefined;
  dateFrom?: string | null;
  dateTo?: string | null;
  users: PortalAssignableUser[] | undefined;
  currentUserId: number | null;
  onCreated: () => Promise<void> | void;
}) {
  const queryClient = useQueryClient();
  const [productSearch, setProductSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [selectedProducts, setSelectedProducts] = useState<PortalProductRow[]>(
    [],
  );
  const [taskKind, setTaskKind] = useState(MANUAL_TASK_PRESETS[0].key);
  const [title, setTitle] = useState(MANUAL_TASK_PRESETS[0].title);
  const [description, setDescription] = useState(
    MANUAL_TASK_PRESETS[0].description,
  );
  const [priority, setPriority] = useState<"P1" | "P2" | "P3" | "P4">("P2");
  const [deadline, setDeadline] = useState(defaultManualDeadline);
  const [assigneeId, setAssigneeId] = useState<number | null>(null);
  const [assigneeOpen, setAssigneeOpen] = useState(false);
  const [manualTaskStage, setManualTaskStage] = useState<"edit" | "review">(
    "edit",
  );

  useEffect(() => {
    const timer = window.setTimeout(
      () => setDebouncedSearch(productSearch.trim()),
      250,
    );
    return () => window.clearTimeout(timer);
  }, [productSearch]);

  useEffect(() => {
    if (!open || assigneeId != null) return;
    const list = users ?? [];
    const current = currentUserId
      ? list.find((item) => item.id === currentUserId)
      : null;
    setAssigneeId(current?.id ?? list[0]?.id ?? null);
  }, [assigneeId, currentUserId, open, users]);

  const productsQuery = useQuery({
    queryKey: [
      "action-center-manual-products",
      accountId,
      debouncedSearch,
      dateFrom,
      dateTo,
    ],
    enabled: open && !!accountId,
    queryFn: () =>
      fetchPortalProducts(
        accountId!,
        {
          limit: 18,
          offset: 0,
          ...(debouncedSearch ? { search: debouncedSearch } : {}),
          sort_by: "priority_score",
          sort_dir: "desc",
        },
        { dateFrom, dateTo },
      ),
    staleTime: 20_000,
  });

  const selectedIds = useMemo(
    () => new Set(selectedProducts.map((item) => Number(item.nm_id))),
    [selectedProducts],
  );
  const selectedUser =
    (users ?? []).find((item) => item.id === assigneeId) ?? null;
  const preset =
    MANUAL_TASK_PRESETS.find((item) => item.key === taskKind) ??
    MANUAL_TASK_PRESETS[0];
  const canSubmit = Boolean(
    accountId &&
    selectedProducts.length &&
    title.trim().length >= 3 &&
    deadline &&
    assigneeId,
  );

  const resetForm = () => {
    setProductSearch("");
    setDebouncedSearch("");
    setSelectedProducts([]);
    setTaskKind(MANUAL_TASK_PRESETS[0].key);
    setTitle(MANUAL_TASK_PRESETS[0].title);
    setDescription(MANUAL_TASK_PRESETS[0].description);
    setPriority("P2");
    setDeadline(defaultManualDeadline());
    setManualTaskStage("edit");
    const list = users ?? [];
    const current = currentUserId
      ? list.find((item) => item.id === currentUserId)
      : null;
    setAssigneeId(current?.id ?? list[0]?.id ?? null);
  };

  const createTask = useMutation({
    mutationFn: async () => {
      if (!accountId || !assigneeId)
        throw new Error("Не выбран аккаунт или ответственный.");
      return createManualPortalAction({
        account_id: accountId,
        title: title.trim(),
        description: description.trim() || null,
        task_kind: taskKind,
        priority,
        assigned_to_user_id: assigneeId,
        deadline_at: dateTimeLocalToIso(deadline),
        products: selectedProducts.map((product) => ({
          nm_id: Number(product.nm_id),
          sku_id: numberFromUnknown(product.sku_id),
          title: productRowTitle(product),
          vendor_code: firstString(product.vendor_code, product.article),
          photo_url: productRowImageCandidates(product)[0] ?? null,
        })),
      });
    },
    onSuccess: async () => {
      toast.success("Задача поставлена в очередь");
      await queryClient.invalidateQueries({ queryKey: ["portal-actions"] });
      await onCreated?.();
      resetForm();
      setManualTaskStage("edit");
      onOpenChange(false);
    },
    onError: (error: any) => {
      toast.error(error?.message ?? "Не удалось поставить задачу");
    },
  });

  const toggleProduct = (row: PortalProductRow) => {
    const nmId = Number(row.nm_id);
    if (!Number.isFinite(nmId)) return;
    setSelectedProducts((prev) =>
      prev.some((item) => Number(item.nm_id) === nmId)
        ? prev.filter((item) => Number(item.nm_id) !== nmId)
        : [...prev, row],
    );
  };

  const choosePreset = (key: string) => {
    const next =
      MANUAL_TASK_PRESETS.find((item) => item.key === key) ??
      MANUAL_TASK_PRESETS[0];
    setTaskKind(next.key);
    setTitle((current) =>
      current === preset.title || !current.trim() ? next.title : current,
    );
    setDescription((current) =>
      current === preset.description || !current.trim()
        ? next.description
        : current,
    );
  };
  const selectedUserName =
    selectedUser?.display_name ||
    selectedUser?.full_name ||
    selectedUser?.email ||
    null;
  const reviewing = manualTaskStage === "review";
  const createDisabledReason = !selectedProducts.length
    ? "Выберите хотя бы один товар"
    : title.trim().length < 3
      ? "Заполните название задачи"
      : !assigneeId
        ? "Назначьте ответственного"
        : !deadline
          ? "Укажите срок"
          : "";

  return (
    <Dialog
      open={open}
      onOpenChange={(value) => {
        if (!value) setManualTaskStage("edit");
        onOpenChange(value);
      }}
    >
      <DialogContent
        className={`flex w-[calc(100vw-24px)] flex-col overflow-hidden border bg-background p-0 shadow-2xl ${
          reviewing
            ? "h-[min(760px,92vh)] max-w-4xl rounded-xl"
            : "h-[min(840px,94vh)] max-w-7xl rounded-xl"
        }`}
      >
        {reviewing ? (
          <>
            <DialogHeader className="shrink-0 border-b bg-card px-4 py-4 pr-12 sm:px-5">
              <DialogTitle className="flex items-center gap-2 text-lg">
                <span className="flex h-9 w-9 items-center justify-center rounded-md bg-primary text-primary-foreground shadow-sm">
                  <ClipboardCheck className="h-4 w-4" />
                </span>
                Проверка задачи
              </DialogTitle>
              <DialogDescription>
                Убедитесь, что товары, исполнитель, срок и brief указаны
                правильно.
              </DialogDescription>
            </DialogHeader>
            <ScrollArea className="min-h-0 flex-1 bg-muted/10">
              <ManualTaskSummaryPanel
                selectedProducts={selectedProducts}
                title={title}
                description={description}
                selectedUserName={selectedUserName}
                deadline={deadline}
                priority={priority}
              />
            </ScrollArea>
            <ManualTaskReviewFooter
              onBack={() => setManualTaskStage("edit")}
              onCreate={() => createTask.mutate()}
              isCreating={createTask.isPending}
            />
          </>
        ) : (
          <>
            <div className="shrink-0 border-b bg-card">
              <DialogHeader className="px-4 py-3 pr-12 sm:px-5 sm:py-4">
                <DialogTitle className="flex items-center gap-2 text-lg">
                  <span className="flex h-9 w-9 items-center justify-center rounded-md bg-primary text-primary-foreground shadow-sm">
                    <Plus className="h-4 w-4" />
                  </span>
                  Поставить ручную задачу
                </DialogTitle>
                <DialogDescription className="mt-1">
                  Выберите товары, brief, исполнителя и срок.
                </DialogDescription>
              </DialogHeader>
              <div className="px-4 pb-3 sm:px-5 sm:pb-4">
                <ManualTaskStepper
                  productCount={selectedProducts.length}
                  hasTitle={title.trim().length >= 3}
                  assigneeName={selectedUserName}
                  deadline={deadline}
                  reviewing={reviewing}
                />
              </div>
            </div>

            <div className="grid min-h-0 flex-1 overflow-hidden lg:grid-cols-[minmax(0,1fr)_420px]">
              <div className="flex min-h-0 flex-col border-r bg-muted/10">
                <div className="border-b bg-background px-4 py-3">
                  <div className="mb-3 flex items-center justify-between gap-3">
                    <div>
                      <div className="text-sm font-semibold">
                        Товары для задачи
                      </div>
                      <div className="text-xs text-muted-foreground">
                        Можно выбрать один товар или сразу группу.
                      </div>
                    </div>
                    <Badge
                      variant={
                        selectedProducts.length ? "default" : "secondary"
                      }
                      className="rounded-full"
                    >
                      {selectedProducts.length} выбрано
                    </Badge>
                  </div>
                  <div className="relative">
                    <Search className="pointer-events-none absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
                    <Input
                      value={productSearch}
                      onChange={(event) => setProductSearch(event.target.value)}
                      placeholder="Найдите товар по nm, артикулу или названию"
                      className="h-11 rounded-xl border-border/70 bg-muted/20 pl-9 pr-3 text-sm shadow-sm"
                    />
                  </div>
                  {selectedProducts.length ? (
                    <div className="mt-3 flex gap-2 overflow-x-auto pb-1 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
                      {selectedProducts.slice(0, 6).map((product) => (
                        <div
                          key={product.nm_id}
                          className="flex max-w-[210px] shrink-0 items-center gap-2 rounded-full border bg-card py-1 pl-1 pr-2 text-left shadow-sm hover:border-primary/40"
                        >
                          <ProductThumb
                            candidates={productRowImageCandidates(product)}
                            label={productRowTitle(product)}
                            className="h-7 w-7 rounded-full"
                          />
                          <span className="min-w-0 truncate text-xs font-medium">
                            {productRowTitle(product)}
                          </span>
                          <button
                            type="button"
                            className="shrink-0 rounded-full p-0.5 text-muted-foreground hover:bg-muted hover:text-foreground"
                            onClick={(event) => {
                              event.stopPropagation();
                              toggleProduct(product);
                            }}
                            aria-label="Убрать товар"
                          >
                            <X className="h-3 w-3" />
                          </button>
                        </div>
                      ))}
                      {selectedProducts.length > 6 ? (
                        <Badge
                          variant="secondary"
                          className="h-9 shrink-0 rounded-full px-3"
                        >
                          +{selectedProducts.length - 6}
                        </Badge>
                      ) : null}
                    </div>
                  ) : null}
                </div>

                <ScrollArea className="min-h-0 flex-1">
                  <div className="grid gap-2.5 p-4">
                    {productsQuery.isLoading ? (
                      Array.from({ length: 6 }).map((_, index) => (
                        <Skeleton key={index} className="h-[82px] rounded-lg" />
                      ))
                    ) : productsQuery.data?.items?.length ? (
                      productsQuery.data.items.map((product) => {
                        const active = selectedIds.has(Number(product.nm_id));
                        return (
                          <ManualProductPickRow
                            key={product.nm_id}
                            product={product}
                            active={active}
                            onToggle={() => toggleProduct(product)}
                          />
                        );
                      })
                    ) : (
                      <div className="flex min-h-[360px] items-center justify-center rounded-xl border border-dashed bg-background p-6 text-center">
                        <div className="max-w-xs space-y-2">
                          <PackageSearch className="mx-auto h-9 w-9 text-muted-foreground" />
                          <div className="font-semibold">Товары не найдены</div>
                          <div className="text-sm text-muted-foreground">
                            Попробуйте nm ID, артикул продавца или часть
                            названия.
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                </ScrollArea>
              </div>

              <div className="flex min-h-0 flex-col bg-background">
                <ScrollArea className="min-h-0 flex-1">
                  <div className="space-y-4 p-4">
                    <div className="rounded-xl border bg-card p-3">
                      <div className="mb-3 flex items-center justify-between gap-3">
                        <div>
                          <div className="text-sm font-semibold">
                            Тип работы
                          </div>
                          <div className="text-xs text-muted-foreground">
                            Выберите шаблон, потом поправьте текст.
                          </div>
                        </div>
                        <Badge variant="outline" className="rounded-full">
                          {preset.label}
                        </Badge>
                      </div>
                      <div className="grid gap-2 sm:grid-cols-2">
                        {MANUAL_TASK_PRESETS.map((item) => (
                          <ManualPresetButton
                            key={item.key}
                            item={item}
                            active={taskKind === item.key}
                            onClick={() => choosePreset(item.key)}
                          />
                        ))}
                      </div>
                    </div>

                    <div className="rounded-xl border bg-card p-3">
                      <div className="mb-3">
                        <div className="text-sm font-semibold">
                          Содержание задачи
                        </div>
                        <div className="text-xs text-muted-foreground">
                          Пишите как поручение человеку: результат должен быть
                          понятен без созвона.
                        </div>
                      </div>
                      <div className="space-y-3">
                        <div className="space-y-1.5">
                          <Label htmlFor="manual-task-title">Название</Label>
                          <Input
                            id="manual-task-title"
                            value={title}
                            onChange={(event) => setTitle(event.target.value)}
                            placeholder="Например: изменить title для летних костюмов"
                            className="h-11 rounded-xl"
                          />
                        </div>
                        <div className="space-y-1.5">
                          <Label htmlFor="manual-task-description">
                            Инструкция
                          </Label>
                          <Textarea
                            id="manual-task-description"
                            value={description}
                            onChange={(event) =>
                              setDescription(event.target.value)
                            }
                            rows={5}
                            placeholder="Что проверить, что изменить, где взять данные, какой результат считается готовым."
                            className="min-h-[130px] rounded-xl"
                          />
                        </div>
                      </div>
                    </div>

                    <div className="rounded-xl border bg-card p-3">
                      <div className="mb-3">
                        <div className="text-sm font-semibold">Исполнение</div>
                        <div className="text-xs text-muted-foreground">
                          Кто делает, когда нужно закончить и насколько срочно.
                        </div>
                      </div>
                      <div className="grid gap-3 sm:grid-cols-2">
                        <div className="space-y-1.5 sm:col-span-2">
                          <Label>Ответственный</Label>
                          <Popover
                            open={assigneeOpen}
                            onOpenChange={setAssigneeOpen}
                          >
                            <PopoverTrigger asChild>
                              <Button
                                type="button"
                                variant="outline"
                                role="combobox"
                                className="h-11 w-full justify-between rounded-xl"
                              >
                                <span className="flex min-w-0 items-center gap-2">
                                  <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-muted text-muted-foreground">
                                    <UserRound className="h-4 w-4" />
                                  </span>
                                  <span className="truncate">
                                    {selectedUserName ||
                                      "Выберите ответственного"}
                                  </span>
                                </span>
                                <ChevronDown className="h-4 w-4 text-muted-foreground" />
                              </Button>
                            </PopoverTrigger>
                            <PopoverContent
                              align="start"
                              className="w-[360px] p-0"
                            >
                              <Command>
                                <CommandInput placeholder="Найти сотрудника" />
                                <CommandList>
                                  <CommandEmpty>Никого не найдено</CommandEmpty>
                                  <CommandGroup>
                                    {(users ?? []).map((item) => {
                                      const active = item.id === assigneeId;
                                      return (
                                        <CommandItem
                                          key={item.id}
                                          value={`${item.display_name} ${item.full_name} ${item.email}`}
                                          onSelect={() => {
                                            setAssigneeId(item.id);
                                            setAssigneeOpen(false);
                                          }}
                                        >
                                          <Check
                                            className={`h-4 w-4 ${active ? "opacity-100" : "opacity-0"}`}
                                          />
                                          <div className="min-w-0">
                                            <div className="truncate text-sm font-medium">
                                              {item.display_name ||
                                                item.full_name ||
                                                item.email}
                                            </div>
                                            <div className="truncate text-xs text-muted-foreground">
                                              {item.email}
                                            </div>
                                          </div>
                                        </CommandItem>
                                      );
                                    })}
                                  </CommandGroup>
                                </CommandList>
                              </Command>
                            </PopoverContent>
                          </Popover>
                        </div>
                        <div className="space-y-1.5">
                          <Label htmlFor="manual-task-deadline">Срок</Label>
                          <Input
                            id="manual-task-deadline"
                            type="datetime-local"
                            value={deadline}
                            onChange={(event) =>
                              setDeadline(event.target.value)
                            }
                            className="h-11 rounded-xl"
                          />
                        </div>
                        <div className="space-y-1.5">
                          <Label>Приоритет</Label>
                          <div className="grid h-11 grid-cols-4 gap-1 rounded-xl border bg-muted/30 p-1">
                            {(["P1", "P2", "P3", "P4"] as const).map((item) => (
                              <Button
                                key={item}
                                type="button"
                                variant={
                                  priority === item ? "default" : "outline"
                                }
                                size="sm"
                                className="h-full rounded-lg border-0 px-0 shadow-none"
                                onClick={() => setPriority(item)}
                              >
                                {item}
                              </Button>
                            ))}
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                </ScrollArea>

                <ManualTaskEditFooter
                  canSubmit={canSubmit}
                  createDisabledReason={createDisabledReason}
                  onCancel={() => onOpenChange(false)}
                  onNext={() => setManualTaskStage("review")}
                />
              </div>
            </div>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}

export function ActionCenterPageContainer({
  routeSearch,
}: {
  routeSearch: ActionCenterSearch;
}) {
  const { activeId } = useAccounts();
  const { user } = useAuth();
  const { from: dateFrom, to: dateTo } = useDateRange();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const routeFilters = useActionCenterFilters(routeSearch);
  const routeGroupKey = useMemo(
    () => normalizeProblemGroupKey(routeSearch.group),
    [routeSearch.group],
  );
  const routeActionId = routeSearch.action_id ?? null;
  const routeFilterKey = useMemo(
    () => JSON.stringify(routeSearch ?? {}),
    [routeSearch],
  );
  const [filters, setFilters] = useState<ActionCenterFilterState>(routeFilters);
  const [selectedId, setSelectedId] = useState<string | null>(
    () => routeActionId,
  );
  const [selectedGroupKey, setSelectedGroupKey] =
    useState<ProblemGroupKey | null>(() => routeGroupKey);
  const [taskBoardMode, setTaskBoardMode] = useState<TaskBoardMode>("active");
  const [busy, setBusy] = useState<string | null>(null);
  const [recheckBusy, setRecheckBusy] = useState<string | null>(null);
  const [manualTaskOpen, setManualTaskOpen] = useState(false);

  const canUseBeta = !!user?.is_superuser;
  const currentUserId = user?.id ?? null;
  const currentRole = userAccountRole(user, activeId);
  const canAssignTasks = roleRank(currentRole) >= roleRank("operator");

  useEffect(() => {
    setFilters({
      ...routeFilters,
      include_beta: canUseBeta && routeFilters.include_beta,
    });
  }, [canUseBeta, routeFilterKey]);

  useEffect(() => {
    setSelectedGroupKey((current) => {
      if (current === routeGroupKey) return current;
      setSelectedId(routeActionId);
      return routeGroupKey;
    });
  }, [routeActionId, routeGroupKey]);

  useEffect(() => {
    if (routeActionId) setSelectedId(routeActionId);
  }, [routeActionId]);

  const navigateActionCenter = (
    nextFilters: ActionCenterFilterState,
    groupKey: ProblemGroupKey | null,
    replace = true,
  ) => {
    navigate({
      to: "/action-center",
      search: {
        ...actionCenterSearchFromState(nextFilters),
        group: groupKey ?? undefined,
      } as ActionCenterSearch,
      replace,
    });
  };

  useEffect(() => {
    const status = norm(filters.status);
    if (COMPLETED_TASK_STATUSES.has(status) && taskBoardMode !== "completed") {
      setTaskBoardMode("completed");
      setSelectedGroupKey(null);
      setSelectedId(null);
      navigateActionCenter(filters, null);
    } else if (
      DEACTIVATED_TASK_STATUSES.has(status) &&
      taskBoardMode !== "deactivated"
    ) {
      setTaskBoardMode("deactivated");
      setSelectedGroupKey(null);
      setSelectedId(null);
      navigateActionCenter(filters, null);
    }
  }, [filters.status, taskBoardMode]);

  const updateFilters = (
    patch: Partial<ActionCenterFilterState>,
    options: { groupKey?: ProblemGroupKey | null; replace?: boolean } = {},
  ) => {
    const next = {
      ...filters,
      ...patch,
      include_beta: canUseBeta
        ? (patch.include_beta ?? filters.include_beta)
        : false,
    };
    const nextGroupKey =
      "groupKey" in options ? (options.groupKey ?? null) : selectedGroupKey;
    setFilters(next);
    navigateActionCenter(next, nextGroupKey, options.replace ?? true);
  };

  const resetFilters = () => {
    const next = {
      ...ACTION_CENTER_DEFAULT_FILTERS,
      include_beta: canUseBeta && filters.include_beta,
    };
    setTaskBoardMode("active");
    setSelectedGroupKey(null);
    setSelectedId(null);
    updateFilters(next, { groupKey: null });
  };

  const boardStatusForQuery =
    taskBoardMode === "completed"
      ? COMPLETED_TASK_QUERY_STATUS
      : taskBoardMode === "deactivated"
        ? DEACTIVATED_TASK_QUERY_STATUS
        : ACTIVE_TASK_QUERY_STATUS;

  const queryStatus =
    filters.status !== "all" ? filters.status : boardStatusForQuery;

  const queryFilters = useMemo(
    () => ({
      ...(queryStatus ? { status: queryStatus } : {}),
      ...(filters.source_module !== "all"
        ? { source_module: [filters.source_module] }
        : {}),
      ...(filters.priority !== "all" ? { priority: [filters.priority] } : {}),
      ...(filters.severity !== "all" ? { severity: [filters.severity] } : {}),
      ...(filters.problem_code !== "all"
        ? { problem_code: [filters.problem_code] }
        : {}),
      ...(filters.trust_state !== "all"
        ? { trust_state: [filters.trust_state] }
        : {}),
      ...(filters.impact_type !== "all"
        ? { impact_type: [filters.impact_type] }
        : {}),
      ...(routeSearch.nm_id ? { nm_id: routeSearch.nm_id } : {}),
      ...(canUseBeta && filters.include_beta ? { include_beta: true } : {}),
    }),
    [canUseBeta, filters, queryStatus, routeSearch.nm_id],
  );

  const { actionsQuery, usersQuery } = useActionCenterData({
    activeId,
    canAssignTasks,
    dateFrom,
    dateTo,
    queryFilters,
  });
  const capabilitiesQuery = useQuery({
    queryKey: ["action-center-capabilities", activeId],
    queryFn: () => fetchActionCenterCapabilities(activeId!),
    enabled: !!activeId,
    staleTime: 5 * 60_000,
  });
  const dataSyncStatusQuery = useQuery({
    queryKey: ["action-center-data-sync-status", activeId],
    queryFn: () => fetchDataSyncStatus(activeId!),
    enabled: !!activeId,
    staleTime: 60_000,
  });
  const missingCostRevenueQuery = useQuery({
    queryKey: [
      "action-center-missing-cost-revenue",
      activeId,
      dateFrom,
      dateTo,
    ],
    queryFn: () =>
      fetchCostsMissing(activeId!, {
        limit: 1,
        offset: 0,
        dateFrom: dateFrom ?? undefined,
        dateTo: dateTo ?? undefined,
        onlyRevenue: true,
      }),
    enabled: !!activeId,
    staleTime: 60_000,
  });
  const { data, isLoading, error, refetch } = actionsQuery;
  const mutation = useActionCenterMutations({
    activeId,
    queryClient,
    setBusy,
  });

  const rawItems = extractActions(data);
  const serverTotal = Number(data?.total ?? rawItems.length ?? 0);
  const adaptedItems = useMemo(
    () =>
      rawItems.map((action) =>
        adaptActionCenterItem(action, { users: usersQuery.data }),
      ),
    [rawItems, usersQuery.data],
  );

  const visibleItems = useMemo(
    () =>
      adaptedItems.filter((item) => {
        if (isSystemHandledAction(item)) return false;
        if (
          actionCenterShouldHideBetaSignal(
            isTestOnlyProblem(item) || isBetaAction(item),
            {
              canUseBeta,
              includeBeta: filters.include_beta,
            },
          )
        ) {
          return false;
        }
        return item.is_seller_visible || canUseBeta;
      }),
    [adaptedItems, canUseBeta, filters.include_beta],
  );

  const now = useMemo(() => new Date(), [data]);
  const filteredItems = useMemo(() => {
    const matched = visibleItems.filter((item) =>
      actionCenterMatchesFilters(item, filters, {
        currentUserId,
        now,
        waitsForRecheck: waitsForRecheckAction(item),
      }),
    );
    return sortActionCenterItems(matched, filters.sort);
  }, [currentUserId, filters, now, visibleItems]);
  const missingCostRevenueValue = numberFromUnknown(
    missingCostRevenueQuery.data?.summary?.affected_revenue,
  );
  const displayItems = useMemo(
    () =>
      applyActionDisplayMoney(filteredItems, {
        missingCostRevenue: missingCostRevenueValue,
      }),
    [filteredItems, missingCostRevenueValue],
  );
  const taskBoardCounts = useMemo(
    () =>
      displayItems.reduce(
        (acc, item) => {
          acc[taskBoardModeForItem(item)] += 1;
          return acc;
        },
        { active: 0, completed: 0, deactivated: 0 } as Record<
          TaskBoardMode,
          number
        >,
      ),
    [displayItems],
  );
  const boardItems = useMemo(
    () =>
      displayItems.filter(
        (item) => taskBoardModeForItem(item) === taskBoardMode,
      ),
    [displayItems, taskBoardMode],
  );

  const problemGroups = useMemo(
    () =>
      buildProblemGroups(boardItems, {
        missingCostRevenue: missingCostRevenueValue,
      }),
    [boardItems, missingCostRevenueValue],
  );
  const selectedGroup = selectedGroupKey
    ? (problemGroups.find((group) => group.key === selectedGroupKey) ?? null)
    : null;
  const capabilityDomains = capabilitiesQuery.data?.domains ?? [];
  const selectedDomain = selectedGroupKey
    ? (capabilityDomains.find(
        (domain) => normalizeProblemGroupKey(domain.key) === selectedGroupKey,
      ) ?? null)
    : null;
  const workItems = selectedGroup ? selectedGroup.items : boardItems;

  useEffect(() => {
    if (
      selectedGroupKey &&
      !isLoading &&
      problemGroups.length > 0 &&
      !problemGroups.some((group) => group.key === selectedGroupKey)
    ) {
      setSelectedGroupKey(null);
      setSelectedId(null);
      navigateActionCenter(filters, null);
    }
  }, [filters, isLoading, problemGroups, selectedGroupKey]);

  const switchTaskBoardMode = (mode: TaskBoardMode) => {
    setTaskBoardMode(mode);
    setSelectedGroupKey(null);
    setSelectedId(null);
    const status = norm(filters.status);
    const statusForcesCompleted = COMPLETED_TASK_STATUSES.has(status);
    const statusForcesDeactivated = DEACTIVATED_TASK_STATUSES.has(status);
    if (
      (mode === "active" &&
        (statusForcesCompleted || statusForcesDeactivated)) ||
      (mode === "completed" && statusForcesDeactivated) ||
      (mode === "deactivated" && statusForcesCompleted)
    ) {
      updateFilters({ status: "all" }, { groupKey: null });
    } else {
      navigateActionCenter(filters, null);
    }
  };

  const queueItems = workItems.slice(0, MAX_QUEUE_ITEMS);
  const openItems =
    taskBoardMode === "active"
      ? workItems.filter((item) => taskBoardModeForItem(item) === "active")
      : workItems;
  const closedItems =
    taskBoardMode === "completed"
      ? workItems
      : workItems.filter(isClosedAction);
  const urgentItems =
    taskBoardMode === "active" ? openItems.filter(isUrgentAction) : [];
  const blockerItems =
    taskBoardMode === "active" ? openItems.filter(isDataBlockerAction) : [];
  const overdueItems =
    taskBoardMode === "active"
      ? openItems.filter((item) => isOverdueAction(item, now))
      : [];
  const actionableItems =
    taskBoardMode === "active" ? openItems.filter(isActionable) : [];
  const coreExecutionSummary = useMemo(
    () =>
      actionExecutionSummary(
        openItems.filter((item) => !isContentQualityOpportunityAction(item)),
      ),
    [openItems],
  );
  const overviewImpactSummary = useMemo(
    () => dedupedImpactSummary(openItems),
    [openItems],
  );

  const selected = useMemo(() => {
    if (!queueItems.length) return null;
    return queueItems.find((item) => item.id === selectedId) ?? queueItems[0];
  }, [queueItems, selectedId]);

  useEffect(() => {
    if (!queueItems.length) {
      setSelectedId(null);
      return;
    }
    if (!selectedId || !queueItems.some((item) => item.id === selectedId)) {
      setSelectedId(queueItems[0].id);
    }
  }, [queueItems, selectedId]);

  const selectedIndex = selected
    ? queueItems.findIndex((item) => item.id === selected.id)
    : -1;
  const nextItem =
    selectedIndex >= 0
      ? (queueItems
          .slice(selectedIndex + 1)
          .find((item) =>
            taskBoardMode === "active" ? !isClosedAction(item) : true,
          ) ??
        queueItems.find(
          (item) =>
            (taskBoardMode === "active" ? !isClosedAction(item) : true) &&
            item.id !== selected?.id,
        ))
      : queueItems.find((item) =>
          taskBoardMode === "active" ? !isClosedAction(item) : true,
        );

  const goNext = () => {
    if (nextItem) setSelectedId(nextItem.id);
  };

  const saveStatus = (
    item: ActionCenterItem,
    status: string,
    moveNext = false,
    options: { deadline_at?: string; comment?: string } = {},
  ) => {
    const effectiveDeadline =
      options?.deadline_at ??
      (status === "done" ? postponeUntilIso(1) : undefined);
    const defaultComment =
      status === "ignored"
        ? "Пропущено из очереди Центра действий"
        : status === "done"
          ? "Выполнено из Центра действий. Скрыто из активной очереди до следующей ежедневной проверки."
          : status === "postponed"
            ? "Отложено из очереди Центра действий"
            : status === "reopened"
              ? "Возвращено в активные задачи"
              : "";
    setBusy(`${item.id}:${status}`);
    mutation.mutate(
      {
        a: item,
        status,
        deadline_at: effectiveDeadline,
        last_comment: options?.comment ?? defaultComment,
      },
      {
        onSuccess: () => {
          if (moveNext) goNext();
        },
      },
    );
  };

  const recheck = async (item: ActionCenterItem) => {
    const problemId = dynamicProblemInstanceId(item);
    setRecheckBusy(item.id);
    try {
      if (problemId != null) {
        await recheckProblemInstance(problemId, activeId);
        toast.success("Перепроверка запущена");
      } else {
        await refetch();
        toast.success("Очередь обновлена");
      }
      await queryClient.invalidateQueries({ queryKey: ["portal-actions"] });
      await refetch();
    } catch (e) {
      toast.error("Не удалось запустить перепроверку");
    } finally {
      setRecheckBusy(null);
    }
  };

  const applyGroupRecalculate = async () => {
    const target = selected ?? openItems[0] ?? null;
    if (target) {
      await recheck(target);
    } else {
      await refetch();
      toast.success("Очередь обновлена");
    }
  };

  const openProblemGroup = (key: ProblemGroupKey) => {
    setSelectedGroupKey(key);
    setSelectedId(null);
    navigateActionCenter(filters, key, false);
  };

  const openProblemItem = (item: ActionCenterItem) => {
    const key = problemGroupKey(item);
    setSelectedGroupKey(key);
    setSelectedId(item.id);
    navigate({
      to: "/action-center",
      search: {
        ...actionCenterSearchFromState(filters),
        group: key,
        action_id: item.id,
      } as ActionCenterSearch,
      replace: false,
    });
  };

  const closeProblemGroup = () => {
    setSelectedGroupKey(null);
    setSelectedId(null);
    navigateActionCenter(filters, null);
  };

  if (!activeId) {
    return (
      <PageShell>
        <NoAccountSelected />
      </PageShell>
    );
  }

  if (isLoading) return <EmptyLoader />;

  if (error) {
    return (
      <PageShell>
        <EndpointError error={error} reset={() => refetch()} />
      </PageShell>
    );
  }

  return (
    <PageShell>
      <ManualTaskDialog
        open={manualTaskOpen}
        onOpenChange={setManualTaskOpen}
        accountId={activeId}
        dateFrom={dateFrom}
        dateTo={dateTo}
        users={usersQuery.data}
        currentUserId={currentUserId}
        onCreated={async () => {
          setTaskBoardMode("active");
          updateFilters(
            { view: "all", source_module: "manual" },
            { groupKey: "manual_tasks", replace: false },
          );
          setSelectedGroupKey("manual_tasks");
          setSelectedId(null);
          await refetch();
        }}
      />

      <div className="space-y-4">
        {!selectedGroup ? (
          <ReferenceOverview
            items={openItems}
            groups={problemGroups}
            counts={taskBoardCounts}
            openCount={openItems.length}
            urgentCount={urgentItems.length}
            overdueCount={overdueItems.length}
            execution={coreExecutionSummary}
            blockerCount={blockerItems.length}
            moneyAtStake={overviewImpactSummary.value}
            moneyOverlap={overviewImpactSummary.overlap}
            dataHealthStatus={dataSyncStatusQuery.data}
            filters={filters}
            updateFilters={updateFilters}
            resetFilters={resetFilters}
            canUseBeta={canUseBeta}
            onOpenItem={openProblemItem}
            onOpenGroup={openProblemGroup}
            onCreateManualTask={() => setManualTaskOpen(true)}
            canAssignTasks={canAssignTasks}
            onRefresh={() => refetch()}
          />
        ) : (
          <ReferenceProblemDetailPage
            item={selected}
            group={selectedGroup}
            accountId={activeId}
            dateFrom={dateFrom}
            dateTo={dateTo}
            busy={busy || recheckBusy}
            onBack={closeProblemGroup}
            onStatus={saveStatus}
            onDoneNext={(item) => saveStatus(item, "done", true)}
            onRecheck={recheck}
            onChanged={async () => {
              await queryClient.invalidateQueries({
                queryKey: ["portal-actions"],
              });
              await refetch();
            }}
            onNext={goNext}
            hasNext={Boolean(nextItem)}
          />
        )}
      </div>
    </PageShell>
  );
}
