import { Card, CardContent } from "@/components/ui/card";
import { TrustBadge, type TrustLevel } from "./TrustBadge";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { Calculator, Info } from "lucide-react";
import { useState } from "react";
import { MetricBreakdownDialog } from "@/components/owner/MetricBreakdownDialog";
import { EvidenceButton, EvidenceDrawer } from "@/components/EvidenceDrawer";
import { MoneyTrustBadge } from "@/components/MoneyTrustBadge";
import type { MetricBreakdown, MetricTrustState } from "@/lib/owner-ux";
import type { EvidenceLedger } from "@/lib/evidence";
import { moneyTrustFrom } from "@/lib/money-trust";
import { cn } from "@/lib/utils";

export type MetricStatus = "good" | "warning" | "danger" | "neutral";
export type Finality = "final" | "provisional" | "test_only" | "not_computable";

const STATUS_BORDER: Record<MetricStatus, string> = {
  good: "border-emerald-500/40",
  warning: "border-amber-500/40",
  danger: "border-red-500/40",
  neutral: "border-border",
};

const FINALITY_TRUST: Record<Finality, TrustLevel> = {
  final: "final",
  provisional: "provisional",
  test_only: "business_accepted",
  not_computable: "data_blocked",
};

const TRUST_FINALITY: Record<MetricTrustState, Finality> = {
  final: "final",
  preliminary: "provisional",
  needs_data: "not_computable",
  system_sync: "provisional",
};

const NOT_COMPUTED = "Не рассчитано";

export interface MetricCardProps {
  title: string;
  value: number | string | null | undefined;
  subvalue?: string | null;
  status?: MetricStatus;
  tooltip?: string;
  finality?: Finality;
  trustState?: MetricTrustState;
  breakdown?: MetricBreakdown;
  evidence?: EvidenceLedger | null;
  format?: (v: number) => string;
}

export function MetricCard({
  title,
  value,
  subvalue,
  status = "neutral",
  tooltip,
  finality = "provisional",
  trustState,
  breakdown,
  evidence,
  format,
}: MetricCardProps) {
  const [open, setOpen] = useState(false);
  const [evidenceOpen, setEvidenceOpen] = useState(false);
  const resolvedFinality = trustState ? TRUST_FINALITY[trustState] : finality;
  const moneyTrust = moneyTrustFrom(evidence?.money_trust, evidence);
  // null/undefined => «Не рассчитано», 0 keeps as 0.
  let display: string;
  if (value === null || value === undefined || value === "" || (typeof value === "number" && Number.isNaN(value))) {
    display = NOT_COMPUTED;
  } else if (typeof value === "number") {
    display = format ? format(value) : value.toLocaleString("ru-RU");
  } else {
    display = String(value);
  }

  const canOpen = !!breakdown;
  const hasExplicitMoneyTrust = Boolean(evidence?.money_trust);
  const moneyImpactKind = String(moneyTrust.impact_kind ?? "").toLowerCase();
  const isConfirmedLossMoney =
    display !== NOT_COMPUTED &&
    moneyImpactKind === "confirmed_loss" &&
    moneyTrust.state === "confirmed";
  const isEstimatedMoney =
    display !== NOT_COMPUTED &&
    !isConfirmedLossMoney &&
    (resolvedFinality === "provisional" ||
      resolvedFinality === "test_only" ||
      resolvedFinality === "not_computable" ||
      (hasExplicitMoneyTrust &&
        (moneyTrust.state === "estimated" ||
          moneyTrust.state === "provisional" ||
          moneyTrust.state === "opportunity" ||
          moneyTrust.state === "blocked" ||
          moneyTrust.state === "test_only" ||
          moneyImpactKind === "probable_loss" ||
          moneyImpactKind === "probable_risk" ||
          moneyImpactKind === "blocked_cash" ||
          moneyImpactKind === "lost_sales_risk" ||
          moneyImpactKind === "opportunity" ||
          moneyTrust.impact_kind === "estimated_opportunity" ||
          moneyImpactKind === "data_blocker" ||
          moneyImpactKind === "data_blocked" ||
          moneyTrust.impact_kind === "test_only")));
  const content = (
    <Card className={cn(STATUS_BORDER[status], "border h-full", canOpen && "cursor-pointer transition-colors hover:bg-muted/40 focus-within:ring-2 focus-within:ring-ring")}>
      <CardContent
        className="p-4 space-y-2 h-full"
        role={canOpen ? "button" : undefined}
        tabIndex={canOpen ? 0 : undefined}
        onClick={canOpen ? () => setOpen(true) : undefined}
        onKeyDown={canOpen ? (event) => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            setOpen(true);
          }
        } : undefined}
      >
        <div className="flex items-center justify-between gap-2">
          <div className="text-xs text-muted-foreground flex items-center gap-1">
            {title}
            {canOpen ? (
              <TooltipProvider delayDuration={150}>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <Calculator className="h-3 w-3 opacity-70" />
                  </TooltipTrigger>
                  <TooltipContent className="max-w-xs text-xs">Показать формулу и источники</TooltipContent>
                </Tooltip>
              </TooltipProvider>
            ) : null}
            {tooltip ? (
              <TooltipProvider delayDuration={150}>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <Info className="h-3 w-3 cursor-help opacity-60" />
                  </TooltipTrigger>
                  <TooltipContent className="max-w-xs text-xs">{tooltip}</TooltipContent>
                </Tooltip>
              </TooltipProvider>
            ) : null}
          </div>
          <div className="flex flex-wrap justify-end gap-1">
            <MoneyTrustBadge trust={moneyTrust} />
            <TrustBadge level={FINALITY_TRUST[resolvedFinality]} className="text-[10px] py-0 px-1.5" />
          </div>
        </div>
        <div
          className={cn(
            "text-2xl font-semibold",
            display === NOT_COMPUTED && "text-muted-foreground",
            isConfirmedLossMoney && "rounded-md border border-destructive/35 bg-destructive/10 px-2 py-1 text-destructive",
            isEstimatedMoney && "rounded-md border border-dashed border-amber-500/45 bg-amber-500/10 px-2 py-1 text-amber-800 dark:text-amber-200",
          )}
        >
          {display}
        </div>
        {isEstimatedMoney ? (
          <div className="text-[10px] font-medium uppercase text-amber-700 dark:text-amber-300">
            Оценка / предварительно, не подтверждённые деньги
          </div>
        ) : null}
        {subvalue ? <div className="text-xs text-muted-foreground">{subvalue}</div> : null}
        <EvidenceButton
          ledger={evidence}
          allowEmpty
          className="w-full justify-start"
          onClick={(event) => {
            event.stopPropagation();
            setEvidenceOpen(true);
          }}
        />
      </CardContent>
    </Card>
  );

  return (
    <>
      {content}
      <MetricBreakdownDialog breakdown={breakdown} open={open} onOpenChange={setOpen} />
      <EvidenceDrawer
        open={evidenceOpen}
        onOpenChange={setEvidenceOpen}
        ledger={evidence}
        title={title}
      />
    </>
  );
}
