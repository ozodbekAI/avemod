// Costs workbench - production-grade cost trust operations.
import { createFileRoute, Link } from "@tanstack/react-router";
import {
  keepPreviousData,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import {
  useEffect,
  useMemo,
  useState,
  type FormEvent,
  type ReactNode,
} from "react";
import {
  AlertCircle,
  ArrowRight,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  ClipboardCheck,
  Database,
  Download,
  Eye,
  FileSpreadsheet,
  FileUp,
  Filter,
  History,
  Link2,
  Loader2,
  PackageCheck,
  RefreshCw,
  Save,
  Search,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  Upload,
  Wallet,
  Wrench,
} from "lucide-react";
import { toast } from "sonner";

import { ActionCenterReturnLink } from "@/components/action-center/ActionCenterReturnLink";
import { DataDependencyNotice } from "@/components/data-health/DataCoveragePanel";
import { EndpointError } from "@/components/EndpointError";
import { ExportButton } from "@/components/ExportButton";
import { PageHeader, PageShell } from "@/components/PageShell";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useAccounts } from "@/lib/account-context";
import {
  api,
  type DashboardDataHealth,
  type ManualCostRow,
  type ManualCostUpload,
  type Paginated,
} from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { useDateRange } from "@/lib/date-range-context";
import { API_ENDPOINTS } from "@/lib/endpoints";
import {
  formatDate,
  formatDateTime,
  formatMoney,
  formatNumber,
  formatPercent,
} from "@/lib/format";
import {
  confirmCostsUpload,
  fetchCostsImports,
  fetchCostsMissing,
  fetchCostsRows,
  fetchCostsUnresolved,
  previewCostsUpload,
  saveInlineCosts,
  uploadCostsFile,
  type CostsMissingResponse,
} from "@/lib/money-endpoints";
import { routeSearchText } from "@/lib/action-center-routing";
import { appendActionCenterProblemHistory } from "@/lib/action-center-task-history";
import { cn } from "@/lib/utils";

type CostsSearch = {
  focus?:
    | "missing-costs"
    | "other-expenses"
    | "relink-sku"
    | "upload"
    | "table";
  q?: string;
  problem_instance_id?: string;
  nm_id?: string;
};

export const Route = createFileRoute("/_authenticated/costs")({
  component: CostsPage,
  validateSearch: (s: Record<string, unknown>): CostsSearch => ({
    focus:
      s.focus === "missing-costs" ||
      s.focus === "other-expenses" ||
      s.focus === "relink-sku" ||
      s.focus === "upload" ||
      s.focus === "table"
        ? s.focus
        : undefined,
    q: typeof s.q === "string" ? s.q : undefined,
    problem_instance_id: routeSearchText(s.problem_instance_id),
    nm_id: routeSearchText(s.nm_id),
  }),
  errorComponent: ({ error, reset }) => (
    <EndpointError error={error} reset={reset} />
  ),
});

const PAGE_SIZE = 50;
const dataGridShellClass =
  "overflow-hidden rounded-lg border bg-background shadow-sm ring-1 ring-black/5 dark:ring-white/10";
const dataGridViewportClass = "overflow-auto bg-muted/20";
const dataGridTableClass = "w-full border-separate border-spacing-0 text-sm";
const dataGridHeadClass =
  "h-10 border-b border-r bg-muted/75 px-3 text-[11px] font-semibold uppercase tracking-normal text-muted-foreground backdrop-blur";
const dataGridCellClass = "border-b border-r px-3 py-2 align-middle";

type WorkTab = "table" | "import" | "links" | "history";
type RowView = "all" | "missing" | "other";

type CostGridRow = {
  key: string;
  source: "existing" | "missing";
  costId?: number;
  sku_id?: number | null;
  nm_id?: number | null;
  vendor_code?: string | null;
  barcode?: string | null;
  tech_size?: string | null;
  product_title?: string | null;
  cost_price?: number | null;
  seller_other_expense?: number | null;
  supplier?: string | null;
  trust?: string | null;
  business_trusted?: boolean | null;
  supplier_confirmed?: boolean | null;
  valid_from?: string | null;
  valid_to?: string | null;
  comment?: string | null;
  affected_revenue?: number | null;
};

type RefreshMartsResult = {
  skipped: boolean;
};

function parseNonNegativeDraft(value?: string): {
  touched: boolean;
  valid: boolean;
  value: number | null;
} {
  if (value == null) return { touched: false, valid: true, value: null };
  const text = String(value).replace(",", ".").trim();
  if (!text) return { touched: true, valid: false, value: null };
  const parsed = Number(text);
  return {
    touched: true,
    valid: Number.isFinite(parsed) && parsed >= 0,
    value: parsed,
  };
}

function moneyChanged(
  nextValue: number | null,
  currentValue: number | null,
): boolean {
  if (nextValue == null) return false;
  if (currentValue == null) return true;
  return Math.abs(nextValue - currentValue) > 0.0001;
}

function toArray<T>(value: unknown): T[] {
  if (Array.isArray(value)) return value as T[];
  if (value && typeof value === "object") {
    const obj = value as Record<string, unknown>;
    if (Array.isArray(obj.items)) return obj.items as T[];
    if (Array.isArray(obj.rows)) return obj.rows as T[];
    if (Array.isArray(obj.preview_rows)) return obj.preview_rows as T[];
  }
  return [];
}

function numberOrNull(value: unknown): number | null {
  if (value == null || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function firstNumber(...values: unknown[]): number | null {
  for (const value of values) {
    const parsed = numberOrNull(value);
    if (parsed != null) return parsed;
  }
  return null;
}

function errorStatus(error: unknown): number | null {
  if (!error || typeof error !== "object") return null;
  return numberOrNull((error as { status?: unknown }).status);
}

function coverageTone(
  value: number | null,
  destructive = false,
): "success" | "warning" | "destructive" {
  if (destructive) return "destructive";
  const pct = value ?? 0;
  if (pct >= 95) return "success";
  if (pct >= 70) return "warning";
  return "destructive";
}

function toneClasses(tone: "success" | "warning" | "destructive" | "neutral") {
  const map = {
    success:
      "border-emerald-500/25 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
    warning:
      "border-amber-500/25 bg-amber-500/10 text-amber-700 dark:text-amber-300",
    destructive:
      "border-rose-500/25 bg-rose-500/10 text-rose-700 dark:text-rose-300",
    neutral: "border-border bg-muted/30 text-muted-foreground",
  };
  return map[tone];
}

function formatImportStatus(status?: string | null): string {
  const map: Record<string, string> = {
    validated: "предпросмотр",
    validated_with_errors: "предпросмотр с ошибками",
    processed: "применён",
    processed_with_errors: "применён с ошибками",
    uploaded: "загружен",
    previewed: "предпросмотр",
    committed: "подтверждён",
    confirmed: "подтверждён",
    failed: "ошибка",
    error: "ошибка",
    processing: "обработка",
    pending: "ожидает",
  };
  return map[String(status || "").toLowerCase()] ?? (status || "—");
}

function uploadTime(
  upload: ManualCostUpload | null | undefined,
): string | null {
  return (upload?.uploaded_at ??
    upload?.imported_at ??
    upload?.created_at ??
    null) as string | null;
}

function uploadRowsCommitted(upload: ManualCostUpload): number | null {
  const direct = numberOrNull(upload.rows_committed);
  if (direct != null) return direct;
  const summary = upload.summary;
  if (summary && typeof summary === "object") {
    return firstNumber((summary as Record<string, unknown>).rowsCommitted);
  }
  return null;
}

function CostsPage() {
  const { activeId } = useAccounts();
  const { user } = useAuth();
  const routeSearch = Route.useSearch();
  const queryClient = useQueryClient();
  const { from: dateFrom, to: dateTo } = useDateRange();

  const [tab, setTab] = useState<WorkTab>("table");
  const [view, setView] = useState<RowView>("all");
  const [file, setFile] = useState<File | null>(null);
  const [pendingUpload, setPendingUpload] = useState<ManualCostUpload | null>(
    null,
  );
  const [search, setSearch] = useState("");
  const [offset, setOffset] = useState(0);
  const [costDrafts, setCostDrafts] = useState<Record<string, string>>({});
  const [otherDrafts, setOtherDrafts] = useState<Record<string, string>>({});

  const focus = routeSearch.focus;

  const recordActionCenterCostFix = (comment: string) => {
    void appendActionCenterProblemHistory({
      accountId: activeId,
      problemInstanceId: routeSearch.problem_instance_id,
      comment,
    }).catch((error) =>
      toast.error(error?.message ?? "Не удалось обновить историю задачи"),
    );
  };

  const invalidateCosts = () => {
    queryClient.invalidateQueries({ queryKey: ["costs-rows"] });
    queryClient.invalidateQueries({ queryKey: ["costs-missing"] });
    queryClient.invalidateQueries({ queryKey: ["costs-unresolved"] });
    queryClient.invalidateQueries({ queryKey: ["costs-imports"] });
    queryClient.invalidateQueries({ queryKey: ["dashboard-data-health"] });
    queryClient.invalidateQueries({ queryKey: ["money-data-blockers"] });
    queryClient.invalidateQueries({ queryKey: ["dash-data-blockers"] });
    queryClient.invalidateQueries({ queryKey: ["dq-issues-summary"] });
    queryClient.invalidateQueries({ queryKey: ["portal-actions"] });
    queryClient.invalidateQueries({ queryKey: ["portal-products"] });
  };

  useEffect(() => {
    setOffset(0);
  }, [activeId, dateFrom, dateTo]);

  useEffect(() => {
    setOffset(0);
  }, [search, view]);

  useEffect(() => {
    setCostDrafts({});
    setOtherDrafts({});
    setPendingUpload(null);
    setFile(null);
  }, [activeId]);

  useEffect(() => {
    if (routeSearch.q) setSearch(routeSearch.q);
  }, [routeSearch.q]);

  useEffect(() => {
    if (focus === "missing-costs") {
      setView("missing");
      setTab("table");
    } else if (focus === "other-expenses") {
      setView("other");
      setTab("table");
    } else if (focus === "relink-sku") {
      setTab("links");
    } else if (focus === "upload") {
      setTab("import");
    } else if (focus === "table") {
      setTab("table");
    }
  }, [focus]);

  const bizParams = activeId
    ? { accountId: activeId, dateFrom, dateTo, limit: PAGE_SIZE, offset }
    : null;

  const healthQ = useQuery({
    queryKey: ["dashboard-data-health", activeId, dateFrom, dateTo],
    enabled: !!activeId,
    queryFn: () =>
      api<DashboardDataHealth>(API_ENDPOINTS.dashboard.dataHealth, {
        query: { account_id: activeId!, date_from: dateFrom, date_to: dateTo },
      }),
    staleTime: 45_000,
  });

  const rowsQ = useQuery({
    queryKey: ["costs-rows", activeId, offset],
    enabled: !!bizParams,
    queryFn: () =>
      fetchCostsRows(bizParams!) as Promise<Paginated<ManualCostRow>>,
    staleTime: 45_000,
    placeholderData: keepPreviousData,
  });

  const missingQ = useQuery({
    queryKey: ["costs-missing", activeId, dateFrom, dateTo],
    enabled: !!activeId,
    queryFn: () =>
      fetchCostsMissing(activeId!, {
        limit: 200,
        offset: 0,
        dateFrom,
        dateTo,
        onlyRevenue: false,
      }) as Promise<CostsMissingResponse>,
    staleTime: 45_000,
    retry: false,
  });

  const unresolvedQ = useQuery({
    queryKey: ["costs-unresolved", activeId],
    enabled: !!activeId,
    queryFn: () => fetchCostsUnresolved(activeId!),
    select: (data) => toArray<ManualCostRow>(data),
    staleTime: 45_000,
  });

  const importsQ = useQuery({
    queryKey: ["costs-imports", activeId],
    enabled: !!activeId,
    queryFn: () => fetchCostsImports(activeId),
    select: (data) => toArray<ManualCostUpload>(data),
    staleTime: 45_000,
  });

  const previewQ = useQuery({
    queryKey: ["costs-preview", pendingUpload?.id],
    enabled: !!pendingUpload?.id,
    queryFn: () => previewCostsUpload(pendingUpload!.id),
  });

  const upload = useMutation({
    mutationFn: async () => {
      if (!file || !activeId) throw new Error("Нужен файл и активный кабинет");
      const fd = new FormData();
      fd.append("account_id", String(activeId));
      fd.append("commit_rows", "false");
      fd.append("file", file);
      const result = (await uploadCostsFile(fd)) as
        | ManualCostUpload
        | { upload: ManualCostUpload };
      return result && typeof result === "object" && "upload" in result
        ? result.upload
        : (result as ManualCostUpload);
    },
    onSuccess: (data) => {
      setPendingUpload(data);
      queryClient.invalidateQueries({ queryKey: ["costs-imports"] });
      toast.success("Предпросмотр готов");
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const confirm = useMutation({
    mutationFn: async () => {
      if (!pendingUpload)
        throw new Error("Нет предпросмотра для подтверждения");
      return confirmCostsUpload(pendingUpload.id);
    },
    onSuccess: () => {
      setPendingUpload(null);
      setFile(null);
      invalidateCosts();
      recordActionCenterCostFix(
        "Себестоимость подтверждена и применена в новом рабочем экране.",
      );
      toast.success("Импорт применён");
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const relink = useMutation({
    mutationFn: () =>
      api(API_ENDPOINTS.costs.relink, {
        method: "POST",
        query: { account_id: activeId ?? undefined },
      }),
    onSuccess: () => {
      invalidateCosts();
      recordActionCenterCostFix(
        "SKU перепривязан в новом рабочем экране себестоимости.",
      );
      toast.success("Перепривязка выполнена");
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const refreshMarts = useMutation<RefreshMartsResult, Error>({
    mutationFn: async () => {
      try {
        await api("/marts/refresh", {
          method: "POST",
          query: { account_id: activeId ?? undefined },
        });
        return { skipped: false };
      } catch (error: unknown) {
        const status = errorStatus(error);
        if (status === 404 || status === 405) return { skipped: true };
        throw error;
      }
    },
    onSuccess: (result) => {
      invalidateCosts();
      if (result.skipped) {
        toast.message("Витрины обновятся автоматически");
      } else {
        toast.success("Витрины обновлены");
      }
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const runDq = useMutation({
    mutationFn: () =>
      api(API_ENDPOINTS.dq.run, {
        method: "POST",
        body: { account_id: activeId },
      }),
    onSuccess: () => {
      invalidateCosts();
      toast.success("Качество данных пересчитано");
    },
    onError: (error: Error) => {
      toast.error(error.message ?? "Не удалось пересчитать качество данных");
    },
  });

  const allCostRows = useMemo<CostGridRow[]>(() => {
    const existing = (rowsQ.data?.items ?? []).map((row) => {
      const raw = row as Record<string, unknown>;
      const legacyOther =
        row.packaging_cost != null || row.inbound_logistics_cost != null
          ? Number(row.packaging_cost ?? 0) +
            Number(row.inbound_logistics_cost ?? 0)
          : null;
      const sellerOther =
        raw.seller_other_expense != null
          ? Number(raw.seller_other_expense)
          : legacyOther;
      return {
        key: `cost:${row.id}`,
        source: "existing" as const,
        costId: row.id,
        sku_id: numberOrNull(raw.sku_id),
        nm_id: row.nm_id,
        vendor_code: row.vendor_code,
        barcode: row.barcode,
        tech_size: typeof raw.tech_size === "string" ? raw.tech_size : null,
        product_title:
          typeof raw.product_title === "string" ? raw.product_title : null,
        cost_price: row.cost_price,
        seller_other_expense: sellerOther,
        supplier: row.supplier,
        trust: raw.cost_truth_level ?? raw.truth_level ?? row.cost_source,
        business_trusted: raw.is_business_trusted ?? null,
        supplier_confirmed:
          raw.is_supplier_confirmed ?? raw.supplier_confirmed ?? null,
        valid_from: row.valid_from,
        valid_to: row.valid_to,
        comment: typeof raw.comment === "string" ? raw.comment : null,
        affected_revenue: null,
      };
    });

    const missing = (missingQ.data?.items ?? []).map((item, index) => ({
      key: `missing:${item.sku_id ?? item.nm_id ?? item.vendor_code ?? item.barcode ?? index}`,
      source: "missing" as const,
      sku_id: item.sku_id ?? null,
      nm_id: item.nm_id ?? null,
      vendor_code: item.vendor_code ?? null,
      barcode: item.barcode ?? null,
      tech_size: item.tech_size ?? null,
      product_title: item.product_title ?? null,
      cost_price: null,
      seller_other_expense: null,
      supplier: "OPERATOR_TRUSTED_COST",
      trust: "missing",
      business_trusted: false,
      supplier_confirmed: false,
      valid_from: null,
      valid_to: null,
      comment: null,
      affected_revenue: item.affected_revenue ?? null,
    }));

    return [...missing, ...existing];
  }, [missingQ.data, rowsQ.data]);

  const visibleRows = useMemo(() => {
    const q = search.trim().toLowerCase();
    return allCostRows.filter((row) => {
      if (view === "missing" && row.source !== "missing") return false;
      if (view === "other" && row.seller_other_expense != null) return false;
      if (!q) return true;
      return [
        row.sku_id,
        row.nm_id,
        row.vendor_code,
        row.barcode,
        row.tech_size,
        row.product_title,
        row.supplier,
      ].some((value) =>
        String(value ?? "")
          .toLowerCase()
          .includes(q),
      );
    });
  }, [allCostRows, search, view]);

  const changedRows = useMemo(() => {
    return allCostRows.filter((row) => {
      const costDraft = parseNonNegativeDraft(costDrafts[row.key]);
      const otherDraft = parseNonNegativeDraft(otherDrafts[row.key]);
      const currentCost =
        row.cost_price == null ? null : Number(row.cost_price);
      const currentOther =
        row.seller_other_expense == null ? 0 : Number(row.seller_other_expense);

      if (row.source === "missing") {
        return costDraft.touched && costDraft.valid;
      }

      return (
        (costDraft.touched &&
          costDraft.valid &&
          moneyChanged(costDraft.value, currentCost)) ||
        (otherDraft.touched &&
          otherDraft.valid &&
          moneyChanged(otherDraft.value, currentOther))
      );
    });
  }, [allCostRows, costDrafts, otherDrafts]);

  const invalidDraftCount = useMemo(() => {
    return allCostRows.filter((row) => {
      const costDraft = parseNonNegativeDraft(costDrafts[row.key]);
      const otherDraft = parseNonNegativeDraft(otherDrafts[row.key]);
      if (costDraft.touched && !costDraft.valid) return true;
      if (otherDraft.touched && !otherDraft.valid) return true;
      if (
        row.source === "missing" &&
        otherDraft.touched &&
        !(costDraft.touched && costDraft.valid)
      ) {
        return true;
      }
      return false;
    }).length;
  }, [allCostRows, costDrafts, otherDrafts]);

  const inlineSave = useMutation({
    mutationFn: async () => {
      if (!activeId) throw new Error("Выберите кабинет");
      if (!changedRows.length) throw new Error("Нет изменений для сохранения");
      return saveInlineCosts({
        account_id: activeId,
        rows: changedRows.map((row) => {
          const costDraft = parseNonNegativeDraft(costDrafts[row.key]);
          const otherDraft = parseNonNegativeDraft(otherDrafts[row.key]);
          return {
            cost_id: row.costId,
            sku_id: row.sku_id,
            cost_price: costDraft.touched ? costDraft.value : row.cost_price,
            seller_other_expense: otherDraft.touched
              ? otherDraft.value
              : (row.seller_other_expense ?? 0),
            valid_from: row.source === "missing" ? dateFrom : undefined,
            supplier: "OPERATOR_TRUSTED_COST",
            comment:
              row.source === "missing"
                ? "Заполнено вручную в новом экране себестоимости"
                : "Обновлено вручную в новом экране себестоимости",
          };
        }),
      });
    },
    onSuccess: () => {
      setCostDrafts({});
      setOtherDrafts({});
      invalidateCosts();
      recordActionCenterCostFix(
        "Себестоимость сохранена вручную, качество данных пересчитано.",
      );
      toast.success("Изменения сохранены");
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const downloadTemplate = async (
    format: "csv" | "xlsx",
    mode: "missing" | "all" = "missing",
  ) => {
    if (!activeId) return;
    try {
      const response = (await api<Response>(API_ENDPOINTS.costs.template, {
        query: {
          account_id: activeId,
          format,
          mode,
          date_from: dateFrom,
          date_to: dateTo,
        },
        raw: true,
      })) as unknown as Response;
      if (!response.ok)
        throw new Error(`Шаблон недоступен (HTTP ${response.status})`);

      const cd = response.headers.get("content-disposition") || "";
      const match = cd.match(/filename\*?=(?:UTF-8'')?"?([^";]+)"?/i);
      const filename = match
        ? decodeURIComponent(match[1])
        : `manual_cost_template_${mode}.${format}`;
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = filename;
      anchor.click();
      URL.revokeObjectURL(url);
    } catch (error) {
      toast.error((error as Error).message);
    }
  };

  const health = (healthQ.data ?? {}) as DashboardDataHealth &
    Record<string, unknown>;
  const costCoverage = (health.cost_coverage ?? {}) as Record<string, unknown>;
  const skuCoverage = firstNumber(
    costCoverage.operational_cost_coverage_percent,
    health.sku_cost_coverage_percent,
    health.revenue_cost_coverage_percent,
  );
  const businessCoverage = firstNumber(
    costCoverage.business_accepted_cost_coverage_percent,
    health.business_accepted_cost_coverage_percent,
    health.business_trusted_cost_coverage_percent,
    health.trusted_revenue_cost_coverage_percent,
  );
  const supplierCoverage = firstNumber(
    costCoverage.supplier_confirmed_cost_coverage_percent,
    health.supplier_confirmed_cost_coverage_percent,
    health.supplier_confirmed_revenue_coverage_percent,
    health.real_revenue_cost_coverage_percent,
  );
  const missingCount =
    firstNumber(
      health.missing_manual_cost_count,
      missingQ.data?.summary?.missing_sku_count,
    ) ?? 0;
  const missingRevenue = firstNumber(
    costCoverage.missing_cost_revenue,
    health.missing_manual_cost_revenue,
    health.missing_cost_revenue,
    health.revenue_without_manual_cost,
    missingQ.data?.summary?.affected_revenue,
  );
  const unresolvedCount = unresolvedQ.data?.length ?? 0;
  const missingOtherExpenseCount = allCostRows.filter(
    (row) => row.seller_other_expense == null,
  ).length;
  const finalProfit = Boolean(
    health.financial_final ??
    costCoverage.can_use_for_final_profit ??
    (supplierCoverage ?? 0) >= 95,
  );
  const supplierZero = (supplierCoverage ?? 0) <= 0;
  const lastImport = importsQ.data?.[0] ?? null;
  const previewData =
    previewQ.data && typeof previewQ.data === "object"
      ? (previewQ.data as Record<string, unknown>)
      : {};
  const previewRows = toArray<Record<string, unknown>>(previewQ.data);
  const previewValid = firstNumber(
    previewData.rows_valid,
    previewData.valid_count,
    pendingUpload?.rows_valid,
    previewRows.filter(
      (row) => !row.invalid_reason && row.is_valid !== false && !row.error,
    ).length,
  );
  const previewInvalid = firstNumber(
    previewData.rows_invalid,
    previewData.invalid_count,
    pendingUpload?.rows_invalid,
    previewRows.filter(
      (row) => row.invalid_reason || row.is_valid === false || row.error,
    ).length,
  );

  const saveDisabled =
    !changedRows.length || invalidDraftCount > 0 || inlineSave.isPending;

  const setRowDraft = (kind: "cost" | "other", key: string, value: string) => {
    if (kind === "cost") {
      setCostDrafts((current) => ({ ...current, [key]: value }));
    } else {
      setOtherDrafts((current) => ({ ...current, [key]: value }));
    }
  };

  const clearDrafts = () => {
    setCostDrafts({});
    setOtherDrafts({});
  };

  const loading = healthQ.isLoading || rowsQ.isLoading;

  return (
    <PageShell>
      <PageHeader
        title="Себестоимость"
        description="Рабочий экран для цены закупки, прочих расходов, доверия к прибыли и импорта от поставщика."
        actions={
          <div className="flex flex-wrap items-center gap-2">
            {user?.is_superuser ? (
              <ExportButton
                endpoint={API_ENDPOINTS.exports.missingCosts}
                filenamePrefix="missing_costs"
                query={{ account_id: activeId }}
                label="Экспорт"
              />
            ) : null}
            <Button
              size="sm"
              variant="outline"
              onClick={() => downloadTemplate("xlsx")}
              disabled={!activeId}
            >
              <Download className="h-3.5 w-3.5" />
              XLSX
            </Button>
            <Button
              size="sm"
              variant="outline"
              disabled={!activeId || healthQ.isFetching || rowsQ.isFetching}
              onClick={invalidateCosts}
            >
              <RefreshCw
                className={cn(
                  "h-3.5 w-3.5",
                  (healthQ.isFetching || rowsQ.isFetching) && "animate-spin",
                )}
              />
              Обновить
            </Button>
          </div>
        }
      />

      <ActionCenterReturnLink
        problem_instance_id={routeSearch.problem_instance_id}
        nm_id={routeSearch.nm_id}
        className="mb-4"
      />

      {!activeId ? (
        <Alert>
          <AlertCircle className="h-4 w-4" />
          <AlertTitle>Кабинет не выбран</AlertTitle>
          <AlertDescription>
            Выберите кабинет в верхней панели, чтобы открыть рабочий экран
            себестоимости.
          </AlertDescription>
        </Alert>
      ) : (
        <>
          <DataDependencyNotice
            accountId={activeId}
            domains={["product_cards", "sales", "finance"]}
          />

          <section className="mt-4 overflow-hidden rounded-lg border bg-background">
            <div className="grid gap-0 lg:grid-cols-[minmax(0,1.1fr)_minmax(360px,0.9fr)]">
              <div className="border-b p-4 lg:border-b-0 lg:border-r">
                <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge
                        variant="outline"
                        className={cn(
                          "gap-1",
                          toneClasses(finalProfit ? "success" : "warning"),
                        )}
                      >
                        {finalProfit ? (
                          <ShieldCheck className="h-3 w-3" />
                        ) : (
                          <ShieldAlert className="h-3 w-3" />
                        )}
                        {finalProfit
                          ? "Финальная прибыль"
                          : "Предварительная прибыль"}
                      </Badge>
                      {supplierZero ? (
                        <Badge
                          variant="outline"
                          className="border-amber-500/30 text-amber-700 dark:text-amber-300"
                        >
                          supplier 0%
                        </Badge>
                      ) : null}
                    </div>
                    <h2 className="mt-3 text-2xl font-semibold tracking-normal">
                      {finalProfit
                        ? "Данные готовы для финальной экономики"
                        : "Сначала закройте доверие к себестоимости"}
                    </h2>
                    <div className="mt-2 flex flex-wrap gap-4 text-sm text-muted-foreground">
                      <span>
                        Без себестоимости:{" "}
                        <b className="text-foreground">
                          {formatNumber(missingCount)}
                        </b>
                      </span>
                      <span>
                        Выручка в риске:{" "}
                        <b className="text-foreground">
                          {missingRevenue == null
                            ? "—"
                            : formatMoney(missingRevenue)}
                        </b>
                      </span>
                      <span>
                        Непривязано:{" "}
                        <b className="text-foreground">
                          {formatNumber(unresolvedCount)}
                        </b>
                      </span>
                    </div>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <Button size="sm" onClick={() => setView("missing")}>
                      <Wrench className="h-3.5 w-3.5" />
                      Закрыть блокеры
                    </Button>
                    <Button size="sm" variant="outline" asChild>
                      <Link to="/money">
                        Деньги
                        <ArrowRight className="h-3.5 w-3.5" />
                      </Link>
                    </Button>
                  </div>
                </div>
              </div>

              <div className="grid gap-3 p-4 sm:grid-cols-3 lg:grid-cols-1 xl:grid-cols-3">
                <CoverageTile
                  title="Операционная"
                  value={skuCoverage}
                  hint={`${formatNumber(health.active_sku_with_manual_cost_count)} / ${formatNumber(health.active_sku_count)} SKU`}
                  icon={<Wallet className="h-4 w-4" />}
                  loading={healthQ.isLoading}
                />
                <CoverageTile
                  title="Принята бизнесом"
                  value={businessCoverage}
                  hint="operator baseline + supplier"
                  icon={<PackageCheck className="h-4 w-4" />}
                  loading={healthQ.isLoading}
                />
                <CoverageTile
                  title="Поставщик"
                  value={supplierCoverage}
                  hint="финальный уровень"
                  icon={<ShieldCheck className="h-4 w-4" />}
                  loading={healthQ.isLoading}
                  critical={supplierZero}
                />
              </div>
            </div>
          </section>

          <section className="mt-4 rounded-lg border bg-background">
            <div className="grid gap-0 lg:grid-cols-[minmax(0,1fr)_320px]">
              <div className="border-b p-4 lg:border-b-0 lg:border-r">
                <div className="grid gap-3 md:grid-cols-3">
                  <SignalButton
                    active={view === "missing"}
                    icon={<AlertCircle className="h-4 w-4" />}
                    title="Нет себестоимости"
                    value={formatNumber(missingQ.data?.total ?? 0)}
                    detail={
                      missingRevenue == null
                        ? "выручка не посчитана"
                        : formatMoney(missingRevenue)
                    }
                    onClick={() => {
                      setView("missing");
                      setTab("table");
                    }}
                  />
                  <SignalButton
                    active={view === "other"}
                    icon={<Sparkles className="h-4 w-4" />}
                    title="Прочие расходы"
                    value={formatNumber(missingOtherExpenseCount)}
                    detail="упаковка, подготовка, прочее"
                    onClick={() => {
                      setView("other");
                      setTab("table");
                    }}
                  />
                  <SignalButton
                    active={tab === "links"}
                    icon={<Link2 className="h-4 w-4" />}
                    title="Связь SKU"
                    value={formatNumber(unresolvedCount)}
                    detail="непривязанные строки"
                    onClick={() => setTab("links")}
                  />
                </div>
              </div>
              <div className="p-4">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="text-xs text-muted-foreground">
                      Последний импорт
                    </div>
                    <div className="mt-1 truncate text-sm font-medium">
                      {lastImport?.filename ?? "Файлов пока нет"}
                    </div>
                    <div className="mt-1 text-xs text-muted-foreground">
                      {formatDateTime(uploadTime(lastImport))}
                    </div>
                  </div>
                  {lastImport ? (
                    <Badge variant="outline" className="shrink-0">
                      {formatImportStatus(lastImport.status)}
                    </Badge>
                  ) : null}
                </div>
                <div className="mt-3 flex flex-wrap gap-2">
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => setTab("import")}
                  >
                    <FileUp className="h-3.5 w-3.5" />
                    Импорт
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => setTab("history")}
                  >
                    <History className="h-3.5 w-3.5" />
                    История
                  </Button>
                </div>
              </div>
            </div>
          </section>

          <Tabs
            value={tab}
            onValueChange={(value) => setTab(value as WorkTab)}
            className="mt-4"
          >
            <div className="flex flex-col gap-3 rounded-lg border bg-background p-3 lg:flex-row lg:items-center lg:justify-between">
              <TabsList className="grid h-auto w-full grid-cols-4 lg:w-auto">
                <TabsTrigger value="table" className="gap-1.5">
                  <FileSpreadsheet className="h-3.5 w-3.5" />
                  Таблица
                </TabsTrigger>
                <TabsTrigger value="import" className="gap-1.5">
                  <Upload className="h-3.5 w-3.5" />
                  Импорт
                </TabsTrigger>
                <TabsTrigger value="links" className="gap-1.5">
                  <Link2 className="h-3.5 w-3.5" />
                  Связи
                </TabsTrigger>
                <TabsTrigger value="history" className="gap-1.5">
                  <History className="h-3.5 w-3.5" />
                  История
                </TabsTrigger>
              </TabsList>

              <div className="flex flex-wrap items-center gap-2">
                <Button
                  size="sm"
                  variant="outline"
                  disabled={!activeId || refreshMarts.isPending}
                  onClick={() => refreshMarts.mutate()}
                >
                  {refreshMarts.isPending ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <Database className="h-3.5 w-3.5" />
                  )}
                  Витрины
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  disabled={!activeId || runDq.isPending}
                  onClick={() => runDq.mutate()}
                >
                  {runDq.isPending ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <ClipboardCheck className="h-3.5 w-3.5" />
                  )}
                  DQ
                </Button>
              </div>
            </div>

            <TabsContent value="table" className="mt-4">
              <section className={dataGridShellClass}>
                <div className="border-b bg-background p-4">
                  <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <h3 className="text-base font-semibold">
                          Рабочая таблица
                        </h3>
                        {rowsQ.isFetching || missingQ.isFetching ? (
                          <Badge
                            variant="outline"
                            className="gap-1 text-muted-foreground"
                          >
                            <Loader2 className="h-3 w-3 animate-spin" />
                            обновление
                          </Badge>
                        ) : null}
                        {changedRows.length ? (
                          <Badge
                            variant="outline"
                            className="border-primary/40 text-primary"
                          >
                            {changedRows.length} измен.
                          </Badge>
                        ) : null}
                      </div>
                      <div className="mt-1 text-sm text-muted-foreground">
                        Плотная таблица для закупочной цены, прочих расходов и
                        блокирующих SKU.
                      </div>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      <Button
                        size="sm"
                        disabled={saveDisabled}
                        onClick={() => inlineSave.mutate()}
                      >
                        {inlineSave.isPending ? (
                          <Loader2 className="h-3.5 w-3.5 animate-spin" />
                        ) : (
                          <Save className="h-3.5 w-3.5" />
                        )}
                        Сохранить
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={clearDrafts}
                        disabled={!changedRows.length || inlineSave.isPending}
                      >
                        Сбросить
                      </Button>
                    </div>
                  </div>

                  <div className="mt-4 flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
                    <div className="flex flex-wrap items-center gap-2">
                      <FilterButton
                        active={view === "all"}
                        onClick={() => setView("all")}
                      >
                        Все
                      </FilterButton>
                      <FilterButton
                        active={view === "missing"}
                        onClick={() => setView("missing")}
                      >
                        Нет цены · {formatNumber(missingQ.data?.total ?? 0)}
                      </FilterButton>
                      <FilterButton
                        active={view === "other"}
                        onClick={() => setView("other")}
                      >
                        Прочие · {formatNumber(missingOtherExpenseCount)}
                      </FilterButton>
                    </div>
                    <div className="relative w-full lg:w-80">
                      <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
                      <Input
                        value={search}
                        onChange={(event) => setSearch(event.target.value)}
                        className="h-9 pl-8"
                        placeholder="SKU, nm_id, артикул, баркод"
                      />
                    </div>
                  </div>

                  {invalidDraftCount > 0 ? (
                    <Alert className="mt-3 border-rose-500/30 bg-rose-500/5">
                      <AlertCircle className="h-4 w-4 text-rose-600" />
                      <AlertTitle>Проверьте числа</AlertTitle>
                      <AlertDescription>
                        Можно сохранить только значения 0 или больше.
                      </AlertDescription>
                    </Alert>
                  ) : null}
                </div>

                {changedRows.length ? (
                  <div className="sticky top-16 z-20 border-b bg-background/95 px-4 py-2 backdrop-blur">
                    <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                      <div className="text-sm">
                        <b>{changedRows.length}</b> строк готово к сохранению
                        {invalidDraftCount ? (
                          <span className="text-rose-600">
                            {" "}
                            · {invalidDraftCount} с ошибкой
                          </span>
                        ) : null}
                      </div>
                      <div className="flex gap-2">
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={clearDrafts}
                          disabled={inlineSave.isPending}
                        >
                          Отменить
                        </Button>
                        <Button
                          size="sm"
                          onClick={() => inlineSave.mutate()}
                          disabled={saveDisabled}
                        >
                          {inlineSave.isPending ? (
                            <Loader2 className="h-3.5 w-3.5 animate-spin" />
                          ) : (
                            <Save className="h-3.5 w-3.5" />
                          )}
                          Сохранить
                        </Button>
                      </div>
                    </div>
                  </div>
                ) : null}

                <div className={cn(dataGridViewportClass, "max-h-[680px]")}>
                  {loading || (missingQ.isLoading && view === "missing") ? (
                    <TableSkeleton />
                  ) : (
                    <Table className={cn(dataGridTableClass, "min-w-[1280px]")}>
                      <TableHeader className="sticky top-0 z-30">
                        <TableRow>
                          <TableHead
                            className={cn(
                              dataGridHeadClass,
                              "sticky left-0 z-40 w-[118px]",
                            )}
                          >
                            Статус
                          </TableHead>
                          <TableHead
                            className={cn(
                              dataGridHeadClass,
                              "sticky left-[118px] z-40 min-w-[320px]",
                            )}
                          >
                            Товар
                          </TableHead>
                          <TableHead
                            className={cn(dataGridHeadClass, "w-[110px]")}
                          >
                            SKU
                          </TableHead>
                          <TableHead
                            className={cn(dataGridHeadClass, "w-[110px]")}
                          >
                            nm_id
                          </TableHead>
                          <TableHead
                            className={cn(dataGridHeadClass, "w-[160px]")}
                          >
                            Баркод
                          </TableHead>
                          <TableHead
                            className={cn(
                              dataGridHeadClass,
                              "w-[160px] text-right",
                            )}
                          >
                            Себестоимость
                          </TableHead>
                          <TableHead
                            className={cn(
                              dataGridHeadClass,
                              "w-[160px] text-right",
                            )}
                          >
                            Прочие
                          </TableHead>
                          <TableHead
                            className={cn(
                              dataGridHeadClass,
                              "w-[130px] text-right",
                            )}
                          >
                            Итого
                          </TableHead>
                          <TableHead
                            className={cn(
                              dataGridHeadClass,
                              "w-[150px] text-right",
                            )}
                          >
                            Риск
                          </TableHead>
                          <TableHead
                            className={cn(dataGridHeadClass, "w-[170px]")}
                          >
                            Доверие
                          </TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {visibleRows.map((row, rowIndex) => (
                          <CostRowEditor
                            key={row.key}
                            row={row}
                            rowIndex={rowIndex}
                            costValue={
                              costDrafts[row.key] ??
                              (row.cost_price == null
                                ? ""
                                : String(row.cost_price))
                            }
                            otherValue={
                              otherDrafts[row.key] ??
                              (row.seller_other_expense == null
                                ? ""
                                : String(row.seller_other_expense))
                            }
                            dirty={changedRows.some(
                              (changed) => changed.key === row.key,
                            )}
                            onCostChange={(value) =>
                              setRowDraft("cost", row.key, value)
                            }
                            onOtherChange={(value) =>
                              setRowDraft("other", row.key, value)
                            }
                          />
                        ))}
                        {!visibleRows.length ? (
                          <TableRow>
                            <TableCell
                              colSpan={10}
                              className="py-12 text-center"
                            >
                              <EmptyTableState view={view} search={search} />
                            </TableCell>
                          </TableRow>
                        ) : null}
                      </TableBody>
                    </Table>
                  )}
                </div>

                <div className="flex flex-col gap-2 border-t px-4 py-3 text-sm text-muted-foreground sm:flex-row sm:items-center sm:justify-between">
                  <span>
                    Показано {formatNumber(visibleRows.length)} · всего
                    сохранено{" "}
                    {formatNumber(
                      rowsQ.data?.total ?? rowsQ.data?.items?.length ?? 0,
                    )}
                  </span>
                  <div className="flex gap-2">
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={
                        offset === 0 || rowsQ.isFetching || view !== "all"
                      }
                      onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
                    >
                      <ChevronLeft className="h-3.5 w-3.5" />
                      Назад
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={
                        view !== "all" ||
                        rowsQ.isFetching ||
                        (rowsQ.data?.total != null
                          ? offset + PAGE_SIZE >= rowsQ.data.total
                          : (rowsQ.data?.items?.length ?? 0) < PAGE_SIZE)
                      }
                      onClick={() => setOffset(offset + PAGE_SIZE)}
                    >
                      Вперёд
                      <ChevronRight className="h-3.5 w-3.5" />
                    </Button>
                  </div>
                </div>
              </section>
            </TabsContent>

            <TabsContent value="import" className="mt-4">
              <section className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_360px]">
                <div className="rounded-lg border bg-background">
                  <div className="border-b p-4">
                    <div className="flex items-center gap-2">
                      <Upload className="h-4 w-4 text-primary" />
                      <h3 className="font-semibold">Импорт себестоимости</h3>
                    </div>
                    <div className="mt-1 text-sm text-muted-foreground">
                      Загрузите CSV/XLSX, проверьте предпросмотр и подтвердите
                      применение.
                    </div>
                  </div>
                  <div className="p-4">
                    <form
                      className="grid gap-3 lg:grid-cols-[auto_auto_minmax(240px,1fr)_auto]"
                      onSubmit={(event: FormEvent) => {
                        event.preventDefault();
                        upload.mutate();
                      }}
                    >
                      <Button
                        type="button"
                        variant="outline"
                        disabled={!activeId}
                        onClick={() => downloadTemplate("xlsx")}
                      >
                        <Download className="h-3.5 w-3.5" />
                        XLSX
                      </Button>
                      <Button
                        type="button"
                        variant="outline"
                        disabled={!activeId}
                        onClick={() => downloadTemplate("csv")}
                      >
                        <Download className="h-3.5 w-3.5" />
                        CSV
                      </Button>
                      <div>
                        <Label className="text-xs">Файл</Label>
                        <Input
                          type="file"
                          accept=".csv,.xlsx,.xls"
                          onChange={(event) =>
                            setFile(event.target.files?.[0] ?? null)
                          }
                        />
                      </div>
                      <Button
                        type="submit"
                        disabled={
                          !file ||
                          !activeId ||
                          upload.isPending ||
                          !!pendingUpload
                        }
                      >
                        {upload.isPending ? (
                          <Loader2 className="h-3.5 w-3.5 animate-spin" />
                        ) : (
                          <FileUp className="h-3.5 w-3.5" />
                        )}
                        Проверить
                      </Button>
                    </form>

                    {pendingUpload ? (
                      <div className="mt-4 rounded-lg border border-amber-500/25 bg-amber-500/5 p-4">
                        <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                          <div>
                            <div className="flex items-center gap-2 font-medium">
                              <Eye className="h-4 w-4 text-amber-700 dark:text-amber-300" />
                              Предпросмотр готов
                            </div>
                            <div className="mt-1 text-sm text-muted-foreground">
                              {pendingUpload.filename ?? "Файл"} ·{" "}
                              {formatNumber(
                                pendingUpload.rows_total ?? previewRows.length,
                              )}{" "}
                              строк
                            </div>
                          </div>
                          <div className="flex gap-2">
                            <Button
                              variant="outline"
                              onClick={() => {
                                setPendingUpload(null);
                                setFile(null);
                              }}
                            >
                              Отменить
                            </Button>
                            <Button
                              onClick={() => confirm.mutate()}
                              disabled={confirm.isPending}
                            >
                              {confirm.isPending ? (
                                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                              ) : (
                                <CheckCircle2 className="h-3.5 w-3.5" />
                              )}
                              Подтвердить
                            </Button>
                          </div>
                        </div>
                        <div className="mt-4 grid gap-3 sm:grid-cols-3">
                          <MiniMetric
                            label="Валидно"
                            value={formatNumber(previewValid)}
                            tone="success"
                          />
                          <MiniMetric
                            label="Ошибки"
                            value={formatNumber(previewInvalid)}
                            tone={previewInvalid ? "destructive" : "neutral"}
                          />
                          <MiniMetric
                            label="Статус"
                            value={formatImportStatus(pendingUpload.status)}
                            tone="warning"
                          />
                        </div>
                        {previewRows.length ? (
                          <div
                            className={cn(
                              dataGridViewportClass,
                              "mt-4 max-h-72 rounded-md border",
                            )}
                          >
                            <Table
                              className={cn(
                                dataGridTableClass,
                                "min-w-[820px]",
                              )}
                            >
                              <TableHeader className="sticky top-0 z-20">
                                <TableRow>
                                  <TableHead className={dataGridHeadClass}>
                                    Артикул
                                  </TableHead>
                                  <TableHead
                                    className={cn(
                                      dataGridHeadClass,
                                      "w-[120px]",
                                    )}
                                  >
                                    nm_id
                                  </TableHead>
                                  <TableHead
                                    className={cn(
                                      dataGridHeadClass,
                                      "w-[170px]",
                                    )}
                                  >
                                    Баркод
                                  </TableHead>
                                  <TableHead
                                    className={cn(
                                      dataGridHeadClass,
                                      "w-[140px] text-right",
                                    )}
                                  >
                                    Цена
                                  </TableHead>
                                  <TableHead
                                    className={cn(
                                      dataGridHeadClass,
                                      "w-[220px]",
                                    )}
                                  >
                                    Результат
                                  </TableHead>
                                </TableRow>
                              </TableHeader>
                              <TableBody>
                                {previewRows.slice(0, 20).map((row, index) => (
                                  <TableRow
                                    key={index}
                                    className="group transition-colors hover:bg-primary/5"
                                  >
                                    <TableCell
                                      className={cn(
                                        dataGridCellClass,
                                        index % 2
                                          ? "bg-muted/15"
                                          : "bg-background",
                                      )}
                                    >
                                      {String(
                                        row.vendor_code ??
                                          row.vendorCode ??
                                          "—",
                                      )}
                                    </TableCell>
                                    <TableCell
                                      className={cn(
                                        dataGridCellClass,
                                        "font-mono text-xs",
                                        index % 2
                                          ? "bg-muted/15"
                                          : "bg-background",
                                      )}
                                    >
                                      {String(row.nm_id ?? row.nmId ?? "—")}
                                    </TableCell>
                                    <TableCell
                                      className={cn(
                                        dataGridCellClass,
                                        "font-mono text-xs",
                                        index % 2
                                          ? "bg-muted/15"
                                          : "bg-background",
                                      )}
                                    >
                                      {String(row.barcode ?? "—")}
                                    </TableCell>
                                    <TableCell
                                      className={cn(
                                        dataGridCellClass,
                                        "text-right font-medium tabular-nums",
                                        index % 2
                                          ? "bg-muted/15"
                                          : "bg-background",
                                      )}
                                    >
                                      {formatMoney(
                                        numberOrNull(
                                          row.cost_price ?? row.costPrice,
                                        ),
                                      )}
                                    </TableCell>
                                    <TableCell
                                      className={cn(
                                        dataGridCellClass,
                                        index % 2
                                          ? "bg-muted/15"
                                          : "bg-background",
                                      )}
                                    >
                                      {row.invalid_reason || row.error ? (
                                        <Badge
                                          variant="outline"
                                          className="border-rose-500/30 text-rose-700 dark:text-rose-300"
                                        >
                                          {String(
                                            row.invalid_reason ?? row.error,
                                          )}
                                        </Badge>
                                      ) : (
                                        <Badge
                                          variant="outline"
                                          className="border-emerald-500/30 text-emerald-700 dark:text-emerald-300"
                                        >
                                          готово
                                        </Badge>
                                      )}
                                    </TableCell>
                                  </TableRow>
                                ))}
                              </TableBody>
                            </Table>
                          </div>
                        ) : null}
                      </div>
                    ) : null}
                  </div>
                </div>

                <div className="rounded-lg border bg-background p-4">
                  <div className="font-semibold">Операции после импорта</div>
                  <div className="mt-3 space-y-2">
                    <ActionLine
                      icon={<Link2 className="h-4 w-4" />}
                      title="Перепривязать SKU"
                      detail={`${formatNumber(unresolvedCount)} строк ждут связи`}
                      action={
                        <Button
                          size="sm"
                          variant="outline"
                          disabled={!activeId || relink.isPending}
                          onClick={() => relink.mutate()}
                        >
                          {relink.isPending ? (
                            <Loader2 className="h-3.5 w-3.5 animate-spin" />
                          ) : (
                            <Link2 className="h-3.5 w-3.5" />
                          )}
                        </Button>
                      }
                    />
                    <ActionLine
                      icon={<Database className="h-4 w-4" />}
                      title="Обновить витрины"
                      detail="profit, dashboard, money"
                      action={
                        <Button
                          size="sm"
                          variant="outline"
                          disabled={!activeId || refreshMarts.isPending}
                          onClick={() => refreshMarts.mutate()}
                        >
                          {refreshMarts.isPending ? (
                            <Loader2 className="h-3.5 w-3.5 animate-spin" />
                          ) : (
                            <RefreshCw className="h-3.5 w-3.5" />
                          )}
                        </Button>
                      }
                    />
                    <ActionLine
                      icon={<ClipboardCheck className="h-4 w-4" />}
                      title="Пересчитать DQ"
                      detail="закрыть блокеры"
                      action={
                        <Button
                          size="sm"
                          variant="outline"
                          disabled={!activeId || runDq.isPending}
                          onClick={() => runDq.mutate()}
                        >
                          {runDq.isPending ? (
                            <Loader2 className="h-3.5 w-3.5 animate-spin" />
                          ) : (
                            <CheckCircle2 className="h-3.5 w-3.5" />
                          )}
                        </Button>
                      }
                    />
                  </div>
                </div>
              </section>
            </TabsContent>

            <TabsContent value="links" className="mt-4">
              <section className={dataGridShellClass}>
                <div className="flex flex-col gap-3 border-b p-4 lg:flex-row lg:items-center lg:justify-between">
                  <div>
                    <h3 className="font-semibold">
                      Непривязанные строки себестоимости
                    </h3>
                    <div className="mt-1 text-sm text-muted-foreground">
                      Эти строки не попали в SKU из-за артикула, размера, nm_id
                      или баркода.
                    </div>
                  </div>
                  <Button
                    size="sm"
                    disabled={!unresolvedCount || relink.isPending}
                    onClick={() => relink.mutate()}
                  >
                    {relink.isPending ? (
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    ) : (
                      <Link2 className="h-3.5 w-3.5" />
                    )}
                    Перепривязать
                  </Button>
                </div>
                <div className={cn(dataGridViewportClass, "max-h-[560px]")}>
                  <Table className={cn(dataGridTableClass, "min-w-[860px]")}>
                    <TableHeader className="sticky top-0 z-20">
                      <TableRow>
                        <TableHead className={dataGridHeadClass}>
                          Артикул
                        </TableHead>
                        <TableHead
                          className={cn(dataGridHeadClass, "w-[120px]")}
                        >
                          nm_id
                        </TableHead>
                        <TableHead
                          className={cn(dataGridHeadClass, "w-[180px]")}
                        >
                          Баркод
                        </TableHead>
                        <TableHead
                          className={cn(dataGridHeadClass, "w-[120px]")}
                        >
                          Размер
                        </TableHead>
                        <TableHead
                          className={cn(
                            dataGridHeadClass,
                            "w-[140px] text-right",
                          )}
                        >
                          Цена
                        </TableHead>
                        <TableHead
                          className={cn(dataGridHeadClass, "w-[170px]")}
                        >
                          Статус
                        </TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {unresolvedQ.data?.map((row, index) => {
                        const rowBg =
                          index % 2 ? "bg-muted/15" : "bg-background";
                        return (
                          <TableRow
                            key={row.id}
                            className="group transition-colors"
                          >
                            <TableCell
                              className={cn(
                                dataGridCellClass,
                                rowBg,
                                "font-medium group-hover:bg-primary/5",
                              )}
                            >
                              {row.vendor_code ?? "—"}
                            </TableCell>
                            <TableCell
                              className={cn(
                                dataGridCellClass,
                                rowBg,
                                "font-mono text-xs group-hover:bg-primary/5",
                              )}
                            >
                              {row.nm_id ?? "—"}
                            </TableCell>
                            <TableCell
                              className={cn(
                                dataGridCellClass,
                                rowBg,
                                "font-mono text-xs group-hover:bg-primary/5",
                              )}
                            >
                              {row.barcode ?? "—"}
                            </TableCell>
                            <TableCell
                              className={cn(
                                dataGridCellClass,
                                rowBg,
                                "group-hover:bg-primary/5",
                              )}
                            >
                              {String(row.tech_size ?? "—")}
                            </TableCell>
                            <TableCell
                              className={cn(
                                dataGridCellClass,
                                rowBg,
                                "text-right font-medium tabular-nums group-hover:bg-primary/5",
                              )}
                            >
                              {formatMoney(row.cost_price)}
                            </TableCell>
                            <TableCell
                              className={cn(
                                dataGridCellClass,
                                rowBg,
                                "group-hover:bg-primary/5",
                              )}
                            >
                              <TrustBadge
                                level={String(
                                  row.cost_truth_level ??
                                    row.cost_source ??
                                    "manual_untrusted",
                                )}
                              />
                            </TableCell>
                          </TableRow>
                        );
                      })}
                      {!unresolvedQ.data?.length ? (
                        <TableRow>
                          <TableCell
                            colSpan={6}
                            className="py-12 text-center text-muted-foreground"
                          >
                            Все строки связаны с SKU
                          </TableCell>
                        </TableRow>
                      ) : null}
                    </TableBody>
                  </Table>
                </div>
              </section>
            </TabsContent>

            <TabsContent value="history" className="mt-4">
              <section className={dataGridShellClass}>
                <div className="border-b p-4">
                  <h3 className="font-semibold">История загрузок</h3>
                  <div className="mt-1 text-sm text-muted-foreground">
                    Файлы текущего кабинета и результат применения.
                  </div>
                </div>
                <div className={cn(dataGridViewportClass, "max-h-[560px]")}>
                  <Table className={cn(dataGridTableClass, "min-w-[860px]")}>
                    <TableHeader className="sticky top-0 z-20">
                      <TableRow>
                        <TableHead className={dataGridHeadClass}>
                          Файл
                        </TableHead>
                        <TableHead
                          className={cn(dataGridHeadClass, "w-[170px]")}
                        >
                          Статус
                        </TableHead>
                        <TableHead
                          className={cn(
                            dataGridHeadClass,
                            "w-[120px] text-right",
                          )}
                        >
                          Всего
                        </TableHead>
                        <TableHead
                          className={cn(
                            dataGridHeadClass,
                            "w-[140px] text-right",
                          )}
                        >
                          Применено
                        </TableHead>
                        <TableHead
                          className={cn(dataGridHeadClass, "w-[190px]")}
                        >
                          Когда
                        </TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {importsQ.data?.map((item, index) => {
                        const rowBg =
                          index % 2 ? "bg-muted/15" : "bg-background";
                        return (
                          <TableRow
                            key={item.id}
                            className="group transition-colors"
                          >
                            <TableCell
                              className={cn(
                                dataGridCellClass,
                                rowBg,
                                "max-w-[360px] group-hover:bg-primary/5",
                              )}
                            >
                              <div className="flex min-w-0 items-center gap-2">
                                <FileSpreadsheet className="h-4 w-4 shrink-0 text-muted-foreground" />
                                <span className="truncate font-medium">
                                  {item.filename ?? "—"}
                                </span>
                              </div>
                            </TableCell>
                            <TableCell
                              className={cn(
                                dataGridCellClass,
                                rowBg,
                                "group-hover:bg-primary/5",
                              )}
                            >
                              <Badge variant="outline">
                                {formatImportStatus(item.status)}
                              </Badge>
                            </TableCell>
                            <TableCell
                              className={cn(
                                dataGridCellClass,
                                rowBg,
                                "text-right tabular-nums group-hover:bg-primary/5",
                              )}
                            >
                              {formatNumber(item.rows_total)}
                            </TableCell>
                            <TableCell
                              className={cn(
                                dataGridCellClass,
                                rowBg,
                                "text-right font-medium tabular-nums group-hover:bg-primary/5",
                              )}
                            >
                              {formatNumber(uploadRowsCommitted(item))}
                            </TableCell>
                            <TableCell
                              className={cn(
                                dataGridCellClass,
                                rowBg,
                                "text-muted-foreground group-hover:bg-primary/5",
                              )}
                            >
                              {formatDateTime(uploadTime(item))}
                            </TableCell>
                          </TableRow>
                        );
                      })}
                      {!importsQ.data?.length ? (
                        <TableRow>
                          <TableCell
                            colSpan={5}
                            className="py-12 text-center text-muted-foreground"
                          >
                            Загрузок пока нет
                          </TableCell>
                        </TableRow>
                      ) : null}
                    </TableBody>
                  </Table>
                </div>
              </section>
            </TabsContent>
          </Tabs>
        </>
      )}
    </PageShell>
  );
}

function CoverageTile({
  title,
  value,
  hint,
  icon,
  loading,
  critical,
}: {
  title: string;
  value: number | null;
  hint: string;
  icon: ReactNode;
  loading: boolean;
  critical?: boolean;
}) {
  const tone = coverageTone(value, critical);
  return (
    <div className={cn("rounded-md border p-3", toneClasses(tone))}>
      <div className="flex items-center justify-between gap-2 text-xs">
        <span className="flex items-center gap-1.5">
          {icon}
          {title}
        </span>
        <span>{hint}</span>
      </div>
      {loading ? (
        <Skeleton className="mt-2 h-7 w-20" />
      ) : (
        <div className="mt-2 text-2xl font-semibold tabular-nums">
          {formatPercent(value)}
        </div>
      )}
      <Progress value={value ?? 0} className="mt-2 h-1.5" />
    </div>
  );
}

function SignalButton({
  active,
  icon,
  title,
  value,
  detail,
  onClick,
}: {
  active: boolean;
  icon: ReactNode;
  title: string;
  value: string;
  detail: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "rounded-md border p-3 text-left transition-colors hover:bg-muted/40",
        active ? "border-primary/45 bg-primary/5" : "bg-background",
      )}
    >
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 text-sm font-medium">
          {icon}
          {title}
        </div>
        <div className="text-xl font-semibold tabular-nums">{value}</div>
      </div>
      <div className="mt-1 text-xs text-muted-foreground">{detail}</div>
    </button>
  );
}

function FilterButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <Button
      type="button"
      size="sm"
      variant={active ? "default" : "outline"}
      onClick={onClick}
    >
      <Filter className="h-3.5 w-3.5" />
      {children}
    </Button>
  );
}

function CostRowEditor({
  row,
  rowIndex,
  costValue,
  otherValue,
  dirty,
  onCostChange,
  onOtherChange,
}: {
  row: CostGridRow;
  rowIndex: number;
  costValue: string;
  otherValue: string;
  dirty: boolean;
  onCostChange: (value: string) => void;
  onOtherChange: (value: string) => void;
}) {
  const parsedCost = parseNonNegativeDraft(costValue);
  const parsedOther = parseNonNegativeDraft(otherValue);
  const total =
    parsedCost.valid && parsedCost.value != null && parsedOther.valid
      ? parsedCost.value + (parsedOther.value ?? 0)
      : null;
  const missing = row.source === "missing";
  const invalidCost = parsedCost.touched && !parsedCost.valid;
  const invalidOther = parsedOther.touched && !parsedOther.valid;
  const rowBg = dirty
    ? "bg-primary/5"
    : missing
      ? "bg-rose-500/5"
      : rowIndex % 2
        ? "bg-muted/15"
        : "bg-background";
  const cellClass = (...extra: string[]) =>
    cn(dataGridCellClass, rowBg, "group-hover:bg-primary/5", ...extra);

  return (
    <TableRow
      className={cn(
        "group transition-colors",
        missing && "hover:bg-rose-500/10",
        dirty && "hover:bg-primary/10",
      )}
    >
      <TableCell className={cellClass("sticky left-0 z-10 w-[118px]")}>
        <div className="flex items-center gap-2">
          <span
            className={cn(
              "h-8 w-1 rounded-full",
              missing ? "bg-rose-500" : dirty ? "bg-primary" : "bg-emerald-500",
            )}
          />
          {missing ? (
            <Badge
              variant="outline"
              className="border-rose-500/30 text-rose-700 dark:text-rose-300"
            >
              нет цены
            </Badge>
          ) : dirty ? (
            <Badge variant="outline" className="border-primary/40 text-primary">
              изменено
            </Badge>
          ) : (
            <Badge
              variant="outline"
              className="border-emerald-500/25 text-emerald-700 dark:text-emerald-300"
            >
              сохранено
            </Badge>
          )}
        </div>
      </TableCell>
      <TableCell
        className={cellClass("sticky left-[118px] z-10 min-w-[320px]")}
      >
        <div className="max-w-[300px]">
          <div className="truncate text-sm font-semibold">
            {row.product_title ?? row.vendor_code ?? "—"}
          </div>
          <div className="mt-1 flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
            <span className="truncate">{row.vendor_code ?? "—"}</span>
            {row.tech_size ? (
              <span className="rounded border bg-background/70 px-1.5 py-0.5">
                {row.tech_size}
              </span>
            ) : null}
          </div>
        </div>
      </TableCell>
      <TableCell className={cellClass("font-mono text-xs")}>
        {row.sku_id ?? "—"}
      </TableCell>
      <TableCell className={cellClass("font-mono text-xs")}>
        {row.nm_id ?? "—"}
      </TableCell>
      <TableCell className={cellClass("font-mono text-xs")}>
        {row.barcode ?? "—"}
      </TableCell>
      <TableCell className={cellClass("text-right")}>
        <Input
          type="number"
          min="0"
          step="0.01"
          value={costValue}
          onChange={(event) => onCostChange(event.target.value)}
          placeholder="0"
          className={cn(
            "ml-auto h-8 w-36 border-muted-foreground/20 bg-background/80 text-right text-xs font-medium tabular-nums shadow-sm",
            invalidCost && "border-rose-500 bg-rose-500/5",
            missing && !costValue && "border-rose-500/45",
            dirty && !invalidCost && "border-primary/45 bg-primary/5",
          )}
        />
      </TableCell>
      <TableCell className={cellClass("text-right")}>
        <Input
          type="number"
          min="0"
          step="0.01"
          value={otherValue}
          onChange={(event) => onOtherChange(event.target.value)}
          placeholder="0"
          className={cn(
            "ml-auto h-8 w-36 border-muted-foreground/20 bg-background/80 text-right text-xs font-medium tabular-nums shadow-sm",
            invalidOther && "border-rose-500 bg-rose-500/5",
            dirty && !invalidOther && "border-primary/45 bg-primary/5",
          )}
        />
      </TableCell>
      <TableCell className={cellClass("text-right font-semibold tabular-nums")}>
        {total == null ? "—" : formatMoney(total)}
      </TableCell>
      <TableCell className={cellClass("text-right tabular-nums")}>
        {row.affected_revenue == null ? "—" : formatMoney(row.affected_revenue)}
      </TableCell>
      <TableCell className={cellClass()}>
        <div className="flex flex-wrap items-center gap-1.5">
          <TrustBadge
            level={row.trust ?? (missing ? "missing" : "operator_baseline")}
          />
          {row.supplier_confirmed ? (
            <Badge
              variant="outline"
              className="border-emerald-500/30 text-emerald-700 dark:text-emerald-300"
            >
              supplier
            </Badge>
          ) : null}
        </div>
      </TableCell>
    </TableRow>
  );
}

function TrustBadge({ level }: { level: string | null | undefined }) {
  const normalized = String(level || "").toLowerCase();
  const config =
    normalized === "supplier_confirmed"
      ? {
          label: "подтверждена",
          cls: "border-emerald-500/30 text-emerald-700 dark:text-emerald-300",
        }
      : normalized === "operator_baseline" ||
          normalized === "operator_trusted_manual"
        ? {
            label: "операторская",
            cls: "border-amber-500/30 text-amber-700 dark:text-amber-300",
          }
        : normalized === "placeholder"
          ? {
              label: "шаблон",
              cls: "border-rose-500/30 text-rose-700 dark:text-rose-300",
            }
          : normalized === "missing"
            ? {
                label: "нет данных",
                cls: "border-rose-500/30 text-rose-700 dark:text-rose-300",
              }
            : { label: level || "—", cls: "text-muted-foreground" };
  return (
    <Badge variant="outline" className={config.cls}>
      {config.label}
    </Badge>
  );
}

function MiniMetric({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone: "success" | "warning" | "destructive" | "neutral";
}) {
  return (
    <div className={cn("rounded-md border p-3", toneClasses(tone))}>
      <div className="text-xs opacity-80">{label}</div>
      <div className="mt-1 text-lg font-semibold">{value}</div>
    </div>
  );
}

function ActionLine({
  icon,
  title,
  detail,
  action,
}: {
  icon: ReactNode;
  title: string;
  detail: string;
  action: ReactNode;
}) {
  return (
    <div className="flex items-center justify-between gap-3 rounded-md border p-3">
      <div className="flex min-w-0 items-center gap-3">
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-muted text-muted-foreground">
          {icon}
        </div>
        <div className="min-w-0">
          <div className="truncate text-sm font-medium">{title}</div>
          <div className="truncate text-xs text-muted-foreground">{detail}</div>
        </div>
      </div>
      {action}
    </div>
  );
}

function TableSkeleton() {
  return (
    <div className="p-4">
      <div className="space-y-2">
        {Array.from({ length: 9 }).map((_, index) => (
          <Skeleton key={index} className="h-10 w-full" />
        ))}
      </div>
    </div>
  );
}

function EmptyTableState({ view, search }: { view: RowView; search: string }) {
  const copy = search
    ? "По этому поиску строк нет"
    : view === "missing"
      ? "SKU без себестоимости не найдены"
      : view === "other"
        ? "Строки без прочих расходов не найдены"
        : "Строки себестоимости ещё не загружены";
  return (
    <div className="mx-auto max-w-sm">
      <CheckCircle2 className="mx-auto h-8 w-8 text-muted-foreground" />
      <div className="mt-2 font-medium">{copy}</div>
      <div className="mt-1 text-sm text-muted-foreground">
        Можно загрузить файл или скачать шаблон для заполнения.
      </div>
    </div>
  );
}
