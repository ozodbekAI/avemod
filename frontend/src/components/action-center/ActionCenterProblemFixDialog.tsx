// @ts-nocheck
import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  ArrowRight,
  CheckCircle2,
  ExternalLink,
  Loader2,
  Wrench,
} from "lucide-react";
import { toast } from "sonner";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { formatMoney } from "@/lib/format";
import {
  fetchCostsMissing,
  saveInlineCosts,
  type CostsMissingItem,
} from "@/lib/money-endpoints";
import { problemImpactLabel, problemTrustLabel } from "@/lib/problem-ux-copy";
import { problemCodeLabel } from "@/lib/problem-ux-copy";
import type { ActionCenterGroup } from "@/lib/action-center-view-utils";
import type { ActionCenterItem } from "@/lib/action-center-contract";

const COST_FIX_CODES = new Set([
  "missing_cost_blocks_profit",
  "missing_manual_cost",
]);

const PRICE_REVIEW_CODES = new Set([
  "negative_unit_profit",
  "price_below_safe_margin",
  "promo_not_profitable",
  "ads_spend_without_profit",
]);

type FixMode = "missing_cost" | "price_review";

type Props = {
  open: boolean;
  accountId: number | null | undefined;
  dateFrom?: string | null;
  dateTo?: string | null;
  group: ActionCenterGroup | null;
  onOpenChange: (open: boolean) => void;
  onApplied: () => Promise<void> | void;
};

type CostDraft = {
  cost_price: string;
  seller_other_expense: string;
};

export function actionCenterProblemGroupFixMode(
  group: ActionCenterGroup | null | undefined,
): FixMode | null {
  const code = String(group?.problem_code ?? "").trim().toLowerCase();
  if (!code) return null;
  if (COST_FIX_CODES.has(code)) return "missing_cost";
  if (PRICE_REVIEW_CODES.has(code)) return "price_review";
  return null;
}

export function actionCenterProblemGroupFixLabel(
  group: ActionCenterGroup | null | undefined,
): string | null {
  const mode = actionCenterProblemGroupFixMode(group);
  if (mode === "missing_cost") return "Исправить группу";
  if (mode === "price_review") return "Разобрать группу";
  return null;
}

function rowKey(row: CostsMissingItem, index: number): string {
  return String(row.sku_id ?? row.nm_id ?? index);
}

function actionKey(action: ActionCenterItem, index: number): string {
  return String(action.problem_instance_id ?? action.source_id ?? action.nm_id ?? index);
}

function productLabel(row: CostsMissingItem | ActionCenterItem | null): string {
  if (!row) return "Товар";
  const parts = [
    row.nm_id ? `nm ${row.nm_id}` : null,
    row.vendor_code,
    "product_title" in row ? row.product_title : null,
  ].filter(Boolean);
  return parts.join(" / ") || "Товар без названия";
}

function parseMoneyDraft(value: string, optional = false): number | null {
  const trimmed = String(value ?? "").replace(",", ".").trim();
  if (!trimmed) return optional ? 0 : null;
  const parsed = Number(trimmed);
  if (!Number.isFinite(parsed) || parsed < 0) return null;
  return Math.round(parsed * 100) / 100;
}

function groupNmIds(group: ActionCenterGroup | null): Set<number> {
  const values = new Set<number>();
  for (const item of group?.items ?? []) {
    if (item.nm_id != null && Number.isFinite(Number(item.nm_id))) {
      values.add(Number(item.nm_id));
    }
  }
  return values;
}

function invalidateActionCenterFixQueries(qc: ReturnType<typeof useQueryClient>) {
  qc.invalidateQueries({ queryKey: ["portal-actions"] });
  qc.invalidateQueries({ queryKey: ["portal-results"] });
  qc.invalidateQueries({ queryKey: ["portal-problem-results"] });
  qc.invalidateQueries({ queryKey: ["costs-missing"] });
  qc.invalidateQueries({ queryKey: ["costs-rows"] });
  qc.invalidateQueries({ queryKey: ["costs-unresolved"] });
  qc.invalidateQueries({ queryKey: ["dashboard-data-health"] });
  qc.invalidateQueries({ queryKey: ["money-data-blockers"] });
  qc.invalidateQueries({ queryKey: ["dash-data-blockers"] });
  qc.invalidateQueries({ queryKey: ["dq-issues-summary"] });
}

export function ActionCenterProblemFixDialog({
  open,
  accountId,
  dateFrom,
  dateTo,
  group,
  onOpenChange,
  onApplied,
}: Props) {
  const qc = useQueryClient();
  const mode = actionCenterProblemGroupFixMode(group);
  const [costIndex, setCostIndex] = useState(0);
  const [reviewIndex, setReviewIndex] = useState(0);
  const [drafts, setDrafts] = useState<Record<string, CostDraft>>({});
  const [supplierConfirmed, setSupplierConfirmed] = useState(false);

  useEffect(() => {
    if (!open) return;
    setCostIndex(0);
    setReviewIndex(0);
    setDrafts({});
    setSupplierConfirmed(false);
  }, [group?.key, open]);

  const missingCostsQ = useQuery({
    queryKey: [
      "action-center-missing-cost-fix-context",
      accountId,
      group?.key,
      dateFrom,
      dateTo,
    ],
    queryFn: () =>
      fetchCostsMissing(accountId!, {
        limit: 200,
        offset: 0,
        dateFrom: dateFrom ?? undefined,
        dateTo: dateTo ?? undefined,
        onlyRevenue: true,
      }),
    enabled: open && mode === "missing_cost" && !!accountId,
    staleTime: 20_000,
  });

  const costRows = useMemo(() => {
    const rows = missingCostsQ.data?.items ?? [];
    const nmIds = groupNmIds(group);
    if (!nmIds.size) return rows;
    const filtered = rows.filter((row) => row.nm_id != null && nmIds.has(Number(row.nm_id)));
    return filtered.length ? filtered : rows;
  }, [group, missingCostsQ.data]);

  const reviewRows = group?.items ?? [];
  const currentCostRow = costRows[Math.min(costIndex, Math.max(costRows.length - 1, 0))] ?? null;
  const currentReviewRow = reviewRows[Math.min(reviewIndex, Math.max(reviewRows.length - 1, 0))] ?? null;

  const validCostRows = useMemo(() => {
    return costRows
      .map((row, index) => {
        const draft = drafts[rowKey(row, index)];
        const costPrice = parseMoneyDraft(draft?.cost_price ?? "");
        const sellerOtherExpense = parseMoneyDraft(draft?.seller_other_expense ?? "", true);
        if (row.sku_id == null || costPrice == null || sellerOtherExpense == null) return null;
        return {
          sku_id: row.sku_id,
          cost_price: costPrice,
          seller_other_expense: sellerOtherExpense,
          supplier: "OPERATOR_TRUSTED_COST",
          valid_from: dateFrom ?? undefined,
          is_supplier_confirmed: supplierConfirmed,
          comment: "Заполнено из Action Center: групповое исправление отсутствующей себестоимости",
        };
      })
      .filter(Boolean);
  }, [costRows, dateFrom, drafts, supplierConfirmed]);

  const filledCount = validCostRows.length;
  const progressValue =
    mode === "missing_cost"
      ? costRows.length
        ? Math.round((filledCount / costRows.length) * 100)
        : 0
      : reviewRows.length
        ? Math.round(((reviewIndex + 1) / reviewRows.length) * 100)
        : 0;

  const saveCosts = useMutation({
    mutationFn: async () => {
      if (!accountId) throw new Error("Выберите кабинет");
      if (!validCostRows.length) throw new Error("Заполните хотя бы одну строку");
      return saveInlineCosts({
        account_id: accountId,
        rows: validCostRows,
      });
    },
    onSuccess: async () => {
      toast.success("Себестоимость сохранена, пересчёт запущен");
      invalidateActionCenterFixQueries(qc);
      await onApplied?.();
      onOpenChange(false);
    },
    onError: (error) => {
      toast.error(error instanceof Error ? error.message : "Не удалось сохранить себестоимость");
    },
  });

  const updateCurrentCostDraft = (patch: Partial<CostDraft>) => {
    if (!currentCostRow) return;
    const key = rowKey(currentCostRow, costIndex);
    setDrafts((current) => ({
      ...current,
      [key]: {
        cost_price: current[key]?.cost_price ?? "",
        seller_other_expense: current[key]?.seller_other_expense ?? "",
        ...patch,
      },
    }));
  };

  const currentDraft = currentCostRow ? drafts[rowKey(currentCostRow, costIndex)] ?? { cost_price: "", seller_other_expense: "" } : { cost_price: "", seller_other_expense: "" };
  const currentCostValid = parseMoneyDraft(currentDraft.cost_price ?? "") != null;
  const title = group?.problem_code
    ? `${problemCodeLabel(group.problem_code)} · ${group.items.length} задач`
    : "Группа задач";

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[92vh] max-w-4xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{mode === "missing_cost" ? "Групповое исправление себестоимости" : "Разбор группы проблем"}</DialogTitle>
          <DialogDescription>
            {title}. Сначала исправляем данные, потом Action Center пересчитает формулы и обновит задачи.
          </DialogDescription>
        </DialogHeader>

        {!mode ? (
          <Alert>
            <Wrench className="h-4 w-4" />
            <AlertTitle>Для этой группы нет безопасного встроенного исправления</AlertTitle>
            <AlertDescription>
              Откройте отдельную задачу: там показаны доказательства, рабочий экран и перепроверка.
            </AlertDescription>
          </Alert>
        ) : mode === "missing_cost" ? (
          <div className="space-y-4">
            <div className="grid gap-3 sm:grid-cols-3">
              <div className="rounded-md border p-3">
                <div className="text-xs text-muted-foreground">Найдено SKU</div>
                <div className="text-xl font-semibold">{missingCostsQ.data?.total ?? costRows.length}</div>
              </div>
              <div className="rounded-md border p-3">
                <div className="text-xs text-muted-foreground">Заполнено в мастере</div>
                <div className="text-xl font-semibold">{filledCount}</div>
              </div>
              <div className="rounded-md border p-3">
                <div className="text-xs text-muted-foreground">Выручка под блокером</div>
                <div className="text-xl font-semibold">
                  {formatMoney(missingCostsQ.data?.summary?.affected_revenue ?? 0)}
                </div>
              </div>
            </div>

            <div className="space-y-2">
              <div className="flex items-center justify-between gap-3 text-xs text-muted-foreground">
                <span>
                  Шаг {costRows.length ? costIndex + 1 : 0} из {costRows.length}
                </span>
                <span>{progressValue}% заполнено</span>
              </div>
              <Progress value={progressValue} />
            </div>

            {missingCostsQ.isLoading ? (
              <div className="space-y-2">
                <Skeleton className="h-20 w-full" />
                <Skeleton className="h-32 w-full" />
              </div>
            ) : currentCostRow ? (
              <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_260px]">
                <section className="space-y-4 rounded-md border p-4">
                  <div className="space-y-2">
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge variant="outline">SKU {currentCostRow.sku_id}</Badge>
                      {currentCostRow.nm_id ? <Badge variant="secondary">nm {currentCostRow.nm_id}</Badge> : null}
                      {currentCostRow.tech_size ? <Badge variant="outline">{currentCostRow.tech_size}</Badge> : null}
                    </div>
                    <div className="text-base font-semibold">{productLabel(currentCostRow)}</div>
                    <div className="text-sm text-muted-foreground">
                      Выручка, которую блокирует отсутствие себестоимости:{" "}
                      <span className="font-medium text-foreground">
                        {formatMoney(currentCostRow.affected_revenue ?? 0)}
                      </span>
                    </div>
                  </div>

                  <div className="grid gap-3 sm:grid-cols-2">
                    <label className="space-y-1">
                      <span className="text-xs font-medium">Себестоимость</span>
                      <Input
                        type="number"
                        inputMode="decimal"
                        min="0"
                        step="0.01"
                        value={currentDraft.cost_price}
                        onChange={(event) => updateCurrentCostDraft({ cost_price: event.target.value })}
                        placeholder="Например 450"
                        className="min-h-10"
                      />
                    </label>
                    <label className="space-y-1">
                      <span className="text-xs font-medium">Прочий расход на единицу</span>
                      <Input
                        type="number"
                        inputMode="decimal"
                        min="0"
                        step="0.01"
                        value={currentDraft.seller_other_expense}
                        onChange={(event) => updateCurrentCostDraft({ seller_other_expense: event.target.value })}
                        placeholder="0, если нет"
                        className="min-h-10"
                      />
                    </label>
                  </div>

                  {!currentCostValid && currentDraft.cost_price ? (
                    <div className="text-xs text-destructive">
                      Себестоимость должна быть числом не меньше 0.
                    </div>
                  ) : null}

                  <label className="flex items-center gap-2 text-sm">
                    <Checkbox
                      checked={supplierConfirmed}
                      onCheckedChange={(checked) => setSupplierConfirmed(checked === true)}
                    />
                    Подтверждено поставщиком
                  </label>
                </section>

                <aside className="space-y-2 rounded-md border p-3">
                  <div className="text-xs font-medium">Очередь</div>
                  <div className="max-h-72 space-y-1 overflow-y-auto">
                    {costRows.map((row, index) => {
                      const filled = Boolean(drafts[rowKey(row, index)]?.cost_price);
                      return (
                        <button
                          key={rowKey(row, index)}
                          type="button"
                          className={`flex w-full items-center justify-between gap-2 rounded-md px-2 py-1.5 text-left text-xs ${
                            index === costIndex ? "bg-primary/10 text-foreground" : "hover:bg-muted"
                          }`}
                          onClick={() => setCostIndex(index)}
                        >
                          <span className="min-w-0 truncate">{productLabel(row)}</span>
                          {filled ? <CheckCircle2 className="h-3.5 w-3.5 shrink-0 text-success" /> : null}
                        </button>
                      );
                    })}
                  </div>
                </aside>
              </div>
            ) : (
              <Alert>
                <CheckCircle2 className="h-4 w-4" />
                <AlertTitle>Нет SKU без себестоимости</AlertTitle>
                <AlertDescription>
                  Данные уже закрыты или текущие фильтры не нашли строк для этой группы.
                </AlertDescription>
              </Alert>
            )}
          </div>
        ) : (
          <PriceReviewGroup
            rows={reviewRows}
            current={currentReviewRow}
            index={reviewIndex}
            progressValue={progressValue}
            onIndexChange={setReviewIndex}
          />
        )}

        <DialogFooter className="gap-2 sm:gap-2">
          {mode === "missing_cost" ? (
            <>
              <Button
                variant="outline"
                onClick={() => setCostIndex((value) => Math.max(0, value - 1))}
                disabled={!costRows.length || costIndex <= 0 || saveCosts.isPending}
              >
                <ArrowLeft className="mr-1 h-4 w-4" />
                Назад
              </Button>
              <Button
                variant="outline"
                onClick={() => setCostIndex((value) => Math.min(costRows.length - 1, value + 1))}
                disabled={!costRows.length || costIndex >= costRows.length - 1 || saveCosts.isPending}
              >
                Далее
                <ArrowRight className="ml-1 h-4 w-4" />
              </Button>
              <Button
                onClick={() => saveCosts.mutate()}
                disabled={!validCostRows.length || saveCosts.isPending}
              >
                {saveCosts.isPending ? (
                  <Loader2 className="mr-1 h-4 w-4 animate-spin" />
                ) : (
                  <CheckCircle2 className="mr-1 h-4 w-4" />
                )}
                Применить {validCostRows.length ? `(${validCostRows.length})` : ""}
              </Button>
            </>
          ) : mode === "price_review" ? (
            <>
              <Button
                variant="outline"
                onClick={() => setReviewIndex((value) => Math.max(0, value - 1))}
                disabled={!reviewRows.length || reviewIndex <= 0}
              >
                <ArrowLeft className="mr-1 h-4 w-4" />
                Назад
              </Button>
              <Button
                onClick={() => setReviewIndex((value) => Math.min(reviewRows.length - 1, value + 1))}
                disabled={!reviewRows.length || reviewIndex >= reviewRows.length - 1}
              >
                Далее
                <ArrowRight className="ml-1 h-4 w-4" />
              </Button>
            </>
          ) : null}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function PriceReviewGroup({
  rows,
  current,
  index,
  progressValue,
  onIndexChange,
}: {
  rows: ActionCenterItem[];
  current: ActionCenterItem | null;
  index: number;
  progressValue: number;
  onIndexChange: (index: number) => void;
}) {
  const safety = current?.price_safety ?? {};
  const currentPrice = safety.current_price ?? safety.price_after_discount ?? null;
  const targetPrice = safety.target_price ?? safety.min_safe_price ?? null;
  const pricingHref = current?.nm_id
    ? `/pricing?search=${encodeURIComponent(String(current.nm_id))}`
    : "/pricing";
  const productHref = current?.nm_id ? `/products/${current.nm_id}?tab=price` : "/products";

  return (
    <div className="space-y-4">
      <Alert>
        <Wrench className="h-4 w-4" />
        <AlertTitle>Автоматическое изменение цены не включено</AlertTitle>
        <AlertDescription>
          В системе есть безопасный расчёт и review-экран, но нет включённого WB price-write endpoint.
          Поэтому здесь показываем очередь и безопасную цену, а изменение выполняется через pricing review.
        </AlertDescription>
      </Alert>

      <div className="space-y-2">
        <div className="flex items-center justify-between gap-3 text-xs text-muted-foreground">
          <span>
            Шаг {rows.length ? index + 1 : 0} из {rows.length}
          </span>
          <span>{progressValue}% просмотрено</span>
        </div>
        <Progress value={progressValue} />
      </div>

      {current ? (
        <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_260px]">
          <section className="space-y-4 rounded-md border p-4">
            <div className="space-y-2">
              <div className="flex flex-wrap items-center gap-2">
                {current.priority ? <Badge variant="outline">{current.priority}</Badge> : null}
                {current.impact_type ? <Badge variant="outline">{problemImpactLabel(current.impact_type)}</Badge> : null}
                {current.trust_state ? <Badge variant="outline">{problemTrustLabel(current.trust_state)}</Badge> : null}
              </div>
              <div className="text-base font-semibold">{current.title}</div>
              <div className="text-sm text-muted-foreground">{current.reason || current.short_explanation}</div>
            </div>

            <div className="grid gap-3 sm:grid-cols-3">
              <Metric label="Текущая цена" value={formatMoney(currentPrice)} />
              <Metric label="Безопасная цена" value={formatMoney(targetPrice)} />
              <Metric label="Влияние" value={formatMoney(current.money_impact_amount ?? 0)} />
            </div>

            <div className="flex flex-wrap gap-2">
              <Button asChild>
                <a href={pricingHref}>
                  <Wrench className="mr-1 h-4 w-4" />
                  Открыть pricing review
                </a>
              </Button>
              <Button asChild variant="outline">
                <a href={productHref}>
                  Открыть товар
                  <ExternalLink className="ml-1 h-4 w-4" />
                </a>
              </Button>
            </div>
          </section>

          <aside className="space-y-2 rounded-md border p-3">
            <div className="text-xs font-medium">Очередь</div>
            <div className="max-h-72 space-y-1 overflow-y-auto">
              {rows.map((row, rowIndex) => (
                <button
                  key={actionKey(row, rowIndex)}
                  type="button"
                  className={`w-full rounded-md px-2 py-1.5 text-left text-xs ${
                    rowIndex === index ? "bg-primary/10 text-foreground" : "hover:bg-muted"
                  }`}
                  onClick={() => onIndexChange(rowIndex)}
                >
                  <div className="truncate">{productLabel(row)}</div>
                  <div className="truncate text-muted-foreground">{formatMoney(row.money_impact_amount ?? 0)}</div>
                </button>
              ))}
            </div>
          </aside>
        </div>
      ) : (
        <Alert>
          <CheckCircle2 className="h-4 w-4" />
          <AlertTitle>Нет задач для разбора</AlertTitle>
          <AlertDescription>Текущая группа пуста после фильтров.</AlertDescription>
        </Alert>
      )}
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string | null | undefined }) {
  return (
    <div className="rounded-md border p-3">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="text-base font-semibold">{value ?? "—"}</div>
    </div>
  );
}
