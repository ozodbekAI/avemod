// @ts-nocheck
import { createFileRoute } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import type { ElementType, ReactNode } from "react";
import { useAccounts } from "@/lib/account-context";
import {
  fetchReputationSummary,
  fetchReputationInbox,
  fetchReputationSettings,
  fetchReputationAnalytics,
  fetchReputationDrafts,
  fetchReputationChats,
  fetchReputationLearning,
  fetchReputationBrands,
  fetchReputationProductInsights,
  fetchReputationAdminGenerationLogDetail,
  fetchReputationAdminGenerationLogs,
  fetchReputationAdminPromptDebug,
  fetchReputationAdminProviderStatus,
  updateReputationSettings,
  toggleReputationLearning,
  updateReputationPrompts,
  applyReputationLearning,
  deleteReputationLearningEntry,
  resetReputationLearning,
  probeReputationAdminPrompt,
  syncReputation,
  createReputationDraft,
  approveAllReputationDrafts,
  approveReputationDraft,
  regenerateReputationDraft,
  rejectReputationDraft,
  publishReputationDraft,
  markReputationNoReply,
} from "@/lib/portal";
import { useModuleStatus, useModuleVisible } from "@/lib/modules-health";
import { useAuth } from "@/lib/auth-context";
import { PageShell, PageHeader } from "@/components/PageShell";
import { NoAccountSelected } from "@/components/portal/NoAccountSelected";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { EndpointError } from "@/components/EndpointError";
import { DataDependencyNotice } from "@/components/data-health/DataCoveragePanel";
import { routeSearchText } from "@/lib/action-center-routing";
import {
  AlertTriangle,
  Brain,
  Bot,
  CheckCircle2,
  Clock,
  ExternalLink,
  Filter,
  Image as ImageIcon,
  Info,
  Pencil,
  RefreshCw,
  RotateCcw,
  Search,
  Settings2,
  ListChecks,
  Sparkles,
  Star,
  Palette,
  PowerOff,
  Trash2,
  FileText,
  Send,
  BarChart3,
  MessageSquare,
  Plus,
  ThumbsDown,
  ThumbsUp,
  XCircle,
  ShieldCheck,
} from "lucide-react";
import { toast } from "sonner";

type ReputationSearch = {
  nm_id?: string;
  tab?: string;
};

const REPUTATION_TABS = new Set([
  "reviews",
  "questions",
  "chats",
  "drafts",
  "analytics",
  "settings",
  "debug",
]);

function normalizeRouteNmId(value: unknown): string {
  return routeSearchText(value)?.replace(/[^\d]/g, "") ?? "";
}

export const Route = createFileRoute("/_authenticated/reputation")({
  validateSearch: (search: Record<string, unknown>): ReputationSearch => {
    const tab = routeSearchText(search.tab);
    const nmId = normalizeRouteNmId(search.nm_id);
    return {
      ...(nmId ? { nm_id: nmId } : {}),
      ...(tab && REPUTATION_TABS.has(tab) ? { tab } : {}),
    };
  },
  component: ReputationPage,
  errorComponent: ({ error, reset }) => (
    <EndpointError error={error} reset={reset} />
  ),
});

const SUMMARY_LABELS: Record<string, string> = {
  total: "Всего",
  total_count: "Всего",
  new_count: "Новые",
  pending_count: "В работе",
  answered_count: "Отвечено",
  drafts_count: "Черновики",
  published_count: "Опубликовано",
  avg_rating: "Средний рейтинг",
  rating: "Рейтинг",
  reviews_count: "Отзывы",
  questions_count: "Вопросы",
  chats_count: "Чаты",
  unanswered_count: "Без ответа",
  sla_hours: "SLA, часов",
  updated_at: "Обновлено",
  last_sync_at: "Последняя синхронизация",
};

const STATUS_LABELS: Record<string, string> = {
  disabled: "Отключено",
  not_configured: "Не настроено",
  enabled: "Включено",
  active: "Активно",
  running: "Выполняется",
  partial: "Частично",
  empty: "Нет данных",
  failed: "Ошибка",
  ok: "ОК",
  new: "Новое",
  pending: "В работе",
  needs_reply: "Нужен ответ",
  answered: "Отвечено",
  draft: "Черновик",
  draft_ready: "Черновик готов",
  in_progress: "В работе",
  ignored: "Без ответа",
  published: "Опубликовано",
  approved: "Одобрено",
  done: "Готово",
  rejected: "Отклонено",
};

const KIND_LABELS: Record<string, string> = {
  review: "Отзыв",
  question: "Вопрос",
  chat: "Чат",
  feedback: "Отзыв",
};

const REPLY_MODE_LABELS: Record<string, string> = {
  manual: "Ручной",
  semi: "Полуавто",
  auto: "Авто",
};

const RUNTIME_MODE_LABELS: Record<string, string> = {
  local: "Рантайм: Finance local",
  external_adapter: "Рантайм: Aveotvet adapter",
  disabled: "Рантайм: отключен",
};

const REPLY_MODE_HINTS: Record<string, string> = {
  manual: "только ручная проверка",
  semi: "черновик ИИ + оператор",
  auto: "черновик ИИ готов к одобрению",
};

const TONE_LABELS: Record<string, string> = {
  polite: "Вежливый",
  warm: "Тёплый",
  empathetic: "С эмпатией",
  clear: "Чёткий",
};

const LENGTH_LABELS: Record<string, string> = {
  short: "Короткий",
  medium: "Средний",
  detailed: "Подробный",
};

const BUCKET_LABELS: Record<string, string> = {
  positive: "Позитив",
  neutral: "Нейтрал",
  negative: "Негатив",
  manual_attention: "Ручная проверка",
};

const SENTIMENT_LABELS: Record<string, string> = {
  negative: "Негатив",
  mixed: "Смешанный",
  neutral: "Нейтрал",
  positive: "Позитив",
  unknown: "Неизвестно",
};

const PRIORITY_LABELS: Record<string, string> = {
  P0: "P0 срочно",
  P1: "P1 высоко",
  P2: "P2 средне",
  P3: "P3 низко",
};

const WARNING_LABELS: Record<string, string> = {
  local: "Локальный режим Finance",
  chats_not_configured: "Синхронизация чатов пока не настроена",
  chat_enabled_false: "Чаты выключены в настройках",
  chat_sync_source_not_configured: "Источник чатов WB пока не подключён",
  wb_content_token_not_configured: "Не подключён токен WB Content API",
  automation_forced_off: "Автоматическая публикация принудительно выключена",
  auto_publish_forced_off: "Автопубликация принудительно выключена",
  manual_attention_recommended: "Рекомендуется ручная проверка",
  rating_mode_manual: "Для этого рейтинга выбран ручной режим",
  ai_generation_failed_fallback_used:
    "ИИ не вернул ответ, использован локальный шаблон",
  reputation_publish_disabled: "Публикация ответов выключена",
};

const SOURCE_LABELS: Record<string, string> = {
  account: "Аккаунт",
  reviews: "Отзывы",
  review: "Отзывы",
  questions: "Вопросы",
  question: "Вопросы",
  chats: "Чаты",
  chat: "Чаты",
  reputation: "Репутация",
};

const humanizeSummaryKey = (k: string) =>
  SUMMARY_LABELS[k] ??
  k.replace(/[_-]+/g, " ").replace(/^\w/, (c) => c.toUpperCase());
const humanizeStatus = (s: string) => STATUS_LABELS[s] ?? s;
const humanizeKind = (k: string) => KIND_LABELS[k] ?? k;
const humanizeWarning = (s: string) =>
  WARNING_LABELS[s] ?? s.replace(/[_-]+/g, " ");
const humanizeSource = (s: string) => SOURCE_LABELS[s] ?? s;
const humanizeReplyMode = (s: string) => REPLY_MODE_LABELS[s] ?? s;
const humanizeRuntimeMode = (s: string | null | undefined) =>
  s ? (RUNTIME_MODE_LABELS[s] ?? `Рантайм: ${s}`) : "Рантайм: неизвестно";
const humanizeBucket = (s: string) => BUCKET_LABELS[s] ?? s;
const humanizePlanKey = (s: string) =>
  s
    .replace(/^routing_/, "")
    .replace(/^primary_review_/, "первичный ")
    .replace(/^secondary_review_/, "вторичный ")
    .replace(/_/g, " ");
const humanizeDraftSource = (s: string | null) =>
  s === "ai"
    ? "Черновик ИИ"
    : s === "local_rules"
      ? "Локальный черновик"
      : s === "manual_text"
        ? "Ручной текст"
        : s
          ? s
          : null;
const humanizeSourceType = (s: string | null) =>
  s === "review"
    ? "Отзыв"
    : s === "question"
      ? "Вопрос"
      : s === "chat"
        ? "Чат"
        : s === "reputation"
          ? "Репутация"
          : s;
const isRecord = (value: unknown): value is Record<string, unknown> =>
  value !== null && typeof value === "object" && !Array.isArray(value);
const getString = (value: unknown) =>
  typeof value === "string" ? value : value == null ? null : String(value);
const getRecordValue = (value: unknown, key: string) =>
  isRecord(value) ? value[key] : undefined;
type ReputationSignature = {
  text: string;
  brand: string;
  type: "all" | "review" | "question" | "chat";
  rating: number | null;
  is_active: boolean;
  created_at: string | null;
  sourceIndex: number;
};
type ReputationSignaturePayload = Omit<ReputationSignature, "sourceIndex">;
const SIGNATURE_KINDS: Array<{
  value: ReputationSignature["type"];
  label: string;
}> = [
  { value: "all", label: "Для всех каналов" },
  { value: "review", label: "Только для отзывов" },
  { value: "question", label: "Только для вопросов" },
  { value: "chat", label: "Только для чатов" },
];
const SIGNATURE_SCOPE_LABELS: Record<ReputationSignature["type"], string> = {
  all: "Любой канал",
  review: "Отзывы",
  question: "Вопросы",
  chat: "Чаты",
};
const SIGNATURE_SCOPE_HINTS: Record<ReputationSignature["type"], string> = {
  all: "Подходят для всех обращений",
  review: "Срабатывают только на отзывах",
  question: "Срабатывают только на вопросах",
  chat: "Срабатывают только на чатах",
};
const SIGNATURE_PRIORITY_STEPS = [
  {
    title: "1) Тип обращения",
    value:
      "Сначала выбираем тип обращения: отзыв, вопрос, чат или правило для всех каналов.",
  },
  {
    title: "2) Бренд",
    value:
      "Затем проверяем правило для конкретного бренда товара. Если для него нет правил — берется «все бренды».",
  },
  {
    title: "3) Рейтинг",
    value:
      "Дальше матчится конкретный рейтинг (1–5). Если его нет — применяется правило для всех рейтингов.",
  },
  {
    title: "4) Резервный вариант",
    value: "Если ничего не подошло, добавляется fallback-подпись из поля ниже.",
  },
];

const signatureScopeLabel = (signature: ReputationSignature) =>
  SIGNATURE_SCOPE_LABELS[signature.type];

const signatureBrandLabel = (signature: ReputationSignature) =>
  signature.brand === "all" ? "Все бренды" : signature.brand;

const signatureRatingLabel = (signature: ReputationSignature) =>
  signature.rating == null ? "Все" : `${signature.rating} ★`;

const signatureRulePriority = (signature: ReputationSignature) => {
  let score = 0;
  if (signature.brand !== "all") score += 2;
  if (signature.rating !== null) score += 1;
  return score;
};
type ReputationSettingsSection = "system" | "rules" | "style" | "learning";
type ReputationSettingsNavItem = {
  id: ReputationSettingsSection;
  title: string;
  description: string;
  icon: ElementType;
};
const REPUTATION_SETTINGS_SECTIONS: ReputationSettingsNavItem[] = [
  {
    id: "system",
    title: "Системные ограничения",
    description: "Автоматизация, синхронизация, лимиты",
    icon: ShieldCheck,
  },
  {
    id: "rules",
    title: "Правила обработки",
    description: "Режим ответов и матрица рейтингов",
    icon: ListChecks,
  },
  {
    id: "style",
    title: "Стиль и подписи",
    description:
      "ИИ-черновики, тон и правила подписей по каналу/бренду/рейтингу",
    icon: Palette,
  },
  {
    id: "learning",
    title: "ИИ-обучение",
    description: "Промпты, категории, ручные правила",
    icon: Brain,
  },
];
const normalizeSignatureKind = (
  value: unknown,
): ReputationSignature["type"] => {
  const kind = typeof value === "string" ? value.trim().toLowerCase() : "all";
  return kind === "review" || kind === "question" || kind === "chat"
    ? kind
    : "all";
};
const normalizeSignatureTypeFilter = (
  value: string,
): ReputationSignature["type"] | "all" =>
  value === "all" ||
  value === "review" ||
  value === "question" ||
  value === "chat"
    ? value
    : "all";
const normalizeSignatureFilterRating = (value: string): string =>
  ["all", "none", "5", "4", "3", "2", "1"].includes(value) ? value : "all";
const normalizeSignatureRating = (value: unknown): number | null => {
  if (value == null || value === "" || value === "all") return null;
  const parsed =
    typeof value === "number"
      ? Math.trunc(value)
      : Number(String(value).trim());
  if (!Number.isInteger(parsed) || parsed < 1 || parsed > 5) return null;
  return parsed;
};
const normalizeSignatureBrand = (value: unknown): string => {
  const brand = String(value ?? "").trim();
  return brand || "all";
};
const normalizeSignatureText = (value: unknown): string => {
  const text = String(value ?? "").trim();
  return text.replace(/\s+/g, " ");
};
const normalizeSignatureCreatedAt = (value: unknown): string | null => {
  const raw = getString(value)?.trim();
  return raw ? raw : null;
};
const parseSignatures = (raw: unknown): ReputationSignature[] =>
  Array.isArray(raw)
    ? raw
        .map((item, index): ReputationSignature | null => {
          if (typeof item === "string") {
            const text = normalizeSignatureText(item);
            if (!text) return null;
            return {
              text,
              brand: "all",
              type: "all" as const,
              rating: null,
              is_active: true,
              created_at: null,
              sourceIndex: index,
            };
          }

          if (!isRecord(item)) return null;
          if (item.is_active === false) return null;
          const text = normalizeSignatureText(item.text ?? item.signature);
          if (!text) return null;
          return {
            text,
            brand: normalizeSignatureBrand(item.brand),
            type: normalizeSignatureKind(item.type),
            rating: normalizeSignatureRating(item.rating),
            is_active: true,
            created_at: normalizeSignatureCreatedAt(item.created_at),
            sourceIndex: index,
          };
        })
        .filter((item): item is ReputationSignature => item !== null)
    : [];
const getNumber = (value: unknown) => {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (
    typeof value === "string" &&
    value.trim() &&
    Number.isFinite(Number(value))
  ) {
    return Number(value);
  }
  return null;
};

function compactDate(value: unknown) {
  const raw = getString(value);
  if (!raw) return "";
  const date = new Date(raw);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleDateString("ru-RU", { day: "2-digit", month: "2-digit" });
}

function compactTime(value: unknown) {
  const raw = getString(value);
  if (!raw) return "";
  const date = new Date(raw);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleTimeString("ru-RU", {
    hour: "2-digit",
    minute: "2-digit",
  });
}

function productDetailsOf(item: Record<string, unknown>) {
  const direct = item.product_details;
  if (isRecord(direct)) return direct;
  const data = isRecord(item.data) ? item.data : {};
  const nested = data.product_details ?? data.productDetails;
  return isRecord(nested) ? nested : {};
}

function productTitleOf(item: Record<string, unknown>) {
  const pd = productDetailsOf(item);
  return (
    getString(pd.product_name) ??
    getString(pd.productName) ??
    getString(pd.name) ??
    getString(pd.title) ??
    getString(item.title) ??
    "Товар"
  );
}

function productBrandOf(item: Record<string, unknown>) {
  const pd = productDetailsOf(item);
  return (
    getString(pd.brand_name) ?? getString(pd.brandName) ?? getString(pd.brand)
  );
}

function firstImageUrl(...values: unknown[]) {
  for (const value of values) {
    const raw = getString(value)?.trim();
    if (raw && /^https?:\/\//i.test(raw)) return raw;
  }
  return null;
}

function firstImageFromArray(value: unknown) {
  if (!Array.isArray(value)) return null;
  for (const item of value) {
    if (typeof item === "string") {
      const url = firstImageUrl(item);
      if (url) return url;
    }
    if (isRecord(item)) {
      const url = firstImageUrl(
        item.fullSize,
        item.miniSize,
        item.big,
        item.url,
        item.c516x688,
        item.c246x328,
        item.square,
        item.photo,
        item.src,
      );
      if (url) return url;
    }
  }
  return null;
}

function firstImageFromRecord(value: unknown) {
  if (!isRecord(value)) return null;
  return firstImageUrl(
    value.product_image_url,
    value.productImageUrl,
    value.image_url,
    value.imageUrl,
    value.main_photo_url,
    value.thumbnail_url,
    value.thumbnail,
    value.preview_photo,
    value.previewPhoto,
    value.img,
    value.image,
    value.photo,
  );
}

function proxyWbImageUrl(src: string | null) {
  if (!src) return null;
  return src;
}

function wbBasketHostByVol(vol: number) {
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
  ];
  const basket = ranges.find(([maxVol]) => vol <= maxVol)?.[1] ?? 26;
  return `basket-${String(basket).padStart(2, "0")}.wbbasket.ru`;
}

function productNmIdOf(item: Record<string, unknown>) {
  const pd = productDetailsOf(item);
  return (
    getNumber(item.nm_id) ??
    getNumber(item.nmId) ??
    getNumber(pd.nm_id) ??
    getNumber(pd.nmId)
  );
}

function wildberriesProductImageUrl(nmId: number | null) {
  if (!nmId || nmId <= 0) return null;
  const normalized = Math.trunc(nmId);
  const vol = Math.floor(normalized / 100000);
  const part = Math.floor(normalized / 1000);
  const host = wbBasketHostByVol(vol);
  return `https://${host}/vol${vol}/part${part}/${normalized}/images/c516x688/1.webp`;
}

function productImageOf(item: Record<string, unknown>) {
  const data = isRecord(item.data) ? item.data : {};
  const sourcePayload = isRecord(item.source_payload)
    ? item.source_payload
    : {};
  const pd = productDetailsOf(item);
  const records = [item, data, sourcePayload, pd];

  for (const record of records) {
    const direct = firstImageFromRecord(record);
    if (direct) return proxyWbImageUrl(direct);
    for (const key of [
      "media",
      "photoLinks",
      "photo_links",
      "photos",
      "images",
    ]) {
      const url = firstImageFromArray(record[key]);
      if (url) return proxyWbImageUrl(url);
    }
  }

  return proxyWbImageUrl(wildberriesProductImageUrl(productNmIdOf(item)));
}

function ratingColor(value: number | null) {
  if (value == null) return "text-muted-foreground";
  if (value <= 2) return "text-destructive";
  if (value <= 3) return "text-warning";
  return "text-success";
}

function statusChipMeta(
  status: string,
  draftId: unknown,
  manualAttention: boolean,
) {
  if (manualAttention) {
    return {
      label: "Ручной",
      icon: AlertTriangle,
      className: "border-destructive/15 bg-destructive/10 text-destructive",
    };
  }
  if (status === "answered" || status === "published") {
    return {
      label: "Отвечено",
      icon: CheckCircle2,
      className: "border-success/15 bg-success/10 text-success",
    };
  }
  if (status === "ignored" || status === "rejected") {
    return {
      label: "Пропущен",
      icon: XCircle,
      className: "border-border/60 bg-muted text-muted-foreground",
    };
  }
  if (draftId) {
    return {
      label: "Черновик",
      icon: Sparkles,
      className: "border-primary/15 bg-primary/10 text-primary",
    };
  }
  return {
    label: "Ожидает",
    icon: Clock,
    className: "border-warning/15 bg-warning/10 text-warning",
  };
}

function ReputationProductThumb({
  item,
  alt,
  kind,
  className = "h-10 w-10",
}: {
  item: Record<string, unknown>;
  alt: string;
  kind: string;
  className?: string;
}) {
  const image = productImageOf(item);
  const [failedSrc, setFailedSrc] = useState<string | null>(null);
  const visibleImage = image && failedSrc !== image ? image : null;

  return (
    <div
      className={`${className} shrink-0 overflow-hidden rounded-lg border border-border/40 bg-muted/50`}
    >
      {visibleImage ? (
        <img
          src={visibleImage}
          alt={alt}
          className="h-full w-full object-cover"
          loading="lazy"
          referrerPolicy="no-referrer"
          onError={() => setFailedSrc(visibleImage)}
        />
      ) : (
        <div className="flex h-full w-full items-center justify-center">
          {kind === "chat" ? (
            <MessageSquare className="h-4 w-4 text-muted-foreground/50" />
          ) : kind === "question" ? (
            <Info className="h-4 w-4 text-muted-foreground/50" />
          ) : (
            <ImageIcon className="h-4 w-4 text-muted-foreground/50" />
          )}
        </div>
      )}
    </div>
  );
}

function SummaryGrid({ data }: { data: unknown }) {
  if (!isRecord(data)) return null;
  const entries = Object.entries(data).filter(
    ([k, v]) =>
      typeof v !== "object" &&
      v != null &&
      ![
        "status",
        "enabled",
        "module",
        "account_id",
        "trust_state",
        "warnings",
        "unavailable_sources",
        "data",
        "runtime_mode",
        "dangerous_actions_enabled",
        "publish_enabled",
        "auto_publish_enabled",
        "chat_send_enabled",
      ].includes(k),
  );
  if (entries.length === 0) return null;
  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-sm">
      {entries.map(([k, v]) => (
        <div key={k} className="rounded-md border bg-muted/20 px-3 py-2">
          <div className="text-[10px] uppercase text-muted-foreground tracking-wide">
            {humanizeSummaryKey(k)}
          </div>
          <div className="mt-1 font-semibold tabular-nums">{String(v)}</div>
        </div>
      ))}
    </div>
  );
}

function ModeSegment({
  value,
  disabled,
  onChange,
  compact = false,
  iconOnly = false,
}: {
  value: string;
  disabled?: boolean;
  onChange: (value: string) => void;
  compact?: boolean;
  iconOnly?: boolean;
}) {
  return (
    <div
      className={`grid grid-cols-3 gap-1 rounded-md border bg-muted/20 p-1 ${
        iconOnly ? "min-w-0" : ""
      }`}
    >
      {["manual", "semi", "auto"].map((mode) => {
        const Icon =
          mode === "manual" ? Pencil : mode === "semi" ? Bot : Sparkles;
        return (
          <Button
            key={mode}
            type="button"
            size="sm"
            variant={value === mode ? "default" : "ghost"}
            className={
              iconOnly
                ? "h-7 min-w-0 px-0 text-[0px] sm:text-[0px]"
                : compact
                  ? "h-7 px-2 text-[11px]"
                  : "h-8 px-2 text-xs"
            }
            disabled={disabled}
            title={humanizeReplyMode(mode)}
            aria-label={humanizeReplyMode(mode)}
            onClick={() => onChange(mode)}
          >
            {iconOnly ? (
              <Icon className="h-3.5 w-3.5" />
            ) : (
              humanizeReplyMode(mode)
            )}
          </Button>
        );
      })}
    </div>
  );
}

type InboxFilters = {
  itemType: "all" | "review" | "question" | "chat";
  status: string;
  rating: string;
  sentiment: string;
  priority: string;
  nmId: string;
  dateFrom: string;
  dateTo: string;
};

const DEFAULT_INBOX_FILTERS: InboxFilters = {
  itemType: "all",
  status: "all",
  rating: "all",
  sentiment: "all",
  priority: "all",
  nmId: "",
  dateFrom: "",
  dateTo: "",
};

function reputationItemMatchesNmId(item: any, nmId: string): boolean {
  if (!nmId) return true;
  const nested = [
    item,
    item?.product,
    item?.product_data,
    item?.payload,
    item?.source_payload,
    item?.metadata,
    item?.data,
  ];
  return nested.some((source) => {
    if (!source || typeof source !== "object") return false;
    const values = [
      source.nm_id,
      source.nmId,
      source.nmid,
      source.nm,
      source.product_nm_id,
      source.card_nm_id,
      source.article,
    ];
    if (Array.isArray(source.nm_ids)) values.push(...source.nm_ids);
    return values.some((value) => String(value ?? "").trim() === nmId);
  });
}

const countActiveFilters = (filters: InboxFilters) =>
  [
    filters.itemType !== "all",
    filters.status !== "all",
    filters.rating !== "all",
    filters.sentiment !== "all",
    filters.priority !== "all",
    Boolean(filters.nmId.trim()),
    Boolean(filters.dateFrom),
    Boolean(filters.dateTo),
  ].filter(Boolean).length;

function InboxFiltersPanel({
  filters,
  onChange,
  onReset,
  total,
  loading,
}: {
  filters: InboxFilters;
  onChange: (patch: Partial<InboxFilters>) => void;
  onReset: () => void;
  total: number;
  loading?: boolean;
}) {
  const activeCount = countActiveFilters(filters);
  return (
    <Card className="mb-3 overflow-hidden">
      <CardContent className="p-0">
        <div className="flex items-center justify-between gap-3 border-b bg-muted/20 px-4 py-3 flex-wrap">
          <div className="flex items-center gap-2">
            <Filter className="h-4 w-4 text-muted-foreground" />
            <div>
              <div className="text-sm font-semibold">Фильтры входящих</div>
              <div className="text-xs text-muted-foreground">
                Быстро найдите нужные отзывы по рейтингу, статусу, приоритету и
                артикулу.
              </div>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Badge variant="outline" className="text-[10px]">
              {loading ? "загрузка…" : `${total} записей`}
            </Badge>
            {activeCount > 0 && (
              <Badge variant="secondary" className="text-[10px]">
                {activeCount} фильтр.
              </Badge>
            )}
            <Button
              type="button"
              size="sm"
              variant="ghost"
              className="h-8 text-xs gap-1"
              onClick={onReset}
              disabled={activeCount === 0}
            >
              <RotateCcw className="h-3.5 w-3.5" />
              Сбросить
            </Button>
          </div>
        </div>

        <div className="space-y-3 p-4">
          <div className="grid gap-2 lg:grid-cols-[1.1fr_1fr_1fr_1fr_1fr]">
            <div className="space-y-1">
              <div className="text-[10px] uppercase tracking-wide text-muted-foreground">
                Тип
              </div>
              <div className="grid grid-cols-4 gap-1 rounded-md border bg-muted/20 p-1">
                {(["all", "review", "question", "chat"] as const).map(
                  (kind) => (
                    <Button
                      key={kind}
                      type="button"
                      size="sm"
                      className="h-8 px-2 text-xs"
                      variant={filters.itemType === kind ? "default" : "ghost"}
                      onClick={() => onChange({ itemType: kind })}
                    >
                      {kind === "all" ? "Все" : humanizeKind(kind)}
                    </Button>
                  ),
                )}
              </div>
            </div>

            <div className="space-y-1">
              <div className="text-[10px] uppercase tracking-wide text-muted-foreground">
                Статус
              </div>
              <Select
                value={filters.status}
                onValueChange={(value) => onChange({ status: value })}
              >
                <SelectTrigger className="h-9">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Все статусы</SelectItem>
                  {[
                    "new",
                    "needs_reply",
                    "draft_ready",
                    "in_progress",
                    "answered",
                    "ignored",
                  ].map((value) => (
                    <SelectItem key={value} value={value}>
                      {humanizeStatus(value)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-1">
              <div className="text-[10px] uppercase tracking-wide text-muted-foreground">
                Рейтинг
              </div>
              <Select
                value={filters.rating}
                onValueChange={(value) => onChange({ rating: value })}
              >
                <SelectTrigger className="h-9">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Любой рейтинг</SelectItem>
                  {["1", "2", "3", "4", "5"].map((value) => (
                    <SelectItem key={value} value={value}>
                      {value} зв.
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-1">
              <div className="text-[10px] uppercase tracking-wide text-muted-foreground">
                Настроение
              </div>
              <Select
                value={filters.sentiment}
                onValueChange={(value) => onChange({ sentiment: value })}
              >
                <SelectTrigger className="h-9">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Любое</SelectItem>
                  {Object.entries(SENTIMENT_LABELS).map(([value, label]) => (
                    <SelectItem key={value} value={value}>
                      {label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-1">
              <div className="text-[10px] uppercase tracking-wide text-muted-foreground">
                Приоритет
              </div>
              <Select
                value={filters.priority}
                onValueChange={(value) => onChange({ priority: value })}
              >
                <SelectTrigger className="h-9">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Любой</SelectItem>
                  {Object.entries(PRIORITY_LABELS).map(([value, label]) => (
                    <SelectItem key={value} value={value}>
                      {label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          <div className="grid gap-2 md:grid-cols-3">
            <div className="space-y-1">
              <div className="text-[10px] uppercase tracking-wide text-muted-foreground">
                Артикул
              </div>
              <Input
                value={filters.nmId}
                inputMode="numeric"
                placeholder="nm_id"
                className="h-9"
                onChange={(event) =>
                  onChange({ nmId: event.target.value.replace(/[^\d]/g, "") })
                }
              />
            </div>
            <div className="space-y-1">
              <div className="text-[10px] uppercase tracking-wide text-muted-foreground">
                Дата от
              </div>
              <Input
                type="date"
                value={filters.dateFrom}
                className="h-9"
                onChange={(event) => onChange({ dateFrom: event.target.value })}
              />
            </div>
            <div className="space-y-1">
              <div className="text-[10px] uppercase tracking-wide text-muted-foreground">
                Дата до
              </div>
              <Input
                type="date"
                value={filters.dateTo}
                className="h-9"
                onChange={(event) => onChange({ dateTo: event.target.value })}
              />
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function DisabledCard({
  message,
  sources,
  warnings,
}: {
  message?: string | null;
  sources?: unknown[];
  warnings?: unknown[];
}) {
  return (
    <Card className="border-dashed">
      <CardContent className="p-6 space-y-3">
        <div className="flex items-center gap-2">
          <PowerOff className="h-5 w-5 text-muted-foreground" />
          <div className="text-base font-semibold">
            Репутация пока не подключена
          </div>
        </div>
        <div className="text-sm text-muted-foreground">
          Модуль ответов на отзывы, вопросы и чаты выключен.
        </div>
        <div className="text-sm text-muted-foreground">
          Публикация отключена. Черновики можно будет создавать после
          подключения.
        </div>
        {message && (
          <div className="text-xs text-muted-foreground border-l-2 border-border pl-2">
            {message}
          </div>
        )}
        {Array.isArray(sources) && sources.length > 0 && (
          <div className="text-xs">
            <div className="uppercase tracking-wide text-muted-foreground mb-1">
              Недоступные источники
            </div>
            <ul className="space-y-0.5">
              {sources.map((s, i: number) => (
                <li key={i} className="text-muted-foreground">
                  •{" "}
                  {typeof s === "string"
                    ? humanizeSource(s)
                    : (getString(getRecordValue(s, "label")) ??
                      getString(getRecordValue(s, "name")) ??
                      (getString(getRecordValue(s, "source"))
                        ? humanizeSource(
                            String(getString(getRecordValue(s, "source"))),
                          )
                        : null) ??
                      JSON.stringify(s))}
                  {isRecord(s) && s.reason && (
                    <span className="opacity-70"> — {getString(s.reason)}</span>
                  )}
                </li>
              ))}
            </ul>
          </div>
        )}
        {Array.isArray(warnings) && warnings.length > 0 && (
          <div className="text-xs">
            <div className="uppercase tracking-wide text-muted-foreground mb-1">
              Предупреждения
            </div>
            <ul className="space-y-0.5">
              {warnings.map((w, i: number) => (
                <li key={i} className="text-warning">
                  •{" "}
                  {typeof w === "string"
                    ? humanizeWarning(w)
                    : (getString(getRecordValue(w, "message")) ??
                      JSON.stringify(w))}
                </li>
              ))}
            </ul>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function ReputationStatusHeader({
  status,
  runtimeMode,
  moduleRuntimeMode,
  hasRuntimeSplit,
  dangerousActionsEnabled,
  publishEnabled,
  autoPublishEnabled,
  chatSendEnabled,
}: {
  status?: string | null;
  runtimeMode?: string | null;
  moduleRuntimeMode?: string | null;
  hasRuntimeSplit?: boolean;
  dangerousActionsEnabled?: boolean;
  publishEnabled?: boolean;
  autoPublishEnabled?: boolean;
  chatSendEnabled?: boolean;
}) {
  return (
    <div className="flex flex-wrap items-center gap-1.5 sm:gap-2">
      <Badge
        variant="outline"
        className="text-[10px] border-warning/30 text-warning bg-warning/10"
      >
        Бета — публикация вручную
      </Badge>
      {status && (
        <Badge variant="outline" className="text-[10px]">
          {humanizeStatus(status)}
        </Badge>
      )}
      <Badge variant="outline" className="text-[10px]">
        {humanizeRuntimeMode(runtimeMode)}
      </Badge>
      {hasRuntimeSplit && (
        <Badge variant="secondary" className="text-[10px]">
          Здоровье:{" "}
          {humanizeRuntimeMode(moduleRuntimeMode).replace("Рантайм: ", "")}
        </Badge>
      )}
      <Badge
        variant={dangerousActionsEnabled ? "outline" : "secondary"}
        className="hidden text-[10px] 2xl:inline-flex"
      >
        Опасные действия {dangerousActionsEnabled ? "вкл" : "выкл"}
      </Badge>
      <Badge
        variant={publishEnabled ? "outline" : "secondary"}
        className={
          publishEnabled
            ? "hidden border-success/30 bg-success/10 text-[10px] text-success lg:inline-flex"
            : "hidden text-[10px] lg:inline-flex"
        }
      >
        {publishEnabled
          ? "Публикация в WB: включена"
          : "Публикация в WB: выключена"}
      </Badge>
      <Badge variant="secondary" className="hidden text-[10px] 2xl:inline-flex">
        Автопубликация {autoPublishEnabled ? "включена" : "выключена"}
      </Badge>
      <Badge
        variant={chatSendEnabled ? "outline" : "secondary"}
        className={
          chatSendEnabled
            ? "hidden border-success/30 bg-success/10 text-[10px] text-success 2xl:inline-flex"
            : "hidden text-[10px] 2xl:inline-flex"
        }
      >
        Отправка чата {chatSendEnabled ? "включена" : "только чтение"}
      </Badge>
    </div>
  );
}

function ratingTone(rating: number | null) {
  if (rating == null || !Number.isFinite(rating))
    return "text-muted-foreground";
  if (rating <= 2) return "text-destructive";
  if (rating === 3) return "text-warning";
  return "text-success";
}

function RatingStars({ value }: { value: number | null }) {
  const normalized =
    value != null && Number.isFinite(value)
      ? Math.max(0, Math.min(5, Math.round(value)))
      : 0;
  return (
    <div className="flex items-center gap-px">
      {Array.from({ length: 5 }).map((_, index) => (
        <Star
          key={index}
          className={`h-3.5 w-3.5 ${
            index < normalized ? ratingTone(normalized) : "text-border"
          }`}
        />
      ))}
    </div>
  );
}

function getItemKey(item: Record<string, unknown>, index = 0) {
  return String(item.id ?? item.item_id ?? item.external_id ?? index);
}

function pickLatestDraftCandidate(candidates: Array<Record<string, unknown>>) {
  if (candidates.length === 0) return null;
  if (candidates.length === 1) return candidates[0];

  const toTimestamp = (value: unknown): number | null => {
    if (typeof value === "number" && Number.isFinite(value)) return value;
    if (typeof value === "string") {
      const parsed = Date.parse(value);
      if (Number.isFinite(parsed)) return parsed;
    }
    return null;
  };

  return candidates.sort((a, b) => {
    const aTs = toTimestamp(
      a.updated_at ?? a.updatedAt ?? a.created_at ?? a.createdAt,
    );
    const bTs = toTimestamp(
      b.updated_at ?? b.updatedAt ?? b.created_at ?? b.createdAt,
    );
    if (aTs !== null || bTs !== null) {
      const right = bTs ?? Number.NEGATIVE_INFINITY;
      const left = aTs ?? Number.NEGATIVE_INFINITY;
      if (left !== right) return right - left;
    }

    const aId = Number(a.id);
    const bId = Number(b.id);
    if (Number.isFinite(aId) || Number.isFinite(bId)) {
      const aSafe = Number.isFinite(aId) ? aId : -Infinity;
      const bSafe = Number.isFinite(bId) ? bId : -Infinity;
      if (aSafe !== bSafe) return bSafe - aSafe;
    }
    return 0;
  })[0];
}

function getItemDraft(item: Record<string, unknown>) {
  const primaryDraft = isRecord(item.draft) ? item.draft : null;
  const draft = pickLatestDraftCandidate(
    [primaryDraft].filter(isRecord) as Array<Record<string, unknown>>,
  );
  return {
    raw: draft,
    id: draft && draft.id != null ? draft.id : null,
    status: draft ? (getString(draft.status) ?? null) : null,
    text: draft ? getString(draft.text) : null,
    data: draft && isRecord(draft.data) ? draft.data : {},
  };
}

function getItemClassification(
  item: Record<string, unknown>,
  draftData: Record<string, unknown>,
) {
  const itemData = isRecord(item.data) ? item.data : {};
  const raw = isRecord(item.raw_json) ? item.raw_json : {};
  if (isRecord(draftData.classification)) return draftData.classification;
  if (isRecord(draftData.classification_context))
    return draftData.classification_context;
  if (isRecord(itemData.local_classification))
    return itemData.local_classification;
  if (isRecord(raw.local_classification)) return raw.local_classification;
  if (isRecord(item.classification)) return item.classification;
  return {};
}

function getInstructionPlan(
  item: Record<string, unknown>,
  draftData: Record<string, unknown>,
  classification: Record<string, unknown>,
) {
  const generation = isRecord(draftData.generation) ? draftData.generation : {};
  const trace = getGenerationTrace(draftData);
  const itemData = isRecord(item.data) ? item.data : {};
  const raw = isRecord(item.raw_json) ? item.raw_json : {};
  const candidates = [
    draftData.instruction_plan,
    generation.instruction_plan,
    generation.category_instruction_plan,
    trace.instruction_plan,
    trace.routing_plan,
    classification.instruction_plan,
    itemData.local_instruction_plan,
    raw.local_instruction_plan,
  ];
  for (const candidate of candidates) {
    if (isRecord(candidate)) return candidate;
  }
  return {};
}

function getGenerationTrace(draftData: Record<string, unknown>) {
  const candidates = [
    draftData.generation_trace,
    draftData.trace,
    draftData.debug_trace,
    draftData.generation,
  ];
  for (const candidate of candidates) {
    if (isRecord(candidate)) return candidate;
  }
  return {};
}

function formatDebugValue(value: unknown) {
  if (value == null) return "—";
  if (
    typeof value === "string" ||
    typeof value === "number" ||
    typeof value === "boolean"
  ) {
    return String(value);
  }
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function compactDebugValue(value: unknown) {
  const text = formatDebugValue(value);
  return text.length > 180 ? `${text.slice(0, 180)}…` : text;
}

function ReputationKpiStrip({
  items,
  total,
  loading,
}: {
  items: Record<string, unknown>[];
  total: number;
  loading?: boolean;
}) {
  const waiting = items.filter((item) => {
    const status = getString(item.status) ?? "";
    return !["answered", "ignored", "published"].includes(status);
  }).length;
  const answered = items.filter((item) =>
    ["answered", "published"].includes(getString(item.status) ?? ""),
  ).length;
  const drafts = items.filter((item) => Boolean(getItemDraft(item).id)).length;
  const progress =
    total > 0 ? Math.round((answered / Math.max(total, 1)) * 100) : 0;
  return (
    <div className="flex items-center gap-3 rounded-xl border border-border/40 bg-card px-3.5 py-2 shadow-sm">
      <KpiChip label="Ожидают" value={loading ? "…" : waiting} tone="warning" />
      <Sep />
      <KpiChip label="Отвечено" value={answered} tone="success">
        <div className="h-[3px] w-10 overflow-hidden rounded-full bg-muted">
          <div
            className="h-full rounded-full bg-success"
            style={{ width: `${Math.min(100, Math.max(0, progress))}%` }}
          />
        </div>
      </KpiChip>
      <Sep />
      <KpiChip label="Черновики" value={drafts} />
      <div className="ml-auto flex items-center gap-1.5 text-[10px] text-muted-foreground">
        <BarChart3 className="h-3 w-3 text-success" />
        <span className="hidden sm:inline font-medium">Прогресс</span>
        <span className="font-semibold tabular-nums text-foreground">
          {progress}%
        </span>
      </div>
    </div>
  );
}

function KpiChip({
  label,
  value,
  tone,
  children,
}: {
  label: string;
  value: number | string;
  tone?: "warning" | "success";
  children?: ReactNode;
}) {
  return (
    <div className="flex items-center gap-1.5">
      <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
        {label}
      </span>
      <span
        className={`text-[13px] font-bold tabular-nums leading-none ${
          tone === "warning"
            ? "text-warning"
            : tone === "success"
              ? "text-success"
              : "text-foreground"
        }`}
      >
        {value}
      </span>
      {children}
    </div>
  );
}

function Sep() {
  return <div className="h-3.5 w-px bg-border/40" />;
}

function itemConversationTitle(item: Record<string, unknown>) {
  const kind = getString(item.kind) ?? getString(item.item_type) ?? "review";
  const title = getString(item.title)?.trim();
  const text = getString(item.text)?.trim();
  const productTitle = productTitleOf(item);
  if (kind === "question") return title || text || "Вопрос покупателя";
  if (kind === "chat") return title || text || "Диалог с покупателем";
  return productTitle || title || "Отзыв покупателя";
}

function itemProductSubtitle(item: Record<string, unknown>) {
  const kind = getString(item.kind) ?? getString(item.item_type) ?? "review";
  const brand = productBrandOf(item);
  const productTitle = productTitleOf(item);
  if (kind === "review") return brand || null;
  if (brand && productTitle && productTitle !== brand) {
    return `${brand} · ${productTitle}`;
  }
  return brand || productTitle || null;
}

function MetaCell({ label, value }: { label: string; value: string | null }) {
  return (
    <div className="min-w-0">
      <div className="text-[10px] uppercase tracking-wider text-muted-foreground/60">
        {label}
      </div>
      <div className="mt-0.5 truncate text-xs font-medium text-foreground">
        {value && value.trim() ? value : "—"}
      </div>
    </div>
  );
}

function InsightBox({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  return (
    <div className="rounded-lg border border-border/50 bg-background px-3 py-2">
      <div className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/70">
        {title}
      </div>
      <div className="flex flex-wrap gap-1.5">{children}</div>
    </div>
  );
}

function ReputationQueueItem({
  item,
  index,
  active,
  onSelect,
}: {
  item: Record<string, unknown>;
  index: number;
  active: boolean;
  onSelect: () => void;
}) {
  const draft = getItemDraft(item);
  const draftData = draft.data;
  const generation = isRecord(draftData.generation) ? draftData.generation : {};
  const classification = getItemClassification(item, draftData);
  const kind = getString(item.kind) ?? getString(item.item_type) ?? "review";
  const statusText = getString(item.status) ?? "new";
  const title = itemConversationTitle(item);
  const bodyText = getString(item.text) ?? getString(item.summary) ?? "—";
  const buyerName = getString(item.buyer_name);
  const receivedAt = getString(item.received_at);
  const nmId = getString(item.nm_id);
  const rating = getNumber(item.rating);
  const replyBucket =
    getString(classification.reply_bucket) ?? getString(item.sentiment);
  const replyMode = getString(generation.reply_mode);
  const subtitle = itemProductSubtitle(item);
  const manualAttention =
    Boolean(classification.requires_manual_attention) ||
    Boolean(item.review_requires_manual_attention);
  const statusChip = statusChipMeta(statusText, draft.id, manualAttention);
  const StatusIcon = statusChip.icon;
  const categories = Array.isArray(classification.categories)
    ? classification.categories
    : Array.isArray(item.review_category_matches)
      ? item.review_category_matches
      : [];

  return (
    <button
      type="button"
      onClick={onSelect}
      className={`w-full border-b border-border/30 px-3.5 py-2.5 text-left transition-colors last:border-b-0 hover:bg-secondary/40 ${
        active ? "bg-primary/[0.06]" : "bg-card"
      }`}
    >
      <div className="flex items-center gap-3">
        <ReputationProductThumb item={item} alt={title} kind={kind} />

        <div className="w-9 shrink-0">
          {rating != null && Number.isFinite(rating) ? (
            <div
              className={`flex items-center gap-0.5 text-[12px] font-semibold tabular-nums ${ratingColor(rating)}`}
            >
              <Star className="h-3.5 w-3.5 fill-current" />
              {rating}
            </div>
          ) : (
            <Badge variant="outline" className="h-5 px-1.5 text-[10px]">
              {humanizeKind(kind)}
            </Badge>
          )}
        </div>

        <div className="min-w-0 flex-1">
          <div className="flex min-w-0 items-baseline gap-1.5">
            <span className="min-w-0 flex-1 truncate text-[13px] font-medium leading-tight text-foreground">
              {title || `Запись #${index + 1}`}
            </span>
            {subtitle && (
              <span className="hidden max-w-[42%] truncate text-[11px] text-muted-foreground lg:inline">
                {subtitle}
              </span>
            )}
          </div>
          <div className="mt-0.5 line-clamp-1 text-[12px] leading-snug text-muted-foreground/75">
            {bodyText}
          </div>
          <div className="mt-1 flex flex-wrap items-center gap-1">
            {buyerName && (
              <span className="text-[11px] text-muted-foreground">
                {buyerName}
              </span>
            )}
            {categories.slice(0, 2).map((category, categoryIndex) => {
              const label = isRecord(category)
                ? (getString(category.label) ?? getString(category.code))
                : String(category);
              return (
                <span
                  key={`${label}-${categoryIndex}`}
                  className="rounded bg-muted px-1.5 py-0.5 text-[10px] font-medium leading-none text-muted-foreground"
                >
                  {label}
                </span>
              );
            })}
            {categories.length > 2 && (
              <span className="text-[10px] text-muted-foreground">
                +{categories.length - 2}
              </span>
            )}
            {replyBucket && (
              <span className="rounded bg-primary/10 px-1.5 py-0.5 text-[10px] font-medium leading-none text-primary">
                {humanizeBucket(replyBucket)}
              </span>
            )}
            {replyMode && (
              <span className="rounded bg-muted px-1.5 py-0.5 text-[10px] font-medium leading-none text-muted-foreground">
                {humanizeReplyMode(replyMode)}
              </span>
            )}
            {nmId && (
              <span className="max-w-[132px] truncate rounded bg-muted px-1.5 py-0.5 font-mono text-[10px] font-medium leading-none text-muted-foreground">
                Артикул {nmId}
              </span>
            )}
          </div>
        </div>

        <div className="hidden shrink-0 text-right sm:block">
          <div className="text-[11px] tabular-nums text-muted-foreground">
            {compactDate(receivedAt)}
          </div>
          <div className="text-[10px] tabular-nums text-muted-foreground/60">
            {compactTime(receivedAt)}
          </div>
        </div>

        <div className="shrink-0">
          <span
            className={`inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-[11px] font-medium ${statusChip.className}`}
          >
            <StatusIcon className="h-3 w-3" />
            {statusChip.label}
          </span>
        </div>
      </div>
    </button>
  );
}

function ReputationInboxList({
  items,
  loading,
  activeItemKey,
  onActiveItemChange,
}: {
  items: Record<string, unknown>[];
  loading?: boolean;
  activeItemKey: string | null;
  onActiveItemChange: (key: string) => void;
}) {
  const selectedKey =
    items.find((item, index) => getItemKey(item, index) === activeItemKey) ??
    items[0] ??
    null;
  const selected = selectedKey ? getItemKey(selectedKey) : activeItemKey;
  return (
    <div className="min-h-0 overflow-hidden rounded-lg border border-border/40 bg-card shadow-sm">
      {loading && items.length === 0 ? (
        <div className="space-y-2 p-3">
          <Skeleton className="h-20 w-full" />
          <Skeleton className="h-20 w-full" />
          <Skeleton className="h-20 w-full" />
        </div>
      ) : items.length === 0 ? (
        <div className="flex min-h-[360px] items-center justify-center p-6 text-center text-sm text-muted-foreground">
          Записей нет. Измените фильтры или запустите синхронизацию.
        </div>
      ) : (
        <div className="h-full min-h-0 overflow-y-auto">
          {items.map((item, index) => {
            const key = getItemKey(item, index);
            return (
              <ReputationQueueItem
                key={key}
                item={item}
                index={index}
                active={key === selected}
                onSelect={() => onActiveItemChange(key)}
              />
            );
          })}
        </div>
      )}
    </div>
  );
}

function CategoryPills({
  title,
  value,
  tone = "default",
}: {
  title: string;
  value: unknown;
  tone?: "default" | "muted" | "warning";
}) {
  const values = Array.isArray(value) ? value : value ? [value] : [];
  return (
    <div className="rounded-md border border-border/50 bg-background px-3 py-2">
      <div className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/70">
        {title}
      </div>
      <div className="flex min-h-5 flex-wrap gap-1">
        {values.length ? (
          values.slice(0, 8).map((entry, index) => {
            const label = isRecord(entry)
              ? (getString(entry.label) ??
                getString(entry.code) ??
                getString(entry.role) ??
                compactDebugValue(entry))
              : String(entry);
            return (
              <Badge
                key={`${label}-${index}`}
                variant={tone === "default" ? "outline" : "secondary"}
                className={
                  tone === "warning"
                    ? "border-warning/30 bg-warning/10 text-warning"
                    : "text-[10px]"
                }
              >
                {label}
              </Badge>
            );
          })
        ) : (
          <span className="text-xs text-muted-foreground">—</span>
        )}
      </div>
    </div>
  );
}

function ReputationClassificationPanel({
  item,
  draftData,
}: {
  item: Record<string, unknown>;
  draftData: Record<string, unknown>;
}) {
  const classification = getItemClassification(item, draftData);
  const plan = getInstructionPlan(item, draftData, classification);
  const score =
    getNumber(classification.need_reply_score) ??
    getNumber(item.review_need_reply_score);
  const manualAttention =
    Boolean(classification.requires_manual_attention) ||
    Boolean(item.review_requires_manual_attention);
  const primary = isRecord(classification.primary_category)
    ? classification.primary_category
    : isRecord(plan.primary_review_category)
      ? plan.primary_review_category
      : (classification.primary_category ?? plan.primary_review_category);
  const categories = Array.isArray(classification.categories)
    ? classification.categories
    : Array.isArray(item.review_category_matches)
      ? item.review_category_matches
      : Array.isArray(item.review_categories)
        ? item.review_categories
        : [];
  const secondary =
    plan.secondary_review_categories ??
    classification.secondary_review_categories ??
    [];
  const toneOnly =
    plan.tone_only_review_categories ??
    classification.tone_only_review_categories ??
    [];
  const suppressed =
    plan.suppressed_review_categories ??
    classification.suppressed_review_categories ??
    [];
  const routingScores = isRecord(plan.routing_scores)
    ? plan.routing_scores
    : isRecord(classification.routing_scores)
      ? classification.routing_scores
      : {};

  return (
    <div className="rounded-lg border border-border/50 bg-muted/10 p-3">
      <div className="mb-2 flex items-center justify-between gap-2">
        <div className="flex items-center gap-1.5 text-xs font-semibold">
          <Brain className="h-3.5 w-3.5 text-primary" />
          Классификация и маршрутизация
        </div>
        <div className="flex flex-wrap items-center justify-end gap-1">
          <Badge
            variant={manualAttention ? "secondary" : "outline"}
            className={
              manualAttention
                ? "border-warning/30 bg-warning/10 text-warning"
                : "text-[10px]"
            }
          >
            {manualAttention ? "ручная проверка" : "без ручного блока"}
          </Badge>
          <Badge variant="outline" className="text-[10px]">
            Оценка {score ?? "—"}
          </Badge>
        </div>
      </div>

      <div className="grid gap-2 md:grid-cols-4">
        <MetaCell
          label="Бакет"
          value={humanizeBucket(
            getString(classification.reply_bucket) ??
              getString(item.sentiment) ??
              "neutral",
          )}
        />
        <MetaCell
          label="Сентимент"
          value={
            SENTIMENT_LABELS[
              getString(classification.sentiment) ??
                getString(item.sentiment) ??
                "unknown"
            ] ??
            getString(classification.sentiment) ??
            getString(item.sentiment)
          }
        />
        <MetaCell
          label="Основной бакет"
          value={getString(plan.primary_review_bucket)}
        />
        <MetaCell
          label="Нет основного"
          value={plan.no_clear_primary === true ? "да" : "нет"}
        />
      </div>

      <div className="mt-2 grid gap-2 lg:grid-cols-2">
        <CategoryPills title="Основная категория" value={primary} />
        <CategoryPills title="Все совпадения" value={categories} />
        <CategoryPills title="Вторичные категории" value={secondary} />
        <CategoryPills title="Только тон" value={toneOnly} tone="muted" />
        <CategoryPills title="Подавленные" value={suppressed} tone="warning" />
        <div className="rounded-md border border-border/50 bg-background px-3 py-2">
          <div className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/70">
            Оценки маршрутизации
          </div>
          <div className="max-h-28 space-y-1 overflow-y-auto">
            {Object.keys(routingScores).length ? (
              Object.entries(routingScores).map(([key, value]) => (
                <div
                  key={key}
                  className="flex items-center justify-between gap-3 text-xs"
                >
                  <span className="truncate text-muted-foreground">
                    {humanizePlanKey(key)}
                  </span>
                  <span className="font-mono tabular-nums">
                    {compactDebugValue(value)}
                  </span>
                </div>
              ))
            ) : (
              <span className="text-xs text-muted-foreground">—</span>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function ReputationDraftPanel({
  draft,
  draftData,
  pending,
  forceAi,
  onForceAiChange,
}: {
  draft: ReturnType<typeof getItemDraft>;
  draftData: Record<string, unknown>;
  pending: Record<string, boolean>;
  forceAi: boolean;
  onForceAiChange: (value: boolean) => void;
}) {
  const draftId = draft.id;
  const trace = getGenerationTrace(draftData);
  const source =
    getString(draftData.source) ??
    getString(trace.source) ??
    getString(trace.generation_source);
  const provider = getString(trace.provider) ?? getString(trace.model_provider);
  const model = getString(trace.model) ?? getString(trace.ai_model);
  const latency = getNumber(trace.latency_ms);
  const promptTokens = getNumber(trace.prompt_tokens);
  const completionTokens = getNumber(trace.completion_tokens);

  return (
    <div className="rounded-lg border border-primary/20 bg-primary/5 p-3">
      <div className="mb-2 flex items-center justify-between gap-2">
        <div className="flex items-center gap-1.5 text-xs font-semibold text-primary">
          <Sparkles className="h-3.5 w-3.5" />
          Черновик ответа
        </div>
        <div className="flex flex-wrap justify-end gap-1">
          {draftId && (
            <Badge variant="outline" className="font-mono text-[10px]">
              draft #{String(draftId)}
            </Badge>
          )}
          {source && (
            <Badge variant="secondary" className="text-[10px]">
              {humanizeDraftSource(source)}
            </Badge>
          )}
        </div>
      </div>
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2 rounded-md border border-border/50 bg-background px-3 py-2">
        <div className="space-y-0.5">
          <div className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
            Режим генерации
          </div>
          <div className="text-[11px] text-muted-foreground">
            Выключено — соблюдает ручные ограничения; Вкл — генерирует AI даже
            при ручной проверке.
          </div>
        </div>
        <Switch
          checked={forceAi}
          disabled={pending.draft || pending.regenerate}
          onCheckedChange={onForceAiChange}
        />
      </div>
      <div className="min-h-24 rounded-lg border border-border/40 bg-background/90 p-3 text-[13px] leading-relaxed text-foreground/85">
        {draft.text ?? "Черновик ещё не создан. Нажмите «Генерация»."}
      </div>

      {(Object.keys(trace).length > 0 || provider || model) && (
        <div className="mt-2 rounded-lg border border-border/50 bg-background px-3 py-2">
          <div className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/70">
            Трассировка генерации
          </div>
          <div className="grid gap-2 text-xs sm:grid-cols-2 lg:grid-cols-4">
            <MetaCell label="Провайдер" value={provider} />
            <MetaCell label="Модель" value={model} />
            <MetaCell
              label="Токены"
              value={
                promptTokens != null || completionTokens != null
                  ? `${promptTokens ?? 0}/${completionTokens ?? 0}`
                  : null
              }
            />
            <MetaCell
              label="Задержка"
              value={latency != null ? `${latency} мс` : null}
            />
          </div>
          {trace.instructions && (
            <pre className="mt-2 max-h-28 overflow-auto whitespace-pre-wrap rounded-md bg-muted/40 p-2 text-[11px] text-muted-foreground">
              {formatDebugValue(trace.instructions)}
            </pre>
          )}
        </div>
      )}
    </div>
  );
}

function ReputationDetailActionBar({
  itemId,
  draft,
  canDraft,
  canPublish,
  publishEnabled,
  pending,
  forceAi,
  onCreateDraft,
  onRegenerate,
  onApprove,
  onReject,
  onNoReply,
  onPublish,
}: {
  itemId: string;
  draft: ReturnType<typeof getItemDraft>;
  canDraft: boolean;
  canPublish: boolean;
  publishEnabled: boolean;
  pending: Record<string, boolean>;
  forceAi: boolean;
  onCreateDraft: (itemId: string, forceAi: boolean) => void;
  onRegenerate: (draftId: string, forceAi: boolean) => void;
  onApprove: (draftId: string) => void;
  onReject: (draftId: string) => void;
  onNoReply: (itemId: string) => void;
  onPublish: (draftId: string, text: string | null) => void;
}) {
  const draftId = draft.id ? String(draft.id) : "";
  const draftStatus = draft.status ?? "";
  const publishBlockedTitle = !publishEnabled
    ? "Публикация в WB отключена серверными runtime-настройками"
    : draftId && !["done", "approved"].includes(draftStatus)
      ? "Сначала одобрите черновик перед ручной публикацией в WB"
      : undefined;

  if (!itemId && !draftId) return null;

  return (
    <div className="shrink-0 border-t border-border/50 bg-card/95 px-3 py-2 backdrop-blur supports-[backdrop-filter]:bg-card/85 sm:px-4 xl:pr-36">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        {!draftId && itemId && (
          <>
            {canDraft && (
              <Button
                size="sm"
                className="h-8 gap-1.5 text-[12px] sm:order-2"
                onClick={() => onCreateDraft(itemId, forceAi)}
                disabled={pending.draft}
              >
                <Sparkles className="h-3.5 w-3.5" />
                Создать черновик
              </Button>
            )}
            <Button
              size="sm"
              variant="ghost"
              className="h-8 text-[12px] sm:order-1"
              onClick={() => onNoReply(itemId)}
              disabled={pending.noReply}
            >
              Ответ не нужен
            </Button>
          </>
        )}
        {draftId && (
          <>
            <div className="flex flex-wrap items-center gap-1.5">
              <Button
                size="sm"
                variant="outline"
                className="h-8 gap-1.5 text-[12px]"
                onClick={() => onRegenerate(draftId, forceAi)}
                disabled={pending.regenerate}
              >
                <RefreshCw className="h-3.5 w-3.5" />
                Перегенерировать
              </Button>
              <Button
                size="sm"
                variant="ghost"
                className="h-8 text-[12px] text-destructive hover:text-destructive"
                onClick={() => onReject(draftId)}
                disabled={pending.reject}
              >
                Отклонить
              </Button>
              {itemId && (
                <Button
                  size="sm"
                  variant="ghost"
                  className="h-8 text-[12px]"
                  onClick={() => onNoReply(itemId)}
                  disabled={pending.noReply}
                >
                  Ответ не нужен
                </Button>
              )}
            </div>
            <div className="flex flex-wrap items-center gap-1.5 sm:justify-end">
              <Button
                size="sm"
                variant="outline"
                className="h-8 gap-1.5 text-[12px]"
                onClick={() => onApprove(draftId)}
                disabled={pending.approve}
              >
                <CheckCircle2 className="h-3.5 w-3.5" />
                Одобрить
              </Button>
              <Button
                size="sm"
                className="h-8 gap-1.5 text-[12px]"
                onClick={() => onPublish(draftId, draft.text)}
                disabled={!canPublish || pending.publish}
                title={publishBlockedTitle}
              >
                <Send className="h-3.5 w-3.5" />
                Опубликовать WB
              </Button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function ReputationChatThreadPanel({
  item,
  chatSendEnabled,
}: {
  item: Record<string, unknown>;
  chatSendEnabled: boolean;
}) {
  const eventsValue =
    item.events ??
    (isRecord(item.data) ? item.data.events : undefined) ??
    (isRecord(item.raw_json) ? item.raw_json.events : undefined);
  const events = Array.isArray(eventsValue) ? eventsValue.filter(isRecord) : [];
  return (
    <div className="rounded-lg border border-border/50 bg-muted/10 p-3">
      <div className="mb-2 flex items-center justify-between gap-2">
        <div className="flex items-center gap-1.5 text-xs font-semibold">
          <MessageSquare className="h-3.5 w-3.5 text-primary" />
          Тред чата
        </div>
        <Badge variant={chatSendEnabled ? "outline" : "secondary"}>
          {chatSendEnabled ? "отправка включена" : "только чтение (beta)"}
        </Badge>
      </div>
      <div className="space-y-2">
        {events.length ? (
          events.slice(-6).map((event, index) => {
            const sender =
              getString(event.sender) ??
              getString(event.sender_type) ??
              getString(event.author) ??
              "event";
            return (
              <div
                key={index}
                className="rounded-lg border bg-background px-3 py-2"
              >
                <div className="mb-1 flex items-center justify-between gap-2 text-[10px] uppercase tracking-wide text-muted-foreground">
                  <span>{sender}</span>
                  <span>
                    {compactDate(event.created_at)}{" "}
                    {compactTime(event.created_at)}
                  </span>
                </div>
                <div className="whitespace-pre-wrap text-xs">
                  {getString(event.text) ??
                    getString(event.message) ??
                    getString(event.body) ??
                    compactDebugValue(event)}
                </div>
              </div>
            );
          })
        ) : (
          <div className="rounded-lg border border-dashed bg-background p-3 text-xs text-muted-foreground">
            Синхронизация сообщений чата в Finance пока не полностью
            портирована: при необходимости система показывает тред только в
            режиме чтения.
          </div>
        )}
      </div>
    </div>
  );
}

function ReputationItemDetail({
  item,
  accountId,
  publishEnabled,
  chatSendEnabled = false,
  pending,
  forceAi,
  onForceAiChange,
  onCreateDraft,
  onRegenerate,
  onApprove,
  onReject,
  onNoReply,
  onPublish,
}: {
  item: Record<string, unknown> | null;
  accountId: number | null | undefined;
  publishEnabled: boolean;
  chatSendEnabled?: boolean;
  pending: Record<string, boolean>;
  forceAi: boolean;
  onForceAiChange: (value: boolean) => void;
  onCreateDraft: (itemId: string, forceAi: boolean) => void;
  onRegenerate: (draftId: string, forceAi: boolean) => void;
  onApprove: (draftId: string) => void;
  onReject: (draftId: string) => void;
  onNoReply: (itemId: string) => void;
  onPublish: (draftId: string, text: string | null) => void;
}) {
  const detailNmId = item
    ? Number(getString(item.nm_id) ?? item.nm_id ?? NaN)
    : NaN;
  const productInsightQ = useQuery({
    queryKey: [
      "portal",
      "reputation",
      "product-insights",
      accountId,
      detailNmId,
    ],
    queryFn: () => fetchReputationProductInsights(accountId, detailNmId),
    enabled: Boolean(accountId && Number.isFinite(detailNmId)),
    staleTime: 30_000,
  });

  if (!item) {
    return (
      <div className="flex h-full min-h-[360px] items-center justify-center rounded-xl border border-dashed bg-card p-6 text-center text-sm text-muted-foreground">
        Выберите запись из очереди.
      </div>
    );
  }

  const draft = getItemDraft(item);
  const draftData = draft.data;
  const classification = getItemClassification(item, draftData);
  const itemId = String(item.id ?? item.item_id ?? "");
  const kind = getString(item.kind) ?? getString(item.item_type) ?? "review";
  const title = getString(item.title) ?? "Сообщение покупателя";
  const bodyText = getString(item.text) ?? getString(item.summary) ?? "—";
  const pros = getString(item.pros);
  const cons = getString(item.cons);
  const buyerName = getString(item.buyer_name) ?? "Покупатель";
  const receivedAt = getString(item.received_at);
  const nmId = getString(item.nm_id);
  const rating =
    typeof item.rating === "number"
      ? item.rating
      : typeof item.rating === "string" && item.rating.trim()
        ? Number(item.rating)
        : null;
  const categories = Array.isArray(classification.categories)
    ? classification.categories
    : Array.isArray(item.review_categories)
      ? item.review_categories
      : [];
  const canDraft = item.can_draft !== false && item.supports_reply !== false;
  const draftId = draft.id;
  const draftStatus = draft.status ?? "";
  const canPublish =
    publishEnabled && !!draftId && ["done", "approved"].includes(draftStatus);
  const productTitle = productTitleOf(item);
  const conversationTitle = itemConversationTitle(item);
  const productSubtitle = itemProductSubtitle(item);
  const statusText = getString(item.status) ?? "new";
  const manualAttention =
    Boolean(classification.requires_manual_attention) ||
    Boolean(item.review_requires_manual_attention);
  const statusChip = statusChipMeta(statusText, draftId, manualAttention);
  const StatusIcon = statusChip.icon;
  const productInsight = isRecord(productInsightQ.data)
    ? productInsightQ.data
    : null;
  const topCategories = Array.isArray(productInsight?.top_categories)
    ? productInsight.top_categories
    : [];
  const painPoints = Array.isArray(productInsight?.pain_points)
    ? productInsight.pain_points
    : [];
  const customerWants = Array.isArray(productInsight?.customer_wants)
    ? productInsight.customer_wants
    : [];
  const promptRules = Array.isArray(productInsight?.prompt_rules)
    ? productInsight.prompt_rules
    : [];
  const learningEntries = Array.isArray(productInsight?.learning_entries)
    ? productInsight.learning_entries
    : [];

  return (
    <div className="flex h-[calc(100vh-5rem)] min-h-[560px] flex-col overflow-hidden rounded-lg border border-border/50 bg-card shadow-[0_8px_32px_-18px_hsl(var(--foreground)/0.18)] lg:h-full lg:min-h-0">
      <div className="flex shrink-0 items-center gap-3 border-b border-border/40 bg-muted/20 px-4 py-2.5">
        <ReputationProductThumb
          item={item}
          alt={conversationTitle || productTitle || title}
          kind={kind}
        />
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <div className="truncate text-[13px] font-semibold leading-tight">
              {conversationTitle || productTitle || title}
            </div>
            <span
              className={`inline-flex shrink-0 items-center gap-1 rounded-md border px-2 py-0.5 text-[10px] font-medium ${statusChip.className}`}
            >
              <StatusIcon className="h-3 w-3" />
              {statusChip.label}
            </span>
          </div>
          <div className="mt-1 flex min-w-0 items-center gap-2 text-[11px] text-muted-foreground">
            {productSubtitle && (
              <span className="truncate">{productSubtitle}</span>
            )}
            {nmId && (
              <span className="shrink-0 rounded bg-muted px-1.5 py-0.5 font-mono text-[10px] font-medium leading-none text-muted-foreground">
                Артикул {nmId}
              </span>
            )}
            {receivedAt && (
              <span className="hidden shrink-0 sm:inline">
                {compactDate(receivedAt)} {compactTime(receivedAt)}
              </span>
            )}
          </div>
        </div>
        {rating != null && Number.isFinite(rating) && (
          <div className="shrink-0 text-right">
            <RatingStars value={rating} />
            <div
              className={`mt-0.5 text-[11px] font-semibold ${ratingColor(rating)}`}
            >
              {rating} / 5
            </div>
          </div>
        )}
        {nmId && (
          <a
            href={`https://www.wildberries.ru/catalog/${nmId}/detail.aspx`}
            target="_blank"
            rel="noreferrer"
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-secondary/60 hover:text-foreground"
          >
            <ExternalLink className="h-3.5 w-3.5" />
          </a>
        )}
      </div>

      <div className="min-h-0 flex-1 space-y-3 overflow-y-auto px-4 py-3">
        <div className="grid grid-cols-2 gap-2 rounded-lg bg-muted/20 px-3 py-2 sm:grid-cols-4">
          <MetaCell label="Покупатель" value={buyerName} />
          <MetaCell label="Тип" value={humanizeKind(kind)} />
          <MetaCell
            label="Дата"
            value={
              receivedAt
                ? `${compactDate(receivedAt)} ${compactTime(receivedAt)}`
                : "—"
            }
          />
          <MetaCell
            label="Режим"
            value={humanizeBucket(
              getString(classification.reply_bucket) ??
                getString(item.sentiment) ??
                "neutral",
            )}
          />
        </div>

        {categories.length > 0 && (
          <div className="flex flex-wrap gap-1">
            {categories.slice(0, 8).map((category, index) => {
              const label = isRecord(category)
                ? (getString(category.label) ?? getString(category.code))
                : String(category);
              return (
                <span
                  key={`${label}-${index}`}
                  className="inline-flex max-w-[11rem] items-center rounded-md bg-muted px-2 py-0.5 text-[10px] font-medium leading-tight text-muted-foreground"
                >
                  <span className="line-clamp-1">{label}</span>
                </span>
              );
            })}
          </div>
        )}

        <div className="rounded-lg border border-border/50 bg-background px-3 py-2.5">
          <div className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/70">
            Текст покупателя
          </div>
          <div className="whitespace-pre-wrap text-[13px] leading-relaxed text-foreground">
            {bodyText}
          </div>
        </div>

        {(pros || cons) && (
          <div className="grid gap-2 sm:grid-cols-2">
            {pros && (
              <div className="rounded-lg border border-success/10 bg-success/5 px-3 py-2.5">
                <div className="mb-0.5 flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wider text-success">
                  <ThumbsUp className="h-3 w-3" />
                  Плюсы
                </div>
                <div className="text-xs leading-snug text-foreground/80">
                  {pros}
                </div>
              </div>
            )}
            {cons && (
              <div className="rounded-lg border border-destructive/10 bg-destructive/5 px-3 py-2.5">
                <div className="mb-0.5 flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wider text-destructive">
                  <ThumbsDown className="h-3 w-3" />
                  Минусы
                </div>
                <div className="text-xs leading-snug text-foreground/80">
                  {cons}
                </div>
              </div>
            )}
          </div>
        )}

        <ReputationClassificationPanel item={item} draftData={draftData} />

        {kind === "chat" && (
          <ReputationChatThreadPanel
            item={item}
            chatSendEnabled={chatSendEnabled}
          />
        )}

        {nmId && (
          <div className="rounded-lg border border-border/50 bg-muted/10 p-3">
            <div className="mb-2 flex items-center justify-between gap-2">
              <div className="flex items-center gap-1.5 text-xs font-semibold">
                <Brain className="h-3.5 w-3.5 text-primary" />
                Анализ артикула
              </div>
              <Badge variant="outline" className="font-mono text-[10px]">
                {productInsightQ.isFetching
                  ? "загрузка"
                  : `${Number(productInsight?.total ?? 0)} записей`}
              </Badge>
            </div>
            <div className="grid gap-2 sm:grid-cols-2">
              <InsightBox title="Частые категории">
                {topCategories.slice(0, 5).map((category, index) => (
                  <Badge
                    key={`cat-${index}`}
                    variant="outline"
                    className="h-5 text-[10px]"
                  >
                    {getString(category.label) ?? getString(category.code)}
                    {category.count != null
                      ? ` · ${String(category.count)}`
                      : ""}
                  </Badge>
                ))}
                {!topCategories.length && (
                  <span className="text-xs text-muted-foreground">
                    Нет данных
                  </span>
                )}
              </InsightBox>
              <InsightBox title="Чего хотят покупатели">
                {customerWants.slice(0, 5).map((want, index) => (
                  <Badge
                    key={`want-${index}`}
                    variant="secondary"
                    className="h-5 text-[10px]"
                  >
                    {getString(want.keyword)}
                    {want.count != null ? ` · ${String(want.count)}` : ""}
                  </Badge>
                ))}
                {!customerWants.length && (
                  <span className="text-xs text-muted-foreground">
                    Нет явных пожеланий
                  </span>
                )}
              </InsightBox>
            </div>
            {painPoints.length > 0 && (
              <div className="mt-2 rounded-lg border border-destructive/15 bg-destructive/5 px-3 py-2">
                <div className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-destructive">
                  Недостатки и боли
                </div>
                <div className="space-y-1">
                  {painPoints.slice(0, 3).map((pain, index) => (
                    <div key={`pain-${index}`} className="text-xs">
                      <span className="font-medium">
                        {getString(pain.label) ?? getString(pain.code)}
                      </span>
                      <span className="text-muted-foreground">
                        {" "}
                        · {String(pain.count ?? 0)}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}
            {(promptRules.length > 0 || learningEntries.length > 0) && (
              <div className="mt-2 grid gap-2 sm:grid-cols-2">
                <InsightBox title="Промпты категорий">
                  {promptRules.slice(0, 3).map((rule, index) => (
                    <div key={`rule-${index}`} className="text-xs">
                      <div className="font-medium">
                        {getString(rule.label) ?? getString(rule.code)}
                      </div>
                      <div className="line-clamp-2 text-muted-foreground">
                        {getString(rule.negative_prompt) ??
                          getString(rule.positive_prompt) ??
                          "—"}
                      </div>
                    </div>
                  ))}
                </InsightBox>
                <InsightBox title="Ручное обучение">
                  {learningEntries.slice(0, 3).map((entry, index) => (
                    <div
                      key={`learn-${index}`}
                      className="line-clamp-2 text-xs"
                    >
                      {getString(entry.applied_text) ??
                        getString(entry.user_instruction)}
                    </div>
                  ))}
                  {!learningEntries.length && (
                    <span className="text-xs text-muted-foreground">
                      Нет отдельных правил
                    </span>
                  )}
                </InsightBox>
              </div>
            )}
          </div>
        )}

        <ReputationDraftPanel
          draft={draft}
          draftData={draftData}
          pending={pending}
          forceAi={forceAi}
          onForceAiChange={onForceAiChange}
        />
      </div>
      <ReputationDetailActionBar
        itemId={itemId}
        draft={draft}
        canDraft={canDraft}
        canPublish={canPublish}
        publishEnabled={publishEnabled}
        pending={pending}
        forceAi={forceAi}
        onCreateDraft={onCreateDraft}
        onRegenerate={onRegenerate}
        onApprove={onApprove}
        onReject={onReject}
        onNoReply={onNoReply}
        onPublish={onPublish}
      />
    </div>
  );
}

function ReputationWorkspace({
  activeTab,
  accountId,
  items,
  total,
  loading,
  fetching,
  error,
  filters,
  onFiltersChange,
  onResetFilters,
  onSync,
  syncing,
  activeItemKey,
  onActiveItemChange,
  publishEnabled,
  chatSendEnabled,
  pending,
  forceAiForDraft,
  onForceAiChange,
  onCreateDraft,
  onRegenerate,
  onApprove,
  onReject,
  onNoReply,
  onPublish,
}: {
  activeTab: string;
  accountId: number | null | undefined;
  items: Record<string, unknown>[];
  total: number;
  loading?: boolean;
  fetching?: boolean;
  error?: unknown;
  filters: InboxFilters;
  onFiltersChange: (patch: Partial<InboxFilters>) => void;
  onResetFilters: () => void;
  onSync: () => void;
  syncing?: boolean;
  activeItemKey: string | null;
  onActiveItemChange: (key: string) => void;
  publishEnabled: boolean;
  chatSendEnabled: boolean;
  pending: Record<string, boolean>;
  forceAiForDraft: boolean;
  onForceAiChange: (value: boolean) => void;
  onCreateDraft: (itemId: string, forceAi: boolean) => void;
  onRegenerate: (draftId: string, forceAi: boolean) => void;
  onApprove: (draftId: string) => void;
  onReject: (draftId: string) => void;
  onNoReply: (itemId: string) => void;
  onPublish: (draftId: string, text: string | null) => void;
}) {
  const title =
    activeTab === "reviews"
      ? "Отзывы"
      : activeTab === "questions"
        ? "Вопросы"
        : "Чаты";
  const subtitle =
    activeTab === "reviews"
      ? "Очередь · Черновики AI · Публикация"
      : activeTab === "questions"
        ? "Вопросы покупателей · Черновики · Контроль"
        : "Диалоги · Контекст · Черновики ответа";
  const selected =
    items.find((item, index) => getItemKey(item, index) === activeItemKey) ??
    items[0] ??
    null;
  const selectedKey = selected ? getItemKey(selected) : null;
  const activeCount = countActiveFilters(filters);
  const selectedDraft = selected ? getItemDraft(selected) : null;
  const selectedItemId = selected
    ? String(selected.id ?? selected.item_id ?? "")
    : "";
  const canGenerateSelected =
    Boolean(selected && selectedItemId && !selectedDraft?.id) &&
    selected?.can_draft !== false &&
    selected?.supports_reply !== false;

  return (
    <div className="flex min-h-0 flex-col gap-2 overflow-visible lg:h-[calc(100vh-214px)] lg:overflow-hidden">
      <div className="shrink-0 space-y-2">
        <div className="flex items-start justify-between gap-3">
          <div className="flex min-w-0 items-center gap-2.5">
            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary/10">
              {activeTab === "chats" ? (
                <MessageSquare className="h-4 w-4 text-primary" />
              ) : activeTab === "questions" ? (
                <Info className="h-4 w-4 text-primary" />
              ) : (
                <Star className="h-4 w-4 text-primary" />
              )}
            </div>
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <h2 className="text-lg font-bold leading-tight">{title}</h2>
                <Badge variant="outline" className="h-5 text-[10px]">
                  {fetching ? "Обновление" : `${total} зап.`}
                </Badge>
              </div>
              <p className="text-[11px] leading-tight text-muted-foreground">
                {subtitle}
              </p>
            </div>
          </div>
          <div className="flex shrink-0 flex-wrap items-center justify-end gap-1.5">
            <div className="hidden items-center gap-2 rounded-lg border border-border/50 bg-background px-2 py-1.5 text-xs sm:flex">
              <span className="text-muted-foreground">Режим генерации</span>
              <Switch
                checked={forceAiForDraft}
                disabled={pending.draft || pending.regenerate}
                onCheckedChange={onForceAiChange}
              />
            </div>
            {canGenerateSelected && (
              <Button
                size="sm"
                className="h-8 gap-1.5 text-[12px]"
                onClick={() => onCreateDraft(selectedItemId, forceAiForDraft)}
                disabled={pending.draft}
              >
                <Sparkles className="h-3 w-3" />
                Генерация
              </Button>
            )}
            <Button
              size="sm"
              variant="outline"
              className="h-8 gap-1 text-[12px]"
              onClick={onSync}
              disabled={syncing}
            >
              <RefreshCw
                className={`h-3 w-3 ${syncing ? "animate-spin" : ""}`}
              />
              {syncing ? "…" : "Обновить"}
            </Button>
          </div>
        </div>

        <div className="space-y-2">
          <div className="flex flex-wrap items-center gap-2 rounded-lg border border-border/40 bg-card px-2.5 py-2 shadow-sm">
            <Badge variant="secondary" className="h-7 shrink-0 gap-1.5 px-2">
              {activeTab === "reviews" ? (
                <Star className="h-3 w-3" />
              ) : activeTab === "questions" ? (
                <Info className="h-3 w-3" />
              ) : (
                <MessageSquare className="h-3 w-3" />
              )}
              Канал: {title}
            </Badge>
            <div className="relative min-w-[220px] flex-1">
              <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
              <Input
                value={filters.nmId}
                inputMode="numeric"
                placeholder="Артикул / nm_id"
                className="h-8 pl-8 text-xs"
                onChange={(event) =>
                  onFiltersChange({
                    nmId: event.target.value.replace(/[^\d]/g, ""),
                  })
                }
              />
            </div>
            <span className="ml-auto hidden text-xs tabular-nums text-muted-foreground sm:inline">
              {items.length} зап.
            </span>
          </div>

          <div className="flex flex-wrap items-center gap-2 rounded-lg border border-border/40 bg-card px-2.5 py-2 shadow-sm">
            <Select
              value={filters.status}
              onValueChange={(value) => onFiltersChange({ status: value })}
            >
              <SelectTrigger className="h-8 min-w-[138px] flex-1 text-xs sm:w-[150px] sm:flex-none">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Все статусы</SelectItem>
                {[
                  "new",
                  "needs_reply",
                  "draft_ready",
                  "in_progress",
                  "answered",
                  "ignored",
                ].map((value) => (
                  <SelectItem key={value} value={value}>
                    {humanizeStatus(value)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select
              value={filters.rating}
              onValueChange={(value) => onFiltersChange({ rating: value })}
            >
              <SelectTrigger className="h-8 min-w-[132px] flex-1 text-xs sm:w-[140px] sm:flex-none">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Все рейтинги</SelectItem>
                {["1", "2", "3", "4", "5"].map((value) => (
                  <SelectItem key={value} value={value}>
                    {value} зв.
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select
              value={filters.sentiment}
              onValueChange={(value) => onFiltersChange({ sentiment: value })}
            >
              <SelectTrigger className="h-8 min-w-[132px] flex-1 text-xs sm:w-[140px] sm:flex-none">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Настроение</SelectItem>
                {Object.entries(SENTIMENT_LABELS).map(([value, label]) => (
                  <SelectItem key={value} value={value}>
                    {label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select
              value={filters.priority}
              onValueChange={(value) => onFiltersChange({ priority: value })}
            >
              <SelectTrigger className="h-8 min-w-[132px] flex-1 text-xs sm:w-[130px] sm:flex-none">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Приоритет</SelectItem>
                {Object.entries(PRIORITY_LABELS).map(([value, label]) => (
                  <SelectItem key={value} value={value}>
                    {label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Button
              type="button"
              size="sm"
              variant="ghost"
              className="h-8 gap-1 text-[12px]"
              onClick={onResetFilters}
              disabled={activeCount === 0}
            >
              <RotateCcw className="h-3.5 w-3.5" />
              Сбросить
            </Button>
            {activeCount > 0 && (
              <Badge variant="secondary" className="text-[10px]">
                {activeCount} фильтр.
              </Badge>
            )}
          </div>
        </div>

        <ReputationKpiStrip items={items} total={total} loading={loading} />
      </div>

      {error && (
        <Alert variant="destructive">
          <AlertTriangle className="h-4 w-4" />
          <AlertDescription>{(error as Error).message}</AlertDescription>
        </Alert>
      )}

      <div className="grid min-h-0 flex-1 gap-2 xl:grid-cols-[minmax(380px,0.58fr)_minmax(440px,0.42fr)]">
        <ReputationInboxList
          items={items}
          loading={loading}
          activeItemKey={selectedKey ?? activeItemKey}
          onActiveItemChange={onActiveItemChange}
        />

        <ReputationItemDetail
          item={selected}
          accountId={accountId}
          publishEnabled={publishEnabled}
          chatSendEnabled={chatSendEnabled}
          pending={pending}
          forceAi={forceAiForDraft}
          onForceAiChange={onForceAiChange}
          onCreateDraft={onCreateDraft}
          onRegenerate={onRegenerate}
          onApprove={onApprove}
          onReject={onReject}
          onNoReply={onNoReply}
          onPublish={onPublish}
        />
      </div>
    </div>
  );
}

function getDraftKey(draft: Record<string, unknown>, index = 0) {
  return String(draft.id ?? draft.source_id ?? draft.case_id ?? index);
}

function getDraftData(draft: Record<string, unknown>) {
  return isRecord(draft.data)
    ? draft.data
    : isRecord(draft.payload)
      ? draft.payload
      : {};
}

function getDraftClassification(draft: Record<string, unknown>) {
  const data = getDraftData(draft);
  const candidates = [
    data.classification,
    data.classification_context,
    data.local_classification,
    draft.classification,
  ];
  for (const candidate of candidates) {
    if (isRecord(candidate)) return candidate;
  }
  return {};
}

function getDraftTitle(draft: Record<string, unknown>) {
  const data = getDraftData(draft);
  return (
    getString(draft.title) ??
    getString(data.title) ??
    getString(data.product_name) ??
    getString(data.subject_name) ??
    "Черновик ответа"
  );
}

function getDraftText(draft: Record<string, unknown>) {
  const data = getDraftData(draft);
  return (
    getString(draft.text) ??
    getString(data.text) ??
    getString(data.answer_text) ??
    getString(data.draft_text) ??
    ""
  );
}

function getDraftSourceType(draft: Record<string, unknown>) {
  const data = getDraftData(draft);
  return (
    getString(draft.source_type) ??
    getString(data.source_type) ??
    getString(data.item_type) ??
    getString(data.kind)
  );
}

function getDraftNmId(draft: Record<string, unknown>) {
  const data = getDraftData(draft);
  return getNumber(
    draft.nm_id ??
      data.nm_id ??
      data.nmId ??
      data.nmid ??
      data.product_nm_id ??
      data.article,
  );
}

function getDraftRating(draft: Record<string, unknown>) {
  const data = getDraftData(draft);
  const classification = getDraftClassification(draft);
  return getNumber(draft.rating ?? data.rating ?? classification.rating);
}

function getDraftDate(draft: Record<string, unknown>) {
  return (
    getString(draft.updated_at) ??
    getString(draft.created_at) ??
    getString(getDraftData(draft).updated_at) ??
    getString(getDraftData(draft).created_at)
  );
}

function getDraftStatusMeta(status: string) {
  if (["rejected", "failed", "error"].includes(status)) {
    return {
      variant: "destructive",
      icon: XCircle,
      className: "text-destructive",
    };
  }
  if (["done", "approved", "published"].includes(status)) {
    return {
      variant: "outline",
      icon: CheckCircle2,
      className: "text-success",
    };
  }
  if (["pending", "in_progress"].includes(status)) {
    return {
      variant: "secondary",
      icon: Clock,
      className: "text-warning",
    };
  }
  return {
    variant: "default",
    icon: FileText,
    className: "text-primary",
  };
}

function ReputationDraftsWorkspace({
  drafts,
  total,
  loading,
  error,
  approveAllPending,
  pending,
  forceAiForDraft,
  publishEnabled,
  onApproveAll,
  onApprove,
  onRegenerate,
  onReject,
}: {
  drafts: Record<string, unknown>[];
  total: number;
  loading?: boolean;
  error?: unknown;
  approveAllPending?: boolean;
  pending: Record<string, boolean>;
  forceAiForDraft: boolean;
  publishEnabled: boolean;
  onApproveAll: () => void;
  onApprove: (draftId: string) => void;
  onRegenerate: (draftId: string, forceAi: boolean) => void;
  onReject: (draftId: string) => void;
}) {
  const [selectedDraftId, setSelectedDraftId] = useState<string | null>(null);
  const firstDraftId = drafts[0] ? getDraftKey(drafts[0], 0) : null;
  const selectedExists = selectedDraftId
    ? drafts.some(
        (draft, index) => getDraftKey(draft, index) === selectedDraftId,
      )
    : false;

  useEffect(() => {
    if (!drafts.length) {
      if (selectedDraftId) setSelectedDraftId(null);
      return;
    }
    if (!selectedDraftId || !selectedExists) {
      setSelectedDraftId(firstDraftId);
    }
  }, [drafts.length, firstDraftId, selectedDraftId, selectedExists]);

  const selectedDraft =
    drafts.find(
      (draft, index) => getDraftKey(draft, index) === selectedDraftId,
    ) ??
    drafts[0] ??
    null;
  const newCount = drafts.filter(
    (draft) => (getString(draft.status) ?? "new") === "new",
  ).length;
  const readyCount = drafts.filter((draft) =>
    ["new", "draft", "draft_ready", "pending", "in_progress"].includes(
      getString(draft.status) ?? "new",
    ),
  ).length;
  const approvedCount = drafts.filter((draft) =>
    ["done", "approved", "published"].includes(
      getString(draft.status) ?? "new",
    ),
  ).length;
  const rejectedCount = drafts.filter(
    (draft) => (getString(draft.status) ?? "new") === "rejected",
  ).length;

  if (loading) {
    return (
      <div className="space-y-2">
        <Skeleton className="h-20 w-full" />
        <div className="grid gap-2 xl:grid-cols-[minmax(360px,0.52fr)_minmax(460px,0.48fr)]">
          <Skeleton className="h-[520px] w-full" />
          <Skeleton className="h-[520px] w-full" />
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <Alert variant="destructive">
        <AlertTriangle className="h-4 w-4" />
        <AlertDescription>{(error as Error).message}</AlertDescription>
      </Alert>
    );
  }

  if (!drafts.length) {
    return (
      <div className="rounded-lg border border-dashed bg-card px-6 py-12 text-center">
        <div className="mx-auto flex h-10 w-10 items-center justify-center rounded-lg bg-muted">
          <FileText className="h-5 w-5 text-muted-foreground" />
        </div>
        <div className="mt-3 text-sm font-semibold">Черновиков пока нет</div>
        <div className="mx-auto mt-1 max-w-md text-xs text-muted-foreground">
          Когда отзывы, вопросы или чаты получат AI-ответ, они появятся здесь
          как очередь проверки.
        </div>
      </div>
    );
  }

  const selectedDraftKey = selectedDraft ? getDraftKey(selectedDraft) : "";
  const selectedStatus = getString(selectedDraft?.status) ?? "new";
  const selectedStatusMeta = getDraftStatusMeta(selectedStatus);
  const SelectedStatusIcon = selectedStatusMeta.icon;
  const selectedData = selectedDraft ? getDraftData(selectedDraft) : {};
  const selectedText = selectedDraft ? getDraftText(selectedDraft) : "";
  const selectedTitle = selectedDraft ? getDraftTitle(selectedDraft) : "";
  const selectedSourceType = selectedDraft
    ? getDraftSourceType(selectedDraft)
    : null;
  const selectedNmId = selectedDraft ? getDraftNmId(selectedDraft) : null;
  const selectedRating = selectedDraft ? getDraftRating(selectedDraft) : null;
  const selectedDate = selectedDraft ? getDraftDate(selectedDraft) : null;
  const classification = selectedDraft
    ? getDraftClassification(selectedDraft)
    : {};
  const trace = selectedDraft ? getGenerationTrace(selectedData) : {};
  const categories = Array.isArray(classification.categories)
    ? classification.categories
    : [];
  const needReplyScore = getNumber(classification.need_reply_score);
  const source =
    getString(selectedData.source) ??
    getString(trace.source) ??
    getString(trace.generation_source);
  const provider = getString(trace.provider) ?? getString(trace.model_provider);
  const model = getString(trace.model) ?? getString(trace.ai_model);
  const warnings = Array.isArray(selectedDraft?.warnings)
    ? selectedDraft.warnings
    : Array.isArray(selectedData.warnings)
      ? selectedData.warnings
      : [];

  return (
    <div className="flex min-h-0 flex-col gap-2 overflow-visible lg:h-[calc(100vh-214px)] lg:overflow-hidden">
      <div className="shrink-0 space-y-2">
        <div className="flex flex-col gap-3 rounded-lg border border-border/50 bg-card px-3.5 py-3 shadow-sm sm:flex-row sm:items-start sm:justify-between">
          <div className="flex min-w-0 items-center gap-2.5">
            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary/10">
              <FileText className="h-4 w-4 text-primary" />
            </div>
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <h2 className="text-lg font-bold leading-tight">Черновики</h2>
                <Badge variant="outline" className="h-5 text-[10px]">
                  {total || drafts.length} зап.
                </Badge>
                <Badge
                  variant={publishEnabled ? "outline" : "secondary"}
                  className="h-5 text-[10px]"
                >
                  Публикация {publishEnabled ? "готова" : "выкл"}
                </Badge>
              </div>
              <p className="text-[11px] leading-tight text-muted-foreground">
                Очередь проверки: AI-текст, классификация, источник и действие
                оператора в одном рабочем экране.
              </p>
            </div>
          </div>
          <Button
            size="sm"
            variant="outline"
            className="h-8 gap-1.5 text-[12px]"
            onClick={onApproveAll}
            disabled={approveAllPending || newCount === 0}
          >
            <CheckCircle2 className="h-3.5 w-3.5" />
            Одобрить новые
          </Button>
        </div>

        <div className="grid gap-2 sm:grid-cols-4">
          <div className="rounded-lg border border-border/50 bg-card px-3 py-2 shadow-sm">
            <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
              Новые
            </div>
            <div className="mt-1 text-lg font-bold tabular-nums text-primary">
              {newCount}
            </div>
          </div>
          <div className="rounded-lg border border-border/50 bg-card px-3 py-2 shadow-sm">
            <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
              В очереди
            </div>
            <div className="mt-1 text-lg font-bold tabular-nums text-warning">
              {readyCount}
            </div>
          </div>
          <div className="rounded-lg border border-border/50 bg-card px-3 py-2 shadow-sm">
            <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
              Одобрено
            </div>
            <div className="mt-1 text-lg font-bold tabular-nums text-success">
              {approvedCount}
            </div>
          </div>
          <div className="rounded-lg border border-border/50 bg-card px-3 py-2 shadow-sm">
            <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
              Отклонено
            </div>
            <div className="mt-1 text-lg font-bold tabular-nums text-destructive">
              {rejectedCount}
            </div>
          </div>
        </div>
      </div>

      <div className="grid min-h-0 flex-1 gap-2 xl:grid-cols-[minmax(360px,0.52fr)_minmax(460px,0.48fr)]">
        <div className="flex min-h-[360px] flex-col overflow-hidden rounded-lg border border-border/50 bg-card shadow-sm">
          <div className="flex shrink-0 items-center justify-between gap-2 border-b border-border/50 px-3 py-2">
            <div>
              <div className="text-xs font-semibold">Очередь черновиков</div>
              <div className="text-[11px] text-muted-foreground">
                Сначала новые, затем уже обработанные.
              </div>
            </div>
            <Badge variant="outline" className="text-[10px]">
              {drafts.length}
            </Badge>
          </div>
          <div className="min-h-0 flex-1 space-y-1.5 overflow-y-auto p-2">
            {drafts.map((draft, index) => {
              const draftId = getDraftKey(draft, index);
              const status = getString(draft.status) ?? "new";
              const statusMeta = getDraftStatusMeta(status);
              const StatusIcon = statusMeta.icon;
              const sourceType = getDraftSourceType(draft);
              const nmId = getDraftNmId(draft);
              const rating = getDraftRating(draft);
              const date = getDraftDate(draft);
              const isActive = draftId === selectedDraftKey;
              return (
                <button
                  key={draftId}
                  type="button"
                  className={
                    "w-full rounded-lg border px-3 py-2.5 text-left transition-colors " +
                    (isActive
                      ? "border-primary/40 bg-primary/5 shadow-sm ring-1 ring-primary/15"
                      : "border-transparent hover:bg-muted/40")
                  }
                  onClick={() => setSelectedDraftId(draftId)}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="line-clamp-1 text-sm font-semibold">
                        {getDraftTitle(draft)}
                      </div>
                      <div className="mt-0.5 flex flex-wrap items-center gap-1.5 text-[11px] text-muted-foreground">
                        {sourceType && (
                          <span>{humanizeSourceType(sourceType)}</span>
                        )}
                        {nmId != null && (
                          <span className="rounded bg-muted px-1.5 py-0.5 font-mono text-[10px]">
                            {nmId}
                          </span>
                        )}
                        {date && (
                          <span>
                            {compactDate(date)} {compactTime(date)}
                          </span>
                        )}
                      </div>
                    </div>
                    <Badge
                      variant={statusMeta.variant}
                      className="shrink-0 gap-1 text-[10px]"
                    >
                      <StatusIcon className="h-3 w-3" />
                      {humanizeStatus(status)}
                    </Badge>
                  </div>
                  <div className="mt-2 line-clamp-2 text-xs leading-relaxed text-muted-foreground">
                    {getDraftText(draft) || "Текст черновика пустой"}
                  </div>
                  <div className="mt-2 flex items-center justify-between gap-2">
                    {rating != null ? (
                      <div className="flex items-center gap-1.5">
                        <RatingStars value={rating} />
                        <span
                          className={`text-[11px] font-semibold ${ratingTone(rating)}`}
                        >
                          {rating}/5
                        </span>
                      </div>
                    ) : (
                      <span className="text-[11px] text-muted-foreground">
                        без рейтинга
                      </span>
                    )}
                    <span className="font-mono text-[10px] text-muted-foreground">
                      #{draftId}
                    </span>
                  </div>
                </button>
              );
            })}
          </div>
        </div>

        <div className="flex min-h-[420px] flex-col overflow-hidden rounded-lg border border-border/50 bg-card shadow-sm">
          <div className="shrink-0 border-b border-border/50 px-3.5 py-3">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="line-clamp-1 text-sm font-semibold">
                  {selectedTitle}
                </div>
                <div className="mt-1 flex flex-wrap items-center gap-1.5 text-[11px] text-muted-foreground">
                  {selectedSourceType && (
                    <Badge variant="secondary" className="h-5 text-[10px]">
                      {humanizeSourceType(selectedSourceType)}
                    </Badge>
                  )}
                  {selectedNmId != null && (
                    <Badge
                      variant="outline"
                      className="h-5 font-mono text-[10px]"
                    >
                      nm {selectedNmId}
                    </Badge>
                  )}
                  {source && (
                    <Badge variant="outline" className="h-5 text-[10px]">
                      {humanizeDraftSource(source)}
                    </Badge>
                  )}
                </div>
              </div>
              <Badge
                variant={selectedStatusMeta.variant}
                className="shrink-0 gap-1 text-[10px]"
              >
                <SelectedStatusIcon className="h-3 w-3" />
                {humanizeStatus(selectedStatus)}
              </Badge>
            </div>
          </div>

          <div className="min-h-0 flex-1 space-y-3 overflow-y-auto p-3.5">
            <div className="grid grid-cols-2 gap-2 rounded-lg bg-muted/20 px-3 py-2 sm:grid-cols-4">
              <MetaCell
                label="Дата"
                value={
                  selectedDate
                    ? `${compactDate(selectedDate)} ${compactTime(selectedDate)}`
                    : null
                }
              />
              <MetaCell
                label="Рейтинг"
                value={selectedRating != null ? `${selectedRating}/5` : null}
              />
              <MetaCell label="Провайдер" value={provider} />
              <MetaCell label="Модель" value={model} />
            </div>

            <div className="rounded-lg border border-primary/20 bg-primary/5 p-3">
              <div className="mb-2 flex items-center justify-between gap-2">
                <div className="flex items-center gap-1.5 text-xs font-semibold text-primary">
                  <Sparkles className="h-3.5 w-3.5" />
                  Текст ответа
                </div>
                <Badge variant="outline" className="font-mono text-[10px]">
                  draft #{selectedDraftKey}
                </Badge>
              </div>
              <div className="min-h-32 whitespace-pre-wrap rounded-lg border border-border/40 bg-background/95 p-3 text-[13px] leading-relaxed text-foreground/90">
                {selectedText || "Текст черновика пустой"}
              </div>
            </div>

            {(Object.keys(classification).length > 0 ||
              categories.length > 0 ||
              needReplyScore != null) && (
              <div className="rounded-lg border border-border/50 bg-background p-3">
                <div className="mb-2 flex items-center justify-between gap-2">
                  <div className="flex items-center gap-1.5 text-xs font-semibold">
                    <Brain className="h-3.5 w-3.5 text-primary" />
                    Классификация
                  </div>
                  {needReplyScore != null && (
                    <Badge variant="outline" className="text-[10px]">
                      need reply {needReplyScore}
                    </Badge>
                  )}
                </div>
                <div className="grid gap-2 text-xs sm:grid-cols-3">
                  <MetaCell
                    label="Bucket"
                    value={
                      getString(classification.reply_bucket)
                        ? humanizeBucket(
                            getString(classification.reply_bucket)!,
                          )
                        : null
                    }
                  />
                  <MetaCell
                    label="Настроение"
                    value={
                      getString(classification.sentiment)
                        ? (SENTIMENT_LABELS[
                            getString(classification.sentiment)!
                          ] ?? getString(classification.sentiment))
                        : null
                    }
                  />
                  <MetaCell
                    label="Приоритет"
                    value={getString(classification.priority)}
                  />
                </div>
                {categories.length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-1">
                    {categories.slice(0, 8).map((category, index) => {
                      const label = isRecord(category)
                        ? (getString(category.label) ??
                          getString(category.code))
                        : String(category);
                      return (
                        <Badge
                          key={`${label}-${index}`}
                          variant="secondary"
                          className="text-[10px]"
                        >
                          {label}
                        </Badge>
                      );
                    })}
                  </div>
                )}
              </div>
            )}

            {(Object.keys(trace).length > 0 || warnings.length > 0) && (
              <div className="rounded-lg border border-border/50 bg-background p-3">
                <div className="mb-2 flex items-center gap-1.5 text-xs font-semibold">
                  <ListChecks className="h-3.5 w-3.5 text-primary" />
                  Аудит генерации
                </div>
                <div className="grid gap-2 text-xs sm:grid-cols-3">
                  <MetaCell
                    label="Токены"
                    value={
                      getNumber(trace.prompt_tokens) != null ||
                      getNumber(trace.completion_tokens) != null
                        ? `${getNumber(trace.prompt_tokens) ?? 0}/${getNumber(trace.completion_tokens) ?? 0}`
                        : null
                    }
                  />
                  <MetaCell
                    label="Задержка"
                    value={
                      getNumber(trace.latency_ms) != null
                        ? `${getNumber(trace.latency_ms)} мс`
                        : null
                    }
                  />
                  <MetaCell
                    label="Warnings"
                    value={warnings.length ? String(warnings.length) : null}
                  />
                </div>
                {trace.instructions && (
                  <pre className="mt-2 max-h-28 overflow-auto whitespace-pre-wrap rounded-md bg-muted/40 p-2 text-[11px] text-muted-foreground">
                    {compactDebugValue(trace.instructions)}
                  </pre>
                )}
                {warnings.length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-1">
                    {warnings.slice(0, 6).map((warning, index) => (
                      <Badge
                        key={`draft-warning-${index}`}
                        variant="secondary"
                        className="text-[10px]"
                      >
                        {humanizeWarning(String(warning))}
                      </Badge>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>

          <div className="shrink-0 border-t border-border/50 bg-card/95 px-3 py-2 xl:pr-36">
            <div className="flex flex-wrap items-center gap-1.5">
              <Button
                size="sm"
                variant="outline"
                className="h-8 gap-1.5 text-[12px]"
                onClick={() => onRegenerate(selectedDraftKey, forceAiForDraft)}
                disabled={pending.regenerate || !selectedDraftKey}
              >
                <RefreshCw className="h-3.5 w-3.5" />
                Перегенерировать
              </Button>
              <Button
                size="sm"
                className="h-8 gap-1.5 text-[12px]"
                onClick={() => onApprove(selectedDraftKey)}
                disabled={pending.approve || !selectedDraftKey}
                title={
                  publishEnabled
                    ? "Одобрить по настройкам публикации"
                    : "Одобрить локально; публикация выключена"
                }
              >
                <CheckCircle2 className="h-3.5 w-3.5" />
                Одобрить
              </Button>
              <Button
                size="sm"
                variant="ghost"
                className="h-8 text-[12px]"
                onClick={() => onReject(selectedDraftKey)}
                disabled={pending.reject || !selectedDraftKey}
              >
                Отклонить
              </Button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function ReputationSetupWizard({
  settings,
  disabled,
  onUpdate,
}: {
  settings: unknown;
  disabled?: boolean;
  onUpdate: (payload: Record<string, unknown>) => void;
}) {
  if (!isRecord(settings)) return null;
  const ratingModeMap = isRecord(settings.rating_mode_map)
    ? settings.rating_mode_map
    : {};
  const runtimeMode = getString(settings.runtime_mode);
  const chatStatus = getString(settings.chats_sync_status);
  const reviewsStatus = getString(settings.reviews_sync_status);
  const questionsStatus = getString(settings.questions_sync_status);
  const backlogStatus = getString(settings.backlog_status);
  const automationStatus = getString(settings.automation_status);
  const signatureCount = parseSignatures(
    (settings as Record<string, unknown>).signatures,
  ).length;
  const fallbackSignature = getString(settings.signature)?.trim() ?? "";
  const updateRatingMode = (rating: string, mode: string) =>
    onUpdate({ rating_mode_map: { ...ratingModeMap, [rating]: mode } });

  const steps = [
    {
      key: "connection",
      title: "Подключение/статус",
      ready: reviewsStatus === "ok" || questionsStatus === "ok",
      detail: `${humanizeRuntimeMode(runtimeMode)} · отзывы ${reviewsStatus ?? "—"} · вопросы ${questionsStatus ?? "—"} · чаты ${chatStatus ?? "—"}`,
    },
    {
      key: "mode",
      title: "Режим",
      ready: Boolean(settings.automation_enabled),
      detail: `Режим ответа: ${humanizeReplyMode(String(settings.reply_mode ?? "semi"))}`,
    },
    {
      key: "ratings",
      title: "Режимы рейтинга",
      ready: Object.keys(ratingModeMap).length > 0,
      detail: "По умолчанию: 1-2 ручной, 3 полуавто, 4-5 авто",
    },
    {
      key: "tone",
      title: "Подписи и тон",
      ready: Boolean(settings.signature) || signatureCount > 0,
      detail:
        signatureCount > 0
          ? `подписи по правилам: ${signatureCount} шт., fallback: ${
              fallbackSignature ? "задан" : "не задан"
            }`
          : fallbackSignature
            ? `fallback: ${fallbackSignature}`
            : "fallback не задан",
    },
    {
      key: "import",
      title: "Импорт прогресса",
      ready: backlogStatus === "ready" || automationStatus === "draft_ready",
      detail: `очередь ${backlogStatus ?? "—"} · автоматизация ${automationStatus ?? "—"}`,
    },
  ];

  return (
    <div className="overflow-hidden rounded-lg border border-border/50 bg-card shadow-sm">
      <div className="flex flex-col gap-3 border-b border-border/50 px-3.5 py-3 lg:flex-row lg:items-center lg:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <div className="text-sm font-semibold">Мастер настройки</div>
            <Badge variant="outline" className="h-5 text-[10px]">
              {steps.filter((step) => step.ready).length}/{steps.length}
            </Badge>
          </div>
          <div className="mt-0.5 text-xs text-muted-foreground">
            Подключение, режим, матрица рейтингов, подписи и импорт в одной
            последовательности.
          </div>
        </div>
        <div className="w-full lg:w-[280px]">
          <ModeSegment
            value={String(settings.reply_mode ?? "semi")}
            disabled={disabled}
            compact
            onChange={(value) => onUpdate({ reply_mode: value })}
          />
        </div>
      </div>

      <div className="grid bg-border/40 sm:grid-cols-2 xl:grid-cols-5">
        {steps.map((step) => (
          <div key={step.key} className="min-w-0 bg-card px-3 py-2.5">
            <div className="mb-1 flex items-center justify-between gap-2">
              <div className="truncate text-xs font-semibold">{step.title}</div>
              {step.ready ? (
                <CheckCircle2 className="h-3.5 w-3.5 shrink-0 text-success" />
              ) : (
                <Clock className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
              )}
            </div>
            <div className="hidden min-h-8 text-[11px] leading-snug text-muted-foreground sm:line-clamp-2">
              {step.detail}
            </div>
          </div>
        ))}
      </div>

      <div className="flex flex-col gap-2 border-t border-border/50 bg-muted/10 px-3.5 py-2.5 sm:flex-row sm:items-center sm:justify-between">
        <div className="text-[11px] text-muted-foreground">
          Быстрый пресет рейтингов: 1–2 ручной, 3 полуавто, 4–5 авто.
        </div>
        <div className="grid w-full grid-cols-5 gap-1 sm:w-[220px]">
          {["1", "2", "3", "4", "5"].map((rating) => (
            <Button
              key={rating}
              type="button"
              size="sm"
              variant="outline"
              className="h-7 px-1 text-xs"
              disabled={disabled}
              onClick={() =>
                updateRatingMode(
                  rating,
                  Number(rating) <= 2
                    ? "manual"
                    : Number(rating) === 3
                      ? "semi"
                      : "auto",
                )
              }
            >
              {rating}
            </Button>
          ))}
        </div>
      </div>
    </div>
  );
}

function ReputationSettingsSections({
  settings,
  learning,
  availableBrands = [],
  brandsLoading,
  brandsError,
  disabled,
  onUpdate,
  onToggleLearning,
  onUpdatePrompts,
  onApplyLearning,
  onDeleteLearningEntry,
  onResetLearning,
}: {
  settings: unknown;
  learning?: unknown;
  availableBrands?: string[];
  brandsLoading?: boolean;
  brandsError?: unknown;
  disabled?: boolean;
  onUpdate: (payload: Record<string, unknown>) => void;
  onToggleLearning: (enabled: boolean) => void;
  onUpdatePrompts: (payload: Record<string, unknown>) => void;
  onApplyLearning: (payload: Record<string, unknown>) => void;
  onDeleteLearningEntry: (entryId: number | string) => void;
  onResetLearning: () => void;
}) {
  const learningRecord = isRecord(learning) ? learning : {};
  const currentReviewPrompt =
    getString(learningRecord.review_prompt_template) ?? "";
  const currentQuestionPrompt =
    getString(learningRecord.question_prompt_template) ?? "";
  const currentChatPrompt =
    getString(learningRecord.chat_prompt_template) ?? "";
  const [instruction, setInstruction] = useState("");
  const [learningTarget, setLearningTarget] = useState("base_prompt");
  const [learningCategory, setLearningCategory] = useState("");
  const [learningSentiment, setLearningSentiment] = useState("negative");
  const [learningStopWord, setLearningStopWord] = useState("");
  const [reviewPromptDraft, setReviewPromptDraft] = useState<string | null>(
    null,
  );
  const [questionPromptDraft, setQuestionPromptDraft] = useState<string | null>(
    null,
  );
  const [chatPromptDraft, setChatPromptDraft] = useState<string | null>(null);
  const [signatureDialogOpen, setSignatureDialogOpen] = useState(false);
  const [signatureBrand, setSignatureBrand] = useState<string>("all");
  const [signatureType, setSignatureType] =
    useState<ReputationSignature["type"]>("all");
  const [signatureRating, setSignatureRating] = useState("all");
  const [signatureText, setSignatureText] = useState("");
  const [signatureEditTarget, setSignatureEditTarget] =
    useState<ReputationSignature | null>(null);
  const [signatureFilterBrand, setSignatureFilterBrand] = useState("all");
  const [signatureFilterRating, setSignatureFilterRating] = useState("all");
  const [signatureFilterType, setSignatureFilterType] = useState<
    ReputationSignature["type"] | "all"
  >("all");
  const [section, setSection] = useState<ReputationSettingsSection>("system");
  if (!isRecord(settings)) return null;
  const rawSignatures = Array.isArray(settings.signatures)
    ? settings.signatures
    : [];
  const signatures = parseSignatures(rawSignatures);
  const signatureBrands = Array.from(
    [
      ...availableBrands,
      ...signatures.map((signature) => signature.brand),
    ].reduce((acc, value) => {
      const brand = normalizeSignatureBrand(value);
      const key = brand.toLowerCase();
      if (key !== "all" && !acc.has(key)) acc.set(key, brand);
      return acc;
    }, new Map<string, string>()),
  )
    .map(([, brand]) => brand)
    .sort((a, b) => a.localeCompare(b, "ru"));
  const filteredSignatures = signatures.filter((signature) => {
    const isBrandMatch =
      signatureFilterBrand === "all" ||
      signature.brand.toLowerCase() === signatureFilterBrand.toLowerCase();
    const isTypeMatch =
      signatureFilterType === "all" || signature.type === signatureFilterType;
    const isRatingMatch =
      signatureFilterRating === "all"
        ? true
        : signatureFilterRating === "none"
          ? signature.rating == null
          : Number(signatureFilterRating) === signature.rating;
    return isBrandMatch && isTypeMatch && isRatingMatch;
  });
  const hasActiveSignatureFilters =
    signatureFilterBrand !== "all" ||
    signatureFilterType !== "all" ||
    signatureFilterRating !== "all";
  const signatureStats = {
    total: signatures.length,
    all: signatures.filter((signature) => signature.type === "all").length,
    review: signatures.filter((signature) => signature.type === "review")
      .length,
    question: signatures.filter((signature) => signature.type === "question")
      .length,
    chat: signatures.filter((signature) => signature.type === "chat").length,
  };
  const fallbackSignature = String(settings.signature ?? "").trim();

  const formatSignatureDate = (value: string | null) => {
    if (!value) return "—";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "—";
    return `${compactDate(value)} ${compactTime(value)}`.trim();
  };
  const resetSignatureFilters = () => {
    setSignatureFilterBrand("all");
    setSignatureFilterType("all");
    setSignatureFilterRating("all");
  };
  const closeSignatureDialog = () => {
    setSignatureDialogOpen(false);
    setSignatureEditTarget(null);
    setSignatureBrand("all");
    setSignatureType("all");
    setSignatureRating("all");
    setSignatureText("");
  };
  const persistSignatures = (nextSignatures: ReputationSignaturePayload[]) => {
    onUpdate({ signatures: nextSignatures });
  };
  const saveSignature = () => {
    const nextText = normalizeSignatureText(signatureText);
    if (!nextText) return;

    const nextItem: ReputationSignature = {
      text: nextText,
      brand: normalizeSignatureBrand(signatureBrand),
      type: signatureType,
      rating:
        signatureRating === "all"
          ? null
          : normalizeSignatureRating(signatureRating),
      is_active: true,
      created_at: signatureEditTarget?.created_at ?? new Date().toISOString(),
      sourceIndex: -1,
    };

    if (signatureEditTarget) {
      const targetIndex = signatures.findIndex(
        (signature) =>
          signature.text === signatureEditTarget.text &&
          signature.brand === signatureEditTarget.brand &&
          signature.type === signatureEditTarget.type &&
          (signature.rating ?? null) === (signatureEditTarget.rating ?? null) &&
          (signature.created_at || "") ===
            (signatureEditTarget.created_at || ""),
      );
      if (targetIndex >= 0) {
        const nextSignatures = signatures.slice();
        nextSignatures[targetIndex] = {
          ...nextItem,
          sourceIndex: signatures[targetIndex].sourceIndex,
        };
        persistSignatures(
          nextSignatures.map(
            ({ text, brand, type, rating, is_active, created_at }) => ({
              text,
              brand,
              type,
              rating,
              is_active,
              created_at,
            }),
          ),
        );
        closeSignatureDialog();
        return;
      }
    }

    persistSignatures([
      ...signatures.map(
        ({ text, brand, type, rating, is_active, created_at }) => ({
          text,
          brand,
          type,
          rating,
          is_active,
          created_at,
        }),
      ),
      {
        text: nextItem.text,
        brand: nextItem.brand,
        type: nextItem.type,
        rating: nextItem.rating,
        is_active: nextItem.is_active,
        created_at: nextItem.created_at,
      },
    ]);
    closeSignatureDialog();
  };
  const openCreateSignature = () => {
    setSignatureEditTarget(null);
    setSignatureBrand("all");
    setSignatureType("all");
    setSignatureRating("all");
    setSignatureText("");
    setSignatureDialogOpen(true);
  };
  const openEditSignature = (index: number) => {
    const signature = filteredSignatures[index];
    if (!signature) return;
    setSignatureEditTarget(signature);
    setSignatureBrand(signature.brand);
    setSignatureType(signature.type);
    setSignatureRating(
      signature.rating == null ? "all" : String(signature.rating),
    );
    setSignatureText(signature.text);
    setSignatureDialogOpen(true);
  };
  const removeSignature = (index: number) => {
    const signature = filteredSignatures[index];
    if (!signature) return;
    const nextSignatures = signatures.filter(
      (item) =>
        !(
          item.text === signature.text &&
          item.brand === signature.brand &&
          item.type === signature.type &&
          (item.rating ?? null) === (signature.rating ?? null) &&
          (item.created_at || "") === (signature.created_at || "")
        ),
    );
    persistSignatures(
      nextSignatures.map(
        ({ text, brand, type, rating, is_active, created_at }) => ({
          text,
          brand,
          type,
          rating,
          is_active,
          created_at,
        }),
      ),
    );
  };

  const learningEnabled = Boolean(learningRecord.enabled);
  const learningCategories = Array.isArray(learningRecord.categories)
    ? learningRecord.categories
    : [];
  const learningEntries = Array.isArray(learningRecord.entries)
    ? learningRecord.entries
    : [];
  const stopWords = Array.isArray(learningRecord.stop_words)
    ? learningRecord.stop_words
    : [];
  const ratingModeMap = isRecord(settings.rating_mode_map)
    ? settings.rating_mode_map
    : {};
  const config = isRecord(settings.config) ? settings.config : {};
  const advanced = isRecord(config.advanced) ? config.advanced : {};
  const toneOfVoice = isRecord(advanced.tone_of_voice)
    ? advanced.tone_of_voice
    : {};
  const settingsData = isRecord(settings.data) ? settings.data : {};
  const ai = isRecord(settingsData.ai) ? settingsData.ai : {};
  const aiConfigured = ai.configured !== false;
  const automationEnabled = Boolean(settings.automation_enabled);
  const autoSync = Boolean(settings.auto_sync);
  const autoDraft = Boolean(settings.auto_draft);
  const questionsAutoDraft = Boolean(settings.questions_auto_draft);
  const questionsAutoPublish = Boolean(settings.questions_auto_publish);
  const chatEnabled = Boolean(settings.chat_enabled);
  const chatAutoReplyEnabled = Boolean(
    settings.chat_auto_reply_enabled ?? settings.chat_auto_reply,
  );
  const autoDraftLimit = Number(settings.auto_draft_limit_per_sync ?? 30);
  const runtimeMode = getString(settings.runtime_mode);
  const dangerousActionsEnabled = settings.dangerous_actions_enabled === true;
  const publishEnabled = settings.publish_enabled === true;
  const autoPublishEnabled = settings.auto_publish_enabled === true;
  const chatSendEnabled = settings.chat_send_enabled === true;
  const updateRatingMode = (rating: string, mode: string) => {
    onUpdate({ rating_mode_map: { ...ratingModeMap, [rating]: mode } });
  };
  const updateAdvanced = (patch: Record<string, unknown>) => {
    onUpdate({ config: { ...config, advanced: { ...advanced, ...patch } } });
  };
  const updateTone = (bucket: string, tone: string) => {
    updateAdvanced({ tone_of_voice: { ...toneOfVoice, [bucket]: tone } });
  };
  const effectiveMode = (rating: string) =>
    String(
      ratingModeMap[rating] ??
        (Number(rating) <= 2
          ? "manual"
          : Number(rating) === 3
            ? "semi"
            : "auto"),
    );

  const sectionStatuses: Record<ReputationSettingsSection, string> = {
    system: automationEnabled
      ? autoSync
        ? "авто включен"
        : "ручной режим"
      : "выключен",
    rules: `общий режим: ${humanizeReplyMode(String(settings.reply_mode ?? "semi"))}`,
    style: `${signatureStats.total} правил для подписей · fallback ${fallbackSignature ? "есть" : "не задан"}`,
    learning: learningEnabled
      ? `${learningEntries.length} правил, ${stopWords.length} стоп-слов`
      : "выключено",
  };

  return (
    <div className="mb-4 space-y-3">
      <ReputationSetupWizard
        settings={settings}
        disabled={disabled}
        onUpdate={onUpdate}
      />
      <Card className="overflow-hidden border-border/50 shadow-sm">
        <CardContent className="p-0">
          <div className="border-b border-border/50 bg-card px-4 py-3">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="flex items-start gap-2">
                <Settings2 className="mt-0.5 h-4 w-4 text-muted-foreground" />
                <div>
                  <div className="text-sm font-semibold">Настройки модуля</div>
                  <div className="text-xs text-muted-foreground">
                    Системные ограничения, правила обработки, стиль ответов и
                    ИИ-черновики.
                  </div>
                </div>
              </div>
              <div className="flex max-w-full flex-wrap items-center justify-end gap-1.5">
                <Badge
                  variant={automationEnabled ? "default" : "secondary"}
                  className="h-5 text-[10px]"
                >
                  {automationEnabled
                    ? "Автоматизация включена"
                    : "Ручной режим"}
                </Badge>
                <Badge
                  variant={autoSync ? "outline" : "secondary"}
                  className="h-5 text-[10px]"
                >
                  Синхронизация {autoSync ? "вкл" : "выкл"}
                </Badge>
                <Badge
                  variant={aiConfigured ? "outline" : "secondary"}
                  className="h-5 text-[10px]"
                >
                  ИИ {aiConfigured ? "готов" : "без ключа"}
                </Badge>
                <Badge
                  variant={publishEnabled ? "outline" : "secondary"}
                  className="hidden h-5 text-[10px] sm:inline-flex"
                >
                  Публикация {publishEnabled ? "вкл" : "выкл"}
                </Badge>
                <Badge
                  variant={chatSendEnabled ? "outline" : "secondary"}
                  className="hidden h-5 text-[10px] lg:inline-flex"
                >
                  Чаты {chatSendEnabled ? "send" : "read"}
                </Badge>
                <Badge
                  variant="outline"
                  className="hidden h-5 text-[10px] xl:inline-flex"
                >
                  {humanizeRuntimeMode(runtimeMode)}
                </Badge>
              </div>
            </div>
          </div>

          <div className="grid gap-0 lg:grid-cols-[218px_1fr]">
            <div className="border-b bg-muted/5 p-3 lg:border-b-0 lg:border-r">
              <div className="grid gap-1 sm:grid-cols-3 lg:grid-cols-1">
                {REPUTATION_SETTINGS_SECTIONS.map((item) => {
                  const isActive = section === item.id;
                  const Icon = item.icon;
                  return (
                    <button
                      key={item.id}
                      type="button"
                      className={
                        "w-full rounded-md px-3 py-2 text-left transition-colors " +
                        "space-y-0.5 text-[12px] " +
                        (isActive
                          ? "bg-background shadow-sm ring-1 ring-primary/20"
                          : "text-muted-foreground hover:bg-muted/50")
                      }
                      onClick={() => setSection(item.id)}
                    >
                      <div className="flex items-start gap-2">
                        <Icon className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                        <span className="min-w-0">
                          <span className="block text-xs font-medium text-foreground">
                            {item.title}
                          </span>
                          <span className="block truncate text-[11px] font-normal text-muted-foreground">
                            {item.description}
                          </span>
                          <span className="block truncate text-[10px] text-muted-foreground/80">
                            {sectionStatuses[item.id]}
                          </span>
                        </span>
                      </div>
                    </button>
                  );
                })}
              </div>
            </div>

            <div className="p-4">
              {section === "system" && (
                <div className="space-y-3">
                  <div className="mb-1">
                    <div className="text-sm font-semibold">
                      Системные ограничения
                    </div>
                    <div className="text-[11px] text-muted-foreground">
                      Включите автоматизацию, настройте синхронизацию и лимиты
                      обработки.
                    </div>
                  </div>
                  <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
                    <div className="rounded-md border p-3">
                      <div className="mb-3 flex items-start justify-between gap-3">
                        <div>
                          <div className="text-xs font-semibold">
                            Автоматизация
                          </div>
                          <div className="text-[11px] text-muted-foreground">
                            Главный переключатель всех фоновых действий.
                          </div>
                        </div>
                        <Switch
                          checked={automationEnabled}
                          disabled={disabled}
                          onCheckedChange={(checked) =>
                            onUpdate({ automation_enabled: checked })
                          }
                        />
                      </div>
                      <Badge
                        variant={automationEnabled ? "default" : "secondary"}
                      >
                        {automationEnabled ? "Активно" : "Остановлено"}
                      </Badge>
                    </div>

                    <div className="rounded-md border p-3">
                      <div className="mb-3 flex items-start justify-between gap-3">
                        <div>
                          <div className="text-xs font-semibold">
                            Автосинхронизация
                          </div>
                          <div className="text-[11px] text-muted-foreground">
                            Плановый сбор отзывов, вопросов и доступных чатов.
                          </div>
                        </div>
                        <Switch
                          checked={autoSync}
                          disabled={disabled}
                          onCheckedChange={(checked) =>
                            onUpdate({ auto_sync: checked })
                          }
                        />
                      </div>
                      <div className="text-[11px] text-muted-foreground">
                        Работает только когда включена автоматизация.
                      </div>
                    </div>

                    <div className="rounded-md border p-3">
                      <div className="mb-3 flex items-start justify-between gap-3">
                        <div>
                          <div className="text-xs font-semibold">
                            ИИ-черновики
                          </div>
                          <div className="text-[11px] text-muted-foreground">
                            Создание черновиков без публикации.
                          </div>
                        </div>
                        <Switch
                          checked={autoDraft}
                          disabled={disabled}
                          onCheckedChange={(checked) =>
                            onUpdate({ auto_draft: checked })
                          }
                        />
                      </div>
                      <div className="flex items-center gap-2">
                        <Bot className="h-4 w-4 text-muted-foreground" />
                        <Badge variant={aiConfigured ? "outline" : "secondary"}>
                          {aiConfigured ? "ИИ готов" : "нет ключа"}
                        </Badge>
                      </div>
                    </div>

                    <div className="rounded-md border p-3">
                      <div className="mb-3 flex items-start justify-between gap-3">
                        <div>
                          <div className="text-xs font-semibold">
                            Публикация
                          </div>
                          <div className="text-[11px] text-muted-foreground">
                            Одобрение черновика публикует ответ при доступе WB.
                          </div>
                        </div>
                        <Switch
                          checked={autoPublishEnabled}
                          disabled={disabled || !publishEnabled}
                          onCheckedChange={(checked) =>
                            onUpdate({
                              auto_publish_enabled: checked,
                              auto_publish: checked,
                            })
                          }
                        />
                      </div>
                      <Badge
                        variant={autoPublishEnabled ? "default" : "secondary"}
                      >
                        Автопубликация {autoPublishEnabled ? "вкл" : "выкл"}
                      </Badge>
                      {!publishEnabled && (
                        <div className="mt-2 text-[11px] text-muted-foreground">
                          Серверный publish flag выключен.
                        </div>
                      )}
                    </div>
                  </div>

                  <div className="rounded-md border p-3">
                    <div className="mb-2 flex items-center justify-between gap-3">
                      <div>
                        <div className="text-xs font-semibold">
                          Лимит черновиков за один проход
                        </div>
                        <div className="text-[11px] text-muted-foreground">
                          Защищает операторов от большой очереди после синка.
                        </div>
                      </div>
                      <Input
                        className="h-8 w-24"
                        type="number"
                        min={0}
                        max={500}
                        value={
                          Number.isFinite(autoDraftLimit) ? autoDraftLimit : 30
                        }
                        disabled={disabled}
                        onChange={(event) =>
                          onUpdate({
                            auto_draft_limit_per_sync: Number(
                              event.target.value,
                            ),
                          })
                        }
                      />
                    </div>
                    {!automationEnabled && (
                      <Alert className="mt-3">
                        <Info className="h-4 w-4" />
                        <AlertTitle>Автоматизация выключена</AlertTitle>
                        <AlertDescription>
                          Ручная синхронизация и ручные черновики доступны,
                          фоновые задачи не запускаются.
                        </AlertDescription>
                      </Alert>
                    )}
                  </div>
                </div>
              )}

              {section === "rules" && (
                <div className="space-y-5">
                  <div className="mb-1">
                    <div className="text-sm font-semibold">
                      Правила обработки
                    </div>
                    <div className="text-[11px] text-muted-foreground">
                      Настройте логику ответов по каналам, в т.ч. матрицу по
                      оценкам 1–5.
                    </div>
                  </div>
                  <div className="grid gap-3 lg:grid-cols-[1.1fr_1fr]">
                    <div className="rounded-md border p-3">
                      <div className="mb-2">
                        <div className="text-xs font-semibold">
                          Общий режим ответов
                        </div>
                        <div className="text-[11px] text-muted-foreground">
                          {REPLY_MODE_HINTS[
                            String(settings.reply_mode ?? "semi")
                          ] ?? "базовое поведение"}
                        </div>
                      </div>
                      <ModeSegment
                        value={String(settings.reply_mode ?? "semi")}
                        disabled={disabled}
                        onChange={(value) => onUpdate({ reply_mode: value })}
                      />
                    </div>
                    <div className="rounded-md border p-3">
                      <div className="mb-2">
                        <div className="text-xs font-semibold">
                          Вопросы покупателей
                        </div>
                        <div className="text-[11px] text-muted-foreground">
                          Отдельный режим для вопросов WB.
                        </div>
                      </div>
                      <ModeSegment
                        value={String(settings.questions_reply_mode ?? "semi")}
                        disabled={disabled}
                        onChange={(value) =>
                          onUpdate({ questions_reply_mode: value })
                        }
                      />
                      <div className="mt-3 flex items-center justify-between gap-3 rounded-md bg-muted/30 px-3 py-2">
                        <div className="text-xs">
                          <div className="font-medium">
                            Черновики для вопросов
                          </div>
                          <div className="text-[11px] text-muted-foreground">
                            Генерировать ответы по вопросам WB.
                          </div>
                        </div>
                        <Switch
                          checked={questionsAutoDraft}
                          disabled={disabled}
                          onCheckedChange={(checked) =>
                            onUpdate({ questions_auto_draft: checked })
                          }
                        />
                      </div>
                      <div className="mt-2 flex items-center justify-between gap-3 rounded-md bg-muted/30 px-3 py-2">
                        <div className="text-xs">
                          <div className="font-medium">
                            Автопубликация вопросов
                          </div>
                          <div className="text-[11px] text-muted-foreground">
                            В режиме auto отправлять ответ после генерации.
                          </div>
                        </div>
                        <Switch
                          checked={questionsAutoPublish}
                          disabled={disabled || !publishEnabled}
                          onCheckedChange={(checked) =>
                            onUpdate({ questions_auto_publish: checked })
                          }
                        />
                      </div>
                    </div>
                  </div>

                  <div className="space-y-2">
                    <div>
                      <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                        Матрица рейтингов
                      </div>
                      <div className="text-xs text-muted-foreground">
                        Низкие оценки отправляем на ручной контроль, высокие
                        можно вести через ИИ-черновик.
                      </div>
                    </div>
                    <div className="grid gap-2 lg:grid-cols-5">
                      {["1", "2", "3", "4", "5"].map((rating) => {
                        const mode = effectiveMode(rating);
                        return (
                          <div
                            key={rating}
                            className="space-y-2 rounded-md border p-3"
                          >
                            <div className="flex items-center justify-between gap-2">
                              <div className="flex items-center gap-1.5 font-semibold">
                                <Star className="h-3.5 w-3.5 text-warning" />
                                <span>{rating}</span>
                              </div>
                              <Badge
                                variant={
                                  mode === "manual"
                                    ? "secondary"
                                    : mode === "auto"
                                      ? "default"
                                      : "outline"
                                }
                                className="text-[10px]"
                              >
                                {humanizeReplyMode(mode)}
                              </Badge>
                            </div>
                            <div className="min-h-8 text-[11px] text-muted-foreground">
                              {REPLY_MODE_HINTS[mode]}
                            </div>
                            <ModeSegment
                              value={mode}
                              disabled={disabled}
                              compact
                              iconOnly
                              onChange={(value) =>
                                updateRatingMode(rating, value)
                              }
                            />
                          </div>
                        );
                      })}
                    </div>
                  </div>

                  <div className="rounded-md border p-3">
                    <div className="mb-3 flex items-start justify-between gap-3">
                      <div>
                        <div className="text-xs font-semibold">Чаты</div>
                        <div className="text-[11px] text-muted-foreground">
                          Включайте после проверки WB chat-доступа; автоответы
                          управляются отдельным флагом.
                        </div>
                      </div>
                      <Switch
                        checked={chatEnabled}
                        disabled={disabled}
                        onCheckedChange={(checked) =>
                          onUpdate({ chat_enabled: checked })
                        }
                      />
                    </div>
                    <div className="flex flex-wrap gap-2">
                      <Badge variant={chatEnabled ? "outline" : "secondary"}>
                        {chatEnabled ? "Чаты включены" : "Чаты выключены"}
                      </Badge>
                      <Badge
                        variant={chatAutoReplyEnabled ? "default" : "secondary"}
                      >
                        Автоответы {chatAutoReplyEnabled ? "вкл" : "выкл"}
                      </Badge>
                    </div>
                    <div className="mt-3 flex items-center justify-between gap-3 rounded-md bg-muted/30 px-3 py-2">
                      <div className="text-xs">
                        <div className="font-medium">Автоответы в чатах</div>
                        <div className="text-[11px] text-muted-foreground">
                          Сохраняет режим AVEOTVET для будущей отправки.
                        </div>
                      </div>
                      <Switch
                        checked={chatAutoReplyEnabled}
                        disabled={disabled || !chatEnabled || !publishEnabled}
                        onCheckedChange={(checked) =>
                          onUpdate({
                            chat_auto_reply_enabled: checked,
                            chat_auto_reply: checked,
                          })
                        }
                      />
                    </div>
                  </div>
                </div>
              )}

              {section === "style" && (
                <div className="space-y-5">
                  <div className="mb-1">
                    <div className="text-sm font-semibold">Стиль и подписи</div>
                    <div className="text-[11px] text-muted-foreground">
                      Настройте ИИ, длину ответа и правила финальных подписей.
                    </div>
                  </div>
                  <div className="grid gap-3 lg:grid-cols-3">
                    <div className="space-y-2 rounded-md border p-3">
                      <div>
                        <div className="text-xs font-medium">ИИ-черновики</div>
                        <div className="text-[11px] text-muted-foreground">
                          Включает генерацию текста через настроенного
                          провайдера.
                        </div>
                      </div>
                      <div className="flex items-center justify-between gap-3">
                        <span className="text-xs font-medium">
                          Черновики ИИ
                        </span>
                        <Switch
                          checked={Boolean(settings.ai_enabled)}
                          disabled={disabled}
                          onCheckedChange={(checked) =>
                            onUpdate({ ai_enabled: checked })
                          }
                        />
                        <Badge variant={aiConfigured ? "outline" : "secondary"}>
                          {aiConfigured ? "ключ настроен" : "нет ключа"}
                        </Badge>
                      </div>
                    </div>

                    <div className="space-y-2 rounded-md border p-3">
                      <div>
                        <div className="text-xs font-medium">Модель</div>
                        <div className="text-[11px] text-muted-foreground">
                          Используется при создании черновиков.
                        </div>
                      </div>
                      <Select
                        value={String(settings.ai_model ?? "gpt-5-mini")}
                        disabled={disabled}
                        onValueChange={(value) => onUpdate({ ai_model: value })}
                      >
                        <SelectTrigger className="h-8">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {["gpt-5-mini", "gpt-5", "gpt-4.1-mini"].map(
                            (model) => (
                              <SelectItem key={model} value={model}>
                                {model}
                              </SelectItem>
                            ),
                          )}
                        </SelectContent>
                      </Select>
                    </div>

                    <div className="space-y-2 rounded-md border p-3">
                      <div>
                        <div className="text-xs font-medium">Длина ответа</div>
                        <div className="text-[11px] text-muted-foreground">
                          Контроль размера готового текста.
                        </div>
                      </div>
                      <Select
                        value={String(advanced.answer_length ?? "short")}
                        disabled={disabled}
                        onValueChange={(value) =>
                          updateAdvanced({ answer_length: value })
                        }
                      >
                        <SelectTrigger className="h-8">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {["short", "medium", "detailed"].map((length) => (
                            <SelectItem key={length} value={length}>
                              {LENGTH_LABELS[length]}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                  </div>

                  <div className="space-y-2">
                    <div>
                      <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                        Тональность ИИ
                      </div>
                      <div className="text-xs text-muted-foreground">
                        Отдельная интонация для положительных, нейтральных,
                        негативных сообщений и вопросов.
                      </div>
                    </div>
                    <div className="grid gap-3 md:grid-cols-4">
                      {[
                        ["positive", "Позитив"],
                        ["neutral", "Нейтрал"],
                        ["negative", "Негатив"],
                        ["question", "Вопрос"],
                      ].map(([bucket, label]) => (
                        <div key={bucket} className="space-y-1">
                          <div className="text-[10px] uppercase tracking-wide text-muted-foreground">
                            {label}
                          </div>
                          <Select
                            value={String(
                              toneOfVoice[bucket] ??
                                (bucket === "negative"
                                  ? "empathetic"
                                  : "polite"),
                            )}
                            disabled={disabled}
                            onValueChange={(value) => updateTone(bucket, value)}
                          >
                            <SelectTrigger className="h-8">
                              <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                              {Object.entries(TONE_LABELS).map(
                                ([tone, labelText]) => (
                                  <SelectItem key={tone} value={tone}>
                                    {labelText}
                                  </SelectItem>
                                ),
                              )}
                            </SelectContent>
                          </Select>
                        </div>
                      ))}
                    </div>
                  </div>

                  <div className="rounded-md border p-3">
                    <div className="mb-2 text-xs font-semibold">
                      Резервная подпись (fallback)
                    </div>
                    <div className="mb-2 flex flex-wrap items-center gap-2">
                      <Badge
                        variant={fallbackSignature ? "outline" : "secondary"}
                      >
                        {fallbackSignature ? "Задана" : "Не задана"}
                      </Badge>
                      <span className="text-[11px] text-muted-foreground">
                        Добавляется только если ни одно правило подписи не
                        подошло.
                      </span>
                    </div>
                    <Input
                      value={String(settings.signature ?? "")}
                      placeholder="Например: Команда поддержки"
                      disabled={disabled}
                      onChange={(event) =>
                        onUpdate({ signature: event.target.value })
                      }
                    />
                    <div className="mt-2 text-[11px] text-muted-foreground">
                      {fallbackSignature
                        ? `Текущий fallback: «${fallbackSignature}»`
                        : "Резервная подпись не задана: если правило не подойдет, подпись не добавится к ответу."}
                    </div>
                  </div>

                  <div className="rounded-md border p-3 space-y-3">
                    <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                      <div>
                        <div className="text-xs font-semibold">
                          Правила подписи
                        </div>
                        <div className="text-[11px] text-muted-foreground">
                          Итого {signatureStats.total} правил. По каналам: любой
                          ({signatureStats.all}), отзывы (
                          {signatureStats.review}), вопросы (
                          {signatureStats.question}), чаты (
                          {signatureStats.chat}).
                        </div>
                        <div className="text-[11px] text-muted-foreground">
                          {brandsLoading
                            ? "Бренды из каталога загружаются..."
                            : brandsError
                              ? "Бренды из каталога не загрузились, доступны только уже сохранённые подписи."
                              : `Брендов из каталога: ${availableBrands.length}. В списке: ${signatureBrands.length}.`}
                        </div>
                      </div>
                      <Button
                        size="sm"
                        className="h-8 px-3"
                        disabled={disabled}
                        onClick={openCreateSignature}
                      >
                        <Plus className="mr-1.5 h-3.5 w-3.5" />
                        Добавить правило
                      </Button>
                      {hasActiveSignatureFilters && (
                        <Button
                          size="sm"
                          variant="outline"
                          className="h-8 px-3"
                          disabled={disabled}
                          onClick={resetSignatureFilters}
                        >
                          Сбросить фильтры
                        </Button>
                      )}
                    </div>

                    <Alert>
                      <Info className="h-4 w-4" />
                      <AlertDescription>
                        <div className="space-y-1">
                          <p className="text-[11px] font-semibold">
                            Как выбирается подпись:
                          </p>
                          <ol className="list-decimal space-y-1 pl-5">
                            {SIGNATURE_PRIORITY_STEPS.map((step) => (
                              <li key={step.title}>
                                <span className="font-medium">
                                  {step.title}:
                                </span>{" "}
                                {step.value}
                              </li>
                            ))}
                          </ol>
                        </div>
                      </AlertDescription>
                    </Alert>

                    <div className="flex flex-wrap gap-2">
                      <div className="min-w-[170px]">
                        <Label className="mb-1 block text-[11px] text-muted-foreground">
                          Тип обращения
                        </Label>
                        <Select
                          value={signatureFilterType}
                          disabled={disabled}
                          onValueChange={(value) =>
                            setSignatureFilterType(
                              normalizeSignatureTypeFilter(value),
                            )
                          }
                        >
                          <SelectTrigger className="h-8">
                            <SelectValue placeholder="Любой канал" />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="all">Любой канал</SelectItem>
                            {SIGNATURE_KINDS.map((kind) => (
                              <SelectItem key={kind.value} value={kind.value}>
                                {kind.label}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>
                      <div className="min-w-[170px]">
                        <Label className="mb-1 block text-[11px] text-muted-foreground">
                          Бренд
                        </Label>
                        <Select
                          value={signatureFilterBrand}
                          disabled={disabled}
                          onValueChange={setSignatureFilterBrand}
                        >
                          <SelectTrigger className="h-8">
                            <SelectValue placeholder="Все бренды" />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="all">Все бренды</SelectItem>
                            {brandsLoading && (
                              <SelectItem value="__loading" disabled>
                                Бренды загружаются...
                              </SelectItem>
                            )}
                            {!brandsLoading && signatureBrands.length === 0 && (
                              <SelectItem value="__none" disabled>
                                Нет брендов в каталоге
                              </SelectItem>
                            )}
                            {signatureBrands.map((brand) => (
                              <SelectItem key={brand} value={brand}>
                                {brand}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>
                      <div className="min-w-[170px]">
                        <Label className="mb-1 block text-[11px] text-muted-foreground">
                          Рейтинг
                        </Label>
                        <Select
                          value={signatureFilterRating}
                          disabled={disabled}
                          onValueChange={(value) =>
                            setSignatureFilterRating(
                              normalizeSignatureFilterRating(value),
                            )
                          }
                        >
                          <SelectTrigger className="h-8">
                            <SelectValue placeholder="Все оценки" />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="all">Все рейтинги</SelectItem>
                            <SelectItem value="none">Для всех</SelectItem>
                            {[5, 4, 3, 2, 1].map((rating) => (
                              <SelectItem key={rating} value={String(rating)}>
                                {rating} ★
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>
                    </div>

                    <div className="rounded-md border border-border/60">
                      <Table>
                        <TableHeader>
                          <TableRow>
                            <TableHead>Текст подписи</TableHead>
                            <TableHead>Тип обращения</TableHead>
                            <TableHead>Бренд</TableHead>
                            <TableHead>Рейтинг</TableHead>
                            <TableHead>Приоритет</TableHead>
                            <TableHead>Создано</TableHead>
                            <TableHead className="w-[90px]" />
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {filteredSignatures.length === 0 ? (
                            <TableRow>
                              <TableCell
                                colSpan={7}
                                className="py-8 text-center text-xs text-muted-foreground"
                              >
                                Подписей по выбранным фильтрам пока нет.
                              </TableCell>
                            </TableRow>
                          ) : (
                            filteredSignatures.map((signature, index) => (
                              <TableRow
                                key={`${signature.text}-${signature.sourceIndex}-${index}`}
                              >
                                <TableCell className="max-w-[360px] break-words">
                                  {signature.text}
                                </TableCell>
                                <TableCell>
                                  <Badge
                                    variant="outline"
                                    className="text-[10px]"
                                    title={
                                      SIGNATURE_SCOPE_HINTS[signature.type]
                                    }
                                  >
                                    {signatureScopeLabel(signature)}
                                  </Badge>
                                </TableCell>
                                <TableCell className="text-xs text-muted-foreground">
                                  {signatureBrandLabel(signature)}
                                </TableCell>
                                <TableCell className="text-xs text-muted-foreground">
                                  {signatureRatingLabel(signature)}
                                </TableCell>
                                <TableCell>
                                  <Badge
                                    variant={
                                      signatureRulePriority(signature) === 0
                                        ? "secondary"
                                        : "outline"
                                    }
                                    className="text-[10px]"
                                  >
                                    +{signatureRulePriority(signature)} балл
                                  </Badge>
                                </TableCell>
                                <TableCell>
                                  {formatSignatureDate(signature.created_at)}
                                </TableCell>
                                <TableCell className="space-x-1">
                                  <Button
                                    size="sm"
                                    variant="outline"
                                    className="h-7 w-7 px-0"
                                    disabled={disabled}
                                    onClick={() => openEditSignature(index)}
                                  >
                                    <Pencil className="h-3.5 w-3.5" />
                                  </Button>
                                  <Button
                                    size="sm"
                                    variant="outline"
                                    className="h-7 w-7 px-0 text-destructive"
                                    disabled={disabled}
                                    onClick={() => removeSignature(index)}
                                  >
                                    <Trash2 className="h-3.5 w-3.5" />
                                  </Button>
                                </TableCell>
                              </TableRow>
                            ))
                          )}
                        </TableBody>
                      </Table>
                    </div>
                  </div>
                </div>
              )}

              {section === "learning" && (
                <div className="space-y-5">
                  <div className="mb-1">
                    <div className="text-sm font-semibold">ИИ-обучение</div>
                    <div className="text-[11px] text-muted-foreground">
                      Добавляйте правила и промпты, которые будут влиять на
                      будущую генерацию черновиков и классификацию.
                    </div>
                  </div>
                  <div className="grid gap-3 lg:grid-cols-[1fr_1.2fr]">
                    <div className="rounded-md border p-3">
                      <div className="mb-3 flex items-start justify-between gap-3">
                        <div>
                          <div className="text-xs font-semibold">
                            Ручное обучение ИИ
                          </div>
                          <div className="text-[11px] text-muted-foreground">
                            Операторские правила добавляются в генерацию
                            черновиков и аналитику артикула.
                          </div>
                        </div>
                        <Switch
                          checked={learningEnabled}
                          disabled={disabled}
                          onCheckedChange={onToggleLearning}
                        />
                      </div>
                      <div className="grid gap-2">
                        <Select
                          value={learningTarget}
                          disabled={disabled}
                          onValueChange={setLearningTarget}
                        >
                          <SelectTrigger className="h-8">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="base_prompt">
                              Общее правило
                            </SelectItem>
                            <SelectItem value="category_prompt">
                              Правило категории
                            </SelectItem>
                            <SelectItem value="stop_word">
                              Стоп-слово
                            </SelectItem>
                          </SelectContent>
                        </Select>
                        {learningTarget === "category_prompt" && (
                          <div className="grid gap-2 sm:grid-cols-2">
                            <Select
                              value={learningCategory || "none"}
                              disabled={disabled}
                              onValueChange={(value) =>
                                setLearningCategory(
                                  value === "none" ? "" : value,
                                )
                              }
                            >
                              <SelectTrigger className="h-8">
                                <SelectValue />
                              </SelectTrigger>
                              <SelectContent>
                                <SelectItem value="none">Категория</SelectItem>
                                {learningCategories.map((category, index) => (
                                  <SelectItem
                                    key={`learn-cat-${index}`}
                                    value={
                                      getString(category.code) ??
                                      `category-${index}`
                                    }
                                  >
                                    {getString(category.label) ??
                                      getString(category.code)}
                                  </SelectItem>
                                ))}
                              </SelectContent>
                            </Select>
                            <Select
                              value={learningSentiment}
                              disabled={disabled}
                              onValueChange={setLearningSentiment}
                            >
                              <SelectTrigger className="h-8">
                                <SelectValue />
                              </SelectTrigger>
                              <SelectContent>
                                <SelectItem value="negative">
                                  Негатив
                                </SelectItem>
                                <SelectItem value="positive">
                                  Позитив
                                </SelectItem>
                                <SelectItem value="neutral">Нейтрал</SelectItem>
                              </SelectContent>
                            </Select>
                          </div>
                        )}
                        {learningTarget === "stop_word" && (
                          <Input
                            value={learningStopWord}
                            disabled={disabled}
                            placeholder="Слово или фраза, которую нельзя использовать"
                            onChange={(event) =>
                              setLearningStopWord(event.target.value)
                            }
                          />
                        )}
                        <Textarea
                          value={instruction}
                          disabled={disabled || !learningEnabled}
                          rows={4}
                          placeholder="Например: при жалобе на размер не спорить с покупателем, мягко предложить свериться с размерной сеткой."
                          onChange={(event) =>
                            setInstruction(event.target.value)
                          }
                        />
                        <div className="flex flex-wrap gap-2">
                          <Button
                            size="sm"
                            disabled={
                              disabled ||
                              !learningEnabled ||
                              !instruction.trim() ||
                              (learningTarget === "category_prompt" &&
                                !learningCategory)
                            }
                            onClick={() => {
                              onApplyLearning({
                                instruction,
                                target_type: learningTarget,
                                category_code:
                                  learningTarget === "category_prompt"
                                    ? learningCategory
                                    : null,
                                sentiment_scope:
                                  learningTarget === "category_prompt"
                                    ? learningSentiment
                                    : null,
                                stop_word:
                                  learningTarget === "stop_word"
                                    ? learningStopWord || instruction
                                    : null,
                              });
                              setInstruction("");
                              setLearningStopWord("");
                            }}
                          >
                            Добавить правило
                          </Button>
                          <Button
                            size="sm"
                            variant="outline"
                            disabled={disabled}
                            onClick={onResetLearning}
                          >
                            Сбросить обучение
                          </Button>
                        </div>
                      </div>
                    </div>

                    <div className="rounded-md border p-3">
                      <div className="mb-2 flex items-center justify-between gap-2">
                        <div>
                          <div className="text-xs font-semibold">
                            Активные правила
                          </div>
                          <div className="text-[11px] text-muted-foreground">
                            {learningEntries.length} правил · {stopWords.length}{" "}
                            стоп-слов
                          </div>
                        </div>
                        <Badge
                          variant={learningEnabled ? "default" : "secondary"}
                        >
                          {learningEnabled ? "обучение включено" : "выключено"}
                        </Badge>
                      </div>
                      <div className="max-h-72 space-y-2 overflow-y-auto">
                        {learningEntries.slice(0, 12).map((entry, index) => (
                          <div
                            key={`entry-${getString(entry.id) ?? index}`}
                            className="rounded-md border bg-background p-2"
                          >
                            <div className="mb-1 flex items-center justify-between gap-2">
                              <Badge variant="outline" className="text-[10px]">
                                {getString(entry.target_type) ?? "правило"}
                              </Badge>
                              {entry.id != null && (
                                <Button
                                  size="sm"
                                  variant="ghost"
                                  className="h-6 px-2 text-[11px]"
                                  disabled={disabled}
                                  onClick={() =>
                                    onDeleteLearningEntry(String(entry.id))
                                  }
                                >
                                  Отключить
                                </Button>
                              )}
                            </div>
                            <div className="text-xs">
                              {getString(entry.applied_text) ??
                                getString(entry.user_instruction)}
                            </div>
                          </div>
                        ))}
                        {!learningEntries.length && (
                          <div className="rounded-md border border-dashed p-4 text-center text-xs text-muted-foreground">
                            Ручных правил пока нет.
                          </div>
                        )}
                      </div>
                    </div>
                  </div>

                  <div className="grid gap-3 xl:grid-cols-3">
                    {[
                      [
                        "review_prompt_template",
                        "Системный промпт отзывов",
                        reviewPromptDraft ?? currentReviewPrompt,
                        setReviewPromptDraft,
                      ],
                      [
                        "question_prompt_template",
                        "Системный промпт вопросов",
                        questionPromptDraft ?? currentQuestionPrompt,
                        setQuestionPromptDraft,
                      ],
                      [
                        "chat_prompt_template",
                        "Системный промпт чатов",
                        chatPromptDraft ?? currentChatPrompt,
                        setChatPromptDraft,
                      ],
                    ].map(([key, label, value, setter]) => (
                      <div key={String(key)} className="rounded-md border p-3">
                        <div className="mb-2 text-xs font-semibold">
                          {String(label)}
                        </div>
                        <Textarea
                          value={String(value)}
                          rows={7}
                          disabled={disabled}
                          className="font-mono text-xs"
                          onChange={(event) =>
                            (setter as (value: string) => void)(
                              event.target.value,
                            )
                          }
                        />
                        <Button
                          size="sm"
                          className="mt-2"
                          disabled={disabled}
                          onClick={() =>
                            onUpdatePrompts({ [String(key)]: String(value) })
                          }
                        >
                          Сохранить
                        </Button>
                      </div>
                    ))}
                  </div>

                  <div className="rounded-md border p-3">
                    <div className="mb-2 flex items-center justify-between gap-2">
                      <div>
                        <div className="text-xs font-semibold">
                          Категории классификации
                        </div>
                        <div className="text-[11px] text-muted-foreground">
                          Эти промпты используются при генерации ответа и в
                          анализе артикула.
                        </div>
                      </div>
                      <Button
                        size="sm"
                        variant="outline"
                        disabled={disabled}
                        onClick={() =>
                          onUpdatePrompts({
                            stop_words: stopWords.map((word) => String(word)),
                          })
                        }
                      >
                        Сохранить стоп-слова
                      </Button>
                    </div>
                    <div className="mb-3 flex flex-wrap gap-1">
                      {stopWords.slice(0, 20).map((word, index) => (
                        <Badge key={`stop-${index}`} variant="secondary">
                          {String(word)}
                        </Badge>
                      ))}
                      {!stopWords.length && (
                        <span className="text-xs text-muted-foreground">
                          Стоп-слова не заданы.
                        </span>
                      )}
                    </div>
                    <div className="grid gap-2 md:grid-cols-2">
                      {learningCategories.map((category, index) => (
                        <div
                          key={`prompt-cat-${index}`}
                          className="rounded-md border bg-background p-2"
                        >
                          <div className="mb-1 flex items-center justify-between gap-2">
                            <div className="text-xs font-medium">
                              {getString(category.label) ??
                                getString(category.code)}
                            </div>
                            <Badge variant="outline" className="text-[10px]">
                              {getString(category.scope) ?? "глобальный"}
                            </Badge>
                          </div>
                          <div className="text-[11px] text-muted-foreground">
                            Позитив:{" "}
                            {getString(category.positive_prompt) ?? "—"}
                          </div>
                          <div className="mt-1 text-[11px] text-muted-foreground">
                            Негатив:{" "}
                            {getString(category.negative_prompt) ?? "—"}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              )}
            </div>
          </div>
        </CardContent>
      </Card>
      <Sheet
        open={signatureDialogOpen}
        onOpenChange={(open) => {
          if (!open) {
            closeSignatureDialog();
          } else {
            setSignatureDialogOpen(true);
          }
        }}
      >
        <SheetContent className="sm:max-w-[540px]">
          <SheetHeader>
            <SheetTitle>
              {signatureEditTarget ? "Редактирование подписи" : "Новая подпись"}
            </SheetTitle>
          </SheetHeader>
          <div className="mt-5 space-y-4">
            <div className="grid gap-2">
              <Label>Канал применения</Label>
              <p className="text-[11px] text-muted-foreground">
                Выберите, для какого типа обращений применить подпись. Если это
                глобальное правило — оставьте «Для всех каналов».
              </p>
              <Select
                value={signatureType}
                disabled={disabled}
                onValueChange={(value) =>
                  setSignatureType(normalizeSignatureKind(value))
                }
              >
                <SelectTrigger className="h-8">
                  <SelectValue placeholder="Выберите канал" />
                </SelectTrigger>
                <SelectContent>
                  {SIGNATURE_KINDS.map((kind) => (
                    <SelectItem key={kind.value} value={kind.value}>
                      {kind.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="grid gap-2">
              <Label>Бренд</Label>
              <p className="text-[11px] text-muted-foreground">
                Укажите конкретный бренд, если правило для него. Для общих
                правил оставьте «Для всех брендов».
                {brandsLoading
                  ? " Бренды загружаются из каталога."
                  : brandsError
                    ? " Бренды не загрузились, показаны только уже сохранённые."
                    : ` Доступно брендов: ${signatureBrands.length}.`}
              </p>
              <Select
                value={signatureBrand}
                disabled={disabled}
                onValueChange={setSignatureBrand}
              >
                <SelectTrigger className="h-8">
                  <SelectValue placeholder="Все бренды" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Для всех брендов</SelectItem>
                  {brandsLoading && (
                    <SelectItem value="__loading" disabled>
                      Бренды загружаются...
                    </SelectItem>
                  )}
                  {!brandsLoading && signatureBrands.length === 0 && (
                    <SelectItem value="__none" disabled>
                      Нет брендов в каталоге
                    </SelectItem>
                  )}
                  {signatureBrands.map((brand) => (
                    <SelectItem key={brand} value={brand}>
                      {brand}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="grid gap-2">
              <Label>Рейтинг</Label>
              <p className="text-[11px] text-muted-foreground">
                Укажите 1–5 если подпись нужна только для конкретного рейтинга.
                Для общих правил оставьте «Для всех».
              </p>
              <Select
                value={signatureRating}
                disabled={disabled}
                onValueChange={(value) =>
                  setSignatureRating(normalizeSignatureFilterRating(value))
                }
              >
                <SelectTrigger className="h-8">
                  <SelectValue placeholder="Все рейтинги" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Для всех</SelectItem>
                  {[5, 4, 3, 2, 1].map((rating) => (
                    <SelectItem key={rating} value={String(rating)}>
                      {rating} ★
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="grid gap-2">
              <Label>Текст подписи</Label>
              <Textarea
                value={signatureText}
                disabled={disabled}
                onChange={(event) => setSignatureText(event.target.value)}
                rows={4}
                placeholder="Например: С уважением, команда магазина"
              />
            </div>

            <div className="flex items-center gap-2">
              <Button
                onClick={saveSignature}
                disabled={disabled || !signatureText.trim()}
              >
                {signatureEditTarget
                  ? "Сохранить изменения"
                  : "Добавить подпись"}
              </Button>
              <Button
                variant="outline"
                disabled={disabled}
                onClick={closeSignatureDialog}
                type="button"
              >
                Отмена
              </Button>
            </div>
          </div>
        </SheetContent>
      </Sheet>
    </div>
  );
}

function ReputationAnalyticsPanel({
  data,
  loading,
  error,
}: {
  data: Record<string, unknown>;
  loading?: boolean;
  error?: unknown;
}) {
  const byType = isRecord(data.by_type) ? data.by_type : {};
  const byRating = isRecord(data.by_rating) ? data.by_rating : {};
  const categoryLabels = isRecord(data.category_labels)
    ? data.category_labels
    : {};
  const categoryRows = Object.entries(byType)
    .map(([key, value]) => ({
      key,
      label: getString(categoryLabels[key]) ?? key,
      value: getNumber(value) ?? 0,
    }))
    .sort((a, b) => b.value - a.value);
  const ratingRows = ["5", "4", "3", "2", "1"].map((rating) => ({
    rating,
    value: getNumber(byRating[rating]) ?? 0,
  }));
  const maxCategory = Math.max(1, ...categoryRows.map((row) => row.value));
  const maxRating = Math.max(1, ...ratingRows.map((row) => row.value));
  const total = getNumber(data.total) ?? 0;
  const avgRating = getNumber(data.avg_rating);
  const positiveShare = getNumber(data.positive_share) ?? 0;
  const growth =
    getString(data.period_growth) ?? String(data.period_growth ?? 0);

  return (
    <Card className="mb-4 overflow-hidden border-border/50 shadow-sm">
      <CardContent className="space-y-4 p-4">
        {loading ? (
          <Skeleton className="h-48 w-full" />
        ) : error ? (
          <Alert variant="destructive">
            <AlertTriangle className="h-4 w-4" />
            <AlertDescription>{(error as Error).message}</AlertDescription>
          </Alert>
        ) : (
          <>
            <div className="flex flex-col gap-1 sm:flex-row sm:items-end sm:justify-between">
              <div>
                <div className="text-sm font-semibold">Аналитика репутации</div>
                <div className="text-xs text-muted-foreground">
                  Частые причины, рейтинг и динамика ответов по выбранному
                  периоду.
                </div>
              </div>
              <Badge variant="outline" className="w-fit text-[10px]">
                {total} обращений
              </Badge>
            </div>

            <div className="grid gap-3 md:grid-cols-4">
              {[
                {
                  label: "Всего",
                  value: total,
                  hint: "за период",
                  tone: "text-foreground",
                },
                {
                  label: "Средний рейтинг",
                  value: avgRating != null ? avgRating.toFixed(1) : "—",
                  hint: "из 5",
                  tone: "text-success",
                },
                {
                  label: "Позитив",
                  value: `${positiveShare}%`,
                  hint: "доля положительных",
                  tone: "text-success",
                },
                {
                  label: "Динамика",
                  value: growth,
                  hint: "к прошлому периоду",
                  tone: String(growth).startsWith("-")
                    ? "text-destructive"
                    : "text-primary",
                },
              ].map((metric) => (
                <div
                  key={metric.label}
                  className="rounded-lg border border-border/50 bg-background px-3 py-3"
                >
                  <div className="text-[11px] font-medium text-muted-foreground">
                    {metric.label}
                  </div>
                  <div
                    className={`mt-1 text-2xl font-bold leading-none tabular-nums ${metric.tone}`}
                  >
                    {String(metric.value)}
                  </div>
                  <div className="mt-1 text-[10px] text-muted-foreground">
                    {metric.hint}
                  </div>
                </div>
              ))}
            </div>

            <div className="grid gap-4 lg:grid-cols-[1.2fr_0.8fr]">
              <div className="rounded-lg border border-border/50 bg-background p-3">
                <div className="mb-3 flex items-center justify-between gap-2">
                  <div>
                    <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                      Категории обращений
                    </div>
                    <div className="text-[11px] text-muted-foreground">
                      Самые частые причины, по которым покупатели пишут.
                    </div>
                  </div>
                  <Badge variant="secondary" className="text-[10px]">
                    {categoryRows.length}
                  </Badge>
                </div>
                <div className="space-y-2">
                  {categoryRows.map((row, index) => (
                    <div key={row.key} className="space-y-1">
                      <div className="flex items-center justify-between gap-3 text-sm">
                        <div className="min-w-0">
                          <span className="mr-2 text-[11px] tabular-nums text-muted-foreground">
                            {String(index + 1).padStart(2, "0")}
                          </span>
                          <span className="font-medium">{row.label}</span>
                        </div>
                        <Badge variant="outline" className="tabular-nums">
                          {row.value}
                        </Badge>
                      </div>
                      <div className="h-2 overflow-hidden rounded-full bg-muted">
                        <div
                          className="h-full rounded-full bg-primary"
                          style={{
                            width: `${Math.max(5, Math.round((row.value / maxCategory) * 100))}%`,
                          }}
                        />
                      </div>
                    </div>
                  ))}
                  {!categoryRows.length && (
                    <div className="rounded-md border border-dashed p-6 text-center text-sm text-muted-foreground">
                      Категорий пока нет.
                    </div>
                  )}
                </div>
              </div>

              <div className="rounded-lg border border-border/50 bg-background p-3">
                <div className="mb-3 flex items-center justify-between gap-2">
                  <div>
                    <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                      Распределение рейтинга
                    </div>
                    <div className="text-[11px] text-muted-foreground">
                      Где нужна ручная проверка.
                    </div>
                  </div>
                  <Star className="h-4 w-4 text-warning" />
                </div>
                <div className="space-y-2">
                  {ratingRows.map((row) => {
                    const ratingNumber = Number(row.rating);
                    return (
                      <div key={row.rating} className="space-y-1">
                        <div className="flex items-center justify-between gap-3 text-sm">
                          <div className="flex items-center gap-1.5 font-medium">
                            <Star
                              className={`h-3.5 w-3.5 fill-current ${ratingColor(ratingNumber)}`}
                            />
                            {row.rating}
                          </div>
                          <Badge variant="outline" className="tabular-nums">
                            {row.value}
                          </Badge>
                        </div>
                        <div className="h-2 overflow-hidden rounded-full bg-muted">
                          <div
                            className={`h-full rounded-full ${
                              ratingNumber <= 2
                                ? "bg-destructive"
                                : ratingNumber === 3
                                  ? "bg-warning"
                                  : "bg-success"
                            }`}
                            style={{
                              width: `${Math.max(5, Math.round((row.value / maxRating) * 100))}%`,
                            }}
                          />
                        </div>
                      </div>
                    );
                  })}
                </div>
                <div className="mt-3 rounded-md bg-muted/40 px-3 py-2 text-[11px] text-muted-foreground">
                  Низкие оценки и ручные категории должны попадать в очередь
                  оператора первыми.
                </div>
              </div>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}

function DebugBlock({ title, value }: { title: string; value: unknown }) {
  return (
    <div className="rounded-md border bg-background">
      <div className="border-b px-3 py-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        {title}
      </div>
      <pre className="max-h-80 overflow-auto whitespace-pre-wrap p-3 text-xs leading-relaxed">
        {formatDebugValue(value)}
      </pre>
    </div>
  );
}

function ReputationAdminDebugPanel({
  accountId,
}: {
  accountId: number | null | undefined;
}) {
  const [itemId, setItemId] = useState("");
  const [selectedLogId, setSelectedLogId] = useState<string | null>(null);
  const providerQ = useQuery({
    queryKey: ["portal", "reputation", "admin", "provider", accountId],
    queryFn: () => fetchReputationAdminProviderStatus(accountId),
    enabled: !!accountId,
    staleTime: 30_000,
  });
  const logsQ = useQuery({
    queryKey: ["portal", "reputation", "admin", "generation-logs", accountId],
    queryFn: () =>
      fetchReputationAdminGenerationLogs(accountId, { limit: 50, offset: 0 }),
    enabled: !!accountId,
    staleTime: 30_000,
  });
  const detailQ = useQuery({
    queryKey: [
      "portal",
      "reputation",
      "admin",
      "generation-log",
      accountId,
      selectedLogId,
    ],
    queryFn: () =>
      fetchReputationAdminGenerationLogDetail(accountId, selectedLogId ?? ""),
    enabled: !!accountId && !!selectedLogId,
    staleTime: 30_000,
  });
  const promptQ = useQuery({
    queryKey: [
      "portal",
      "reputation",
      "admin",
      "prompt-debug",
      accountId,
      itemId,
    ],
    queryFn: () => fetchReputationAdminPromptDebug(accountId, itemId.trim()),
    enabled: !!accountId && !!itemId.trim(),
    staleTime: 15_000,
  });
  const probeM = useMutation({
    mutationFn: () =>
      probeReputationAdminPrompt(accountId, itemId.trim(), { dry_run: true }),
    onSuccess: () =>
      toast.success("Проба промпта выполнена без обращения к провайдеру"),
    onError: (e: Error) => toast.error(e.message),
  });

  const provider = isRecord(providerQ.data) ? providerQ.data : {};
  const logs =
    isRecord(logsQ.data) && Array.isArray(logsQ.data.items)
      ? logsQ.data.items.filter(isRecord)
      : [];
  const firstLogId = logs.length ? String(logs[0].id ?? "") : null;
  const detail = isRecord(detailQ.data) ? detailQ.data : {};
  const prompt = isRecord(promptQ.data) ? promptQ.data : {};

  useEffect(() => {
    if (!selectedLogId && firstLogId) {
      setSelectedLogId(firstLogId);
    }
  }, [firstLogId, selectedLogId]);

  return (
    <div className="grid gap-4 xl:grid-cols-[420px_1fr]">
      <div className="space-y-4">
        <Card>
          <CardContent className="space-y-3 p-4">
            <div className="flex items-center justify-between gap-2">
              <div>
                <div className="text-sm font-semibold">Статус провайдера</div>
                <div className="text-xs text-muted-foreground">
                  Прогон без сети: провайдер не проверяется в реальном времени.
                </div>
              </div>
              <Badge
                variant={provider.provider_configured ? "outline" : "secondary"}
              >
                {provider.provider_configured ? "настроен" : "не настроен"}
              </Badge>
            </div>
            <div className="grid grid-cols-2 gap-2 text-xs">
              <MetaCell
                label="Рантайм"
                value={getString(provider.runtime_mode)}
              />
              <MetaCell
                label="Провайдер"
                value={getString(provider.provider)}
              />
              <MetaCell label="Модель" value={getString(provider.model)} />
              <MetaCell
                label="Живой проб"
                value={provider.live_probe_enabled ? "включен" : "выключен"}
              />
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="space-y-3 p-4">
            <div>
              <div className="text-sm font-semibold">
                Контекст отладки промпта
              </div>
              <div className="text-xs text-muted-foreground">
                Введите `review:...`, `question:...` или `chat:...`.
              </div>
            </div>
            <div className="flex gap-2">
              <Input
                value={itemId}
                placeholder="review:feedback-id"
                onChange={(event) => setItemId(event.target.value)}
              />
              <Button
                type="button"
                variant="outline"
                disabled={!itemId.trim() || probeM.isPending}
                onClick={() => probeM.mutate()}
              >
                Прогнать
              </Button>
            </div>
            {promptQ.isFetching && <Skeleton className="h-16 w-full" />}
            {prompt.status && (
              <Badge variant={prompt.status === "ok" ? "outline" : "secondary"}>
                {getString(prompt.status)}
              </Badge>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-0">
            <div className="border-b px-4 py-3">
              <div className="text-sm font-semibold">Логи генерации</div>
              <div className="text-xs text-muted-foreground">
                Сохранённые черновики и трассы репутации.
              </div>
            </div>
            <div className="max-h-[520px] overflow-y-auto">
              {logsQ.isLoading ? (
                <div className="space-y-2 p-3">
                  <Skeleton className="h-14 w-full" />
                  <Skeleton className="h-14 w-full" />
                </div>
              ) : logs.length ? (
                logs.map((log) => {
                  const id = String(log.id ?? "");
                  return (
                    <button
                      key={id}
                      type="button"
                      className={`w-full border-b px-4 py-3 text-left text-sm hover:bg-muted/40 ${
                        selectedLogId === id ? "bg-primary/5" : ""
                      }`}
                      onClick={() => setSelectedLogId(id)}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className="font-medium">
                          #{id} · {getString(log.entity_wb_id) ?? "черновик"}
                        </span>
                        <Badge variant="outline" className="text-[10px]">
                          {humanizeStatus(getString(log.status) ?? "new")}
                        </Badge>
                      </div>
                      <div className="mt-1 text-xs text-muted-foreground">
                        {getString(log.source) ?? "неизвестный источник"} ·{" "}
                        {getString(log.provider) ?? "локальный"} ·{" "}
                        {compactDate(log.updated_at)}{" "}
                        {compactTime(log.updated_at)}
                      </div>
                    </button>
                  );
                })
              ) : (
                <div className="p-4 text-sm text-muted-foreground">
                  Логи генерации пока отсутствуют.
                </div>
              )}
            </div>
          </CardContent>
        </Card>
      </div>

      <div className="space-y-4">
        <Card>
          <CardContent className="space-y-3 p-4">
            <div className="text-sm font-semibold">Выбранная трасса</div>
            {detailQ.isFetching ? (
              <Skeleton className="h-72 w-full" />
            ) : selectedLogId && detail.status === "ok" ? (
              <>
                <div className="grid gap-2 md:grid-cols-4">
                  <MetaCell
                    label="Провайдер"
                    value={getString(detail.provider)}
                  />
                  <MetaCell label="Модель" value={getString(detail.model)} />
                  <MetaCell
                    label="Заблокировано"
                    value={getString(detail.blocked_reason)}
                  />
                  <MetaCell
                    label="Резерв"
                    value={getString(detail.fallback_reason)}
                  />
                </div>
                <DebugBlock title="Инструкции" value={detail.instructions} />
                <DebugBlock title="Входной текст" value={detail.input_text} />
                <DebugBlock title="Отчёт отладки" value={detail.debug_report} />
              </>
            ) : (
              <div className="rounded-md border border-dashed p-6 text-center text-sm text-muted-foreground">
                Выберите лог генерации.
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardContent className="space-y-3 p-4">
            <div className="text-sm font-semibold">Контекст промпта</div>
            {promptQ.isFetching ? (
              <Skeleton className="h-72 w-full" />
            ) : prompt.status === "ok" ? (
              <>
                <div className="grid gap-2 md:grid-cols-3">
                  <MetaCell
                    label="Элемент"
                    value={getString(getRecordValue(prompt.item, "id"))}
                  />
                  <MetaCell
                    label="Оценка"
                    value={getString(
                      getRecordValue(prompt.classification, "need_reply_score"),
                    )}
                  />
                  <MetaCell
                    label="Ручной"
                    value={
                      getRecordValue(
                        prompt.classification,
                        "requires_manual_attention",
                      )
                        ? "да"
                        : "нет"
                    }
                  />
                </div>
                <DebugBlock title="Инструкции" value={prompt.instructions} />
                <DebugBlock title="Входной текст" value={prompt.input_text} />
                <DebugBlock
                  title="Классификация"
                  value={prompt.classification}
                />
              </>
            ) : (
              <div className="rounded-md border border-dashed p-6 text-center text-sm text-muted-foreground">
                Введите id элемента для просмотра контекста промпта.
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function ReputationPage() {
  const { activeId } = useAccounts();
  const { user } = useAuth();
  const qc = useQueryClient();
  const visible = useModuleVisible("reputation");
  const moduleStatus = useModuleStatus("reputation");
  const { status, message } = moduleStatus;
  const routeSearch = Route.useSearch();
  const routeNmId = normalizeRouteNmId(routeSearch.nm_id);
  const routeTab = routeSearch.tab ?? "reviews";
  const [filters, setFilters] = useState<InboxFilters>(() => ({
    ...DEFAULT_INBOX_FILTERS,
    nmId: routeNmId,
  }));
  const [activeTab, setActiveTab] = useState(routeTab);
  const [activeItemKey, setActiveItemKey] = useState<string | null>(null);
  const [forceAiForDraft, setForceAiForDraft] = useState(false);
  const isSuperuser = !!user?.is_superuser;

  useEffect(() => {
    setFilters((current) =>
      current.nmId === routeNmId ? current : { ...current, nmId: routeNmId },
    );
    setActiveItemKey(null);
  }, [routeNmId]);

  const invalidateReputation = () => {
    qc.invalidateQueries({ queryKey: ["portal", "reputation"] });
    qc.invalidateQueries({ queryKey: ["portal", "results"] });
  };

  const summaryQ = useQuery({
    queryKey: ["portal", "reputation", "summary", activeId],
    queryFn: () => fetchReputationSummary(activeId),
    enabled: visible && !!activeId,
    staleTime: 60_000,
  });
  const settingsQ = useQuery({
    queryKey: ["portal", "reputation", "settings", activeId],
    queryFn: () => fetchReputationSettings(activeId),
    enabled: visible && !!activeId,
    staleTime: 60_000,
  });
  const brandsQ = useQuery({
    queryKey: ["portal", "reputation", "brands", activeId],
    queryFn: () => fetchReputationBrands(activeId),
    enabled: visible && !!activeId && activeTab === "settings",
    staleTime: 10 * 60_000,
  });

  const summaryData = isRecord(summaryQ.data) ? summaryQ.data : {};
  const settingsData = isRecord(settingsQ.data) ? settingsQ.data : {};
  const summaryStatus = getString(summaryData.status);
  const settingsStatus = getString(settingsData.status);
  const runtimeMode =
    getString(settingsData.runtime_mode) ??
    getString(summaryData.runtime_mode) ??
    moduleStatus.runtime_mode ??
    null;
  const moduleRuntimeMode = moduleStatus.runtime_mode ?? null;
  const hasRuntimeSplit = Boolean(
    moduleRuntimeMode && runtimeMode && moduleRuntimeMode !== runtimeMode,
  );
  const dangerousActionsEnabled =
    settingsData.dangerous_actions_enabled === true ||
    summaryData.dangerous_actions_enabled === true ||
    moduleStatus.dangerous_actions_enabled;
  const publishFlagEnabled =
    settingsData.publish_enabled === true ||
    summaryData.publish_enabled === true ||
    moduleStatus.publish_enabled;
  const autoPublishEnabled =
    settingsData.auto_publish_enabled === true ||
    summaryData.auto_publish_enabled === true ||
    moduleStatus.auto_publish_enabled;
  const chatSendEnabled =
    settingsData.chat_send_enabled === true ||
    summaryData.chat_send_enabled === true ||
    moduleStatus.chat_send_enabled;
  const isDisabled =
    !visible ||
    status === "disabled" ||
    status === "not_configured" ||
    summaryStatus === "disabled" ||
    settingsStatus === "disabled" ||
    settingsData.enabled === false;

  const tabItemType =
    activeTab === "reviews"
      ? "review"
      : activeTab === "questions"
        ? "question"
        : activeTab === "chats"
          ? "chat"
          : null;
  const inboxEnabled = ["reviews", "questions"].includes(activeTab);
  const chatsEnabled = activeTab === "chats";
  const nmIdQuery = filters.nmId.trim()
    ? { nm_id: Number(filters.nmId.trim()) }
    : {};
  const inboxQuery = {
    ...(tabItemType
      ? { item_type: tabItemType }
      : filters.itemType !== "all"
        ? { item_type: filters.itemType }
        : {}),
    ...(filters.status !== "all" ? { status: filters.status } : {}),
    ...(filters.rating !== "all" ? { rating: Number(filters.rating) } : {}),
    ...(filters.sentiment !== "all" ? { sentiment: filters.sentiment } : {}),
    ...(filters.priority !== "all" ? { priority: filters.priority } : {}),
    ...nmIdQuery,
    ...(filters.dateFrom ? { date_from: filters.dateFrom } : {}),
    ...(filters.dateTo ? { date_to: filters.dateTo } : {}),
  };

  const inboxQ = useQuery({
    queryKey: ["portal", "reputation", "inbox", activeId, activeTab, filters],
    queryFn: () => fetchReputationInbox(activeId, inboxQuery),
    enabled: !isDisabled && !!activeId && inboxEnabled,
    staleTime: 60_000,
  });
  const chatsQ = useQuery({
    queryKey: ["portal", "reputation", "chats", activeId, filters],
    queryFn: () =>
      fetchReputationChats(activeId, {
        limit: 50,
        offset: 0,
        ...nmIdQuery,
      }),
    enabled: !isDisabled && !!activeId && chatsEnabled,
    staleTime: 60_000,
  });
  const draftsQ = useQuery({
    queryKey: ["portal", "reputation", "drafts", activeId, filters.nmId],
    queryFn: () =>
      fetchReputationDrafts(activeId, {
        limit: 100,
        offset: 0,
        ...nmIdQuery,
      }),
    enabled: !isDisabled && !!activeId && activeTab === "drafts",
    staleTime: 60_000,
  });
  const analyticsQ = useQuery({
    queryKey: ["portal", "reputation", "analytics", activeId, filters.nmId],
    queryFn: () =>
      fetchReputationAnalytics(activeId, {
        granularity: "day",
        ...nmIdQuery,
      }),
    enabled: !isDisabled && !!activeId && activeTab === "analytics",
    staleTime: 60_000,
  });
  const learningQ = useQuery({
    queryKey: ["portal", "reputation", "learning", activeId],
    queryFn: () => fetchReputationLearning(activeId),
    enabled: !isDisabled && !!activeId && activeTab === "settings",
    staleTime: 60_000,
  });

  const syncM = useMutation({
    mutationFn: () => syncReputation(activeId),
    onSuccess: () => {
      toast.success("Синхронизация запущена");
      invalidateReputation();
    },
    onError: (e: Error) => toast.error(e.message),
  });
  const draftM = useMutation({
    mutationFn: ({ itemId, forceAi }: { itemId: string; forceAi: boolean }) =>
      createReputationDraft(itemId, activeId, { force_ai: forceAi }),
    onSuccess: () => {
      toast.success("Черновик создан");
      invalidateReputation();
    },
    onError: (e: Error) => toast.error(e.message),
  });
  const approveM = useMutation({
    mutationFn: (draftId: string) => approveReputationDraft(draftId, activeId),
    onSuccess: (result: unknown) => {
      const payload = isRecord(result) ? result : {};
      const warnings = Array.isArray(payload.warnings) ? payload.warnings : [];
      if (warnings.length > 0)
        toast.warning("Черновик одобрен, публикация требует проверки");
      else toast.success("Черновик одобрен и обработан");
      invalidateReputation();
    },
    onError: (e: Error) => toast.error(e.message),
  });
  const approveAllM = useMutation({
    mutationFn: () => approveAllReputationDrafts(activeId),
    onSuccess: (result: unknown) => {
      const payload = isRecord(result) ? result : {};
      const published = getNumber(payload.published_count);
      toast.success(
        published && published > 0
          ? `Опубликовано: ${published}`
          : "Черновики одобрены",
      );
      invalidateReputation();
    },
    onError: (e: Error) => toast.error(e.message),
  });
  const regenerateM = useMutation({
    mutationFn: ({ draftId, forceAi }: { draftId: string; forceAi: boolean }) =>
      regenerateReputationDraft(draftId, activeId, {
        reason: "operator_regenerate",
        payload: { force_ai: forceAi },
      }),
    onSuccess: () => {
      toast.success("Черновик перегенерирован");
      invalidateReputation();
    },
    onError: (e: Error) => toast.error(e.message),
  });
  const rejectM = useMutation({
    mutationFn: (draftId: string) =>
      rejectReputationDraft(draftId, activeId, { reason: "operator_reject" }),
    onSuccess: () => {
      toast.success("Черновик отклонён локально");
      invalidateReputation();
    },
    onError: (e: Error) => toast.error(e.message),
  });
  const noReplyM = useMutation({
    mutationFn: (itemId: string) =>
      markReputationNoReply(itemId, activeId, {
        confirm: true,
        reason: "operator_no_reply_needed",
      }),
    onSuccess: () => {
      toast.success("Элемент закрыт: ответ не требуется");
      invalidateReputation();
    },
    onError: (e: Error) => toast.error(e.message),
  });
  const publishM = useMutation({
    mutationFn: ({
      draftId,
      text,
    }: {
      draftId: string;
      text?: string | null;
    }) => publishReputationDraft(draftId, activeId, { confirm: true, text }),
    onSuccess: (result: unknown) => {
      const payload = isRecord(result) ? result : {};
      if (payload.success === false)
        toast.warning(
          getString(payload.title) ?? "Публикация в WB заблокирована",
        );
      else toast.success("Опубликовано в WB");
      invalidateReputation();
    },
    onError: (e: Error) => toast.error(e.message),
  });
  const settingsM = useMutation({
    mutationFn: (payload: Record<string, unknown>) =>
      updateReputationSettings(activeId, payload),
    onSuccess: () => {
      toast.success("Настройки сохранены");
      invalidateReputation();
    },
    onError: (e: Error) => toast.error(e.message),
  });
  const learningToggleM = useMutation({
    mutationFn: (enabled: boolean) =>
      toggleReputationLearning(activeId, enabled),
    onSuccess: () => {
      toast.success("Обучение обновлено");
      invalidateReputation();
    },
    onError: (e: Error) => toast.error(e.message),
  });
  const promptsM = useMutation({
    mutationFn: (payload: Record<string, unknown>) =>
      updateReputationPrompts(activeId, payload),
    onSuccess: () => {
      toast.success("Промпты сохранены");
      invalidateReputation();
    },
    onError: (e: Error) => toast.error(e.message),
  });
  const learningApplyM = useMutation({
    mutationFn: (payload: Record<string, unknown>) =>
      applyReputationLearning(activeId, payload),
    onSuccess: () => {
      toast.success("Правило обучения добавлено");
      invalidateReputation();
    },
    onError: (e: Error) => toast.error(e.message),
  });
  const learningDeleteM = useMutation({
    mutationFn: (entryId: number | string) =>
      deleteReputationLearningEntry(activeId, entryId),
    onSuccess: () => {
      toast.success("Правило отключено");
      invalidateReputation();
    },
    onError: (e: Error) => toast.error(e.message),
  });
  const learningResetM = useMutation({
    mutationFn: () => resetReputationLearning(activeId),
    onSuccess: () => {
      toast.success("Обучение сброшено");
      invalidateReputation();
    },
    onError: (e: Error) => toast.error(e.message),
  });

  if (!activeId) {
    return (
      <PageShell>
        <PageHeader title="Репутация" />
        <NoAccountSelected />
      </PageShell>
    );
  }

  if (isDisabled) {
    const sourcesValue =
      summaryData.unavailable_sources ?? settingsData.unavailable_sources;
    const warningsValue = summaryData.warnings ?? settingsData.warnings;
    const sources = Array.isArray(sourcesValue) ? sourcesValue : undefined;
    const warnings = Array.isArray(warningsValue) ? warningsValue : undefined;
    return (
      <PageShell>
        <PageHeader
          title="Репутация"
          description={
            <div className="flex items-center gap-2 flex-wrap">
              <Badge variant="outline" className="text-[10px]">
                {humanizeStatus("disabled")}
              </Badge>
              <Badge variant="outline" className="text-[10px]">
                {humanizeRuntimeMode(runtimeMode)}
              </Badge>
              {hasRuntimeSplit && (
                <Badge variant="secondary" className="text-[10px]">
                  Здоровье:{" "}
                  {humanizeRuntimeMode(moduleRuntimeMode).replace(
                    "Рантайм: ",
                    "",
                  )}
                </Badge>
              )}
            </div>
          }
        />
        <DisabledCard
          message={message ?? getString(summaryData.message)}
          sources={sources}
          warnings={warnings}
        />
      </PageShell>
    );
  }

  const publishEnabled = publishFlagEnabled;
  const activeInboxData = activeTab === "chats" ? chatsQ.data : inboxQ.data;
  const activeInboxQ = activeTab === "chats" ? chatsQ : inboxQ;
  const rawInbox = Array.isArray(activeInboxData)
    ? activeInboxData
    : isRecord(activeInboxData) && Array.isArray(activeInboxData.items)
      ? activeInboxData.items
      : [];
  const inbox = rawInbox
    .filter(isRecord)
    .filter((item) => reputationItemMatchesNmId(item, filters.nmId));
  const inboxTotal =
    isRecord(activeInboxData) && typeof activeInboxData.total === "number"
      ? activeInboxData.total
      : inbox.length;
  const draftsData = isRecord(draftsQ.data) ? draftsQ.data : {};
  const draftItems = Array.isArray(draftsData.items)
    ? draftsData.items
        .filter(isRecord)
        .filter((item) => reputationItemMatchesNmId(item, filters.nmId))
    : [];
  const draftTotal =
    typeof draftsData.total === "number" ? draftsData.total : draftItems.length;
  const analyticsData = isRecord(analyticsQ.data) ? analyticsQ.data : {};
  const brandsData = isRecord(brandsQ.data) ? brandsQ.data : {};
  const availableBrands = Array.isArray(brandsData.brands)
    ? brandsData.brands
        .map((brand) => normalizeSignatureBrand(brand))
        .filter((brand) => brand.toLowerCase() !== "all")
    : [];

  return (
    <PageShell>
      <PageHeader
        title="Репутация"
        description={
          <ReputationStatusHeader
            status={status}
            runtimeMode={runtimeMode}
            moduleRuntimeMode={moduleRuntimeMode}
            hasRuntimeSplit={hasRuntimeSplit}
            dangerousActionsEnabled={dangerousActionsEnabled}
            publishEnabled={publishEnabled}
            autoPublishEnabled={autoPublishEnabled}
            chatSendEnabled={chatSendEnabled}
          />
        }
        actions={
          activeTab === "settings" || activeTab === "analytics" ? (
            <Button
              size="sm"
              variant="outline"
              onClick={() => syncM.mutate()}
              disabled={syncM.isPending}
            >
              {syncM.isPending ? "Синхронизация…" : "Синхронизировать"}
            </Button>
          ) : null
        }
      />
      <DataDependencyNotice
        accountId={activeId}
        domains={["reputation", "buyer_chat", "product_cards"]}
      />
      {summaryQ.error && (
        <Alert variant="destructive" className="mb-4">
          <AlertTriangle className="h-4 w-4" />
          <AlertDescription>
            {(summaryQ.error as Error).message}
          </AlertDescription>
        </Alert>
      )}

      <Tabs
        value={activeTab}
        onValueChange={(value) => {
          setActiveTab(value);
          setActiveItemKey(null);
        }}
        className="mb-3"
      >
        <div className="-mx-1 overflow-x-auto px-1 pb-1">
          <TabsList className="flex h-10 min-w-max justify-start gap-1 rounded-lg bg-muted/70 p-1 md:w-full md:min-w-0">
            <TabsTrigger
              value="reviews"
              className="h-8 shrink-0 gap-1.5 px-3 text-xs sm:text-sm"
            >
              <Star className="h-3.5 w-3.5" />
              Отзывы
            </TabsTrigger>
            <TabsTrigger
              value="questions"
              className="h-8 shrink-0 gap-1.5 px-3 text-xs sm:text-sm"
            >
              <Info className="h-3.5 w-3.5" />
              Вопросы
            </TabsTrigger>
            <TabsTrigger
              value="chats"
              className="h-8 shrink-0 gap-1.5 px-3 text-xs sm:text-sm"
            >
              <MessageSquare className="h-3.5 w-3.5" />
              Чаты
            </TabsTrigger>
            <TabsTrigger
              value="drafts"
              className="h-8 shrink-0 gap-1.5 px-3 text-xs sm:text-sm"
            >
              <FileText className="h-3.5 w-3.5" />
              Черновики
            </TabsTrigger>
            <TabsTrigger
              value="analytics"
              className="h-8 shrink-0 gap-1.5 px-3 text-xs sm:text-sm"
            >
              <BarChart3 className="h-3.5 w-3.5" />
              Аналитика
            </TabsTrigger>
            <TabsTrigger
              value="settings"
              className="h-8 shrink-0 gap-1.5 px-3 text-xs sm:text-sm"
            >
              <Settings2 className="h-3.5 w-3.5" />
              Настройки
            </TabsTrigger>
            {isSuperuser && (
              <TabsTrigger
                value="debug"
                className="h-8 shrink-0 gap-1.5 px-3 text-xs sm:text-sm"
              >
                <Brain className="h-3.5 w-3.5" />
                Debug
              </TabsTrigger>
            )}
          </TabsList>
        </div>
        <TabsContent value={activeTab} className="mt-0" />
      </Tabs>

      {activeTab === "settings" &&
        (settingsQ.isLoading ? (
          <Skeleton className="h-48 w-full mb-4" />
        ) : (
          <ReputationSettingsSections
            settings={settingsQ.data}
            learning={learningQ.data}
            availableBrands={availableBrands}
            brandsLoading={brandsQ.isLoading}
            brandsError={brandsQ.error}
            disabled={
              settingsM.isPending ||
              learningToggleM.isPending ||
              promptsM.isPending ||
              learningApplyM.isPending ||
              learningDeleteM.isPending ||
              learningResetM.isPending
            }
            onUpdate={(payload) => settingsM.mutate(payload)}
            onToggleLearning={(enabled) => learningToggleM.mutate(enabled)}
            onUpdatePrompts={(payload) => promptsM.mutate(payload)}
            onApplyLearning={(payload) => learningApplyM.mutate(payload)}
            onDeleteLearningEntry={(entryId) => learningDeleteM.mutate(entryId)}
            onResetLearning={() => learningResetM.mutate()}
          />
        ))}

      {activeTab === "analytics" && (
        <ReputationAnalyticsPanel
          data={analyticsData}
          loading={analyticsQ.isLoading}
          error={analyticsQ.error}
        />
      )}

      {activeTab === "debug" && isSuperuser && (
        <ReputationAdminDebugPanel accountId={activeId} />
      )}

      {activeTab === "drafts" && (
        <ReputationDraftsWorkspace
          drafts={draftItems}
          total={draftTotal}
          loading={draftsQ.isLoading}
          error={draftsQ.error}
          approveAllPending={approveAllM.isPending}
          pending={{
            approve: approveM.isPending,
            regenerate: regenerateM.isPending,
            reject: rejectM.isPending,
          }}
          forceAiForDraft={forceAiForDraft}
          publishEnabled={publishEnabled}
          onApproveAll={() => approveAllM.mutate()}
          onApprove={(draftId) => approveM.mutate(draftId)}
          onRegenerate={(draftId, forceAi) =>
            regenerateM.mutate({ draftId, forceAi })
          }
          onReject={(draftId) => rejectM.mutate(draftId)}
        />
      )}

      {["reviews", "questions", "chats"].includes(activeTab) && (
        <ReputationWorkspace
          activeTab={activeTab}
          accountId={activeId}
          items={inbox}
          total={inboxTotal}
          loading={activeInboxQ.isLoading}
          fetching={activeInboxQ.isFetching}
          error={activeInboxQ.error}
          filters={filters}
          onFiltersChange={(patch) =>
            setFilters((current) => ({ ...current, ...patch }))
          }
          onResetFilters={() =>
            setFilters({ ...DEFAULT_INBOX_FILTERS, nmId: routeNmId })
          }
          onSync={() => syncM.mutate()}
          syncing={syncM.isPending}
          activeItemKey={activeItemKey}
          onActiveItemChange={setActiveItemKey}
          publishEnabled={publishEnabled}
          chatSendEnabled={chatSendEnabled}
          pending={{
            draft: draftM.isPending,
            regenerate: regenerateM.isPending,
            approve: approveM.isPending,
            reject: rejectM.isPending,
            noReply: noReplyM.isPending,
            publish: publishM.isPending,
          }}
          forceAiForDraft={forceAiForDraft}
          onForceAiChange={setForceAiForDraft}
          onCreateDraft={(itemId, forceAi) =>
            draftM.mutate({ itemId, forceAi })
          }
          onRegenerate={(draftId, forceAi) =>
            regenerateM.mutate({ draftId, forceAi })
          }
          onApprove={(draftId) => approveM.mutate(draftId)}
          onReject={(draftId) => rejectM.mutate(draftId)}
          onNoReply={(itemId) => noReplyM.mutate(itemId)}
          onPublish={(draftId, text) =>
            publishM.mutate({
              draftId,
              text,
            })
          }
        />
      )}
    </PageShell>
  );
}
