// @ts-nocheck
import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  ArrowDownRight,
  ArrowUpRight,
  BarChart3,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Clock3,
  DatabaseZap,
  ExternalLink,
  FileSearch,
  Filter,
  Layers3,
  LineChart,
  ListChecks,
  RefreshCw,
  Search,
  ShieldCheck,
  SlidersHorizontal,
  TimerReset,
  X,
} from "lucide-react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Pie,
  PieChart,
  XAxis,
  YAxis,
} from "recharts";

import { useAccounts } from "@/lib/account-context";
import {
  fetchProblemResults,
  fetchResults,
  type PortalResultEventsPage,
} from "@/lib/portal";
import { PageShell } from "@/components/PageShell";
import { PageHeader } from "@/components/shell/PageHeader";
import { EmptyState } from "@/components/shell/EmptyState";
import { LoadingSkeleton } from "@/components/shell/LoadingSkeleton";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from "@/components/ui/chart";
import { EndpointError } from "@/components/EndpointError";
import { EvidenceDrawer } from "@/components/EvidenceDrawer";
import { NoAccountSelected } from "@/components/portal/NoAccountSelected";
import { ActionCenterReturnLink } from "@/components/action-center/ActionCenterReturnLink";
import {
  ImpactBadge,
  ResultBadge,
  TrustBadge,
} from "@/components/badges/StatusBadges";
import { ResultDetailDrawer } from "@/components/results/ResultDetailDrawer";
import {
  classifyOutcome,
  classifyTrust,
  computeSummaryCounts,
  isMeasuredEffect,
  measuredAmount,
  type ResultOutcomeKey,
} from "@/components/results/resultsClassify";
import { evidenceFrom } from "@/lib/evidence";
import { formatMoney, formatNumber } from "@/lib/format";
import { routeSearchText } from "@/lib/action-center-routing";
import { sellerSafeMessage } from "@/lib/results-i18n";
import {
  humanizeEventType,
  humanizeMessage,
  humanizeModule,
} from "@/lib/results-i18n";
import { problemCodeLabel } from "@/lib/problem-ux-copy";
import {
  PROBLEM_RESULT_CORRELATION_DISCLAIMER,
  problemResultHasAfterData,
  problemResultHasConfidence,
} from "@/lib/problem-results";
import {
  buildContextLinks,
  formatConfidenceValue,
  hasEvidence,
} from "@/lib/results-metric-templates";
import { cn } from "@/lib/utils";

const ALL_VALUE = "__all__";
const DEFAULT_LIMIT = 100;
const PAGE_LIMITS = [25, 50, 100, 200];

export type ResultsSearch = {
  action_id?: string;
  problem_code?: string;
  problem_instance_id?: string;
  nm_id?: string;
  source_module?: string;
  event_type?: string;
  result_status?: string;
  trust_state?: string;
  impact_type?: string;
  date_from?: string;
  date_to?: string;
  search?: string;
  page?: string;
  limit?: string;
};

export const Route = createFileRoute("/_authenticated/results")({
  component: ResultsPage,
  validateSearch: (s: Record<string, unknown>): ResultsSearch => ({
    action_id: routeSearchText(s.action_id),
    problem_code: routeSearchText(s.problem_code),
    problem_instance_id: routeSearchText(s.problem_instance_id),
    nm_id: routeSearchText(s.nm_id),
    source_module: routeSearchText(s.source_module),
    event_type: routeSearchText(s.event_type),
    result_status: routeSearchText(s.result_status),
    trust_state: routeSearchText(s.trust_state),
    impact_type: routeSearchText(s.impact_type),
    date_from: routeSearchText(s.date_from),
    date_to: routeSearchText(s.date_to),
    search: routeSearchText(s.search),
    page: routeSearchText(s.page),
    limit: routeSearchText(s.limit),
  }),
  errorComponent: ({ error, reset }) => (
    <EndpointError error={error} reset={reset} />
  ),
});

type TrackingFilter =
  | "all"
  | "attention"
  | "missing_after"
  | "missing_evidence"
  | "measured"
  | "checker";

type Option = { value: string; label: string };

const SOURCE_OPTIONS: Option[] = [
  { value: ALL_VALUE, label: "Все модули" },
  { value: "problem_engine", label: "Проблемы товара" },
  { value: "checker", label: "Качество карточек" },
  { value: "action_center", label: "Центр задач" },
  { value: "data_quality", label: "Качество данных" },
  { value: "finance", label: "Финансы" },
  { value: "ads", label: "Реклама" },
  { value: "stock", label: "Остатки" },
];

const EVENT_OPTIONS: Option[] = [
  { value: ALL_VALUE, label: "Все события" },
  { value: "before_snapshot", label: "Снимок до" },
  { value: "action_started", label: "Действие начато" },
  { value: "action_completed", label: "Действие выполнено" },
  { value: "recheck_result", label: "Перепроверка" },
  { value: "result_evaluated", label: "Результат оценён" },
  { value: "status_changed", label: "Статус изменён" },
];

const RESULT_STATUS_OPTIONS: Option[] = [
  { value: ALL_VALUE, label: "Любой результат" },
  { value: "pending_data", label: "Ждём данных" },
  { value: "improved", label: "Есть улучшение" },
  { value: "worse", label: "Стало хуже" },
  { value: "neutral", label: "Без изменений" },
  { value: "not_enough_data", label: "Нет данных" },
];

const TRUST_OPTIONS: Option[] = [
  { value: ALL_VALUE, label: "Любая точность" },
  { value: "confirmed", label: "Подтверждённые" },
  { value: "estimated", label: "Оценочные" },
  { value: "blocked", label: "Заблокировано данными" },
  { value: "unknown", label: "Неизвестно" },
];

const IMPACT_OPTIONS: Option[] = [
  { value: ALL_VALUE, label: "Любой эффект" },
  { value: "money_risk", label: "Деньги / риск" },
  { value: "data_blocker", label: "Блокер данных" },
  { value: "content_quality", label: "Качество карточки" },
  { value: "stock_risk", label: "Остатки" },
  { value: "opportunity", label: "Возможность" },
  { value: "operational", label: "Операционный" },
];

const TRACKING_FILTERS: Array<{
  value: TrackingFilter;
  label: string;
  hint: string;
}> = [
  { value: "all", label: "Все", hint: "Все загруженные события" },
  {
    value: "attention",
    label: "Требуют внимания",
    hint: "Ждут данных или проверки",
  },
  {
    value: "missing_after",
    label: "Нет данных после",
    hint: "Нет снимка после действия",
  },
  {
    value: "missing_evidence",
    label: "Нет доказательств",
    hint: "Нет ведомости расчёта",
  },
  { value: "measured", label: "Факт", hint: "Есть измеренный результат" },
  { value: "checker", label: "Карточки WB", hint: "Качество карточек" },
];

const OUTCOME_META: Record<
  ResultOutcomeKey,
  { label: string; color: string; tone: string }
> = {
  pending_data: {
    label: "Ждём данных",
    color: "var(--warning)",
    tone: "text-warning",
  },
  improved: {
    label: "Улучшение",
    color: "var(--success)",
    tone: "text-success",
  },
  worse: {
    label: "Хуже",
    color: "var(--destructive)",
    tone: "text-destructive",
  },
  neutral: {
    label: "Без изменений",
    color: "var(--info)",
    tone: "text-info",
  },
  not_enough_data: {
    label: "Нет данных",
    color: "var(--muted-foreground)",
    tone: "text-muted-foreground",
  },
};

const TREND_CHART_CONFIG: ChartConfig = {
  total: { label: "Всего", color: "var(--chart-1)" },
  improved: { label: "Улучшение", color: "var(--success)" },
  worse: { label: "Хуже", color: "var(--destructive)" },
  pending: { label: "Ждём данных", color: "var(--warning)" },
};

const MODULE_CHART_CONFIG: ChartConfig = {
  count: { label: "Событий", color: "var(--chart-5)" },
};

function isRecord(v: unknown): v is Record<string, unknown> {
  return !!v && typeof v === "object" && !Array.isArray(v);
}

function pick<T = unknown>(obj: unknown, keys: string[]): T | undefined {
  if (!isRecord(obj)) return undefined;
  for (const key of keys) {
    const value = obj[key];
    if (value != null && value !== "") return value as T;
  }
  return undefined;
}

function compactText(v: unknown): string {
  return String(v ?? "").trim();
}

function routeFilter(v?: string): string {
  const value = compactText(v);
  return value === ALL_VALUE || value === "all" ? "" : value;
}

function positiveInt(v: unknown, fallback: number): number {
  const n = Number(v);
  return Number.isFinite(n) && n > 0 ? Math.floor(n) : fallback;
}

function allowedLimit(v: unknown): number {
  const n = positiveInt(v, DEFAULT_LIMIT);
  return PAGE_LIMITS.includes(n) ? n : DEFAULT_LIMIT;
}

function fmtDateTime(value?: string | null): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    year: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function fmtDay(value?: string | null): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleDateString("ru-RU", {
    day: "2-digit",
    month: "2-digit",
  });
}

function dayKey(value?: string | null): string {
  if (!value) return "unknown";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "unknown";
  return date.toISOString().slice(0, 10);
}

function hasSnapshot(
  event: unknown,
  key: "before_snapshot" | "after_snapshot",
) {
  const r = isRecord(event) ? event : {};
  const value = r[key];
  return isRecord(value) && Object.keys(value).length > 0;
}

function ledgerFromEvent(event: unknown) {
  const r = isRecord(event) ? event : {};
  const payload = isRecord(r.payload) ? r.payload : {};
  return evidenceFrom(r.evidence_ledger, payload.evidence_ledger);
}

function hasProof(event: unknown): boolean {
  return hasEvidence(event) || !!ledgerFromEvent(event);
}

function eventProductIdentity(event: unknown) {
  const r = isRecord(event) ? event : {};
  return isRecord(r.product_identity) ? r.product_identity : {};
}

function eventTitle(event: unknown): string {
  const r = isRecord(event) ? event : {};
  const identity = eventProductIdentity(event);
  return (
    pick<string>(identity, ["title", "name", "product_title"]) ??
    pick<string>(r, ["product_title", "nm_name"]) ??
    humanizeEventType(pick<string>(r, ["event_type"])).label ??
    "Событие результата"
  );
}

function eventNmId(event: unknown): string | null {
  const r = isRecord(event) ? event : {};
  const identity = eventProductIdentity(event);
  const value =
    pick<string | number>(identity, ["nm_id"]) ??
    pick<string | number>(r, ["nm_id"]);
  return value == null || value === "" ? null : String(value);
}

function eventVendorCode(event: unknown): string | null {
  const r = isRecord(event) ? event : {};
  const identity = eventProductIdentity(event);
  return (
    pick<string>(identity, ["vendor_code", "article", "vendorCode"]) ??
    pick<string>(r, ["vendor_code", "article"]) ??
    null
  );
}

function eventCreatedAt(event: unknown): string | null {
  const r = isRecord(event) ? event : {};
  return (
    pick<string>(r, ["created_at", "at", "occurred_at", "timestamp"]) ?? null
  );
}

function eventModule(event: unknown): string {
  const r = isRecord(event) ? event : {};
  return compactText(pick<string>(r, ["source_module", "module", "source"]));
}

function eventProblemCode(event: unknown): string {
  const r = isRecord(event) ? event : {};
  return compactText(pick<string>(r, ["problem_code"]));
}

function isCheckerEvent(event: unknown): boolean {
  const module = eventModule(event).toLowerCase();
  const code = eventProblemCode(event).toLowerCase();
  return (
    module === "checker" ||
    module === "card_quality" ||
    /checker|card_quality|content|photo|title|description|characteristics/.test(
      code,
    )
  );
}

function needsAttention(event: unknown): boolean {
  const outcome = classifyOutcome(event);
  if (outcome === "pending_data" || outcome === "not_enough_data") return true;
  if (!problemResultHasAfterData(event)) return true;
  return false;
}

function matchesAuditEvent(event: unknown): boolean {
  const r = isRecord(event) ? event : {};
  if (
    r.audit === true ||
    r.is_audit === true ||
    r.is_test === true ||
    r.test === true
  ) {
    return true;
  }
  const payload = [r.payload, r.data, r.meta].find(isRecord);
  if (
    payload &&
    (payload.audit === true ||
      payload.is_audit === true ||
      payload.is_test === true ||
      payload.test === true)
  ) {
    return true;
  }
  const tags = r.tags ?? r.labels;
  return (
    Array.isArray(tags) &&
    tags.some((tag) => ["audit", "test"].includes(String(tag).toLowerCase()))
  );
}

function matchesLocalSearch(event: unknown, query: string): boolean {
  const text = query.trim().toLowerCase();
  if (!text) return true;
  const r = isRecord(event) ? event : {};
  const identity = eventProductIdentity(event);
  const haystack = [
    r.event_type,
    r.source_module,
    r.problem_code,
    r.message,
    r.source_id,
    r.external_id,
    r.nm_id,
    r.vendor_code,
    identity.title,
    identity.name,
    identity.nm_id,
    identity.vendor_code,
    identity.article,
  ]
    .filter(Boolean)
    .map((v) => String(v).toLowerCase())
    .join(" ");
  return haystack.includes(text);
}

function matchesExactText(eventValue: unknown, filterValue: string): boolean {
  const filter = filterValue.trim().toLowerCase();
  if (!filter) return true;
  return (
    String(eventValue ?? "")
      .trim()
      .toLowerCase() === filter
  );
}

function matchesDateRange(
  value: string | null,
  dateFrom: string,
  dateTo: string,
): boolean {
  if (!dateFrom.trim() && !dateTo.trim()) return true;
  if (!value) return false;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return false;
  if (dateFrom.trim()) {
    const from = new Date(`${dateFrom.trim()}T00:00:00`);
    if (!Number.isNaN(from.getTime()) && date < from) return false;
  }
  if (dateTo.trim()) {
    const to = new Date(`${dateTo.trim()}T23:59:59`);
    if (!Number.isNaN(to.getTime()) && date > to) return false;
  }
  return true;
}

function matchesFocusedProblemFilters(
  event: unknown,
  filters: {
    actionId: string;
    eventType: string;
    resultStatus: string;
    dateFrom: string;
    dateTo: string;
    search: string;
  },
): boolean {
  const r = isRecord(event) ? event : {};
  if (!matchesExactText(r.action_id, filters.actionId)) return false;
  if (!matchesExactText(r.event_type, filters.eventType)) return false;
  if (
    filters.resultStatus.trim() &&
    classifyOutcome(event) !== filters.resultStatus.trim()
  ) {
    return false;
  }
  if (
    !matchesDateRange(eventCreatedAt(event), filters.dateFrom, filters.dateTo)
  ) {
    return false;
  }
  if (!matchesLocalSearch(event, filters.search)) return false;
  return true;
}

function matchesTrackingFilter(
  event: unknown,
  filter: TrackingFilter,
): boolean {
  if (filter === "all") return true;
  if (filter === "attention") return needsAttention(event);
  if (filter === "missing_after") return !problemResultHasAfterData(event);
  if (filter === "missing_evidence") return !hasProof(event);
  if (filter === "measured") return isMeasuredEffect(event);
  if (filter === "checker") return isCheckerEvent(event);
  return true;
}

function pct(part: number, total: number): number {
  if (!total) return 0;
  return Math.round((part / total) * 100);
}

function buildTrend(items: unknown[]) {
  const grouped = new Map<
    string,
    {
      key: string;
      label: string;
      total: number;
      improved: number;
      worse: number;
      pending: number;
    }
  >();
  for (const item of items) {
    const createdAt = eventCreatedAt(item);
    const key = dayKey(createdAt);
    const current = grouped.get(key) ?? {
      key,
      label: key === "unknown" ? "Без даты" : fmtDay(createdAt),
      total: 0,
      improved: 0,
      worse: 0,
      pending: 0,
    };
    const outcome = classifyOutcome(item);
    current.total += 1;
    if (outcome === "improved") current.improved += 1;
    if (outcome === "worse") current.worse += 1;
    if (outcome === "pending_data" || outcome === "not_enough_data") {
      current.pending += 1;
    }
    grouped.set(key, current);
  }
  return [...grouped.values()]
    .sort((a, b) => a.key.localeCompare(b.key))
    .slice(-21);
}

function buildModuleRows(items: unknown[]) {
  const grouped = new Map<
    string,
    {
      key: string;
      label: string;
      count: number;
      improved: number;
      attention: number;
    }
  >();
  for (const item of items) {
    const key = eventModule(item) || "unknown";
    const current = grouped.get(key) ?? {
      key,
      label: key === "unknown" ? "Источник не указан" : humanizeModule(key),
      count: 0,
      improved: 0,
      attention: 0,
    };
    current.count += 1;
    if (classifyOutcome(item) === "improved") current.improved += 1;
    if (needsAttention(item)) current.attention += 1;
    grouped.set(key, current);
  }
  return [...grouped.values()].sort((a, b) => b.count - a.count).slice(0, 8);
}

function buildProblemRows(items: unknown[]) {
  const grouped = new Map<
    string,
    {
      code: string;
      count: number;
      improved: number;
      worse: number;
      pending: number;
      after: number;
    }
  >();
  for (const item of items) {
    const code = eventProblemCode(item) || "unknown";
    const current = grouped.get(code) ?? {
      code,
      count: 0,
      improved: 0,
      worse: 0,
      pending: 0,
      after: 0,
    };
    const outcome = classifyOutcome(item);
    current.count += 1;
    if (outcome === "improved") current.improved += 1;
    if (outcome === "worse") current.worse += 1;
    if (outcome === "pending_data" || outcome === "not_enough_data") {
      current.pending += 1;
    }
    if (problemResultHasAfterData(item)) current.after += 1;
    grouped.set(code, current);
  }
  return [...grouped.values()].sort((a, b) => b.count - a.count).slice(0, 7);
}

function buildDashboard(items: unknown[], total: number) {
  const counts = computeSummaryCounts(items);
  const loaded = items.length;
  let before = 0;
  let after = 0;
  let evidence = 0;
  let confidence = 0;
  let confirmed = 0;
  let estimated = 0;
  let unknown = 0;
  let checker = 0;
  let measured = 0;
  let attention = 0;

  for (const item of items) {
    if (hasSnapshot(item, "before_snapshot")) before += 1;
    if (problemResultHasAfterData(item)) after += 1;
    if (hasProof(item)) evidence += 1;
    if (problemResultHasConfidence(item)) confidence += 1;
    const trust = classifyTrust(item);
    if (trust === "confirmed") confirmed += 1;
    else if (trust === "estimated") estimated += 1;
    else unknown += 1;
    if (isCheckerEvent(item)) checker += 1;
    if (isMeasuredEffect(item)) measured += 1;
    if (needsAttention(item)) attention += 1;
  }

  const outcomeChart = (Object.keys(OUTCOME_META) as ResultOutcomeKey[])
    .map((key) => ({
      key,
      label: OUTCOME_META[key].label,
      value: counts[key],
      fill: OUTCOME_META[key].color,
    }))
    .filter((row) => row.value > 0);

  return {
    total,
    loaded,
    counts,
    before,
    after,
    evidence,
    confidence,
    confirmed,
    estimated,
    unknown,
    checker,
    measured,
    attention,
    beforePct: pct(before, loaded),
    afterPct: pct(after, loaded),
    evidencePct: pct(evidence, loaded),
    confidencePct: pct(confidence, loaded),
    confirmedPct: pct(confirmed, loaded),
    attentionPct: pct(attention, loaded),
    trend: buildTrend(items),
    modules: buildModuleRows(items),
    problems: buildProblemRows(items),
    outcomeChart,
  };
}

function dataItems(data: PortalResultEventsPage | unknown): unknown[] {
  if (Array.isArray(data)) return data;
  const obj = isRecord(data) ? data : {};
  for (const key of ["items", "recent_events", "results"]) {
    const value = obj[key];
    if (Array.isArray(value)) return value;
  }
  return [];
}

function SelectFilter({
  label,
  value,
  options,
  onChange,
  disabled,
}: {
  label: string;
  value: string;
  options: Option[];
  onChange: (value: string) => void;
  disabled?: boolean;
}) {
  return (
    <div className="space-y-1.5">
      <Label className="text-xs text-muted-foreground">{label}</Label>
      <Select
        value={value || ALL_VALUE}
        onValueChange={(next) => onChange(next === ALL_VALUE ? "" : next)}
        disabled={disabled}
      >
        <SelectTrigger className="h-9 rounded-md">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {options.map((option) => (
            <SelectItem key={option.value} value={option.value}>
              {option.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}

function KpiCard({
  icon: Icon,
  title,
  value,
  hint,
  trend,
  tone = "default",
}: {
  icon: any;
  title: string;
  value: string;
  hint: string;
  trend?: "up" | "down" | "flat";
  tone?: "default" | "success" | "warning" | "danger" | "info";
}) {
  const toneClass =
    tone === "success"
      ? "text-success bg-success/10 border-success/30"
      : tone === "warning"
        ? "text-warning bg-warning/10 border-warning/30"
        : tone === "danger"
          ? "text-destructive bg-destructive/10 border-destructive/30"
          : tone === "info"
            ? "text-info bg-info/10 border-info/30"
            : "text-primary bg-primary/10 border-primary/30";
  const TrendIcon =
    trend === "up" ? ArrowUpRight : trend === "down" ? ArrowDownRight : null;
  return (
    <Card className="rounded-md">
      <CardContent className="p-3">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="text-[11px] font-medium uppercase text-muted-foreground">
              {title}
            </div>
            <div className="mt-1 text-2xl font-semibold tabular-nums">
              {value}
            </div>
          </div>
          <div
            className={cn(
              "flex h-9 w-9 shrink-0 items-center justify-center rounded-md border",
              toneClass,
            )}
          >
            <Icon className="h-4 w-4" />
          </div>
        </div>
        <div className="mt-2 flex min-h-8 items-start gap-1.5 text-xs text-muted-foreground">
          {TrendIcon ? (
            <TrendIcon className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          ) : null}
          <span>{hint}</span>
        </div>
      </CardContent>
    </Card>
  );
}

function TrackingMeter({
  label,
  value,
  total,
  description,
}: {
  label: string;
  value: number;
  total: number;
  description: string;
}) {
  const percent = pct(value, total);
  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between gap-3 text-xs">
        <div>
          <div className="font-medium">{label}</div>
          <div className="text-[11px] text-muted-foreground">{description}</div>
        </div>
        <div className="shrink-0 font-mono tabular-nums">
          {formatNumber(value)} / {formatNumber(total)}
        </div>
      </div>
      <Progress value={percent} className="h-1.5 rounded-sm" />
      <div className="text-right text-[11px] text-muted-foreground">
        {percent}%
      </div>
    </div>
  );
}

function ResultsFilterPanel({
  search,
  setSearch,
  dateFrom,
  setDateFrom,
  dateTo,
  setDateTo,
  sourceModule,
  setSourceModule,
  eventType,
  setEventType,
  resultStatus,
  setResultStatus,
  trustState,
  setTrustState,
  impactType,
  setImpactType,
  problemCode,
  setProblemCode,
  problemInstanceId,
  setProblemInstanceId,
  nmId,
  setNmId,
  actionId,
  setActionId,
  focusedProblem,
  showAdvanced,
  setShowAdvanced,
  showAudit,
  setShowAudit,
  onClear,
}: any) {
  const mutate = (fn: (v: string) => void) => (value: string) => {
    fn(value);
  };

  return (
    <section className="rounded-md border bg-card p-3">
      <div className="grid gap-3 lg:grid-cols-[minmax(240px,1.4fr)_repeat(4,minmax(150px,1fr))_auto]">
        <div className="space-y-1.5">
          <Label className="text-xs text-muted-foreground">
            Поиск по результатам
          </Label>
          <div className="relative">
            <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="название, артикул, код проблемы, сообщение"
              className="h-9 rounded-md pl-8"
            />
          </div>
        </div>
        <SelectFilter
          label="Результат"
          value={resultStatus}
          options={RESULT_STATUS_OPTIONS}
          onChange={mutate(setResultStatus)}
        />
        <SelectFilter
          label="Модуль"
          value={sourceModule}
          options={SOURCE_OPTIONS}
          onChange={mutate(setSourceModule)}
          disabled={focusedProblem}
        />
        <SelectFilter
          label="Событие"
          value={eventType}
          options={EVENT_OPTIONS}
          onChange={mutate(setEventType)}
        />
        <SelectFilter
          label="Точность"
          value={trustState}
          options={TRUST_OPTIONS}
          onChange={mutate(setTrustState)}
          disabled={focusedProblem}
        />
        <div className="flex items-end gap-2">
          <Button
            type="button"
            variant="outline"
            className="h-9 rounded-md"
            onClick={() => setShowAdvanced((v: boolean) => !v)}
          >
            <SlidersHorizontal className="h-4 w-4" />
            <span className="hidden xl:inline">Ещё</span>
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="h-9 w-9 rounded-md"
            onClick={onClear}
            title="Сбросить фильтры"
          >
            <X className="h-4 w-4" />
          </Button>
        </div>
      </div>

      {showAdvanced ? (
        <div className="mt-3 grid gap-3 border-t pt-3 md:grid-cols-2 xl:grid-cols-6">
          <div className="space-y-1.5">
            <Label className="text-xs text-muted-foreground">Дата с</Label>
            <Input
              type="date"
              value={dateFrom}
              onChange={(e) => setDateFrom(e.target.value)}
              className="h-9 rounded-md"
            />
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs text-muted-foreground">Дата по</Label>
            <Input
              type="date"
              value={dateTo}
              onChange={(e) => setDateTo(e.target.value)}
              className="h-9 rounded-md"
            />
          </div>
          <SelectFilter
            label="Тип эффекта"
            value={impactType}
            options={IMPACT_OPTIONS}
            onChange={mutate(setImpactType)}
            disabled={focusedProblem}
          />
          <div className="space-y-1.5">
            <Label className="text-xs text-muted-foreground">
              Код проблемы
            </Label>
            <Input
              value={problemCode}
              onChange={(e) => setProblemCode(e.target.value)}
              placeholder="введите код из задачи"
              disabled={focusedProblem}
              className="h-9 rounded-md"
            />
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs text-muted-foreground">ID проблемы</Label>
            <Input
              value={problemInstanceId}
              onChange={(e) => setProblemInstanceId(e.target.value)}
              placeholder="123"
              inputMode="numeric"
              className="h-9 rounded-md"
            />
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs text-muted-foreground">nmID</Label>
            <Input
              value={nmId}
              onChange={(e) => setNmId(e.target.value)}
              placeholder="Введите nmID"
              inputMode="numeric"
              disabled={focusedProblem}
              className="h-9 rounded-md"
            />
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs text-muted-foreground">ID действия</Label>
            <Input
              value={actionId}
              onChange={(e) => setActionId(e.target.value)}
              placeholder="123"
              inputMode="numeric"
              className="h-9 rounded-md"
            />
          </div>
          <div className="flex items-end gap-2 pb-2 xl:col-span-2">
            <Switch
              id="show-audit"
              checked={showAudit}
              onCheckedChange={setShowAudit}
            />
            <Label
              htmlFor="show-audit"
              className="cursor-pointer text-xs text-muted-foreground"
            >
              Показывать служебные события
            </Label>
          </div>
        </div>
      ) : null}
    </section>
  );
}

function TrackingFilterBar({
  value,
  onChange,
  dashboard,
}: {
  value: TrackingFilter;
  onChange: (value: TrackingFilter) => void;
  dashboard: ReturnType<typeof buildDashboard>;
}) {
  const counts: Record<TrackingFilter, number> = {
    all: dashboard.loaded,
    attention: dashboard.attention,
    missing_after: dashboard.loaded - dashboard.after,
    missing_evidence: dashboard.loaded - dashboard.evidence,
    measured: dashboard.measured,
    checker: dashboard.checker,
  };
  return (
    <div className="flex flex-wrap gap-1.5">
      {TRACKING_FILTERS.map((filter) => {
        const active = value === filter.value;
        return (
          <Button
            key={filter.value}
            type="button"
            variant={active ? "default" : "outline"}
            size="sm"
            className="h-8 rounded-md text-xs"
            onClick={() => onChange(filter.value)}
            title={filter.hint}
          >
            {filter.label}
            <span
              className={cn(
                "ml-1 rounded-sm px-1.5 py-0.5 font-mono text-[10px]",
                active ? "bg-primary-foreground/20" : "bg-muted",
              )}
            >
              {formatNumber(counts[filter.value] ?? 0)}
            </span>
          </Button>
        );
      })}
    </div>
  );
}

function ResultsKpis({
  dashboard,
}: {
  dashboard: ReturnType<typeof buildDashboard>;
}) {
  const waiting =
    dashboard.counts.pending_data + dashboard.counts.not_enough_data;
  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-6">
      <KpiCard
        icon={DatabaseZap}
        title="Событий найдено"
        value={formatNumber(dashboard.total)}
        hint={`На странице: ${formatNumber(dashboard.loaded)}`}
        tone="info"
      />
      <KpiCard
        icon={CheckCircle2}
        title="Улучшения"
        value={formatNumber(dashboard.counts.improved)}
        hint={`${dashboard.loaded ? pct(dashboard.counts.improved, dashboard.loaded) : 0}% от загруженных`}
        tone="success"
        trend="up"
      />
      <KpiCard
        icon={TimerReset}
        title="Ждут данных"
        value={formatNumber(waiting)}
        hint="Нет данных после действия или сравнения"
        tone={waiting > 0 ? "warning" : "success"}
      />
      <KpiCard
        icon={AlertTriangle}
        title="Ухудшения"
        value={formatNumber(dashboard.counts.worse)}
        hint="Нужно открыть событие и проверить причину"
        tone={dashboard.counts.worse > 0 ? "danger" : "default"}
        trend={dashboard.counts.worse > 0 ? "down" : undefined}
      />
      <KpiCard
        icon={ShieldCheck}
        title="Подтверждено"
        value={`${dashboard.confirmedPct}%`}
        hint={`${formatNumber(dashboard.confirmed)} подтверждено · ${formatNumber(dashboard.estimated)} оценка`}
        tone="default"
      />
      <KpiCard
        icon={BarChart3}
        title="Измеренный эффект"
        value={formatMoney(dashboard.counts.measured_amount)}
        hint={`${formatNumber(dashboard.counts.measured_count)} событий можно считать фактом`}
        tone="success"
      />
    </div>
  );
}

function ResultsCharts({
  dashboard,
}: {
  dashboard: ReturnType<typeof buildDashboard>;
}) {
  return (
    <div className="grid gap-3 xl:grid-cols-[1.25fr_0.75fr]">
      <Card className="rounded-md">
        <CardHeader className="p-4 pb-2">
          <CardTitle className="flex items-center gap-2 text-sm">
            <LineChart className="h-4 w-4 text-primary" />
            Динамика результата
          </CardTitle>
        </CardHeader>
        <CardContent className="p-4 pt-0">
          {dashboard.trend.length === 0 ? (
            <MiniEmpty text="Нет событий для графика" />
          ) : (
            <ChartContainer
              config={TREND_CHART_CONFIG}
              className="h-[260px] w-full"
            >
              <AreaChart data={dashboard.trend} margin={{ left: 4, right: 8 }}>
                <CartesianGrid vertical={false} strokeDasharray="3 3" />
                <XAxis
                  dataKey="label"
                  tickLine={false}
                  axisLine={false}
                  tickMargin={8}
                />
                <YAxis
                  allowDecimals={false}
                  tickLine={false}
                  axisLine={false}
                  width={32}
                />
                <ChartTooltip content={<ChartTooltipContent />} />
                <Area
                  type="monotone"
                  dataKey="total"
                  stroke="var(--color-total)"
                  fill="var(--color-total)"
                  fillOpacity={0.14}
                  strokeWidth={2}
                />
                <Area
                  type="monotone"
                  dataKey="improved"
                  stroke="var(--color-improved)"
                  fill="var(--color-improved)"
                  fillOpacity={0.18}
                  strokeWidth={2}
                />
                <Area
                  type="monotone"
                  dataKey="worse"
                  stroke="var(--color-worse)"
                  fill="var(--color-worse)"
                  fillOpacity={0.12}
                  strokeWidth={2}
                />
              </AreaChart>
            </ChartContainer>
          )}
        </CardContent>
      </Card>

      <Card className="rounded-md">
        <CardHeader className="p-4 pb-2">
          <CardTitle className="flex items-center gap-2 text-sm">
            <ListChecks className="h-4 w-4 text-primary" />
            Итог по статусам
          </CardTitle>
        </CardHeader>
        <CardContent className="grid gap-4 p-4 pt-0 md:grid-cols-[180px_1fr] xl:grid-cols-1 2xl:grid-cols-[180px_1fr]">
          {dashboard.outcomeChart.length === 0 ? (
            <MiniEmpty text="Нет данных" />
          ) : (
            <ChartContainer config={{}} className="h-[190px] w-full">
              <PieChart>
                <ChartTooltip content={<ChartTooltipContent hideLabel />} />
                <Pie
                  data={dashboard.outcomeChart}
                  dataKey="value"
                  nameKey="label"
                  innerRadius={52}
                  outerRadius={78}
                  paddingAngle={2}
                >
                  {dashboard.outcomeChart.map((entry) => (
                    <Cell key={entry.key} fill={entry.fill} />
                  ))}
                </Pie>
              </PieChart>
            </ChartContainer>
          )}
          <div className="space-y-2">
            {(Object.keys(OUTCOME_META) as ResultOutcomeKey[]).map((key) => {
              const value = dashboard.counts[key];
              return (
                <div
                  key={key}
                  className="flex items-center justify-between gap-2 text-sm"
                >
                  <div className="flex min-w-0 items-center gap-2">
                    <span
                      className="h-2.5 w-2.5 shrink-0 rounded-sm"
                      style={{ background: OUTCOME_META[key].color }}
                    />
                    <span className="truncate">{OUTCOME_META[key].label}</span>
                  </div>
                  <span className="font-mono tabular-nums">
                    {formatNumber(value)}
                  </span>
                </div>
              );
            })}
          </div>
        </CardContent>
      </Card>

      <Card className="rounded-md">
        <CardHeader className="p-4 pb-2">
          <CardTitle className="flex items-center gap-2 text-sm">
            <Layers3 className="h-4 w-4 text-primary" />
            Откуда пришли результаты
          </CardTitle>
        </CardHeader>
        <CardContent className="p-4 pt-0">
          {dashboard.modules.length === 0 ? (
            <MiniEmpty text="Нет модулей" />
          ) : (
            <ChartContainer
              config={MODULE_CHART_CONFIG}
              className="h-[260px] w-full"
            >
              <BarChart
                data={dashboard.modules}
                layout="vertical"
                margin={{ left: 10, right: 12 }}
              >
                <CartesianGrid horizontal={false} strokeDasharray="3 3" />
                <XAxis type="number" hide />
                <YAxis
                  dataKey="label"
                  type="category"
                  tickLine={false}
                  axisLine={false}
                  width={118}
                />
                <ChartTooltip content={<ChartTooltipContent />} />
                <Bar
                  dataKey="count"
                  fill="var(--color-count)"
                  radius={[0, 5, 5, 0]}
                  barSize={22}
                />
              </BarChart>
            </ChartContainer>
          )}
        </CardContent>
      </Card>

      <Card className="rounded-md">
        <CardHeader className="p-4 pb-2">
          <CardTitle className="flex items-center gap-2 text-sm">
            <ShieldCheck className="h-4 w-4 text-primary" />
            Качество записи результата
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4 p-4 pt-0">
          <TrackingMeter
            label="Снимок до действия"
            value={dashboard.before}
            total={dashboard.loaded}
            description="Снимок до действия сохранён"
          />
          <TrackingMeter
            label="Снимок после действия"
            value={dashboard.after}
            total={dashboard.loaded}
            description="Есть данные после действия"
          />
          <TrackingMeter
            label="Доказательства"
            value={dashboard.evidence}
            total={dashboard.loaded}
            description="Есть ведомость расчёта"
          />
          <TrackingMeter
            label="Точность"
            value={dashboard.confidence}
            total={dashboard.loaded}
            description="Есть уровень доверия к результату"
          />
        </CardContent>
      </Card>
    </div>
  );
}

function ProblemBreakdown({
  rows,
}: {
  rows: ReturnType<typeof buildProblemRows>;
}) {
  if (rows.length === 0) return null;
  return (
    <Card className="rounded-md">
      <CardHeader className="p-4 pb-2">
        <CardTitle className="flex items-center gap-2 text-sm">
          <Filter className="h-4 w-4 text-primary" />
          Частые причины
        </CardTitle>
      </CardHeader>
      <CardContent className="p-4 pt-0">
        <div className="grid gap-2 lg:grid-cols-2 2xl:grid-cols-3">
          {rows.map((row) => (
            <div
              key={row.code}
              className="rounded-md border bg-background px-3 py-2"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div
                    className="truncate text-sm font-medium"
                    title={row.code}
                  >
                    {problemCodeLabel(row.code)}
                  </div>
                  <div className="mt-1 text-[11px] text-muted-foreground">
                    Данные после действия: {pct(row.after, row.count)}%
                  </div>
                </div>
                <div className="font-mono text-lg font-semibold tabular-nums">
                  {formatNumber(row.count)}
                </div>
              </div>
              <div className="mt-2 grid grid-cols-3 gap-1 text-[11px]">
                <span className="rounded-sm bg-success/10 px-1.5 py-1 text-success">
                  + {formatNumber(row.improved)}
                </span>
                <span className="rounded-sm bg-destructive/10 px-1.5 py-1 text-destructive">
                  - {formatNumber(row.worse)}
                </span>
                <span className="rounded-sm bg-warning/10 px-1.5 py-1 text-warning">
                  ждут {formatNumber(row.pending)}
                </span>
              </div>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

function MiniEmpty({ text }: { text: string }) {
  return (
    <div className="flex h-[190px] items-center justify-center rounded-md border border-dashed text-sm text-muted-foreground">
      {text}
    </div>
  );
}

function ResultEventMobileCard({
  event,
  onOpen,
  onEvidence,
}: {
  event: unknown;
  onOpen: () => void;
  onEvidence: () => void;
}) {
  const r = isRecord(event) ? event : {};
  const outcome = classifyOutcome(event);
  const trust = classifyTrust(event);
  const moduleKey = eventModule(event);
  const eventType = pick<string>(r, ["event_type", "type", "event"]);
  const problemCode = eventProblemCode(event);
  const nmId = eventNmId(event);
  const vendor = eventVendorCode(event);
  const impact = pick<string>(r, ["impact_type"]);
  const measured = measuredAmount(event);
  const links = buildContextLinks(event).slice(0, 2);
  return (
    <div className="rounded-md border bg-card p-3 lg:hidden">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 space-y-1">
          <div className="flex flex-wrap gap-1.5">
            <ResultBadge value={outcome} />
            <TrustBadge
              value={
                trust === "confirmed"
                  ? "confirmed"
                  : trust === "estimated"
                    ? "estimated"
                    : "provisional"
              }
            />
            {impact ? <ImpactBadge value={impact} /> : null}
          </div>
          <div className="line-clamp-2 text-sm font-medium">
            {eventTitle(event)}
          </div>
          <div className="text-xs text-muted-foreground">
            {humanizeModule(moduleKey)} · {humanizeEventType(eventType).label}
          </div>
        </div>
        <div className="shrink-0 text-right text-xs text-muted-foreground">
          {fmtDateTime(eventCreatedAt(event))}
        </div>
      </div>
      <div className="mt-3 grid grid-cols-2 gap-2 text-xs">
        <InfoPill
          label="До действия"
          value={hasSnapshot(event, "before_snapshot") ? "есть" : "нет"}
        />
        <InfoPill
          label="После действия"
          value={problemResultHasAfterData(event) ? "есть" : "нет"}
        />
        <InfoPill
          label="Доказательства"
          value={hasProof(event) ? "есть" : "нет"}
        />
        <InfoPill label="Точность" value={formatConfidenceValue(event)} />
      </div>
      <ExperimentEvidence event={event} />
      <div className="mt-3 flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
        {problemCode ? (
          <Badge variant="outline" title={problemCode}>
            {problemCodeLabel(problemCode)}
          </Badge>
        ) : null}
        {nmId ? <Badge variant="outline">nmID {nmId}</Badge> : null}
        {vendor ? <Badge variant="outline">{vendor}</Badge> : null}
        {isMeasuredEffect(event) && measured != null ? (
          <Badge className="bg-success text-success-foreground">
            {formatMoney(measured)}
          </Badge>
        ) : null}
      </div>
      <div className="mt-3 flex flex-wrap gap-1.5 border-t pt-2">
        <Button size="sm" variant="outline" className="h-8" onClick={onOpen}>
          <FileSearch className="h-3.5 w-3.5" />
          Детали
        </Button>
        <Button
          size="sm"
          variant="outline"
          className="h-8"
          onClick={onEvidence}
          disabled={!ledgerFromEvent(event)}
        >
          <ShieldCheck className="h-3.5 w-3.5" />
          Доказательства
        </Button>
        {links.map((link) =>
          link.disabled ? null : (
            <Button
              key={link.key}
              size="sm"
              variant="ghost"
              className="h-8"
              asChild
            >
              <Link
                to={link.to as any}
                params={link.params as any}
                search={link.search as any}
              >
                {link.label}
                <ExternalLink className="h-3.5 w-3.5" />
              </Link>
            </Button>
          ),
        )}
      </div>
    </div>
  );
}

function InfoPill({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-sm border bg-background px-2 py-1">
      <div className="text-[10px] uppercase text-muted-foreground">{label}</div>
      <div className="font-medium">{value}</div>
    </div>
  );
}

function experimentEvidencePayload(
  event: unknown,
): Record<string, unknown> | null {
  const r = isRecord(event) ? event : {};
  const payload =
    [r.payload, r.data, r.meta, r.evaluation].find(isRecord) ?? {};
  const experiment =
    pick<Record<string, unknown>>(payload, [
      "experiment",
      "experiment_evidence",
      "experiment_result",
    ]) ?? payload;
  if (!isRecord(experiment)) return null;
  const hasExperimentEvidence = [
    "baseline_window",
    "post_window",
    "primary_result",
    "data_sufficiency",
    "confounders",
  ].some((key) => experiment[key] != null);
  return hasExperimentEvidence ? experiment : null;
}

function experimentValue(value: unknown): string {
  if (value == null || value === "") return "—";
  if (Array.isArray(value)) return value.length ? value.join(", ") : "—";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function ExperimentEvidence({ event }: { event: unknown }) {
  const payload = experimentEvidencePayload(event);
  if (!payload) return null;
  const baseline_window = payload.baseline_window;
  const post_window = payload.post_window;
  const primary_result = payload.primary_result;
  const data_sufficiency = payload.data_sufficiency;
  const confounders = payload.confounders;
  const rows = [
    ["До", baseline_window],
    ["После", post_window],
    ["Метрика", primary_result],
    ["Достаточность", data_sufficiency],
    ["Факторы", confounders],
  ];
  return (
    <div className="mt-2 rounded-md border bg-warning/5 p-2 text-[11px]">
      <div className="mb-1 font-medium text-warning">
        Корреляция, а не гарантия
      </div>
      <div className="grid gap-1 sm:grid-cols-2">
        {rows.map(([label, value]) => (
          <div key={label} className="min-w-0">
            <span className="text-muted-foreground">{label}: </span>
            <span className="break-words">{experimentValue(value)}</span>
          </div>
        ))}
      </div>
      <div className="mt-1 text-muted-foreground">
        {PROBLEM_RESULT_CORRELATION_DISCLAIMER}
      </div>
    </div>
  );
}

function ResultsEventLedger({
  items,
  rawCount,
  total,
  offset,
  pageSize,
  page,
  pageCount,
  onPageChange,
  onPageSizeChange,
  onOpen,
  onEvidence,
  isFetching,
}: {
  items: unknown[];
  rawCount: number;
  total: number;
  offset: number;
  pageSize: number;
  page: number;
  pageCount: number;
  onPageChange: (page: number) => void;
  onPageSizeChange: (size: number) => void;
  onOpen: (event: unknown) => void;
  onEvidence: (event: unknown) => void;
  isFetching: boolean;
}) {
  const rangeStart = total === 0 ? 0 : offset + 1;
  const rangeEnd = Math.min(offset + rawCount, total);
  return (
    <Card className="rounded-md">
      <CardHeader className="flex flex-row items-start justify-between gap-3 p-4 pb-2">
        <div>
          <CardTitle className="flex items-center gap-2 text-sm">
            <Clock3 className="h-4 w-4 text-primary" />
            Журнал событий
          </CardTitle>
          <div className="mt-1 text-xs text-muted-foreground">
            Показано {formatNumber(rangeStart)}-{formatNumber(rangeEnd)} из{" "}
            {formatNumber(total)}. В списке: {formatNumber(items.length)} из{" "}
            {formatNumber(rawCount)} загруженных.
          </div>
        </div>
        {isFetching ? (
          <Badge variant="outline" className="gap-1">
            <RefreshCw className="h-3 w-3 animate-spin" />
            Обновление
          </Badge>
        ) : null}
      </CardHeader>
      <CardContent className="space-y-3 p-4 pt-0">
        {items.length === 0 ? (
          <EmptyState
            variant="no_data"
            title="Событий по выбранным фильтрам нет"
            hint="Измените период, модуль, статус результата или быстрый отбор."
          />
        ) : (
          <>
            <div className="space-y-2 lg:hidden">
              {items.map((event, idx) => (
                <ResultEventMobileCard
                  key={pick(event, ["id"]) ?? idx}
                  event={event}
                  onOpen={() => onOpen(event)}
                  onEvidence={() => onEvidence(event)}
                />
              ))}
            </div>
            <div className="hidden overflow-hidden rounded-md border lg:block">
              <Table>
                <TableHeader>
                  <TableRow className="bg-muted/40">
                    <TableHead className="w-[132px]">Дата</TableHead>
                    <TableHead>Товар / проблема</TableHead>
                    <TableHead className="w-[190px]">Статус</TableHead>
                    <TableHead className="w-[180px]">Проверка записи</TableHead>
                    <TableHead className="w-[160px] text-right">
                      Эффект
                    </TableHead>
                    <TableHead className="w-[180px] text-right">
                      Действия
                    </TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {items.map((event, idx) => (
                    <ResultEventTableRow
                      key={pick(event, ["id"]) ?? idx}
                      event={event}
                      onOpen={() => onOpen(event)}
                      onEvidence={() => onEvidence(event)}
                    />
                  ))}
                </TableBody>
              </Table>
            </div>
          </>
        )}

        <div className="flex flex-col gap-3 border-t pt-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <span>Строк:</span>
            <Select
              value={String(pageSize)}
              onValueChange={(next) => onPageSizeChange(Number(next))}
            >
              <SelectTrigger className="h-8 w-[92px] rounded-md">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {PAGE_LIMITS.map((limit) => (
                  <SelectItem key={limit} value={String(limit)}>
                    {limit}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="flex items-center justify-end gap-2">
            <Button
              variant="outline"
              size="sm"
              className="h-8 rounded-md"
              disabled={page <= 1}
              onClick={() => onPageChange(Math.max(1, page - 1))}
            >
              <ChevronLeft className="h-4 w-4" />
              Назад
            </Button>
            <div className="min-w-[110px] text-center text-xs text-muted-foreground">
              Стр. {formatNumber(page)} / {formatNumber(pageCount)}
            </div>
            <Button
              variant="outline"
              size="sm"
              className="h-8 rounded-md"
              disabled={page >= pageCount || offset + rawCount >= total}
              onClick={() => onPageChange(Math.min(pageCount, page + 1))}
            >
              Вперёд
              <ChevronRight className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function ResultEventTableRow({
  event,
  onOpen,
  onEvidence,
}: {
  event: unknown;
  onOpen: () => void;
  onEvidence: () => void;
}) {
  const r = isRecord(event) ? event : {};
  const outcome = classifyOutcome(event);
  const trust = classifyTrust(event);
  const moduleKey = eventModule(event);
  const eventType = pick<string>(r, ["event_type", "type", "event"]);
  const problemCode = eventProblemCode(event);
  const nmId = eventNmId(event);
  const vendor = eventVendorCode(event);
  const impact = pick<string>(r, ["impact_type"]);
  const measured = measuredAmount(event);
  const hasLedger = !!ledgerFromEvent(event);
  const links = buildContextLinks(event).slice(0, 1);
  const message = pick<string>(r, ["message"]);

  return (
    <TableRow>
      <TableCell className="align-top text-xs text-muted-foreground">
        <div className="font-mono tabular-nums">
          {fmtDateTime(eventCreatedAt(event))}
        </div>
        <div className="mt-1">{humanizeModule(moduleKey)}</div>
      </TableCell>
      <TableCell className="align-top">
        <button
          type="button"
          onClick={onOpen}
          className="block max-w-[520px] text-left text-sm font-medium hover:text-primary"
        >
          <span className="line-clamp-2">{eventTitle(event)}</span>
        </button>
        <div className="mt-1 flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
          <span>{humanizeEventType(eventType).label}</span>
          {problemCode ? (
            <span title={problemCode}>· {problemCodeLabel(problemCode)}</span>
          ) : null}
          {nmId ? <span>· nmID {nmId}</span> : null}
          {vendor ? <span>· {vendor}</span> : null}
        </div>
        {message ? (
          <div className="mt-1 line-clamp-1 text-xs text-muted-foreground">
            {humanizeMessage(message)}
          </div>
        ) : null}
        <ExperimentEvidence event={event} />
      </TableCell>
      <TableCell className="align-top">
        <div className="flex flex-wrap gap-1.5">
          <ResultBadge value={outcome} />
          <TrustBadge
            value={
              trust === "confirmed"
                ? "confirmed"
                : trust === "estimated"
                  ? "estimated"
                  : "provisional"
            }
          />
          {impact ? <ImpactBadge value={impact} /> : null}
        </div>
        <div className="mt-1 text-[11px] text-muted-foreground">
          точность: {formatConfidenceValue(event)}
        </div>
      </TableCell>
      <TableCell className="align-top">
        <div className="grid grid-cols-2 gap-1 text-[11px]">
          <TrackingChip ok={hasSnapshot(event, "before_snapshot")} label="До" />
          <TrackingChip ok={problemResultHasAfterData(event)} label="После" />
          <TrackingChip ok={hasProof(event)} label="Расчёт" />
          <TrackingChip
            ok={problemResultHasConfidence(event)}
            label="Точность"
          />
        </div>
      </TableCell>
      <TableCell className="align-top text-right">
        {isMeasuredEffect(event) && measured != null ? (
          <div className="font-mono text-sm font-semibold text-success">
            {measured > 0 ? "+" : ""}
            {formatMoney(measured)}
          </div>
        ) : (
          <Badge variant="outline" className="text-[10px]">
            ожидаемый
          </Badge>
        )}
      </TableCell>
      <TableCell className="align-top">
        <div className="flex justify-end gap-1.5">
          <Button
            size="sm"
            variant="outline"
            className="h-8 rounded-md"
            onClick={onOpen}
          >
            <FileSearch className="h-3.5 w-3.5" />
          </Button>
          <Button
            size="sm"
            variant="outline"
            className="h-8 rounded-md"
            onClick={onEvidence}
            disabled={!hasLedger}
          >
            <ShieldCheck className="h-3.5 w-3.5" />
          </Button>
          {links.map((link) =>
            link.disabled ? null : (
              <Button
                key={link.key}
                size="sm"
                variant="ghost"
                className="h-8 rounded-md"
                asChild
              >
                <Link
                  to={link.to as any}
                  params={link.params as any}
                  search={link.search as any}
                >
                  <ExternalLink className="h-3.5 w-3.5" />
                </Link>
              </Button>
            ),
          )}
        </div>
      </TableCell>
    </TableRow>
  );
}

function TrackingChip({ ok, label }: { ok: boolean; label: string }) {
  return (
    <span
      className={cn(
        "rounded-sm border px-1.5 py-1 text-center font-medium",
        ok
          ? "border-success/30 bg-success/10 text-success"
          : "border-warning/30 bg-warning/10 text-warning",
      )}
    >
      {label}: {ok ? "есть" : "нет"}
    </span>
  );
}

function ResultsPage() {
  const routeSearch = Route.useSearch();
  const navigate = useNavigate({ from: Route.fullPath });
  const { activeId } = useAccounts();

  const routeProblemInstanceId = routeFilter(routeSearch.problem_instance_id);
  const routeHasProblemInstance = Boolean(routeProblemInstanceId);

  const [actionId, setActionIdState] = useState(
    routeFilter(routeSearch.action_id),
  );
  const [problemCode, setProblemCodeState] = useState(
    routeHasProblemInstance ? "" : routeFilter(routeSearch.problem_code),
  );
  const [problemInstanceId, setProblemInstanceIdState] = useState(
    routeProblemInstanceId,
  );
  const [nmId, setNmIdState] = useState(
    routeHasProblemInstance ? "" : routeFilter(routeSearch.nm_id),
  );
  const [sourceModule, setSourceModuleState] = useState(
    routeFilter(routeSearch.source_module),
  );
  const [eventType, setEventTypeState] = useState(
    routeFilter(routeSearch.event_type),
  );
  const [resultStatus, setResultStatusState] = useState(
    routeFilter(routeSearch.result_status),
  );
  const [trustState, setTrustStateState] = useState(
    routeFilter(routeSearch.trust_state),
  );
  const [impactType, setImpactTypeState] = useState(
    routeFilter(routeSearch.impact_type),
  );
  const [dateFrom, setDateFromState] = useState(
    routeFilter(routeSearch.date_from),
  );
  const [dateTo, setDateToState] = useState(routeFilter(routeSearch.date_to));
  const [search, setSearchState] = useState(routeFilter(routeSearch.search));
  const [page, setPageState] = useState(positiveInt(routeSearch.page, 1));
  const [pageSize, setPageSizeState] = useState(
    allowedLimit(routeSearch.limit),
  );
  const [trackingFilter, setTrackingFilter] = useState<TrackingFilter>("all");
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [showAudit, setShowAudit] = useState(false);
  const [drawerEvent, setDrawerEvent] = useState<unknown>(null);
  const [evidenceLedger, setEvidenceLedger] = useState<unknown>(null);

  const setPage = (value: number) => setPageState(Math.max(1, value));
  const resetPage = () => setPageState(1);
  const setActionId = (value: string) => {
    setActionIdState(value);
    resetPage();
  };
  const setProblemCode = (value: string) => {
    setProblemCodeState(value);
    resetPage();
  };
  const setProblemInstanceId = (value: string) => {
    setProblemInstanceIdState(value);
    resetPage();
  };
  const setNmId = (value: string) => {
    setNmIdState(value);
    resetPage();
  };
  const setSourceModule = (value: string) => {
    setSourceModuleState(value);
    resetPage();
  };
  const setEventType = (value: string) => {
    setEventTypeState(value);
    resetPage();
  };
  const setResultStatus = (value: string) => {
    setResultStatusState(value);
    resetPage();
  };
  const setTrustState = (value: string) => {
    setTrustStateState(value);
    resetPage();
  };
  const setImpactType = (value: string) => {
    setImpactTypeState(value);
    resetPage();
  };
  const setDateFrom = (value: string) => {
    setDateFromState(value);
    resetPage();
  };
  const setDateTo = (value: string) => {
    setDateToState(value);
    resetPage();
  };
  const setSearch = (value: string) => {
    setSearchState(value);
    resetPage();
  };
  const setPageSize = (value: number) => {
    setPageSizeState(value);
    setPageState(1);
  };

  useEffect(() => {
    const nextProblemInstanceId = routeFilter(routeSearch.problem_instance_id);
    const focused = Boolean(nextProblemInstanceId);
    setActionIdState(routeFilter(routeSearch.action_id));
    setProblemCodeState(focused ? "" : routeFilter(routeSearch.problem_code));
    setProblemInstanceIdState(nextProblemInstanceId);
    setNmIdState(focused ? "" : routeFilter(routeSearch.nm_id));
    setSourceModuleState(routeFilter(routeSearch.source_module));
    setEventTypeState(routeFilter(routeSearch.event_type));
    setResultStatusState(routeFilter(routeSearch.result_status));
    setTrustStateState(routeFilter(routeSearch.trust_state));
    setImpactTypeState(routeFilter(routeSearch.impact_type));
    setDateFromState(routeFilter(routeSearch.date_from));
    setDateToState(routeFilter(routeSearch.date_to));
    setSearchState(routeFilter(routeSearch.search));
    setPageState(positiveInt(routeSearch.page, 1));
    setPageSizeState(allowedLimit(routeSearch.limit));
  }, [
    routeSearch.action_id,
    routeSearch.problem_code,
    routeSearch.problem_instance_id,
    routeSearch.nm_id,
    routeSearch.source_module,
    routeSearch.event_type,
    routeSearch.result_status,
    routeSearch.trust_state,
    routeSearch.impact_type,
    routeSearch.date_from,
    routeSearch.date_to,
    routeSearch.search,
    routeSearch.page,
    routeSearch.limit,
  ]);

  useEffect(() => {
    const next: Record<string, string | undefined> = {
      action_id: actionId.trim() || undefined,
      problem_code: problemCode.trim() || undefined,
      problem_instance_id: problemInstanceId.trim() || undefined,
      nm_id: nmId.trim() || undefined,
      source_module: sourceModule.trim() || undefined,
      event_type: eventType.trim() || undefined,
      result_status: resultStatus.trim() || undefined,
      trust_state: trustState.trim() || undefined,
      impact_type: impactType.trim() || undefined,
      date_from: dateFrom.trim() || undefined,
      date_to: dateTo.trim() || undefined,
      search: search.trim() || undefined,
      page: page > 1 ? String(page) : undefined,
      limit: pageSize !== DEFAULT_LIMIT ? String(pageSize) : undefined,
    };
    const same =
      (routeSearch.action_id ?? undefined) === next.action_id &&
      (routeSearch.problem_code ?? undefined) === next.problem_code &&
      (routeSearch.problem_instance_id ?? undefined) ===
        next.problem_instance_id &&
      (routeSearch.nm_id ?? undefined) === next.nm_id &&
      (routeSearch.source_module ?? undefined) === next.source_module &&
      (routeSearch.event_type ?? undefined) === next.event_type &&
      (routeSearch.result_status ?? undefined) === next.result_status &&
      (routeSearch.trust_state ?? undefined) === next.trust_state &&
      (routeSearch.impact_type ?? undefined) === next.impact_type &&
      (routeSearch.date_from ?? undefined) === next.date_from &&
      (routeSearch.date_to ?? undefined) === next.date_to &&
      (routeSearch.search ?? undefined) === next.search &&
      (routeSearch.page ?? undefined) === next.page &&
      (routeSearch.limit ?? undefined) === next.limit;
    if (same) return;
    navigate({
      search: (prev: any) => ({ ...prev, ...next }),
      replace: true,
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    actionId,
    problemCode,
    problemInstanceId,
    nmId,
    sourceModule,
    eventType,
    resultStatus,
    trustState,
    impactType,
    dateFrom,
    dateTo,
    search,
    page,
    pageSize,
  ]);

  const focusedProblemInstanceId = problemInstanceId.trim();
  const hasFocusedProblemInstance = Boolean(focusedProblemInstanceId);
  const offset = (page - 1) * pageSize;

  const resultFilters = useMemo(
    () => ({
      limit: pageSize,
      offset,
      ...(actionId.trim() ? { action_id: actionId.trim() } : {}),
      ...(!hasFocusedProblemInstance && problemCode.trim()
        ? { problem_code: problemCode.trim() }
        : {}),
      ...(!hasFocusedProblemInstance && nmId.trim()
        ? { nm_id: nmId.trim() }
        : {}),
      ...(!hasFocusedProblemInstance && sourceModule.trim()
        ? { source_module: sourceModule.trim() }
        : {}),
      ...(eventType.trim() ? { event_type: eventType.trim() } : {}),
      ...(resultStatus.trim() ? { result_status: resultStatus.trim() } : {}),
      ...(!hasFocusedProblemInstance && trustState.trim()
        ? { trust_state: trustState.trim() }
        : {}),
      ...(!hasFocusedProblemInstance && impactType.trim()
        ? { impact_type: impactType.trim() }
        : {}),
      ...(dateFrom.trim() ? { date_from: dateFrom.trim() } : {}),
      ...(dateTo.trim() ? { date_to: dateTo.trim() } : {}),
      ...(search.trim() ? { search: search.trim() } : {}),
    }),
    [
      actionId,
      dateFrom,
      dateTo,
      eventType,
      hasFocusedProblemInstance,
      impactType,
      nmId,
      offset,
      pageSize,
      problemCode,
      resultStatus,
      search,
      sourceModule,
      trustState,
    ],
  );

  const listQ = useQuery({
    queryKey: ["portal-results", activeId, resultFilters],
    queryFn: () => fetchResults(activeId, resultFilters),
    enabled: !!activeId && !hasFocusedProblemInstance,
    staleTime: 45_000,
  });
  const problemQ = useQuery({
    queryKey: [
      "portal-problem-results",
      focusedProblemInstanceId,
      pageSize,
      offset,
    ],
    queryFn: () =>
      fetchProblemResults(focusedProblemInstanceId, {
        limit: pageSize,
        offset,
      }),
    enabled: !!activeId && hasFocusedProblemInstance,
    staleTime: 45_000,
  });
  const activeQ = hasFocusedProblemInstance ? problemQ : listQ;
  const { data, isLoading, error, refetch, isFetching } = activeQ;

  const obj = useMemo<Record<string, unknown>>(
    () => (data && isRecord(data) ? data : {}),
    [data],
  );
  const rawItems = useMemo(() => dataItems(data), [data]);
  const backendTotal = Number(obj.total ?? rawItems.length);
  const total = Number.isFinite(backendTotal) ? backendTotal : rawItems.length;
  const pageCount = Math.max(1, Math.ceil(total / pageSize));

  useEffect(() => {
    if (total > 0 && page > pageCount) setPage(pageCount);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page, pageCount, total]);

  const { operationalItems, auditCount } = useMemo(() => {
    let audit = 0;
    const items: unknown[] = [];
    for (const item of rawItems) {
      if (matchesAuditEvent(item)) {
        audit += 1;
        if (!showAudit) continue;
      }
      items.push(item);
    }
    return { operationalItems: items, auditCount: audit };
  }, [rawItems, showAudit]);

  const localSearchedItems = useMemo(() => {
    if (!hasFocusedProblemInstance) return operationalItems;
    return operationalItems.filter((item) =>
      matchesFocusedProblemFilters(item, {
        actionId,
        eventType,
        resultStatus,
        dateFrom,
        dateTo,
        search,
      }),
    );
  }, [
    actionId,
    dateFrom,
    dateTo,
    eventType,
    hasFocusedProblemInstance,
    operationalItems,
    resultStatus,
    search,
  ]);

  const filteredItems = useMemo(
    () =>
      localSearchedItems.filter((item) =>
        matchesTrackingFilter(item, trackingFilter),
      ),
    [localSearchedItems, trackingFilter],
  );

  const dashboard = useMemo(
    () => buildDashboard(filteredItems, total),
    [filteredItems, total],
  );

  const productContextNmId = hasFocusedProblemInstance
    ? undefined
    : routeSearch.nm_id;

  function clearFilters() {
    setActionIdState("");
    setProblemCodeState("");
    setProblemInstanceIdState("");
    setNmIdState("");
    setSourceModuleState("");
    setEventTypeState("");
    setResultStatusState("");
    setTrustStateState("");
    setImpactTypeState("");
    setDateFromState("");
    setDateToState("");
    setSearchState("");
    setTrackingFilter("all");
    setPageState(1);
  }

  function openEvidence(event: unknown) {
    const ledger = ledgerFromEvent(event);
    if (ledger) setEvidenceLedger(ledger);
  }

  return (
    <PageShell>
      <PageHeader
        title="Результаты"
        subtitle="Что изменилось после действий: факт, ожидание данных, доказательства и переход к задаче или товару."
        actions={
          <Button
            size="sm"
            variant="outline"
            className="rounded-md"
            onClick={() => refetch()}
            disabled={!activeId || isFetching}
          >
            <RefreshCw
              className={cn("h-3.5 w-3.5", isFetching && "animate-spin")}
            />
            Обновить
          </Button>
        }
      />

      <div className="mt-4 space-y-4">
        <ActionCenterReturnLink
          action_id={routeSearch.action_id}
          problem_instance_id={routeSearch.problem_instance_id}
          nm_id={productContextNmId}
        />

        {!activeId ? <NoAccountSelected /> : null}

        {activeId ? (
          <>
            <div className="flex items-start gap-2 rounded-md border bg-card px-3 py-2 text-xs text-muted-foreground">
              <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-warning" />
              <span>{PROBLEM_RESULT_CORRELATION_DISCLAIMER}</span>
            </div>

            <ResultsFilterPanel
              search={search}
              setSearch={setSearch}
              dateFrom={dateFrom}
              setDateFrom={setDateFrom}
              dateTo={dateTo}
              setDateTo={setDateTo}
              sourceModule={sourceModule}
              setSourceModule={setSourceModule}
              eventType={eventType}
              setEventType={setEventType}
              resultStatus={resultStatus}
              setResultStatus={setResultStatus}
              trustState={trustState}
              setTrustState={setTrustState}
              impactType={impactType}
              setImpactType={setImpactType}
              problemCode={problemCode}
              setProblemCode={setProblemCode}
              problemInstanceId={problemInstanceId}
              setProblemInstanceId={setProblemInstanceId}
              nmId={nmId}
              setNmId={setNmId}
              actionId={actionId}
              setActionId={setActionId}
              focusedProblem={hasFocusedProblemInstance}
              showAdvanced={showAdvanced}
              setShowAdvanced={setShowAdvanced}
              showAudit={showAudit}
              setShowAudit={setShowAudit}
              onClear={clearFilters}
            />

            {auditCount > 0 && !showAudit ? (
              <div className="text-right text-xs text-muted-foreground">
                Служебные события скрыты: {formatNumber(auditCount)}
              </div>
            ) : null}

            {error ? (
              <EmptyState
                variant="error"
                title="Не удалось загрузить результаты"
                hint={sellerSafeMessage(
                  error,
                  "Проверьте подключение или повторите попытку.",
                )}
                onRetry={() => refetch()}
                retryLabel={isFetching ? "Повтор…" : "Повторить"}
              />
            ) : null}

            {isLoading && !error ? (
              <LoadingSkeleton variant="page" rows={6} />
            ) : null}

            {!isLoading && !error ? (
              <>
                <ResultsKpis dashboard={dashboard} />

                <div className="flex flex-col gap-2 rounded-md border bg-card p-3 lg:flex-row lg:items-center lg:justify-between">
                  <div>
                    <div className="text-sm font-medium">Быстрый отбор</div>
                    <div className="text-xs text-muted-foreground">
                      Основные фильтры выше отправляются на сервер; быстрый
                      отбор работает по текущей странице.
                    </div>
                  </div>
                  <TrackingFilterBar
                    value={trackingFilter}
                    onChange={setTrackingFilter}
                    dashboard={buildDashboard(localSearchedItems, total)}
                  />
                </div>

                {rawItems.length === 0 ? (
                  <EmptyState
                    variant="no_data"
                    title="Результатов пока нет"
                    hint="Закройте задачу, запустите перепроверку карточки или выберите другой период."
                  />
                ) : (
                  <>
                    <ResultsCharts dashboard={dashboard} />
                    <ProblemBreakdown rows={dashboard.problems} />
                    <ResultsEventLedger
                      items={filteredItems}
                      rawCount={localSearchedItems.length}
                      total={total}
                      offset={offset}
                      pageSize={pageSize}
                      page={page}
                      pageCount={pageCount}
                      onPageChange={setPage}
                      onPageSizeChange={setPageSize}
                      onOpen={setDrawerEvent}
                      onEvidence={openEvidence}
                      isFetching={isFetching}
                    />
                  </>
                )}
              </>
            ) : null}
          </>
        ) : null}
      </div>

      <ResultDetailDrawer
        open={!!drawerEvent}
        onOpenChange={(open) => {
          if (!open) setDrawerEvent(null);
        }}
        event={drawerEvent ?? {}}
      />

      <EvidenceDrawer
        open={!!evidenceLedger}
        onOpenChange={(open) => {
          if (!open) setEvidenceLedger(null);
        }}
        ledger={evidenceLedger}
      />
    </PageShell>
  );
}
