// Profit finality badges + operator-baseline warning.
// Renders strictly per spec — never claims "Финальная прибыль" unless
// backend says financial_final === true AND no contradicting signals.
import { Badge } from "@/components/ui/badge";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { AlertTriangle, CheckCircle2, Clock, ShieldCheck, ShieldAlert } from "lucide-react";

export interface ProfitFinalityInputs {
  financial_final?: boolean | null;
  trust_state?: string | null;                              // e.g. "operational_provisional" | "financial_final"
  cost_trust_policy?: string | null;                        // e.g. "operator_baseline" | "supplier_confirmed"
  supplier_confirmed_revenue_coverage_percent?: number | null;
  final_profit_blockers_total?: number | null;
  finance_reconciliation_status?: string | null;            // "mismatch" | "critical_mismatch" | ...
}

const T = {
  success: "bg-success/15 text-success border-success/30",
  warning: "bg-warning/15 text-warning border-warning/30",
  danger:  "bg-destructive/15 text-destructive border-destructive/30",
  info:    "bg-primary/10 text-primary border-primary/30",
  muted:   "bg-muted text-muted-foreground border-border",
};

/**
 * Strict rule: profit may NOT be labelled "Финальная" when ANY of:
 *   - financial_final !== true
 *   - supplier_confirmed_revenue_coverage_percent === 0
 *   - final_profit_blockers_total > 0
 *   - trust_state === "operational_provisional"
 */
export function isProfitFinal(i: ProfitFinalityInputs): boolean {
  if (i.financial_final !== true) return false;
  if ((i.supplier_confirmed_revenue_coverage_percent ?? null) === 0) return false;
  if ((i.final_profit_blockers_total ?? 0) > 0) return false;
  if ((i.trust_state ?? "").toLowerCase() === "operational_provisional") return false;
  return true;
}

export function ProfitFinalityBadges({
  inputs, className = "",
}: { inputs: ProfitFinalityInputs; className?: string }) {
  const final = isProfitFinal(inputs);
  const coverage = inputs.supplier_confirmed_revenue_coverage_percent ?? null;
  const policy = (inputs.cost_trust_policy ?? "").toLowerCase();
  const financeBad = ["mismatch", "critical_mismatch"].includes((inputs.finance_reconciliation_status ?? "").toLowerCase());
  const supplierMissing = coverage === 0 || policy === "operator_baseline";
  const showNotFinal = !final && (financeBad || supplierMissing || (inputs.final_profit_blockers_total ?? 0) > 0);

  return (
    <div className={`flex flex-wrap items-center gap-1.5 ${className}`}>
      {final ? (
        <Badge variant="outline" className={`text-[10px] uppercase ${T.success}`}>
          <CheckCircle2 className="h-3 w-3 mr-1" /> Финальная прибыль
        </Badge>
      ) : (
        <Badge variant="outline" className={`text-[10px] uppercase ${T.warning}`}>
          <Clock className="h-3 w-3 mr-1" /> Операционная прибыль
        </Badge>
      )}

      {policy === "operator_baseline" && (
        <Badge variant="outline" className={`text-[10px] uppercase ${T.warning}`}>
          <ShieldAlert className="h-3 w-3 mr-1" /> Операторская себестоимость
        </Badge>
      )}
      {(policy === "supplier_confirmed" || (coverage != null && coverage >= 95)) && (
        <Badge variant="outline" className={`text-[10px] uppercase ${T.success}`}>
          <ShieldCheck className="h-3 w-3 mr-1" /> Подтверждённая себестоимость
          {coverage != null ? ` · ${coverage.toFixed(0)}%` : ""}
        </Badge>
      )}

      {showNotFinal && (
        <Badge variant="outline" className={`text-[10px] uppercase ${T.danger}`}>
          <AlertTriangle className="h-3 w-3 mr-1" /> Не финально
        </Badge>
      )}
    </div>
  );
}

/**
 * Warning shown whenever profit is being computed on operator baseline
 * (i.e. supplier-confirmed cost is missing or coverage is too low).
 */
export function OperatorBaselineWarning({
  inputs, className = "",
}: { inputs: ProfitFinalityInputs; className?: string }) {
  const policy = (inputs.cost_trust_policy ?? "").toLowerCase();
  const coverage = inputs.supplier_confirmed_revenue_coverage_percent ?? null;
  const show =
    policy === "operator_baseline" ||
    coverage === 0 ||
    (coverage != null && coverage < 50);
  if (!show) return null;
  return (
    <Alert className={`border-warning/40 bg-warning/5 ${className}`}>
      <AlertTriangle className="h-4 w-4 text-warning" />
      <AlertTitle className="text-sm">Прибыль на операторской себестоимости</AlertTitle>
      <AlertDescription className="text-xs">
        Прибыль рассчитана на операторской себестоимости. Для финального финансового результата
        загрузите supplier-confirmed себестоимость и закройте расхождения.
        {coverage != null && (
          <> {" "}Текущее покрытие supplier-confirmed: <b>{coverage.toFixed(0)}%</b>.</>
        )}
      </AlertDescription>
    </Alert>
  );
}

/** Build ProfitFinalityInputs from typical /money/summary + /dashboard/owner shapes. */
export function profitFinalityFromSummary(s: any): ProfitFinalityInputs {
  const k = s?.kpis ?? {};
  const meta = s?.meta ?? {};
  const dt = meta?.data_trust ?? {};
  const ans = s?.answer ?? {};
  return {
    financial_final: s?.financial_final ?? dt?.financial_final ?? k?.financial_final ?? null,
    trust_state: dt?.state ?? dt?.trust_state ?? ans?.business_status ?? null,
    cost_trust_policy:
      s?.cost_trust_policy ?? k?.cost_trust_policy ?? dt?.cost_trust_policy ?? null,
    supplier_confirmed_revenue_coverage_percent:
      k?.supplier_confirmed_revenue_coverage_percent
      ?? k?.supplier_confirmed_cost_coverage_percent
      ?? k?.supplier_cost_coverage_percent
      ?? k?.supplier_cost_confirmed_revenue_percent
      ?? null,
    final_profit_blockers_total:
      s?.financial_final_blockers_total
      ?? s?.final_profit_blockers_total
      ?? k?.financial_final_blockers_total
      ?? k?.final_profit_blockers_total
      ?? null,
    finance_reconciliation_status:
      s?.finance_reconciliation_status ?? k?.finance_reconciliation_status ?? null,
  };
}
