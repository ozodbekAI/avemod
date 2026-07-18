import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

export type Finality =
  | "final"
  | "provisional"
  | "business_accepted"
  | "operator_baseline"
  | "finance_mismatch"
  | "data_issue";

const MAP: Record<
  Finality,
  {
    label: string;
    tone: "success" | "warning" | "danger" | "info" | "muted";
    hint?: string;
  }
> = {
  final: {
    label: "Финальная",
    tone: "success",
    hint: "Подтверждено финансами и поставщиком",
  },
  provisional: {
    label: "Предварительная",
    tone: "warning",
    hint: "Цифры приблизительные",
  },
  business_accepted: {
    label: "Принято бизнесом",
    tone: "info",
    hint: "Можно использовать операционно",
  },
  operator_baseline: {
    label: "Операторская оценка",
    tone: "warning",
    hint: "Себестоимость не подтверждена поставщиком",
  },
  finance_mismatch: {
    label: "Финансы Вайлдберриз сверяются",
    tone: "warning",
    hint: "Идёт автоматическая сверка продаж с финансовым отчетом Вайлдберриз",
  },
  data_issue: {
    label: "Сначала данные",
    tone: "danger",
    hint: "Нужно починить данные",
  },
};

const TONE: Record<string, string> = {
  success: "bg-success/15 text-success border-success/30",
  warning: "bg-warning/15 text-warning border-warning/30",
  danger: "bg-destructive/15 text-destructive border-destructive/30",
  info: "bg-primary/10 text-primary border-primary/30",
  muted: "bg-muted text-muted-foreground border-border",
};

export function FinalityBadge({
  state,
  className,
}: {
  state: Finality;
  className?: string;
}) {
  const cfg = MAP[state];
  return (
    <Badge
      variant="outline"
      title={cfg.hint}
      className={cn(
        "text-[10px] uppercase tracking-wide border",
        TONE[cfg.tone],
        className,
      )}
    >
      {cfg.label}
    </Badge>
  );
}

/**
 * Derive a finality state from the typical money summary signals.
 * Order of precedence: data_issue > finance_mismatch > operator_baseline >
 * provisional > business_accepted > final.
 */
export function deriveFinality(input: {
  business_status?: string | null;
  finance_reconciliation_status?: string | null;
  cost_truth_level?: string | null;
  supplier_cost_coverage_percent?: number | null;
}): Finality {
  const bs = (input.business_status || "").toLowerCase();
  const fr = (input.finance_reconciliation_status || "").toLowerCase();
  const ct = (input.cost_truth_level || "").toLowerCase();
  const sc = input.supplier_cost_coverage_percent ?? null;

  if (bs === "data_blocked" || bs === "blocked") return "data_issue";
  if (fr === "mismatch" || fr === "critical_mismatch")
    return "finance_mismatch";
  if (ct === "operator_baseline" || (sc != null && sc < 95))
    return "operator_baseline";
  if (bs === "provisional" || bs === "accepted_with_warnings")
    return "provisional";
  if (bs === "accepted") return "business_accepted";
  if (bs === "final" || ct === "supplier_confirmed") return "final";
  return "provisional";
}
