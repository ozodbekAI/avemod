// @ts-nocheck
import { type ChangeEvent, type ReactNode, useEffect, useMemo, useState } from "react";
import { Link } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowRight,
  AlertTriangle,
  CheckCircle2,
  Download,
  FileUp,
  RefreshCw,
  Search,
  ShieldAlert,
  Tags,
  Wrench,
} from "lucide-react";
import { toast } from "sonner";

import { useAuth } from "@/lib/auth-context";
import {
  api,
  type DataQualityIssue,
  type DataQualityResolutionContext,
  type GuidedFixActionResponse,
  type GuidedFixActionType,
  type MDataBlocker,
} from "@/lib/api";
import { API_ENDPOINTS } from "@/lib/endpoints";
import { fetchProblemResults, type PortalResultEventsPage } from "@/lib/portal";
import { formatMoney, formatNumber } from "@/lib/format";
import { evidenceFrom } from "@/lib/evidence";
import { moneyTrustFrom } from "@/lib/money-trust";
import {
  problemResultContractValue,
  problemResultEvents,
  problemResultSummaryFromPage,
} from "@/lib/problem-results";
import {
  EVIDENCE_BUTTON_LABEL,
  problemCodeLabel,
  problemResultStatusLabel,
  problemStatusLabel,
  problemTrustLabel,
} from "@/lib/problem-ux-copy";
import { EvidenceDrawer } from "@/components/EvidenceDrawer";
import { MoneyTrustBadge } from "@/components/MoneyTrustBadge";
import { EmptyState } from "@/components/shell/EmptyState";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ProblemEmptyState, SellerProblemLifecycle } from "@/components/problem/SellerProblemUX";
import type { ActionCenterSearch } from "@/hooks/action-center/useActionCenterFilters";
import { useIsMobile } from "@/hooks/use-mobile";
import {
  anyRowHasMissingFields,
  formatCellText,
  formatConfidenceValue,
  formatRowStatus,
  normalizeAffectedRows,
  searchAffectedRows,
  type AffectedRowView,
} from "@/lib/data-fix/affected-rows";

type WorkbenchProps = {
  issueId: number | null;
  fallbackBlocker?: MDataBlocker | null;
  open: boolean;
  onOpenChange?: (open: boolean) => void;
  onChanged?: () => void;
  onLocalActionSaved?: (payload: ActionPayload) => void | Promise<void>;
  inline?: boolean;
  hideHeader?: boolean;
  className?: string;
};

type ActionPayload = {
  action_type: GuidedFixActionType;
  inputs?: Record<string, unknown>;
  comment?: string | null;
};

const OWNER_COPY: Record<string, string> = {
  user: "Исправляет пользователь",
  system: "Проверяет система",
  admin: "Нужна проверка администратора",
  mixed: "Пользователь + система",
  business: "Бизнес-решение",
};

const COMPONENT_COPY: Record<string, string> = {
  upload_cost_file: "Загрузить себестоимость",
  cost_inline_editor: "Заполнить в таблице",
  map_sku: "Привязать SKU",
  sku_mapping: "Привязать SKU",
  classify_expense: "Разнести расход",
  expense_classification: "Разнести расход",
  rerun_sync: "Повторить синхронизацию",
  sync_recheck: "Повторить синхронизацию",
  open_finance_reconciliation: "Проверить сверку финансов",
  wait_for_wb_report: "Дождаться отчета WB",
  review_price: "Проверить цену",
  open_card_mapping: "Привязать карточку",
  card_mapping: "Проверить карточку",
  stock_decision: "Разобрать остаток",
  ads_allocation_status: "Проверить рекламу",
  admin_investigation: "Передать администратору",
};

const FIELD_LABELS: Record<string, string> = {
  _source: "Источник",
  id: "ID",
  stat_date: "Дата",
  code: "Код проблемы",
  sku_id: "SKU",
  sku: "SKU",
  mapped_sku_id: "SKU для привязки",
  nm_id: "Артикул WB",
  vendor_code: "Артикул продавца",
  barcode: "Баркод",
  amount: "Сумма",
  final_revenue: "Выручка",
  current_price: "Текущая цена",
  cost_price: "Себестоимость",
  seller_other_expense: "Прочие расходы",
  title: "Название",
  closing_stock_qty: "Остаток",
  sale_rows: "Продажи",
  final_sales_qty: "Продано, шт.",
  revenue_impact: "Затронутая выручка",
  expense_category: "Категория расхода",
  classification_reason: "Комментарий к категории",
  status: "Статус",
  source_table: "Таблица-источник",
  source_endpoint: "API-источник",
  row_count: "Строк",
};

const EXPENSE_CATEGORY_LABELS: Record<string, string> = {
  logistics: "Логистика",
  commission: "Комиссия WB",
  storage: "Хранение",
  penalty: "Штраф",
  deduction: "Удержание",
  marketing: "Маркетинг / реклама",
  other_wb_expense: "Прочий расход WB",
};

function fieldLabel(key: string): string {
  return FIELD_LABELS[key] ?? key.replace(/_/g, " ");
}

function displayValue(value: unknown): string {
  if (value == null || value === "") return "-";
  if (typeof value === "number") return Number.isFinite(value) ? formatNumber(value) : "-";
  if (typeof value === "boolean") return value ? "да" : "нет";
  if (typeof value === "string") return value;
  return "структурированные данные";
}

function objectText(value: unknown): string {
  if (value == null || value === "") return "-";
  if (typeof value === "number") return Number.isFinite(value) ? formatNumber(value) : "-";
  if (typeof value === "string") return value;
  if (typeof value === "boolean") return value ? "да" : "нет";
  if (Array.isArray(value)) return value.map(displayValue).join(", ");
  if (typeof value === "object") {
    return Object.entries(value as Record<string, unknown>)
      .slice(0, 4)
      .map(([key, item]) => `${key}: ${displayValue(item)}`)
      .join("; ");
  }
  return String(value);
}

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback;
}

const CANONICAL_COLUMNS: { key: keyof AffectedRowView; label: string }[] = [
  { key: "nm_id", label: "nmID" },
  { key: "vendor_code", label: "Артикул продавца" },
  { key: "barcode", label: "Баркод" },
  { key: "source", label: "Источник" },
  { key: "current_value", label: "Сейчас" },
  { key: "missing_or_invalid_value", label: "Что не так" },
  { key: "suggested_fix", label: "Предложение" },
  { key: "confidence", label: "Уверенность" },
  { key: "row_status", label: "Статус строки" },
];

function canonicalCellText(row: AffectedRowView, key: keyof AffectedRowView): string {
  if (key === "confidence") return formatConfidenceValue(row.confidence);
  if (key === "row_status") return formatRowStatus(row.row_status);
  return formatCellText(row[key] as string | number | null | undefined);
}

function exportCanonicalRows(rows: AffectedRowView[]) {
  const escape = (value: string) => `"${value.replace(/"/g, '""')}"`;
  const header = CANONICAL_COLUMNS.map((c) => c.label).join(",");
  const body = rows
    .map((row) => CANONICAL_COLUMNS.map((c) => escape(canonicalCellText(row, c.key))).join(","))
    .join("\n");
  const blob = new Blob([`${header}\n${body}`], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `data-fix-affected-rows-${Date.now()}.csv`;
  link.click();
  URL.revokeObjectURL(url);
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="rounded-md border bg-background p-4">
      <h3 className="text-sm font-semibold mb-3">{title}</h3>
      {children}
    </section>
  );
}

function formatEventDate(value?: string | null): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    year: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function actionCenterSearchFor(ctx: DataQualityResolutionContext): ActionCenterSearch {
  const instance = ctx.dynamic_problem_instance;
  return {
    source: "problem_engine",
    code: String(instance?.problem_code ?? ctx.issue.code ?? ""),
    ...(ctx.issue.nm_id != null ? { nm_id: String(ctx.issue.nm_id) } : {}),
    ...(instance?.id != null ? { problem_instance_id: String(instance.id) } : {}),
  };
}

function resultsSearchFor(ctx: DataQualityResolutionContext) {
  const instance = ctx.dynamic_problem_instance;
  return {
    source_module: "problem_engine",
    ...(instance?.id != null ? { problem_instance_id: String(instance.id) } : {}),
    ...(instance?.problem_code != null ? { problem_code: String(instance.problem_code) } : {}),
    ...(ctx.issue.nm_id != null ? { nm_id: String(ctx.issue.nm_id) } : {}),
  };
}

function resolutionModeCopy(ctx: DataQualityResolutionContext, owner: string, component: string): { title: string; body: string; tone: string } {
  const normalizedComponent = String(component || "").toLowerCase();
  const normalizedOwner = String(owner || "").toLowerCase();
  if (normalizedComponent.includes("upload_cost")) {
    return {
      title: "Нужно загрузить данные",
      body: "Загрузите файл себестоимости или заполните строки вручную. После сохранения исправление данных запустит повторную проверку.",
      tone: "border-emerald-500/40 bg-emerald-500/10",
    };
  }
  if (normalizedComponent.includes("sku")) {
    return {
      title: "Нужно сопоставить SKU",
      body: "Проверьте nm_id, SKU, баркод и артикул продавца, затем выберите правильную привязку.",
      tone: "border-emerald-500/40 bg-emerald-500/10",
    };
  }
  if (normalizedComponent.includes("expense")) {
    return {
      title: "Нужно классифицировать расход",
      body: "Выберите категорию расхода. Сумма WB не меняется, меняется только понятная бизнес-классификация.",
      tone: "border-emerald-500/40 bg-emerald-500/10",
    };
  }
  if (normalizedComponent.includes("sync") || normalizedComponent.includes("wait") || normalizedComponent.includes("reconciliation")) {
    return {
      title: "Нужна синхронизация или сверка",
      body: "Не меняйте суммы вручную. Запустите повторную проверку, дождитесь отчёта WB или передайте расхождение администратору.",
      tone: "border-amber-500/40 bg-amber-500/10",
    };
  }
  if (normalizedOwner === "system" || normalizedOwner === "admin" || !ctx.safe_to_apply) {
    return {
      title: normalizedOwner === "admin" ? "Нужен администратор" : "Проверяет система",
      body: "Проблема закрывается через системную загрузку, правила сопоставления или админский разбор. Пользователь не должен подгонять факты вручную.",
      tone: "border-amber-500/40 bg-amber-500/10",
    };
  }
  return {
    title: "Можно исправить внутри платформы",
    body: "Откройте мастер ниже, заполните недостающие бизнес-данные и запустите повторную проверку.",
    tone: "border-emerald-500/40 bg-emerald-500/10",
  };
}

function DataFixProblemResultLinkage({
  ctx,
  resultPage,
  loading,
  canSeeTechnicalDetails,
}: {
  ctx: DataQualityResolutionContext;
  resultPage?: PortalResultEventsPage | null;
  loading?: boolean;
  canSeeTechnicalDetails?: boolean;
}) {
  const instance = ctx.dynamic_problem_instance;
  if (!instance?.id) return null;
  const summary = resultPage ? problemResultSummaryFromPage(resultPage) : null;
  const events = problemResultEvents(resultPage);
  const recheckEvent = events.find((event) => String(event.event_type ?? "").includes("recheck"));
  const latestEvent = events[0];
  const resultStatus = summary?.status ?? "pending_data";
  const resultDetail =
    summary?.disclaimer ||
    latestEvent?.calculation_note ||
    "После действия платформа сравнит данные до и после. Это корреляция, а не доказанная причинность.";
  return (
    <Section title="L. Результат">
      <div className="grid gap-3 md:grid-cols-[1fr_auto]">
        <div className="space-y-3">
          <div className="flex flex-wrap gap-2">
            <Badge variant="outline" className="text-[10px]">
              Результат: {loading ? "загружаем" : problemResultStatusLabel(resultStatus)}
            </Badge>
            <Badge variant="outline" className="text-[10px]">
              Перепроверка: {recheckEvent ? formatEventDate(recheckEvent.created_at) : "ещё не запускалась"}
            </Badge>
            <Badge variant="outline" className="text-[10px]">
              Статус: {problemStatusLabel(instance.status)}
            </Badge>
          </div>
          <p className="text-sm text-muted-foreground">
            {loading
              ? "Загружаем ленту результата по этой проблеме."
              : resultPage
              ? resultDetail
              : "Лента результата появится после первого статуса, действия или повторной проверки."}
          </p>
          {canSeeTechnicalDetails ? (
            <details className="text-xs text-muted-foreground">
              <summary className="cursor-pointer select-none">Детали для поддержки</summary>
              <div className="mt-1 space-y-1 font-mono text-[11px]">
                <div>problem_instance_id: {instance.id}</div>
                <div>problem_code: {instance.problem_code}</div>
                <div>dq_issue_id: {ctx.issue.id}</div>
              </div>
            </details>
          ) : null}
        </div>
        <div className="flex flex-wrap items-start gap-2">
          <Button asChild size="sm" variant="outline">
            <Link to="/action-center" search={actionCenterSearchFor(ctx)}>
              Открыть задачу <ArrowRight className="ml-1.5 h-3.5 w-3.5" />
            </Link>
          </Button>
          <Button asChild size="sm" variant="outline">
            <Link to="/results" search={resultsSearchFor(ctx)}>
              Открыть результат <ArrowRight className="ml-1.5 h-3.5 w-3.5" />
            </Link>
          </Button>
        </div>
      </div>
    </Section>
  );
}

function AffectedRowMobileCard({
  row,
  canSeeTechnicalDetails,
}: {
  row: AffectedRowView;
  canSeeTechnicalDetails?: boolean;
}) {
  return (
    <div className="rounded-md border bg-background p-3 space-y-2 text-xs">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="space-y-0.5">
          <div className="text-[10px] uppercase text-muted-foreground">nmID</div>
          <div className="font-semibold text-sm">{formatCellText(row.nm_id)}</div>
        </div>
        <div className="space-y-0.5 text-right">
          <div className="text-[10px] uppercase text-muted-foreground">Артикул продавца</div>
          <div className="font-semibold text-sm break-all">{formatCellText(row.vendor_code)}</div>
        </div>
      </div>
      <div>
        <Badge variant="outline" className="text-[10px]">
          Статус: {formatRowStatus(row.row_status)}
        </Badge>
      </div>
      <div className="grid grid-cols-2 gap-2 pt-1">
        <div>
          <div className="text-[10px] uppercase text-muted-foreground">Баркод</div>
          <div className="break-all">{formatCellText(row.barcode)}</div>
        </div>
        <div>
          <div className="text-[10px] uppercase text-muted-foreground">Источник</div>
          <div className="break-all">{formatCellText(row.source)}</div>
        </div>
        <div>
          <div className="text-[10px] uppercase text-muted-foreground">Сейчас</div>
          <div className="break-all">{formatCellText(row.current_value)}</div>
        </div>
        <div>
          <div className="text-[10px] uppercase text-muted-foreground">Что не так</div>
          <div className="break-all">{formatCellText(row.missing_or_invalid_value)}</div>
        </div>
        <div>
          <div className="text-[10px] uppercase text-muted-foreground">Предложение</div>
          <div className="break-all">{formatCellText(row.suggested_fix)}</div>
        </div>
        <div>
          <div className="text-[10px] uppercase text-muted-foreground">Уверенность</div>
          <div>{formatConfidenceValue(row.confidence)}</div>
        </div>
      </div>
      {canSeeTechnicalDetails && row.raw ? (
        <details className="pt-1">
          <summary className="cursor-pointer text-[10px] text-muted-foreground select-none">
            Детали для поддержки
          </summary>
          <pre className="mt-1 overflow-x-auto rounded bg-muted/50 p-2 text-[10px] leading-snug">
            {JSON.stringify(row.raw, null, 2)}
          </pre>
        </details>
      ) : null}
    </div>
  );
}

function AffectedRowsTable({
  rows,
  total,
  limit,
  offset,
  onPageChange,
  serverExportPath,
  canSeeTechnicalDetails,
}: {
  rows: Record<string, unknown>[];
  total: number;
  limit: number;
  offset: number;
  onPageChange: (offset: number) => void;
  serverExportPath?: string | null;
  canSeeTechnicalDetails?: boolean;
}) {
  const isMobile = useIsMobile();
  const [search, setSearch] = useState("");
  const [exporting, setExporting] = useState(false);
  const [rawOpen, setRawOpen] = useState(false);

  const canonical = useMemo(() => normalizeAffectedRows(rows), [rows]);
  const filtered = useMemo(() => searchAffectedRows(canonical, search), [canonical, search]);
  const missingWarning = useMemo(() => anyRowHasMissingFields(filtered), [filtered]);

  const pageStart = total > 0 ? offset + 1 : 0;
  const pageEnd = Math.min(offset + rows.length, total);
  const canPrev = offset > 0;
  const canNext = offset + limit < total;

  const exportServerRows = async () => {
    if (!serverExportPath) {
      exportCanonicalRows(filtered);
      return;
    }
    setExporting(true);
    try {
      const response = await api<Response>(serverExportPath, { raw: true });
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `data-fix-affected-rows-${Date.now()}.csv`;
      link.click();
      URL.revokeObjectURL(url);
    } catch (error) {
      toast.error(errorMessage(error, "Не удалось скачать CSV"));
    } finally {
      setExporting(false);
    }
  };

  if (total === 0 && rows.length === 0) {
    return (
      <EmptyState
        variant="no_data"
        title="Нет затронутых строк"
        hint="Платформа не получила строки для этого исправления. Проверьте синхронизацию или откройте задачу."
      />
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
        <div className="relative flex-1">
          <Search className="absolute left-2 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Поиск по nmID, артикулу, баркоду, источнику, значению, статусу"
            className="pl-8"
          />
        </div>
        <Button type="button" variant="outline" size="sm" onClick={exportServerRows} disabled={exporting || (!filtered.length && !serverExportPath)}>
          <Download className="h-4 w-4 mr-1.5" />
          {exporting ? "Готовим CSV..." : "Скачать CSV"}
        </Button>
      </div>

      {missingWarning ? (
        <div className="rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-xs text-amber-700 dark:text-amber-300">
          Часть полей отсутствует в источнике данных. Пустые значения показаны как «—».
        </div>
      ) : null}

      {isMobile ? (
        <div className="space-y-2">
          {filtered.length ? (
            filtered.map((row, index) => (
              <AffectedRowMobileCard
                key={index}
                row={row}
                canSeeTechnicalDetails={canSeeTechnicalDetails}
              />
            ))
          ) : (
            <div className="rounded-md border bg-muted/30 p-3 text-sm text-muted-foreground">
              Строки не найдены.
            </div>
          )}
        </div>
      ) : (
        <div className="rounded-md border overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                {CANONICAL_COLUMNS.map((c) => (
                  <TableHead key={c.key} className="whitespace-nowrap text-xs">
                    {c.label}
                  </TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {filtered.length ? filtered.map((row, index) => (
                <TableRow key={index}>
                  {CANONICAL_COLUMNS.map((c) => {
                    const text = canonicalCellText(row, c.key);
                    return (
                      <TableCell
                        key={c.key}
                        className="max-w-[220px] truncate text-xs align-top"
                        title={text}
                      >
                        {text}
                      </TableCell>
                    );
                  })}
                </TableRow>
              )) : (
                <TableRow>
                  <TableCell colSpan={CANONICAL_COLUMNS.length} className="text-sm text-muted-foreground">
                    Строки не найдены.
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </div>
      )}

      <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
        <span>{pageStart}-{pageEnd} из {total}</span>
        <div className="flex gap-2">
          <Button type="button" variant="outline" size="sm" onClick={() => onPageChange(Math.max(0, offset - limit))} disabled={!canPrev}>
            Назад
          </Button>
          <Button type="button" variant="outline" size="sm" onClick={() => onPageChange(offset + limit)} disabled={!canNext}>
            Далее
          </Button>
        </div>
      </div>

      {canSeeTechnicalDetails && !isMobile && filtered.length ? (
        <details
          className="text-xs text-muted-foreground"
          open={rawOpen}
          onToggle={(e) => setRawOpen((e.target as HTMLDetailsElement).open)}
        >
          <summary className="cursor-pointer select-none">Детали для поддержки (raw)</summary>
          <pre className="mt-2 max-h-64 overflow-auto rounded bg-muted/50 p-2 text-[11px] leading-snug">
            {JSON.stringify(filtered.map((r) => r.raw), null, 2)}
          </pre>
        </details>
      ) : null}
    </div>
  );
}

function rowNumber(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string") {
    const normalized = value.replace(/\s/g, "").replace(",", ".");
    if (!normalized) return null;
    const parsed = Number(normalized);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function rowString(value: unknown): string {
  if (value == null) return "";
  return String(value);
}

function compactRowsBySku(rows: Record<string, unknown>[]) {
  const byKey = new Map<string, Record<string, unknown>>();
  for (const row of rows) {
    const costId = rowNumber(row.cost_id ?? row.costId);
    const sku = rowNumber(row.sku_id ?? row.skuId);
    if (!sku && !costId) continue;
    const key = costId ? `cost:${costId}` : `sku:${sku}`;
    const existing = byKey.get(key) ?? {};
    byKey.set(key, { ...existing, ...row, ...(sku ? { sku_id: sku } : {}), ...(costId ? { cost_id: costId } : {}) });
  }
  return [...byKey.values()].slice(0, 50);
}

type CostDraftRow = {
  key: string;
  row: Record<string, unknown>;
  costId: number | null;
  skuId: number;
  costPrice: string;
  sellerOtherExpense: string;
};

function CostInlineEditorPanel({
  ctx,
  postAction,
}: {
  ctx: DataQualityResolutionContext;
  postAction: (payload: ActionPayload) => Promise<GuidedFixActionResponse>;
}) {
  const accountId = ctx.issue.account_id;
  const requiresCost = ctx.resolver?.required_inputs?.some((item) => /себестоимость|cost/i.test(item)) || ctx.issue.code === "missing_manual_cost";
  const rows = useMemo(() => compactRowsBySku(ctx.affected_rows), [ctx.affected_rows]);
  const [drafts, setDrafts] = useState<CostDraftRow[]>([]);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setDrafts(
      rows.map((row, index) => {
        const costId = rowNumber(row.cost_id ?? row.costId);
        const skuId = rowNumber(row.sku_id ?? row.skuId) ?? 0;
        return {
          key: `${costId ? `cost-${costId}` : skuId || "row"}-${index}`,
          row,
          costId,
          skuId,
          costPrice: rowString(row.cost_price),
          sellerOtherExpense: row.seller_other_expense == null ? "" : rowString(row.seller_other_expense),
        };
      }),
    );
  }, [rows]);

  const updateDraft = (key: string, field: "costPrice" | "sellerOtherExpense", value: string) => {
    setDrafts((items) => items.map((item) => (item.key === key ? { ...item, [field]: value } : item)));
  };

  const changedDrafts = drafts.filter((draft) => {
    const originalCost = rowString(draft.row.cost_price);
    const originalOther = draft.row.seller_other_expense == null ? "" : rowString(draft.row.seller_other_expense);
    return draft.costPrice !== originalCost || draft.sellerOtherExpense !== originalOther;
  });

  const invalidMessage = (() => {
    if (!accountId) return "Нет аккаунта для сохранения.";
    if (!drafts.length) return "Платформа пока не нашла строки для встроенного редактирования. Запустите повторную проверку или откройте таблицу себестоимости.";
    if (!changedDrafts.length) return "Изменений пока нет.";
    for (const draft of changedDrafts) {
      if (!draft.skuId && !draft.costId) return "В одной из строк нет SKU или записи себестоимости: такую строку нельзя сохранить автоматически.";
      const cost = rowNumber(draft.costPrice);
      const other = rowNumber(draft.sellerOtherExpense);
      if (cost == null || cost < 0) return requiresCost ? "Заполните себестоимость числом 0 или больше." : "Для сохранения прочих расходов нужна текущая себестоимость.";
      if (other == null || other < 0) return "Заполните «Прочие расходы» числом 0 или больше. Если расходов нет, поставьте 0.";
    }
    return "";
  })();

  const save = async () => {
    if (invalidMessage || !accountId) return;
    setSaving(true);
    try {
      const payloadRows = changedDrafts.map((draft) => ({
        cost_id: draft.costId,
        sku_id: draft.skuId || undefined,
        cost_price: rowNumber(draft.costPrice),
        seller_other_expense: rowNumber(draft.sellerOtherExpense),
        supplier: "OPERATOR_TRUSTED_COST",
        comment: "Заполнено из мастера обзора бизнеса / исправления данных",
      }));
      await api(API_ENDPOINTS.costs.inlineSave, {
        method: "POST",
        body: { account_id: accountId, rows: payloadRows },
      });
      toast.success("Себестоимость сохранена. Запускаем перепроверку.");
      await postAction({
        action_type: "trigger_recheck",
        inputs: { source: "cost_inline_editor", rows: payloadRows.length },
        comment: "Себестоимость сохранена из встроенного редактора; запрошена повторная проверка качества данных.",
      });
    } catch (error) {
      toast.error(errorMessage(error, "Не удалось сохранить себестоимость"));
    } finally {
      setSaving(false);
    }
  };

  if (!drafts.length) {
    return (
      <div className="space-y-3">
        <div className="rounded-md border border-dashed p-3 text-sm text-muted-foreground">
          Строки для встроенной таблицы не пришли в контекст исправления. Нажмите «Перепроверить» или откройте «Себестоимость», но продажи и суммы WB вручную не меняйте.
        </div>
        <Button type="button" onClick={() => postAction({ action_type: "trigger_recheck", inputs: { source: "cost_inline_editor_empty" } })}>
          <RefreshCw className="h-4 w-4 mr-1.5" />
          Перепроверить
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="rounded-md border bg-muted/30 p-3 text-sm">
        <div className="font-medium">Заполните прямо здесь</div>
        <div className="mt-1 text-muted-foreground">
          Введите реальные бизнес-данные продавца. Пустое значение не закрывает проблему: если прочих расходов нет, поставьте 0.
        </div>
      </div>

      <div className="overflow-x-auto rounded-md border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="min-w-[86px]">SKU</TableHead>
              <TableHead className="min-w-[90px]">nmId</TableHead>
              <TableHead className="min-w-[140px]">Артикул</TableHead>
              <TableHead className="min-w-[110px] text-right">Выручка</TableHead>
              {requiresCost ? <TableHead className="min-w-[150px]">Себестоимость</TableHead> : null}
              <TableHead className="min-w-[160px]">Прочие расходы</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {drafts.map((draft) => {
              const revenue = rowNumber(draft.row.final_revenue ?? draft.row.revenue_impact);
              return (
                <TableRow key={draft.key}>
                  <TableCell className="font-medium tabular-nums">{draft.skuId || "-"}</TableCell>
                  <TableCell className="tabular-nums">{displayValue(draft.row.nm_id)}</TableCell>
                  <TableCell className="max-w-[220px] truncate" title={rowString(draft.row.vendor_code || draft.row.title)}>
                    {displayValue(draft.row.vendor_code || draft.row.title)}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">{revenue != null ? formatMoney(revenue) : "-"}</TableCell>
                  {requiresCost ? (
                    <TableCell>
                      <Input
                        inputMode="decimal"
                        value={draft.costPrice}
                        onChange={(event) => updateDraft(draft.key, "costPrice", event.target.value)}
                        placeholder="0"
                      />
                    </TableCell>
                  ) : null}
                  <TableCell>
                    <Input
                      inputMode="decimal"
                      value={draft.sellerOtherExpense}
                      onChange={(event) => updateDraft(draft.key, "sellerOtherExpense", event.target.value)}
                      placeholder="Если нет расходов, 0"
                    />
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </div>

      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div className="text-xs text-muted-foreground">
          Будет сохранено строк: {changedDrafts.length}. После сохранения платформа пересчитает витрины и DQ-проверку.
        </div>
        <Button type="button" onClick={save} disabled={!!invalidMessage || saving}>
          <CheckCircle2 className="h-4 w-4 mr-1.5" />
          {saving ? "Сохраняем..." : "Сохранить и перепроверить"}
        </Button>
      </div>
      {invalidMessage ? <div className="text-xs text-muted-foreground">{invalidMessage}</div> : null}
    </div>
  );
}

function CostUploadPanel({
  ctx,
  postAction,
}: {
  ctx: DataQualityResolutionContext;
  postAction: (payload: ActionPayload) => Promise<GuidedFixActionResponse>;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const accountId = ctx.issue.account_id;

  const onFileChange = (event: ChangeEvent<HTMLInputElement>) => {
    setFile(event.target.files?.[0] ?? null);
  };

  const upload = async () => {
    if (!file || !accountId) return;
    setUploading(true);
    try {
      const formData = new FormData();
      formData.append("account_id", String(accountId));
      formData.append("commit_rows", "true");
      formData.append("file", file);
      await api(API_ENDPOINTS.costs.upload, { method: "POST", formData });
      await postAction({ action_type: "mark_cost_upload_started", inputs: { filename: file.name } });
      toast.success("Себестоимость загружена, повторная проверка запущена из исправления данных");
    } catch (error) {
      toast.error(errorMessage(error, "Не удалось загрузить себестоимость"));
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="space-y-3">
      <div className="rounded-md border bg-muted/30 p-3 text-sm">
        <div className="font-medium">Что сделать</div>
        <ol className="mt-2 space-y-1 list-decimal pl-4 text-muted-foreground">
          <li>Нажмите поле «Файл себестоимости».</li>
          <li>Выберите CSV/XLSX от поставщика.</li>
          <li>Нажмите «Загрузить себестоимость».</li>
          <li>Платформа загрузит строки, отметит действие и запустит повторную проверку.</li>
        </ol>
        <div className="mt-2 text-xs text-muted-foreground">
          Финансовые факты WB здесь не редактируются: меняется только себестоимость, которую ввел продавец.
        </div>
      </div>
      <div className="grid gap-2">
        <Label htmlFor="cost-upload">Файл себестоимости</Label>
        <Input id="cost-upload" type="file" accept=".csv,.xlsx" onChange={onFileChange} />
      </div>
      <Button type="button" onClick={upload} disabled={!file || !accountId || uploading}>
        <FileUp className="h-4 w-4 mr-1.5" />
        {uploading ? "Загружаем..." : "Загрузить себестоимость"}
      </Button>
    </div>
  );
}

function SkuMappingPanel({
  ctx,
  postAction,
}: {
  ctx: DataQualityResolutionContext;
  postAction: (payload: ActionPayload) => Promise<GuidedFixActionResponse>;
}) {
  const [skuId, setSkuId] = useState("");
  const [reason, setReason] = useState("");
  const candidates = ctx.issue.candidate_sku_ids ?? [];
  const submit = () => postAction({ action_type: "map_sku", inputs: { mapped_sku_id: Number(skuId), reason }, comment: reason });

  return (
    <div className="space-y-3">
      <div className="rounded-md border bg-muted/30 p-3 text-sm">
        <div className="font-medium">Что сделать</div>
        <ol className="mt-2 space-y-1 list-decimal pl-4 text-muted-foreground">
          <li>Посмотрите проблемную строку ниже в таблице.</li>
          <li>Выберите предложенный SKU кнопкой или введите правильный SKU вручную.</li>
          <li>Напишите коротко, почему это правильная привязка.</li>
          <li>Нажмите «Привязать SKU». После этого платформа сохранит действие и обновит проверки.</li>
        </ol>
      </div>
      {candidates.length ? (
        <div className="flex flex-wrap gap-2 text-xs">
          <span className="text-muted-foreground">Возможные SKU:</span>
          {candidates.map((id) => (
            <Button key={id} type="button" variant="outline" size="sm" onClick={() => setSkuId(String(id))}>{id}</Button>
          ))}
        </div>
      ) : null}
      <div className="grid gap-2">
        <Label htmlFor="mapped-sku">SKU, к которому нужно привязать строку</Label>
        <Input id="mapped-sku" inputMode="numeric" value={skuId} onChange={(event) => setSkuId(event.target.value)} placeholder="Например: 123456789" />
      </div>
      <div className="grid gap-2">
        <Label htmlFor="mapped-reason">Почему выбран именно этот SKU</Label>
        <Textarea id="mapped-reason" value={reason} onChange={(event) => setReason(event.target.value)} rows={3} placeholder="Например: совпадает nm_id, баркод и артикул продавца" />
      </div>
      <Button type="button" onClick={submit} disabled={!Number(skuId)}>
        <Tags className="h-4 w-4 mr-1.5" />
        Привязать SKU
      </Button>
    </div>
  );
}

function ExpenseClassificationPanel({
  postAction,
}: {
  postAction: (payload: ActionPayload) => Promise<GuidedFixActionResponse>;
}) {
  const [category, setCategory] = useState("");
  const [reason, setReason] = useState("");
  const categories = ["logistics", "commission", "storage", "penalty", "deduction", "marketing", "other_wb_expense"];
  const submit = () => postAction({
    action_type: "classify_expense",
    inputs: { expense_category: category, classification_reason: reason },
    comment: reason,
  });

  return (
    <div className="space-y-3">
      <div className="rounded-md border bg-muted/30 p-3 text-sm">
        <div className="font-medium">Что сделать</div>
        <ol className="mt-2 space-y-1 list-decimal pl-4 text-muted-foreground">
          <li>Посмотрите название операции и сумму в строках ниже.</li>
          <li>Нажмите подходящую категорию расхода.</li>
          <li>Добавьте короткий комментарий, если категория не очевидна.</li>
          <li>Нажмите «Сохранить категорию». Сумма WB не меняется, меняется только классификация.</li>
        </ol>
      </div>
      <div className="flex flex-wrap gap-2">
        {categories.map((item) => (
          <Button key={item} type="button" variant="outline" size="sm" onClick={() => setCategory(item)}>
            {EXPENSE_CATEGORY_LABELS[item] ?? item}
          </Button>
        ))}
      </div>
      <div className="grid gap-2">
        <Label htmlFor="expense-category">Категория расхода</Label>
        <Input id="expense-category" value={EXPENSE_CATEGORY_LABELS[category] ?? category} readOnly placeholder="Выберите категорию кнопкой выше" />
      </div>
      <div className="grid gap-2">
        <Label htmlFor="expense-reason">Комментарий к классификации</Label>
        <Textarea id="expense-reason" value={reason} onChange={(event) => setReason(event.target.value)} rows={3} placeholder="Например: это удержание WB за хранение" />
      </div>
      <Button type="button" onClick={submit} disabled={!category.trim()}>
        <CheckCircle2 className="h-4 w-4 mr-1.5" />
        Сохранить категорию
      </Button>
    </div>
  );
}

function FinanceReconciliationPanel({
  postAction,
}: {
  postAction: (payload: ActionPayload) => Promise<GuidedFixActionResponse>;
}) {
  return (
    <div className="space-y-3">
      <div className="rounded-md border border-amber-500/40 bg-amber-500/10 p-3 text-sm">
        Финансовые факты WB доступны только для чтения. Платформа не просит пользователя менять продажи или суммы вручную, чтобы «подогнать» число.
      </div>
      <div className="rounded-md border bg-muted/30 p-3 text-sm text-muted-foreground">
        Нажмите «Запустить повторную проверку», если данные уже обновились. Если расхождение осталось, нажмите «Передать администратору».
      </div>
      <div className="flex flex-wrap gap-2">
        <Button type="button" variant="outline" onClick={() => postAction({ action_type: "mark_admin_investigation", inputs: { reason: "Finance reconciliation needs admin review" } })}>
          <ShieldAlert className="h-4 w-4 mr-1.5" />
          Передать администратору
        </Button>
        <Button type="button" onClick={() => postAction({ action_type: "trigger_recheck" })}>
          <RefreshCw className="h-4 w-4 mr-1.5" />
          Запустить повторную проверку
        </Button>
      </div>
    </div>
  );
}

function SyncWaitPanel({
  postAction,
}: {
  postAction: (payload: ActionPayload) => Promise<GuidedFixActionResponse>;
}) {
  return (
    <div className="space-y-3">
      <div className="rounded-md border bg-muted/30 p-3 text-sm">
        <div className="font-medium">Что сделать</div>
        <div className="mt-1 text-muted-foreground">
          Часто это задержка отчета WB или синхронизации источника. Можно отметить ожидание системы или запустить повторную проверку.
        </div>
      </div>
      <div className="flex flex-wrap gap-2">
        <Button type="button" variant="outline" onClick={() => postAction({ action_type: "mark_system_wait", inputs: { reason: "Waiting for WB report/source sync" } })}>
          Отметить ожидание системы
        </Button>
        <Button type="button" onClick={() => postAction({ action_type: "trigger_recheck" })}>
          <RefreshCw className="h-4 w-4 mr-1.5" />
          Запустить повторную проверку
        </Button>
      </div>
    </div>
  );
}

function StockDecisionPanel({
  ctx,
  postAction,
}: {
  ctx: DataQualityResolutionContext;
  postAction: (payload: ActionPayload) => Promise<GuidedFixActionResponse>;
}) {
  const [comment, setComment] = useState("");
  const salesWithoutStock = ctx.issue.code === "sales_without_stock";
  const decisions = salesWithoutStock
    ? [
        { key: "refresh_stock", label: "Обновить остатки", description: "Если это задержка загрузки, запускаем перепроверку свежего снимка." },
        { key: "replenish", label: "Создать задачу на пополнение", description: "Если товар реально продается, фиксируем действие на пополнение." },
        { key: "availability", label: "Проверить доступность", description: "Проверяем склад, карточку и доступность в WB." },
      ]
    : [
        { key: "sale", label: "Распродажа", description: "Остаток реальный, нужно разгрузить товар." },
        { key: "ads", label: "Реклама", description: "Остаток реальный, нужно усилить спрос." },
        { key: "stop_buying", label: "Не закупать", description: "Пауза закупки, пока остаток не снизится." },
        { key: "return", label: "Возврат", description: "Лишний товар нужно вернуть или вывести." },
      ];

  const chooseDecision = (decision: string) => postAction({
    action_type: decision === "refresh_stock" ? "trigger_recheck" : "mark_admin_investigation",
    inputs: { decision, comment, source: "stock_decision" },
    comment: comment || decisions.find((item) => item.key === decision)?.label,
  });

  return (
    <div className="space-y-3">
      <div className="rounded-md border bg-muted/30 p-3 text-sm">
        <div className="font-medium">Здесь не меняем остатки или продажи вручную</div>
        <div className="mt-1 text-muted-foreground">
          Выберите понятное решение. Если похоже на ошибку загрузки, запускайте повторную проверку. Платформа сохранит решение в истории проблемы.
        </div>
      </div>
      <div className="grid gap-2 md:grid-cols-2">
        {decisions.map((item) => (
          <Button key={item.key} type="button" variant="outline" className="h-auto justify-start whitespace-normal p-3 text-left" onClick={() => chooseDecision(item.key)}>
            <span>
              <span className="block font-medium">{item.label}</span>
              <span className="block text-xs font-normal text-muted-foreground">{item.description}</span>
            </span>
          </Button>
        ))}
        <Button type="button" variant="outline" className="h-auto justify-start whitespace-normal p-3 text-left" onClick={() => postAction({ action_type: "trigger_recheck", inputs: { source: "stock_decision", reason: "possible_source_delay" }, comment })}>
          <span>
            <span className="block font-medium">Ошибка данных → повторная проверка</span>
            <span className="block text-xs font-normal text-muted-foreground">Остаток или продажа выглядят как задержка источника.</span>
          </span>
        </Button>
      </div>
      <Textarea
        value={comment}
        onChange={(event) => setComment(event.target.value)}
        rows={3}
        placeholder="Комментарий: что увидели в карточке и почему выбрали это решение"
      />
    </div>
  );
}

function AdsAllocationStatusPanel({
  postAction,
}: {
  postAction: (payload: ActionPayload) => Promise<GuidedFixActionResponse>;
}) {
  return (
    <div className="space-y-3">
      <div className="rounded-md border border-amber-500/40 bg-amber-500/10 p-3 text-sm">
        Рекламные суммы вручную не редактируются. Платформа защищает финальную прибыль: подозрительный излишек не должен вычитаться второй раз.
      </div>
      <div className="grid gap-2 md:grid-cols-2">
        <Button type="button" onClick={() => postAction({ action_type: "trigger_recheck", inputs: { source: "ads_allocation_status" } })}>
          <RefreshCw className="h-4 w-4 mr-1.5" />
          Перепроверить рекламу
        </Button>
        <Button type="button" variant="outline" onClick={() => postAction({ action_type: "mark_admin_investigation", inputs: { reason: "Ads allocation requires admin review" } })}>
          <ShieldAlert className="h-4 w-4 mr-1.5" />
          Передать администратору
        </Button>
      </div>
    </div>
  );
}

function CardMappingPanel({
  postAction,
}: {
  postAction: (payload: ActionPayload) => Promise<GuidedFixActionResponse>;
}) {
  return (
    <div className="space-y-3">
      <div className="rounded-md border border-amber-500/40 bg-amber-500/10 p-3 text-sm">
        chrt_id нельзя вводить наугад. Он должен прийти из карточек WB или из другого надежного источника.
      </div>
      <div className="flex flex-wrap gap-2">
        <Button type="button" onClick={() => postAction({ action_type: "trigger_recheck", inputs: { source: "card_mapping" } })}>
          <RefreshCw className="h-4 w-4 mr-1.5" />
          Обновить карточки и перепроверить
        </Button>
        <Button type="button" variant="outline" onClick={() => postAction({ action_type: "mark_admin_investigation", inputs: { reason: "Нет chrt_id: нужен доверенный источник" } })}>
          <ShieldAlert className="h-4 w-4 mr-1.5" />
          Передать администратору
        </Button>
      </div>
    </div>
  );
}

function AdminInvestigationPanel({
  postAction,
}: {
  postAction: (payload: ActionPayload) => Promise<GuidedFixActionResponse>;
}) {
  const [reason, setReason] = useState("");
  return (
    <div className="space-y-3">
      <Textarea
        value={reason}
        onChange={(event) => setReason(event.target.value)}
        rows={3}
        placeholder="Комментарий для администратора: что проверили и что осталось непонятным"
      />
      <Button
        type="button"
        variant="outline"
        onClick={() => postAction({ action_type: "mark_admin_investigation", inputs: { reason }, comment: reason })}
      >
        <ShieldAlert className="h-4 w-4 mr-1.5" />
        Передать администратору
      </Button>
    </div>
  );
}

function PriceReviewPanel({
  postAction,
}: {
  postAction: (payload: ActionPayload) => Promise<GuidedFixActionResponse>;
}) {
  const [reason, setReason] = useState("");
  return (
    <div className="space-y-3">
      <Textarea
        value={reason}
        onChange={(event) => setReason(event.target.value)}
        rows={3}
        placeholder="Например: цена проверена, значение верное или исправлено в источнике"
      />
      <Button type="button" onClick={() => postAction({ action_type: "review_price", inputs: { reason }, comment: reason })}>
        <CheckCircle2 className="h-4 w-4 mr-1.5" />
        Сохранить проверку цены
      </Button>
    </div>
  );
}

function FixPanel({
  ctx,
  postAction,
}: {
  ctx: DataQualityResolutionContext;
  postAction: (payload: ActionPayload) => Promise<GuidedFixActionResponse>;
}) {
  switch (ctx.definition.fix_component_type) {
    case "cost_inline_editor":
      return <CostInlineEditorPanel ctx={ctx} postAction={postAction} />;
    case "upload_cost_file":
      return <CostUploadPanel ctx={ctx} postAction={postAction} />;
    case "sku_mapping":
    case "map_sku":
      return <SkuMappingPanel ctx={ctx} postAction={postAction} />;
    case "card_mapping":
    case "open_card_mapping":
      return <CardMappingPanel postAction={postAction} />;
    case "expense_classification":
    case "classify_expense":
      return <ExpenseClassificationPanel postAction={postAction} />;
    case "open_finance_reconciliation":
      return <FinanceReconciliationPanel postAction={postAction} />;
    case "sync_recheck":
    case "wait_for_wb_report":
    case "rerun_sync":
      return <SyncWaitPanel postAction={postAction} />;
    case "stock_decision":
      return <StockDecisionPanel ctx={ctx} postAction={postAction} />;
    case "ads_allocation_status":
      return <AdsAllocationStatusPanel postAction={postAction} />;
    case "review_price":
      return <PriceReviewPanel postAction={postAction} />;
    default:
      return <AdminInvestigationPanel postAction={postAction} />;
  }
}

export function DataFixWorkbench({
  issueId,
  fallbackBlocker,
  open,
  onOpenChange,
  onChanged,
  onLocalActionSaved,
  inline = false,
  hideHeader = false,
  className,
}: WorkbenchProps) {
  const qc = useQueryClient();
  const { user } = useAuth();
  const canSeeTechnicalDetails = !!user?.is_superuser;
  const [affectedRowsOffset, setAffectedRowsOffset] = useState(0);
  const [evidenceOpen, setEvidenceOpen] = useState(false);
  const affectedRowsLimit = 50;
  useEffect(() => {
    setAffectedRowsOffset(0);
  }, [issueId]);
  const contextQ = useQuery({
    queryKey: ["dq-resolution-context", issueId, affectedRowsLimit, affectedRowsOffset],
    enabled: open && !!issueId,
    queryFn: () => api<DataQualityResolutionContext>(API_ENDPOINTS.dq.resolutionContext(issueId!), {
      query: {
        affected_rows_limit: affectedRowsLimit,
        affected_rows_offset: affectedRowsOffset,
      },
    }),
    retry: false,
  });

  const actionM = useMutation({
    mutationFn: (payload: ActionPayload) => api<GuidedFixActionResponse>(API_ENDPOINTS.dq.guidedAction(issueId!), {
      method: "POST",
      body: payload,
    }),
    onSuccess: (result, payload) => {
      toast.success(result.message || "Действие исправления данных сохранено");
      qc.invalidateQueries({ queryKey: ["dq-resolution-context", issueId] });
      qc.invalidateQueries({ queryKey: ["dq-issues-for-data-fix"] });
      qc.invalidateQueries({ queryKey: ["money-data-blockers"] });
      qc.invalidateQueries({ queryKey: ["dash-data-blockers"] });
      qc.invalidateQueries({ queryKey: ["dashboard-data-health"] });
      qc.invalidateQueries({ queryKey: ["dq-issues-summary"] });
      qc.invalidateQueries({ queryKey: ["portal-problem-results", "data-fix"] });
      onChanged?.();
      if (onLocalActionSaved) {
        void Promise.resolve(onLocalActionSaved(payload)).catch((error) => {
          toast.error(errorMessage(error, "Не удалось обновить историю задачи"));
        });
      }
    },
    onError: (error) => toast.error(errorMessage(error, "Не удалось сохранить действие исправления данных")),
  });

  const ctx = contextQ.data;
  const issue: DataQualityIssue | null = ctx?.issue ?? null;
  const amount = fallbackBlocker?.affected_amount ?? fallbackBlocker?.affected_revenue;
  const resolver = ctx?.resolver ?? issue?.resolver ?? null;
  const owner = resolver?.owner_type ?? ctx?.definition.owner_type ?? "mixed";
  const component = resolver?.component_type ?? ctx?.definition.fix_component_type ?? "admin_investigation";
  const ledger = evidenceFrom(ctx?.dynamic_problem_instance?.evidence_ledger, issue?.evidence_ledger);
  const problemInstanceId = ctx?.dynamic_problem_instance?.id ?? null;
  const problemResultsQ = useQuery({
    queryKey: ["portal-problem-results", "data-fix", problemInstanceId],
    enabled: open && !!problemInstanceId,
    queryFn: () => fetchProblemResults(problemInstanceId!),
    staleTime: 30_000,
    retry: false,
  });
  const problemResult = problemResultsQ.data ? problemResultContractValue(problemResultsQ.data) : undefined;
  const dataFixMoneyTrust = issue
    ? moneyTrustFrom(issue.money_trust, ledger?.money_trust, { state: "blocked" })
    : null;
  const problemLike = issue
    ? {
        ...(ctx?.dynamic_problem_instance ?? {}),
        title: ctx?.dynamic_problem_instance?.title ?? issue.message,
        reason: ctx?.dynamic_problem_instance?.explanation ?? issue.simple_reason ?? issue.business_impact,
        recommendation: ctx?.dynamic_problem_instance?.recommendation ?? objectText(ctx?.definition.preview_before_change.description),
        next_step: objectText(ctx?.definition.preview_before_change.description),
        status: ctx?.dynamic_problem_instance?.status ?? issue.status,
        problem_instance_id: ctx?.dynamic_problem_instance?.id,
        is_dynamic_problem: Boolean(ctx?.dynamic_problem_instance),
        source_module: ctx?.dynamic_problem_instance ? "problem_engine" : issue.domain,
        problem_code: ctx?.dynamic_problem_instance?.problem_code ?? issue.code,
        severity: ctx?.dynamic_problem_instance?.severity ?? (issue.effective_financial_final_blocker ? "high" : "medium"),
        trust_state: ctx?.dynamic_problem_instance?.trust_state ?? issue.money_trust?.state ?? ledger?.confidence ?? "blocked",
        impact_type: ctx?.dynamic_problem_instance?.impact_type ?? (issue.effective_financial_final_blocker ? "data_blocker" : "system_warning"),
        money_impact_amount: ctx?.dynamic_problem_instance?.money_impact_amount ?? amount,
        can_user_fix_inside_platform: ctx?.safe_to_apply,
        allowed_actions: ctx?.definition.apply_action ? [ctx.definition.apply_action, "recheck"] : ["recheck"],
        recheck_rule_human: ctx?.recheck_rule,
        evidence_ledger: ledger,
      }
    : null;
  const resolutionCopy = ctx ? resolutionModeCopy(ctx, owner, component) : null;

  const content = (
    <>
        {!hideHeader ? (
        <SheetHeader className="pr-8">
          <SheetTitle>Мастер исправления данных</SheetTitle>
          <SheetDescription>
            Платформа показывает: что случилось, откуда взялась проблема, куда нажать, что заполнить и как проверить результат.
          </SheetDescription>
        </SheetHeader>
        ) : null}

        {!issueId ? (
          <ProblemEmptyState
            className="mt-6"
            kind="data_missing"
            message="У этого блокера пока нет конкретной строки качества данных в текущей выборке. Нажмите «Обновить» в исправлении данных и попробуйте открыть задачу снова."
          />
        ) : contextQ.isLoading ? (
          <div className="mt-6 space-y-3">
            <Skeleton className="h-24 w-full" />
            <Skeleton className="h-52 w-full" />
            <Skeleton className="h-40 w-full" />
          </div>
        ) : contextQ.isError || !ctx || !issue ? (
          <div className="mt-6 rounded-md border border-destructive/40 bg-destructive/5 p-4 text-sm">
            Не удалось загрузить контекст исправления. Обновите исправление данных и попробуйте снова.
          </div>
        ) : (
          <div className="mt-6 space-y-4">
            <Section title="A. Что произошло?">
              <div className="flex flex-wrap items-center gap-2">
                <Badge variant="outline" title={`Код проверки: ${issue.code}`}>
                  {problemCodeLabel(issue.code)}
                </Badge>
                {ctx.dynamic_problem_instance ? (
                  <>
                    <Badge variant="outline" title={`Код правила: ${ctx.dynamic_problem_instance.problem_code}`}>
                      Правило: {problemCodeLabel(ctx.dynamic_problem_instance.problem_code)}
                    </Badge>
                    <Badge variant="outline">{problemStatusLabel(ctx.dynamic_problem_instance.status)}</Badge>
                  </>
                ) : null}
                <Badge variant={issue.effective_financial_final_blocker ? "destructive" : "secondary"}>
                  {issue.effective_financial_final_blocker ? "блокирует финальную прибыль" : "предупреждение / система"}
                </Badge>
                <Badge variant="outline">{OWNER_COPY[owner] ?? owner}</Badge>
                <Badge variant="outline">{COMPONENT_COPY[component] ?? component}</Badge>
              </div>
              <div className="mt-3 text-sm font-medium">{issue.message}</div>
              <div className="mt-1 text-sm text-muted-foreground">{issue.simple_reason || issue.business_impact}</div>
              {resolutionCopy ? (
                <div className={`mt-3 rounded-md border p-3 text-sm ${resolutionCopy.tone}`}>
                  <div className="font-medium">{resolutionCopy.title}</div>
                  <div className="mt-1 text-muted-foreground">{resolutionCopy.body}</div>
                </div>
              ) : null}
              {ctx.dynamic_problem_instance && canSeeTechnicalDetails ? (
                <details className="mt-3 text-xs text-muted-foreground">
                  <summary className="cursor-pointer select-none">Детали для поддержки</summary>
                  <div className="mt-1 space-y-1 font-mono text-[11px]">
                    <div>problem_instance_id: {ctx.dynamic_problem_instance.id}</div>
                    <div>problem_code: {ctx.dynamic_problem_instance.problem_code}</div>
                    <div>dq_issue_id: {issue.id}</div>
                  </div>
                </details>
              ) : null}
              {problemLike ? (
                <SellerProblemLifecycle
                  problem={problemLike}
                  ledger={ledger}
                  recheckRule={ctx.recheck_rule}
                  result={problemResult}
                  className="mt-3"
                  onEvidence={() => setEvidenceOpen(true)}
                />
              ) : null}
            </Section>

            <DataFixProblemResultLinkage
              ctx={ctx}
              resultPage={problemResultsQ.data}
              loading={problemResultsQ.isLoading}
              canSeeTechnicalDetails={canSeeTechnicalDetails}
            />

            <Section title="B. Почему это важно?">
              <p className="mb-3 text-sm text-muted-foreground">
                Ниже — что именно ломает эта проблема: сколько денег и строк она затрагивает и насколько платформе можно доверять расчёту.
              </p>
              <div className="grid gap-3 md:grid-cols-3">
                <div className="rounded-md bg-muted/40 p-3">
                  <div className="text-xs text-muted-foreground">Затронутые деньги</div>
                  <div className="text-lg font-semibold">{typeof amount === "number" ? formatMoney(amount) : "-"}</div>
                </div>
                <div className="rounded-md bg-muted/40 p-3">
                  <div className="text-xs text-muted-foreground">Доверие к расчёту</div>
                  <div className="mt-1 flex flex-wrap items-center gap-2">
                    {dataFixMoneyTrust ? <MoneyTrustBadge trust={dataFixMoneyTrust} /> : null}
                    <span className="text-sm font-medium">{problemTrustLabel(issue.money_trust?.state ?? issue.evidence_ledger?.confidence ?? "blocked")}</span>
                  </div>
                </div>
                <div className="rounded-md bg-muted/40 p-3">
                  <div className="text-xs text-muted-foreground">Строк в задаче</div>
                  <div className="text-lg font-semibold">{ctx.affected_rows.length}</div>
                </div>
              </div>
            </Section>

            <Section title="C. Какие строки затронуты?">
              <p className="text-sm text-muted-foreground">
                Всего строк: <b className="text-foreground">{ctx.affected_rows_total ?? ctx.affected_rows.length}</b>.
                {" "}Полный список — ниже, в разделе «Затронутые строки».
              </p>
            </Section>

            <Section title="D. Доказательства">
              <p className="mb-3 text-sm text-muted-foreground">
                Исходные факты, по которым платформа нашла проблему. Это не догадки, а данные из источников и проверок качества.
              </p>
              {ledger ? (
                <div className="mb-3 flex flex-wrap items-center gap-2 rounded-md border bg-muted/30 p-3 text-sm">
                  <div className="min-w-0 flex-1">
                    <div className="font-medium">Доказательства расчёта</div>
                    <div className="truncate text-xs text-muted-foreground">{ledger.formula_human || ledger.formula_code}</div>
                  </div>
                  <Button type="button" variant="outline" size="sm" onClick={() => setEvidenceOpen(true)}>
                    {EVIDENCE_BUTTON_LABEL}
                  </Button>
                </div>
              ) : null}
              <div className="grid gap-3 md:grid-cols-2">
                {ctx.source_facts.map((fact, index) => (
                  <div key={index} className="rounded-md bg-muted/40 p-3 text-sm">
                    <div className="font-medium">{fact.label}</div>
                    <div className="mt-1 text-muted-foreground">{displayValue(fact.value)} {fact.unit ?? ""}</div>
                    <div className="mt-2 text-xs text-muted-foreground">
                      {fact.source_table || "-"} · строк: {fact.row_count ?? "-"}
                    </div>
                  </div>
                ))}
              </div>
            </Section>

            <Section title="E. Можно исправить здесь?">
              <div className="space-y-3 text-sm">
                <div>{objectText(ctx.definition.preview_before_change.description)}</div>
                {(resolver?.required_inputs?.length || ctx.definition.required_inputs.length) ? (
                  <div>
                    <div className="text-xs font-medium text-muted-foreground mb-1">Что потребуется заполнить</div>
                    <div className="flex flex-wrap gap-2">
                      {(resolver?.required_inputs?.length ? resolver.required_inputs : ctx.definition.required_inputs).map((item) => (
                        <Badge key={item} variant="outline">{fieldLabel(item)}</Badge>
                      ))}
                    </div>
                  </div>
                ) : null}
                {(ctx.definition.safety_notes.length || resolver?.blocked_actions?.length) ? (
                  <div className="rounded-md border border-amber-500/40 bg-amber-500/10 p-3">
                    {ctx.definition.safety_notes.map((note) => <div key={note}>{note}</div>)}
                    {resolver?.blocked_actions?.map((note) => <div key={note}>{note}</div>)}
                  </div>
                ) : null}
              </div>
            </Section>

            <Section title="F. Что нужно сделать?">
              {Array.isArray(ctx.definition.how_to_fix) && ctx.definition.how_to_fix.length > 0 ? (
                <ol className="list-decimal pl-5 space-y-1 text-sm">
                  {ctx.definition.how_to_fix.map((step, i) => (
                    <li key={i} className="text-muted-foreground">{objectText(step)}</li>
                  ))}
                </ol>
              ) : (
                <p className="text-sm text-muted-foreground">
                  Заполните форму ниже и сохраните — платформа сама запустит повторную проверку.
                </p>
              )}
            </Section>

            <Section title="G. Исправление">
              <FixPanel ctx={ctx} postAction={(payload) => actionM.mutateAsync(payload)} />
              {actionM.isPending ? <div className="mt-2 text-xs text-muted-foreground">Сохраняем действие...</div> : null}
            </Section>

            <Section title="H. Preview">
              <div className="rounded-md border border-primary/30 bg-primary/5 p-3 text-sm space-y-2">
                <div className="text-xs uppercase tracking-wide text-muted-foreground">Предварительный просмотр перед сохранением</div>
                <div>
                  <b>Что изменится:</b>{" "}
                  {objectText(ctx.definition.preview_before_change?.description) || "Изменение бизнес-данных без правки WB-фактов."}
                </div>
                <div>
                  <b>Сколько строк будет затронуто:</b>{" "}
                  {ctx.affected_rows_total ?? ctx.affected_rows.length}
                </div>
                <div>
                  <b>Что разблокирует:</b>{" "}
                  {objectText((ctx.definition.preview_before_change as any)?.unblocks) ||
                    "расчёт прибыли, маржи и связанных бизнес-действий."}
                </div>
                <div>
                  <b>Возможные риски:</b>{" "}
                  {(ctx.definition.safety_notes?.[0] ?? null) ||
                    "проверьте, что данные относятся к правильному SKU/периоду — иначе метрика может исказиться."}
                </div>
                <div>
                  <b>Как платформа перепроверит результат:</b>{" "}
                  {ctx.recheck_rule || "после сохранения платформа запустит повторную проверку и обновит статус."}
                </div>
              </div>
            </Section>

            <Section title="I. Применить / Сохранить">
              <p className="text-sm text-muted-foreground">
                Сохранение происходит в блоке «G. Исправление». WB финансовые факты платформа не редактирует.
              </p>
            </Section>

            <Tabs defaultValue="affected_rows" className="space-y-3">
              <TabsList className="flex-wrap h-auto">
                <TabsTrigger value="affected_rows">Затронутые строки</TabsTrigger>
                <TabsTrigger value="source_facts">Исходные факты</TabsTrigger>
                <TabsTrigger value="audit">J. Статус и история</TabsTrigger>
              </TabsList>
              <TabsContent value="affected_rows">
                <Section title="Затронутые строки">
                  <AffectedRowsTable
                    rows={ctx.affected_rows}
                    total={ctx.affected_rows_total}
                    limit={ctx.affected_rows_limit}
                    offset={ctx.affected_rows_offset}
                    onPageChange={setAffectedRowsOffset}
                    serverExportPath={ctx.affected_rows_export_endpoint ?? API_ENDPOINTS.dq.affectedRowsCsv(issue.id)}
                    canSeeTechnicalDetails={canSeeTechnicalDetails}
                  />
                </Section>
              </TabsContent>
              <TabsContent value="source_facts">
                <Section title="Исходные факты">
                  <div className="grid gap-3 md:grid-cols-2">
                    {ctx.source_facts.map((fact, index) => (
                      <div key={index} className="rounded-md bg-muted/40 p-3 text-sm">
                        <div className="font-medium">{fact.label}</div>
                        <div className="mt-1 text-muted-foreground">{displayValue(fact.value)} {fact.unit ?? ""}</div>
                        <div className="mt-2 text-xs text-muted-foreground">
                          {fact.source_table || "-"} · строк: {fact.row_count ?? "-"}
                        </div>
                      </div>
                    ))}
                  </div>
                </Section>
              </TabsContent>
              <TabsContent value="audit">
                <Section title="J. Статус и история">
                  {ctx.audit_history.length ? (
                    <div className="space-y-2">
                      {ctx.audit_history.slice().reverse().map((item, index) => (
                        <div key={index} className="rounded-md bg-muted/40 p-3 text-xs">
                          <div className="font-medium">{displayValue(item.actionType)} · {displayValue(item.status)}</div>
                          <div className="mt-1 text-muted-foreground">{displayValue(item.message)}</div>
                          <div className="mt-1 text-muted-foreground">{displayValue(item.createdAt)}</div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="text-sm text-muted-foreground">Попыток исправления пока нет.</div>
                  )}
                </Section>
              </TabsContent>
            </Tabs>


            <Section title="K. Повторная проверка">
              <div className="space-y-3 text-sm">
                <div className="text-muted-foreground">{ctx.recheck_rule || "После изменения источника запустите повторную проверку качества данных."}</div>
                <Button type="button" onClick={() => actionM.mutate({ action_type: "trigger_recheck" })} disabled={actionM.isPending}>
                  <RefreshCw className={`h-4 w-4 mr-1.5 ${actionM.isPending ? "animate-spin" : ""}`} />
                  Запустить повторную проверку
                </Button>
              </div>
            </Section>


            {!ctx.safe_to_apply ? (
              <div className="flex items-start gap-2 rounded-md border border-amber-500/40 bg-amber-500/10 p-3 text-sm">
                <AlertTriangle className="mt-0.5 h-4 w-4" />
                <div>
                  Эту проблему нельзя исправлять ручным изменением фактов. Используйте синхронизацию, ожидание отчета WB или передачу администратору.
                </div>
              </div>
            ) : (
              <div className="flex items-start gap-2 rounded-md border border-emerald-500/40 bg-emerald-500/10 p-3 text-sm">
                <Wrench className="mt-0.5 h-4 w-4" />
                <div>Эту задачу можно закрыть внутри платформы. Повторная проверка подтвердит, что проблема исчезла.</div>
              </div>
            )}
          </div>
        )}
    </>
  );

  const evidenceDrawer = (
    <EvidenceDrawer
      open={evidenceOpen}
      onOpenChange={setEvidenceOpen}
      ledger={ledger}
      title={issue?.message ?? "Доказательства исправления данных"}
    />
  );

  if (inline) {
    return <div className={className}>{content}{evidenceDrawer}</div>;
  }

  return (
    <Sheet open={open} onOpenChange={onOpenChange ?? (() => undefined)}>
      <SheetContent side="right" className="w-[94vw] overflow-y-auto sm:max-w-[980px]">
        {content}
      </SheetContent>
      {evidenceDrawer}
    </Sheet>
  );
}
