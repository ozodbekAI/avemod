import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { Link } from "@tanstack/react-router";
import { TrustBadge, type TrustLevel } from "./TrustBadge";
import { AlertTriangle, ArrowRight, Calendar, Coins, Package, Sparkles } from "lucide-react";
import { MoneyTrustBadge } from "@/components/MoneyTrustBadge";
import type { MoneyTrustInfo } from "@/lib/money-trust";
import { PriceSafetyMissingNotice, priceSafetyNeededFromText } from "@/components/PriceSafetyPanel";


export type ActionStatus = "new" | "in_progress" | "done" | "ignored" | "snoozed";

const STATUS_LABEL: Record<ActionStatus, string> = {
  new: "Новое",
  in_progress: "В работе",
  done: "Сделано",
  ignored: "Игнорировать",
  snoozed: "Отложить",
};

export interface ActionCardProps {
  title: string;
  whatToDo?: string | null;
  why?: string | null;
  expectedEffectAmount?: number | null;
  requiredCash?: number | null;
  recommendedQty?: number | null;
  confidence?: "high" | "medium" | "low" | null;
  deadlineHint?: string | null;
  linkedArticle?: { nmId?: number | string | null; vendorCode?: string | null; title?: string | null } | null;
  linkedSkuId?: number | string | null;
  trust?: TrustLevel;
  moneyTrust?: MoneyTrustInfo | null;
  financialFinal?: boolean | null;
  blockedReasons?: string[] | null;
  status?: ActionStatus;
  onStatusChange?: (s: ActionStatus) => void;
  onOpenLink?: () => void;
}

function fmtMoney(n: number | null | undefined): string | null {
  if (n == null || Number.isNaN(n)) return null;
  return n.toLocaleString("ru-RU", { maximumFractionDigits: 0 }) + " ₽";
}

const CONF_LABEL: Record<string, { label: string; tone: string }> = {
  high:   { label: "Высокая уверенность",  tone: "text-emerald-700" },
  medium: { label: "Средняя уверенность",  tone: "text-amber-700" },
  low:    { label: "Низкая уверенность",   tone: "text-red-700" },
};

const BLOCKED_REASON_LABEL: Record<string, string> = {
  finance_not_confirmed: "финансы ещё не подтверждены",
  finance_reconciliation_mismatch: "идёт сверка финансов WB",
  open_blocking_dq_issues: "есть блокеры качества данных",
  missing_manual_cost: "не хватает себестоимости",
  supplier_cost_not_confirmed: "себестоимость не подтверждена",
};

export function ActionCard(p: ActionCardProps) {
  const effect = fmtMoney(p.expectedEffectAmount);
  const cash = fmtMoney(p.requiredCash);
  const blockedReasons = p.blockedReasons?.filter(Boolean) ?? [];
  const provisional = p.financialFinal === false || blockedReasons.length > 0;
  const confirmedEffect = p.moneyTrust?.show_as_confirmed_money === true;
  const needsPriceSafety = priceSafetyNeededFromText(p.title, p.whatToDo, p.why);
  const articleLabel = p.linkedArticle?.title
    || p.linkedArticle?.vendorCode
    || (p.linkedArticle?.nmId ? `nm ${p.linkedArticle.nmId}` : null)
    || (p.linkedSkuId ? `SKU ${p.linkedSkuId}` : null);

  return (
    <Card>
      <CardContent className="p-4 space-y-3">
        <div className="flex items-start justify-between gap-3">
          <div className="space-y-1 min-w-0">
            <div className="font-semibold leading-snug">{p.title}</div>
            {p.whatToDo ? <div className="text-sm text-muted-foreground">{p.whatToDo}</div> : null}
          </div>
          <div className="flex flex-wrap justify-end gap-1">
            {p.moneyTrust ? <MoneyTrustBadge trust={p.moneyTrust} /> : null}
            {p.trust || provisional ? <TrustBadge level={p.trust ?? "provisional"} /> : null}
          </div>
        </div>

        {provisional ? (
          <div className="text-xs text-amber-800 dark:text-amber-300 border-l-2 border-amber-500/40 pl-2 flex gap-1.5">
            <AlertTriangle className="h-3 w-3 mt-0.5 shrink-0" />
            <span>
              Предварительное действие
              {blockedReasons.length > 0
                ? `: ${blockedReasons.map((r) => BLOCKED_REASON_LABEL[r] ?? r).join(", ")}`
                : ": прибыль ещё не финальная"}
            </span>
          </div>
        ) : null}

        {p.why ? (
          <div className="text-xs text-muted-foreground border-l-2 border-border pl-2">
            <span className="font-medium text-foreground">Почему: </span>{p.why}
          </div>
        ) : null}

        <div className="flex flex-wrap gap-2 text-xs">
          {effect ? (
            <Badge
              variant="outline"
              className={
                confirmedEffect
                  ? "gap-1 border-emerald-500/40 text-emerald-700"
                  : "gap-1 border-dashed border-amber-500/45 bg-amber-500/10 text-amber-800 dark:text-amber-200"
              }
            >
              <Sparkles className="h-3 w-3" /> {confirmedEffect ? p.moneyTrust?.amount_label ?? "Измеренный эффект" : p.moneyTrust?.amount_label ?? "Оценка эффекта"}: {effect}
            </Badge>
          ) : null}
          {cash ? (
            <Badge variant="outline" className="gap-1">
              <Coins className="h-3 w-3" /> Нужно денег: {cash}
            </Badge>
          ) : null}
          {p.recommendedQty != null ? (
            <Badge variant="outline" className="gap-1">
              <Package className="h-3 w-3" /> Кол-во: {p.recommendedQty}
            </Badge>
          ) : null}
          {p.deadlineHint ? (
            <Badge variant="outline" className="gap-1">
              <Calendar className="h-3 w-3" /> {p.deadlineHint}
            </Badge>
          ) : null}
          {p.confidence && CONF_LABEL[p.confidence] ? (
            <span className={`${CONF_LABEL[p.confidence].tone}`}>
              {CONF_LABEL[p.confidence].label}
            </span>
          ) : null}
        </div>

        {needsPriceSafety ? <PriceSafetyMissingNotice compact /> : null}

        {(articleLabel || p.onOpenLink || p.linkedArticle?.nmId) ? (
          <div className="flex items-center justify-between gap-2 pt-1 border-t">
            <div className="text-xs text-muted-foreground truncate">
              {articleLabel ? `Карточка: ${articleLabel}` : ""}
            </div>
            {p.onOpenLink ? (
              <Button size="sm" variant="outline" onClick={p.onOpenLink} className="h-7 text-xs shrink-0">
                Открыть <ArrowRight className="h-3 w-3 ml-1" />
              </Button>
            ) : p.linkedArticle?.nmId ? (
              <Button asChild size="sm" variant="outline" className="h-7 text-xs shrink-0">
                <Link to={`/products/${p.linkedArticle.nmId}` as any}>
                  Открыть карточку <ArrowRight className="h-3 w-3 ml-1" />
                </Link>
              </Button>
            ) : p.linkedSkuId ? (
              <Button asChild size="sm" variant="outline" className="h-7 text-xs shrink-0">
                <Link to={`/sku/${p.linkedSkuId}` as any}>
                  Открыть SKU <ArrowRight className="h-3 w-3 ml-1" />
                </Link>
              </Button>
            ) : null}
          </div>
        ) : null}


        {p.onStatusChange ? (
          <div className="flex items-center gap-2 pt-1">
            <span className="text-xs text-muted-foreground">Статус:</span>
            <Select value={p.status ?? "new"} onValueChange={(v) => p.onStatusChange?.(v as ActionStatus)}>
              <SelectTrigger className="h-8 w-44 text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {(Object.keys(STATUS_LABEL) as ActionStatus[]).map((k) => (
                  <SelectItem key={k} value={k}>{STATUS_LABEL[k]}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}
