// @ts-nocheck
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Link } from "@tanstack/react-router";
import { ArrowRight, TrendingUp, Wallet, CheckCircle2, X, Clock, Package, AlertTriangle } from "lucide-react";
import { cn } from "@/lib/utils";
import type { MNextAction } from "@/lib/api";
import { PRIORITY_COPY, humanizeAction, isDataFixAction, CONFIDENCE_COPY } from "@/lib/copy";
import { formatMoney } from "@/lib/format";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { updateAction } from "@/lib/money-endpoints";
import { useState } from "react";
import { toast } from "sonner";
import { EvidenceButton, EvidenceDrawer } from "@/components/EvidenceDrawer";
import { evidenceFrom } from "@/lib/evidence";
import { isTestOnlyProblem, ProblemBadgeRow, SellerProblemLifecycle } from "@/components/problem/SellerProblemUX";
import { PriceSafetyMissingNotice, PriceSafetyPanel, priceSafetyFrom, priceSafetyNeededForProblem } from "@/components/PriceSafetyPanel";

const PRIO_BAR: Record<string, string> = {
  critical: "bg-destructive", high: "bg-warning", medium: "bg-primary", low: "bg-muted-foreground",
};
const PRIO_BADGE: Record<string, string> = {
  danger:  "bg-destructive/15 text-destructive border-destructive/30",
  warning: "bg-warning/15 text-warning border-warning/30",
  info:    "bg-primary/10 text-primary border-primary/30",
  muted:   "bg-muted text-muted-foreground border-border",
};
const CONF_TONE: Record<string, string> = {
  success: "bg-success/15 text-success border-success/30",
  warning: "bg-warning/15 text-warning border-warning/30",
  danger:  "bg-destructive/15 text-destructive border-destructive/30",
};

const BLOCKED_REASON_RU: Record<string, string> = {
  finance_not_confirmed: "финансовые цифры ещё не сверены — пока подтвердятся отчёты WB, прибыль считается предварительной",
  finance_reconciliation_mismatch: "идёт автоматическая сверка финансов WB — ручных действий от пользователя нет",
  open_blocking_dq_issues: "есть открытые проблемы качества данных — сначала почините их в разделе «Починка данных»",
  data_blocked: "данные по карточке заблокированы — действие можно выполнить только после починки",
  missing_cost: "не указана себестоимость — добавьте её, чтобы посчитать прибыль",
  missing_finance_report: "ещё не загружен финансовый отчёт WB за период",
  stale_data: "данные устарели — обновите выгрузку",
  no_sales_history: "недостаточно истории продаж для надёжной рекомендации",
};

const SYSTEM_HANDLED_ACTIONS = new Set([
  "finance_reconciliation_mismatch",
  "finance_without_sale",
  "sale_without_finance",
  "order_without_sale_or_return",
]);

function isSystemHandledAction(action: MNextAction): boolean {
  const code = String(action.action_type ?? (action as any).code ?? "").toLowerCase();
  if (SYSTEM_HANDLED_ACTIONS.has(code)) return true;
  if (code.includes("finance") || code.includes("sync") || code.includes("scheduler") || code.includes("task")) return true;
  const text = `${action.title ?? ""} ${action.reason ?? ""} ${action.description ?? ""}`.toLowerCase();
  return text.includes("сумма продажи") && text.includes("отчете wb");
}

export function BusinessActionCard({ action, compact = false }: { action: MNextAction; compact?: boolean }) {
  if (isSystemHandledAction(action)) return null;

  const prio = PRIORITY_COPY[action.priority] ?? PRIORITY_COPY.medium;
  const conf = CONFIDENCE_COPY[action.confidence] ?? CONFIDENCE_COPY.medium;
  const dataFix = action.action_group === "data_fix" || isDataFixAction(action.action_type);
  const hasId = !!action.id && action.id > 0;
  const skuId = action.linked_entity?.sku_id;
  const nmId = action.linked_entity?.nm_id;
  const [localStatus, setLocalStatus] = useState<string | null>(null);
  const [evidenceOpen, setEvidenceOpen] = useState(false);
  const qc = useQueryClient();

  const link = nmId
    ? `/products/${nmId}`
    : skuId
      ? "/products"
      : dataFix
        ? "/data-fix"
        : "/action-center";

  const title = action.title?.trim() || humanizeAction(action.action_type);
  const isLiquidation = /liquidat|discount_to_clear/i.test(action.action_type || "");
  const isReorder = /reorder|restock|increase_purchase/i.test(action.action_type || "");
  const affectedStockValue = (action as any).affected_stock_value as number | undefined;
  const deadline = action.deadline_hint;
  const ledger = evidenceFrom((action as any).evidence_ledger, (action as any).payload?.evidence_ledger);
  const priceSafety = priceSafetyFrom((action as any).payload, (action as any).raw, action);
  const problemLike = {
    ...(action as any),
    title,
    problem_code: (action as any).problem_code ?? action.action_type,
    severity: (action as any).severity ?? action.priority,
    trust_state: (action as any).trust_state ?? (action as any).money_trust?.state ?? action.confidence,
    impact_type: (action as any).impact_type ?? (dataFix ? "data_blocker" : action.expected_effect_amount > 0 ? "opportunity" : "risk"),
    money_impact_amount: (action as any).money_impact_amount ?? action.expected_effect_amount,
    reason: (action as any).reason ?? action.why,
    explanation: (action as any).explanation ?? action.description,
    recommendation: (action as any).recommendation ?? action.what_to_do,
    next_step: (action as any).next_step ?? action.what_to_do,
    can_user_fix_inside_platform: dataFix || Boolean(nmId || skuId),
    allowed_actions: dataFix ? ["open_data_fix", "recheck", "dismiss"] : ["create_task", "recheck", "dismiss"],
    recheck_rule_human: (action as any).recheck_rule_human ?? "Действие перепроверяется после изменения исходных данных или статуса задачи.",
    evidence_ledger: ledger,
  };

  const mut = useMutation({
    mutationFn: (body: Record<string, unknown>) => updateAction(action.id!, body),
    onSuccess: (_d, vars) => {
      setLocalStatus(String((vars as any).status));
      toast.success("Действие обновлено");
      qc.invalidateQueries({ queryKey: ["money-actions"] });
      qc.invalidateQueries({ queryKey: ["money-actions-today"] });
    },
    onError: (e: any) => toast.error(e?.message ?? "Не удалось обновить действие"),
  });
  const setStatus = (status: string, extra: Record<string, unknown> = {}) =>
    mut.mutate({ status, ...extra });
  const done = localStatus === "done";
  const ignored = localStatus === "ignored";
  const snoozed = localStatus === "snoozed";
  const needsPriceSafety = priceSafetyNeededForProblem(problemLike);
  if (isTestOnlyProblem(problemLike)) return null;

  return (
    <>
      <Card className="relative overflow-hidden">
        <div className={cn("absolute left-0 top-0 bottom-0 w-1", PRIO_BAR[action.priority])} />
        <CardContent className={cn("space-y-3 pl-5", compact ? "p-3" : "p-4")}>
          <div className="flex items-start justify-between gap-2 flex-wrap">
            <div className="flex items-center gap-2 flex-wrap">
              <Badge variant="outline" className={cn("border text-[10px] uppercase", PRIO_BADGE[prio.tone])}>{prio.label}</Badge>
              {dataFix && (
                <Badge variant="outline" className="text-[10px] uppercase border-warning/30 text-warning bg-warning/10">
                  Починка данных
                </Badge>
              )}
              {!dataFix && (
                <Badge variant="outline" className="text-[10px] uppercase border-success/30 text-success bg-success/10">
                  Бизнес-действие
                </Badge>
              )}
              <Badge variant="outline" className={cn("text-[10px] uppercase border", CONF_TONE[conf.tone])}>{conf.label}</Badge>
              <ProblemBadgeRow problem={problemLike} ledger={ledger} />
            </div>
            <div className="flex items-center gap-2">
              {action.expected_effect_amount > 0 && (
                <div className="flex items-center gap-1 rounded-md border border-dashed border-amber-500/45 bg-amber-500/10 px-2 py-1 text-xs font-medium text-amber-800 dark:text-amber-200">
                  <TrendingUp className="h-3 w-3" /> Оценка эффекта: {formatMoney(action.expected_effect_amount)}
                </div>
              )}
              <EvidenceButton
                ledger={ledger}
                allowEmpty
                onClick={() => setEvidenceOpen(true)}
              />
            </div>
          </div>

          <div>
            <div className="font-medium text-sm leading-snug">{title}</div>
            {action.what_to_do && <div className="text-sm text-muted-foreground mt-1">{action.what_to_do}</div>}
          </div>

          {action.why && (
            <div className="text-xs text-muted-foreground border-l-2 border-muted pl-2">
              <span className="font-medium">Почему: </span>{action.why}
            </div>
          )}

          {!compact ? (
            <SellerProblemLifecycle
              problem={problemLike}
              ledger={ledger}
              showHeader={false}
              onEvidence={() => setEvidenceOpen(true)}
            />
          ) : null}

          {!compact && priceSafety ? (
            <PriceSafetyPanel priceSafety={priceSafety} compact />
          ) : !compact && needsPriceSafety ? (
            <PriceSafetyMissingNotice compact />
          ) : null}

          {!compact && action.how_to_fix?.length > 0 && (
          <div className="bg-muted/30 rounded-md p-2.5 space-y-1">
            <div className="text-[10px] uppercase tracking-wider text-muted-foreground font-semibold">Как починить</div>
            <ol className="text-xs space-y-1 list-decimal list-inside">
              {action.how_to_fix.map((s, i) => <li key={i}>{s}</li>)}
            </ol>
          </div>
        )}

        {!compact && (isReorder || isLiquidation || action.recommended_qty > 0 || action.days_of_stock > 0 || deadline || action.lead_time_days > 0 || action.safety_days > 0 || action.unit_cost > 0) && (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-xs">
            {isReorder && action.required_cash > 0 && (
              <div><div className="text-[10px] text-muted-foreground uppercase">Нужно денег</div><div className="flex items-center gap-1 font-medium"><Wallet className="h-3 w-3" />{formatMoney(action.required_cash)}</div></div>
            )}
            {isLiquidation && affectedStockValue != null && (
              <div><div className="text-[10px] text-muted-foreground uppercase">Затронутый остаток</div><div className="flex items-center gap-1 font-medium"><Package className="h-3 w-3" />{formatMoney(affectedStockValue)}</div></div>
            )}
            {action.recommended_qty > 0 && (
              <div><div className="text-[10px] text-muted-foreground uppercase">Кол-во</div><div className="font-medium">{action.recommended_qty} шт</div></div>
            )}
            {action.unit_cost > 0 && (
              <div><div className="text-[10px] text-muted-foreground uppercase">Себест. ед.</div><div className="font-medium">{formatMoney(action.unit_cost)}</div></div>
            )}
            {action.days_of_stock > 0 && (
              <div><div className="text-[10px] text-muted-foreground uppercase">Дней остатка</div><div className="font-medium">{action.days_of_stock.toFixed(0)}</div></div>
            )}
            {action.lead_time_days > 0 && (
              <div><div className="text-[10px] text-muted-foreground uppercase">Срок поставки</div><div className="font-medium">{action.lead_time_days} дн</div></div>
            )}
            {action.safety_days > 0 && (
              <div><div className="text-[10px] text-muted-foreground uppercase">Страховой запас</div><div className="font-medium">{action.safety_days} дн</div></div>
            )}
            {deadline && (
              <div><div className="text-[10px] text-muted-foreground uppercase">Дедлайн</div><div className="flex items-center gap-1 font-medium"><Clock className="h-3 w-3" />{deadline}</div></div>
            )}
          </div>
        )}

        {action.linked_entity?.vendor_code && (
          <div className="text-[11px] text-muted-foreground font-mono">
            {action.linked_entity.vendor_code}{action.linked_entity.nm_id ? ` · nm ${action.linked_entity.nm_id}` : ""}
          </div>
        )}

        {(action.blocked_reasons?.length ?? 0) > 0 && (
          <div className="text-[11px] text-warning flex items-start gap-1">
            <AlertTriangle className="h-3 w-3 mt-0.5 shrink-0" />
            <span>
              <span className="font-medium">Действие заблокировано:</span>{" "}
              {action.blocked_reasons.map((r) => BLOCKED_REASON_RU[r] ?? r).join("; ")}
            </span>
          </div>
        )}

          <div className="flex items-center gap-2 flex-wrap pt-1">
          <Button asChild size="sm" variant="outline" className="h-7 text-xs">
            <Link to={link as any}>
              {nmId ? "Открыть карточку" : skuId ? "Открыть SKU" : dataFix ? "Открыть починку" : "Подробнее"}
              <ArrowRight className="h-3 w-3 ml-1" />
            </Link>
          </Button>
          <Button size="sm" variant="ghost" className="h-7 text-xs"
            disabled={!hasId || mut.isPending || done}
            onClick={() => setStatus("done")}
            title={hasId ? "" : "Бэкенд ещё не сохранил действие"}>
            <CheckCircle2 className="h-3 w-3 mr-1" /> {done ? "Сделано" : "Выполнено"}
          </Button>
          <Button size="sm" variant="ghost" className="h-7 text-xs"
            disabled={!hasId || mut.isPending || snoozed}
            onClick={() => setStatus("snoozed", { snooze_days: 1 })}>
            <Clock className="h-3 w-3 mr-1" /> {snoozed ? "Отложено" : "Отложить"}
          </Button>
          <Button size="sm" variant="ghost" className="h-7 text-xs"
            disabled={!hasId || mut.isPending || ignored}
            onClick={() => setStatus("ignored")}>
            <X className="h-3 w-3 mr-1" /> {ignored ? "Отклонено" : "Отклонить"}
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
