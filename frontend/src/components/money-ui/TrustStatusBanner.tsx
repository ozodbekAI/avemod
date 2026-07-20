// Reusable trust banner for every money-control page.
// Single source of truth for owner-facing trust messaging.
//
// Display rules (strict — see /lovable spec):
//   1. financial_final=true                 → green   "Финальные данные подтверждены"
//   2. operational_trusted && !final        → yellow  "Данные предварительные"
//   3. business_status=data_blocked         → red     "Бизнес-рекомендации заблокированы. Сначала исправьте данные"
//   + supplier coverage=0                   → "Supplier-confirmed себестоимость не загружена; используется operator baseline"
//   + ads overallocated                     → "Реклама распределена с предупреждением: возможное двойное распределение"
//   + open_issues_total>0                   → "Открытых data issues: {count}"
//
// NEVER renders "Доверенные данные" unless financial_final === true.

import { Card, CardContent } from "@/components/ui/card";
import { AlertTriangle, CheckCircle2, Clock, XCircle } from "lucide-react";
import { Badge } from "@/components/ui/badge";

export interface TrustInput {
  operational_trusted?: boolean | null;
  financial_final?: boolean | null;
  business_status?: string | null;
  trust_label?: string | null;
  trust_reasons?: string[] | null;
}
export interface QualityInput {
  finance_reconciliation_status?: string | null;
  supplier_confirmed_cost_coverage_percent?: number | null;
  ads_allocation_status?: string | null;
  open_issues_total?: number | null;
}

export interface TrustStatusBannerProps {
  trust?: TrustInput | null;
  quality?: QualityInput | null;
  className?: string;
}

type Tone = "success" | "warning" | "danger";

const TRUST_REASON_LABELS: Record<string, string> = {
  data_blocked: "данные заблокированы до исправления",
  finance_not_confirmed: "финансовые данные еще не подтверждены",
  finance_reconciliation_mismatch: "идет сверка финансов WB",
  finance_without_sale: "финансовая строка без продажи",
  missing_cost: "не указана себестоимость",
  missing_finance_report: "не загружен финансовый отчет WB",
  missing_manual_cost: "не хватает ручной себестоимости",
  no_sales_history: "недостаточно истории продаж",
  open_blocking_dq_issues: "есть блокирующие проблемы данных",
  order_without_sale_or_return: "заказ пока без продажи или возврата",
  sale_without_finance: "продажа без финансовой строки",
  stale_data: "данные нужно обновить",
  supplier_cost_coverage_below_threshold:
    "покрытие себестоимости ниже нужного порога",
  supplier_cost_not_confirmed: "себестоимость не подтверждена",
};

const TONE: Record<
  Tone,
  { card: string; icon: string; Icon: typeof CheckCircle2; badge: string }
> = {
  success: {
    card: "border-emerald-500/40 bg-emerald-500/5",
    icon: "text-emerald-600",
    Icon: CheckCircle2,
    badge:
      "bg-emerald-500/15 text-emerald-700 dark:text-emerald-300 border-emerald-500/30",
  },
  warning: {
    card: "border-amber-500/40 bg-amber-500/5",
    icon: "text-amber-600",
    Icon: Clock,
    badge:
      "bg-amber-500/15 text-amber-800 dark:text-amber-300 border-amber-500/30",
  },
  danger: {
    card: "border-red-500/40 bg-red-500/5",
    icon: "text-red-600",
    Icon: XCircle,
    badge: "bg-red-500/15 text-red-700 dark:text-red-300 border-red-500/30",
  },
};

function pickHeadline(trust?: TrustInput | null): { tone: Tone; text: string } {
  if (trust?.business_status === "data_blocked") {
    return {
      tone: "danger",
      text: "Расчеты заблокированы. Сначала исправьте данные",
    };
  }
  if (trust?.financial_final === true) {
    return {
      tone: "success",
      text: "Финальные финансовые данные подтверждены",
    };
  }
  if (trust?.operational_trusted === true) {
    return { tone: "warning", text: "Данные предварительные" };
  }
  return { tone: "warning", text: "Данные предварительные" };
}

function trustReasonLabel(reason: string): string {
  const normalized = reason.trim().toLowerCase();
  return (
    TRUST_REASON_LABELS[normalized] ||
    normalized.replace(/_/g, " ").replace(/\s+/g, " ")
  );
}

export function TrustStatusBanner({
  trust,
  quality,
  className = "",
}: TrustStatusBannerProps) {
  const head = pickHeadline(trust);

  const extras: { tone: Tone; text: string }[] = [];
  if (quality?.supplier_confirmed_cost_coverage_percent === 0) {
    extras.push({
      tone: "warning",
      text: "Подтвержденная себестоимость не загружена; используется операторская себестоимость",
    });
  }
  if (quality?.ads_allocation_status === "overallocated") {
    extras.push({
      tone: "warning",
      text: "Реклама распределена с предупреждением: возможное двойное распределение",
    });
  }
  if ((quality?.open_issues_total ?? 0) > 0) {
    extras.push({
      tone: "warning",
      text: `Открытые проблемы данных: ${quality!.open_issues_total}`,
    });
  }

  const worst: Tone =
    head.tone === "danger" || extras.some((e) => e.tone === "danger")
      ? "danger"
      : head.tone === "warning" || extras.some((e) => e.tone === "warning")
        ? "warning"
        : "success";
  const cfg = TONE[worst];
  const HeadIcon = cfg.Icon;

  // Reasons from backend (optional context, never overrides the rules above).
  const reasons = Array.from(
    new Set((trust?.trust_reasons ?? []).filter(Boolean).map(trustReasonLabel)),
  );
  // trust_label is allowed only if it's not the forbidden "Доверенные данные"
  // copy in a non-final state.
  const label =
    trust?.trust_label &&
    (trust.financial_final === true ||
      trust.trust_label !== "Доверенные данные")
      ? trust.trust_label
      : null;

  return (
    <Card className={`border ${cfg.card} ${className}`}>
      <CardContent className="p-4 flex items-start gap-3">
        <HeadIcon className={`h-5 w-5 mt-0.5 shrink-0 ${cfg.icon}`} />
        <div className="space-y-1.5 min-w-0 flex-1">
          <div className="flex items-center gap-2 flex-wrap">
            <div className="text-sm font-semibold leading-snug">
              {head.text}
            </div>
            {label ? (
              <Badge
                variant="outline"
                className={`text-[10px] py-0 px-1.5 ${cfg.badge}`}
              >
                {label}
              </Badge>
            ) : null}
          </div>
          {extras.map((l, i) => (
            <div
              key={i}
              className="text-sm leading-snug flex items-start gap-1.5"
            >
              {l.tone === "danger" ? (
                <AlertTriangle className="inline h-3.5 w-3.5 mt-0.5 text-red-600 shrink-0" />
              ) : null}
              <span>{l.text}</span>
            </div>
          ))}
          {reasons.length ? (
            <div className="text-xs text-muted-foreground pt-0.5">
              {reasons.join(" · ")}
            </div>
          ) : null}
        </div>
      </CardContent>
    </Card>
  );
}

type UnknownRecord = Record<string, unknown>;

function record(value: unknown): UnknownRecord {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as UnknownRecord)
    : {};
}

function optionalBoolean(value: unknown): boolean | null {
  return typeof value === "boolean" ? value : null;
}

function optionalString(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}

function optionalNumber(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function optionalStringList(value: unknown): string[] | null {
  if (!Array.isArray(value)) return null;
  const items = value.filter(
    (item): item is string => typeof item === "string" && item.trim() !== "",
  );
  return items.length ? items : null;
}

/** Adapter: build TrustStatusBanner inputs from MMoneySummary-shaped data. */
export function trustInputsFromSummary(s: unknown): {
  trust: TrustInput;
  quality: QualityInput;
} {
  const root = record(s);
  const k = record(root.kpis);
  const meta = record(root.meta);
  const dt = record(meta.data_trust);
  const ans = record(root.answer);
  const trust: TrustInput = {
    operational_trusted:
      optionalBoolean(root.operational_trusted) ??
      optionalBoolean(dt.operational_trusted),
    financial_final:
      optionalBoolean(root.financial_final) ??
      optionalBoolean(dt.financial_final),
    business_status:
      optionalString(ans.business_status) ?? optionalString(dt.business_status),
    trust_label: optionalString(dt.label) ?? optionalString(dt.human_label),
    trust_reasons:
      optionalStringList(dt.blocked_reasons) ?? optionalStringList(dt.reasons),
  };
  const quality: QualityInput = {
    finance_reconciliation_status:
      optionalString(root.finance_reconciliation_status) ??
      optionalString(k.finance_reconciliation_status),
    supplier_confirmed_cost_coverage_percent:
      optionalNumber(k.supplier_confirmed_cost_coverage_percent) ??
      optionalNumber(k.supplier_cost_confirmed_revenue_percent) ??
      optionalNumber(k.supplier_cost_coverage_percent),
    ads_allocation_status: optionalString(k.ads_allocation_status),
    open_issues_total: optionalNumber(root.open_issues_total),
  };
  return { trust, quality };
}
