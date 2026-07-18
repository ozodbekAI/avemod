// Honest-signal panel. Scans backend data for risk signals listed in the
// product brief and renders them in business language. Never green-washes.
import { Link } from "@tanstack/react-router";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { AlertTriangle, AlertCircle, Info, ArrowRight, CheckCircle2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { formatMoney } from "@/lib/format";
import { HONEST_LABELS, humanizeBusinessStatus } from "@/lib/copy";
import type { MMoneySummary, DashboardDataHealth } from "@/lib/api";

type Sev = "danger" | "warning" | "info";

interface Signal {
  sev: Sev;
  title: string;       // business language
  detail?: string;     // extra context
  cta?: { label: string; href: string };
}

const TONE: Record<Sev, string> = {
  danger:  "border-destructive/40 bg-destructive/5",
  warning: "border-warning/40 bg-warning/5",
  info:    "border-primary/30 bg-primary/5",
};

const ICON: Record<Sev, typeof AlertTriangle> = {
  danger:  AlertCircle,
  warning: AlertTriangle,
  info:    Info,
};

export function collectHonestSignals(
  s: MMoneySummary | null | undefined,
  health?: DashboardDataHealth | null,
  articlesSummary?: { final_profitable_count?: number; economically_profitable_count?: number } | null,
): Signal[] {
  const out: Signal[] = [];
  if (!s) return out;
  const k: any = s.kpis ?? {};
  const meta: any = s.meta ?? {};
  const ans: any = s.answer ?? {};

  // 1) business_status = provisional
  const bizStatus = ans.business_status ?? meta.data_trust?.state;
  if (bizStatus === "provisional") {
    const c = humanizeBusinessStatus("provisional");
    out.push({ sev: "warning", title: `${HONEST_LABELS.provisional_profit}: ${c.label}`, detail: c.hint });
  }
  if (bizStatus === "accepted_with_warnings") {
    const c = humanizeBusinessStatus("accepted_with_warnings");
    out.push({ sev: "warning", title: c.label, detail: "Решения принимать можно, но проверяйте предупреждения ниже." });
  }
  if (bizStatus === "data_blocked") {
    out.push({
      sev: "danger",
      title: HONEST_LABELS.needs_review,
      detail: "Данные пока не надёжны для бизнес-решений — сначала почините блокеры.",
      cta: { label: "Починка данных", href: "/data-fix" },
    });
  }

  // 2) finance_reconciliation_status
  const finStatus: string | undefined = k.finance_reconciliation_status;
  if (finStatus && /critical_mismatch|mismatch|partial/i.test(finStatus)) {
    const c = humanizeBusinessStatus(finStatus);
    out.push({
      sev: finStatus === "critical_mismatch" ? "danger" : "warning",
      title: `${HONEST_LABELS.finance_not_closed}: ${c.label}`,
      detail: c.hint,
      cta: { label: "Открыть сверку", href: "/finance" },
    });
  }

  // 3) finance_difference_percent > 2
  const finDiffPct = num(k.finance_difference_percent ?? k.finance_diff_percent);
  if (finDiffPct != null && Math.abs(finDiffPct) > 2) {
    out.push({
      sev: Math.abs(finDiffPct) > 5 ? "danger" : "warning",
      title: HONEST_LABELS.finance_not_closed,
      detail: `Расхождение с финотчётом WB: ${finDiffPct.toFixed(2)}%`,
      cta: { label: "Открыть сверку", href: "/finance" },
    });
  }

  // 4) supplier_confirmed_revenue_coverage_percent (a.k.a. supplier_cost_confirmed_revenue_percent)
  const supCov = num(k.supplier_confirmed_revenue_coverage_percent ?? k.supplier_cost_confirmed_revenue_percent);
  if (supCov != null) {
    if (supCov === 0) {
      out.push({
        sev: "danger",
        title: HONEST_LABELS.supplier_cost_unconfirmed,
        detail: "Ни по одной карточке нет подтверждённой поставщиком себестоимости.",
        cta: { label: "Открыть себестоимость", href: "/costs" },
      });
    } else if (supCov < 95) {
      out.push({
        sev: "warning",
        title: HONEST_LABELS.supplier_cost_unconfirmed,
        detail: `Покрытие подтверждённой себестоимостью: ${supCov.toFixed(0)}% (нужно ≥95%).`,
        cta: { label: "Открыть себестоимость", href: "/costs" },
      });
    }
  }

  // 5) cost truth level operator_baseline (not supplier_confirmed)
  const costTruth: string | undefined = k.cost_truth_level ?? k.cogs_truth_level;
  if (costTruth && costTruth !== "supplier_confirmed") {
    const c = humanizeBusinessStatus(costTruth);
    out.push({
      sev: costTruth === "operator_baseline" ? "warning" : "danger",
      title: c.label,
      detail: c.hint,
      cta: { label: "Открыть себестоимость", href: "/costs" },
    });
  }

  // 6) open_issues_total > 0
  const openIssues = health?.open_issues_total ?? num(k.open_issues_total) ?? 0;
  if (openIssues > 0) {
    out.push({
      sev: openIssues > 10 ? "danger" : "warning",
      title: HONEST_LABELS.needs_review,
      detail: `Открытых проблем качества данных: ${openIssues}.`,
      cta: { label: "Починка данных", href: "/data-fix" },
    });
  }

  // 7) ads_overallocated_spend > 0
  const adsOver = num(k.ads_overallocated_spend);
  if (adsOver != null && adsOver > 0) {
    out.push({
      sev: "warning",
      title: "Реклама распределена сверх затрат",
      detail: `На карточки распределено больше рекламы, чем по факту потрачено: ${formatMoney(adsOver)}.`,
      cta: { label: "Открыть рекламу", href: "/ads" },
    });
  }

  // 8) unallocated_expenses high
  const unalloc = num(k.unallocated_expenses) ?? 0;
  const revenue = num(k.revenue) ?? 0;
  if (unalloc > 0 && (revenue === 0 || unalloc / Math.max(revenue, 1) > 0.02 || unalloc > 50_000)) {
    out.push({
      sev: "warning",
      title: "Расходы не привязаны к карточкам",
      detail: `Нераспределённые расходы аккаунта: ${formatMoney(unalloc)}. Прибыль владельца считается оценочно.`,
      cta: { label: "Починка данных", href: "/data-fix" },
    });
  }

  // 9) final_profitable_count = 0 while economic_profitable_count > 0
  const finalProf = articlesSummary?.final_profitable_count;
  const econProf  = articlesSummary?.economically_profitable_count;
  if (finalProf === 0 && (econProf ?? 0) > 0) {
    out.push({
      sev: "warning",
      title: "Прибыль операционная, но финансово ещё не подтверждена",
      detail: `Карточек с операционной прибылью: ${econProf}, с подтверждённой финансами: 0.`,
      cta: { label: "Открыть сверку", href: "/finance" },
    });
  }

  // 10) profit_final = false
  const profitFinal = (k.profit_final ?? meta.profit_final);
  if (profitFinal === false) {
    out.push({
      sev: "warning",
      title: HONEST_LABELS.provisional_profit,
      detail: "Финальная прибыль ещё не подтверждена — показатели предварительные.",
    });
  }

  return out;
}

export function HonestSignalsPanel({
  signals,
  emptyHint = "Нет открытых предупреждений. Можно опираться на цифры.",
  title = "Что мешает доверять цифрам",
}: {
  signals: Signal[];
  emptyHint?: string;
  title?: string;
}) {
  if (signals.length === 0) {
    return (
      <Card className="border-success/30 bg-success/5">
        <CardContent className="p-4 flex items-start gap-3">
          <CheckCircle2 className="h-4 w-4 text-success mt-0.5 shrink-0" />
          <div className="text-sm">{emptyHint}</div>
        </CardContent>
      </Card>
    );
  }
  return (
    <section className="space-y-2">
      <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">
        {title}
      </h2>
      <div className="grid gap-2 md:grid-cols-2">
        {signals.map((sig, i) => {
          const Icon = ICON[sig.sev];
          return (
            <Card key={i} className={cn("border", TONE[sig.sev])}>
              <CardContent className="p-3 flex items-start gap-2.5">
                <Icon className={cn(
                  "h-4 w-4 mt-0.5 shrink-0",
                  sig.sev === "danger" ? "text-destructive" : sig.sev === "warning" ? "text-warning" : "text-primary",
                )} />
                <div className="min-w-0 flex-1">
                  <div className="text-sm font-medium leading-snug">{sig.title}</div>
                  {sig.detail && <div className="text-xs text-muted-foreground mt-0.5">{sig.detail}</div>}
                  <div className="flex items-center gap-2 mt-1.5">
                    <Badge variant="outline" className="text-[10px] uppercase">{
                      sig.sev === "danger" ? "Критично" : sig.sev === "warning" ? "Внимание" : "Инфо"
                    }</Badge>
                    {sig.cta && (
                      <Button asChild size="sm" variant="ghost" className="h-6 text-xs px-2">
                        <Link to={sig.cta.href as any}>
                          {sig.cta.label} <ArrowRight className="h-3 w-3 ml-1" />
                        </Link>
                      </Button>
                    )}
                  </div>
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>
    </section>
  );
}

function num(v: unknown): number | null {
  if (v == null) return null;
  const n = typeof v === "number" ? v : parseFloat(String(v));
  return Number.isFinite(n) ? n : null;
}
