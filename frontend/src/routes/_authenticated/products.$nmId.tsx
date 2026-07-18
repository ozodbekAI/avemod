// @ts-nocheck
import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import type { ReactNode } from "react";
import { useAccounts } from "@/lib/account-context";
import { useDateRange } from "@/lib/date-range-context";
import {
  fetchProduct360,
  analyzeProductCardQuality,
  updateCardQualityIssueStatus,
  updateActionBySource,
  updateActionById,
  type PortalAction,
} from "@/lib/portal";
import { PageShell, PageHeader } from "@/components/PageShell";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Skeleton } from "@/components/ui/skeleton";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { EvidenceButton, EvidenceDrawer } from "@/components/EvidenceDrawer";
import { MoneyTrustBadge } from "@/components/MoneyTrustBadge";
import { EndpointError } from "@/components/EndpointError";
import { NoAccountSelected } from "@/components/portal/NoAccountSelected";
import {
  AlertTriangle,
  BadgeDollarSign,
  BarChart3,
  Boxes,
  CalendarClock,
  ChevronLeft,
  ChevronDown,
  CircleDollarSign,
  ClipboardCheck,
  Edit3,
  ImageOff,
  Sparkles,
  ArrowRight,
  Camera,
  CheckCircle2,
  ExternalLink,
  FileText,
  ListChecks,
  Megaphone,
  PackageSearch,
  Percent,
  Plus,
  ReceiptText,
  Save,
  Send,
  Tag,
  TrendingDown,
  TrendingUp,
  Truck,
  ShieldCheck,
  Star,
  Trash2,
  Wand2,
  Workflow,
} from "lucide-react";
import { formatMoney } from "@/lib/format";
import { cn } from "@/lib/utils";
import { NullValue } from "@/components/money/NullValue";
import { humanizeModuleMessage } from "@/lib/copy";
import { MoneyWaterfall } from "@/components/money/MoneyWaterfall";
import { toast } from "sonner";
import { isSystemHandledCode } from "@/lib/owner-ux";
import { evidenceFrom, type EvidenceLedger } from "@/lib/evidence";
import { isSellerVisibleMoneyTrust, moneyTrustFrom } from "@/lib/money-trust";
import { DataDependencyNotice } from "@/components/data-health/DataCoveragePanel";
import { ProductDoctorSection } from "@/components/portal/ProductDoctorSection";
import { ProductHealthSummary } from "@/components/portal/ProductHealthSummary";
import { ProductHeaderCard } from "@/components/portal/ProductHeaderCard";
import { ActionCenterReturnLink } from "@/components/action-center/ActionCenterReturnLink";
import { appendActionCenterProblemHistory } from "@/lib/action-center-task-history";
import { routeSearchText } from "@/lib/action-center-routing";

// ─── Wildberries CDN image fallback ───────────────────────────────────
// Backend identity.image is often missing for live SKUs; reconstruct the
// canonical WB basket URL and try a few extensions before showing the
// "no image" placeholder.
function wbBasketHost(vol: number): string {
  const ranges: Array<[number, number, string]> = [
    [0, 143, "01"],
    [144, 287, "02"],
    [288, 431, "03"],
    [432, 719, "04"],
    [720, 1007, "05"],
    [1008, 1061, "06"],
    [1062, 1115, "07"],
    [1116, 1169, "08"],
    [1170, 1313, "09"],
    [1314, 1601, "10"],
    [1602, 1655, "11"],
    [1656, 1919, "12"],
    [1920, 2045, "13"],
    [2046, 2189, "14"],
    [2190, 2405, "15"],
    [2406, 2621, "16"],
    [2622, 2837, "17"],
    [2838, 3053, "18"],
    [3054, 3269, "19"],
    [3270, 3485, "20"],
    [3486, 3701, "21"],
    [3702, 3917, "22"],
    [3918, 4133, "23"],
    [4134, 4349, "24"],
    [4350, 4565, "25"],
    [4566, 4877, "26"],
    [4878, 5193, "27"],
    [5194, 5509, "28"],
    [5510, 5825, "29"],
    [5826, 6141, "30"],
  ];
  for (const [a, b, host] of ranges) if (vol >= a && vol <= b) return host;
  return "30";
}
function wbImageCandidates(nmId: string | number): string[] {
  const n = Number(nmId);
  if (!Number.isFinite(n) || n <= 0) return [];
  const vol = Math.floor(n / 1e5);
  const part = Math.floor(n / 1e3);
  const host = wbBasketHost(vol);
  const base = `https://basket-${host}.wbbasket.ru/vol${vol}/part${part}/${n}/images/big`;
  return [`${base}/1.webp`, `${base}/1.jpg`];
}

function ProductImage({
  src,
  nmId,
  alt,
  className,
}: {
  src?: string | null;
  nmId: string | number;
  alt: string;
  className?: string;
}) {
  const candidates = [src, ...wbImageCandidates(nmId)].filter(
    Boolean,
  ) as string[];
  const [idx, setIdx] = useState(0);
  const [loaded, setLoaded] = useState(false);
  if (candidates.length === 0 || idx >= candidates.length) {
    return (
      <div
        className={cn(
          "flex aspect-square w-full flex-col items-center justify-center rounded border bg-muted text-muted-foreground",
          className,
        )}
      >
        <ImageOff className="h-6 w-6 mb-1" />
        <span className="text-[10px] leading-none">Нет фото</span>
      </div>
    );
  }
  return (
    <div
      className={cn(
        "relative aspect-square w-full overflow-hidden rounded border bg-muted",
        className,
      )}
      aria-label={alt}
    >
      {!loaded ? (
        <div className="absolute inset-0 flex flex-col items-center justify-center text-muted-foreground">
          <ImageOff className="h-6 w-6" />
        </div>
      ) : null}
      <img
        key={candidates[idx]}
        src={candidates[idx]}
        alt=""
        className={cn(
          "absolute inset-0 h-full w-full object-cover transition-opacity",
          loaded ? "opacity-100" : "opacity-0",
        )}
        loading="lazy"
        onLoad={() => setLoaded(true)}
        onError={() => {
          setLoaded(false);
          setIdx((i) => i + 1);
        }}
      />
    </div>
  );
}

type Product360Search = {
  tab?: "price" | "promo";
  problem_instance_id?: string;
};

export const Route = createFileRoute("/_authenticated/products/$nmId")({
  component: Product360Page,
  validateSearch: (s: Record<string, unknown>): Product360Search => ({
    tab: s.tab === "price" || s.tab === "promo" ? s.tab : undefined,
    problem_instance_id: routeSearchText(s.problem_instance_id),
  }),
  errorComponent: ProductRouteError,
});

function ProductRouteError({
  error,
  reset,
}: {
  error: unknown;
  reset: () => void;
}) {
  return <EndpointError error={error} reset={reset} />;
}

// ─── helpers ──────────────────────────────────────────────────────────
function pick<T = any>(obj: any, keys: string[]): T | undefined {
  if (!obj) return undefined;
  for (const k of keys) {
    const v = obj[k];
    if (v != null) return v as T;
  }
  return undefined;
}
/**
 * Backend wraps every Product 360 section as `{status, data, message}`.
 * sectionData() peels that wrapper and returns the inner data, or the value
 * itself when the backend hasn't wrapped it (forward compat).
 */
function sectionData<T = any>(section: any): T | null {
  if (section == null) return null;
  if (typeof section === "object" && "data" in section)
    return (section.data ?? null) as T | null;
  return section as T;
}
function sectionStatus(section: any): string | null {
  if (
    section &&
    typeof section === "object" &&
    typeof section.status === "string"
  )
    return section.status;
  return null;
}
function sectionMessage(section: any): string | null {
  if (
    section &&
    typeof section === "object" &&
    typeof section.message === "string"
  )
    return section.message;
  return null;
}
/**
 * Derive a section's visible status. Forces "blocked"/"warning" when the
 * payload lists blockers/warnings, even if the backend reported "ok".
 */
function deriveSectionStatus(
  section: any,
  opts?: {
    blockers?: any[];
    warnings?: any[];
  },
): string | null {
  const raw = sectionStatus(section);
  const blockers = opts?.blockers ?? [];
  const warnings = opts?.warnings ?? [];
  if (blockers.length) return "blocked";
  if (warnings.length)
    return raw && raw !== "ok" && raw !== "healthy" ? raw : "warning";
  return raw;
}
/**
 * Render a metric value: shows "Нет данных" for null/undefined or untrusted
 * values instead of falling back to 0.
 */
function displayMetric(
  value: number | null | undefined,
  opts?: { trusted?: boolean },
): React.ReactNode {
  if (value === null || value === undefined || Number.isNaN(value as number)) {
    return (
      <span className="text-xs italic text-muted-foreground">Нет данных</span>
    );
  }
  if (opts && opts.trusted === false) {
    return (
      <span className="text-xs italic text-muted-foreground">Нет данных</span>
    );
  }
  return (
    <span className="tabular-nums">
      {(value as number).toLocaleString("ru-RU")}
    </span>
  );
}
const isObj = (x: any) => x && typeof x === "object" && !Array.isArray(x);
const STATUS_COLORS: Record<string, string> = {
  ok: "bg-success/15 text-success border-success/30",
  healthy: "bg-success/15 text-success border-success/30",
  empty: "bg-muted text-muted-foreground border-border",
  not_analyzed: "bg-muted text-muted-foreground border-border",
  running: "bg-warning/15 text-warning border-warning/30",
  warning: "bg-warning/15 text-warning border-warning/30",
  degraded: "bg-warning/15 text-warning border-warning/30",
  risk: "bg-warning/15 text-warning border-warning/30",
  critical: "bg-destructive/15 text-destructive border-destructive/30",
  bad: "bg-destructive/15 text-destructive border-destructive/30",
  blocked: "bg-destructive/15 text-destructive border-destructive/30",
  error: "bg-destructive/15 text-destructive border-destructive/30",
  failed: "bg-destructive/15 text-destructive border-destructive/30",
  not_configured: "bg-muted text-muted-foreground border-border",
  disabled: "bg-muted text-muted-foreground border-border",
  unavailable: "bg-muted text-muted-foreground border-border",
};
const PRIO_COLORS: Record<string, string> = {
  critical: "bg-destructive/15 text-destructive border-destructive/30",
  high: "bg-warning/15 text-warning border-warning/30",
  medium: "bg-primary/10 text-primary border-primary/30",
  low: "bg-muted text-muted-foreground border-border",
};
const STATUS_LABEL_RU: Record<string, string> = {
  ok: "В порядке",
  healthy: "Готово",
  warning: "Требует внимания",
  degraded: "Требует внимания",
  risk: "Риск",
  critical: "Критично",
  bad: "Плохо",
  blocked: "Заблокировано",
  empty: "Нет данных",
  not_analyzed: "Не анализировалось",
  running: "Идёт анализ",
  not_configured: "Не настроен",
  disabled: "Отключен",
  unavailable: "Недоступен",
  error: "Ошибка",
  failed: "Ошибка",
};

function humanizeIssueMeta(value: unknown): string {
  const raw = String(value ?? "").trim();
  const key = raw.toLowerCase();
  const map: Record<string, string> = {
    critical: "критично",
    high: "важно",
    medium: "средне",
    low: "низко",
    warning: "предупреждение",
    error: "ошибка",
    title: "название",
    description: "описание",
    photo: "фото",
    media: "медиа",
    characteristics: "характеристики",
  };
  return map[key] ?? raw.replaceAll("_", " ");
}
function formatIssueValue(value: unknown): string {
  if (value === null || value === undefined) return "нет данных";
  if (Array.isArray(value))
    return value
      .map((item) => formatIssueValue(item))
      .filter(Boolean)
      .join(", ");
  if (typeof value === "object") {
    try {
      return JSON.stringify(value);
    } catch {
      return String(value);
    }
  }
  return String(value);
}
function StatusBadge({
  value,
  fallback,
}: {
  value?: string | null;
  fallback?: string;
}) {
  if (!value)
    return fallback ? (
      <span className="text-xs text-muted-foreground">{fallback}</span>
    ) : (
      <NullValue />
    );
  const key = value.toLowerCase();
  const cls =
    STATUS_COLORS[key] ?? "bg-muted text-muted-foreground border-border";
  const label = STATUS_LABEL_RU[key] ?? value;
  return (
    <Badge variant="outline" className={`text-[10px] ${cls}`}>
      {label}
    </Badge>
  );
}

function SectionCard({
  title,
  subtitle,
  status,
  children,
  className,
  evidence,
  ...rest
}: {
  title: string;
  subtitle?: string;
  status?: string | null;
  children: React.ReactNode;
  className?: string;
  evidence?: EvidenceLedger | null;
} & Record<`data-${string}`, string | undefined>) {
  const [evidenceOpen, setEvidenceOpen] = useState(false);
  const ledger = evidenceFrom(evidence);
  const moneyTrust = moneyTrustFrom(ledger?.money_trust, ledger);
  return (
    <>
      <Card className={className} {...rest}>
        <CardContent className="p-4 space-y-3">
          <div className="flex items-start justify-between gap-2">
            <div>
              <div className="text-sm font-semibold">{title}</div>
              {subtitle && (
                <div className="text-[11px] text-muted-foreground">
                  {subtitle}
                </div>
              )}
            </div>
            <div className="flex flex-wrap items-center justify-end gap-1.5">
              {ledger ? (
                <EvidenceButton
                  ledger={ledger}
                  className="max-w-[210px]"
                  onClick={() => setEvidenceOpen(true)}
                />
              ) : null}
              {ledger ? <MoneyTrustBadge trust={moneyTrust} /> : null}
              {status && <StatusBadge value={status} />}
            </div>
          </div>
          {children}
        </CardContent>
      </Card>
      <EvidenceDrawer
        open={evidenceOpen}
        onOpenChange={setEvidenceOpen}
        ledger={ledger}
        title={title}
      />
    </>
  );
}

function KV({
  label,
  value,
  money,
  negativeRed,
}: {
  label: string;
  value: any;
  money?: boolean;
  negativeRed?: boolean;
}) {
  const rendered = (() => {
    if (value === null || value === undefined) return <NullValue />;
    if (money && typeof value === "number") {
      const cls = negativeRed && value < 0 ? "text-destructive" : "";
      return (
        <span className={`tabular-nums font-medium ${cls}`}>
          {formatMoney(value)}
        </span>
      );
    }
    if (typeof value === "number")
      return (
        <span className="tabular-nums">{value.toLocaleString("ru-RU")}</span>
      );
    if (typeof value === "boolean")
      return (
        <Badge variant="outline" className="text-[10px]">
          {value ? "да" : "нет"}
        </Badge>
      );
    return <span className="text-sm">{String(value)}</span>;
  })();
  return (
    <div className="flex justify-between gap-3 border-b border-border/50 py-1.5 last:border-0">
      <span className="text-xs text-muted-foreground">{label}</span>
      <span className="text-right">{rendered}</span>
    </div>
  );
}

function compactCount(value: number | null | undefined) {
  if (value == null || Number.isNaN(value))
    return (
      <span className="text-xs italic text-muted-foreground">Нет данных</span>
    );
  return (
    <span className="tabular-nums font-medium">
      {value.toLocaleString("ru-RU")}
    </span>
  );
}

function moduleBusinessStatus(
  rawStatus: string | null | undefined,
  state: "ok" | "attention" | "claim" | "running" | "empty",
) {
  const technical = String(rawStatus || "").toLowerCase();
  if (technical === "not_configured" || technical === "disabled")
    return "Модуль не подключён";
  if (
    technical === "unavailable" ||
    technical === "error" ||
    technical === "failed"
  )
    return "Модуль недоступен";
  if (state === "attention") return "Нужно ответить";
  if (state === "claim") return "Есть претензия";
  if (state === "running") return "Идёт тест";
  if (state === "empty") return "Нет данных";
  return "В порядке";
}

function formatDateTimeShort(value: any) {
  if (!value) return null;
  const date = new Date(value);
  if (!Number.isNaN(date.getTime()))
    return date.toLocaleString("ru-RU", {
      day: "2-digit",
      month: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  return String(value).slice(0, 16).replace("T", " ");
}

function normalizeStatusLabel(value: any) {
  const key = String(value || "").toLowerCase();
  const map: Record<string, string> = {
    ok: "в порядке",
    healthy: "готово",
    empty: "нет данных",
    new: "новые",
    reviewing: "в работе",
    in_progress: "в работе",
    accepted: "приняты",
    rejected: "отклонены",
    ignored: "пропущены",
    resolved: "закрытые",
    case_created: "кейс создан",
    candidate: "кандидат",
    submitted: "отправлено",
    running: "идёт",
    pending: "план",
    planned: "план",
    finished: "завершён",
    completed: "завершён",
    cancelled: "отменён",
    failed: "ошибка",
    unavailable: "недоступно",
    no_source_data: "нет источника",
    source_none: "нет источника",
    price_only: "цена есть, расчёта нет",
    beta: "бета",
    partial_account_level: "частично на уровне кабинета",
    account_level_logistics_partially_allocated: "частично распределено",
  };
  return map[key] ?? String(value || "без статуса").replaceAll("_", " ");
}

function expenseStatusLabel(value: any) {
  const key = String(value || "")
    .toLowerCase()
    .replace(/[\s-]+/g, "_");
  const map: Record<string, string> = {
    partial_account_level: "часть суммы пришла общим платежом",
    account_level_logistics_partially_allocated:
      "часть логистики рассчитана по общему отчету",
    wb_logistics_partially_linked_to_sku:
      "часть логистики рассчитана по общему отчету",
  };
  return map[key] ?? normalizeStatusLabel(value);
}

function countBy<T>(items: T[], getter: (item: T) => any) {
  return items.reduce<Record<string, number>>((acc, item) => {
    const key = String(getter(item) || "unknown");
    acc[key] = (acc[key] ?? 0) + 1;
    return acc;
  }, {});
}

function MiniKpi({
  label,
  value,
  money,
}: {
  label: string;
  value: any;
  money?: boolean;
}) {
  return (
    <div className="rounded border bg-background px-2.5 py-2">
      <div className="text-[11px] text-muted-foreground">{label}</div>
      <div className="mt-0.5 text-sm font-medium tabular-nums">
        {value == null ? (
          <span className="text-xs italic text-muted-foreground">
            Нет данных
          </span>
        ) : money && typeof value === "number" ? (
          formatMoney(value)
        ) : typeof value === "number" ? (
          value.toLocaleString("ru-RU")
        ) : (
          String(value)
        )}
      </div>
    </div>
  );
}

function ProductStorySection({
  data,
  nmId,
}: {
  data: any;
  accountId: number | null | undefined;
  nmId: string | number;
}) {
  const [evidenceOpen, setEvidenceOpen] = useState(false);
  const moneyData = sectionData<any>(data?.money) ?? {};
  const dataTrust = sectionData<any>(data?.data_quality) ?? {};
  const checker = sectionData<any>(data?.card_quality ?? data?.quality) ?? {};
  const actionsData = sectionData<any>(data?.actions) ?? {};
  const actionItems: any[] = Array.isArray(actionsData?.items)
    ? actionsData.items
    : Array.isArray(actionsData?.actions)
      ? actionsData.actions
      : Array.isArray(actionsData)
        ? actionsData
        : [];
  const openActions = actionItems.filter(
    (item) =>
      !["done", "resolved", "ignored", "closed"].includes(
        String(item?.status ?? "").toLowerCase(),
      ),
  );
  const checkerIssues: any[] = Array.isArray(checker?.issues)
    ? checker.issues
    : Array.isArray(checker?.blockers)
      ? checker.blockers
      : [];
  const money = moneyData.money ?? moneyData.summary ?? moneyData;
  const revenue =
    pick<number>(moneyData.summary ?? money, ["revenue", "revenue_final"]) ??
    pick<number>(money, ["revenue", "revenue_final"]);
  const profit =
    pick<number>(moneyData.summary ?? money, [
      "estimated_profit",
      "net_profit",
      "profit",
    ]) ??
    pick<number>(money?.profit ?? money, [
      "after_ads",
      "net_profit",
      "estimated_profit",
    ]);
  const trustStatus =
    sectionStatus(data?.data_quality) ??
    pick<string>(dataTrust, ["status", "state", "trust_state"]);
  const checkerScore = pick<number>(checker, ["score", "checker_score"]);
  const ledger = evidenceFrom(
    data?.evidence_ledger,
    data?.money?.evidence_ledger,
    data?.data_quality?.evidence_ledger,
    data?.card_quality?.evidence_ledger,
    data?.quality?.evidence_ledger,
    data?.actions?.evidence_ledger,
  );

  return (
    <>
      <section className="space-y-3">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h2 className="text-base font-semibold">История товара</h2>
            <p className="text-xs text-muted-foreground">
              Одна цепочка: деньги, доверие к данным, проблемы карточки,
              открытые действия и доказательства.
            </p>
          </div>
          <EvidenceButton
            ledger={ledger}
            allowEmpty
            onClick={() => setEvidenceOpen(true)}
          />
        </div>
        <div className="grid auto-rows-fr gap-3 grid-cols-2 lg:grid-cols-5">
          <StoryStep
            icon={<Sparkles className="h-4 w-4" />}
            title="Деньги"
            value={profit == null ? "Нет расчёта" : formatMoney(profit)}
            detail={
              revenue == null
                ? "Выручка не рассчитана"
                : `Выручка: ${formatMoney(revenue)}`
            }
            tone={profit != null && profit < 0 ? "danger" : "default"}
          />
          <StoryStep
            icon={<ShieldCheck className="h-4 w-4" />}
            title="Доверие к данным"
            value={
              STATUS_LABEL_RU[String(trustStatus ?? "empty").toLowerCase()] ??
              "Нет данных"
            }
            detail={
              sectionMessage(data?.data_quality) ??
              "Откройте доказательства, чтобы увидеть источник."
            }
            to="/data-fix"
            action="Починить данные"
            tone={
              ["blocked", "critical", "error", "failed"].includes(
                String(trustStatus ?? "").toLowerCase(),
              )
                ? "danger"
                : "default"
            }
          />
          <StoryStep
            icon={<CheckCircle2 className="h-4 w-4" />}
            title="Проверка карточки"
            value={
              checkerScore == null
                ? `${checkerIssues.length} проблем`
                : `${checkerScore}/100`
            }
            detail={
              checkerIssues.length
                ? `${checkerIssues.length} пунктов требуют решения`
                : "Активных проблем карточки не найдено."
            }
            to={`/checker/${nmId}`}
            action="Открыть проверку"
            tone={checkerIssues.length ? "warning" : "default"}
          />
          <StoryStep
            icon={<ListChecks className="h-4 w-4" />}
            title="Открытые действия"
            value={openActions.length}
            detail={
              openActions[0]?.title ??
              openActions[0]?.summary ??
              "Нет задач по этому товару."
            }
            to="/action-center"
            action="Назначить или закрыть"
            tone={openActions.length ? "warning" : "default"}
          />
          <StoryStep
            icon={<FileText className="h-4 w-4" />}
            title="Доказательства"
            value={ledger ? "Есть источник" : "Источник не передан"}
            detail={
              ledger?.formula_human ??
              "Если источник не передан, сумма не должна восприниматься как полностью объяснённая."
            }
            onAction={() => setEvidenceOpen(true)}
            action="Показать"
            tone={ledger ? "default" : "warning"}
          />
        </div>
      </section>
      <EvidenceDrawer
        open={evidenceOpen}
        onOpenChange={setEvidenceOpen}
        ledger={ledger}
        title="Доказательства по товару"
      />
    </>
  );
}

function StoryStep({
  icon,
  title,
  value,
  detail,
  tone = "default",
  to,
  action,
  onAction,
}: {
  icon: ReactNode;
  title: string;
  value: ReactNode;
  detail: string;
  tone?: "default" | "warning" | "danger";
  to?: string;
  action?: string;
  onAction?: () => void;
}) {
  const toneClass =
    tone === "danger"
      ? "border-destructive/40 bg-destructive/5"
      : tone === "warning"
        ? "border-warning/40 bg-warning/5"
        : "bg-background";
  return (
    <Card className={cn("flex h-full flex-col", toneClass)}>
      <CardContent className="flex flex-1 flex-col gap-2 p-3">
        <div className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
          {icon}
          {title}
        </div>
        <div className="text-lg font-semibold tabular-nums">{value}</div>
        <div className="min-h-10 text-xs text-muted-foreground line-clamp-3">
          {detail}
        </div>
        <div className="mt-auto">
          {to && action ? (
            <Button
              asChild
              size="sm"
              variant="outline"
              className="h-7 w-full text-xs"
            >
              <Link to={to as any}>
                {action} <ArrowRight className="h-3 w-3 ml-1" />
              </Link>
            </Button>
          ) : onAction && action ? (
            <Button
              size="sm"
              variant="outline"
              className="h-7 w-full text-xs"
              onClick={onAction}
            >
              {action}
            </Button>
          ) : null}
        </div>
      </CardContent>
    </Card>
  );
}

// ─── focused section renderers ────────────────────────────────────────
function MoneySection({
  section,
  costsSection,
}: {
  section: any;
  costsSection?: any;
}) {
  const status = sectionStatus(section);
  const message = sectionMessage(section);
  const d = sectionData<any>(section) ?? {};
  const summary = d.summary ?? {};
  const m = d.money ?? {};
  const ads = isObj(m.ads) ? m.ads : {};
  const profit = isObj(m.profit) ? m.profit : null;
  const variants = isObj(d.profit_variants) ? d.profit_variants : {};
  const wbExp = isObj(m.wb_expenses) ? m.wb_expenses : {};

  const revenue =
    pick<number>(summary, ["revenue"]) ??
    pick<number>(m, ["revenue", "revenue_final"]);
  const forPay =
    pick<number>(summary, ["for_pay"]) ?? pick<number>(m, ["for_pay"]);
  const profitV =
    pick<number>(summary, ["estimated_profit"]) ??
    pick<number>(variants, [
      "after_allocated_ads",
      "after_source_ads",
      "before_ads",
    ]) ??
    pick<number>(m, [
      "net_profit_after_all_expenses",
      "profit_amount",
      "net_profit",
      "gross_profit",
    ]) ??
    (profit
      ? pick<number>(profit, ["after_ads", "after_allocated_ads", "before_ads"])
      : undefined);
  const marginRaw =
    pick<number>(summary, ["margin_percent"]) ??
    (profit ? pick<number>(profit, ["margin_after_ads_percent"]) : undefined);
  const adsSpend =
    pick<number>(ads, ["allocated_spend", "spend"]) ??
    pick<number>(m, ["ad_spend_final", "ad_spend_operational"]);
  const wbFees =
    pick<number>(wbExp, ["total_wb_expenses", "direct"]) ??
    pick<number>(m, ["wb_expenses_total"]);
  const ordersRaw = pick<number>(ads, ["orders"]);
  const ordersTrusted =
    ads?.orders_trusted === true ||
    ads?.orders_available === true ||
    ads?.orders_status === "ok" ||
    (ordersRaw != null && ordersRaw > 0);
  const showOrders = ordersRaw != null && ordersTrusted;

  // ── Waterfall inputs (Etap-3 spec) ──────────────────────────────────
  const costsData = sectionData<any>(costsSection) ?? {};
  const cogsAmount =
    pick<number>(costsData.cogs ?? {}, ["estimated_cogs"]) ??
    pick<number>(d, ["cogs_amount"]);
  const cardLevel =
    pick<number>(variants, ["after_allocated_ads", "after_source_ads"]) ??
    (revenue != null && cogsAmount != null && wbFees != null && adsSpend != null
      ? revenue - cogsAmount - wbFees - adsSpend
      : null);
  const unallocated =
    pick<number>(wbExp, ["allocated_overhead", "unallocated"]) ??
    (variants.after_overhead != null && cardLevel != null
      ? Math.max(0, cardLevel - (variants.after_overhead as number))
      : null);
  const ownerProfit = pick<number>(variants, [
    "after_overhead",
    "with_allocated_overhead",
  ]);
  const hasWaterfall =
    revenue != null &&
    (cogsAmount != null || cardLevel != null || ownerProfit != null);

  const hasAny = [revenue, forPay, profitV, marginRaw, adsSpend, wbFees].some(
    (v) => v != null,
  );

  return (
    <SectionCard
      title="Деньги"
      status={status}
      subtitle={message ?? undefined}
      evidence={evidenceFrom(section?.evidence_ledger, d?.evidence_ledger)}
      data-testid="product-360-money"
    >
      {hasAny ? (
        <div>
          <KV label="Выручка" value={revenue} money />
          <KV label="К перечислению" value={forPay} money />
          <KV label="Прибыль" value={profitV} money negativeRed />
          <KV
            label="Маржа"
            value={
              marginRaw != null
                ? `${(Math.abs(marginRaw) <= 1 ? marginRaw * 100 : marginRaw).toFixed(1)}%`
                : null
            }
          />
          <KV label="Расходы WB" value={wbFees} money />
          <KV label="Реклама" value={adsSpend} money />
          <div className="flex justify-between gap-3 border-b border-border/50 py-1.5 last:border-0">
            <span className="text-xs text-muted-foreground">Заказы</span>
            <span className="text-right">
              {showOrders ? displayMetric(ordersRaw) : displayMetric(null)}
            </span>
          </div>
        </div>
      ) : (
        <div className="text-xs text-muted-foreground">Нет данных</div>
      )}
      {hasWaterfall && (
        <div className="pt-3" data-testid="product-360-waterfall">
          <div className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground mb-1">
            Откуда берётся прибыль
          </div>
          <MoneyWaterfall
            revenue={revenue ?? null}
            cogs={cogsAmount ?? null}
            wbExpenses={wbFees ?? null}
            adsSpend={adsSpend ?? null}
            cardLevelProfit={cardLevel ?? null}
            unallocated={unallocated ?? null}
            ownerProfit={ownerProfit ?? null}
            ownerProfitEstimated
          />
        </div>
      )}
    </SectionCard>
  );
}

function CostsSection({ section }: { section: any }) {
  const status = sectionStatus(section);
  const d = sectionData<any>(section) ?? {};
  const cogs = isObj(d.cogs) ? d.cogs : {};
  const unitCost =
    pick<number>(cogs, ["unit_cost"]) ?? pick<number>(d, ["unit_cost"]);
  const estimatedCogs = pick<number>(cogs, ["estimated_cogs"]);
  const truth = pick<string>(cogs, ["cost_truth_label", "truth_level"]);
  const reason = pick<string>(cogs, ["reason"]) ?? sectionMessage(section);
  const missing =
    status === "blocked" || status === "missing" || unitCost == null;

  return (
    <SectionCard
      title="Себестоимость"
      status={status}
      evidence={evidenceFrom(section?.evidence_ledger, d?.evidence_ledger)}
    >
      {missing && (
        <Alert variant="destructive" className="py-2">
          <AlertTriangle className="h-3.5 w-3.5" />
          <AlertTitle className="text-xs">
            Себестоимость не подтверждена
          </AlertTitle>
          <AlertDescription className="text-xs">
            {reason ??
              "Без подтверждённой себестоимости финальная прибыль неполная."}
          </AlertDescription>
        </Alert>
      )}
      <div>
        <KV label="Цена за ед." value={unitCost} money />
        <KV label="Себестоимость за период" value={estimatedCogs} money />
        {truth && <KV label="Уровень доверия" value={truth} />}
      </div>
    </SectionCard>
  );
}

function DataQualitySection({ section }: { section: any }) {
  const dq = sectionData<any>(section) ?? {};
  // Backend exposes a single `issues` list with `severity`, plus optional
  // `blockers`/`problems`/`warnings`. Split by severity so blockers (errors)
  // and warnings render in their own group with humanized copy.
  const issues: any[] = Array.isArray(dq.issues)
    ? dq.issues
    : Array.isArray(dq.problems)
      ? dq.problems
      : [];
  const explicitBlockers: any[] = Array.isArray(dq.blockers) ? dq.blockers : [];
  const explicitWarnings: any[] = Array.isArray(dq.warnings) ? dq.warnings : [];

  const isBlocker = (it: any) => {
    const sev = String(it?.severity ?? "").toLowerCase();
    if (it?.financial_final_blocker || it?.effective_financial_final_blocker)
      return true;
    return (
      sev === "error" ||
      sev === "critical" ||
      sev === "blocker" ||
      sev === "high"
    );
  };

  const isSystemHandledIssue = (it: any) => {
    const code = String(
      it?.code ?? it?.action_type ?? it?.type ?? "",
    ).toLowerCase();
    return isSystemHandledCode(code);
  };
  const rawBlockers = [...explicitBlockers, ...issues.filter(isBlocker)].filter(
    (it) => !isSystemHandledIssue(it),
  );
  const rawWarnings = [
    ...explicitWarnings,
    ...issues.filter((it) => !isBlocker(it)),
  ].filter((it) => !isSystemHandledIssue(it));

  const status =
    deriveSectionStatus(section, {
      blockers: rawBlockers,
      warnings: rawWarnings,
    }) ??
    pick<string>(dq, ["status", "state"]) ??
    (rawBlockers.length ? "blocked" : rawWarnings.length ? "warning" : null);

  // Prefer the humanized fields the backend already provides.
  const titleOf = (it: any) =>
    String(
      it?.business_impact ??
        it?.simple_reason ??
        it?.title ??
        it?.message ??
        it?.code ??
        "Проблема с данными",
    );
  const codeOf = (it: any) => String(it?.code ?? titleOf(it));
  const detailOf = (it: any) =>
    it?.recommended_fix ??
    it?.first_action ??
    it?.message ??
    it?.detail ??
    null;

  const groupBy = (items: any[]) => {
    const map = new Map<string, { title: string; items: any[] }>();
    for (const it of items) {
      const key = codeOf(it);
      if (!map.has(key)) map.set(key, { title: titleOf(it), items: [] });
      map.get(key)!.items.push(it);
    }
    return Array.from(map.values()).sort(
      (a, b) => b.items.length - a.items.length,
    );
  };
  const blockerGroups = groupBy(rawBlockers);
  const warningGroups = groupBy(rawWarnings);

  if (!rawBlockers.length && !rawWarnings.length) {
    return (
      <SectionCard
        title="Качество данных"
        status={status ?? "ok"}
        evidence={evidenceFrom(section?.evidence_ledger, dq?.evidence_ledger)}
        data-testid="product-360-data-quality"
      >
        <div className="text-xs text-muted-foreground">Проблем нет</div>
      </SectionCard>
    );
  }

  const renderGroup = (
    g: { title: string; items: any[] },
    i: number,
    tone: "destructive" | "warning",
  ) => {
    const sample = g.items[0] ?? {};
    const fix = detailOf(sample);
    const steps: string[] = Array.isArray(sample?.step_by_step)
      ? sample.step_by_step
      : [];
    return (
      <li key={i} className="rounded border border-border/60 p-2 space-y-1">
        <div className="flex items-center justify-between gap-2">
          <span
            className={`text-xs font-medium ${tone === "destructive" ? "text-destructive" : "text-warning"}`}
          >
            {g.title}
          </span>
          {g.items.length > 1 && (
            <Badge variant="outline" className="text-[10px]">
              ×{g.items.length}
            </Badge>
          )}
        </div>
        {fix && (
          <div className="text-[11px] text-muted-foreground">
            <span className="font-medium">Что сделать: </span>
            {String(fix)}
          </div>
        )}
        {steps.length > 0 && (
          <ol className="text-[11px] text-muted-foreground space-y-0.5 list-decimal pl-4">
            {steps.slice(0, 3).map((s, j) => (
              <li key={j}>{s}</li>
            ))}
          </ol>
        )}
      </li>
    );
  };

  return (
    <SectionCard
      title="Качество данных"
      status={status}
      evidence={evidenceFrom(section?.evidence_ledger, dq?.evidence_ledger)}
      data-testid="product-360-data-quality"
    >
      {blockerGroups.length > 0 && (
        <div className="space-y-1">
          <div className="text-xs font-semibold text-destructive">Блокеры</div>
          <ul className="space-y-1.5">
            {blockerGroups
              .slice(0, 6)
              .map((g, i) => renderGroup(g, i, "destructive"))}
          </ul>
        </div>
      )}
      {warningGroups.length > 0 && (
        <div className="space-y-1">
          <div className="text-xs font-semibold text-warning">
            Предупреждения
          </div>
          <ul className="space-y-1.5">
            {warningGroups
              .slice(0, 6)
              .map((g, i) => renderGroup(g, i, "warning"))}
          </ul>
        </div>
      )}
    </SectionCard>
  );
}

function CardQualitySection({
  section,
  accountId,
  nmId,
}: {
  section: any;
  accountId?: number | null;
  nmId: number | string;
}) {
  const qc = useQueryClient();
  const [showIssues, setShowIssues] = useState(true);
  const [dismissReasons, setDismissReasons] = useState<Record<string, string>>(
    {},
  );
  const [issueEvidence, setIssueEvidence] = useState<{
    title: string;
    ledger: EvidenceLedger | null;
  } | null>(null);
  const q = sectionData<any>(section) ?? {};
  const rawStatus = (
    sectionStatus(section) ??
    pick<string>(q, ["status", "state"]) ??
    ""
  ).toLowerCase();
  const score = pick<number>(q, ["score", "checker_score"]);
  const issues: any[] = Array.isArray(q.issues) ? q.issues : [];
  const recs: any[] = Array.isArray(q.recommendations) ? q.recommendations : [];
  const summary = isObj(q.summary) ? q.summary : {};
  const categoryScores = isObj(q.category_scores)
    ? q.category_scores
    : isObj(summary.category_scores)
      ? summary.category_scores
      : {};
  const photosCount =
    pick<number>(summary, ["photos_count", "photo_count"]) ??
    pick<number>(q, ["photos_count", "photo_count"]);
  const analyzedAt = pick<string>(q, ["analyzed_at", "updated_at"]);
  const invalidateQuality = () => {
    qc.invalidateQueries({ queryKey: ["portal-product-detail"] });
    qc.invalidateQueries({ queryKey: ["portal-actions"] });
    qc.invalidateQueries({ queryKey: ["portal-results"] });
  };
  const analyzeMutation = useMutation({
    mutationFn: (force: boolean) =>
      analyzeProductCardQuality(nmId, accountId, { force }),
    onSuccess: () => {
      toast.success("Проверка карточки запущена");
      invalidateQuality();
    },
    onError: (e: any) =>
      toast.error(e?.message ?? "Не удалось запустить проверку"),
  });
  const taskMutation = useMutation({
    mutationFn: (issue: any) =>
      updateActionBySource({
        account_id: accountId,
        source_module: "checker",
        source_id: String(issue.id),
        status: "in_progress",
        comment: "Создано из карточки товара",
      }),
    onSuccess: () => {
      toast.success("Задача отправлена в центр действий");
      invalidateQuality();
    },
    onError: (e: any) =>
      toast.error(e?.message ?? "Не удалось обновить задачу"),
  });
  const dismissMutation = useMutation({
    mutationFn: ({ issue, reason }: { issue: any; reason: string }) =>
      updateCardQualityIssueStatus(issue.id, accountId, {
        status: "ignored",
        reason,
      }),
    onSuccess: () => {
      toast.success("Проблема скрыта");
      invalidateQuality();
    },
    onError: (e: any) =>
      toast.error(e?.message ?? "Не удалось скрыть проблему"),
  });
  const issueKey = (it: any, idx: number) =>
    String(it.id ?? it.issue_id ?? it.code ?? idx);
  const issueId = (it: any) => it.id ?? it.issue_id;
  const isBusy =
    analyzeMutation.isPending ||
    taskMutation.isPending ||
    dismissMutation.isPending;
  const actionButtons = (
    <div className="flex flex-wrap gap-1.5">
      <Button
        size="sm"
        variant="outline"
        className="h-7 text-xs"
        onClick={() => analyzeMutation.mutate(false)}
        disabled={!accountId || analyzeMutation.isPending}
      >
        Запустить проверку
      </Button>
      <Button
        size="sm"
        variant="outline"
        className="h-7 text-xs"
        onClick={() => analyzeMutation.mutate(true)}
        disabled={!accountId || analyzeMutation.isPending}
      >
        Проверить заново
      </Button>
      <Button asChild size="sm" variant="default" className="h-7 text-xs">
        <Link to="/checker/$nmId" params={{ nmId: String(nmId) }}>
          Открыть проверку карточки <ArrowRight className="h-3 w-3 ml-1" />
        </Link>
      </Button>
      <Button
        size="sm"
        variant="ghost"
        className="h-7 text-xs"
        onClick={() => setShowIssues((v) => !v)}
        disabled={issues.length === 0}
      >
        {showIssues ? "Скрыть проблемы" : "Показать проблемы"}
      </Button>
      <Button asChild size="sm" variant="ghost" className="h-7 text-xs">
        <Link to="/action-center">
          Центр действий <ArrowRight className="h-3 w-3 ml-1" />
        </Link>
      </Button>
    </div>
  );

  // Не настроен / отключён / недоступен — показываем явное объяснение.
  if (rawStatus === "not_configured") {
    return (
      <SectionCard
        title="Качество карточки"
        status="not_configured"
        evidence={evidenceFrom(section?.evidence_ledger, q?.evidence_ledger)}
        data-quality-status="not_configured"
      >
        <div className="text-xs text-muted-foreground space-y-1">
          <div className="font-medium text-foreground">
            Проверка карточек не подключена
          </div>
          <div>Качество карточки пока не анализируется.</div>
          <div>
            Подключите модуль в настройках, чтобы видеть проблемы фото, описания
            и характеристик.
          </div>
        </div>
        {actionButtons}
      </SectionCard>
    );
  }
  if (rawStatus === "disabled") {
    return (
      <SectionCard
        title="Качество карточки"
        status="disabled"
        evidence={evidenceFrom(section?.evidence_ledger, q?.evidence_ledger)}
        data-quality-status="disabled"
      >
        <div className="text-xs text-muted-foreground">
          Модуль качества карточек отключён.
        </div>
        {actionButtons}
      </SectionCard>
    );
  }
  if (
    rawStatus === "unavailable" ||
    rawStatus === "error" ||
    rawStatus === "failed"
  ) {
    return (
      <SectionCard
        title="Качество карточки"
        status={rawStatus}
        evidence={evidenceFrom(section?.evidence_ledger, q?.evidence_ledger)}
        data-quality-status={rawStatus}
      >
        <div className="text-xs text-destructive">
          Не удалось загрузить качество карточки. Попробуйте обновить страницу
          позже.
        </div>
        {actionButtons}
      </SectionCard>
    );
  }

  return (
    <>
      <SectionCard
        title="Качество карточки"
        status={rawStatus || "ok"}
        evidence={evidenceFrom(section?.evidence_ledger, q?.evidence_ledger)}
        data-quality-status={rawStatus || "ok"}
      >
        {actionButtons}
        {score != null && (
          <KV label="Оценка качества" value={`${Math.round(score)}`} />
        )}
        {photosCount != null && <KV label="Фото" value={photosCount} />}
        {analyzedAt && (
          <KV
            label="Проверено"
            value={new Date(analyzedAt).toLocaleString("ru-RU")}
          />
        )}
        <KV label="Открытых проблем" value={issues.length} />
        {Object.keys(categoryScores).length > 0 && (
          <div className="space-y-1">
            <div className="text-xs font-semibold">Score по категориям</div>
            <div className="grid grid-cols-2 gap-1">
              {Object.entries(categoryScores).map(([key, value]) => (
                <div
                  key={key}
                  className="flex justify-between gap-2 rounded border px-2 py-1 text-xs"
                >
                  <span className="text-muted-foreground">
                    {humanizeIssueMeta(key)}
                  </span>
                  <span className="tabular-nums">{String(value)}</span>
                </div>
              ))}
            </div>
          </div>
        )}
        {issues.length === 0 &&
          rawStatus !== "warning" &&
          rawStatus !== "critical" && (
            <div className="text-xs text-muted-foreground">
              Проблем не найдено
            </div>
          )}
        {issues.length > 0 && showIssues && (
          <div className="space-y-1">
            <div className="text-xs font-semibold">Проблемы</div>
            <ul className="text-xs space-y-2">
              {issues.slice(0, 10).map((it, i) => {
                const key = issueKey(it, i);
                const id = issueId(it);
                const reason = dismissReasons[key] ?? "";
                const suggestionKind = String(
                  it.suggestion_kind ?? "",
                ).toLowerCase();
                const requiresHuman = it.requires_human_check === true;
                const suggested =
                  it.ai_suggested_value ?? it.suggested_value ?? null;
                const currentValue =
                  it.current_value_json ?? it.current_value ?? null;
                const allowedValues: any[] = Array.isArray(it.allowed_values)
                  ? it.allowed_values
                  : Array.isArray(it.allowed_values_json)
                    ? it.allowed_values_json
                    : [];
                const alternatives: any[] = Array.isArray(it.ai_alternatives)
                  ? it.ai_alternatives
                  : Array.isArray(it.alternatives)
                    ? it.alternatives
                    : [];
                const evidence = isObj(it.ai_evidence)
                  ? it.ai_evidence
                  : isObj(it.ai_evidence_json)
                    ? it.ai_evidence_json
                    : {};
                const issueLedger = evidenceFrom(it.evidence_ledger);
                const issueMoneyTrust = moneyTrustFrom(
                  it.money_trust,
                  issueLedger?.money_trust,
                  issueLedger,
                );
                const observed: any[] = Array.isArray(evidence.observed)
                  ? evidence.observed
                  : [];
                const issueMode = requiresHuman
                  ? "Нужна ручная проверка"
                  : suggestionKind === "exact_fix"
                    ? "Можно исправить точно"
                    : suggestionKind === "candidate" ||
                        suggestionKind === "draft_text"
                      ? "Есть кандидат"
                      : "Безопасного автоисправления нет";
                return (
                  <li key={key} className="rounded border p-2 space-y-1.5">
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0">
                        <div className="flex flex-wrap items-center gap-1.5">
                          <div className="font-medium">
                            {it.title ??
                              it.message ??
                              it.code ??
                              "Проблема качества карточки"}
                          </div>
                          <Badge variant="outline" className="text-[10px]">
                            {issueMode}
                          </Badge>
                          {it.money_trust || issueLedger ? (
                            <MoneyTrustBadge trust={issueMoneyTrust} />
                          ) : null}
                        </div>
                        {(it.business_explanation ?? it.description) && (
                          <div className="text-muted-foreground">
                            {it.business_explanation ?? it.description}
                          </div>
                        )}
                        {(it.recommended_fix ?? it.recommendation) && (
                          <div className="text-muted-foreground">
                            Шаг: {it.recommended_fix ?? it.recommendation}
                          </div>
                        )}
                        {currentValue != null && (
                          <div className="rounded bg-muted/40 px-2 py-1 text-[11px]">
                            <span className="text-muted-foreground">
                              Сейчас:{" "}
                            </span>
                            {formatIssueValue(currentValue)}
                          </div>
                        )}
                        {suggested && (
                          <div className="rounded border border-success/30 bg-success/10 px-2 py-1 text-[11px]">
                            <span className="text-muted-foreground">
                              {requiresHuman ? "Кандидат: " : "Исправить на: "}
                            </span>
                            {String(suggested)}
                          </div>
                        )}
                        {!suggested && alternatives.length > 0 && (
                          <div className="flex flex-wrap gap-1">
                            <span className="text-[11px] text-muted-foreground">
                              Кандидаты:
                            </span>
                            {alternatives.slice(0, 5).map((value, idx) => (
                              <Badge
                                key={idx}
                                variant="outline"
                                className="text-[10px]"
                              >
                                {String(value)}
                              </Badge>
                            ))}
                          </div>
                        )}
                        {allowedValues.length > 0 && (
                          <div className="space-y-1">
                            <div className="text-[11px] text-muted-foreground">
                              Разрешённые WB значения
                            </div>
                            <div className="flex flex-wrap gap-1">
                              {allowedValues.slice(0, 8).map((value, idx) => (
                                <Badge
                                  key={idx}
                                  variant="outline"
                                  className="text-[10px]"
                                >
                                  {String(value).trim()}
                                </Badge>
                              ))}
                              {allowedValues.length > 8 && (
                                <span className="text-[11px] text-muted-foreground">
                                  ещё {allowedValues.length - 8}
                                </span>
                              )}
                            </div>
                          </div>
                        )}
                        {(it.ai_reason_short ?? it.ai_reason) && (
                          <div className="text-[11px] text-muted-foreground">
                            Почему: {it.ai_reason_short ?? it.ai_reason}
                          </div>
                        )}
                        {observed.length > 0 && (
                          <div className="text-[11px] text-muted-foreground">
                            Доказательство:{" "}
                            {observed.slice(0, 2).map(String).join("; ")}
                          </div>
                        )}
                        <div className="flex flex-wrap gap-2 text-[11px] text-muted-foreground">
                          {(it.category ?? it.type) && (
                            <span>
                              {humanizeIssueMeta(it.category ?? it.type)}
                            </span>
                          )}
                          {it.severity && (
                            <span>{humanizeIssueMeta(it.severity)}</span>
                          )}
                          {(it.field_name ?? it.field_path) && (
                            <span>
                              {humanizeIssueMeta(
                                it.field_name ?? it.field_path,
                              )}
                            </span>
                          )}
                          {it.source && (
                            <span>{humanizeIssueMeta(it.source)}</span>
                          )}
                        </div>
                      </div>
                      <div className="flex shrink-0 flex-col gap-1">
                        {issueLedger ? (
                          <EvidenceButton
                            ledger={issueLedger}
                            className="max-w-[190px]"
                            onClick={() =>
                              setIssueEvidence({
                                title:
                                  it.title ??
                                  it.message ??
                                  "Проблема качества карточки",
                                ledger: issueLedger,
                              })
                            }
                          />
                        ) : null}
                        {id != null && (
                          <Button
                            size="sm"
                            className="h-7 text-xs shrink-0"
                            onClick={() => taskMutation.mutate(it)}
                            disabled={!accountId || isBusy}
                          >
                            В работу
                          </Button>
                        )}
                      </div>
                    </div>
                    {id != null && (
                      <div className="grid gap-1.5">
                        <Input
                          value={reason}
                          onChange={(e) =>
                            setDismissReasons((prev) => ({
                              ...prev,
                              [key]: e.target.value,
                            }))
                          }
                          placeholder="Почему можно скрыть проблему"
                          className="h-8 text-xs"
                        />
                        <div className="flex justify-end">
                          <Button
                            size="sm"
                            variant="outline"
                            className="h-7 text-xs"
                            onClick={() =>
                              dismissMutation.mutate({ issue: it, reason })
                            }
                            disabled={
                              !accountId || isBusy || reason.trim().length === 0
                            }
                          >
                            Скрыть проблему
                          </Button>
                        </div>
                      </div>
                    )}
                  </li>
                );
              })}
            </ul>
          </div>
        )}
        {recs.length > 0 && (
          <div className="space-y-1">
            <div className="text-xs font-semibold">Рекомендации</div>
            <ul className="text-xs space-y-1 list-disc pl-4">
              {recs.slice(0, 10).map((it, i) => (
                <li key={i}>
                  {it.title ?? it.message ?? it.code ?? JSON.stringify(it)}
                </li>
              ))}
            </ul>
          </div>
        )}
      </SectionCard>
      <EvidenceDrawer
        open={!!issueEvidence}
        onOpenChange={(open) => {
          if (!open) setIssueEvidence(null);
        }}
        ledger={issueEvidence?.ledger}
        title={issueEvidence?.title}
      />
    </>
  );
}

function PhotoSection({
  section,
  nmId,
}: {
  section: any;
  nmId: string | number;
}) {
  const p = sectionData<any>(section) ?? {};
  const status =
    sectionStatus(section) ?? pick<string>(p, ["status", "state"]) ?? "ok";
  const sourcesCount = pick<number>(p, ["wb_sources_count", "sources_count"]);
  const versionsCount = pick<number>(p, ["versions_count"]);
  const approvedThumb = pick<string>(p, [
    "approved_thumbnail",
    "approved_image",
  ]);
  const preferredThumb = pick<string>(p, ["preferred_thumbnail"]);
  const activeProjectId = pick<number | string>(p, [
    "active_project_id",
    "project_id",
  ]);
  const issues: any[] = Array.isArray(p.issues) ? p.issues : [];
  const generation: string = pick<string>(p, ["generation_status"]) ?? "ok";

  return (
    <SectionCard title="Фото карточки" status={status}>
      <div className="space-y-2">
        {issues.length > 0 && (
          <ul className="text-xs space-y-0.5">
            {issues.slice(0, 4).map((it, i) => (
              <li key={i} className="text-warning">
                • {it.title ?? it.message ?? it.code ?? String(it)}
              </li>
            ))}
          </ul>
        )}
        {(approvedThumb || preferredThumb) && (
          <div className="flex gap-2">
            {approvedThumb && (
              <img
                src={approvedThumb}
                alt="Одобренная версия"
                className="w-16 h-16 rounded border object-cover"
                loading="lazy"
              />
            )}
            {preferredThumb && !approvedThumb && (
              <img
                src={preferredThumb}
                alt="Предпочтительная версия"
                className="w-16 h-16 rounded border object-cover"
                loading="lazy"
              />
            )}
          </div>
        )}
        <div className="flex flex-wrap gap-x-3 gap-y-0.5 text-[11px] text-muted-foreground">
          {sourcesCount != null && (
            <span>
              WB-исходники:{" "}
              <span className="text-foreground">{sourcesCount}</span>
            </span>
          )}
          {versionsCount != null && (
            <span>
              Версии: <span className="text-foreground">{versionsCount}</span>
            </span>
          )}
          {generation && generation !== "ok" && (
            <span>
              Генерация:{" "}
              {generation === "not_configured" ? "не подключена" : "выключена"}
            </span>
          )}
        </div>
        <div className="flex flex-wrap gap-1.5 pt-1">
          {activeProjectId != null ? (
            <Button asChild size="sm" variant="default" className="h-7 text-xs">
              <Link
                to="/photo-studio/projects/$projectId"
                params={{ projectId: String(activeProjectId) }}
              >
                <Camera className="h-3 w-3 mr-1" /> Открыть проект
              </Link>
            </Button>
          ) : (
            <Button asChild size="sm" variant="default" className="h-7 text-xs">
              <Link
                to="/photo-studio"
                search={{ nm_id: String(nmId), source: "product360" }}
              >
                <Camera className="h-3 w-3 mr-1" /> Открыть фотостудию
              </Link>
            </Button>
          )}
          {approvedThumb && (
            <Button asChild size="sm" variant="outline" className="h-7 text-xs">
              <a href={approvedThumb} download target="_blank" rel="noreferrer">
                Скачать одобренную
              </a>
            </Button>
          )}
        </div>
      </div>
    </SectionCard>
  );
}

function StockSection({ section }: { section: any }) {
  const s = sectionData<any>(section) ?? {};
  const status =
    sectionStatus(section) ?? pick<string>(s, ["status", "stock_status"]);
  const qty = pick<number>(s, ["quantity", "qty", "stock_qty", "available"]);
  const days = pick<number>(s, [
    "days_of_stock",
    "days_left",
    "cover_days",
    "days_of_cover",
  ]);
  const value = pick<number>(s, ["stock_value"]);
  return (
    <SectionCard title="Остатки" status={status}>
      <KV label="Остаток, шт." value={qty} />
      {days != null && <KV label="Хватит на, дн." value={days} />}
      {value != null && <KV label="Стоимость остатка" value={value} money />}
    </SectionCard>
  );
}

function ClaimsSection({
  section,
  nmId,
}: {
  section: any;
  nmId: string | number;
}) {
  const c = sectionData<any>(section) ?? {};
  const status = sectionStatus(section) ?? pick<string>(c, ["status"]);
  if (
    status === "disabled" ||
    status === "not_configured" ||
    status === "unavailable"
  ) {
    return (
      <SectionCard title="Претензии" status={status}>
        <div className="text-xs text-muted-foreground">
          {humanizeModuleMessage("claims", sectionMessage(section))}
        </div>
        <Button asChild size="sm" variant="outline" className="h-7 text-xs">
          <Link to="/claims" search={{ nm_id: String(nmId) } as any}>
            Открыть претензии <ArrowRight className="h-3 w-3 ml-1" />
          </Link>
        </Button>
      </SectionCard>
    );
  }
  const openCount = pick<number>(c, ["open_cases_count", "local_cases_count"]);
  const potential = pick<number>(c, ["potential_compensation_amount"]);
  const cases: any[] = Array.isArray(c.cases)
    ? c.cases
    : Array.isArray(c.local_cases)
      ? c.local_cases
      : Array.isArray(c.items)
        ? c.items
        : [];
  const candidates: any[] = Array.isArray(c.candidates) ? c.candidates : [];
  const candidateCount =
    pick<number>(c, ["candidate_count"]) ?? candidates.length;
  const allRows = [...candidates, ...cases];
  const statusCounts = countBy(
    allRows,
    (it) => it.status ?? it.review_status ?? it.external_status,
  );
  const first = c.next_claim_action ?? candidates[0] ?? cases[0] ?? null;
  const hasWork = (candidateCount ?? 0) > 0 || (openCount ?? cases.length) > 0;
  const businessStatus = moduleBusinessStatus(status, hasWork ? "claim" : "ok");
  return (
    <SectionCard
      title="Претензии"
      subtitle={businessStatus}
      status={hasWork ? "warning" : "ok"}
    >
      <div className="grid grid-cols-3 gap-2">
        <MiniKpi label="Кейсы" value={openCount ?? cases.length} />
        <MiniKpi label="Кандидаты" value={candidateCount} />
        <MiniKpi label="Компенсация" value={potential} money />
      </div>
      {Object.keys(statusCounts).length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {Object.entries(statusCounts)
            .slice(0, 5)
            .map(([key, value]) => (
              <Badge key={key} variant="outline" className="text-[10px]">
                {normalizeStatusLabel(key)}: {value}
              </Badge>
            ))}
        </div>
      )}
      {!hasWork && (
        <div className="text-xs text-muted-foreground">
          По этой карточке претензий нет.
        </div>
      )}
      {first && (
        <div className="rounded border bg-muted/30 p-2 text-xs">
          <div className="font-medium">
            {first.title ??
              first.subject ??
              first.action_type ??
              "Претензия по карточке"}
          </div>
          {(first.summary ??
            first.business_explanation ??
            first.reason ??
            first.next_step) && (
            <div className="text-muted-foreground mt-0.5 line-clamp-2">
              {first.summary ??
                first.business_explanation ??
                first.reason ??
                first.next_step}
            </div>
          )}
        </div>
      )}
      {allRows.length > 0 && (
        <ul className="text-xs space-y-1">
          {allRows.slice(0, 3).map((cs, i) => (
            <li
              key={i}
              className="flex justify-between gap-2 border-b border-border/50 py-1 last:border-0"
            >
              <span className="truncate">
                {cs.title ??
                  cs.subject ??
                  cs.reason_code ??
                  `Кейс #${cs.id ?? i + 1}`}
              </span>
              <span className="text-muted-foreground shrink-0">
                {normalizeStatusLabel(
                  cs.status ?? cs.review_status ?? cs.external_status,
                )}
              </span>
            </li>
          ))}
        </ul>
      )}
      <Button
        asChild
        size="sm"
        variant={hasWork ? "default" : "outline"}
        className="h-7 text-xs w-full"
      >
        <Link to="/claims" search={{ nm_id: String(nmId) } as any}>
          {candidateCount > 0 ? "Разобрать претензию" : "Открыть кейсы"}{" "}
          <ArrowRight className="h-3 w-3 ml-1" />
        </Link>
      </Button>
    </SectionCard>
  );
}

function ReputationSection({
  section,
  nmId,
}: {
  section: any;
  nmId: string | number;
}) {
  const r = sectionData<any>(section) ?? {};
  const status = sectionStatus(section) ?? pick<string>(r, ["status"]);
  if (
    status === "disabled" ||
    status === "not_configured" ||
    status === "unavailable"
  ) {
    return (
      <SectionCard title="Репутация" status={status}>
        <div className="text-xs text-muted-foreground">
          {humanizeModuleMessage("reputation", sectionMessage(section))}
        </div>
        <Button asChild size="sm" variant="outline" className="h-7 text-xs">
          <Link to="/reputation" search={{ nm_id: String(nmId) } as any}>
            Открыть репутацию <ArrowRight className="h-3 w-3 ml-1" />
          </Link>
        </Button>
      </SectionCard>
    );
  }
  const items: any[] = Array.isArray(r.items)
    ? r.items
    : Array.isArray(r.last_items)
      ? r.last_items
      : [];
  const reviewsCount =
    pick<number>(r, ["reviews_count"]) ??
    items.filter((it) => it.item_type === "review").length;
  const questionsCount =
    pick<number>(r, ["questions_count"]) ??
    items.filter((it) => it.item_type === "question").length;
  const unansweredReviews = pick<number>(r, ["unanswered_reviews_count"]);
  const unansweredQuestions = pick<number>(r, ["unanswered_questions_count"]);
  const negative = pick<number>(r, ["negative_unanswered_count"]);
  const unansweredTotal =
    pick<number>(r, ["unanswered_count"]) ??
    (unansweredReviews ?? 0) + (unansweredQuestions ?? 0);
  const answeredCount =
    pick<number>(r, ["answered_count"]) ??
    items.filter((it) => !it.needs_reply || it.status === "answered").length;
  const rating =
    pick<number>(r, ["rating", "avg_rating", "average_rating"]) ??
    (() => {
      const ratings = items
        .map((it) => Number(it.rating))
        .filter((v) => Number.isFinite(v));
      return ratings.length
        ? ratings.reduce((sum, v) => sum + v, 0) / ratings.length
        : undefined;
    })();
  const rawBreakdown = isObj(r.rating_breakdown) ? r.rating_breakdown : {};
  const ratingBreakdown = [5, 4, 3, 2, 1].reduce<Record<number, number>>(
    (acc, value) => {
      const fromBackend = Number(
        rawBreakdown[value] ?? rawBreakdown[String(value)],
      );
      acc[value] = Number.isFinite(fromBackend)
        ? fromBackend
        : items.filter((it) => Number(it.rating) === value).length;
      return acc;
    },
    {} as Record<number, number>,
  );
  const sentimentCounts = isObj(r.sentiment_counts) ? r.sentiment_counts : {};
  const categoryCounts = isObj(r.category_counts) ? r.category_counts : {};
  const topCategories = Object.entries(categoryCounts)
    .map(([label, value]) => ({ label, value: Number(value) }))
    .filter(
      (item) => item.label && Number.isFinite(item.value) && item.value > 0,
    )
    .sort((a, b) => b.value - a.value)
    .slice(0, 3);
  const sentimentLabel: Record<string, string> = {
    negative: "Негатив",
    mixed: "Смешанные",
    neutral: "Нейтральные",
    positive: "Позитив",
    unknown: "Неясно",
  };
  const businessStatus = moduleBusinessStatus(
    status,
    unansweredTotal > 0 ? "attention" : items.length ? "ok" : "empty",
  );
  return (
    <SectionCard
      title="Репутация"
      subtitle={businessStatus}
      status={unansweredTotal > 0 ? "warning" : items.length ? "ok" : "empty"}
    >
      <div className="grid grid-cols-3 gap-2">
        <MiniKpi label="Отзывы" value={reviewsCount} />
        <MiniKpi label="Вопросы" value={questionsCount} />
        <MiniKpi
          label="Рейтинг"
          value={rating != null ? rating.toFixed(1) : null}
        />
      </div>
      <div>
        <KV label="Отзывов без ответа" value={unansweredReviews} />
        <KV label="Вопросов без ответа" value={unansweredQuestions} />
        <KV label="Негатив без ответа" value={negative} />
        <KV label="Отвечено" value={answeredCount} />
      </div>
      {(Object.keys(sentimentCounts).length > 0 ||
        topCategories.length > 0) && (
        <div className="space-y-2">
          {Object.keys(sentimentCounts).length > 0 && (
            <div className="grid grid-cols-2 gap-1">
              {Object.entries(sentimentCounts)
                .slice(0, 4)
                .map(([key, value]) => (
                  <div
                    key={key}
                    className="flex justify-between gap-2 rounded border px-2 py-1 text-xs"
                  >
                    <span className="text-muted-foreground">
                      {sentimentLabel[key] ?? normalizeStatusLabel(key)}
                    </span>
                    <span className="tabular-nums font-medium">
                      {String(value)}
                    </span>
                  </div>
                ))}
            </div>
          )}
          {topCategories.length > 0 && (
            <div>
              <div className="text-xs font-semibold mb-1">
                Главные темы отзывов
              </div>
              <div className="flex flex-wrap gap-1">
                {topCategories.map((item) => (
                  <Badge
                    key={item.label}
                    variant="outline"
                    className="text-[10px]"
                  >
                    {item.label}: {item.value}
                  </Badge>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
      <div className="space-y-1">
        <div className="text-xs font-semibold">Распределение рейтинга</div>
        <div className="grid grid-cols-5 gap-1">
          {[5, 4, 3, 2, 1].map((value) => (
            <div key={value} className="rounded border px-1.5 py-1 text-center">
              <div className="text-[11px] text-muted-foreground flex items-center justify-center gap-0.5">
                {value}
                <Star className="h-2.5 w-2.5 fill-current" />
              </div>
              <div className="text-xs tabular-nums font-medium">
                {ratingBreakdown[value] ?? 0}
              </div>
            </div>
          ))}
        </div>
      </div>
      {items.length > 0 ? (
        <ul className="text-xs space-y-1">
          {items.slice(0, 3).map((it, i) => (
            <li
              key={it.id ?? it.external_id ?? i}
              className="rounded border p-2"
            >
              <div className="flex items-center justify-between gap-2">
                <span className="font-medium">
                  {it.item_type === "question"
                    ? "Вопрос"
                    : it.item_type === "chat"
                      ? "Чат"
                      : "Отзыв"}
                </span>
                <span className="text-muted-foreground">
                  {it.needs_reply ? "без ответа" : "отвечено"}
                </span>
              </div>
              <div className="text-muted-foreground line-clamp-2 mt-0.5">
                {it.text ?? it.title ?? "Текст не передан"}
              </div>
            </li>
          ))}
        </ul>
      ) : (
        <div className="text-xs text-muted-foreground">
          По этой карточке ещё нет отзывов и вопросов.
        </div>
      )}
      <Button
        asChild
        size="sm"
        variant={unansweredTotal > 0 ? "default" : "outline"}
        className="h-7 text-xs w-full"
      >
        <Link to="/reputation" search={{ nm_id: String(nmId) } as any}>
          {unansweredTotal > 0 ? "Открыть ответы" : "Открыть репутацию"}{" "}
          <ArrowRight className="h-3 w-3 ml-1" />
        </Link>
      </Button>
    </SectionCard>
  );
}

function ActionsSection({
  section,
  accountId,
}: {
  section: any;
  accountId: number | null;
}) {
  const sd = sectionData<any>(section);
  const list: PortalAction[] = Array.isArray(sd)
    ? sd
    : Array.isArray(sd?.items)
      ? sd.items
      : Array.isArray(sd?.actions)
        ? sd.actions
        : Array.isArray(section)
          ? section
          : [];
  const qc = useQueryClient();
  const [busy, setBusy] = useState<string | null>(null);
  const [actionEvidence, setActionEvidence] = useState<{
    title: string;
    ledger: EvidenceLedger | null;
  } | null>(null);
  const visibleList = list.filter((a: any) =>
    isSellerVisibleMoneyTrust(
      a.money_trust,
      a.payload?.money_trust,
      a.evidence_ledger?.money_trust,
      a.payload?.evidence_ledger?.money_trust,
    ),
  );

  const mut = useMutation({
    mutationFn: async (vars: { a: PortalAction; status: string }) => {
      const { a, status } = vars;
      if (a.source_module && a.source_id != null) {
        return updateActionBySource({
          source_module: a.source_module,
          source_id: String(a.source_id),
          status,
          account_id: accountId,
        });
      }
      const actionId = Number(a.action_id ?? a.id);
      if (Number.isFinite(actionId) && actionId > 0)
        return updateActionById(actionId, { status, account_id: accountId });
      throw new Error("Нет идентификатора действия.");
    },
    onSuccess: () => {
      toast.success("Статус обновлён");
      qc.invalidateQueries({ queryKey: ["portal-product-detail"] });
      qc.invalidateQueries({ queryKey: ["portal-actions"] });
    },
    onError: (e: any) =>
      toast.error(e?.message ?? "Не удалось обновить статус"),
    onSettled: () => setBusy(null),
  });

  return (
    <>
      <SectionCard
        title="Действия по товару"
        evidence={evidenceFrom(section?.evidence_ledger)}
      >
        {visibleList.length === 0 ? (
          <div className="text-xs text-muted-foreground">
            Открытых действий нет
          </div>
        ) : (
          <div className="space-y-2">
            {visibleList.map((a: any, i: number) => {
              const key = String(
                a.id ?? `${a.source_module ?? "m"}-${a.source_id ?? i}`,
              );
              const canUpdate =
                a.can_update_status !== false && a.can_update !== false;
              const ledger = evidenceFrom(
                a.evidence_ledger,
                a.payload?.evidence_ledger,
              );
              const actionMoneyTrust = moneyTrustFrom(
                a.money_trust,
                a.payload?.money_trust,
                ledger?.money_trust,
                ledger,
              );
              return (
                <div key={key} className="rounded border p-2 space-y-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    {a.priority && (
                      <Badge
                        variant="outline"
                        className={`text-[10px] ${PRIO_COLORS[a.priority] ?? ""}`}
                      >
                        {a.priority}
                      </Badge>
                    )}
                    <div className="text-sm font-medium">
                      {a.title ?? "Действие"}
                    </div>
                    <MoneyTrustBadge trust={actionMoneyTrust} />
                    {a.status && (
                      <Badge variant="outline" className="text-[10px]">
                        {a.status}
                      </Badge>
                    )}
                  </div>
                  {a.reason && (
                    <div className="text-xs text-muted-foreground">
                      <span className="font-medium">Почему: </span>
                      {a.reason}
                    </div>
                  )}
                  {a.next_step && (
                    <div className="text-xs text-muted-foreground">
                      <span className="font-medium">Шаг: </span>
                      {a.next_step}
                    </div>
                  )}
                  {(canUpdate || ledger) && (
                    <div className="flex gap-1 pt-1 flex-wrap">
                      {ledger ? (
                        <EvidenceButton
                          ledger={ledger}
                          onClick={() =>
                            setActionEvidence({
                              title: a.title ?? "Действие",
                              ledger,
                            })
                          }
                        />
                      ) : null}
                      {[
                        { value: "in_progress", label: "В работе" },
                        { value: "done", label: "Готово" },
                        { value: "postponed", label: "Отложено" },
                        { value: "ignored", label: "Пропустить" },
                      ].map((s) => (
                        <Button
                          key={s.value}
                          size="sm"
                          variant="outline"
                          className="h-6 text-[11px]"
                          disabled={busy === key || mut.isPending}
                          onClick={() => {
                            setBusy(key);
                            mut.mutate({ a, status: s.value });
                          }}
                        >
                          {s.label}
                        </Button>
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </SectionCard>
      <EvidenceDrawer
        open={!!actionEvidence}
        onOpenChange={(open) => {
          if (!open) setActionEvidence(null);
        }}
        ledger={actionEvidence?.ledger}
        title={actionEvidence?.title}
      />
    </>
  );
}

function ResultsHistorySection({ data }: { data: any }) {
  const r = Array.isArray(data)
    ? data
    : Array.isArray(data?.items)
      ? data.items
      : Array.isArray(data?.events)
        ? data.events
        : Array.isArray(data?.result_events)
          ? data.result_events
          : Array.isArray(data?.result_history)
            ? data.result_history
            : Array.isArray(data?.results)
              ? data.results
              : Array.isArray(data?.recent_events)
                ? data.recent_events
                : [];
  if (!r.length) {
    return (
      <SectionCard title="История результатов">
        <div className="text-xs text-muted-foreground">Пока нет событий</div>
      </SectionCard>
    );
  }
  return (
    <SectionCard title="История результатов">
      <ul className="text-xs space-y-1">
        {r.slice(0, 10).map((e: any, i: number) => (
          <li
            key={i}
            className="flex justify-between gap-3 border-b border-border/50 py-1 last:border-0"
          >
            <span className="truncate">
              {e.title ?? e.event ?? e.message ?? "Событие"}
            </span>
            <span className="text-muted-foreground tabular-nums shrink-0">
              {e.amount != null
                ? formatMoney(e.amount)
                : (e.at ?? e.created_at ?? "")}
            </span>
          </li>
        ))}
      </ul>
    </SectionCard>
  );
}

function NextBestActionCard({ data }: { data: any }) {
  const a = data?.next_best_action ?? data?.next_action;
  const [evidenceOpen, setEvidenceOpen] = useState(false);
  if (!a || (typeof a === "object" && Object.keys(a).length === 0)) return null;
  const title = a.title ?? a.action_title ?? "Рекомендуемое действие";
  const ledger = evidenceFrom(a.evidence_ledger, a.payload?.evidence_ledger);
  if (
    !isSellerVisibleMoneyTrust(
      a.money_trust,
      a.payload?.money_trust,
      ledger?.money_trust,
      ledger,
    )
  )
    return null;
  const moneyTrust = moneyTrustFrom(
    a.money_trust,
    a.payload?.money_trust,
    ledger?.money_trust,
    ledger,
  );
  return (
    <>
      <Card className="border-primary/40 bg-primary/5">
        <CardContent className="p-4 space-y-3">
          <div className="flex items-center gap-2">
            <Sparkles className="h-4 w-4 text-primary shrink-0" />
            <div className="text-[11px] uppercase tracking-wide text-primary font-semibold">
              Следующее лучшее действие
            </div>
            <div className="ml-auto">
              <MoneyTrustBadge trust={moneyTrust} />
            </div>
          </div>
          <div className="text-sm font-semibold leading-snug">{title}</div>
          {a.reason && (
            <div className="text-xs text-muted-foreground leading-relaxed">
              <span className="font-medium text-foreground">Почему: </span>
              {a.reason}
            </div>
          )}
          {a.next_step && (
            <div className="text-xs text-muted-foreground leading-relaxed">
              <span className="font-medium text-foreground">Шаг: </span>
              {a.next_step}
            </div>
          )}
          {(a.expected_effect_amount ?? a.expected_impact_amount) != null && (
            <div className="rounded-md border border-dashed border-warning/45 bg-warning/10 px-2 py-1.5 text-xs font-medium tabular-nums text-warning">
              {moneyTrust.show_as_confirmed_money
                ? moneyTrust.amount_label
                : "Оценка риска/возможности"}
              :{" "}
              {formatMoney(
                a.expected_effect_amount ?? a.expected_impact_amount,
              )}
            </div>
          )}
          <div className="flex flex-wrap gap-2 pt-1">
            {ledger ? (
              <EvidenceButton
                ledger={ledger}
                onClick={() => setEvidenceOpen(true)}
              />
            ) : null}
            <Button
              asChild
              size="sm"
              className="h-8 text-xs flex-1 min-w-[140px]"
            >
              <Link to="/action-center">
                В центр действий <ArrowRight className="h-3 w-3 ml-1" />
              </Link>
            </Button>
          </div>
        </CardContent>
      </Card>
      <EvidenceDrawer
        open={evidenceOpen}
        onOpenChange={setEvidenceOpen}
        ledger={ledger}
        title={title}
      />
    </>
  );
}

// ─── Product cockpit helpers ─────────────────────────────────────────
type CockpitTone = "default" | "good" | "warning" | "danger" | "info" | "muted";

const COCKPIT_TONE: Record<CockpitTone, string> = {
  default: "border-border bg-background",
  good: "border-success/25 bg-background",
  warning: "border-warning/30 bg-background",
  danger: "border-destructive/30 bg-background",
  info: "border-info/25 bg-background",
  muted: "border-border bg-background",
};

const COCKPIT_ACCENT_TONE: Record<CockpitTone, string> = {
  default: "before:bg-border",
  good: "before:bg-success",
  warning: "before:bg-warning",
  danger: "before:bg-destructive",
  info: "before:bg-info",
  muted: "before:bg-muted-foreground/35",
};

const COCKPIT_ICON_TONE: Record<CockpitTone, string> = {
  default: "bg-muted text-muted-foreground",
  good: "bg-success/10 text-success",
  warning: "bg-warning/10 text-warning",
  danger: "bg-destructive/10 text-destructive",
  info: "bg-info/10 text-info",
  muted: "bg-muted text-muted-foreground",
};

const COCKPIT_SOFT_TONE: Record<CockpitTone, string> = {
  default: "border-border bg-muted/25",
  good: "border-success/25 bg-success/5",
  warning: "border-warning/35 bg-warning/5",
  danger: "border-destructive/30 bg-destructive/5",
  info: "border-info/25 bg-info/5",
  muted: "border-border bg-muted/30",
};

const COCKPIT_TEXT_TONE: Record<CockpitTone, string> = {
  default: "text-foreground",
  good: "text-success",
  warning: "text-warning",
  danger: "text-destructive",
  info: "text-info",
  muted: "text-muted-foreground",
};

const COCKPIT_BAR_TONE: Record<CockpitTone, string> = {
  default: "bg-foreground",
  good: "bg-success",
  warning: "bg-warning",
  danger: "bg-destructive",
  info: "bg-info",
  muted: "bg-muted-foreground/55",
};

const CONTROL_INPUT_CLASS =
  "h-11 rounded-xl border-0 bg-muted/55 px-4 ring-1 ring-border/50 transition placeholder:text-muted-foreground/70 hover:bg-muted/70 focus-visible:bg-background focus-visible:ring-2 focus-visible:ring-primary/35";
const CONTROL_PANEL_CLASS =
  "rounded-2xl border border-border/55 bg-background/95 shadow-[0_18px_48px_rgba(15,23,42,0.10)]";
const CONTROL_BUTTON_CLASS = "rounded-xl transition";
const COCKPIT_PANEL_CLASS =
  "border border-border/50 bg-background/82 shadow-none backdrop-blur";
const COCKPIT_SURFACE_CLASS =
  "border border-border/45 bg-background/72 shadow-none backdrop-blur";

function toFiniteNumber(value: any): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string") {
    const trimmed = value.trim();
    if (!trimmed) return null;
    const normalized = trimmed
      .replace(/\s/g, "")
      .replace(/₽|руб\.?|%/gi, "")
      .replace(",", ".");
    const parsed = Number(normalized);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function firstNumber(...values: any[]): number | null {
  for (const value of values) {
    const parsed = toFiniteNumber(value);
    if (parsed !== null) return parsed;
  }
  return null;
}

function firstNonZeroNumber(...values: any[]): number | null {
  let fallback: number | null = null;
  for (const value of values) {
    const parsed = toFiniteNumber(value);
    if (parsed === null) continue;
    if (Math.abs(parsed) > 0.0001) return parsed;
    if (fallback === null) fallback = parsed;
  }
  return fallback;
}

function sumPresent(...values: any[]): number | null {
  const nums = values
    .map((value) => toFiniteNumber(value))
    .filter((value): value is number => value !== null);
  if (!nums.length) return null;
  return nums.reduce((sum, value) => sum + value, 0);
}

function firstText(...values: any[]): string | null {
  for (const value of values) {
    if (value === null || value === undefined) continue;
    const text = String(value).trim();
    if (text) return text;
  }
  return null;
}

function asArray(value: any): any[] {
  if (Array.isArray(value)) return value;
  return [];
}

function firstProductImageFromMedia(value: any): string | null {
  if (!value) return null;
  if (typeof value === "string") {
    const text = value.trim();
    return text.startsWith("http://") || text.startsWith("https://")
      ? text
      : null;
  }
  if (Array.isArray(value)) {
    for (const item of value) {
      const nested = firstProductImageFromMedia(item);
      if (nested) return nested;
    }
    return null;
  }
  if (!isObj(value)) return null;
  const direct = firstText(
    value.big,
    value.canonical_url,
    value.url,
    value.full,
    value.photo,
    value.src,
    value.c516x688,
    value.square,
    value.c246x328,
    value.tm,
    value.image,
    value.image_url,
  );
  if (direct?.startsWith("http://") || direct?.startsWith("https://")) {
    return direct;
  }
  return (
    firstProductImageFromMedia(value.photos) ??
    firstProductImageFromMedia(value.images) ??
    firstProductImageFromMedia(value.media)
  );
}

function objectValuesForKeys(sources: any[], keys: string[]): any[] {
  return sources.flatMap((source) =>
    isObj(source) ? keys.map((key) => source[key]) : [],
  );
}

function expenseAmount(sources: any[], keys: string[]): number | null {
  return firstNonZeroNumber(...objectValuesForKeys(sources, keys));
}

function wbExpenseItem({
  key,
  label,
  amount,
  detail,
  tone = "warning",
}: {
  key: string;
  label: string;
  amount: any;
  detail?: string;
  tone?: CockpitTone;
}) {
  const parsed = toFiniteNumber(amount);
  if (parsed === null || Math.abs(parsed) < 0.01) return null;
  return {
    key,
    label,
    amount: Math.abs(parsed),
    detail,
    tone,
  };
}

function blockData(section: any): any {
  return sectionData<any>(section) ?? {};
}

function formatMoneyOrDash(value: any): string {
  const n = toFiniteNumber(value);
  return n === null ? "Нет данных" : formatMoney(n);
}

function formatNumberOrDash(
  value: any,
  opts?: Intl.NumberFormatOptions,
): string {
  const n = toFiniteNumber(value);
  return n === null ? "Нет данных" : n.toLocaleString("ru-RU", opts);
}

function formatPercentOrDash(value: any): string {
  const n = toFiniteNumber(value);
  if (n === null) return "Нет данных";
  const pct = Math.abs(n) <= 1 ? n * 100 : n;
  return `${pct.toLocaleString("ru-RU", { maximumFractionDigits: 1 })}%`;
}

function formatMoneyTiny(value: any): string {
  const n = toFiniteNumber(value);
  if (n === null) return "Нет данных";
  const abs = Math.abs(n);
  if (abs >= 1_000_000)
    return `${(n / 1_000_000).toLocaleString("ru-RU", { maximumFractionDigits: 1 })} млн ₽`;
  if (abs >= 100_000)
    return `${Math.round(n / 1_000).toLocaleString("ru-RU")} тыс ₽`;
  return formatMoney(n);
}

function isClosedActionStatus(status: any): boolean {
  return [
    "done",
    "resolved",
    "ignored",
    "closed",
    "dismissed",
    "cancelled",
    "completed",
  ].includes(String(status ?? "").toLowerCase());
}

function getActionList(section: any): PortalAction[] {
  const d = sectionData<any>(section);
  const list = Array.isArray(d)
    ? d
    : Array.isArray(d?.items)
      ? d.items
      : Array.isArray(d?.actions)
        ? d.actions
        : Array.isArray(section)
          ? section
          : [];
  return list.filter((action: any) =>
    isSellerVisibleMoneyTrust(
      action.money_trust,
      action.payload?.money_trust,
      action.evidence_ledger?.money_trust,
      action.payload?.evidence_ledger?.money_trust,
    ),
  ) as PortalAction[];
}

function actionSourceLabel(action: any): string {
  const source = String(
    action?.source_module ?? action?.source ?? "",
  ).toLowerCase();
  const map: Record<string, string> = {
    finance: "Деньги",
    data_quality: "Данные",
    costs: "Себестоимость",
    checker: "Карточка",
    stockops: "Остатки",
    grouping: "Группировка",
    grouping_beta: "Группировка",
    reputation: "Репутация",
    claims: "Претензии",
    photo: "Фото",
    experiments: "A/B",
    problem_engine: "Проблема",
  };
  return map[source] ?? normalizeStatusLabel(source || action?.action_type);
}

function sourceLabel(value: any): string {
  const key = String(value ?? "")
    .toLowerCase()
    .replace(/[\s-]+/g, "_");
  const map: Record<string, string> = {
    ads: "Реклама",
    claims: "Претензии",
    claim_cases: "Претензии",
    local_claim_cases: "Претензии",
    costs: "Себестоимость",
    data_quality: "Данные",
    experiments: "A/B",
    finance: "Деньги",
    grouping: "Группировка",
    grouping_beta: "Группировка",
    photo: "Фото",
    photo_studio: "Фото",
    pricing: "Цена",
    reputation: "Репутация",
    stock: "Остатки",
    stockops: "Остатки",
  };
  return map[key] ?? normalizeStatusLabel(value);
}

function severityTone(value: any): CockpitTone {
  const key = String(value ?? "").toLowerCase();
  if (["critical", "p0", "bad", "error", "failed"].includes(key))
    return "danger";
  if (["high", "p1", "warning", "risk", "blocked"].includes(key))
    return "warning";
  if (["ok", "healthy", "clean", "done"].includes(key)) return "good";
  return "info";
}

function actionTarget(action: any, nmId: string | number) {
  const source = String(
    action?.source_module ?? action?.source ?? "",
  ).toLowerCase();
  const actionText = String(
    action?.action_type ??
      action?.detector_code ??
      action?.payload?.problem_code ??
      "",
  ).toLowerCase();
  const problemInstanceId =
    action?.problem_instance_id ??
    action?.payload?.problem_instance_id ??
    action?.raw?.problem_instance_id;
  const numericNmId = Number(nmId);
  const searchNmId = Number.isFinite(numericNmId) ? numericNmId : String(nmId);
  const baseSearch = {
    nm_id: searchNmId,
    ...(problemInstanceId
      ? { problem_instance_id: String(problemInstanceId) }
      : {}),
  };
  if (source === "checker")
    return { to: "/checker/$nmId", params: { nmId: String(nmId) } };
  if (source === "data_quality" || source === "costs")
    return {
      to: "/data-fix",
      search: {
        ...baseSearch,
        ...(action?.payload?.code || action?.detector_code
          ? { code: String(action?.payload?.code ?? action?.detector_code) }
          : {}),
      },
    };
  if (source === "stockops")
    return { to: "/stock-control", search: { ...baseSearch, tab: "overview" } };
  if (source === "claims") return { to: "/claims", search: baseSearch };
  if (source === "reputation") return { to: "/reputation", search: baseSearch };
  if (source === "photo") return { to: "/photo-studio", search: baseSearch };
  if (source === "experiments") return { to: "/ab-tests", search: baseSearch };
  if (source === "grouping" || source === "grouping_beta")
    return { to: "/grouping", search: baseSearch };
  if (actionText.includes("price"))
    return { to: "/pricing", search: baseSearch };
  if (actionText.includes("ad") || actionText.includes("promo"))
    return { to: "/ads", search: { ...baseSearch, sort: "spend" } };
  return {
    to: "/action-center",
    search: {
      ...baseSearch,
      ...(action?.action_id || action?.id
        ? { action_id: String(action.action_id ?? action.id) }
        : {}),
    },
  };
}

function safeRatioPercent(
  part: number | null,
  whole: number | null,
): number | null {
  if (part === null || whole === null || whole === 0) return null;
  return (part / whole) * 100;
}

function problemTitle(item: any, fallback = "Проблема по карточке"): string {
  return String(
    item?.title ??
      item?.summary ??
      item?.message ??
      item?.business_impact ??
      item?.simple_reason ??
      item?.problem_code ??
      item?.code ??
      fallback,
  );
}

function buildProblemItems({
  actions,
  business,
  dataQuality,
  cardQuality,
  problemInstances,
  nmId,
}: {
  actions: any[];
  business: any;
  dataQuality: any;
  cardQuality: any;
  problemInstances: any[];
  nmId: string | number;
}) {
  const items: any[] = [];
  const seen = new Set<string>();
  const push = (item: any) => {
    const key = `${item.source}:${item.title}`.toLowerCase();
    if (seen.has(key)) return;
    seen.add(key);
    items.push(item);
  };

  actions.slice(0, 8).forEach((action) => {
    push({
      title: problemTitle(action, "Действие по товару"),
      detail: firstText(action.reason, action.next_step, action.status_reason),
      source: actionSourceLabel(action),
      tone: severityTone(action.severity ?? action.priority),
      amount: firstNumber(
        action.expected_effect_amount,
        action.expected_impact_amount,
      ),
      link: actionTarget(action, nmId),
    });
  });

  asArray(business?.open)
    .slice(0, 5)
    .forEach((item) => {
      push({
        title: problemTitle(item),
        detail: firstText(item.reason, item.next_step, item.description),
        source: "Диагностика",
        tone: severityTone(item.severity ?? item.priority),
        amount: firstNumber(
          item.expected_effect_amount,
          item.money_impact_amount,
        ),
        link: { to: "/action-center", search: { nm_id: String(nmId) } },
      });
    });

  problemInstances.slice(0, 5).forEach((item) => {
    if (isClosedActionStatus(item?.status ?? item?.result_status)) return;
    push({
      title: problemTitle(item),
      detail: firstText(item.summary, item.result_summary, item.next_step),
      source: "Проблема",
      tone: severityTone(item.severity ?? item.priority),
      amount: firstNumber(
        item.money_impact_amount,
        item.expected_effect_amount,
      ),
      link: { to: "/action-center", search: { nm_id: String(nmId) } },
    });
  });

  asArray(cardQuality?.issues)
    .slice(0, 4)
    .forEach((issue) => {
      push({
        title: problemTitle(issue, "Проблема качества карточки"),
        detail: firstText(
          issue.recommended_fix,
          issue.business_explanation,
          issue.description,
        ),
        source: "Карточка",
        tone: severityTone(issue.severity),
        link: { to: "/checker/$nmId", params: { nmId: String(nmId) } },
      });
    });

  asArray(dataQuality?.issues)
    .slice(0, 4)
    .forEach((issue) => {
      push({
        title: problemTitle(issue, "Проблема данных"),
        detail: firstText(
          issue.recommended_fix,
          issue.first_action,
          issue.message,
        ),
        source: "Данные",
        tone: severityTone(issue.severity),
        link: {
          to: "/data-fix",
          search: {
            nm_id: String(nmId),
            ...(issue?.code ? { code: String(issue.code) } : {}),
          },
        },
      });
    });

  return items;
}

function getProductCockpit(data: any, nmId: string | number) {
  const rawIdentity = blockData(data?.identity);
  const productIdentity = isObj(data?.product_identity)
    ? data.product_identity
    : {};
  const identity = { ...rawIdentity, ...productIdentity };

  const moneyBlock = blockData(data?.money);
  const summary = isObj(moneyBlock.summary) ? moneyBlock.summary : {};
  const money = isObj(moneyBlock.money) ? moneyBlock.money : moneyBlock;
  const kpis = isObj(moneyBlock.kpis) ? moneyBlock.kpis : {};
  const profitObj = isObj(money?.profit) ? money.profit : {};
  const variants = isObj(moneyBlock.profit_variants)
    ? moneyBlock.profit_variants
    : {};
  const articleAudit = isObj(moneyBlock.article_audit)
    ? moneyBlock.article_audit
    : {};
  const auditPrice = isObj(articleAudit.price) ? articleAudit.price : {};
  const auditFinance = isObj(articleAudit.finance) ? articleAudit.finance : {};
  const moneyWbExpenses = isObj(money?.wb_expenses) ? money.wb_expenses : {};
  const unitEconomics = isObj(money.unit_economics) ? money.unit_economics : {};
  const moneyOperations = isObj(moneyBlock.operations)
    ? moneyBlock.operations
    : {};
  const moneyFinance = isObj(moneyBlock.finance) ? moneyBlock.finance : {};
  const moneyStock = isObj(moneyBlock.stock) ? moneyBlock.stock : {};

  const costsBlock = blockData(data?.costs ?? data?.cost);
  const cogs = isObj(costsBlock.cogs) ? costsBlock.cogs : {};
  const expenseBreakdown = isObj(costsBlock.expense_breakdown)
    ? costsBlock.expense_breakdown
    : isObj(moneyBlock.expense_breakdown)
      ? moneyBlock.expense_breakdown
      : {};
  const directExpenseBreakdown = isObj(expenseBreakdown.direct_expenses)
    ? expenseBreakdown.direct_expenses
    : {};

  const adsBlock = blockData(data?.ads);
  const moneyAds = isObj(moneyBlock.ads)
    ? moneyBlock.ads
    : isObj(money?.ads)
      ? money.ads
      : {};
  const adsSummary = isObj(data?.ads_summary) ? data.ads_summary : {};

  const stockBlock = blockData(data?.stock);
  const stockSummary = isObj(data?.stock_summary) ? data.stock_summary : {};
  const stockops = isObj(stockBlock.stockops) ? stockBlock.stockops : {};

  const pricing = blockData(data?.pricing ?? data?.price);
  const cardQuality = blockData(data?.card_quality ?? data?.quality);
  const checkerSummary = isObj(data?.checker_summary)
    ? data.checker_summary
    : {};
  const dataQuality = blockData(data?.data_quality);
  const business = blockData(data?.business_issues);
  const healthSummary = isObj(data?.health_summary) ? data.health_summary : {};

  const actions = getActionList(data?.actions);
  const openActions = actions.filter(
    (action) => !isClosedActionStatus(action.status),
  );
  const problemInstances = asArray(data?.problem_instances);

  const revenue = firstNumber(
    summary.revenue,
    money.revenue,
    kpis.revenue,
    moneyBlock.revenue,
  );
  const forPay = firstNumber(summary.for_pay, money.for_pay, kpis.for_pay);
  const profit = firstNumber(
    summary.estimated_profit,
    kpis.net_profit_after_all_expenses,
    profitObj.net_profit_after_all_expenses,
    variants.after_allocated_ads,
    variants.after_source_ads,
    profitObj.after_ads,
    money.net_profit,
    money.profit,
    moneyBlock.profit,
  );
  const margin = firstNumber(
    summary.margin_percent,
    profitObj.margin_after_ads_percent,
    money.margin_percent,
    moneyBlock.margin,
  );
  const roi = firstNumber(
    summary.roi_percent,
    profitObj.roi_after_ads_percent,
    money.roi_percent,
  );
  const unitCost = firstNumber(
    cogs.unit_cost,
    cogs.cost_price,
    costsBlock.unit_cost,
    money?.cogs?.unit_cost,
  );
  const cogsAmount = firstNumber(
    cogs.estimated_cogs,
    costsBlock.estimated_cogs,
    money?.cogs?.estimated_cogs,
    money.cogs_amount,
  );

  const logisticsDirect =
    firstNumber(
      moneyWbExpenses.logistics,
      money.logistics,
      expenseBreakdown.logistics_total,
      moneyWbExpenses.logistics_total,
      auditFinance.logistics_total,
    ) ??
    sumPresent(
      firstNumber(
        moneyWbExpenses.wb_logistics,
        auditFinance.wb_logistics,
        money.wb_logistics,
      ),
      firstNumber(
        moneyWbExpenses.wb_logistics_rebill,
        auditFinance.wb_logistics_rebill,
        money.wb_logistics_rebill,
      ),
    );
  const wbExpensesTotal = firstNumber(
    moneyWbExpenses.direct,
    moneyWbExpenses.total_wb_expenses,
    money.wb_expenses_total,
    money.total_wb_expenses,
    auditFinance.total_wb_expenses,
    expenseBreakdown.total_wb_expenses,
  );
  const logisticsStatus = firstText(
    moneyWbExpenses.logistics_mapping_status,
    moneyWbExpenses.status,
    auditFinance.logistics_mapping_status,
    expenseBreakdown.logistics_mapping_status,
    money.logistics_mapping_status,
  );
  const wbExpenseSources = [
    moneyWbExpenses,
    directExpenseBreakdown,
    expenseBreakdown,
    auditFinance,
    money,
  ];
  const wbExpenseItems = [
    wbExpenseItem({
      key: "wb_commission",
      label: "Комиссия WB",
      amount: expenseAmount(wbExpenseSources, ["wb_commission", "commission"]),
      detail: "Комиссия площадки за продажи",
      tone: "warning",
    }),
    wbExpenseItem({
      key: "payment_processing",
      label: "Эквайринг",
      amount: expenseAmount(wbExpenseSources, [
        "payment_processing",
        "acquiring_fee",
      ]),
      detail: "Оплата и обработка платежей",
      tone: "warning",
    }),
    wbExpenseItem({
      key: "pvz_reward",
      label: "ПВЗ",
      amount: expenseAmount(wbExpenseSources, ["pvz_reward"]),
      detail: "Вознаграждение пункта выдачи",
      tone: "warning",
    }),
    wbExpenseItem({
      key: "logistics",
      label: "Логистика WB",
      amount: logisticsDirect,
      detail: logisticsStatus
        ? expenseStatusLabel(logisticsStatus)
        : "Доставка, возвраты и перевыставленная логистика",
      tone: "info",
    }),
    wbExpenseItem({
      key: "acceptance",
      label: "Приемка",
      amount: expenseAmount(wbExpenseSources, [
        "acceptance",
        "paid_acceptance",
      ]),
      detail: "Платная приемка поставок",
      tone: "warning",
    }),
    wbExpenseItem({
      key: "storage",
      label: "Хранение",
      amount: expenseAmount(wbExpenseSources, ["storage"]),
      detail: "Хранение на складах WB",
      tone: "warning",
    }),
    wbExpenseItem({
      key: "penalty",
      label: "Штрафы",
      amount: expenseAmount(wbExpenseSources, ["penalty", "penalties"]),
      detail: "Штрафы из финансового отчета",
      tone: "danger",
    }),
    wbExpenseItem({
      key: "deduction",
      label: "Удержания",
      amount: expenseAmount(wbExpenseSources, ["deduction", "deductions"]),
      detail: "Прочие удержания WB",
      tone: "danger",
    }),
    wbExpenseItem({
      key: "loyalty",
      label: "Лояльность и кешбэк",
      amount: expenseAmount(wbExpenseSources, ["loyalty"]),
      detail: "Скидки/кешбэк, прошедшие как расход WB",
      tone: "warning",
    }),
    wbExpenseItem({
      key: "marketing_deduction",
      label: "Продвижение WB",
      amount: expenseAmount(wbExpenseSources, ["marketing_deduction"]),
      detail: "Маркетинговые удержания из финансового отчета",
      tone: "warning",
    }),
    wbExpenseItem({
      key: "other_wb_expenses",
      label: "Прочие WB расходы",
      amount: expenseAmount(wbExpenseSources, [
        "other_wb_expenses",
        "wb_other",
        "unclassified_wb_expenses",
        "unclassified",
      ]),
      detail: "Неразобранные или редкие категории отчета",
      tone: "muted",
    }),
  ].filter(Boolean);
  const wbExpenseKnownTotal = wbExpenseItems.reduce(
    (sum: number, item: any) =>
      sum + Math.abs(toFiniteNumber(item.amount) ?? 0),
    0,
  );
  const wbExpenseRemainder =
    wbExpensesTotal !== null &&
    Math.abs(wbExpensesTotal) - wbExpenseKnownTotal > 1
      ? Math.abs(wbExpensesTotal) - wbExpenseKnownTotal
      : null;
  if (wbExpenseRemainder !== null) {
    wbExpenseItems.push(
      wbExpenseItem({
        key: "remainder",
        label: "Прочее / разница",
        amount: wbExpenseRemainder,
        detail: "Остаток до суммы Расходы WB",
        tone: "muted",
      }),
    );
  }
  const wbExpenseAccountLevel = firstNonZeroNumber(
    moneyWbExpenses.account_level,
    expenseBreakdown.account_level_total,
    auditFinance.account_level,
    money.account_level_wb_expenses,
  );
  const wbExpenseUnallocated = firstNonZeroNumber(
    moneyWbExpenses.unallocated,
    expenseBreakdown.unallocated_total,
    auditFinance.unallocated,
    money.unallocated_wb_expenses,
  );
  const wbExpenseAccountLevelLogistics = firstNonZeroNumber(
    moneyWbExpenses.account_level_logistics,
    expenseBreakdown.account_level_logistics,
    auditFinance.account_level_logistics,
  );
  const wbExpenseUnallocatedLogistics = firstNonZeroNumber(
    moneyWbExpenses.unallocated_logistics,
    expenseBreakdown.unallocated_logistics,
    auditFinance.unallocated_logistics,
  );
  const wbExpenseMessage = firstText(
    expenseBreakdown.message,
    expenseBreakdown.not_linked_reason,
    moneyWbExpenses.reason,
    auditFinance.wb_expenses_reason,
  );

  const adsSpend = firstNumber(
    adsBlock.final_spend,
    adsBlock.spend,
    adsBlock.allocated_spend,
    moneyAds.final_spend,
    moneyAds.spend,
    moneyAds.allocated_spend,
    adsSummary.spend,
  );
  const adsSourceSpend = firstNumber(
    adsBlock.source_spend,
    adsBlock.raw_spend,
    moneyAds.source_spend,
    moneyAds.raw_allocated_spend,
  );
  const adsAllocated = firstNumber(
    adsBlock.allocated_spend,
    moneyAds.allocated_spend,
  );
  const adsUnallocated = firstNumber(
    adsBlock.unallocated_spend,
    adsBlock.unallocated,
    moneyAds.unallocated_spend,
  );
  const adsOverallocated = firstNumber(
    adsBlock.overallocated_spend,
    adsBlock.overallocated,
    moneyAds.overallocated_spend,
  );
  const adsDrr =
    firstNumber(
      adsBlock.drr_percent,
      adsBlock.drr,
      moneyAds.drr_percent,
      moneyAds.drr,
    ) ?? safeRatioPercent(adsSpend, revenue);
  const adsViews = firstNumber(
    adsBlock.views,
    moneyAds.views,
    adsSummary.views,
  );
  const adsClicks = firstNumber(
    adsBlock.clicks,
    moneyAds.clicks,
    adsSummary.clicks,
  );
  const adsOrders = firstNumber(
    adsBlock.orders,
    moneyAds.orders,
    adsSummary.orders,
  );
  const soldUnits = firstNumber(
    summary.net_units,
    summary.units_sold,
    summary.sales_units,
    moneyOperations.net_units,
    moneyOperations.units_sold,
    moneyOperations.final_net_qty,
    moneyFinance.net_units,
    auditFinance.net_units,
    money.net_units,
    money.units_sold,
    money.sales_units,
    kpis.net_units,
    moneyBlock.net_units,
    unitEconomics.net_units,
  );
  const salesCount = firstNumber(
    moneyOperations.sales_count,
    moneyOperations.sales,
    money.sales_count,
    kpis.sales_count,
    summary.sales_count,
  );
  const ordersCount = firstNumber(
    moneyOperations.orders_count,
    moneyOperations.orders,
    adsOrders,
    money.orders_count,
    kpis.orders_count,
  );
  const returnsCount = firstNumber(
    moneyOperations.returns_count,
    moneyOperations.returns,
    money.returns_count,
    kpis.returns_count,
  );
  const adsAllocationStatus = firstText(
    adsBlock.allocation_status,
    adsBlock.profit_allocation_status,
    moneyAds.allocation_status,
    sectionStatus(data?.ads),
  );

  const priceDiscount = firstNumber(
    pricing.discount,
    auditPrice.discount,
    unitEconomics.discount,
  );
  const unitReferencePrice = firstNumber(
    unitEconomics.current_discounted_price,
    unitEconomics.price,
    unitEconomics.reference_price,
    unitEconomics.average_sale_price,
  );
  const derivedCurrentPrice =
    unitReferencePrice !== null &&
    priceDiscount !== null &&
    priceDiscount > 0 &&
    priceDiscount < 99
      ? unitReferencePrice / (1 - priceDiscount / 100)
      : null;
  const basePrice = firstNumber(
    productIdentity.price,
    pricing.current_price,
    pricing.price,
    identity.price,
    money.current_price,
    money.price,
    derivedCurrentPrice,
    unitEconomics.current_price,
    unitReferencePrice,
  );
  const discountedPrice = firstNumber(
    pricing.current_discounted_price,
    pricing.price_after_discount,
    pricing.discounted_price,
    pricing.sale_price,
    auditPrice.current_discounted_price,
    productIdentity.discounted_price,
    unitEconomics.current_discounted_price,
    unitReferencePrice,
  );
  const currentPrice = discountedPrice ?? basePrice;
  const breakEvenPrice = firstNumber(
    pricing.break_even_price_final,
    pricing.break_even_price,
    pricing.break_even_price_estimated,
    pricing.safe_price,
    pricing.min_safe_price,
    pricing.recommended_min_price,
    auditPrice.break_even_price_final,
    auditPrice.break_even_price,
    auditPrice.break_even_price_estimated,
    unitEconomics.break_even_price,
  );
  const targetMarginPrice = firstNumber(
    pricing.target_margin_price_final,
    pricing.target_margin_price,
    pricing.target_margin_price_estimated,
    pricing.target_price,
    pricing.recommended_price,
    auditPrice.target_margin_price_final,
    auditPrice.target_margin_price,
    auditPrice.target_margin_price_estimated,
    unitEconomics.target_margin_price,
  );
  const estimatedMarginPercent = firstNumber(
    pricing.estimated_margin_percent,
    pricing.estimated_margin_at_current_price,
    auditPrice.estimated_margin_percent,
    unitEconomics.estimated_margin_percent,
  );
  const priceConfidence = firstText(
    pricing.confidence,
    auditPrice.confidence,
    unitEconomics.confidence,
  );
  const priceGap =
    currentPrice !== null && breakEvenPrice !== null
      ? currentPrice - breakEvenPrice
      : null;
  const rawPriceStatus =
    sectionStatus(data?.pricing) ??
    firstText(pricing.status, pricing.calc_state, pricing.calculation_state);
  const priceStatus =
    currentPrice !== null &&
    ["unavailable", "empty", "not_configured", "disabled"].includes(
      String(rawPriceStatus ?? "").toLowerCase(),
    )
      ? "price_only"
      : (rawPriceStatus ??
        (currentPrice === null
          ? "empty"
          : priceGap !== null && priceGap < 0
            ? "warning"
            : "ok"));

  const quantity = firstNumber(
    stockBlock.quantity,
    stockBlock.qty,
    stockBlock.stock_qty,
    stockBlock.available,
    stockBlock.total,
    stockSummary.total_stock_units,
    productIdentity.stock,
  );
  const quantityFull = firstNumber(
    stockBlock.quantity_full,
    stockBlock.full_quantity,
    stockBlock.total_quantity,
  );
  const inTransit =
    sumPresent(stockBlock.in_way_to_client, stockBlock.in_way_from_client) ??
    firstNumber(stockBlock.in_transit, stockops.in_transit);
  const daysOfStock = firstNumber(
    stockBlock.days_of_stock,
    stockBlock.days_left,
    stockBlock.cover_days,
    stockops.days_of_stock,
    moneyStock.days_of_stock,
  );
  const salesVelocity = firstNumber(
    stockBlock.sales_velocity_daily,
    stockBlock.sales_velocity,
    stockBlock.velocity_daily,
    stockops.sales_velocity_daily,
    stockops.sales_velocity,
    stockSummary.sales_velocity_daily,
    moneyStock.sales_velocity_daily,
  );
  const stockRows = firstNumber(
    stockBlock.rows_count,
    stockBlock.row_count,
    stockops.rows_count,
  );

  const cardIssues = asArray(cardQuality.issues);
  const criticalIssueCount =
    firstNumber(
      cardQuality.critical_issue_count,
      cardQuality.summary?.critical_count,
    ) ??
    cardIssues.filter(
      (issue) => String(issue?.severity ?? "").toLowerCase() === "critical",
    ).length;
  const warningIssueCount =
    firstNumber(
      cardQuality.warning_issue_count,
      cardQuality.summary?.warning_count,
    ) ??
    cardIssues.filter(
      (issue) => String(issue?.severity ?? "").toLowerCase() === "warning",
    ).length;
  const cardIssueCount =
    firstNumber(
      cardQuality.issue_count,
      cardQuality.open_issue_count,
      cardQuality.total_issues,
      checkerSummary.open_issue_count,
    ) ??
    cardIssues.length ??
    (criticalIssueCount ?? 0) + (warningIssueCount ?? 0);
  const cardScore = firstNumber(
    cardQuality.score,
    cardQuality.checker_score,
    checkerSummary.score,
  );
  const cardStatus =
    sectionStatus(data?.card_quality ?? data?.quality) ??
    firstText(cardQuality.status, checkerSummary.status) ??
    (cardIssueCount > 0 ? "warning" : "ok");

  const dqIssues = [
    ...asArray(dataQuality.issues),
    ...asArray(dataQuality.problems),
    ...asArray(data?.data_issues),
  ];
  const healthDataBlockers = firstNumber(healthSummary.data_blocker_count);
  const healthOpenProblems = firstNumber(healthSummary.open_problem_count);
  const healthCriticalProblems = firstNumber(
    healthSummary.critical_problem_count,
  );
  const healthStatusRaw = firstText(healthSummary.status);
  const dqBlockers = healthDataBlockers ?? asArray(dataQuality.blockers).length;
  const dqWarnings = asArray(dataQuality.warnings).length;
  const dataIssueCount =
    firstNumber(
      dataQuality.issue_count,
      dataQuality.open_issue_count,
      dataQuality.count,
    ) ?? dqIssues.length;
  const dataStatus =
    healthDataBlockers !== null && healthDataBlockers > 0
      ? "blocked"
      : (sectionStatus(data?.data_quality) ??
        firstText(
          dataQuality.status,
          dataQuality.state,
          dataQuality.trust?.status,
        ) ??
        (dqBlockers > 0 ? "blocked" : dataIssueCount > 0 ? "warning" : "ok"));

  const businessSummary = isObj(business.summary) ? business.summary : {};
  const businessOpenCount =
    firstNumber(
      healthOpenProblems,
      businessSummary.open_count,
      business.open_count,
      business.count,
    ) ?? asArray(business.open).length;

  const reputation = blockData(data?.reputation);
  const reputationItems = asArray(reputation.items);
  const reviewsCount =
    firstNumber(
      reputation.reviews_count,
      reputationItems.filter((it) => it.item_type === "review").length,
    ) ?? null;
  const questionsCount =
    firstNumber(
      reputation.questions_count,
      reputationItems.filter((it) => it.item_type === "question").length,
    ) ?? null;
  const unansweredReputation = firstNumber(
    reputation.unanswered_count,
    reputation.unanswered_reviews_count,
    reputation.negative_unanswered_count,
  );
  const rating = firstNumber(
    reputation.rating,
    reputation.avg_rating,
    reputation.average_rating,
  );

  const claims = blockData(data?.claims);
  const claimsCases =
    asArray(claims.cases).length || asArray(claims.local_cases).length;
  const claimsCandidates = firstNumber(
    claims.candidate_count,
    asArray(claims.candidates).length,
  );
  const claimsOpen = firstNumber(
    claims.open_cases_count,
    claims.local_cases_count,
    claimsCases,
  );
  const claimsPotential = firstNumber(claims.potential_compensation_amount);

  const photo = blockData(data?.photo_studio ?? data?.photo);
  const photoStatus =
    sectionStatus(data?.photo_studio ?? data?.photo) ??
    firstText(photo.status, photo.generation_status);
  const photoSources = firstNumber(photo.wb_sources_count, photo.sources_count);
  const photoVersions = firstNumber(
    photo.versions_count,
    photo.generated_count,
  );
  const photoIssues = asArray(photo.issues).length;

  const grouping = blockData(data?.grouping ?? data?.grouping_beta);
  const groupingItems =
    asArray(grouping.recommendations).length || asArray(grouping.items).length;
  const groupingCount = firstNumber(
    grouping.recommendations_count,
    grouping.recommendation_count,
    grouping.count,
    groupingItems,
  );

  const experiments = blockData(data?.experiments);
  const experimentItems =
    asArray(experiments.items).length ||
    asArray(experiments.experiments).length;
  const experimentSummary = isObj(experiments.summary)
    ? experiments.summary
    : {};
  const activeExperiments = firstNumber(
    experimentSummary.active_count,
    experimentSummary.running_count,
    experiments.active_count,
    experimentItems,
  );

  const problems = buildProblemItems({
    actions: openActions,
    business,
    dataQuality: { ...dataQuality, issues: dqIssues },
    cardQuality,
    problemInstances,
    nmId,
  });

  const inferredHealthStatus =
    healthStatusRaw ??
    ((profit !== null && profit < 0) ||
    String(cardStatus).toLowerCase() === "critical" ||
    String(dataStatus).toLowerCase() === "blocked"
      ? "critical"
      : problems.length > 0 ||
          cardIssueCount > 0 ||
          dataIssueCount > 0 ||
          (adsOverallocated ?? 0) > 0 ||
          (adsUnallocated ?? 0) > 0
        ? "warning"
        : "ok");
  const healthTone: CockpitTone =
    ["blocked", "critical", "bad", "error", "failed"].includes(
      String(inferredHealthStatus).toLowerCase(),
    ) ||
    (healthCriticalProblems ?? 0) > 0 ||
    (profit !== null && profit < 0)
      ? "danger"
      : String(inferredHealthStatus).toLowerCase() === "warning" ||
          problems.length > 0 ||
          cardIssueCount > 0 ||
          dataIssueCount > 0 ||
          (adsOverallocated ?? 0) > 0 ||
          (adsUnallocated ?? 0) > 0
        ? "warning"
        : "good";

  return {
    identity: {
      title:
        firstText(identity.title, identity.name, `Артикул ${nmId}`) ??
        `Артикул ${nmId}`,
      nmId: String(firstText(identity.nm_id, nmId) ?? nmId),
      vendorCode: firstText(
        identity.vendor_code,
        identity.article,
        identity.seller_article,
      ),
      brand: firstText(identity.brand),
      subject: firstText(
        identity.subject_name,
        identity.category,
        identity.subject,
      ),
      barcode: firstText(identity.barcode),
      image: firstText(
        identity.image,
        identity.image_url,
        identity.photo_url,
        identity.photo,
        identity.thumbnail,
        firstProductImageFromMedia(identity.photos),
        firstProductImageFromMedia(identity.images),
        firstProductImageFromMedia(identity.media),
      ),
    },
    healthTone,
    healthStatus: inferredHealthStatus,
    money: {
      revenue,
      forPay,
      profit,
      margin,
      roi,
      soldUnits,
      salesCount,
      ordersCount,
      returnsCount,
      unitCost,
      cogsAmount,
      wbExpensesTotal,
      logisticsDirect,
      logisticsStatus,
      wbExpenseItems,
      wbExpenseAccountLevel,
      wbExpenseUnallocated,
      wbExpenseAccountLevelLogistics,
      wbExpenseUnallocatedLogistics,
      wbExpenseMessage,
    },
    ads: {
      spend: adsSpend,
      sourceSpend: adsSourceSpend,
      allocated: adsAllocated,
      unallocated: adsUnallocated,
      overallocated: adsOverallocated,
      drr: adsDrr,
      views: adsViews,
      clicks: adsClicks,
      orders: adsOrders,
      allocationStatus: adsAllocationStatus,
      status:
        sectionStatus(data?.ads) ??
        firstText(adsBlock.status, adsAllocationStatus),
    },
    price: {
      current: currentPrice,
      base: basePrice,
      discounted: discountedPrice,
      breakEven: breakEvenPrice,
      target: targetMarginPrice,
      gap: priceGap,
      status: priceStatus,
      moduleStatus: rawPriceStatus,
      discount: priceDiscount,
      estimatedMargin: estimatedMarginPercent,
      confidence: priceConfidence,
    },
    stock: {
      quantity,
      quantityFull,
      inTransit,
      daysOfStock,
      salesVelocity,
      rows: stockRows,
      status: sectionStatus(data?.stock) ?? firstText(stockBlock.status),
    },
    quality: {
      score: cardScore,
      status: cardStatus,
      issueCount: cardIssueCount,
      criticalIssueCount,
      warningIssueCount,
    },
    dataQuality: {
      status: dataStatus,
      issueCount: dataIssueCount,
      blockers: dqBlockers,
      warnings: dqWarnings,
    },
    business: {
      openCount: businessOpenCount,
    },
    reputation: {
      status: sectionStatus(data?.reputation) ?? firstText(reputation.status),
      reviewsCount,
      questionsCount,
      unanswered: unansweredReputation,
      rating,
    },
    claims: {
      status: sectionStatus(data?.claims) ?? firstText(claims.status),
      open: claimsOpen,
      candidates: claimsCandidates,
      potential: claimsPotential,
    },
    photo: {
      status: photoStatus,
      sources: photoSources,
      versions: photoVersions,
      issues: photoIssues,
    },
    grouping: {
      status:
        sectionStatus(data?.grouping ?? data?.grouping_beta) ??
        firstText(grouping.status, grouping.state),
      count: groupingCount,
    },
    experiments: {
      status: sectionStatus(data?.experiments) ?? firstText(experiments.status),
      active: activeExperiments,
    },
    actions: {
      total: actions.length,
      open: openActions.length,
      items: openActions,
    },
    problems,
    unavailable: asArray(data?.unavailable_sources),
  };
}

function CockpitMetric({
  icon,
  label,
  value,
  detail,
  tone = "default",
}: {
  icon: ReactNode;
  label: string;
  value: ReactNode;
  detail?: ReactNode;
  tone?: CockpitTone;
}) {
  return (
    <div
      className={cn(
        "relative min-h-[78px] overflow-hidden rounded-md border p-2.5 shadow-sm transition-colors before:absolute before:inset-x-0 before:top-0 before:h-0.5",
        COCKPIT_TONE[tone],
        COCKPIT_ACCENT_TONE[tone],
      )}
    >
      <div className="flex items-center gap-2">
        <span
          className={cn(
            "inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-md",
            COCKPIT_ICON_TONE[tone],
          )}
        >
          {icon}
        </span>
        <span className="min-w-0 truncate text-[10px] font-medium uppercase text-muted-foreground sm:text-[11px]">
          {label}
        </span>
      </div>
      <div className="mt-2 text-base font-semibold leading-none tabular-nums sm:text-lg">
        {value}
      </div>
      {detail ? (
        <div className="mt-1.5 line-clamp-2 text-[11px] leading-snug text-muted-foreground">
          {detail}
        </div>
      ) : null}
    </div>
  );
}

function MiniSignal({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="min-w-0">
      <div className="truncate text-[11px] text-muted-foreground">{label}</div>
      <div className="mt-0.5 truncate text-xs font-medium tabular-nums">
        {value}
      </div>
    </div>
  );
}

function SectionJumpCard({
  icon,
  title,
  value,
  detail,
  tone = "default",
  to,
  href,
  search,
  params,
  signals = [],
  testId,
}: {
  icon: ReactNode;
  title: string;
  value: ReactNode;
  detail?: ReactNode;
  tone?: CockpitTone;
  to: string;
  href?: string;
  search?: Record<string, any>;
  params?: Record<string, any>;
  signals?: Array<{ label: string; value: ReactNode }>;
  testId?: string;
}) {
  const className = cn(
    "group relative block overflow-hidden rounded-md border p-3 pl-4 outline-none shadow-sm transition before:absolute before:inset-y-0 before:left-0 before:w-1 hover:border-primary/45 hover:bg-primary/[0.025] hover:shadow-md focus-visible:ring-2 focus-visible:ring-ring",
    COCKPIT_TONE[tone],
    COCKPIT_ACCENT_TONE[tone],
  );
  const content = (
    <>
      <div className="flex items-start gap-3">
        <span
          className={cn(
            "inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-md",
            COCKPIT_ICON_TONE[tone],
          )}
        >
          {icon}
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex items-center justify-between gap-2">
            <div className="min-w-0 truncate text-sm font-semibold">
              {title}
            </div>
            <ExternalLink className="h-3.5 w-3.5 shrink-0 text-muted-foreground transition group-hover:text-primary" />
          </div>
          <div className="mt-1 flex flex-wrap items-baseline gap-x-2 gap-y-1">
            <span className="text-lg font-semibold leading-none tabular-nums">
              {value}
            </span>
            {detail ? (
              <span className="min-w-0 flex-1 truncate text-xs text-muted-foreground">
                {detail}
              </span>
            ) : null}
          </div>
        </div>
      </div>
      {signals.length > 0 ? (
        <div className="mt-2 grid gap-x-4 gap-y-1.5 border-t border-border/60 pt-2 sm:grid-cols-3">
          {signals.slice(0, 3).map((signal) => (
            <MiniSignal
              key={signal.label}
              label={signal.label}
              value={signal.value}
            />
          ))}
        </div>
      ) : null}
    </>
  );

  if (href) {
    return (
      <a
        href={href}
        data-testid={testId}
        className={className}
        onClick={(event) => {
          if (
            event.defaultPrevented ||
            event.button !== 0 ||
            event.metaKey ||
            event.ctrlKey ||
            event.shiftKey ||
            event.altKey
          ) {
            return;
          }
          event.preventDefault();
          window.location.assign(href);
        }}
      >
        {content}
      </a>
    );
  }

  return (
    <Link
      to={to as any}
      search={search as any}
      params={params as any}
      data-testid={testId}
      className={className}
    >
      {content}
    </Link>
  );
}

function BreakdownRow({
  label,
  value,
  max,
  tone,
  detail,
  actionLabel,
  onClick,
}: {
  label: string;
  value: number | null;
  max: number;
  tone: CockpitTone;
  detail?: string;
  actionLabel?: string;
  onClick?: () => void;
}) {
  const width =
    value === null
      ? 0
      : Math.max(7, Math.min(100, (Math.abs(value) / max) * 100));
  const barClass =
    tone === "good"
      ? "bg-success"
      : tone === "danger"
        ? "bg-destructive"
        : tone === "warning"
          ? "bg-warning"
          : tone === "info"
            ? "bg-info"
            : "bg-muted-foreground/50";
  const content = (
    <>
      <div className="flex items-center justify-between gap-3 text-sm">
        <span className="flex min-w-0 items-center gap-2 font-medium">
          <span className="truncate">{label}</span>
          {actionLabel ? (
            <span className="rounded border bg-background px-1.5 py-0.5 text-[10px] font-semibold text-muted-foreground">
              {actionLabel}
            </span>
          ) : null}
        </span>
        <span
          className={cn(
            "tabular-nums",
            value !== null && value < 0 ? "text-destructive" : "",
          )}
        >
          {formatMoneyOrDash(value)}
        </span>
      </div>
      <div className="h-2 overflow-hidden rounded bg-muted">
        <div
          className={cn("h-full rounded", barClass)}
          style={{ width: `${width}%` }}
        />
      </div>
      {detail ? (
        <div className="text-[11px] text-muted-foreground">{detail}</div>
      ) : null}
    </>
  );

  if (onClick) {
    return (
      <button
        type="button"
        className="grid w-full gap-1.5 rounded-md text-left outline-none transition hover:bg-muted/30 focus-visible:ring-2 focus-visible:ring-ring"
        onClick={onClick}
      >
        {content}
      </button>
    );
  }

  return <div className="grid gap-1.5">{content}</div>;
}

function WbExpenseDetailRow({ item, total }: { item: any; total: number }) {
  const amount = Math.abs(toFiniteNumber(item.amount) ?? 0);
  const share = total > 0 ? (amount / total) * 100 : null;
  const width = share === null ? 0 : Math.max(6, Math.min(100, share));
  const barClass =
    item.tone === "danger"
      ? "bg-destructive"
      : item.tone === "info"
        ? "bg-info"
        : item.tone === "muted"
          ? "bg-muted-foreground/45"
          : "bg-warning";

  return (
    <div className="grid gap-2 py-3 md:grid-cols-[minmax(0,1fr)_150px_96px] md:items-center">
      <div className="min-w-0 pr-2">
        <div className="flex min-w-0 items-center gap-2">
          <span className={cn("h-2 w-2 shrink-0 rounded-full", barClass)} />
          <div className="truncate text-sm font-medium">{item.label}</div>
        </div>
        {item.detail ? (
          <div className="mt-0.5 truncate pl-4 text-[11px] text-muted-foreground">
            {item.detail}
          </div>
        ) : null}
      </div>
      <div className="min-w-0">
        <div className="h-1.5 overflow-hidden rounded-full bg-muted/70">
          <div
            className={cn("h-full rounded-full", barClass)}
            style={{ width: `${width}%` }}
          />
        </div>
        {share !== null ? (
          <div className="mt-1 text-right text-[10px] text-muted-foreground tabular-nums">
            {share.toLocaleString("ru-RU", { maximumFractionDigits: 1 })}%
          </div>
        ) : null}
      </div>
      <div className="text-right text-sm font-semibold tabular-nums text-destructive">
        {formatMoney(-amount)}
      </div>
    </div>
  );
}

function ExpenseStackBar({ items, total }: { items: any[]; total: number }) {
  const visible = items
    .map((item) => ({
      ...item,
      amount: Math.abs(toFiniteNumber(item.amount) ?? 0),
    }))
    .filter((item) => item.amount > 0.01);

  if (!visible.length || total <= 0) return null;

  return (
    <div className="mt-4 flex h-3 overflow-hidden rounded-full bg-muted/70">
      {visible.slice(0, 8).map((item) => {
        const width = Math.max(2, (item.amount / total) * 100);
        const className =
          item.tone === "danger"
            ? "bg-destructive"
            : item.tone === "info"
              ? "bg-info"
              : item.tone === "muted"
                ? "bg-muted-foreground/55"
                : "bg-warning";
        return (
          <div
            key={item.key}
            className={className}
            style={{ width: `${width}%` }}
            title={`${item.label}: ${formatMoney(-item.amount)}`}
          />
        );
      })}
    </div>
  );
}

function WbExpenseDetailPanel({ cockpit }: { cockpit: any }) {
  const total = Math.abs(toFiniteNumber(cockpit.money.wbExpensesTotal) ?? 0);
  const items = cockpit.money.wbExpenseItems ?? [];
  const hasStoreLevelExpenseInfo = [
    cockpit.money.wbExpenseAccountLevel,
    cockpit.money.wbExpenseUnallocated,
    cockpit.money.wbExpenseAccountLevelLogistics,
    cockpit.money.wbExpenseUnallocatedLogistics,
  ].some((value) => Math.abs(toFiniteNumber(value) ?? 0) > 0.01);
  const itemVisualTotal = Math.max(
    total,
    ...items.map((item: any) => Math.abs(toFiniteNumber(item.amount) ?? 0)),
    items.reduce(
      (sum: number, item: any) =>
        sum + Math.abs(toFiniteNumber(item.amount) ?? 0),
      0,
    ),
    1,
  );

  return (
    <div
      id="wb-expenses-breakdown"
      className="scroll-mt-24 border-t border-border/50 px-1 pt-4"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="text-sm font-semibold">Состав расходов WB</div>
          <div className="mt-0.5 text-xs text-muted-foreground">
            Финансовые удержания, которые относятся к этой карточке.
          </div>
        </div>
        <div className="text-right">
          <div className="text-[10px] font-semibold uppercase text-muted-foreground">
            Итого
          </div>
          <div className="mt-0.5 text-base font-semibold tabular-nums text-destructive">
            {formatMoney(-total)}
          </div>
        </div>
      </div>
      <div>
        <ExpenseStackBar items={items} total={itemVisualTotal} />
      </div>

      {items.length ? (
        <div className="mt-2 divide-y divide-border/55">
          {items.map((item: any) => (
            <WbExpenseDetailRow
              key={item.key}
              item={item}
              total={itemVisualTotal}
            />
          ))}
        </div>
      ) : (
        <div className="mt-3 rounded-xl bg-muted/25 p-3 text-sm text-muted-foreground">
          По этой карточке есть только общая сумма WB расходов без разбивки по
          категориям.
        </div>
      )}

      {hasStoreLevelExpenseInfo ? (
        <div className="mt-3 flex gap-2 border-l-2 border-info/50 bg-info/5 px-3 py-2.5 text-xs leading-5 text-muted-foreground">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-info" />
          <div>
            Часть расходов WB пришла общим платежом по магазину. Мы не смешиваем
            их с экономикой этой карточки: выше показаны только суммы, которые
            можно уверенно отнести к товару.
          </div>
        </div>
      ) : null}
    </div>
  );
}

function MoneyStatementRow({
  label,
  value,
  max,
  tone,
  detail,
  actionLabel,
  onClick,
}: {
  label: string;
  value: number | null;
  max: number;
  tone: CockpitTone;
  detail?: string;
  actionLabel?: string;
  onClick?: () => void;
}) {
  const width =
    value === null
      ? 0
      : Math.max(5, Math.min(100, (Math.abs(value) / max) * 100));
  const barClass =
    tone === "good"
      ? "bg-success"
      : tone === "danger"
        ? "bg-destructive"
        : tone === "warning"
          ? "bg-warning"
          : tone === "info"
            ? "bg-info"
            : "bg-muted-foreground/50";
  const valueClass =
    value !== null && value < 0
      ? "text-destructive"
      : tone === "good"
        ? "text-success"
        : "text-foreground";
  const content = (
    <div className="grid gap-2 border-b border-border/55 py-3 last:border-b-0 md:grid-cols-[168px_minmax(0,1fr)_126px] md:items-center">
      <div className="min-w-0">
        <div className="flex min-w-0 items-center gap-2">
          <span
            className={cn("h-2 w-2 shrink-0 rounded-full", barClass)}
            aria-hidden="true"
          />
          <span className="truncate text-sm font-medium">{label}</span>
        </div>
        {detail ? (
          <div className="mt-0.5 truncate pl-4 text-[11px] text-muted-foreground">
            {detail}
          </div>
        ) : null}
      </div>

      <div className="min-w-0">
        <div className="h-1.5 overflow-hidden rounded-full bg-muted/70">
          <div
            className={cn("h-full rounded-full", barClass)}
            style={{ width: `${width}%` }}
          />
        </div>
      </div>

      <div className="flex items-center justify-end gap-2">
        {actionLabel ? (
          <span className="rounded-full bg-muted/70 px-2 py-0.5 text-[10px] font-medium text-muted-foreground">
            {actionLabel}
          </span>
        ) : null}
        <span className={cn("text-sm font-semibold tabular-nums", valueClass)}>
          {formatMoneyOrDash(value)}
        </span>
      </div>
    </div>
  );

  if (!onClick) return content;

  return (
    <button
      type="button"
      className="block w-full text-left outline-none transition hover:bg-muted/25 focus-visible:ring-2 focus-visible:ring-ring"
      onClick={onClick}
    >
      {content}
    </button>
  );
}

function MoneyBreakdownPanel({ cockpit }: { cockpit: any }) {
  const [detailsOpen, setDetailsOpen] = useState(false);
  const revenue = cockpit.money.revenue;
  const cogsAmount = cockpit.money.cogsAmount;
  const wbExpenses = cockpit.money.wbExpensesTotal;
  const logistics = cockpit.money.logisticsDirect;
  const adsSpend = cockpit.ads.spend;
  const profit = cockpit.money.profit;
  const hasWbExpenseDetails = (cockpit.money.wbExpenseItems?.length ?? 0) > 0;
  const max = Math.max(
    1,
    ...[revenue, cogsAmount, wbExpenses, logistics, adsSpend, profit]
      .map((value) => Math.abs(toFiniteNumber(value) ?? 0))
      .filter(Number.isFinite),
  );
  const toggleExpenseDetails = () => {
    if (!hasWbExpenseDetails) return;
    const nextOpen = !detailsOpen;
    setDetailsOpen(nextOpen);
    if (nextOpen) {
      window.setTimeout(() => {
        document
          .getElementById("wb-expenses-breakdown")
          ?.scrollIntoView({ behavior: "smooth", block: "start" });
      }, 0);
    }
  };

  return (
    <section
      className={cn("overflow-hidden rounded-[24px]", COCKPIT_PANEL_CLASS)}
    >
      <div className="flex items-start justify-between gap-3 px-5 py-4">
        <div>
          <h2 className="text-base font-semibold">Деньги по карточке</h2>
          <p className="text-xs text-muted-foreground">
            Выручка, расходы WB, реклама и расчётная прибыль.
          </p>
        </div>
        <StatusBadge value={cockpit.healthStatus} />
      </div>

      <div className="grid px-5 pb-4 lg:grid-cols-[230px_minmax(0,1fr)]">
        <div className="border-b border-border/55 pb-4 lg:border-b-0 lg:border-r lg:pr-5">
          <div className="text-[10px] font-semibold uppercase text-muted-foreground">
            Итог периода
          </div>
          <div
            className={cn(
              "mt-2 text-3xl font-semibold leading-none tabular-nums",
              profit !== null && profit < 0
                ? "text-destructive"
                : "text-success",
            )}
          >
            {formatMoneyOrDash(profit)}
          </div>
          <div className="mt-4 grid gap-2 text-xs text-muted-foreground">
            <div className="flex justify-between gap-2 border-b border-border/50 pb-2">
              <span>Маржа</span>
              <span className="font-medium text-foreground tabular-nums">
                {formatPercentOrDash(cockpit.money.margin)}
              </span>
            </div>
            <div className="flex justify-between gap-2 border-b border-border/50 pb-2">
              <span>ДРР</span>
              <span className="font-medium text-foreground tabular-nums">
                {formatPercentOrDash(cockpit.ads.drr)}
              </span>
            </div>
            <div className="pt-1 text-[11px] leading-4 text-muted-foreground">
              Выручка минус себестоимость, удержания WB и реклама.
            </div>
          </div>
        </div>

        <div className="pt-2 lg:pl-5 lg:pt-0">
          <MoneyStatementRow
            label="Выручка"
            value={revenue}
            max={max}
            tone="good"
          />
          <MoneyStatementRow
            label="Себестоимость"
            value={cogsAmount === null ? null : -Math.abs(cogsAmount)}
            max={max}
            tone="muted"
            detail={
              cockpit.money.unitCost !== null
                ? `Цена за ед.: ${formatMoney(cockpit.money.unitCost)}`
                : undefined
            }
          />
          <MoneyStatementRow
            label="Расходы WB"
            value={wbExpenses === null ? null : -Math.abs(wbExpenses)}
            max={max}
            tone="warning"
            detail={
              hasWbExpenseDetails
                ? "Логистика, штрафы, удержания и прочие категории ниже"
                : undefined
            }
            actionLabel={
              hasWbExpenseDetails
                ? detailsOpen
                  ? "скрыть"
                  : "состав"
                : undefined
            }
            onClick={hasWbExpenseDetails ? toggleExpenseDetails : undefined}
          />
          <MoneyStatementRow
            label="Логистика WB"
            value={logistics === null ? null : -Math.abs(logistics)}
            max={max}
            tone="info"
            detail={
              logistics !== null
                ? cockpit.money.logisticsStatus
                  ? expenseStatusLabel(cockpit.money.logisticsStatus)
                  : "Входит в расходы WB"
                : undefined
            }
          />
          <MoneyStatementRow
            label="Реклама"
            value={adsSpend === null ? null : -Math.abs(adsSpend)}
            max={max}
            tone="warning"
            detail={
              cockpit.ads.drr !== null
                ? `ДРР: ${formatPercentOrDash(cockpit.ads.drr)}`
                : undefined
            }
          />
        </div>
      </div>

      {detailsOpen ? (
        <div className="px-5 pb-5">
          <WbExpenseDetailPanel cockpit={cockpit} />
        </div>
      ) : null}
    </section>
  );
}

function ProblemsPanel({
  cockpit,
  nmId,
}: {
  cockpit: any;
  nmId: string | number;
}) {
  const problems = cockpit.problems;
  return (
    <section className={cn("overflow-hidden rounded-2xl", COCKPIT_PANEL_CLASS)}>
      <div className="flex items-start justify-between gap-3 px-4 py-3">
        <div>
          <h2 className="text-base font-semibold">Главные проблемы</h2>
          <p className="text-xs text-muted-foreground">
            Открытые действия и сигналы по этой карточке.
          </p>
        </div>
        <Badge variant="outline" className="text-[10px]">
          {cockpit.actions.open} открыто
        </Badge>
      </div>
      {problems.length === 0 ? (
        <div className="m-3 rounded-2xl bg-success/5 p-3 text-sm shadow-sm ring-1 ring-success/20">
          <div className="font-medium text-success">Критичных задач нет</div>
          <div className="mt-1 text-xs text-muted-foreground">
            Деньги, карточка и данные не показывают открытых блокеров.
          </div>
        </div>
      ) : (
        <div className="grid gap-2 px-3 pb-3">
          {problems.slice(0, 6).map((problem: any, index: number) => (
            <Link
              key={`${problem.source}-${problem.title}-${index}`}
              to={problem.link?.to as any}
              search={problem.link?.search as any}
              params={problem.link?.params as any}
              className="group grid min-h-[94px] grid-cols-[minmax(0,1fr)_36px] gap-3 rounded-2xl bg-background/76 px-3.5 py-3 shadow-sm ring-1 ring-border/40 transition hover:-translate-y-0.5 hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-1.5">
                  <Badge
                    variant="outline"
                    className="h-5 bg-background text-[10px]"
                  >
                    {problem.source}
                  </Badge>
                  {problem.amount !== null && problem.amount !== undefined ? (
                    <Badge
                      variant="outline"
                      className="h-5 bg-background text-[10px]"
                    >
                      {formatMoneyTiny(problem.amount)}
                    </Badge>
                  ) : null}
                </div>
                <div className="mt-1.5 line-clamp-2 text-sm font-semibold leading-snug">
                  {problem.title}
                </div>
                {problem.detail ? (
                  <div className="mt-1 line-clamp-2 text-xs leading-snug text-muted-foreground">
                    {problem.detail}
                  </div>
                ) : null}
              </div>
              <span className="mt-6 inline-flex h-9 w-9 items-center justify-center rounded-xl bg-muted text-muted-foreground shadow-sm transition group-hover:bg-primary group-hover:text-primary-foreground">
                <ArrowRight className="h-3.5 w-3.5" />
              </span>
            </Link>
          ))}
          {problems.length > 6 ? (
            <Button
              asChild
              variant="ghost"
              size="sm"
              className="h-8 justify-self-start rounded-xl text-xs"
            >
              <Link to="/action-center" search={{ nm_id: String(nmId) } as any}>
                Все действия <ArrowRight className="ml-1 h-3.5 w-3.5" />
              </Link>
            </Button>
          ) : null}
        </div>
      )}
    </section>
  );
}

function percentNumber(value: any): number | null {
  const n = toFiniteNumber(value);
  if (n === null) return null;
  return Math.abs(n) <= 1 ? n * 100 : n;
}

function clampNumber(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}

const FORECAST_PRICE_STEPS = [-0.1, -0.05, 0, 0.05, 0.1];

function positiveNumber(value: any): number | null {
  const n = toFiniteNumber(value);
  return n !== null && n > 0 ? n : null;
}

function parseDateOnly(value?: string | null): Date | null {
  if (!value) return null;
  const [year, month, day] = String(value).split("-").map(Number);
  if (!year || !month || !day) return null;
  return new Date(Date.UTC(year, month - 1, day));
}

function inclusivePeriodDays(
  dateFrom?: string,
  dateTo?: string,
): number | null {
  const from = parseDateOnly(dateFrom);
  const to = parseDateOnly(dateTo);
  if (!from || !to) return null;
  const diff = Math.floor((to.getTime() - from.getTime()) / 86_400_000) + 1;
  return diff > 0 ? clampNumber(diff, 1, 366) : null;
}

function amountPerUnit(amount: any, units: number | null): number | null {
  const n = toFiniteNumber(amount);
  if (n === null || units === null || units <= 0) return null;
  return Math.abs(n) / units;
}

function formatUnitsOrDash(value: any, suffix = "шт"): string {
  const n = toFiniteNumber(value);
  if (n === null) return "Нет данных";
  return `${n.toLocaleString("ru-RU", { maximumFractionDigits: 1 })} ${suffix}`;
}

function formatSignedMoney(value: any): string {
  const n = toFiniteNumber(value);
  if (n === null) return "Нет данных";
  return `${n > 0 ? "+" : ""}${formatMoney(n)}`;
}

function forecastElasticity(cockpit: any, dailyVelocity: number | null) {
  const drr = percentNumber(cockpit.ads.drr);
  const stockDays = toFiniteNumber(cockpit.stock.daysOfStock);
  const stockQuantity = toFiniteNumber(cockpit.stock.quantity);
  const qualityIssues = toFiniteNumber(cockpit.quality.issueCount) ?? 0;
  let elasticity = -1.05;
  const reasons = [
    "Базовая модель WB: изменение цены влияет на спрос не линейно.",
  ];

  if (drr !== null && drr >= 25) {
    elasticity -= 0.25;
    reasons.push(
      "ДРР высокий, поэтому цена сильнее влияет на окупаемость заказов.",
    );
  } else if (drr !== null && drr <= 8) {
    elasticity += 0.12;
    reasons.push("ДРР низкий, спрос меньше зависит от рекламы.");
  }

  if (stockQuantity !== null && stockQuantity <= 0) {
    elasticity += 0.55;
    reasons.push("Остатка нет, прогноз продаж ограничен складом.");
  } else if (stockDays !== null && stockDays < 14) {
    elasticity += 0.32;
    reasons.push(
      "Запас меньше 14 дней, поэтому рост продаж ограничиваем остатками.",
    );
  }

  if (qualityIssues > 0) {
    elasticity -= qualityIssues >= 5 ? 0.18 : 0.1;
    reasons.push(
      "Есть проблемы карточки, конверсия может сильнее просесть при росте цены.",
    );
  }

  if (dailyVelocity !== null && dailyVelocity < 0.3) {
    elasticity += 0.18;
    reasons.push("Продаж мало, модель сглаживает реакцию на цену.");
  }

  return {
    elasticity: clampNumber(elasticity, -1.8, -0.3),
    reasons,
  };
}

function forecastToneByProfit(value: number | null): CockpitTone {
  if (value === null) return "muted";
  if (value < 0) return "danger";
  if (value === 0) return "warning";
  return "good";
}

function buildProductForecast(
  cockpit: any,
  dateFrom?: string,
  dateTo?: string,
) {
  const periodDays = inclusivePeriodDays(dateFrom, dateTo) ?? 30;
  const revenue = toFiniteNumber(cockpit.money.revenue);
  const factProfit = toFiniteNumber(cockpit.money.profit);
  const salePrice = positiveNumber(
    firstNumber(
      cockpit.price.discounted,
      cockpit.price.current,
      cockpit.price.base,
    ),
  );
  const listPrice = positiveNumber(
    firstNumber(cockpit.price.base, cockpit.price.current),
  );
  const factUnits = positiveNumber(cockpit.money.soldUnits);
  const unitsFromRevenue =
    factUnits === null && salePrice !== null && revenue !== null && revenue > 0
      ? revenue / salePrice
      : null;
  const soldUnits = factUnits ?? unitsFromRevenue;
  const forecastBaseUnits =
    soldUnits ??
    (() => {
      const velocity = positiveNumber(cockpit.stock.salesVelocity);
      return velocity !== null ? velocity * periodDays : null;
    })();
  const dailyVelocity =
    positiveNumber(cockpit.stock.salesVelocity) ??
    (soldUnits !== null ? soldUnits / periodDays : null);

  const cogsPerUnit =
    positiveNumber(cockpit.money.unitCost) ??
    amountPerUnit(cockpit.money.cogsAmount, soldUnits);
  const wbPerUnit = amountPerUnit(cockpit.money.wbExpensesTotal, soldUnits);
  const logisticsPerUnit = amountPerUnit(
    cockpit.money.logisticsDirect,
    soldUnits,
  );
  const adsPerUnit = amountPerUnit(cockpit.ads.spend, soldUnits);
  const otherWbPerUnit =
    wbPerUnit !== null && logisticsPerUnit !== null
      ? Math.max(0, wbPerUnit - logisticsPerUnit)
      : null;
  const costComponentValues = [cogsPerUnit, wbPerUnit, adsPerUnit].filter(
    (value): value is number => value !== null && Number.isFinite(value),
  );
  const directCostPerUnit = costComponentValues.length
    ? costComponentValues.reduce((sum, value) => sum + value, 0)
    : null;
  const profitPerUnitFact =
    factProfit !== null && soldUnits !== null && soldUnits > 0
      ? factProfit / soldUnits
      : null;
  const costFromFact =
    salePrice !== null && profitPerUnitFact !== null
      ? Math.max(0, salePrice - profitPerUnitFact)
      : null;
  const breakEven = positiveNumber(cockpit.price.breakEven);
  const hasCoreUnitCost = cogsPerUnit !== null && wbPerUnit !== null;
  const totalCostPerUnit =
    hasCoreUnitCost && directCostPerUnit !== null
      ? directCostPerUnit
      : (costFromFact ?? directCostPerUnit ?? breakEven);
  const costPrecision =
    hasCoreUnitCost && adsPerUnit !== null
      ? "Полный расчет"
      : hasCoreUnitCost
        ? "Без отдельной рекламы"
        : costFromFact !== null
          ? "Из фактической прибыли"
          : "Оценка по безубыточности";
  const currentUnitProfit =
    salePrice !== null && totalCostPerUnit !== null
      ? salePrice - totalCostPerUnit
      : profitPerUnitFact;
  const currentMargin =
    salePrice !== null && salePrice > 0 && currentUnitProfit !== null
      ? (currentUnitProfit / salePrice) * 100
      : percentNumber(cockpit.money.margin);
  const backendTargetPrice = positiveNumber(cockpit.price.target);
  const targetPrice =
    backendTargetPrice ??
    (totalCostPerUnit !== null ? totalCostPerUnit / 0.75 : null);

  const stockQuantity = positiveNumber(cockpit.stock.quantity);
  const inTransit = positiveNumber(cockpit.stock.inTransit) ?? 0;
  const stockCap =
    stockQuantity !== null ? Math.max(0, stockQuantity + inTransit) : null;
  const { elasticity, reasons } = forecastElasticity(cockpit, dailyVelocity);

  const scenarios =
    salePrice !== null &&
    totalCostPerUnit !== null &&
    forecastBaseUnits !== null
      ? FORECAST_PRICE_STEPS.map((delta) => {
          const price = salePrice * (1 + delta);
          const demandFactor = clampNumber(1 + elasticity * delta, 0.2, 2.2);
          const rawUnits = Math.max(0, forecastBaseUnits * demandFactor);
          const projectedUnits =
            stockCap !== null ? Math.min(rawUnits, stockCap) : rawUnits;
          const unitProfit = price - totalCostPerUnit;
          const projectedProfit = unitProfit * projectedUnits;
          const projectedRevenue = price * projectedUnits;
          return {
            delta,
            deltaLabel:
              delta === 0
                ? "Текущая"
                : `${delta > 0 ? "+" : ""}${Math.round(delta * 100)}%`,
            price,
            projectedUnits,
            rawUnits,
            stockLimited: stockCap !== null && rawUnits - projectedUnits > 0.01,
            unitProfit,
            projectedProfit,
            projectedRevenue,
            margin: price > 0 ? (unitProfit / price) * 100 : null,
            tone: forecastToneByProfit(unitProfit),
          };
        })
      : [];
  const currentScenario =
    scenarios.find((scenario) => scenario.delta === 0) ?? null;
  scenarios.forEach((scenario) => {
    scenario.deltaProfit =
      currentScenario !== null
        ? scenario.projectedProfit - currentScenario.projectedProfit
        : null;
  });
  const recommended =
    scenarios
      .filter(
        (scenario) =>
          scenario.unitProfit >= 0 &&
          (breakEven === null || scenario.price >= breakEven),
      )
      .sort((a, b) => b.projectedProfit - a.projectedProfit)[0] ??
    currentScenario ??
    null;

  const costRows = [
    {
      key: "cogs",
      label: "Себестоимость товара",
      value: cogsPerUnit,
      total: cockpit.money.cogsAmount,
      tone: "muted" as CockpitTone,
      detail: "Закупочная или ручная себестоимость.",
    },
    {
      key: "wb",
      label: "Расходы WB",
      value: wbPerUnit,
      total: cockpit.money.wbExpensesTotal,
      tone: "warning" as CockpitTone,
      detail: "Комиссия, логистика, хранение, штрафы и удержания.",
    },
    {
      key: "logistics",
      label: "Логистика внутри WB",
      value: logisticsPerUnit,
      total: cockpit.money.logisticsDirect,
      tone: "info" as CockpitTone,
      detail: "Показана отдельно, но второй раз в расход не добавляется.",
      nested: true,
    },
    {
      key: "other_wb",
      label: "Прочие WB без логистики",
      value: otherWbPerUnit,
      total: (() => {
        const wbTotal = toFiniteNumber(cockpit.money.wbExpensesTotal);
        const logisticsTotal = toFiniteNumber(cockpit.money.logisticsDirect);
        return wbTotal !== null && logisticsTotal !== null
          ? Math.max(0, Math.abs(wbTotal) - Math.abs(logisticsTotal))
          : null;
      })(),
      tone: "warning" as CockpitTone,
      detail: "Комиссии и удержания без логистической части.",
      nested: true,
    },
    {
      key: "ads",
      label: "Реклама",
      value: adsPerUnit,
      total: cockpit.ads.spend,
      tone: "info" as CockpitTone,
      detail: "Средний рекламный расход на продажу за выбранный период.",
    },
  ];

  const dataNotes: string[] = [];
  if (salePrice === null) dataNotes.push("нет текущей цены продажи");
  if (factUnits === null && unitsFromRevenue !== null) {
    dataNotes.push("продажи в штуках рассчитаны как выручка / цена");
  } else if (factUnits === null) {
    dataNotes.push("нет продаж в штуках из финансового отчета");
  }
  if (cogsPerUnit === null) dataNotes.push("нет себестоимости на единицу");
  if (wbPerUnit === null) dataNotes.push("нет расходов WB на единицу");
  if ((cockpit.money.wbExpenseUnallocated ?? 0) > 0) {
    dataNotes.push("есть нераспределенные WB расходы");
  }
  if (
    (cockpit.ads.unallocated ?? 0) > 0 ||
    (cockpit.ads.overallocated ?? 0) > 0
  ) {
    dataNotes.push("рекламные расходы распределены не полностью");
  }

  const confidenceScore = clampNumber(
    100 -
      (salePrice === null ? 25 : 0) -
      (soldUnits === null ? 20 : 0) -
      (cogsPerUnit === null ? 20 : 0) -
      (wbPerUnit === null ? 15 : 0) -
      ((cockpit.money.wbExpenseUnallocated ?? 0) > 0 ? 10 : 0) -
      ((cockpit.ads.unallocated ?? 0) > 0 ||
      (cockpit.ads.overallocated ?? 0) > 0
        ? 10
        : 0),
    20,
    100,
  );
  const confidence =
    confidenceScore >= 80
      ? "Высокая"
      : confidenceScore >= 60
        ? "Рабочая"
        : "Осторожная";

  const levers = [];
  if (wbPerUnit !== null) {
    levers.push({
      key: "wb",
      title: "Разобрать WB расходы",
      value: formatMoneyOrDash(wbPerUnit),
      detail:
        logisticsPerUnit !== null
          ? `Логистика внутри: ${formatMoneyOrDash(logisticsPerUnit)} на продажу.`
          : "Проверьте комиссии, хранение и удержания.",
      tone: "warning" as CockpitTone,
      icon: "truck",
    });
  }
  if (adsPerUnit !== null || cockpit.ads.drr !== null) {
    levers.push({
      key: "ads",
      title: "Окупаемость рекламы",
      value:
        adsPerUnit !== null
          ? formatMoneyOrDash(adsPerUnit)
          : formatPercentOrDash(cockpit.ads.drr),
      detail: `ДРР: ${formatPercentOrDash(cockpit.ads.drr)}. Сравните с маржей после расходов.`,
      tone:
        percentNumber(cockpit.ads.drr) !== null &&
        percentNumber(cockpit.ads.drr)! >= 25
          ? "warning"
          : "info",
      icon: "ads",
    });
  }
  if (
    toFiniteNumber(cockpit.stock.quantity) !== null ||
    toFiniteNumber(cockpit.stock.daysOfStock) !== null
  ) {
    levers.push({
      key: "stock",
      title: "Склад и скорость",
      value:
        dailyVelocity !== null
          ? `${dailyVelocity.toLocaleString("ru-RU", { maximumFractionDigits: 1 })}/день`
          : `${formatNumberOrDash(cockpit.stock.quantity)} шт`,
      detail: `Запас: ${formatNumberOrDash(cockpit.stock.quantity)} шт, ${formatNumberOrDash(cockpit.stock.daysOfStock, { maximumFractionDigits: 1 })} дней.`,
      tone:
        stockQuantity === null
          ? "muted"
          : stockQuantity <= 0 ||
              (toFiniteNumber(cockpit.stock.daysOfStock) ?? 999) < 14
            ? "danger"
            : "good",
      icon: "stock",
    });
  }
  if ((cockpit.quality.issueCount ?? 0) > 0) {
    levers.push({
      key: "quality",
      title: "Конверсия карточки",
      value: `${cockpit.quality.issueCount} сигналов`,
      detail:
        "Проблемы карточки учитываются как риск просадки продаж при росте цены.",
      tone: cockpit.quality.criticalIssueCount > 0 ? "danger" : "warning",
      icon: "quality",
    });
  }
  if (!levers.length) {
    levers.push({
      key: "price",
      title: "Цена и маржа",
      value: formatMoneyOrDash(currentUnitProfit),
      detail: "Основной рычаг сейчас - держать цену выше безубыточного порога.",
      tone: forecastToneByProfit(currentUnitProfit),
      icon: "price",
    });
  }

  const recommendation =
    stockCap !== null && stockCap <= 0
      ? "Сначала пополнить остатки, иначе ценовой прогноз не даст продаж."
      : recommended === null
        ? "Недостаточно данных для точного ценового сценария."
        : recommended.delta === 0
          ? "Текущая цена выглядит самым устойчивым сценарием."
          : recommended.delta > 0
            ? `Проверить повышение цены до ${formatMoneyOrDash(recommended.price)}.`
            : `Проверить снижение цены до ${formatMoneyOrDash(recommended.price)}.`;

  return {
    periodDays,
    salePrice,
    listPrice,
    soldUnits,
    factUnits,
    unitsEstimated: factUnits === null && unitsFromRevenue !== null,
    dailyVelocity,
    forecastBaseUnits,
    costPrecision,
    cogsPerUnit,
    wbPerUnit,
    logisticsPerUnit,
    adsPerUnit,
    otherWbPerUnit,
    directCostPerUnit,
    totalCostPerUnit,
    breakEven,
    targetPrice,
    backendTargetPrice,
    currentUnitProfit,
    currentMargin,
    factProfit,
    scenarios,
    currentScenario,
    recommended,
    costRows,
    dataNotes,
    confidence,
    confidenceScore,
    elasticity,
    elasticityReasons: reasons,
    levers,
    recommendation,
    stockCap,
    tone: forecastToneByProfit(currentUnitProfit),
  };
}

function productVector(cockpit: any): {
  tone: CockpitTone;
  label: string;
  detail: string;
  direction: "up" | "down" | "flat";
} {
  const profit = toFiniteNumber(cockpit.money.profit);
  const revenue = toFiniteNumber(cockpit.money.revenue);
  const margin = percentNumber(cockpit.money.margin);
  const drr = percentNumber(cockpit.ads.drr);
  const stock = toFiniteNumber(cockpit.stock.quantity);
  const qualityScore = toFiniteNumber(cockpit.quality.score);

  if (stock !== null && stock <= 0) {
    return {
      tone: "danger",
      label: "Продажи могут остановиться",
      detail: `Остаток ${formatNumberOrDash(stock)} шт. Нужно закрыть вопрос со складом.`,
      direction: "down",
    };
  }

  if (profit !== null && profit < 0) {
    return {
      tone: "danger",
      label: "Товар уходит в минус",
      detail: `Прибыль ${formatMoneyOrDash(profit)}, маржа ${formatPercentOrDash(margin)}. Проверьте расходы и рекламу.`,
      direction: "down",
    };
  }

  if (revenue !== null && revenue <= 0) {
    return {
      tone: "warning",
      label: "Продаж нет в периоде",
      detail: "Карточка требует проверки цены, остатков, рекламы и видимости.",
      direction: "flat",
    };
  }

  if (drr !== null && drr >= 25) {
    return {
      tone: "warning",
      label: "Реклама давит прибыль",
      detail: `ДРР ${formatPercentOrDash(drr)} при прибыли ${formatMoneyOrDash(profit)}.`,
      direction: "down",
    };
  }

  if (margin !== null && margin < 8) {
    return {
      tone: "warning",
      label: "Продажи есть, маржа тонкая",
      detail: `Маржа ${formatPercentOrDash(margin)}. Нужен контроль цены и себестоимости.`,
      direction: "flat",
    };
  }

  if (qualityScore !== null && qualityScore < 70) {
    return {
      tone: "warning",
      label: "Карточка ограничивает рост",
      detail: `Качество ${Math.round(qualityScore)}/100. Лучше закрыть проблемы карточки.`,
      direction: "flat",
    };
  }

  if (profit !== null && profit > 0 && margin !== null && margin >= 20) {
    return {
      tone: "good",
      label: "Карточка прибыльная",
      detail: `Прибыль ${formatMoneyOrDash(profit)}, маржа ${formatPercentOrDash(margin)}. Можно усиливать рабочие каналы.`,
      direction: "up",
    };
  }

  return {
    tone: profit !== null && profit > 0 ? "good" : "info",
    label: "Состояние стабильное",
    detail: `Выручка ${formatMoneyOrDash(revenue)}, прибыль ${formatMoneyOrDash(profit)}.`,
    direction: "flat",
  };
}

function productPulseRows(cockpit: any) {
  const margin = percentNumber(cockpit.money.margin);
  const profitRate = safeRatioPercent(
    cockpit.money.profit,
    cockpit.money.revenue,
  );
  const drr = percentNumber(cockpit.ads.drr);
  const daysOfStock = toFiniteNumber(cockpit.stock.daysOfStock);
  const qualityScore = toFiniteNumber(cockpit.quality.score);

  return [
    {
      label: "Маржа",
      value: formatPercentOrDash(margin),
      width:
        margin === null ? 0 : clampNumber(((margin + 20) / 60) * 100, 6, 100),
      tone:
        margin === null
          ? "muted"
          : margin < 0
            ? "danger"
            : margin < 10
              ? "warning"
              : "good",
    },
    {
      label: "Результат",
      value: formatPercentOrDash(profitRate),
      width:
        profitRate === null ? 0 : clampNumber(Math.abs(profitRate) * 2, 6, 100),
      tone:
        profitRate === null
          ? "muted"
          : profitRate < 0
            ? "danger"
            : profitRate < 8
              ? "warning"
              : "good",
    },
    {
      label: "Реклама",
      value: formatPercentOrDash(drr),
      width: drr === null ? 0 : clampNumber(drr * 2.5, 6, 100),
      tone:
        drr === null
          ? "muted"
          : drr > 25
            ? "danger"
            : drr > 15
              ? "warning"
              : "info",
    },
    {
      label: "Запас",
      value:
        daysOfStock === null
          ? "Нет данных"
          : `${formatNumberOrDash(daysOfStock, { maximumFractionDigits: 1 })} дн.`,
      width:
        daysOfStock === null
          ? 0
          : clampNumber((daysOfStock / 60) * 100, 6, 100),
      tone:
        daysOfStock === null
          ? "muted"
          : daysOfStock < 14
            ? "danger"
            : daysOfStock < 30
              ? "warning"
              : "good",
    },
    {
      label: "Карточка",
      value:
        qualityScore === null
          ? "Нет данных"
          : `${Math.round(qualityScore)}/100`,
      width: qualityScore === null ? 0 : clampNumber(qualityScore, 6, 100),
      tone:
        qualityScore === null
          ? "muted"
          : qualityScore < 60
            ? "danger"
            : qualityScore < 80
              ? "warning"
              : "good",
    },
  ];
}

function ProductVectorPanel({ cockpit }: { cockpit: any }) {
  const vector = productVector(cockpit);
  const Icon =
    vector.direction === "down"
      ? TrendingDown
      : vector.direction === "up"
        ? TrendingUp
        : Sparkles;

  return (
    <div
      className={cn(
        "relative overflow-hidden rounded-2xl border p-3 before:absolute before:inset-y-3 before:left-0 before:w-1 before:rounded-r-full",
        COCKPIT_SOFT_TONE[vector.tone],
        COCKPIT_ACCENT_TONE[vector.tone],
      )}
    >
      <div className="flex items-start gap-3">
        <span
          className={cn(
            "inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-xl",
            COCKPIT_ICON_TONE[vector.tone],
          )}
        >
          <Icon className="h-4 w-4" />
        </span>
        <div className="min-w-0">
          <div className="text-[11px] font-semibold uppercase text-muted-foreground">
            Текущий вектор
          </div>
          <div className="mt-0.5 text-base font-semibold leading-tight">
            {vector.label}
          </div>
          <div className="mt-1 text-xs leading-snug text-muted-foreground">
            {vector.detail}
          </div>
        </div>
      </div>
    </div>
  );
}

function ProductHeroMetric({
  icon,
  label,
  value,
  detail,
  tone = "default",
  to,
  href,
  search,
  params,
  wide = false,
  testId,
}: {
  icon: ReactNode;
  label: string;
  value: ReactNode;
  detail?: ReactNode;
  tone?: CockpitTone;
  to?: string;
  href?: string;
  search?: Record<string, any>;
  params?: Record<string, any>;
  wide?: boolean;
  testId?: string;
}) {
  const className = cn(
    "group relative flex min-h-[82px] flex-col justify-between overflow-hidden bg-background/76 p-3 outline-none transition duration-200 before:absolute before:inset-x-3 before:top-0 before:h-0.5 before:rounded-full hover:bg-background focus-visible:ring-2 focus-visible:ring-primary/35",
    COCKPIT_ACCENT_TONE[tone],
    wide ? "" : "",
  );
  const content = (
    <>
      <div className="flex items-start justify-between gap-2">
        <div className="flex min-w-0 items-center gap-2">
          <span
            className={cn(
              "inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-lg",
              COCKPIT_ICON_TONE[tone],
            )}
          >
            {icon}
          </span>
          <span className="truncate text-xs font-semibold uppercase text-muted-foreground">
            {label}
          </span>
        </div>
        {to || href ? (
          <ArrowRight className="h-4 w-4 shrink-0 text-muted-foreground transition group-hover:text-primary" />
        ) : null}
      </div>
      <div>
        <div
          className={cn(
            "text-[22px] font-semibold leading-none tabular-nums",
            COCKPIT_TEXT_TONE[tone],
          )}
        >
          {value}
        </div>
        {detail ? (
          <div className="mt-1.5 line-clamp-2 text-xs leading-snug text-muted-foreground">
            {detail}
          </div>
        ) : null}
      </div>
    </>
  );

  if (href) {
    return (
      <a
        href={href}
        data-testid={testId}
        className={className}
        onClick={(event) => {
          if (
            event.defaultPrevented ||
            event.button !== 0 ||
            event.metaKey ||
            event.ctrlKey ||
            event.shiftKey ||
            event.altKey
          ) {
            return;
          }
          event.preventDefault();
          window.location.assign(href);
        }}
      >
        {content}
      </a>
    );
  }

  if (to) {
    return (
      <Link
        to={to as any}
        search={search as any}
        params={params as any}
        data-testid={testId}
        className={className}
      >
        {content}
      </Link>
    );
  }

  return <div className={className}>{content}</div>;
}

function ProductPulsePanel({ cockpit }: { cockpit: any }) {
  const rows = productPulseRows(cockpit);

  return (
    <div className="rounded-[20px] border border-border/45 bg-background/60 p-3">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <span className="inline-flex h-8 w-8 items-center justify-center rounded-lg bg-info/10 text-info">
            <BarChart3 className="h-4 w-4" />
          </span>
          <div>
            <div className="text-sm font-semibold">Пульс товара</div>
            <div className="text-xs text-muted-foreground">
              Финансы, реклама, запас и качество
            </div>
          </div>
        </div>
        <StatusBadge value={cockpit.healthStatus} />
      </div>
      <div className="mt-2.5 grid gap-2.5 sm:grid-cols-5">
        {rows.map((row) => (
          <div key={row.label} className="min-w-0">
            <div className="flex items-center justify-between gap-2 text-[11px]">
              <span className="truncate text-muted-foreground">
                {row.label}
              </span>
              <span className="shrink-0 font-medium tabular-nums">
                {row.value}
              </span>
            </div>
            <div className="mt-1.5 h-2 overflow-hidden rounded-full bg-muted">
              <div
                className={cn(
                  "h-full rounded-full",
                  COCKPIT_BAR_TONE[row.tone],
                )}
                style={{ width: `${row.width}%` }}
              />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function ForecastKpi({
  icon,
  label,
  value,
  detail,
  tone = "default",
}: {
  icon: ReactNode;
  label: string;
  value: ReactNode;
  detail?: ReactNode;
  tone?: CockpitTone;
}) {
  return (
    <div className="min-h-[106px] bg-background/76 p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="text-[10px] font-semibold uppercase text-muted-foreground">
            {label}
          </div>
          <div
            className={cn(
              "mt-2 truncate text-[22px] font-semibold leading-none tabular-nums",
              COCKPIT_TEXT_TONE[tone],
            )}
          >
            {value}
          </div>
        </div>
        <span
          className={cn(
            "inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-xl",
            COCKPIT_ICON_TONE[tone],
          )}
        >
          {icon}
        </span>
      </div>
      {detail ? (
        <div className="mt-2 line-clamp-2 text-xs leading-snug text-muted-foreground">
          {detail}
        </div>
      ) : null}
    </div>
  );
}

function ForecastCostRow({ row, max }: { row: any; max: number }) {
  const value = toFiniteNumber(row.value);
  const width =
    value !== null ? clampNumber((Math.abs(value) / max) * 100, 4, 100) : 0;
  return (
    <div
      className={cn(
        "rounded-2xl border border-border/45 bg-background/74 p-3",
        row.nested ? "ml-3 border-dashed bg-muted/16" : "",
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="truncate text-sm font-semibold">{row.label}</div>
          <div className="mt-0.5 line-clamp-2 text-[11px] leading-snug text-muted-foreground">
            {row.detail}
          </div>
        </div>
        <div
          className={cn(
            "shrink-0 text-right text-sm font-semibold tabular-nums",
            COCKPIT_TEXT_TONE[row.tone ?? "default"],
          )}
        >
          {formatMoneyOrDash(value)}
          <div className="mt-0.5 text-[10px] font-medium text-muted-foreground">
            за 1 шт
          </div>
        </div>
      </div>
      <div className="mt-2 h-2 overflow-hidden rounded-full bg-muted">
        <div
          className={cn(
            "h-full rounded-full",
            COCKPIT_BAR_TONE[row.tone ?? "default"],
          )}
          style={{ width: `${width}%` }}
        />
      </div>
      <div className="mt-2 flex items-center justify-between gap-2 text-[11px] text-muted-foreground">
        <span>Сумма за период</span>
        <span className="font-medium tabular-nums text-foreground">
          {formatMoneyOrDash(row.total)}
        </span>
      </div>
    </div>
  );
}

function ForecastScenarioCard({
  scenario,
  recommended,
}: {
  scenario: any;
  recommended: boolean;
}) {
  const tone: CockpitTone =
    scenario.unitProfit < 0
      ? "danger"
      : scenario.deltaProfit !== null && scenario.deltaProfit > 0
        ? "good"
        : scenario.delta === 0
          ? "info"
          : "default";
  return (
    <div
      className={cn(
        "relative min-h-[188px] rounded-2xl border p-3.5 shadow-sm transition",
        COCKPIT_SOFT_TONE[tone],
        recommended ? "ring-2 ring-primary/35" : "ring-1 ring-border/30",
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="text-[10px] font-semibold uppercase text-muted-foreground">
            Сценарий
          </div>
          <div className="mt-1 text-base font-semibold">
            {scenario.deltaLabel}
          </div>
        </div>
        {recommended ? (
          <Badge className="h-6 rounded-full bg-primary text-[10px] text-primary-foreground">
            Лучший
          </Badge>
        ) : null}
      </div>
      <div className="mt-3 text-2xl font-semibold leading-none tabular-nums">
        {formatMoneyOrDash(scenario.price)}
      </div>
      <div className="mt-3 grid gap-2 text-xs">
        <div className="flex justify-between gap-2">
          <span className="text-muted-foreground">Продажи</span>
          <span className="font-medium tabular-nums">
            {formatUnitsOrDash(scenario.projectedUnits)}
          </span>
        </div>
        <div className="flex justify-between gap-2">
          <span className="text-muted-foreground">Прибыль</span>
          <span
            className={cn(
              "font-semibold tabular-nums",
              scenario.projectedProfit < 0
                ? "text-destructive"
                : "text-success",
            )}
          >
            {formatMoneyOrDash(scenario.projectedProfit)}
          </span>
        </div>
        <div className="flex justify-between gap-2">
          <span className="text-muted-foreground">Маржа</span>
          <span className="font-medium tabular-nums">
            {formatPercentOrDash(scenario.margin)}
          </span>
        </div>
      </div>
      <div className="mt-3 flex flex-wrap gap-1.5">
        {scenario.delta === 0 ? (
          <Badge variant="outline" className="h-6 bg-background text-[10px]">
            текущая база
          </Badge>
        ) : (
          <Badge variant="outline" className="h-6 bg-background text-[10px]">
            {formatSignedMoney(scenario.deltaProfit)}
          </Badge>
        )}
        {scenario.stockLimited ? (
          <Badge
            variant="outline"
            className="h-6 border-warning/35 bg-warning/5 text-[10px] text-warning"
          >
            ограничено складом
          </Badge>
        ) : null}
      </div>
    </div>
  );
}

function ForecastLeverIcon({ icon }: { icon: string }) {
  if (icon === "truck") return <Truck className="h-4 w-4" />;
  if (icon === "ads") return <Megaphone className="h-4 w-4" />;
  if (icon === "stock") return <Boxes className="h-4 w-4" />;
  if (icon === "quality") return <ShieldCheck className="h-4 w-4" />;
  if (icon === "price") return <Tag className="h-4 w-4" />;
  return <Sparkles className="h-4 w-4" />;
}

function buildManualForecastScenario(forecast: any, priceDraft: any) {
  const price = positiveNumber(priceDraft);
  if (
    price === null ||
    forecast.salePrice === null ||
    forecast.totalCostPerUnit === null ||
    forecast.forecastBaseUnits === null
  ) {
    return null;
  }
  const delta = price / forecast.salePrice - 1;
  const demandFactor = clampNumber(1 + forecast.elasticity * delta, 0.2, 2.2);
  const rawUnits = Math.max(0, forecast.forecastBaseUnits * demandFactor);
  const projectedUnits =
    forecast.stockCap !== null
      ? Math.min(rawUnits, forecast.stockCap)
      : rawUnits;
  const unitProfit = price - forecast.totalCostPerUnit;
  const projectedProfit = unitProfit * projectedUnits;
  const projectedRevenue = price * projectedUnits;
  const currentProfit = forecast.currentScenario?.projectedProfit ?? null;

  return {
    delta,
    deltaLabel: "Ваша цена",
    price,
    projectedUnits,
    rawUnits,
    stockLimited:
      forecast.stockCap !== null && rawUnits - projectedUnits > 0.01,
    unitProfit,
    projectedProfit,
    projectedRevenue,
    deltaProfit:
      currentProfit !== null ? projectedProfit - currentProfit : null,
    margin: price > 0 ? (unitProfit / price) * 100 : null,
    tone: forecastToneByProfit(unitProfit),
  };
}

function ForecastCompactStat({
  icon,
  label,
  value,
  detail,
  tone = "default",
}: {
  icon: ReactNode;
  label: string;
  value: ReactNode;
  detail?: ReactNode;
  tone?: CockpitTone;
}) {
  return (
    <div className="rounded-xl bg-muted/28 px-3 py-2.5">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="truncate text-[10px] font-semibold uppercase text-muted-foreground">
            {label}
          </div>
          <div
            className={cn(
              "mt-1 truncate text-lg font-semibold leading-none tabular-nums",
              COCKPIT_TEXT_TONE[tone],
            )}
          >
            {value}
          </div>
        </div>
        <span
          className={cn(
            "inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-lg",
            COCKPIT_ICON_TONE[tone],
          )}
        >
          {icon}
        </span>
      </div>
      {detail ? (
        <div className="mt-1.5 truncate text-[11px] text-muted-foreground">
          {detail}
        </div>
      ) : null}
    </div>
  );
}

function ForecastUnitLine({
  label,
  value,
  detail,
  tone = "default",
  sign,
  nested = false,
  strong = false,
}: {
  label: string;
  value: any;
  detail?: ReactNode;
  tone?: CockpitTone;
  sign?: "+" | "-" | "=";
  nested?: boolean;
  strong?: boolean;
}) {
  const parsed = toFiniteNumber(value);
  return (
    <div
      className={cn(
        "grid grid-cols-[minmax(0,1fr)_auto] items-center gap-3 border-b border-border/50 px-1 py-2.5 last:border-b-0",
        strong ? "bg-muted/20 px-3" : "",
        nested ? "ml-4 border-dashed text-muted-foreground" : "",
      )}
    >
      <div className="min-w-0">
        <div
          className={cn(
            "truncate text-sm",
            strong ? "font-semibold" : "font-medium",
          )}
        >
          {label}
        </div>
        {detail ? (
          <div className="mt-0.5 truncate text-[11px] text-muted-foreground">
            {detail}
          </div>
        ) : null}
      </div>
      <div
        className={cn(
          "shrink-0 text-right text-sm font-semibold tabular-nums",
          COCKPIT_TEXT_TONE[tone],
        )}
      >
        {sign ? (
          <span className="mr-1 text-muted-foreground">{sign}</span>
        ) : null}
        {formatMoneyOrDash(parsed)}
      </div>
    </div>
  );
}

function ForecastScenarioStrip({
  scenario,
  recommended,
}: {
  scenario: any;
  recommended: boolean;
}) {
  const tone: CockpitTone =
    scenario.unitProfit < 0
      ? "danger"
      : scenario.deltaProfit !== null && scenario.deltaProfit > 0
        ? "good"
        : scenario.delta === 0
          ? "info"
          : "default";
  return (
    <div
      className={cn(
        "rounded-xl border p-2.5",
        COCKPIT_SOFT_TONE[tone],
        recommended ? "ring-2 ring-primary/25" : "",
      )}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs font-semibold">{scenario.deltaLabel}</span>
        {recommended ? (
          <Badge className="h-5 rounded-full bg-primary text-[9px] text-primary-foreground">
            лучше
          </Badge>
        ) : null}
      </div>
      <div className="mt-1 text-base font-semibold tabular-nums">
        {formatMoneyOrDash(scenario.price)}
      </div>
      <div className="mt-1 grid gap-0.5 text-[11px] text-muted-foreground">
        <div className="flex justify-between gap-2">
          <span>1 шт</span>
          <span
            className={cn(
              "font-medium tabular-nums",
              scenario.unitProfit < 0 ? "text-destructive" : "text-success",
            )}
          >
            {formatMoneyOrDash(scenario.unitProfit)}
          </span>
        </div>
        <div className="flex justify-between gap-2">
          <span>Период</span>
          <span className="font-medium text-foreground tabular-nums">
            {formatMoneyOrDash(scenario.projectedProfit)}
          </span>
        </div>
      </div>
    </div>
  );
}

function ProductForecastPanel({
  cockpit,
  dateFrom,
  dateTo,
  forecast: providedForecast,
}: {
  cockpit: any;
  dateFrom?: string;
  dateTo?: string;
  forecast?: any;
}) {
  const forecast =
    providedForecast ?? buildProductForecast(cockpit, dateFrom, dateTo);
  const initialPrice = forecast.recommended?.price ?? forecast.salePrice ?? "";
  const [customPrice, setCustomPrice] = useState(
    initialPrice === "" ? "" : String(Math.round(initialPrice)),
  );
  const customScenario = buildManualForecastScenario(forecast, customPrice);
  const period =
    dateFrom && dateTo
      ? `${dateFrom} - ${dateTo}`
      : `${forecast.periodDays} дней`;
  const recommendedPrice =
    forecast.recommended?.price ?? forecast.targetPrice ?? null;
  const recommendedDelta = forecast.recommended?.deltaProfit ?? null;
  const manualPriceNumber = positiveNumber(customPrice);
  const manualPriceGap =
    manualPriceNumber !== null && forecast.breakEven !== null
      ? manualPriceNumber - forecast.breakEven
      : null;
  const unitDelta =
    customScenario !== null && forecast.currentUnitProfit !== null
      ? customScenario.unitProfit - forecast.currentUnitProfit
      : null;

  return (
    <section id="product-forecast" className="flex scroll-mt-24 justify-end">
      <Dialog>
        <DialogTrigger asChild>
          <Button
            type="button"
            size="lg"
            className="h-11 rounded-xl px-4 shadow-sm"
          >
            <TrendingUp className="mr-2 h-4 w-4" />
            Прогноз
            <span className="ml-2 rounded-lg bg-primary-foreground/15 px-2 py-0.5 text-xs font-semibold">
              1 шт {formatMoneyOrDash(forecast.currentUnitProfit)}
            </span>
          </Button>
        </DialogTrigger>
        <DialogContent className="max-h-[calc(100vh-28px)] w-[calc(100vw-28px)] max-w-none overflow-hidden p-0 sm:max-w-[1120px]">
          <DialogHeader className="border-b border-border/55 px-4 py-3 text-left">
            <div className="flex flex-wrap items-start justify-between gap-2">
              <div className="min-w-0">
                <DialogTitle className="flex flex-wrap items-center gap-2 text-lg">
                  <span className="inline-flex h-9 w-9 items-center justify-center rounded-xl bg-primary/10 text-primary">
                    <TrendingUp className="h-4 w-4" />
                  </span>
                  Прогноз по 1 штуке
                </DialogTitle>
                <DialogDescription className="mt-1.5 max-w-3xl text-xs leading-snug">
                  Сначала считаем экономику одной продажи, затем показываем
                  влияние выбранной цены на период.
                </DialogDescription>
              </div>
              <div className="flex flex-wrap justify-end gap-1.5">
                <Badge
                  variant="outline"
                  className="h-6 bg-background px-2.5 text-[10px]"
                >
                  {period}
                </Badge>
                <Badge
                  variant="outline"
                  className={cn(
                    "h-6 bg-background px-2.5 text-[10px]",
                    forecast.confidenceScore >= 80
                      ? "border-success/30 text-success"
                      : forecast.confidenceScore >= 60
                        ? "border-info/30 text-info"
                        : "border-warning/35 text-warning",
                  )}
                >
                  Точность: {forecast.confidence}
                </Badge>
                <Badge
                  variant="outline"
                  className="h-6 bg-background px-2.5 text-[10px]"
                >
                  {forecast.costPrecision}
                </Badge>
              </div>
            </div>
          </DialogHeader>

          <div className="max-h-[calc(100vh-116px)] overflow-y-auto bg-muted/10 p-3">
            <div className="grid gap-3 lg:grid-cols-[minmax(0,430px)_minmax(0,1fr)]">
              <div className="min-w-0 rounded-[18px] border border-border/45 bg-background/90 p-3">
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <h3 className="text-sm font-semibold">Сейчас: 1 продажа</h3>
                    <p className="mt-0.5 text-xs text-muted-foreground">
                      Логистика показана внутри WB расходов и не добавляется
                      второй раз.
                    </p>
                  </div>
                  <Badge
                    variant="outline"
                    className="h-6 shrink-0 bg-background text-[10px]"
                  >
                    {forecast.unitsEstimated ? "шт оценены" : "шт из отчета"}
                  </Badge>
                </div>

                <div className="mt-3 grid gap-2 sm:grid-cols-2">
                  <ForecastCompactStat
                    icon={<Tag className="h-4 w-4" />}
                    label="Цена за 1 шт"
                    value={formatMoneyOrDash(forecast.salePrice)}
                    detail={`До скидки ${formatMoneyOrDash(forecast.listPrice)}`}
                    tone={forecast.salePrice === null ? "muted" : "info"}
                  />
                  <ForecastCompactStat
                    icon={<CircleDollarSign className="h-4 w-4" />}
                    label="Чистая прибыль"
                    value={formatMoneyOrDash(forecast.currentUnitProfit)}
                    detail={`Маржа ${formatPercentOrDash(forecast.currentMargin)}`}
                    tone={forecast.tone}
                  />
                  <ForecastCompactStat
                    icon={<ReceiptText className="h-4 w-4" />}
                    label="Все расходы"
                    value={formatMoneyOrDash(forecast.totalCostPerUnit)}
                    detail={forecast.costPrecision}
                    tone={
                      forecast.totalCostPerUnit === null ? "muted" : "warning"
                    }
                  />
                  <ForecastCompactStat
                    icon={<BarChart3 className="h-4 w-4" />}
                    label="Скорость"
                    value={
                      forecast.dailyVelocity !== null
                        ? `${forecast.dailyVelocity.toLocaleString("ru-RU", { maximumFractionDigits: 1 })}/день`
                        : "Нет данных"
                    }
                    detail={`Продаж: ${formatUnitsOrDash(forecast.soldUnits)}`}
                    tone={forecast.dailyVelocity === null ? "muted" : "good"}
                  />
                </div>

                <div className="mt-3 grid gap-1.5 rounded-2xl border border-border/45 bg-muted/18 p-2.5">
                  <ForecastUnitLine
                    label="Цена продажи"
                    value={forecast.salePrice}
                    detail="Покупатель платит за 1 шт"
                    tone="info"
                    sign="+"
                  />
                  <ForecastUnitLine
                    label="Себестоимость"
                    value={forecast.cogsPerUnit}
                    detail="Закупка / ручная себестоимость"
                    tone="muted"
                    sign="-"
                  />
                  <ForecastUnitLine
                    label="Расходы WB"
                    value={forecast.wbPerUnit}
                    detail="Комиссии, удержания, хранение и логистика"
                    tone="warning"
                    sign="-"
                  />
                  <ForecastUnitLine
                    label="Логистика внутри WB"
                    value={forecast.logisticsPerUnit}
                    detail="Для контроля, в итог второй раз не входит"
                    tone="info"
                    nested
                  />
                  <ForecastUnitLine
                    label="Реклама"
                    value={forecast.adsPerUnit}
                    detail={`ДРР ${formatPercentOrDash(cockpit.ads.drr)}`}
                    tone="info"
                    sign="-"
                  />
                  <ForecastUnitLine
                    label="Итого расход на 1 шт"
                    value={forecast.totalCostPerUnit}
                    tone="warning"
                    sign="-"
                    strong
                  />
                  <ForecastUnitLine
                    label="Чистая прибыль с 1 шт"
                    value={forecast.currentUnitProfit}
                    detail={`Маржа ${formatPercentOrDash(forecast.currentMargin)}`}
                    tone={forecast.tone}
                    sign="="
                    strong
                  />
                </div>
              </div>

              <div className="min-w-0 rounded-[18px] border border-border/45 bg-background/90 p-3">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div>
                    <h3 className="text-sm font-semibold">
                      Если изменить цену
                    </h3>
                    <p className="mt-0.5 text-xs text-muted-foreground">
                      Введите цену за 1 шт, остальное пересчитается
                      автоматически.
                    </p>
                  </div>
                  <Badge
                    variant="outline"
                    className="h-6 bg-background text-[10px]"
                  >
                    база {formatUnitsOrDash(forecast.forecastBaseUnits)}
                  </Badge>
                </div>

                <div className="mt-3 rounded-2xl border border-border/45 bg-muted/18 p-3">
                  <div className="grid gap-3 md:grid-cols-[minmax(0,230px)_minmax(0,1fr)]">
                    <div>
                      <Label
                        htmlFor="forecast-custom-price"
                        className="text-xs font-semibold uppercase text-muted-foreground"
                      >
                        Цена за 1 шт
                      </Label>
                      <div className="mt-2 flex items-center gap-2">
                        <Input
                          id="forecast-custom-price"
                          inputMode="decimal"
                          value={customPrice}
                          onChange={(event) =>
                            setCustomPrice(event.target.value)
                          }
                          className="h-11 rounded-xl bg-background text-lg font-semibold tabular-nums"
                          placeholder="Например 2490"
                        />
                        <span className="shrink-0 text-sm font-semibold">
                          ₽
                        </span>
                      </div>
                      <div className="mt-2 flex flex-wrap gap-1.5">
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          className="h-7 rounded-lg text-xs"
                          onClick={() =>
                            setCustomPrice(
                              forecast.salePrice === null
                                ? ""
                                : String(Math.round(forecast.salePrice)),
                            )
                          }
                        >
                          Текущая
                        </Button>
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          className="h-7 rounded-lg text-xs"
                          onClick={() =>
                            setCustomPrice(
                              recommendedPrice === null
                                ? ""
                                : String(Math.round(recommendedPrice)),
                            )
                          }
                        >
                          Рекоменд.
                        </Button>
                      </div>
                    </div>

                    <div className="grid gap-2 sm:grid-cols-2">
                      <ForecastCompactStat
                        icon={<CircleDollarSign className="h-4 w-4" />}
                        label="Прибыль с 1 шт"
                        value={formatMoneyOrDash(customScenario?.unitProfit)}
                        detail={`Разница ${formatSignedMoney(unitDelta)}`}
                        tone={
                          customScenario
                            ? forecastToneByProfit(customScenario.unitProfit)
                            : "muted"
                        }
                      />
                      <ForecastCompactStat
                        icon={<Percent className="h-4 w-4" />}
                        label="Маржа"
                        value={formatPercentOrDash(customScenario?.margin)}
                        detail={
                          manualPriceGap === null
                            ? "Порог не рассчитан"
                            : manualPriceGap < 0
                              ? `Ниже порога ${formatMoneyOrDash(Math.abs(manualPriceGap))}`
                              : `Запас ${formatMoneyOrDash(manualPriceGap)}`
                        }
                        tone={
                          manualPriceGap !== null && manualPriceGap < 0
                            ? "danger"
                            : customScenario
                              ? forecastToneByProfit(customScenario.unitProfit)
                              : "muted"
                        }
                      />
                    </div>
                  </div>

                  {customScenario ? (
                    <div className="mt-3 grid gap-1.5">
                      <ForecastUnitLine
                        label="Ваша цена"
                        value={customScenario.price}
                        detail={`Изменение цены ${formatPercentOrDash(customScenario.delta * 100)}`}
                        tone="info"
                        sign="+"
                      />
                      <ForecastUnitLine
                        label="Тот же расход на 1 шт"
                        value={forecast.totalCostPerUnit}
                        detail={forecast.costPrecision}
                        tone="warning"
                        sign="-"
                      />
                      <ForecastUnitLine
                        label="Новая прибыль с 1 шт"
                        value={customScenario.unitProfit}
                        detail={`К текущей прибыли ${formatSignedMoney(unitDelta)}`}
                        tone={forecastToneByProfit(customScenario.unitProfit)}
                        sign="="
                        strong
                      />
                    </div>
                  ) : (
                    <div className="mt-3 rounded-xl border border-warning/35 bg-warning/5 p-3 text-sm text-warning">
                      Нужны цена, продажи в штуках и расход на 1 шт.
                    </div>
                  )}
                </div>

                {customScenario ? (
                  <div className="mt-3 grid gap-2 sm:grid-cols-3">
                    <ForecastCompactStat
                      icon={<Boxes className="h-4 w-4" />}
                      label="Продаж за период"
                      value={formatUnitsOrDash(customScenario.projectedUnits)}
                      detail={
                        customScenario.stockLimited
                          ? "Ограничено остатком"
                          : "По скорости"
                      }
                      tone={customScenario.stockLimited ? "warning" : "info"}
                    />
                    <ForecastCompactStat
                      icon={<BarChart3 className="h-4 w-4" />}
                      label="Выручка"
                      value={formatMoneyOrDash(customScenario.projectedRevenue)}
                      detail="Цена x продажи"
                      tone="info"
                    />
                    <ForecastCompactStat
                      icon={<CircleDollarSign className="h-4 w-4" />}
                      label="Прибыль за период"
                      value={formatMoneyOrDash(customScenario.projectedProfit)}
                      detail={`К текущей ${formatSignedMoney(customScenario.deltaProfit)}`}
                      tone={forecastToneByProfit(customScenario.unitProfit)}
                    />
                  </div>
                ) : null}

                <div className="mt-3 grid gap-2 md:grid-cols-[minmax(0,1fr)_260px]">
                  <div className="rounded-2xl border border-border/45 bg-background/78 p-3">
                    <div className="flex items-start gap-2">
                      <Sparkles className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
                      <div>
                        <div className="text-sm font-semibold">
                          {forecast.recommendation}
                        </div>
                        <div className="mt-1 text-xs leading-snug text-muted-foreground">
                          Рекомендованная цена:{" "}
                          {formatMoneyOrDash(recommendedPrice)}. Эффект за
                          период: {formatSignedMoney(recommendedDelta)}.
                        </div>
                      </div>
                    </div>
                  </div>
                  <div className="rounded-2xl border border-border/45 bg-background/78 p-3">
                    <div className="text-[10px] font-semibold uppercase text-muted-foreground">
                      Пороги
                    </div>
                    <div className="mt-2 grid gap-1 text-xs">
                      <div className="flex justify-between gap-2">
                        <span>Безубыточность</span>
                        <span className="font-semibold tabular-nums">
                          {formatMoneyOrDash(forecast.breakEven)}
                        </span>
                      </div>
                      <div className="flex justify-between gap-2">
                        <span>Цель по марже</span>
                        <span className="font-semibold tabular-nums">
                          {formatMoneyOrDash(forecast.targetPrice)}
                        </span>
                      </div>
                    </div>
                  </div>
                </div>

                {forecast.scenarios.length ? (
                  <div className="mt-3">
                    <div className="mb-2 flex items-center justify-between gap-2">
                      <h4 className="text-sm font-semibold">
                        Быстрые варианты
                      </h4>
                      <Badge
                        variant="outline"
                        className="h-6 bg-background text-[10px]"
                      >
                        1 шт + период
                      </Badge>
                    </div>
                    <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-5">
                      {forecast.scenarios.map((scenario: any) => (
                        <ForecastScenarioStrip
                          key={scenario.deltaLabel}
                          scenario={scenario}
                          recommended={forecast.recommended === scenario}
                        />
                      ))}
                    </div>
                  </div>
                ) : null}
              </div>
            </div>

            <div className="mt-3 grid gap-3 lg:grid-cols-[minmax(0,1fr)_330px]">
              <div className="rounded-[18px] border border-border/45 bg-background/90 p-3">
                <div className="mb-2 flex items-center justify-between gap-2">
                  <h3 className="text-sm font-semibold">
                    Что влияет на расчет
                  </h3>
                  <Badge
                    variant="outline"
                    className="h-6 bg-background text-[10px]"
                  >
                    {forecast.levers.length} факторов
                  </Badge>
                </div>
                <div className="grid gap-2 md:grid-cols-2 xl:grid-cols-4">
                  {forecast.levers.slice(0, 4).map((lever: any) => (
                    <div
                      key={lever.key}
                      className={cn(
                        "min-h-[88px] rounded-xl border p-2.5",
                        COCKPIT_SOFT_TONE[lever.tone ?? "default"],
                      )}
                    >
                      <div className="flex items-start justify-between gap-2">
                        <span
                          className={cn(
                            "inline-flex h-7 w-7 items-center justify-center rounded-lg",
                            COCKPIT_ICON_TONE[lever.tone ?? "default"],
                          )}
                        >
                          <ForecastLeverIcon icon={lever.icon} />
                        </span>
                        <span
                          className={cn(
                            "text-xs font-semibold tabular-nums",
                            COCKPIT_TEXT_TONE[lever.tone ?? "default"],
                          )}
                        >
                          {lever.value}
                        </span>
                      </div>
                      <div className="mt-1.5 text-xs font-semibold">
                        {lever.title}
                      </div>
                      <div className="mt-0.5 line-clamp-2 text-[11px] leading-snug text-muted-foreground">
                        {lever.detail}
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              <div className="space-y-2">
                {forecast.dataNotes.length ? (
                  <div className="rounded-[18px] border border-warning/35 bg-warning/5 p-3">
                    <div className="flex items-center gap-2 text-sm font-semibold text-warning">
                      <AlertTriangle className="h-4 w-4" />
                      Проверить
                    </div>
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      {forecast.dataNotes.slice(0, 4).map((note: string) => (
                        <Badge
                          key={note}
                          variant="outline"
                          className="bg-background text-[10px]"
                        >
                          {note}
                        </Badge>
                      ))}
                    </div>
                  </div>
                ) : null}

                <details className="rounded-[18px] border border-border/45 bg-background/90 p-3">
                  <summary className="cursor-pointer text-sm font-semibold">
                    Формулы
                  </summary>
                  <div className="mt-2 grid gap-1.5 text-xs leading-snug text-muted-foreground">
                    <div>
                      1 шт прибыль = цена - себестоимость - WB расходы -
                      реклама.
                    </div>
                    <div>
                      Логистика входит в WB расходы и не добавляется второй раз.
                    </div>
                    <div>
                      Прогноз продаж = база продаж x реакция спроса на цену,
                      затем ограничение по складу.
                    </div>
                    {forecast.elasticityReasons
                      .slice(0, 2)
                      .map((reason: string) => (
                        <div key={reason}>- {reason}</div>
                      ))}
                  </div>
                </details>
              </div>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </section>
  );
}

function ForecastScenarioDecisionRow({
  scenario,
  recommended,
  onSelect,
}: {
  scenario: any;
  recommended: boolean;
  onSelect: () => void;
}) {
  const isCurrent = scenario.delta === 0;
  const positive = scenario.unitProfit >= 0;
  return (
    <button
      type="button"
      onClick={onSelect}
      className={cn(
        "grid w-full gap-2 border-b border-border/55 px-3 py-2.5 text-left transition last:border-b-0 hover:bg-muted/35 md:grid-cols-[126px_120px_120px_120px_minmax(0,1fr)] md:items-center",
        recommended ? "bg-primary/5" : "bg-background",
      )}
    >
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="text-sm font-semibold">{scenario.deltaLabel}</span>
        {recommended ? (
          <Badge className="h-5 rounded-full bg-primary text-[9px] text-primary-foreground">
            лучше
          </Badge>
        ) : isCurrent ? (
          <Badge variant="outline" className="h-5 bg-background text-[9px]">
            сейчас
          </Badge>
        ) : null}
      </div>
      <div>
        <div className="text-[10px] uppercase text-muted-foreground">Цена</div>
        <div className="font-semibold tabular-nums">
          {formatMoneyOrDash(scenario.price)}
        </div>
      </div>
      <div>
        <div className="text-[10px] uppercase text-muted-foreground">1 шт</div>
        <div
          className={cn(
            "font-semibold tabular-nums",
            positive ? "text-success" : "text-destructive",
          )}
        >
          {formatMoneyOrDash(scenario.unitProfit)}
        </div>
      </div>
      <div>
        <div className="text-[10px] uppercase text-muted-foreground">Период</div>
        <div
          className={cn(
            "font-semibold tabular-nums",
            scenario.projectedProfit >= 0 ? "text-success" : "text-destructive",
          )}
        >
          {formatMoneyOrDash(scenario.projectedProfit)}
        </div>
      </div>
      <div className="min-w-0">
        <div className="text-[10px] uppercase text-muted-foreground">
          Продажи / эффект
        </div>
        <div className="truncate text-sm text-muted-foreground">
          {formatUnitsOrDash(scenario.projectedUnits)}
          {scenario.deltaProfit !== null && !isCurrent
            ? ` · ${formatSignedMoney(scenario.deltaProfit)}`
            : ""}
          {scenario.stockLimited ? " · ограничено складом" : ""}
        </div>
      </div>
    </button>
  );
}

function ProductForecastPanelSimple({
  cockpit,
  dateFrom,
  dateTo,
  forecast: providedForecast,
}: {
  cockpit: any;
  dateFrom?: string;
  dateTo?: string;
  forecast?: any;
}) {
  const forecast =
    providedForecast ?? buildProductForecast(cockpit, dateFrom, dateTo);
  const initialPrice = forecast.recommended?.price ?? forecast.salePrice ?? "";
  const [customPrice, setCustomPrice] = useState(
    initialPrice === "" ? "" : String(Math.round(initialPrice)),
  );
  const customScenario = buildManualForecastScenario(forecast, customPrice);
  const period =
    dateFrom && dateTo
      ? `${dateFrom} - ${dateTo}`
      : `${forecast.periodDays} дней`;
  const recommendedPrice =
    forecast.recommended?.price ?? forecast.targetPrice ?? null;
  const recommendedDelta = forecast.recommended?.deltaProfit ?? null;
  const manualPriceNumber = positiveNumber(customPrice);
  const manualPriceGap =
    manualPriceNumber !== null && forecast.breakEven !== null
      ? manualPriceNumber - forecast.breakEven
      : null;
  const unitDelta =
    customScenario !== null && forecast.currentUnitProfit !== null
      ? customScenario.unitProfit - forecast.currentUnitProfit
      : null;
  const selectedTone =
    customScenario !== null
      ? forecastToneByProfit(customScenario.unitProfit)
      : "muted";

  return (
    <section id="product-forecast" className="flex scroll-mt-24 justify-end">
      <Dialog>
        <DialogTrigger asChild>
          <Button
            type="button"
            size="lg"
            className="h-10 rounded-full px-4 shadow-none"
          >
            <TrendingUp className="mr-2 h-4 w-4" />
            Прогноз
            <span className="ml-2 rounded-full bg-primary-foreground/15 px-2 py-0.5 text-xs font-semibold">
              {formatMoneyOrDash(forecast.currentUnitProfit)} / шт
            </span>
          </Button>
        </DialogTrigger>

        <DialogContent className="max-h-[calc(100vh-28px)] w-[calc(100vw-28px)] max-w-none overflow-hidden p-0 sm:max-w-[980px]">
          <DialogHeader className="border-b border-border/55 px-5 py-4 text-left">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0">
                <DialogTitle className="flex items-center gap-2 text-xl">
                  <span className="inline-flex h-9 w-9 items-center justify-center rounded-xl bg-primary/10 text-primary">
                    <TrendingUp className="h-4 w-4" />
                  </span>
                  Прогноз цены
                </DialogTitle>
                <DialogDescription className="mt-1 max-w-2xl text-xs leading-snug">
                  Выберите цену и сразу увидите прибыль на 1 штуку, продажи и
                  результат за период.
                </DialogDescription>
              </div>
              <div className="flex flex-wrap justify-end gap-1.5">
                <Badge variant="outline" className="h-6 bg-background text-[10px]">
                  {period}
                </Badge>
                <Badge
                  variant="outline"
                  className={cn(
                    "h-6 bg-background text-[10px]",
                    forecast.confidenceScore >= 80
                      ? "border-success/30 text-success"
                      : forecast.confidenceScore >= 60
                        ? "border-info/30 text-info"
                        : "border-warning/35 text-warning",
                  )}
                >
                  {forecast.confidence}
                </Badge>
              </div>
            </div>
          </DialogHeader>

          <div className="max-h-[calc(100vh-116px)] overflow-y-auto bg-background p-5">
            <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_300px]">
              <div className="rounded-[22px] border border-primary/20 bg-primary/[0.035] p-4">
                <div className="flex items-start gap-3">
                  <span className="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl bg-primary/10 text-primary">
                    <Sparkles className="h-5 w-5" />
                  </span>
                  <div className="min-w-0">
                    <div className="text-sm font-semibold">
                      {forecast.recommendation}
                    </div>
                    <div className="mt-1 text-xs leading-relaxed text-muted-foreground">
                      Рекомендуемая цена {formatMoneyOrDash(recommendedPrice)}.
                      Ожидаемый эффект за период:{" "}
                      <span className="font-semibold text-foreground">
                        {formatSignedMoney(recommendedDelta)}
                      </span>
                      .
                    </div>
                  </div>
                </div>
              </div>

              <div className="grid grid-cols-3 overflow-hidden rounded-[22px] border border-border/55 bg-border/45">
                <div className="bg-background p-3">
                  <div className="text-[10px] uppercase text-muted-foreground">
                    Сейчас
                  </div>
                  <div className="mt-1 text-lg font-semibold tabular-nums text-info">
                    {formatMoneyOrDash(forecast.salePrice)}
                  </div>
                </div>
                <div className="bg-background p-3">
                  <div className="text-[10px] uppercase text-muted-foreground">
                    1 шт
                  </div>
                  <div
                    className={cn(
                      "mt-1 text-lg font-semibold tabular-nums",
                      COCKPIT_TEXT_TONE[forecast.tone],
                    )}
                  >
                    {formatMoneyOrDash(forecast.currentUnitProfit)}
                  </div>
                </div>
                <div className="bg-background p-3">
                  <div className="text-[10px] uppercase text-muted-foreground">
                    Скорость
                  </div>
                  <div className="mt-1 text-lg font-semibold tabular-nums">
                    {forecast.dailyVelocity !== null
                      ? `${forecast.dailyVelocity.toLocaleString("ru-RU", { maximumFractionDigits: 1 })}/д`
                      : "Нет"}
                  </div>
                </div>
              </div>
            </div>

            <div className="mt-4 grid gap-4 lg:grid-cols-[360px_minmax(0,1fr)]">
              <div className="rounded-[22px] border border-border/55 p-4">
                <div className="flex items-center justify-between gap-2">
                  <h3 className="text-base font-semibold">1 продажа сейчас</h3>
                  <Badge variant="outline" className="h-6 bg-background text-[10px]">
                    {forecast.unitsEstimated ? "шт оценены" : "шт из отчета"}
                  </Badge>
                </div>
                <div className="mt-3">
                  <ForecastUnitLine
                    label="Цена продажи"
                    value={forecast.salePrice}
                    tone="info"
                    sign="+"
                  />
                  <ForecastUnitLine
                    label="Себестоимость"
                    value={forecast.cogsPerUnit}
                    tone="muted"
                    sign="-"
                  />
                  <ForecastUnitLine
                    label="Расходы WB"
                    value={forecast.wbPerUnit}
                    detail="Логистика уже внутри этой суммы"
                    tone="warning"
                    sign="-"
                  />
                  <ForecastUnitLine
                    label="Реклама"
                    value={forecast.adsPerUnit}
                    detail={`ДРР ${formatPercentOrDash(cockpit.ads.drr)}`}
                    tone="info"
                    sign="-"
                  />
                  <ForecastUnitLine
                    label="Чистая прибыль"
                    value={forecast.currentUnitProfit}
                    detail={`Маржа ${formatPercentOrDash(forecast.currentMargin)}`}
                    tone={forecast.tone}
                    sign="="
                    strong
                  />
                </div>
              </div>

              <div className="rounded-[22px] border border-border/55 p-4">
                <div className="grid gap-4 md:grid-cols-[230px_minmax(0,1fr)]">
                  <div>
                    <Label
                      htmlFor="forecast-custom-price-simple"
                      className="text-xs font-semibold uppercase text-muted-foreground"
                    >
                      Новая цена
                    </Label>
                    <div className="mt-2 flex items-center gap-2">
                      <Input
                        id="forecast-custom-price-simple"
                        inputMode="decimal"
                        value={customPrice}
                        onChange={(event) => setCustomPrice(event.target.value)}
                        className="h-12 rounded-2xl bg-muted/30 text-xl font-semibold tabular-nums"
                        placeholder="Цена"
                      />
                      <span className="text-sm font-semibold">₽</span>
                    </div>
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        className="h-7 rounded-full text-xs"
                        onClick={() =>
                          setCustomPrice(
                            forecast.salePrice === null
                              ? ""
                              : String(Math.round(forecast.salePrice)),
                          )
                        }
                      >
                        Текущая
                      </Button>
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        className="h-7 rounded-full text-xs"
                        onClick={() =>
                          setCustomPrice(
                            recommendedPrice === null
                              ? ""
                              : String(Math.round(recommendedPrice)),
                          )
                        }
                      >
                        Рекоменд.
                      </Button>
                    </div>
                  </div>

                  <div className="rounded-2xl bg-muted/20 px-3 py-2.5">
                    <div className="grid gap-2">
                      <div className="flex items-center justify-between gap-3 border-b border-border/50 pb-2">
                        <div className="text-sm font-medium">Прибыль с 1 шт</div>
                        <div
                          className={cn(
                            "text-lg font-semibold tabular-nums",
                            COCKPIT_TEXT_TONE[selectedTone],
                          )}
                        >
                          {formatMoneyOrDash(customScenario?.unitProfit)}
                        </div>
                      </div>
                      <div className="flex items-center justify-between gap-3 border-b border-border/50 pb-2 text-sm">
                        <span className="text-muted-foreground">Маржа</span>
                        <span
                          className={cn(
                            "font-semibold tabular-nums",
                            COCKPIT_TEXT_TONE[
                              manualPriceGap !== null && manualPriceGap < 0
                                ? "danger"
                                : selectedTone
                            ],
                          )}
                        >
                          {formatPercentOrDash(customScenario?.margin)}
                        </span>
                      </div>
                      <div className="flex items-center justify-between gap-3 text-sm">
                        <span className="text-muted-foreground">
                          Прибыль за период
                        </span>
                        <span
                          className={cn(
                            "font-semibold tabular-nums",
                            COCKPIT_TEXT_TONE[selectedTone],
                          )}
                        >
                          {formatMoneyOrDash(customScenario?.projectedProfit)}
                        </span>
                      </div>
                    </div>
                    <div className="mt-2 text-[11px] leading-snug text-muted-foreground">
                      {manualPriceGap === null
                        ? "Порог не рассчитан."
                        : manualPriceGap < 0
                          ? `Цена ниже безубыточности на ${formatMoneyOrDash(Math.abs(manualPriceGap))}.`
                          : `Запас до безубыточности ${formatMoneyOrDash(manualPriceGap)}.`}{" "}
                      К текущей прибыли: {formatSignedMoney(unitDelta)}.
                    </div>
                  </div>
                </div>

                {customScenario ? (
                  <div className="mt-4 rounded-2xl bg-muted/20 px-3 py-2.5 text-sm">
                    <div className="grid gap-2 md:grid-cols-3">
                      <div>
                        <span className="text-muted-foreground">Выручка: </span>
                        <span className="font-semibold tabular-nums">
                          {formatMoneyOrDash(customScenario.projectedRevenue)}
                        </span>
                      </div>
                      <div>
                        <span className="text-muted-foreground">
                          Изменение цены:{" "}
                        </span>
                        <span className="font-semibold tabular-nums">
                          {formatPercentOrDash(customScenario.delta * 100)}
                        </span>
                      </div>
                      <div>
                        <span className="text-muted-foreground">Эффект: </span>
                        <span
                          className={cn(
                            "font-semibold tabular-nums",
                            (customScenario.deltaProfit ?? 0) >= 0
                              ? "text-success"
                              : "text-destructive",
                          )}
                        >
                          {formatSignedMoney(customScenario.deltaProfit)}
                        </span>
                      </div>
                    </div>
                  </div>
                ) : (
                  <div className="mt-4 rounded-2xl border border-warning/35 bg-warning/5 p-3 text-sm text-warning">
                    Нужны цена, продажи и расход на 1 штуку.
                  </div>
                )}
              </div>
            </div>

            {forecast.scenarios.length ? (
              <div className="mt-4 overflow-hidden rounded-[22px] border border-border/55">
                <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border/55 bg-muted/18 px-4 py-3">
                  <div>
                    <h3 className="text-base font-semibold">
                      Быстрые варианты
                    </h3>
                    <p className="text-xs text-muted-foreground">
                      Нажмите строку, чтобы подставить цену.
                    </p>
                  </div>
                  <Badge variant="outline" className="h-6 bg-background text-[10px]">
                    1 шт + период
                  </Badge>
                </div>
                {forecast.scenarios.map((scenario: any) => (
                  <ForecastScenarioDecisionRow
                    key={scenario.deltaLabel}
                    scenario={scenario}
                    recommended={forecast.recommended === scenario}
                    onSelect={() =>
                      setCustomPrice(String(Math.round(scenario.price)))
                    }
                  />
                ))}
              </div>
            ) : null}

            <details className="mt-4 rounded-[22px] border border-border/55 bg-muted/10 p-4">
              <summary className="cursor-pointer text-sm font-semibold">
                Расходы, факторы и формулы
              </summary>
              <div className="mt-4 grid gap-4 lg:grid-cols-[minmax(0,1fr)_280px]">
                <div>
                  <div className="text-xs font-semibold uppercase text-muted-foreground">
                    Расходы на 1 штуку
                  </div>
                  <div className="mt-2">
                    {forecast.costRows
                      .filter((row: any) => row.key !== "other_wb")
                      .map((row: any) => (
                        <ForecastUnitLine
                          key={row.key}
                          label={row.label}
                          value={row.value}
                          detail={row.detail}
                          tone={row.tone}
                          nested={row.nested}
                        />
                      ))}
                  </div>
                </div>
                <div className="grid gap-3">
                  <div>
                    <div className="text-xs font-semibold uppercase text-muted-foreground">
                      Факторы
                    </div>
                    <div className="mt-2 grid gap-2">
                      {forecast.levers.slice(0, 4).map((lever: any) => (
                        <div key={lever.key} className="flex gap-2 text-xs">
                          <span
                            className={cn(
                              "inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-lg",
                              COCKPIT_ICON_TONE[lever.tone ?? "default"],
                            )}
                          >
                            <ForecastLeverIcon icon={lever.icon} />
                          </span>
                          <div className="min-w-0">
                            <div className="font-semibold">{lever.title}</div>
                            <div className="line-clamp-2 text-muted-foreground">
                              {lever.detail}
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                  {forecast.dataNotes.length ? (
                    <div>
                      <div className="text-xs font-semibold uppercase text-muted-foreground">
                        Проверить
                      </div>
                      <div className="mt-2 flex flex-wrap gap-1.5">
                        {forecast.dataNotes.slice(0, 4).map((note: string) => (
                          <Badge
                            key={note}
                            variant="outline"
                            className="bg-background text-[10px]"
                          >
                            {note}
                          </Badge>
                        ))}
                      </div>
                    </div>
                  ) : null}
                  <div className="text-xs leading-relaxed text-muted-foreground">
                    Прибыль/шт = цена - себестоимость - WB расходы - реклама.
                    Логистика уже входит в WB расходы и второй раз не
                    добавляется.
                  </div>
                </div>
              </div>
            </details>
          </div>
        </DialogContent>
      </Dialog>
    </section>
  );
}

function ProductForecastPanelLegacy({
  cockpit,
  dateFrom,
  dateTo,
  forecast: providedForecast,
}: {
  cockpit: any;
  dateFrom?: string;
  dateTo?: string;
  forecast?: any;
}) {
  const forecast =
    providedForecast ?? buildProductForecast(cockpit, dateFrom, dateTo);
  const initialPrice = forecast.recommended?.price ?? forecast.salePrice ?? "";
  const [customPrice, setCustomPrice] = useState(
    initialPrice === "" ? "" : String(Math.round(initialPrice)),
  );
  const customScenario = buildManualForecastScenario(forecast, customPrice);
  const period =
    dateFrom && dateTo
      ? `${dateFrom} - ${dateTo}`
      : `${forecast.periodDays} дней`;
  const maxCost = Math.max(
    1,
    ...forecast.costRows
      .map((row: any) => Math.abs(toFiniteNumber(row.value) ?? 0))
      .filter(Number.isFinite),
  );
  const recommendedPrice =
    forecast.recommended?.price ?? forecast.targetPrice ?? null;
  const recommendedDelta = forecast.recommended?.deltaProfit ?? null;
  const manualPriceNumber = positiveNumber(customPrice);
  const manualPriceGap =
    manualPriceNumber !== null && forecast.breakEven !== null
      ? manualPriceNumber - forecast.breakEven
      : null;

  return (
    <section id="product-forecast" className="flex scroll-mt-24 justify-end">
      <Dialog>
        <DialogTrigger asChild>
          <Button
            type="button"
            size="lg"
            className="h-12 rounded-xl px-4 shadow-sm"
          >
            <TrendingUp className="mr-2 h-4 w-4" />
            Открыть прогноз
            <span className="ml-2 rounded-lg bg-primary-foreground/15 px-2 py-0.5 text-xs font-semibold">
              {formatMoneyOrDash(recommendedPrice)}
            </span>
          </Button>
        </DialogTrigger>
        <DialogContent className="max-h-[calc(100vh-32px)] w-[calc(100vw-32px)] max-w-none overflow-hidden p-0 sm:max-w-[1180px]">
          <DialogHeader className="border-b border-border/55 px-5 py-4 text-left">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0">
                <DialogTitle className="flex flex-wrap items-center gap-2 text-xl">
                  <span className="inline-flex h-9 w-9 items-center justify-center rounded-xl bg-primary/10 text-primary">
                    <TrendingUp className="h-4 w-4" />
                  </span>
                  Прогноз цены и маржи
                </DialogTitle>
                <DialogDescription className="mt-2 max-w-3xl text-xs leading-snug">
                  Слева текущая экономика карточки, справа расчет по вашей цене
                  продажи. Все суммы считаются по выбранному периоду.
                </DialogDescription>
              </div>
              <div className="flex flex-wrap justify-end gap-2">
                <Badge
                  variant="outline"
                  className="h-7 bg-background px-2.5 text-xs"
                >
                  {period}
                </Badge>
                <Badge
                  variant="outline"
                  className={cn(
                    "h-7 bg-background px-2.5 text-xs",
                    forecast.confidenceScore >= 80
                      ? "border-success/30 text-success"
                      : forecast.confidenceScore >= 60
                        ? "border-info/30 text-info"
                        : "border-warning/35 text-warning",
                  )}
                >
                  Точность: {forecast.confidence}
                </Badge>
              </div>
            </div>
          </DialogHeader>

          <div className="max-h-[calc(100vh-136px)] overflow-y-auto bg-muted/10 p-4">
            <div className="grid gap-4 lg:grid-cols-[minmax(0,420px)_minmax(0,1fr)]">
              <div className="min-w-0 rounded-[22px] border border-border/45 bg-background/86 p-3.5">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <h3 className="text-base font-semibold">
                      Текущее состояние
                    </h3>
                    <p className="mt-1 text-xs text-muted-foreground">
                      Цена, скорость продаж и расход на одну продажу сейчас.
                    </p>
                  </div>
                  <Badge
                    variant="outline"
                    className="h-6 bg-background text-[10px]"
                  >
                    {forecast.unitsEstimated ? "шт оценены" : "шт из отчета"}
                  </Badge>
                </div>

                <div className="mt-3 grid gap-px overflow-hidden rounded-2xl border border-border/45 bg-border/45 sm:grid-cols-2">
                  <ForecastKpi
                    icon={<Tag className="h-4 w-4" />}
                    label="Цена продажи"
                    value={formatMoneyOrDash(forecast.salePrice)}
                    detail={`Безубыточность: ${formatMoneyOrDash(forecast.breakEven)}`}
                    tone={forecast.salePrice === null ? "muted" : "info"}
                  />
                  <ForecastKpi
                    icon={<CircleDollarSign className="h-4 w-4" />}
                    label="Прибыль на 1 шт"
                    value={formatMoneyOrDash(forecast.currentUnitProfit)}
                    detail={`Маржа ${formatPercentOrDash(forecast.currentMargin)}`}
                    tone={forecast.tone}
                  />
                  <ForecastKpi
                    icon={<ReceiptText className="h-4 w-4" />}
                    label="Расход на 1 шт"
                    value={formatMoneyOrDash(forecast.totalCostPerUnit)}
                    detail="Себестоимость + WB + реклама"
                    tone={
                      forecast.totalCostPerUnit === null ? "muted" : "warning"
                    }
                  />
                  <ForecastKpi
                    icon={<BarChart3 className="h-4 w-4" />}
                    label="Скорость"
                    value={
                      forecast.dailyVelocity !== null
                        ? `${forecast.dailyVelocity.toLocaleString("ru-RU", { maximumFractionDigits: 1 })}/день`
                        : "Нет данных"
                    }
                    detail={`Продаж: ${formatUnitsOrDash(forecast.soldUnits)}`}
                    tone={forecast.dailyVelocity === null ? "muted" : "good"}
                  />
                </div>

                <div className="mt-3 rounded-2xl border border-border/45 bg-muted/18 p-3 text-xs">
                  <div className="font-semibold">Формула</div>
                  <div className="mt-1 leading-snug text-muted-foreground">
                    Прибыль/шт = цена продажи - себестоимость - WB расходы -
                    реклама.
                  </div>
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    <Badge
                      variant="outline"
                      className="bg-background text-[10px]"
                    >
                      {formatMoneyOrDash(forecast.salePrice)}
                    </Badge>
                    <Badge
                      variant="outline"
                      className="bg-background text-[10px]"
                    >
                      - {formatMoneyOrDash(forecast.totalCostPerUnit)}
                    </Badge>
                    <Badge
                      variant="outline"
                      className={cn(
                        "bg-background text-[10px]",
                        forecast.currentUnitProfit !== null &&
                          forecast.currentUnitProfit < 0
                          ? "text-destructive"
                          : "text-success",
                      )}
                    >
                      = {formatMoneyOrDash(forecast.currentUnitProfit)}
                    </Badge>
                  </div>
                </div>

                <div className="mt-3 grid gap-2.5">
                  {forecast.costRows.map((row: any) => (
                    <ForecastCostRow key={row.key} row={row} max={maxCost} />
                  ))}
                </div>
              </div>

              <div className="min-w-0 rounded-[22px] border border-border/45 bg-background/86 p-3.5">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <h3 className="text-base font-semibold">
                      Прогноз по вашей цене
                    </h3>
                    <p className="mt-1 text-xs text-muted-foreground">
                      Введите новую цену продажи и сразу увидите прогноз.
                    </p>
                  </div>
                  <Badge
                    variant="outline"
                    className="h-6 bg-background text-[10px]"
                  >
                    база {formatUnitsOrDash(forecast.forecastBaseUnits)}
                  </Badge>
                </div>

                <div className="mt-3 grid gap-3 md:grid-cols-[minmax(0,260px)_minmax(0,1fr)]">
                  <div className="rounded-2xl border border-border/45 bg-muted/18 p-3">
                    <Label
                      htmlFor="forecast-custom-price"
                      className="text-xs font-semibold uppercase text-muted-foreground"
                    >
                      Новая цена продажи
                    </Label>
                    <div className="mt-2 flex items-center gap-2">
                      <Input
                        id="forecast-custom-price"
                        inputMode="decimal"
                        value={customPrice}
                        onChange={(event) => setCustomPrice(event.target.value)}
                        className="h-11 rounded-xl bg-background text-lg font-semibold tabular-nums"
                        placeholder="Например 2490"
                      />
                      <span className="shrink-0 text-sm font-semibold">₽</span>
                    </div>
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        className="h-7 rounded-lg text-xs"
                        onClick={() =>
                          setCustomPrice(
                            forecast.salePrice === null
                              ? ""
                              : String(Math.round(forecast.salePrice)),
                          )
                        }
                      >
                        Текущая
                      </Button>
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        className="h-7 rounded-lg text-xs"
                        onClick={() =>
                          setCustomPrice(
                            recommendedPrice === null
                              ? ""
                              : String(Math.round(recommendedPrice)),
                          )
                        }
                      >
                        Рекоменд.
                      </Button>
                    </div>
                    <div
                      className={cn(
                        "mt-3 rounded-xl border p-2 text-xs leading-snug",
                        manualPriceGap !== null && manualPriceGap < 0
                          ? "border-destructive/30 bg-destructive/5 text-destructive"
                          : "border-success/25 bg-success/5 text-success",
                      )}
                    >
                      {manualPriceGap === null
                        ? "Введите цену, чтобы увидеть запас до безубыточности."
                        : manualPriceGap < 0
                          ? `Ниже безубыточности на ${formatMoneyOrDash(Math.abs(manualPriceGap))}.`
                          : `Выше безубыточности на ${formatMoneyOrDash(manualPriceGap)}.`}
                    </div>
                  </div>

                  {customScenario ? (
                    <div className="grid gap-px overflow-hidden rounded-2xl border border-border/45 bg-border/45 sm:grid-cols-2">
                      <ForecastKpi
                        icon={<Boxes className="h-4 w-4" />}
                        label="Прогноз продаж"
                        value={formatUnitsOrDash(customScenario.projectedUnits)}
                        detail={
                          customScenario.stockLimited
                            ? "Ограничено остатком"
                            : "По скорости и цене"
                        }
                        tone={customScenario.stockLimited ? "warning" : "info"}
                      />
                      <ForecastKpi
                        icon={<BarChart3 className="h-4 w-4" />}
                        label="Выручка"
                        value={formatMoneyOrDash(
                          customScenario.projectedRevenue,
                        )}
                        detail={`К текущей цене: ${formatPercentOrDash(customScenario.delta * 100)}`}
                        tone="info"
                      />
                      <ForecastKpi
                        icon={<CircleDollarSign className="h-4 w-4" />}
                        label="Прибыль"
                        value={formatMoneyOrDash(
                          customScenario.projectedProfit,
                        )}
                        detail={`К текущей: ${formatSignedMoney(customScenario.deltaProfit)}`}
                        tone={forecastToneByProfit(customScenario.unitProfit)}
                      />
                      <ForecastKpi
                        icon={<Percent className="h-4 w-4" />}
                        label="Маржа"
                        value={formatPercentOrDash(customScenario.margin)}
                        detail={`Прибыль/шт ${formatMoneyOrDash(customScenario.unitProfit)}`}
                        tone={forecastToneByProfit(customScenario.unitProfit)}
                      />
                    </div>
                  ) : (
                    <div className="rounded-2xl border border-warning/35 bg-warning/5 p-4">
                      <div className="font-semibold text-warning">
                        Прогноз пока не считается
                      </div>
                      <div className="mt-1 text-sm text-muted-foreground">
                        Нужны цена продажи, продажи в штуках и расход на одну
                        продажу.
                      </div>
                    </div>
                  )}
                </div>

                <div className="mt-3 rounded-2xl border border-border/45 bg-muted/18 p-3">
                  <div className="flex items-start gap-2">
                    <Sparkles className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
                    <div>
                      <div className="text-sm font-semibold">
                        {forecast.recommendation}
                      </div>
                      <div className="mt-1 text-xs leading-snug text-muted-foreground">
                        Рекомендуемая цена:{" "}
                        {formatMoneyOrDash(recommendedPrice)}. Эффект к текущей:{" "}
                        {formatSignedMoney(recommendedDelta)}.
                      </div>
                    </div>
                  </div>
                </div>

                {forecast.scenarios.length ? (
                  <div className="mt-3">
                    <div className="mb-2 flex items-center justify-between gap-3">
                      <h4 className="text-sm font-semibold">
                        Готовые сценарии
                      </h4>
                      <Badge
                        variant="outline"
                        className="h-6 bg-background text-[10px]"
                      >
                        +/- цена
                      </Badge>
                    </div>
                    <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
                      {forecast.scenarios.map((scenario: any) => (
                        <ForecastScenarioCard
                          key={scenario.deltaLabel}
                          scenario={scenario}
                          recommended={forecast.recommended === scenario}
                        />
                      ))}
                    </div>
                  </div>
                ) : null}
              </div>
            </div>

            <div className="mt-4 grid gap-4 lg:grid-cols-[minmax(0,1fr)_360px]">
              <div>
                <div className="mb-2 flex items-center justify-between gap-3">
                  <h3 className="text-base font-semibold">
                    Что влияет на прогноз
                  </h3>
                  <Badge
                    variant="outline"
                    className="h-6 bg-background text-[10px]"
                  >
                    {forecast.levers.length} факторов
                  </Badge>
                </div>
                <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
                  {forecast.levers.slice(0, 4).map((lever: any) => (
                    <div
                      key={lever.key}
                      className={cn(
                        "min-h-[118px] rounded-2xl border p-3",
                        COCKPIT_SOFT_TONE[lever.tone ?? "default"],
                      )}
                    >
                      <div className="flex items-start justify-between gap-2">
                        <span
                          className={cn(
                            "inline-flex h-8 w-8 items-center justify-center rounded-lg",
                            COCKPIT_ICON_TONE[lever.tone ?? "default"],
                          )}
                        >
                          <ForecastLeverIcon icon={lever.icon} />
                        </span>
                        <span
                          className={cn(
                            "text-sm font-semibold tabular-nums",
                            COCKPIT_TEXT_TONE[lever.tone ?? "default"],
                          )}
                        >
                          {lever.value}
                        </span>
                      </div>
                      <div className="mt-2 text-sm font-semibold">
                        {lever.title}
                      </div>
                      <div className="mt-1 line-clamp-3 text-xs leading-snug text-muted-foreground">
                        {lever.detail}
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              <div className="space-y-3">
                {forecast.dataNotes.length ? (
                  <div className="rounded-2xl border border-warning/35 bg-warning/5 p-3">
                    <div className="flex items-center gap-2 text-sm font-semibold text-warning">
                      <AlertTriangle className="h-4 w-4" />
                      Проверить перед решением
                    </div>
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      {forecast.dataNotes.slice(0, 4).map((note: string) => (
                        <Badge
                          key={note}
                          variant="outline"
                          className="bg-background text-[10px]"
                        >
                          {note}
                        </Badge>
                      ))}
                    </div>
                  </div>
                ) : null}

                <details className="rounded-2xl border border-border/45 bg-background/78 p-3">
                  <summary className="cursor-pointer text-sm font-semibold">
                    Формулы и источники
                  </summary>
                  <div className="mt-2 grid gap-2 text-xs leading-snug text-muted-foreground">
                    <div>
                      Цена продажи берется из актуальной цены со скидкой, затем
                      из текущей цены карточки.
                    </div>
                    <div>
                      Продажи в штуках берутся из финансового отчета; если их
                      нет, оценка = выручка / цена продажи.
                    </div>
                    <div>
                      Расход/шт: себестоимость + WB расходы + реклама. Логистика
                      входит в WB расходы и не прибавляется повторно.
                    </div>
                    <div>
                      Спрос в сценарии: продажи x (1 + эластичность x изменение
                      цены), затем ограничение по текущему складу и товарам в
                      пути.
                    </div>
                    {forecast.elasticityReasons
                      .slice(0, 3)
                      .map((reason: string) => (
                        <div key={reason}>- {reason}</div>
                      ))}
                  </div>
                </details>
              </div>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </section>
  );
}

function SignalStat({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="rounded-xl border border-border/45 bg-background/64 px-2.5 py-2">
      <div className="text-[10px] font-semibold uppercase text-muted-foreground">
        {label}
      </div>
      <div className="mt-1 truncate text-sm font-semibold tabular-nums">
        {value}
      </div>
    </div>
  );
}

function MainSignalPanel({
  cockpit,
  nmId,
}: {
  cockpit: any;
  nmId: string | number;
}) {
  const primary = cockpit.problems[0];

  return (
    <aside className="space-y-3">
      <div className="flex items-center gap-2">
        <span className="inline-flex h-8 w-8 items-center justify-center rounded-lg bg-primary/10 text-primary">
          <Sparkles className="h-4 w-4" />
        </span>
        <div className="text-sm font-semibold">Что сделать сейчас</div>
      </div>

      {primary ? (
        <div
          className={cn(
            "relative overflow-hidden rounded-2xl border p-3 before:absolute before:inset-y-3 before:left-0 before:w-1 before:rounded-r-full",
            COCKPIT_SOFT_TONE[primary.tone ?? "warning"],
            COCKPIT_ACCENT_TONE[primary.tone ?? "warning"],
          )}
        >
          <div className="flex flex-wrap items-center gap-1.5">
            <Badge variant="outline" className="bg-background/80 text-[10px]">
              {primary.source}
            </Badge>
            {primary.amount !== null && primary.amount !== undefined ? (
              <Badge variant="outline" className="bg-background/80 text-[10px]">
                {formatMoneyTiny(primary.amount)}
              </Badge>
            ) : null}
          </div>
          <div className="mt-2 text-sm font-semibold leading-snug">
            {primary.title}
          </div>
          {primary.detail ? (
            <div className="mt-1.5 line-clamp-3 text-xs leading-snug text-muted-foreground">
              {primary.detail}
            </div>
          ) : null}
          {primary.link?.to ? (
            <Button
              asChild
              size="sm"
              className={cn("mt-3 h-9 w-full text-xs", CONTROL_BUTTON_CLASS)}
            >
              <Link
                to={primary.link.to as any}
                search={primary.link.search as any}
                params={primary.link.params as any}
              >
                Открыть блок <ArrowRight className="ml-1 h-3.5 w-3.5" />
              </Link>
            </Button>
          ) : null}
        </div>
      ) : (
        <div className="rounded-2xl border border-success/20 bg-success/5 p-3">
          <div className="flex items-center gap-2 text-success">
            <CheckCircle2 className="h-4 w-4" />
            <div className="font-semibold">Критичных задач нет</div>
          </div>
          <div className="mt-1.5 text-xs text-muted-foreground">
            Карточка сейчас без открытых блокеров.
          </div>
        </div>
      )}

      <div className="grid grid-cols-3 gap-2">
        <SignalStat label="Действия" value={cockpit.actions.open} />
        <SignalStat
          label="Карточка"
          value={
            cockpit.quality.score !== null
              ? `${Math.round(cockpit.quality.score)}/100`
              : "Нет"
          }
        />
        <SignalStat label="Данные" value={cockpit.dataQuality.issueCount} />
      </div>

      <div className="grid grid-cols-2 gap-2">
        <Button
          asChild
          size="sm"
          variant="outline"
          className={cn(
            "h-9 border-border/55 bg-background/70 text-xs",
            CONTROL_BUTTON_CLASS,
          )}
        >
          <Link to="/action-center" search={{ nm_id: String(nmId) } as any}>
            <ListChecks className="mr-1 h-3.5 w-3.5" />
            Задачи
          </Link>
        </Button>
        <Button
          asChild
          size="sm"
          variant="outline"
          className={cn(
            "h-9 border-border/55 bg-background/70 text-xs",
            CONTROL_BUTTON_CLASS,
          )}
        >
          <Link to="/results" search={{ nm_id: String(nmId) } as any}>
            <ReceiptText className="mr-1 h-3.5 w-3.5" />
            История
          </Link>
        </Button>
      </div>
    </aside>
  );
}

const COMMAND_TILE_SPAN: Record<string, string> = {
  normal: "",
  wide: "",
  large: "",
  compact: "",
};

function CommandTile({
  icon,
  title,
  value,
  detail,
  tone = "default",
  to,
  href,
  search,
  params,
  signals = [],
  span = "normal",
  testId,
}: {
  icon: ReactNode;
  title: string;
  value: ReactNode;
  detail?: ReactNode;
  tone?: CockpitTone;
  to: string;
  href?: string;
  search?: Record<string, any>;
  params?: Record<string, any>;
  signals?: Array<{ label: string; value: ReactNode }>;
  span?: "normal" | "wide" | "large" | "compact";
  testId?: string;
}) {
  const className = cn(
    "group relative block min-h-[82px] overflow-hidden rounded-md border bg-background p-2.5 pl-3 outline-none transition before:absolute before:inset-y-0 before:left-0 before:w-1 hover:-translate-y-0.5 hover:border-primary/40 hover:bg-muted/25 hover:shadow-sm focus-visible:ring-2 focus-visible:ring-ring",
    COCKPIT_TONE[tone],
    COCKPIT_ACCENT_TONE[tone],
    COMMAND_TILE_SPAN[span],
  );
  const content = (
    <div className="flex min-h-[62px] items-center gap-3">
      <span
        className={cn(
          "inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-md",
          COCKPIT_ICON_TONE[tone],
        )}
      >
        {icon}
      </span>

      <div className="min-w-0 flex-1">
        <div className="flex min-w-0 items-center gap-2">
          <div className="truncate text-sm font-semibold">{title}</div>
          {detail ? (
            <div className="hidden min-w-0 truncate text-xs text-muted-foreground xl:block">
              {detail}
            </div>
          ) : null}
        </div>
        <div className="mt-1 flex flex-wrap gap-1.5">
          {detail ? (
            <span className="max-w-full truncate rounded bg-muted/55 px-1.5 py-0.5 text-[11px] text-muted-foreground xl:hidden">
              {detail}
            </span>
          ) : null}
          {signals.slice(0, 2).map((signal) => (
            <span
              key={signal.label}
              className="max-w-full truncate rounded bg-muted/55 px-1.5 py-0.5 text-[11px] text-muted-foreground"
            >
              {signal.label}{" "}
              <span className="font-semibold text-foreground tabular-nums">
                {signal.value}
              </span>
            </span>
          ))}
        </div>
      </div>

      <div className="flex shrink-0 items-center gap-2">
        <div
          className={cn(
            "text-right text-lg font-semibold leading-none tabular-nums",
            COCKPIT_TEXT_TONE[tone],
          )}
        >
          {value}
        </div>
        <ArrowRight className="h-4 w-4 shrink-0 text-muted-foreground transition group-hover:text-primary" />
      </div>
    </div>
  );

  if (href) {
    return (
      <a
        href={href}
        data-testid={testId}
        className={className}
        onClick={(event) => {
          if (
            event.defaultPrevented ||
            event.button !== 0 ||
            event.metaKey ||
            event.ctrlKey ||
            event.shiftKey ||
            event.altKey
          ) {
            return;
          }
          event.preventDefault();
          window.location.assign(href);
        }}
      >
        {content}
      </a>
    );
  }

  return (
    <Link
      to={to as any}
      search={search as any}
      params={params as any}
      data-testid={testId}
      className={className}
    >
      {content}
    </Link>
  );
}

function ModuleBoardItem({ item }: { item: any }) {
  const tone = (item.tone ?? "default") as CockpitTone;
  const className = cn(
    "group relative grid min-h-[62px] grid-cols-[30px_minmax(0,1fr)_auto_24px] items-center gap-2 overflow-hidden bg-background/72 px-3 py-2 outline-none transition before:absolute before:inset-y-2 before:left-0 before:w-0.5 before:rounded-r-full hover:bg-muted/30 focus-visible:ring-2 focus-visible:ring-ring",
    COCKPIT_ACCENT_TONE[tone],
  );
  const content = (
    <>
      <span
        className={cn(
          "inline-flex h-[30px] w-[30px] items-center justify-center rounded-md",
          COCKPIT_ICON_TONE[tone],
        )}
      >
        {item.icon}
      </span>
      <div className="min-w-0">
        <div className="flex min-w-0 flex-wrap items-baseline gap-x-2 gap-y-0.5">
          <div className="text-sm font-semibold leading-tight">
            {item.title}
          </div>
          {item.detail ? (
            <div className="min-w-0 truncate text-[11px] text-muted-foreground">
              {item.detail}
            </div>
          ) : null}
        </div>
        {item.signals?.length ? (
          <div className="mt-1 flex flex-wrap gap-1 text-[10.5px] text-muted-foreground">
            {item.signals.slice(0, 2).map((signal: any) => (
              <span
                key={signal.label}
                className="max-w-full truncate rounded-md bg-muted/45 px-1.5 py-0.5"
              >
                {signal.label}{" "}
                <span className="font-semibold text-foreground tabular-nums">
                  {signal.value}
                </span>
              </span>
            ))}
          </div>
        ) : null}
      </div>
      <span
        className={cn(
          "min-w-[74px] truncate text-right text-base font-semibold tabular-nums",
          COCKPIT_TEXT_TONE[tone],
        )}
      >
        {item.value}
      </span>
      <span className="inline-flex h-6 w-6 items-center justify-center rounded-md bg-muted/45 text-muted-foreground transition group-hover:bg-primary group-hover:text-primary-foreground">
        <ArrowRight className="h-3.5 w-3.5" />
      </span>
    </>
  );

  if (item.href) {
    return (
      <a
        href={item.href}
        data-testid={item.testId}
        className={className}
        onClick={(event) => {
          if (
            event.defaultPrevented ||
            event.button !== 0 ||
            event.metaKey ||
            event.ctrlKey ||
            event.shiftKey ||
            event.altKey
          ) {
            return;
          }
          event.preventDefault();
          window.location.assign(item.href);
        }}
      >
        {content}
      </a>
    );
  }

  return (
    <Link
      to={item.to as any}
      search={item.search as any}
      params={item.params as any}
      data-testid={item.testId}
      className={className}
    >
      {content}
    </Link>
  );
}

function ModuleBoard({ items }: { items: any[] }) {
  return (
    <div className="overflow-hidden rounded-[22px] border border-border/45 bg-border/45">
      <div className="grid gap-px lg:grid-cols-2 xl:grid-cols-3">
        {items.map((item) => (
          <ModuleBoardItem key={item.key} item={item} />
        ))}
      </div>
    </div>
  );
}

type CharacteristicDraft = {
  id: string;
  name: string;
  value: string;
};

function localDateTimeInputValue(value?: Date | string | null): string {
  const date =
    value instanceof Date
      ? value
      : value
        ? new Date(String(value))
        : new Date();
  const safeDate = Number.isNaN(date.getTime()) ? new Date() : date;
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${safeDate.getFullYear()}-${pad(safeDate.getMonth() + 1)}-${pad(safeDate.getDate())}T${pad(safeDate.getHours())}:${pad(safeDate.getMinutes())}`;
}

function localDateTimePlusDays(base: string, days: number): string {
  const date = new Date(base);
  if (Number.isNaN(date.getTime())) return localDateTimeInputValue();
  date.setDate(date.getDate() + days);
  return localDateTimeInputValue(date);
}

function moneyDraftValue(value: any): string {
  const number = toFiniteNumber(value);
  return number === null ? "" : String(Math.round(number));
}

function inputNumber(value: string): number | null {
  return toFiniteNumber(value.replace(/\s+/g, "").replace(",", "."));
}

function characteristicValueText(value: any): string {
  if (value === null || value === undefined) return "";
  if (Array.isArray(value))
    return value.map(characteristicValueText).filter(Boolean).join(", ");
  if (typeof value === "object") {
    const nested = firstText(value.value, value.name, value.title, value.label);
    return nested ?? JSON.stringify(value);
  }
  return String(value);
}

function normalizeCharacteristicDrafts(value: any): CharacteristicDraft[] {
  return asArray(value)
    .map((item, index) => {
      const name = firstText(
        item?.name,
        item?.label,
        item?.key,
        item?.char_name,
      );
      const rawValue =
        item?.value ??
        item?.values ??
        item?.text ??
        item?.current_value ??
        item?.current_value_json;
      return {
        id: String(
          item?.id ?? item?.charc_id ?? item?.char_id ?? `char-${index}`,
        ),
        name: name ?? "",
        value: characteristicValueText(rawValue),
      };
    })
    .filter((item) => item.name || item.value)
    .slice(0, 12);
}

function productControlSeed(data: any, cockpit: any) {
  const identity = {
    ...blockData(data?.identity),
    ...(isObj(data?.product_identity) ? data.product_identity : {}),
  };
  const cardQuality = blockData(data?.card_quality ?? data?.quality);
  const issues = asArray(cardQuality.issues);
  const titleIssue = issues.find(
    (issue) =>
      String(issue?.category ?? issue?.field_name ?? "").toLowerCase() ===
      "title",
  );
  const descriptionIssue = issues.find((issue) => {
    const text = String(
      issue?.category ?? issue?.field_name ?? "",
    ).toLowerCase();
    return text === "description" || text.includes("description");
  });
  const characteristicSource =
    identity.characteristics ??
    cardQuality.characteristics ??
    cardQuality.card?.characteristics ??
    cardQuality.snapshot?.characteristics_json ??
    [];
  return {
    title:
      firstText(
        identity.title,
        identity.name,
        titleIssue?.current_value_json,
        titleIssue?.current_value,
        cockpit.identity.title,
      ) ?? "",
    description:
      firstText(
        identity.description,
        cardQuality.description,
        cardQuality.current_description,
        descriptionIssue?.current_value_json,
        descriptionIssue?.current_value,
      ) ?? "",
    characteristics: normalizeCharacteristicDrafts(characteristicSource),
    updatedAt: firstText(identity.updated_at_wb, identity.source_updated_at),
  };
}

function ProductControlPanel({
  data,
  cockpit,
  nmId,
  dateFrom,
  dateTo,
}: {
  data: any;
  cockpit: any;
  nmId: string | number;
  dateFrom?: string;
  dateTo?: string;
}) {
  const seed = productControlSeed(data, cockpit);
  const [titleDraft, setTitleDraft] = useState(seed.title);
  const [descriptionDraft, setDescriptionDraft] = useState(seed.description);
  const [basePriceDraft, setBasePriceDraft] = useState(
    moneyDraftValue(cockpit.price.base),
  );
  const [discountPriceDraft, setDiscountPriceDraft] = useState(
    moneyDraftValue(cockpit.price.discounted ?? cockpit.price.current),
  );
  const [promoStart, setPromoStart] = useState(
    localDateTimeInputValue(dateTo ? `${dateTo}T09:00:00` : undefined),
  );
  const [promoEnd, setPromoEnd] = useState(
    localDateTimePlusDays(
      localDateTimeInputValue(dateTo ? `${dateTo}T09:00:00` : undefined),
      7,
    ),
  );
  const [characteristics, setCharacteristics] = useState<CharacteristicDraft[]>(
    seed.characteristics.length
      ? seed.characteristics
      : [
          {
            id: "char-material",
            name: "Материал",
            value: "",
          },
          {
            id: "char-color",
            name: "Цвет",
            value: "",
          },
        ],
  );

  const basePrice = inputNumber(basePriceDraft);
  const discountPrice = inputNumber(discountPriceDraft);
  const effectivePrice = discountPrice ?? basePrice ?? cockpit.price.current;
  const discountPercent =
    basePrice !== null && discountPrice !== null && basePrice > 0
      ? Math.max(0, Math.min(99, 100 - (discountPrice / basePrice) * 100))
      : null;
  const safeGap =
    effectivePrice !== null && cockpit.price.breakEven !== null
      ? effectivePrice - cockpit.price.breakEven
      : null;
  const quarantineRisk =
    basePrice !== null &&
    discountPrice !== null &&
    basePrice > 0 &&
    discountPrice <= basePrice / 3;
  const contentChanged =
    titleDraft.trim() !== seed.title.trim() ||
    descriptionDraft.trim() !== seed.description.trim() ||
    JSON.stringify(characteristics) !== JSON.stringify(seed.characteristics);
  const priceChanged =
    basePriceDraft !== moneyDraftValue(cockpit.price.base) ||
    discountPriceDraft !==
      moneyDraftValue(cockpit.price.discounted ?? cockpit.price.current);
  const periodLabel =
    dateFrom && dateTo ? `${dateFrom} — ${dateTo}` : "текущий период";

  const saveDraft = () => {
    const payload = {
      nm_id: nmId,
      title: titleDraft.trim(),
      description: descriptionDraft.trim(),
      base_price: basePrice,
      discount_price: discountPrice,
      promo_start: promoStart,
      promo_end: promoEnd,
      characteristics,
      saved_at: new Date().toISOString(),
    };
    try {
      if (typeof window !== "undefined") {
        window.localStorage.setItem(
          `product-control-draft:${nmId}`,
          JSON.stringify(payload),
        );
      }
      toast.success("Черновик пульта сохранён");
    } catch {
      toast.error("Не удалось сохранить черновик");
    }
  };

  const schedulePromo = () => {
    saveDraft();
    toast.success(
      "План акции собран. Можно передать менеджеру или подключить WB upload.",
    );
  };

  const submitWb = () => {
    toast.info(
      "Прямая отправка в WB будет через отдельное подтверждение: контент — Content API, цены — Prices and Discounts.",
    );
  };

  const addCharacteristic = () => {
    setCharacteristics((items) => [
      ...items,
      { id: `char-${Date.now()}`, name: "", value: "" },
    ]);
  };

  const updateCharacteristic = (
    id: string,
    patch: Partial<CharacteristicDraft>,
  ) => {
    setCharacteristics((items) =>
      items.map((item) => (item.id === id ? { ...item, ...patch } : item)),
    );
  };

  const removeCharacteristic = (id: string) => {
    setCharacteristics((items) => items.filter((item) => item.id !== id));
  };

  return (
    <Dialog>
      <DialogTrigger asChild>
        <Button
          type="button"
          size="sm"
          variant="outline"
          className={cn(
            "h-8 gap-1.5 rounded-xl border-0 bg-primary/10 px-3 text-xs font-semibold text-primary shadow-sm ring-1 ring-primary/20 hover:bg-primary/15",
            CONTROL_BUTTON_CLASS,
          )}
          data-testid="product-control-open"
        >
          <Workflow className="h-3.5 w-3.5" />
          Пульт WB
        </Button>
      </DialogTrigger>
      <DialogContent className="max-h-[calc(100vh-24px)] w-[calc(100vw-24px)] max-w-[1280px] overflow-hidden rounded-[28px] border-0 bg-background/95 p-0 shadow-[0_30px_110px_rgba(15,23,42,0.35)] ring-1 ring-white/30 backdrop-blur">
        <DialogHeader className="border-b border-border/50 bg-[linear-gradient(135deg,hsl(var(--background))_0%,hsl(var(--muted))_100%)] px-5 py-4 text-left">
          <div className="flex flex-col gap-3 pr-8 lg:flex-row lg:items-start lg:justify-between">
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <span className="inline-flex h-10 w-10 items-center justify-center rounded-2xl bg-primary/10 text-primary shadow-sm ring-1 ring-primary/15">
                  <Workflow className="h-4 w-4" />
                </span>
                <div className="min-w-0">
                  <DialogTitle className="truncate text-base">
                    Пульт управления WB
                  </DialogTitle>
                  <DialogDescription className="mt-1 flex flex-wrap gap-2 text-xs">
                    <span>nm_id {nmId}</span>
                    <span>{periodLabel}</span>
                    {seed.updatedAt ? (
                      <span>
                        WB обновлён {formatDateTimeShort(seed.updatedAt)}
                      </span>
                    ) : null}
                  </DialogDescription>
                </div>
              </div>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button
                size="sm"
                variant="outline"
                className={cn(
                  "h-9 border-0 bg-background/80 px-3 text-xs ring-1 ring-border/60",
                  CONTROL_BUTTON_CLASS,
                )}
                onClick={saveDraft}
              >
                <Save className="h-3.5 w-3.5" />
                Черновик
              </Button>
              <Button
                size="sm"
                variant="outline"
                className={cn(
                  "h-9 border-0 bg-background/80 px-3 text-xs ring-1 ring-border/60",
                  CONTROL_BUTTON_CLASS,
                )}
                onClick={schedulePromo}
              >
                <CalendarClock className="h-3.5 w-3.5" />
                Запланировать
              </Button>
              <Button
                size="sm"
                className={cn(
                  "h-9 bg-primary px-3 text-xs",
                  CONTROL_BUTTON_CLASS,
                )}
                onClick={submitWb}
              >
                <Send className="h-3.5 w-3.5" />
                Отправить
              </Button>
            </div>
          </div>
        </DialogHeader>
        <div className="grid max-h-[calc(100vh-112px)] overflow-hidden bg-muted/25 xl:grid-cols-[minmax(0,1fr)_350px]">
          <div className="space-y-4 overflow-y-auto p-4">
            <div className="grid items-start gap-4 lg:grid-cols-[1.05fr_.95fr]">
              <ProductControlSection
                icon={<Percent className="h-4 w-4" />}
                title="Цена, скидка, акция"
                summary={
                  discountPercent !== null
                    ? `скидка ${discountPercent.toLocaleString("ru-RU", { maximumFractionDigits: 1 })}%`
                    : "ожидает цену"
                }
                tone={
                  quarantineRisk || (safeGap !== null && safeGap < 0)
                    ? "warning"
                    : "good"
                }
                defaultOpen
              >
                <div className="grid gap-3 sm:grid-cols-2">
                  <div className="space-y-1.5">
                    <Label
                      htmlFor={`base-price-${nmId}`}
                      className="text-xs text-muted-foreground"
                    >
                      Основная цена
                    </Label>
                    <Input
                      id={`base-price-${nmId}`}
                      inputMode="decimal"
                      value={basePriceDraft}
                      onChange={(event) =>
                        setBasePriceDraft(event.target.value)
                      }
                      className={cn(
                        CONTROL_INPUT_CLASS,
                        "text-base font-semibold tabular-nums",
                      )}
                      placeholder="0"
                    />
                  </div>
                  <div className="space-y-1.5">
                    <Label
                      htmlFor={`discount-price-${nmId}`}
                      className="text-xs text-muted-foreground"
                    >
                      Цена со скидкой
                    </Label>
                    <Input
                      id={`discount-price-${nmId}`}
                      inputMode="decimal"
                      value={discountPriceDraft}
                      onChange={(event) =>
                        setDiscountPriceDraft(event.target.value)
                      }
                      className={cn(
                        CONTROL_INPUT_CLASS,
                        "text-base font-semibold tabular-nums",
                      )}
                      placeholder="0"
                    />
                  </div>
                  <div className="space-y-1.5">
                    <Label
                      htmlFor={`promo-start-${nmId}`}
                      className="text-xs text-muted-foreground"
                    >
                      Старт
                    </Label>
                    <Input
                      id={`promo-start-${nmId}`}
                      type="datetime-local"
                      value={promoStart}
                      onChange={(event) => setPromoStart(event.target.value)}
                      className={cn(CONTROL_INPUT_CLASS, "text-xs")}
                    />
                  </div>
                  <div className="space-y-1.5">
                    <Label
                      htmlFor={`promo-end-${nmId}`}
                      className="text-xs text-muted-foreground"
                    >
                      Финал
                    </Label>
                    <Input
                      id={`promo-end-${nmId}`}
                      type="datetime-local"
                      value={promoEnd}
                      onChange={(event) => setPromoEnd(event.target.value)}
                      className={cn(CONTROL_INPUT_CLASS, "text-xs")}
                    />
                  </div>
                </div>
                <div className="flex flex-wrap gap-2">
                  {[
                    ["24 часа", 1],
                    ["7 дней", 7],
                    ["14 дней", 14],
                  ].map(([label, days]) => (
                    <Button
                      key={String(label)}
                      type="button"
                      size="sm"
                      variant="secondary"
                      className="h-8 rounded-xl border-0 bg-muted/70 px-3 text-[11px] shadow-sm ring-1 ring-border/45 hover:bg-muted"
                      onClick={() =>
                        setPromoEnd(
                          localDateTimePlusDays(promoStart, Number(days)),
                        )
                      }
                    >
                      {label}
                    </Button>
                  ))}
                </div>
              </ProductControlSection>

              <ProductControlSection
                icon={<Edit3 className="h-4 w-4" />}
                title="Контент карточки"
                summary={
                  descriptionDraft.trim()
                    ? `${descriptionDraft.trim().length} символов`
                    : "описание пустое"
                }
                tone={descriptionDraft.trim() ? "info" : "warning"}
                defaultOpen
              >
                <div className="space-y-3">
                  <div className="space-y-1.5">
                    <Label
                      htmlFor={`title-draft-${nmId}`}
                      className="text-xs text-muted-foreground"
                    >
                      Название
                    </Label>
                    <Input
                      id={`title-draft-${nmId}`}
                      value={titleDraft}
                      onChange={(event) => setTitleDraft(event.target.value)}
                      className={cn(CONTROL_INPUT_CLASS, "font-medium")}
                      placeholder="Название товара"
                    />
                  </div>
                  <details
                    className="group overflow-hidden rounded-2xl bg-muted/45 shadow-inner ring-1 ring-border/45"
                    open
                  >
                    <summary className="flex cursor-pointer list-none items-center justify-between gap-2 px-3 py-2.5 text-xs font-semibold">
                      Описание
                      <ChevronDown className="h-3.5 w-3.5 transition group-open:rotate-180" />
                    </summary>
                    <div className="border-t bg-background p-2">
                      <Textarea
                        rows={6}
                        value={descriptionDraft}
                        onChange={(event) =>
                          setDescriptionDraft(event.target.value)
                        }
                        placeholder="Материал, посадка, комплектация, уход, сезонность"
                        className="min-h-32 resize-y rounded-2xl border-0 bg-background/90 text-sm shadow-inner ring-1 ring-border/55 focus-visible:ring-2 focus-visible:ring-primary/35"
                      />
                    </div>
                  </details>
                </div>
              </ProductControlSection>
            </div>

            <ProductControlSection
              icon={<ClipboardCheck className="h-4 w-4" />}
              title="Характеристики"
              summary={`${characteristics.filter((item) => item.name && item.value).length}/${characteristics.length} заполнено`}
              tone={
                characteristics.some((item) => item.name && !item.value)
                  ? "warning"
                  : "muted"
              }
              defaultOpen
            >
              <div className="grid gap-2 md:grid-cols-2">
                {characteristics.map((item) => (
                  <div
                    key={item.id}
                    className="grid grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)_36px] items-center gap-2 rounded-2xl bg-background/80 p-2 shadow-sm ring-1 ring-border/50"
                  >
                    <Input
                      value={item.name}
                      onChange={(event) =>
                        updateCharacteristic(item.id, {
                          name: event.target.value,
                        })
                      }
                      placeholder="Характеристика"
                      className="h-9 rounded-xl border-0 bg-muted/50 px-3 text-xs shadow-inner ring-1 ring-border/45 focus-visible:ring-2 focus-visible:ring-primary/30"
                    />
                    <Input
                      value={item.value}
                      onChange={(event) =>
                        updateCharacteristic(item.id, {
                          value: event.target.value,
                        })
                      }
                      placeholder="Значение"
                      className="h-9 rounded-xl border-0 bg-muted/50 px-3 text-xs shadow-inner ring-1 ring-border/45 focus-visible:ring-2 focus-visible:ring-primary/30"
                    />
                    <Button
                      type="button"
                      size="icon"
                      variant="ghost"
                      className="h-9 w-9 rounded-xl hover:bg-destructive/10 hover:text-destructive"
                      onClick={() => removeCharacteristic(item.id)}
                      aria-label="Удалить характеристику"
                      title="Удалить характеристику"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </Button>
                  </div>
                ))}
              </div>
              <Button
                type="button"
                size="sm"
                variant="outline"
                className={cn(
                  "h-9 border-0 bg-background/80 text-xs ring-1 ring-border/55",
                  CONTROL_BUTTON_CLASS,
                )}
                onClick={addCharacteristic}
              >
                <Plus className="h-3.5 w-3.5" />
                Добавить характеристику
              </Button>
            </ProductControlSection>
          </div>

          <aside className="border-t border-border/50 bg-background/55 p-4 backdrop-blur xl:overflow-y-auto xl:border-l xl:border-t-0">
            <div className="space-y-4">
              <div className={cn(CONTROL_PANEL_CLASS, "p-4")}>
                <div className="flex items-center justify-between gap-2">
                  <div className="text-sm font-semibold">
                    Предпросмотр решения
                  </div>
                  <Badge variant="outline" className="text-[10px]">
                    {contentChanged || priceChanged
                      ? "Есть правки"
                      : "Без правок"}
                  </Badge>
                </div>
                <div className="mt-3 grid grid-cols-2 gap-2">
                  <ControlStat
                    label="Цена"
                    value={formatMoneyOrDash(effectivePrice)}
                    tone="info"
                  />
                  <ControlStat
                    label="Скидка"
                    value={
                      discountPercent === null
                        ? "Нет данных"
                        : `${discountPercent.toLocaleString("ru-RU", { maximumFractionDigits: 1 })}%`
                    }
                    tone={quarantineRisk ? "warning" : "good"}
                  />
                  <ControlStat
                    label="Запас к безопасной"
                    value={
                      safeGap === null ? "Нет данных" : formatMoney(safeGap)
                    }
                    tone={safeGap !== null && safeGap < 0 ? "warning" : "good"}
                  />
                  <ControlStat
                    label="Маржа"
                    value={formatPercentOrDash(cockpit.money.margin)}
                    tone={(cockpit.money.margin ?? 0) < 10 ? "warning" : "good"}
                  />
                </div>
              </div>

              <div className={cn(CONTROL_PANEL_CLASS, "p-4")}>
                <div className="text-sm font-semibold">Контроль перед WB</div>
                <div className="mt-3 space-y-2">
                  <ControlChecklistItem
                    ok={!quarantineRisk}
                    text="цена не падает в карантин 3x"
                  />
                  <ControlChecklistItem
                    ok={safeGap === null || safeGap >= 0}
                    text="скидочная цена выше безопасной"
                  />
                  <ControlChecklistItem
                    ok={Boolean(titleDraft.trim())}
                    text="название заполнено"
                  />
                  <ControlChecklistItem
                    ok={descriptionDraft.trim().length >= 80}
                    text="описание не выглядит пустым"
                  />
                </div>
              </div>

              <div className={cn(CONTROL_PANEL_CLASS, "p-4")}>
                <div className="flex items-center gap-2 text-sm font-semibold">
                  <Wand2 className="h-4 w-4 text-primary" />
                  Следующий шаг
                </div>
                <div className="mt-2 text-xs leading-5 text-muted-foreground">
                  {quarantineRisk
                    ? "Сначала поднимите скидочную цену: WB может оставить старую цену."
                    : safeGap !== null && safeGap < 0
                      ? "Цена ниже безопасной. Проверьте себестоимость и маржу."
                      : contentChanged || priceChanged
                        ? "Сохраните черновик и отправьте изменение после подтверждения."
                        : "По текущим данным срочная правка не требуется."}
                </div>
              </div>
            </div>
          </aside>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function ProductControlSection({
  icon,
  title,
  summary,
  tone = "default",
  defaultOpen = false,
  children,
}: {
  icon: ReactNode;
  title: string;
  summary: string;
  tone?: CockpitTone;
  defaultOpen?: boolean;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <details
      className={cn("group overflow-hidden", CONTROL_PANEL_CLASS)}
      open={open}
      onToggle={(event) => setOpen(event.currentTarget.open)}
    >
      <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-4 py-3">
        <span className="flex min-w-0 items-center gap-2">
          <span
            className={cn(
              "inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl shadow-sm",
              COCKPIT_ICON_TONE[tone],
            )}
          >
            {icon}
          </span>
          <span className="min-w-0">
            <span className="block truncate text-sm font-semibold">
              {title}
            </span>
            <span className="block truncate text-xs text-muted-foreground">
              {summary}
            </span>
          </span>
        </span>
        <ChevronDown className="h-4 w-4 shrink-0 text-muted-foreground transition group-open:rotate-180" />
      </summary>
      <div className="space-y-3 border-t border-border/50 px-4 py-3">
        {children}
      </div>
    </details>
  );
}

function ControlStat({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone: CockpitTone;
}) {
  return (
    <div
      className={cn(
        "rounded-2xl border-0 p-3 shadow-sm ring-1 ring-border/45",
        COCKPIT_SOFT_TONE[tone],
      )}
    >
      <div className="text-[10px] uppercase text-muted-foreground">{label}</div>
      <div
        className={cn(
          "mt-1 truncate text-base font-semibold tabular-nums",
          COCKPIT_TEXT_TONE[tone],
        )}
      >
        {value}
      </div>
    </div>
  );
}

function ControlChecklistItem({ ok, text }: { ok: boolean; text: string }) {
  return (
    <div className="flex items-center gap-2 text-xs">
      <span
        className={cn(
          "inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full",
          ok ? "bg-success/10 text-success" : "bg-warning/10 text-warning",
        )}
      >
        {ok ? (
          <CheckCircle2 className="h-3.5 w-3.5" />
        ) : (
          <AlertTriangle className="h-3.5 w-3.5" />
        )}
      </span>
      <span className={ok ? "text-foreground" : "text-warning"}>{text}</span>
    </div>
  );
}

function ProductCockpit({
  data,
  nmId,
  dateFrom,
  dateTo,
}: {
  data: any;
  nmId: string | number;
  dateFrom?: string;
  dateTo?: string;
}) {
  const cockpit = getProductCockpit(data, nmId);
  const wbHref = `https://www.wildberries.ru/catalog/${nmId}/detail.aspx`;
  const period = dateFrom && dateTo ? `${dateFrom} — ${dateTo}` : null;
  const numericNmId = Number(nmId);
  const searchNmId = Number.isFinite(numericNmId) ? numericNmId : String(nmId);
  const baseSearch = { nm_id: searchNmId };
  const adsProductSearch = { ...baseSearch, sort: "spend" };

  const profit = toFiniteNumber(cockpit.money.profit);
  const revenue = toFiniteNumber(cockpit.money.revenue);
  const drr = percentNumber(cockpit.ads.drr);
  const stockQuantity = toFiniteNumber(cockpit.stock.quantity);
  const stockDays = toFiniteNumber(cockpit.stock.daysOfStock);
  const qualityScore = toFiniteNumber(cockpit.quality.score);
  const adsHasAllocationProblem =
    (cockpit.ads.unallocated ?? 0) > 0 || (cockpit.ads.overallocated ?? 0) > 0;
  const priceRisk = cockpit.price.gap !== null && cockpit.price.gap < 0;
  const forecast = buildProductForecast(cockpit, dateFrom, dateTo);

  const moduleTiles = [
    {
      key: "money",
      icon: <BadgeDollarSign className="h-4 w-4" />,
      title: "Деньги",
      value: formatMoneyOrDash(cockpit.money.profit),
      detail: `Маржа ${formatPercentOrDash(cockpit.money.margin)}`,
      tone: profit === null ? "muted" : profit < 0 ? "danger" : "good",
      to: "/money",
      search: baseSearch,
      span:
        profit !== null && (profit < 0 || Math.abs(profit) >= 50_000)
          ? "large"
          : "wide",
      signals: [
        { label: "Выручка", value: formatMoneyOrDash(cockpit.money.revenue) },
        { label: "ROI", value: formatPercentOrDash(cockpit.money.roi) },
      ],
    },
    {
      key: "ads",
      icon: <Megaphone className="h-4 w-4" />,
      title: "Реклама",
      value: formatMoneyOrDash(cockpit.ads.spend),
      detail: `ДРР ${formatPercentOrDash(cockpit.ads.drr)}`,
      tone:
        adsHasAllocationProblem || (drr !== null && drr >= 25)
          ? "warning"
          : cockpit.ads.spend === null
            ? "muted"
            : "info",
      to: "/ads",
      href: `/ads?nm_id=${encodeURIComponent(String(nmId))}&sort=spend`,
      search: adsProductSearch,
      testId: "product-ads-link",
      span:
        adsHasAllocationProblem || (drr !== null && drr >= 18)
          ? "wide"
          : "normal",
      signals: [
        { label: "Клики", value: formatNumberOrDash(cockpit.ads.clicks) },
        { label: "Заказы", value: formatNumberOrDash(cockpit.ads.orders) },
      ],
    },
    {
      key: "stock",
      icon: <Boxes className="h-4 w-4" />,
      title: "Остатки",
      value: `${formatNumberOrDash(cockpit.stock.quantity)} шт`,
      detail:
        stockDays !== null
          ? `${formatNumberOrDash(stockDays, { maximumFractionDigits: 1 })} дн. запаса`
          : "Склад и движение товара",
      tone:
        stockQuantity === null
          ? "muted"
          : stockQuantity <= 0 || (stockDays !== null && stockDays < 14)
            ? "danger"
            : stockDays !== null && stockDays < 30
              ? "warning"
              : "good",
      to: "/stock-control",
      search: { ...baseSearch, tab: "overview" },
      span:
        stockQuantity !== null &&
        (stockQuantity <= 50 || (stockDays !== null && stockDays < 30))
          ? "wide"
          : "normal",
      signals: [
        {
          label: "В пути",
          value: `${formatNumberOrDash(cockpit.stock.inTransit)} шт`,
        },
        { label: "Строк", value: formatNumberOrDash(cockpit.stock.rows) },
      ],
    },
    {
      key: "price",
      icon: <Tag className="h-4 w-4" />,
      title: "Цена",
      value: formatMoneyOrDash(cockpit.price.current),
      detail:
        cockpit.price.breakEven === null
          ? "Безопасная цена не рассчитана"
          : priceRisk
            ? "Ниже безопасной цены"
            : "Цена в рабочей зоне",
      tone: priceRisk
        ? "warning"
        : cockpit.price.current === null
          ? "muted"
          : "good",
      to: "/pricing",
      search: baseSearch,
      span: priceRisk ? "wide" : "normal",
      signals: [
        { label: "До скидки", value: formatMoneyOrDash(cockpit.price.base) },
        {
          label: "Безопасная",
          value: formatMoneyOrDash(cockpit.price.breakEven),
        },
      ],
    },
    {
      key: "forecast",
      icon: <TrendingUp className="h-4 w-4" />,
      title: "Прогноз",
      value: formatMoneyOrDash(
        forecast.recommended?.price ?? forecast.targetPrice,
      ),
      detail: forecast.recommendation,
      tone:
        forecast.currentUnitProfit === null
          ? "muted"
          : forecast.currentUnitProfit < 0
            ? "danger"
            : forecast.recommended?.delta !== 0
              ? "good"
              : "info",
      href: "#product-forecast",
      span: "wide",
      signals: [
        {
          label: "Прибыль/шт",
          value: formatMoneyOrDash(forecast.currentUnitProfit),
        },
        {
          label: "Скорость",
          value:
            forecast.dailyVelocity !== null
              ? `${forecast.dailyVelocity.toLocaleString("ru-RU", { maximumFractionDigits: 1 })}/дн`
              : "Нет данных",
        },
      ],
    },
    {
      key: "logistics",
      icon: <Truck className="h-4 w-4" />,
      title: "Логистика WB",
      value: formatMoneyOrDash(cockpit.money.logisticsDirect),
      detail: cockpit.money.logisticsStatus
        ? expenseStatusLabel(cockpit.money.logisticsStatus)
        : "Расходы и удержания WB",
      tone: cockpit.money.logisticsDirect === null ? "muted" : "warning",
      to: "/expenses",
      search: { category: "wb_logistics" },
      span: "normal",
      signals: [
        {
          label: "WB расходы",
          value: formatMoneyOrDash(cockpit.money.wbExpensesTotal),
        },
      ],
    },
    {
      key: "quality",
      icon: <ShieldCheck className="h-4 w-4" />,
      title: "Checker",
      value:
        qualityScore !== null
          ? `${Math.round(qualityScore)}/100`
          : formatNumberOrDash(cockpit.quality.issueCount),
      detail:
        cockpit.quality.issueCount > 0
          ? `${cockpit.quality.issueCount} проблем по карточке`
          : "Фото, описание и характеристики",
      tone:
        cockpit.quality.criticalIssueCount > 0
          ? "danger"
          : cockpit.quality.issueCount > 0
            ? "warning"
            : "good",
      to: "/checker/$nmId",
      params: { nmId: String(nmId) },
      span: cockpit.quality.issueCount > 0 ? "wide" : "normal",
      signals: [
        { label: "Критично", value: cockpit.quality.criticalIssueCount },
        { label: "Предупр.", value: cockpit.quality.warningIssueCount },
      ],
    },
    {
      key: "data",
      icon: <AlertTriangle className="h-4 w-4" />,
      title: "Данные",
      value: cockpit.dataQuality.issueCount,
      detail:
        STATUS_LABEL_RU[String(cockpit.dataQuality.status).toLowerCase()] ??
        "Качество данных",
      tone:
        String(cockpit.dataQuality.status).toLowerCase() === "blocked"
          ? "danger"
          : cockpit.dataQuality.issueCount > 0
            ? "warning"
            : "good",
      to: "/data-fix",
      search: baseSearch,
      span: cockpit.dataQuality.issueCount > 0 ? "wide" : "normal",
      signals: [
        { label: "Блокеры", value: cockpit.dataQuality.blockers },
        { label: "Предупр.", value: cockpit.dataQuality.warnings },
      ],
    },
    {
      key: "reputation",
      icon: <Star className="h-4 w-4" />,
      title: "Репутация",
      value:
        cockpit.reputation.rating !== null
          ? cockpit.reputation.rating.toFixed(1)
          : formatNumberOrDash(cockpit.reputation.unanswered),
      detail:
        cockpit.reputation.unanswered > 0
          ? `${cockpit.reputation.unanswered} без ответа`
          : "Отзывы и вопросы",
      tone: cockpit.reputation.unanswered > 0 ? "warning" : "info",
      to: "/reputation",
      search: baseSearch,
      span: cockpit.reputation.unanswered > 0 ? "wide" : "normal",
      signals: [
        {
          label: "Отзывы",
          value: formatNumberOrDash(cockpit.reputation.reviewsCount),
        },
        {
          label: "Вопросы",
          value: formatNumberOrDash(cockpit.reputation.questionsCount),
        },
      ],
    },
    {
      key: "claims",
      icon: <ReceiptText className="h-4 w-4" />,
      title: "Претензии",
      value: formatNumberOrDash(cockpit.claims.open),
      detail:
        cockpit.claims.potential !== null
          ? `Потенциал ${formatMoneyOrDash(cockpit.claims.potential)}`
          : "Кейсы и кандидаты",
      tone:
        (cockpit.claims.open ?? 0) > 0 || (cockpit.claims.candidates ?? 0) > 0
          ? "warning"
          : "muted",
      to: "/claims",
      search: baseSearch,
      span:
        (cockpit.claims.open ?? 0) > 0 || (cockpit.claims.candidates ?? 0) > 0
          ? "wide"
          : "normal",
      signals: [
        {
          label: "Кандидаты",
          value: formatNumberOrDash(cockpit.claims.candidates),
        },
        { label: "Сумма", value: formatMoneyOrDash(cockpit.claims.potential) },
      ],
    },
    {
      key: "grouping",
      icon: <PackageSearch className="h-4 w-4" />,
      title: "Группировка",
      value: formatNumberOrDash(cockpit.grouping.count),
      detail: "Кандидаты и ручная проверка",
      tone: (cockpit.grouping.count ?? 0) > 0 ? "warning" : "muted",
      to: "/grouping",
      search: baseSearch,
      span: (cockpit.grouping.count ?? 0) > 0 ? "wide" : "normal",
      signals: [
        {
          label: "Статус",
          value: normalizeStatusLabel(cockpit.grouping.status),
        },
      ],
    },
    {
      key: "photo",
      icon: <Camera className="h-4 w-4" />,
      title: "Фото",
      value: formatNumberOrDash(cockpit.photo.versions),
      detail:
        cockpit.photo.issues > 0
          ? `${cockpit.photo.issues} сигналов`
          : "Фото-студия и версии",
      tone: cockpit.photo.issues > 0 ? "warning" : "muted",
      to: "/photo-studio",
      search: baseSearch,
      span: cockpit.photo.issues > 0 ? "wide" : "normal",
      signals: [
        { label: "WB", value: formatNumberOrDash(cockpit.photo.sources) },
        { label: "Статус", value: normalizeStatusLabel(cockpit.photo.status) },
      ],
    },
    {
      key: "actions",
      icon: <ListChecks className="h-4 w-4" />,
      title: "Action Center",
      value: cockpit.actions.open,
      detail:
        cockpit.business.openCount > 0
          ? `${cockpit.business.openCount} бизнес-сигналов`
          : "Открытые действия",
      tone: cockpit.actions.open > 0 ? "warning" : "good",
      to: "/action-center",
      search: { nm_id: String(nmId) },
      span: cockpit.actions.open > 0 ? "wide" : "normal",
      signals: [
        { label: "Всего", value: cockpit.actions.total },
        { label: "Проблемы", value: cockpit.problems.length },
      ],
    },
    {
      key: "ab",
      icon: <TrendingUp className="h-4 w-4" />,
      title: "A/B тесты",
      value: formatNumberOrDash(cockpit.experiments.active),
      detail: "Гипотезы по фото и карточке",
      tone: (cockpit.experiments.active ?? 0) > 0 ? "warning" : "muted",
      to: "/ab-tests",
      search: baseSearch,
      span: "normal",
      signals: [
        {
          label: "Статус",
          value: normalizeStatusLabel(cockpit.experiments.status),
        },
      ],
    },
  ];

  return (
    <div className="space-y-4">
      <section
        className={cn("overflow-hidden rounded-2xl", COCKPIT_PANEL_CLASS)}
      >
        <div className="grid items-start xl:grid-cols-[minmax(0,1fr)_300px]">
          <div className="p-4">
            <div className="grid items-start gap-4 lg:grid-cols-[164px_minmax(0,1fr)]">
              <div className="min-w-0">
                <div className="overflow-hidden rounded-2xl border border-border/45 bg-background/64 p-1.5">
                  <ProductImage
                    src={cockpit.identity.image}
                    nmId={nmId}
                    alt={cockpit.identity.title}
                    className="h-40 w-full max-w-none rounded-xl lg:h-44"
                  />
                </div>
                <div className="mt-2 flex flex-wrap gap-1.5">
                  <Badge
                    variant="outline"
                    className="h-6 rounded-full border-border/55 bg-background/80 px-2.5 font-mono"
                  >
                    nm_id {cockpit.identity.nmId}
                  </Badge>
                  {cockpit.identity.brand ? (
                    <Badge
                      variant="secondary"
                      className="h-6 rounded-full border-0 px-2.5"
                    >
                      {cockpit.identity.brand}
                    </Badge>
                  ) : null}
                  {cockpit.identity.subject ? (
                    <Badge
                      variant="secondary"
                      className="h-6 rounded-full border-0 px-2.5"
                    >
                      {cockpit.identity.subject}
                    </Badge>
                  ) : null}
                  {cockpit.identity.vendorCode ? (
                    <Badge
                      variant="outline"
                      className="h-6 max-w-full gap-1 rounded-full border-border/55 bg-background/80 px-2.5 font-mono"
                    >
                      <span className="truncate">
                        Артикул {cockpit.identity.vendorCode}
                      </span>
                    </Badge>
                  ) : null}
                </div>
              </div>

              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <StatusBadge value={cockpit.healthStatus} />
                  {period ? (
                    <Badge variant="outline" className="text-[10px]">
                      {period}
                    </Badge>
                  ) : null}
                  {cockpit.unavailable.length ? (
                    <Badge
                      variant="outline"
                      className="border-warning/35 bg-warning/5 text-[10px] text-warning"
                    >
                      Недоступно:{" "}
                      {cockpit.unavailable
                        .slice(0, 2)
                        .map(sourceLabel)
                        .join(", ")}
                    </Badge>
                  ) : null}
                  <div className="ml-auto flex items-center gap-2">
                    <ProductControlPanel
                      data={data}
                      cockpit={cockpit}
                      nmId={nmId}
                      dateFrom={dateFrom}
                      dateTo={dateTo}
                    />
                    <Button
                      asChild
                      size="sm"
                      variant="ghost"
                      className="h-7 px-2 text-xs"
                    >
                      <a href={wbHref} target="_blank" rel="noreferrer">
                        WB <ExternalLink className="ml-1 h-3.5 w-3.5" />
                      </a>
                    </Button>
                  </div>
                </div>

                <h1
                  data-testid="product-360-title"
                  className="mt-2.5 max-w-4xl text-2xl font-semibold leading-tight md:text-[28px]"
                >
                  {cockpit.identity.title}
                </h1>

                <div className="mt-3 max-w-4xl">
                  <ProductVectorPanel cockpit={cockpit} />
                </div>
              </div>
            </div>

            <div className="mt-4 overflow-hidden rounded-[22px] border border-border/45 bg-muted/20">
              <div className="grid gap-px bg-border/45 sm:grid-cols-2 xl:grid-cols-5">
                <ProductHeroMetric
                  icon={<CircleDollarSign className="h-4 w-4" />}
                  label="Прибыль"
                  value={formatMoneyOrDash(cockpit.money.profit)}
                  detail={`Маржа ${formatPercentOrDash(cockpit.money.margin)}, ROI ${formatPercentOrDash(cockpit.money.roi)}`}
                  tone={
                    profit === null ? "muted" : profit < 0 ? "danger" : "good"
                  }
                  to="/money"
                  search={baseSearch}
                />
                <ProductHeroMetric
                  icon={<BarChart3 className="h-4 w-4" />}
                  label="Выручка"
                  value={formatMoneyOrDash(cockpit.money.revenue)}
                  detail={`К перечислению ${formatMoneyOrDash(cockpit.money.forPay)}`}
                  tone={revenue === null ? "muted" : "info"}
                  to="/money"
                  search={baseSearch}
                />
                <ProductHeroMetric
                  icon={<Boxes className="h-4 w-4" />}
                  label="Остаток"
                  value={`${formatNumberOrDash(cockpit.stock.quantity)} шт`}
                  detail={`В пути ${formatNumberOrDash(cockpit.stock.inTransit)} шт`}
                  tone={
                    stockQuantity === null
                      ? "muted"
                      : stockQuantity <= 0
                        ? "danger"
                        : "good"
                  }
                  to="/stock-control"
                  search={{ ...baseSearch, tab: "overview" }}
                />
                <ProductHeroMetric
                  icon={<Megaphone className="h-4 w-4" />}
                  label="Реклама"
                  value={formatMoneyOrDash(cockpit.ads.spend)}
                  detail={`ДРР ${formatPercentOrDash(cockpit.ads.drr)}, заказы ${formatNumberOrDash(cockpit.ads.orders)}`}
                  tone={
                    adsHasAllocationProblem || (drr !== null && drr >= 25)
                      ? "warning"
                      : cockpit.ads.spend === null
                        ? "muted"
                        : "info"
                  }
                  href={`/ads?nm_id=${encodeURIComponent(String(nmId))}&sort=spend`}
                  to="/ads"
                  search={adsProductSearch}
                />
                <ProductHeroMetric
                  icon={<Tag className="h-4 w-4" />}
                  label="Цена"
                  value={formatMoneyOrDash(cockpit.price.current)}
                  detail={
                    cockpit.price.breakEven !== null
                      ? `Безопасная ${formatMoneyOrDash(cockpit.price.breakEven)}`
                      : "Безопасная цена не рассчитана"
                  }
                  tone={
                    priceRisk
                      ? "warning"
                      : cockpit.price.current === null
                        ? "muted"
                        : "good"
                  }
                  to="/pricing"
                  search={baseSearch}
                />
              </div>
            </div>

            <div className="mt-3">
              <ProductPulsePanel cockpit={cockpit} />
            </div>
          </div>

          <div className="border-t bg-muted/20 p-4 backdrop-blur xl:border-l xl:border-t-0">
            <MainSignalPanel cockpit={cockpit} nmId={nmId} />
          </div>
        </div>
      </section>

      <ProductForecastPanelSimple
        cockpit={cockpit}
        dateFrom={dateFrom}
        dateTo={dateTo}
        forecast={forecast}
      />

      <section className="space-y-3">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h2 className="text-base font-semibold">Рабочие блоки</h2>
            <p className="text-xs text-muted-foreground">
              Финансы, реклама, склад, данные и качество по текущему nmID.
            </p>
          </div>
          <Badge variant="outline" className="text-[10px]">
            {cockpit.problems.length} сигналов
          </Badge>
        </div>
        <ModuleBoard items={moduleTiles} />
      </section>

      <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,1fr)_420px]">
        <MoneyBreakdownPanel cockpit={cockpit} />
        <ProblemsPanel cockpit={cockpit} nmId={nmId} />
      </div>
    </div>
  );
}

function ProductCockpitLegacy({
  data,
  nmId,
  dateFrom,
  dateTo,
}: {
  data: any;
  nmId: string | number;
  dateFrom?: string;
  dateTo?: string;
}) {
  const cockpit = getProductCockpit(data, nmId);
  const wbHref = `https://www.wildberries.ru/catalog/${nmId}/detail.aspx`;
  const period = dateFrom && dateTo ? `${dateFrom} — ${dateTo}` : null;
  const numericNmId = Number(nmId);
  const searchNmId = Number.isFinite(numericNmId) ? numericNmId : String(nmId);
  const baseSearch = { nm_id: searchNmId };
  const adsProductSearch = { ...baseSearch, sort: "spend" };

  return (
    <div className="space-y-4">
      <div className="grid items-start gap-4 xl:grid-cols-[minmax(0,1fr)_280px]">
        <section className="rounded-lg border bg-background p-3 shadow-sm">
          <div className="flex items-start gap-3">
            <ProductImage
              src={cockpit.identity.image}
              nmId={nmId}
              alt={cockpit.identity.title}
              className="h-20 w-20 max-w-none shrink-0 rounded-md"
            />
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <StatusBadge value={cockpit.healthStatus} />
                {period ? (
                  <Badge variant="outline" className="text-[10px]">
                    {period}
                  </Badge>
                ) : null}
                {cockpit.unavailable.length ? (
                  <Badge
                    variant="outline"
                    className="border-warning/35 bg-warning/5 text-[10px] text-warning"
                  >
                    Недоступно:{" "}
                    {cockpit.unavailable
                      .slice(0, 2)
                      .map(sourceLabel)
                      .join(", ")}
                  </Badge>
                ) : null}
                <Button
                  asChild
                  size="sm"
                  variant="ghost"
                  className="ml-auto h-7 px-2 text-xs"
                >
                  <a href={wbHref} target="_blank" rel="noreferrer">
                    WB <ExternalLink className="ml-1 h-3.5 w-3.5" />
                  </a>
                </Button>
              </div>

              <h1
                data-testid="product-360-title"
                className="mt-2 max-w-4xl text-xl font-semibold leading-tight md:text-2xl"
              >
                {cockpit.identity.title}
              </h1>

              <div className="mt-2 flex flex-wrap items-center gap-2 text-xs">
                <Badge variant="outline" className="h-6 gap-1 font-mono">
                  nm_id {cockpit.identity.nmId}
                </Badge>
                {cockpit.identity.vendorCode ? (
                  <Badge variant="outline" className="h-6 gap-1 font-mono">
                    Артикул {cockpit.identity.vendorCode}
                  </Badge>
                ) : null}
                {cockpit.identity.brand ? (
                  <Badge variant="secondary" className="h-6">
                    {cockpit.identity.brand}
                  </Badge>
                ) : null}
                {cockpit.identity.subject ? (
                  <Badge variant="secondary" className="h-6">
                    {cockpit.identity.subject}
                  </Badge>
                ) : null}
              </div>
            </div>
          </div>

          <div className="mt-3 grid grid-cols-2 gap-2 md:grid-cols-3 2xl:grid-cols-6">
            <CockpitMetric
              icon={<CircleDollarSign className="h-4 w-4" />}
              label="Прибыль"
              value={formatMoneyOrDash(cockpit.money.profit)}
              detail={`Маржа: ${formatPercentOrDash(cockpit.money.margin)}`}
              tone={
                cockpit.money.profit === null
                  ? "muted"
                  : cockpit.money.profit < 0
                    ? "danger"
                    : "good"
              }
            />
            <CockpitMetric
              icon={<BarChart3 className="h-4 w-4" />}
              label="Выручка"
              value={formatMoneyOrDash(cockpit.money.revenue)}
              detail={`К перечислению: ${formatMoneyOrDash(cockpit.money.forPay)}`}
              tone="info"
            />
            <CockpitMetric
              icon={<Tag className="h-4 w-4" />}
              label="Текущая цена"
              value={formatMoneyOrDash(cockpit.price.current)}
              detail={
                cockpit.price.base !== null &&
                cockpit.price.current !== null &&
                Math.abs(cockpit.price.base - cockpit.price.current) > 0.5
                  ? `До скидки: ${formatMoneyOrDash(cockpit.price.base)}`
                  : cockpit.price.gap !== null
                    ? `До безопасной цены: ${formatMoneyOrDash(cockpit.price.gap)}`
                    : "Безопасная цена не рассчитана"
              }
              tone={
                cockpit.price.current === null
                  ? "muted"
                  : cockpit.price.gap !== null && cockpit.price.gap < 0
                    ? "warning"
                    : "good"
              }
            />
            <CockpitMetric
              icon={<Megaphone className="h-4 w-4" />}
              label="Реклама"
              value={formatMoneyOrDash(cockpit.ads.spend)}
              detail={`ДРР: ${formatPercentOrDash(cockpit.ads.drr)}`}
              tone={
                (cockpit.ads.unallocated ?? 0) > 0 ||
                (cockpit.ads.overallocated ?? 0) > 0
                  ? "warning"
                  : cockpit.ads.spend === null
                    ? "muted"
                    : "info"
              }
            />
            <CockpitMetric
              icon={<Truck className="h-4 w-4" />}
              label="Логистика WB"
              value={formatMoneyOrDash(cockpit.money.logisticsDirect)}
              detail={`Расходы WB: ${formatMoneyOrDash(cockpit.money.wbExpensesTotal)}`}
              tone={
                cockpit.money.logisticsDirect === null ? "muted" : "warning"
              }
            />
            <CockpitMetric
              icon={<Boxes className="h-4 w-4" />}
              label="Остаток"
              value={`${formatNumberOrDash(cockpit.stock.quantity)} шт`}
              detail={`В пути: ${formatNumberOrDash(cockpit.stock.inTransit)} шт`}
              tone={
                cockpit.stock.quantity === null
                  ? "muted"
                  : cockpit.stock.quantity <= 0
                    ? "danger"
                    : "good"
              }
            />
          </div>
        </section>

        <aside className="rounded-lg border bg-background p-3 shadow-sm xl:row-span-2">
          <div className="flex items-center gap-2">
            <Sparkles className="h-4 w-4 text-primary" />
            <div className="text-sm font-semibold">Главный сигнал</div>
          </div>
          <div className="mt-2 rounded-md border bg-background p-3">
            {cockpit.problems[0] ? (
              <>
                <div className="flex flex-wrap items-center gap-1.5">
                  <Badge variant="outline" className="text-[10px]">
                    {cockpit.problems[0].source}
                  </Badge>
                  <StatusBadge value={cockpit.healthStatus} />
                </div>
                <div className="mt-2 text-sm font-semibold leading-snug">
                  {cockpit.problems[0].title}
                </div>
                {cockpit.problems[0].detail ? (
                  <div className="mt-1 line-clamp-2 text-xs leading-relaxed text-muted-foreground">
                    {cockpit.problems[0].detail}
                  </div>
                ) : null}
                <Button asChild size="sm" className="mt-3 h-8 w-full text-xs">
                  <Link
                    to={cockpit.problems[0].link?.to as any}
                    search={cockpit.problems[0].link?.search as any}
                    params={cockpit.problems[0].link?.params as any}
                  >
                    Открыть блок <ArrowRight className="ml-1 h-3.5 w-3.5" />
                  </Link>
                </Button>
              </>
            ) : (
              <>
                <div className="text-sm font-semibold text-success">
                  Открытых блокеров нет
                </div>
                <div className="mt-1 text-xs leading-relaxed text-muted-foreground">
                  Основные показатели по карточке сейчас без критичных сигналов.
                </div>
              </>
            )}
          </div>
          <div className="mt-2 grid grid-cols-3 gap-2 text-xs">
            <div className="rounded-md border bg-background p-2">
              <div className="text-[10px] uppercase text-muted-foreground">
                Действия
              </div>
              <div className="mt-1 font-semibold tabular-nums">
                {cockpit.actions.open}
              </div>
            </div>
            <div className="rounded-md border bg-background p-2">
              <div className="text-[10px] uppercase text-muted-foreground">
                Карточка
              </div>
              <div className="mt-1 font-semibold tabular-nums">
                {cockpit.quality.score !== null
                  ? `${Math.round(cockpit.quality.score)}/100`
                  : (STATUS_LABEL_RU[
                      String(cockpit.quality.status).toLowerCase()
                    ] ?? "Нет")}
              </div>
            </div>
            <div className="rounded-md border bg-background p-2">
              <div className="text-[10px] uppercase text-muted-foreground">
                Данные
              </div>
              <div className="mt-1 font-semibold tabular-nums">
                {cockpit.dataQuality.issueCount}
              </div>
            </div>
          </div>
          <div className="mt-2 grid grid-cols-2 gap-2">
            <Button asChild size="sm" variant="outline" className="h-8 text-xs">
              <Link to="/action-center" search={{ nm_id: String(nmId) } as any}>
                <ListChecks className="mr-1 h-3.5 w-3.5" />
                Задачи
              </Link>
            </Button>
            <Button asChild size="sm" variant="outline" className="h-8 text-xs">
              <Link to="/results" search={{ nm_id: String(nmId) } as any}>
                <ReceiptText className="mr-1 h-3.5 w-3.5" />
                История
              </Link>
            </Button>
          </div>
        </aside>

        <section className="space-y-3 xl:col-start-1">
          <div className="flex items-end justify-between gap-3">
            <div>
              <h2 className="text-base font-semibold">Блоки управления</h2>
              <p className="text-xs text-muted-foreground">
                Ключевые разделы по этой карточке.
              </p>
            </div>
          </div>
          <div className="grid gap-2 lg:grid-cols-2">
            <SectionJumpCard
              icon={<BadgeDollarSign className="h-4 w-4" />}
              title="Деньги"
              value={formatMoneyTiny(cockpit.money.profit)}
              detail={`Выручка ${formatMoneyTiny(cockpit.money.revenue)}`}
              tone={
                cockpit.money.profit !== null && cockpit.money.profit < 0
                  ? "danger"
                  : "good"
              }
              to="/money"
              search={baseSearch}
              signals={[
                {
                  label: "Маржа",
                  value: formatPercentOrDash(cockpit.money.margin),
                },
                { label: "ROI", value: formatPercentOrDash(cockpit.money.roi) },
                {
                  label: "К выплате",
                  value: formatMoneyTiny(cockpit.money.forPay),
                },
              ]}
            />
            <SectionJumpCard
              icon={<Megaphone className="h-4 w-4" />}
              title="Реклама по товару"
              value={formatMoneyTiny(cockpit.ads.spend)}
              detail={
                cockpit.ads.allocationStatus
                  ? `${normalizeStatusLabel(cockpit.ads.allocationStatus)} · открыть кампании`
                  : "Открыть кампании по этому nm_id"
              }
              tone={
                (cockpit.ads.unallocated ?? 0) > 0 ||
                (cockpit.ads.overallocated ?? 0) > 0
                  ? "warning"
                  : "info"
              }
              to="/ads"
              href={`/ads?nm_id=${encodeURIComponent(String(nmId))}&sort=spend`}
              search={adsProductSearch}
              testId="product-ads-link"
              signals={[
                { label: "ДРР", value: formatPercentOrDash(cockpit.ads.drr) },
                {
                  label: "Клики",
                  value: formatNumberOrDash(cockpit.ads.clicks),
                },
                {
                  label: "Заказы",
                  value: formatNumberOrDash(cockpit.ads.orders),
                },
              ]}
            />
            <SectionJumpCard
              icon={<Truck className="h-4 w-4" />}
              title="Логистика"
              value={formatMoneyTiny(cockpit.money.logisticsDirect)}
              detail={
                cockpit.money.logisticsStatus
                  ? expenseStatusLabel(cockpit.money.logisticsStatus)
                  : "WB логистика и прочие удержания"
              }
              tone={
                cockpit.money.logisticsDirect === null ? "muted" : "warning"
              }
              to="/expenses"
              search={{ category: "wb_logistics" }}
              signals={[
                {
                  label: "Расходы WB",
                  value: formatMoneyTiny(cockpit.money.wbExpensesTotal),
                },
                {
                  label: "Доля от выручки",
                  value: formatPercentOrDash(
                    safeRatioPercent(
                      cockpit.money.logisticsDirect,
                      cockpit.money.revenue,
                    ),
                  ),
                },
                {
                  label: "Статус",
                  value: cockpit.money.logisticsStatus
                    ? expenseStatusLabel(cockpit.money.logisticsStatus)
                    : "Нет данных",
                },
              ]}
            />
            <SectionJumpCard
              icon={<Tag className="h-4 w-4" />}
              title="Цена"
              value={formatMoneyTiny(cockpit.price.current)}
              detail={
                cockpit.price.breakEven === null
                  ? "Безопасная цена не рассчитана"
                  : (STATUS_LABEL_RU[
                      String(cockpit.price.status).toLowerCase()
                    ] ?? normalizeStatusLabel(cockpit.price.status))
              }
              tone={
                cockpit.price.gap !== null && cockpit.price.gap < 0
                  ? "warning"
                  : cockpit.price.current === null
                    ? "muted"
                    : "good"
              }
              to="/pricing"
              search={baseSearch}
              signals={[
                {
                  label: "До скидки",
                  value: formatMoneyTiny(cockpit.price.base),
                },
                {
                  label: "Безопасная",
                  value: formatMoneyTiny(cockpit.price.breakEven),
                },
                { label: "Запас", value: formatMoneyTiny(cockpit.price.gap) },
              ]}
            />
            <SectionJumpCard
              icon={<Boxes className="h-4 w-4" />}
              title="Остатки"
              value={`${formatNumberOrDash(cockpit.stock.quantity)} шт`}
              detail={
                cockpit.stock.daysOfStock !== null
                  ? `${formatNumberOrDash(cockpit.stock.daysOfStock)} дн. запаса`
                  : "Склад и движение товара"
              }
              tone={
                cockpit.stock.quantity !== null && cockpit.stock.quantity <= 0
                  ? "danger"
                  : cockpit.stock.quantity === null
                    ? "muted"
                    : "good"
              }
              to="/stock-control"
              search={{ ...baseSearch, tab: "overview" }}
              signals={[
                {
                  label: "Полный остаток",
                  value: `${formatNumberOrDash(cockpit.stock.quantityFull)} шт`,
                },
                {
                  label: "В пути",
                  value: `${formatNumberOrDash(cockpit.stock.inTransit)} шт`,
                },
                {
                  label: "Строк",
                  value: formatNumberOrDash(cockpit.stock.rows),
                },
              ]}
            />
            <SectionJumpCard
              icon={<ShieldCheck className="h-4 w-4" />}
              title="Качество карточки"
              value={
                cockpit.quality.score !== null
                  ? `${Math.round(cockpit.quality.score)}/100`
                  : formatNumberOrDash(cockpit.quality.issueCount)
              }
              detail={
                cockpit.quality.issueCount > 0
                  ? `${cockpit.quality.issueCount} проблем`
                  : "Фото, описание и характеристики"
              }
              tone={cockpit.quality.issueCount > 0 ? "warning" : "good"}
              to="/checker/$nmId"
              params={{ nmId: String(nmId) }}
              signals={[
                {
                  label: "Критично",
                  value: cockpit.quality.criticalIssueCount,
                },
                { label: "Предупр.", value: cockpit.quality.warningIssueCount },
              ]}
            />
            <SectionJumpCard
              icon={<AlertTriangle className="h-4 w-4" />}
              title="Данные"
              value={cockpit.dataQuality.issueCount}
              detail={
                STATUS_LABEL_RU[
                  String(cockpit.dataQuality.status).toLowerCase()
                ] ?? "Качество данных"
              }
              tone={
                String(cockpit.dataQuality.status).toLowerCase() === "blocked"
                  ? "danger"
                  : cockpit.dataQuality.issueCount > 0
                    ? "warning"
                    : "good"
              }
              to="/data-fix"
              search={baseSearch}
              signals={[
                { label: "Блокеры", value: cockpit.dataQuality.blockers },
                { label: "Предупр.", value: cockpit.dataQuality.warnings },
              ]}
            />
            <SectionJumpCard
              icon={<ListChecks className="h-4 w-4" />}
              title="Action Center"
              value={cockpit.actions.open}
              detail={
                cockpit.business.openCount > 0
                  ? `${cockpit.business.openCount} бизнес-сигналов`
                  : "Открытые действия"
              }
              tone={cockpit.actions.open > 0 ? "warning" : "good"}
              to="/action-center"
              search={{ nm_id: String(nmId) }}
              signals={[
                { label: "Всего", value: cockpit.actions.total },
                { label: "Проблемы", value: cockpit.problems.length },
              ]}
            />
            <SectionJumpCard
              icon={<Star className="h-4 w-4" />}
              title="Репутация"
              value={
                cockpit.reputation.rating !== null
                  ? cockpit.reputation.rating.toFixed(1)
                  : formatNumberOrDash(cockpit.reputation.unanswered)
              }
              detail={
                cockpit.reputation.unanswered
                  ? `${cockpit.reputation.unanswered} без ответа`
                  : "Отзывы и вопросы"
              }
              tone={
                (cockpit.reputation.unanswered ?? 0) > 0 ? "warning" : "info"
              }
              to="/reputation"
              search={baseSearch}
              signals={[
                {
                  label: "Отзывы",
                  value: formatNumberOrDash(cockpit.reputation.reviewsCount),
                },
                {
                  label: "Вопросы",
                  value: formatNumberOrDash(cockpit.reputation.questionsCount),
                },
              ]}
            />
            <SectionJumpCard
              icon={<ReceiptText className="h-4 w-4" />}
              title="Претензии"
              value={formatNumberOrDash(cockpit.claims.open)}
              detail={
                cockpit.claims.potential !== null
                  ? `Компенсация ${formatMoneyTiny(cockpit.claims.potential)}`
                  : "Кейсы и кандидаты"
              }
              tone={
                (cockpit.claims.open ?? 0) > 0 ||
                (cockpit.claims.candidates ?? 0) > 0
                  ? "warning"
                  : "muted"
              }
              to="/claims"
              search={baseSearch}
              signals={[
                {
                  label: "Кандидаты",
                  value: formatNumberOrDash(cockpit.claims.candidates),
                },
                {
                  label: "Потенциал",
                  value: formatMoneyTiny(cockpit.claims.potential),
                },
              ]}
            />
            <SectionJumpCard
              icon={<Camera className="h-4 w-4" />}
              title="Фото"
              value={formatNumberOrDash(cockpit.photo.versions)}
              detail={
                cockpit.photo.issues
                  ? `${cockpit.photo.issues} сигналов по фото`
                  : "Фото-студия и версии"
              }
              tone={cockpit.photo.issues > 0 ? "warning" : "muted"}
              to="/photo-studio"
              search={baseSearch}
              signals={[
                {
                  label: "WB исходники",
                  value: formatNumberOrDash(cockpit.photo.sources),
                },
                {
                  label: "Статус",
                  value: normalizeStatusLabel(cockpit.photo.status),
                },
              ]}
            />
            <SectionJumpCard
              icon={<PackageSearch className="h-4 w-4" />}
              title="Группировка"
              value={formatNumberOrDash(cockpit.grouping.count)}
              detail="Кандидаты на объединение и ручная проверка"
              tone={(cockpit.grouping.count ?? 0) > 0 ? "warning" : "muted"}
              to="/grouping"
              search={baseSearch}
              signals={[
                {
                  label: "Статус",
                  value: normalizeStatusLabel(cockpit.grouping.status),
                },
              ]}
            />
            <SectionJumpCard
              icon={<TrendingUp className="h-4 w-4" />}
              title="A/B тесты"
              value={formatNumberOrDash(cockpit.experiments.active)}
              detail="Тесты фото, карточки и гипотез"
              tone={(cockpit.experiments.active ?? 0) > 0 ? "warning" : "muted"}
              to="/ab-tests"
              search={baseSearch}
              signals={[
                {
                  label: "Статус",
                  value: normalizeStatusLabel(cockpit.experiments.status),
                },
              ]}
            />
          </div>
        </section>
      </div>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_420px]">
        <MoneyBreakdownPanel cockpit={cockpit} />
        <ProblemsPanel cockpit={cockpit} nmId={nmId} />
      </div>
    </div>
  );
}

function ProductCockpitSkeleton() {
  return (
    <div className="space-y-4">
      <section
        className={cn("overflow-hidden rounded-2xl", COCKPIT_PANEL_CLASS)}
      >
        <div className="grid items-start xl:grid-cols-[minmax(0,1fr)_300px]">
          <div className="p-3">
            <div className="grid items-start gap-3 lg:grid-cols-[150px_minmax(0,1fr)]">
              <div className="min-w-0">
                <Skeleton className="h-40 w-full rounded-xl" />
                <div className="mt-2 flex flex-wrap gap-1.5">
                  <Skeleton className="h-6 w-32 rounded-full" />
                  <Skeleton className="h-6 w-20 rounded-full" />
                  <Skeleton className="h-6 w-24 rounded-full" />
                </div>
              </div>

              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <Skeleton className="h-6 w-24 rounded-full" />
                  <Skeleton className="h-6 w-36 rounded-full" />
                  <Skeleton className="h-6 w-44 rounded-full" />
                </div>
                <Skeleton className="mt-2.5 h-8 w-full max-w-[780px] rounded-xl" />

                <div
                  className={cn("mt-3 rounded-2xl p-3", COCKPIT_SURFACE_CLASS)}
                >
                  <div className="flex items-start gap-3">
                    <Skeleton className="h-8 w-8 shrink-0 rounded-lg" />
                    <div className="min-w-0 flex-1">
                      <Skeleton className="h-3 w-28 rounded-full" />
                      <Skeleton className="mt-2 h-5 w-64 max-w-full rounded-lg" />
                      <Skeleton className="mt-2 h-3 w-full max-w-[520px] rounded-full" />
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <div className="mt-3 rounded-2xl bg-muted/35 p-1.5 shadow-inner ring-1 ring-border/35">
              <div className="grid gap-1.5 sm:grid-cols-2 xl:grid-cols-5">
                {[0, 1, 2, 3, 4].map((index) => (
                  <div
                    key={index}
                    className={cn(
                      "min-h-[84px] rounded-xl bg-background/78 p-3 shadow-sm ring-1 ring-border/40",
                    )}
                  >
                    <div className="flex items-center gap-2">
                      <Skeleton className="h-7 w-7 rounded-lg" />
                      <Skeleton className="h-3 w-20 rounded-full" />
                    </div>
                    <Skeleton className="mt-4 h-6 w-28 rounded-lg" />
                    <Skeleton className="mt-2 h-3 w-36 rounded-full" />
                  </div>
                ))}
              </div>
            </div>

            <div className={cn("mt-3 rounded-2xl p-3", COCKPIT_SURFACE_CLASS)}>
              <div className="flex items-center gap-2">
                <Skeleton className="h-7 w-7 rounded-lg" />
                <div>
                  <Skeleton className="h-4 w-28 rounded-lg" />
                  <Skeleton className="mt-2 h-3 w-44 rounded-full" />
                </div>
              </div>
              <div className="mt-3 grid gap-3 sm:grid-cols-5">
                {Array.from({ length: 5 }).map((_, index) => (
                  <div key={index}>
                    <div className="flex justify-between gap-2">
                      <Skeleton className="h-3 w-16 rounded-full" />
                      <Skeleton className="h-3 w-10 rounded-full" />
                    </div>
                    <Skeleton className="mt-2 h-2 rounded-full" />
                  </div>
                ))}
              </div>
            </div>
          </div>

          <div className="border-t bg-muted/15 p-3 xl:border-l xl:border-t-0">
            <div className="flex items-center gap-2">
              <Skeleton className="h-4 w-4 rounded-md" />
              <Skeleton className="h-4 w-36 rounded-md" />
            </div>
            <div className="mt-3 rounded-md border bg-muted/25 p-3">
              <Skeleton className="h-6 w-20 rounded-md" />
              <Skeleton className="mt-3 h-5 w-full rounded-md" />
              <Skeleton className="mt-2 h-4 w-5/6 rounded-md" />
              <Skeleton className="mt-4 h-8 w-full rounded-md" />
            </div>
            <div className="mt-3 grid grid-cols-3 gap-2">
              {Array.from({ length: 3 }).map((_, index) => (
                <Skeleton key={index} className="h-12 rounded-md" />
              ))}
            </div>
          </div>
        </div>
      </section>

      <section className="space-y-3">
        <div className="flex items-end justify-between gap-3">
          <div>
            <Skeleton className="h-5 w-36 rounded-lg" />
            <Skeleton className="mt-2 h-3 w-64 rounded-full" />
          </div>
          <Skeleton className="h-6 w-20 rounded-full" />
        </div>
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          {Array.from({ length: 9 }).map((_, index) => (
            <div
              key={index}
              className={cn(
                "min-h-[96px] rounded-2xl bg-background/78 p-3.5 shadow-sm ring-1 ring-border/40",
                index % 4 === 0 ? "xl:col-span-2" : "",
              )}
            >
              <div className="flex items-start gap-3">
                <Skeleton className="h-9 w-9 rounded-xl" />
                <div className="min-w-0 flex-1">
                  <Skeleton className="h-4 w-32 rounded-lg" />
                  <div className="mt-2 flex gap-1.5">
                    <Skeleton className="h-5 w-20 rounded-full" />
                    <Skeleton className="h-5 w-16 rounded-full" />
                  </div>
                </div>
                <Skeleton className="h-6 w-20 rounded-lg" />
              </div>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}

function ProductCockpitSkeletonLegacy() {
  return (
    <div className="space-y-3">
      <div className="grid items-start gap-4 xl:grid-cols-[minmax(0,1fr)_280px]">
        <section className="rounded-lg border bg-background p-3 shadow-sm">
          <div className="flex items-start gap-3">
            <Skeleton className="h-20 w-20 shrink-0 rounded-md" />
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <Skeleton className="h-6 w-28 rounded-md" />
                <Skeleton className="h-6 w-36 rounded-md" />
                <Skeleton className="h-6 w-40 rounded-md" />
              </div>
              <Skeleton className="mt-3 h-7 w-full max-w-[680px] rounded-md" />
              <div className="mt-3 flex flex-wrap gap-2">
                <Skeleton className="h-6 w-32 rounded-md" />
                <Skeleton className="h-6 w-24 rounded-md" />
                <Skeleton className="h-6 w-28 rounded-md" />
              </div>
            </div>
          </div>

          <div className="mt-3 grid grid-cols-2 gap-2 md:grid-cols-3 2xl:grid-cols-6">
            {Array.from({ length: 6 }).map((_, index) => (
              <div
                key={index}
                className="rounded-md border bg-background p-2.5 shadow-sm"
              >
                <div className="flex items-center gap-2">
                  <Skeleton className="h-7 w-7 rounded-md" />
                  <Skeleton className="h-3 w-20 rounded-md" />
                </div>
                <Skeleton className="mt-3 h-5 w-24 rounded-md" />
                <Skeleton className="mt-2 h-3 w-28 rounded-md" />
              </div>
            ))}
          </div>
        </section>

        <aside className="rounded-lg border bg-background p-3 shadow-sm xl:row-span-2">
          <div className="flex items-center gap-2">
            <Skeleton className="h-4 w-4 rounded-md" />
            <Skeleton className="h-4 w-28 rounded-md" />
          </div>
          <div className="mt-3 rounded-md border bg-background p-3">
            <div className="flex gap-2">
              <Skeleton className="h-6 w-20 rounded-md" />
              <Skeleton className="h-6 w-28 rounded-md" />
            </div>
            <Skeleton className="mt-3 h-4 w-full rounded-md" />
            <Skeleton className="mt-2 h-4 w-5/6 rounded-md" />
            <Skeleton className="mt-4 h-8 w-full rounded-md" />
          </div>
          <div className="mt-2 grid grid-cols-3 gap-2">
            {Array.from({ length: 3 }).map((_, index) => (
              <Skeleton key={index} className="h-12 rounded-md" />
            ))}
          </div>
        </aside>

        <section className="space-y-3 xl:col-start-1">
          <div>
            <Skeleton className="h-5 w-40 rounded-md" />
            <Skeleton className="mt-2 h-3 w-64 rounded-md" />
          </div>
          <div className="grid gap-2 lg:grid-cols-2">
            {Array.from({ length: 8 }).map((_, index) => (
              <div
                key={index}
                className="rounded-md border bg-background p-3 shadow-sm"
              >
                <div className="flex items-start gap-3">
                  <Skeleton className="h-8 w-8 shrink-0 rounded-md" />
                  <div className="min-w-0 flex-1">
                    <Skeleton className="h-4 w-32 rounded-md" />
                    <Skeleton className="mt-2 h-5 w-44 rounded-md" />
                  </div>
                  <Skeleton className="h-4 w-4 rounded-md" />
                </div>
                <div className="mt-3 grid grid-cols-3 gap-4 border-t pt-2">
                  <Skeleton className="h-8 rounded-md" />
                  <Skeleton className="h-8 rounded-md" />
                  <Skeleton className="h-8 rounded-md" />
                </div>
              </div>
            ))}
          </div>
        </section>
      </div>
    </div>
  );
}

// ─── page ─────────────────────────────────────────────────────────────
function Product360Page() {
  const { nmId } = Route.useParams();
  const routeSearch = Route.useSearch();
  const { activeId } = useAccounts();
  const { from: dateFrom, to: dateTo } = useDateRange();
  const qc = useQueryClient();
  const browserSearch =
    typeof window === "undefined"
      ? null
      : new URLSearchParams(window.location.search);
  const contextProblemInstanceId =
    routeSearch.problem_instance_id ??
    browserSearch?.get("problem_instance_id") ??
    undefined;
  const contextTab =
    routeSearch.tab ??
    (browserSearch?.get("tab") === "price" ||
    browserSearch?.get("tab") === "promo"
      ? (browserSearch.get("tab") as "price" | "promo")
      : undefined);

  const { data, isLoading, error, refetch, isFetching } = useQuery({
    queryKey: ["portal-product-detail", activeId, nmId, dateFrom, dateTo],
    queryFn: () => fetchProduct360(nmId, activeId, { dateFrom, dateTo }),
    enabled: !!activeId,
    staleTime: 60_000,
  });

  const identity = sectionData<Record<string, unknown>>(data?.identity) ?? {};
  const image = pick<string>(identity, [
    "image",
    "image_url",
    "photo_url",
    "photo",
    "thumbnail",
  ]);
  const name = pick<string>(identity, ["title", "name"]) ?? `Артикул ${nmId}`;
  const vendorCode = pick<string>(identity, ["vendor_code", "article"]);
  const brand = pick<string>(identity, ["brand"]);
  const subject = pick<string>(identity, ["subject_name", "category"]);
  const contextualReviewMutation = useMutation({
    mutationFn: () =>
      appendActionCenterProblemHistory({
        accountId: activeId,
        problemInstanceId: contextProblemInstanceId,
        comment:
          contextTab === "promo"
            ? "Промо и цена проверены в карточке товара."
            : "Цена и маржа проверены в карточке товара.",
      }),
    onSuccess: () => {
      toast.success("История задачи обновлена");
      qc.invalidateQueries({ queryKey: ["portal-actions"] });
    },
    onError: (error: any) =>
      toast.error(error?.message ?? "Не удалось обновить историю задачи"),
  });

  return (
    <PageShell>
      <div data-testid="product-360-page" className="-mt-2 space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <Button
            asChild
            variant="ghost"
            size="sm"
            className="h-8 px-2 text-xs"
          >
            <Link to="/products">
              <ChevronLeft className="mr-1 h-3.5 w-3.5" /> К списку
            </Link>
          </Button>
          {activeId ? (
            <Badge variant="outline" className="text-[10px]">
              Product 360
            </Badge>
          ) : null}
        </div>

        {!data ? (
          <h1 data-testid="product-360-title" className="sr-only">
            {String(name)}
          </h1>
        ) : null}

        {!activeId && <NoAccountSelected />}

        {activeId && contextProblemInstanceId ? (
          <ActionCenterReturnLink
            problem_instance_id={contextProblemInstanceId}
            nm_id={nmId}
            description={
              contextTab === "promo"
                ? "Вы открыли план промо из задачи. После проверки зафиксируйте действие и вернитесь к той же задаче."
                : contextTab === "price"
                  ? "Вы открыли проверку цены из задачи. После проверки зафиксируйте действие и вернитесь к той же задаче."
                  : undefined
            }
          />
        ) : null}

        {activeId &&
          contextProblemInstanceId &&
          (contextTab === "price" || contextTab === "promo") && (
            <Alert className="border-primary/30 bg-primary/5">
              <CheckCircle2 className="h-4 w-4 text-primary" />
              <AlertTitle>
                {contextTab === "promo"
                  ? "Проверьте промо в контексте задачи"
                  : "Проверьте цену в контексте задачи"}
              </AlertTitle>
              <AlertDescription className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                <span>
                  Контекст товара и задачи сохранён. Зафиксируйте проверку,
                  чтобы в Центре действий появилась история локального шага.
                </span>
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  data-testid="action-center-context-local-fix"
                  disabled={contextualReviewMutation.isPending}
                  onClick={() => contextualReviewMutation.mutate()}
                >
                  {contextualReviewMutation.isPending
                    ? "Сохраняем..."
                    : "Зафиксировать проверку"}
                </Button>
              </AlertDescription>
            </Alert>
          )}

        {activeId && error && (
          <Alert variant="destructive">
            <AlertTriangle className="h-4 w-4" />
            <AlertTitle>Не удалось загрузить карточку</AlertTitle>
            <AlertDescription className="space-y-2">
              <div>{(error as Error).message}</div>
              <Button
                size="sm"
                variant="outline"
                onClick={() => refetch()}
                disabled={isFetching}
              >
                {isFetching ? "Повтор…" : "Повторить"}
              </Button>
            </AlertDescription>
          </Alert>
        )}

        {activeId && isLoading && !error && <ProductCockpitSkeleton />}

        {activeId && data && (
          <ProductCockpit
            data={data}
            nmId={nmId}
            dateFrom={dateFrom}
            dateTo={dateTo}
          />
        )}
      </div>
    </PageShell>
  );
}

// ─── friendly placeholders for known-but-unavailable backend sections ──
function FriendlySection({
  title,
  text,
  status,
}: {
  title: string;
  text: string;
  status?: string;
}) {
  return (
    <SectionCard title={title} status={status ?? "not_configured"}>
      <div className="text-xs text-muted-foreground">{text}</div>
    </SectionCard>
  );
}

// Grouping Beta block — never claims the module is disabled; always links to /grouping.
function GroupingProductSection({
  grouping,
  nmId,
}: {
  grouping: any;
  nmId: string | number;
}) {
  const status = sectionStatus(grouping);
  const g =
    sectionData<any>(grouping) ??
    (grouping && typeof grouping === "object" ? grouping : {});
  if (
    status === "disabled" ||
    status === "not_configured" ||
    status === "unavailable"
  ) {
    return (
      <SectionCard
        title="Группировка"
        subtitle={moduleBusinessStatus(status, "empty")}
        status={status}
      >
        <div className="text-xs text-muted-foreground">
          {sectionMessage(grouping) ??
            "Модуль группировки пока не готов для этой карточки."}
        </div>
        <Button
          asChild
          size="sm"
          variant="outline"
          className="h-7 text-xs w-full"
        >
          <Link to="/grouping" search={{ nm_id: String(nmId) } as any}>
            Открыть группировку <ArrowRight className="h-3 w-3 ml-1" />
          </Link>
        </Button>
      </SectionCard>
    );
  }
  const recommendations: any[] = Array.isArray(g.recommendations)
    ? g.recommendations
    : Array.isArray(g.items)
      ? g.items
      : Array.isArray(g.candidates)
        ? g.candidates
        : [];
  const recCount =
    Number(
      g.recommendations_count ??
        g.recommendation_count ??
        g.count ??
        recommendations.length,
    ) || 0;
  const lastAt = g.last_analyzed_at ?? g.analyzed_at ?? g.updated_at ?? null;
  const confidence =
    g.max_confidence ??
    g.confidence ??
    recommendations.find((it) => it.confidence != null)?.confidence ??
    null;
  const risk =
    g.max_risk ??
    g.risk ??
    recommendations.find((it) => it.risk != null)?.risk ??
    null;
  const stateRaw = String(
    g.state ??
      g.status ??
      (recCount > 0 ? "ok" : lastAt ? "empty" : "not_analyzed"),
  ).toLowerCase();
  const stateLabel =
    stateRaw === "ok"
      ? "Есть рекомендации для ручной проверки."
      : stateRaw === "empty"
        ? "По текущим правилам безопасных кандидатов не найдено."
        : stateRaw === "running"
          ? "Идёт анализ…"
          : stateRaw === "partial"
            ? "Анализ выполнен частично."
            : stateRaw === "failed"
              ? "Анализ завершился ошибкой."
              : "Модуль ещё не анализировал этот товар.";
  return (
    <SectionCard
      title="Группировка"
      subtitle="Только ручная проверка, автообъединение выключено"
      status={recCount > 0 ? "warning" : stateRaw}
    >
      <div className="space-y-3 text-xs">
        <div className="text-muted-foreground">{stateLabel}</div>
        <div className="grid grid-cols-3 gap-2">
          <MiniKpi label="Рекомендации" value={recCount} />
          <MiniKpi label="Уверенность" value={confidence ?? null} />
          <MiniKpi label="Риск" value={risk ?? null} />
        </div>
        {lastAt && (
          <div className="text-[11px] text-muted-foreground">
            Последний анализ: {formatDateTimeShort(lastAt)}
          </div>
        )}
        {recommendations.length > 0 && (
          <ul className="space-y-1">
            {recommendations.slice(0, 3).map((it, i) => (
              <li
                key={it.id ?? it.candidate_id ?? i}
                className="rounded border p-2"
              >
                <div className="font-medium truncate">
                  {it.title ??
                    it.name ??
                    it.source_title ??
                    `Кандидат #${i + 1}`}
                </div>
                <div className="flex flex-wrap gap-2 text-[11px] text-muted-foreground mt-0.5">
                  {(it.confidence ?? it.score) != null && (
                    <span>
                      Уверенность: {String(it.confidence ?? it.score)}
                    </span>
                  )}
                  {it.risk != null && <span>Риск: {String(it.risk)}</span>}
                </div>
              </li>
            ))}
          </ul>
        )}
        <Button
          asChild
          size="sm"
          variant={recCount > 0 ? "default" : "outline"}
          className="h-7 text-xs w-full"
        >
          <Link to="/grouping" search={{ nm_id: String(nmId) } as any}>
            Открыть группировку <ArrowRight className="h-3 w-3 ml-1" />
          </Link>
        </Button>
      </div>
    </SectionCard>
  );
}

function ExperimentsSection({
  section,
  nmId,
}: {
  section: any;
  nmId: string | number;
}) {
  const e = sectionData<any>(section) ?? {};
  const status = sectionStatus(section) ?? pick<string>(e, ["status"]);
  const items: any[] = Array.isArray(e.items)
    ? e.items
    : Array.isArray(e.experiments)
      ? e.experiments
      : Array.isArray(e.running)
        ? e.running
        : [];
  const summary = isObj(e.summary) ? e.summary : {};
  const activeCount =
    pick<number>(summary, ["active_count", "running_count"]) ??
    items.filter((it) =>
      ["running", "active", "started"].includes(
        String(it.status || "").toLowerCase(),
      ),
    ).length;
  const plannedCount =
    pick<number>(summary, ["planned_count", "pending_count"]) ??
    items.filter((it) =>
      ["planned", "pending", "draft"].includes(
        String(it.status || "").toLowerCase(),
      ),
    ).length;
  const finishedCount =
    pick<number>(summary, ["finished_count", "completed_count"]) ??
    items.filter((it) =>
      ["finished", "completed", "cancelled"].includes(
        String(it.status || "").toLowerCase(),
      ),
    ).length;
  const latest =
    e.latest_result ??
    e.latest_evaluation ??
    items.find((it) => it.latest_evaluation)?.latest_evaluation ??
    items[0]?.latest_evaluation ??
    null;
  const latestText =
    latest?.seller_summary ?? latest?.summary ?? latest?.outcome ?? null;
  const confidence = latest?.confidence ?? e.confidence ?? null;
  const nextDate =
    e.next_evaluation_at ??
    items.find((it) => it.evaluation_due_at)?.evaluation_due_at ??
    null;
  const hasTests =
    items.length > 0 ||
    activeCount > 0 ||
    plannedCount > 0 ||
    finishedCount > 0;
  const rawUnavailable =
    status === "disabled" ||
    status === "not_configured" ||
    status === "unavailable";
  if (rawUnavailable) {
    return (
      <SectionCard
        title="A/B тесты"
        subtitle={moduleBusinessStatus(status, "empty")}
        status={status}
      >
        <div className="text-xs text-muted-foreground">
          {sectionMessage(section) ?? "Модуль A/B тестов пока недоступен."}
        </div>
        <Button
          asChild
          size="sm"
          variant="outline"
          className="h-7 text-xs w-full"
        >
          <Link to="/ab-tests" search={{ nm_id: String(nmId) } as any}>
            Открыть A/B тесты <ArrowRight className="h-3 w-3 ml-1" />
          </Link>
        </Button>
      </SectionCard>
    );
  }
  return (
    <SectionCard
      title="A/B тесты"
      subtitle={moduleBusinessStatus(
        status,
        activeCount > 0 ? "running" : hasTests ? "ok" : "empty",
      )}
      status={activeCount > 0 ? "warning" : hasTests ? "ok" : "empty"}
    >
      <div className="grid grid-cols-3 gap-2">
        <MiniKpi label="Идут" value={activeCount} />
        <MiniKpi label="План" value={plannedCount} />
        <MiniKpi label="Завершены" value={finishedCount} />
      </div>
      {latestText ? (
        <div className="rounded border bg-muted/30 p-2 text-xs">
          <div className="font-medium">Последний результат</div>
          <div className="text-muted-foreground mt-0.5 line-clamp-3">
            {latestText}
          </div>
          {confidence && (
            <div className="text-[11px] text-muted-foreground mt-1">
              Уверенность: {String(confidence)}
            </div>
          )}
        </div>
      ) : (
        <div className="text-xs text-muted-foreground">
          {hasTests
            ? "Данных для оценки пока мало."
            : "По этой карточке A/B тестов пока нет."}
        </div>
      )}
      {nextDate && (
        <div className="text-[11px] text-muted-foreground">
          Следующая оценка: {formatDateTimeShort(nextDate)}
        </div>
      )}
      <Button
        asChild
        size="sm"
        variant={activeCount > 0 ? "default" : "outline"}
        className="h-7 text-xs w-full"
      >
        <Link to="/ab-tests" search={{ nm_id: String(nmId) } as any}>
          {activeCount > 0 ? "Открыть A/B тест" : "Создать тест"}{" "}
          <ArrowRight className="h-3 w-3 ml-1" />
        </Link>
      </Button>
    </SectionCard>
  );
}

const KNOWN_TOP_KEYS = new Set([
  "identity",
  "money",
  "costs",
  "cost",
  "data_quality",
  "card_quality",
  "quality",
  "stock",
  "claims",
  "reputation",
  "actions",
  "result_history",
  "history",
  "results",
  "recent_events",
  "next_best_action",
  "next_action",
  "ads",
  "photo",
  "photo_studio",
  "experiments",
  "grouping",
  "grouping_beta",
  "title",
  "name",
  "image",
  "image_url",
  "vendor_code",
  "brand",
  "subject_name",
  "business_status",
  "priority",
  "nm_id",
]);

function ExtraSections({ data }: { data: any }) {
  const [debugOpen, setDebugOpen] = useState(false);

  // Friendly cards for known unavailable sections, instead of raw JSON.
  const pricing = data?.pricing;
  const overviewDiag = data?.overview_diagnosis ?? data?.overview;
  const history = data?.history ?? data?.result_history;

  const historyItems = Array.isArray(history)
    ? history
    : Array.isArray(history?.items)
      ? history.items
      : Array.isArray(history?.events)
        ? history.events
        : Array.isArray(sectionData<any>(history)?.events)
          ? sectionData<any>(history).events
          : [];

  // Collect remaining unknown object blocks for the admin debug accordion.
  const debugEntries = Object.entries(data ?? {}).filter(
    ([k, v]) =>
      isObj(v) &&
      !KNOWN_TOP_KEYS.has(k) &&
      !["pricing", "overview_diagnosis", "overview", "history"].includes(k),
  );

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
        {pricing !== undefined && (
          <FriendlySection
            title="Ценообразование"
            text="Рекомендация по цене пока не рассчитана: нужны текущая цена, комиссия WB, себестоимость и свежие продажи за период."
          />
        )}
        {overviewDiag !== undefined && (
          <FriendlySection
            title="Диагностика"
            text="Подробная диагностика появится после следующей синхронизации."
          />
        )}
        {history !== undefined && (
          <FriendlySection
            title="История"
            text={
              historyItems.length
                ? `История: ${historyItems.length} событий`
                : "История: нет событий"
            }
            status="ok"
          />
        )}
      </div>

      {(debugEntries.length > 0 || pricing !== undefined) && (
        <details
          className="rounded border border-dashed border-border/60 p-2"
          open={debugOpen}
          onToggle={(e) => setDebugOpen((e.target as HTMLDetailsElement).open)}
        >
          <summary className="cursor-pointer text-[11px] text-muted-foreground select-none">
            Технические данные (для администратора)
          </summary>
          <div className="pt-2 space-y-2">
            {debugEntries.slice(0, 12).map(([k, v]) => (
              <div key={k} className="rounded border p-2">
                <div className="text-[11px] font-mono text-muted-foreground mb-1">
                  {k}
                </div>
                <pre className="text-[10px] text-muted-foreground overflow-x-auto max-h-48">
                  {JSON.stringify(v, null, 2)}
                </pre>
              </div>
            ))}
          </div>
        </details>
      )}
    </div>
  );
}
