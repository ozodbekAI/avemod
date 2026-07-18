// Banner that surfaces "финальный финансовый результат ещё не закрыт"
// whenever financial_final === false.
//
// Pulls open financial-final blockers from /dq/issues?financial_final_blocker=true
// and shows only blockers the operator can actually fix.
//
// Renders nothing when financial_final === true.

import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { useMemo } from "react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { AlertTriangle, ArrowRight } from "lucide-react";
import {
  api,
  type DataQualityIssue,
  type DataQualityIssuesPage,
  type MMoneySummary,
} from "@/lib/api";
import { API_ENDPOINTS } from "@/lib/endpoints";
import { normalizeTrust } from "@/lib/trust";

interface Props {
  accountId: number | null | undefined;
  dateFrom?: string;
  dateTo?: string;
  /** Money / dashboard summary used to derive trust state. */
  summary?: MMoneySummary | null;
  className?: string;
}

const GROUPS: Array<{
  key: "missing_manual_cost" | "supplier_confirmed_cost_missing";
  label: string;
  codes: string[];
}> = [
  {
    key: "missing_manual_cost",
    label: "Нет ручной себестоимости",
    codes: [
      "missing_manual_cost",
      "manual_cost_ambiguous_match",
      "manual_cost_unresolved_sku",
    ],
  },
  {
    key: "supplier_confirmed_cost_missing",
    label: "Нет подтвержденной себестоимости поставщика",
    codes: [
      "supplier_confirmed_cost_missing",
      "supplier_cost_missing",
      "supplier_cost_not_confirmed",
    ],
  },
];

const SYSTEM_HANDLED_CODES = new Set([
  "finance_reconciliation_mismatch",
  "finance_mismatch",
  "finance_without_sale",
  "sale_without_finance",
  "sales_without_finance",
  "order_without_sale_or_return",
]);

function trustStateLabel(value: string): string {
  switch (String(value).toLowerCase()) {
    case "trusted":
    case "ok":
    case "ready":
      return "доверенные данные";
    case "data_blocked":
    case "blocked":
      return "есть блокировка";
    case "warning":
    case "partial":
      return "требует проверки";
    default:
      return "требует проверки";
  }
}

function costPolicyLabel(value: string): string {
  switch (String(value).toLowerCase()) {
    case "manual":
      return "ручная";
    case "supplier_confirmed":
      return "подтверждена поставщиком";
    case "operator_baseline":
      return "операторская база";
    default:
      return "требует проверки";
  }
}

export function FinancialFinalBlockerBanner({
  accountId,
  dateFrom,
  dateTo,
  summary,
  className = "",
}: Props) {
  const trust = normalizeTrust(summary ?? {});
  const enabled = !!accountId && trust.financialFinal === false;

  const issuesQ = useQuery({
    queryKey: [
      "dq-issues-final-blockers",
      accountId,
      dateFrom ?? null,
      dateTo ?? null,
    ],
    enabled,
    queryFn: ({ signal }) =>
      api<DataQualityIssuesPage>(API_ENDPOINTS.dq.issues, {
        query: {
          account_id: accountId!,
          only_open: true,
          financial_final_blocker: true,
          ...(dateFrom ? { date_from: dateFrom } : {}),
          ...(dateTo ? { date_to: dateTo } : {}),
          limit: 100,
        },
        signal,
      }),
    retry: false,
    staleTime: 60 * 1000,
  });

  const issues: DataQualityIssue[] = useMemo(
    () => issuesQ.data?.items ?? [],
    [issuesQ.data],
  );

  const grouped = useMemo(() => {
    const out = new Map<string, number>();
    for (const g of GROUPS) out.set(g.key, 0);
    for (const it of issues) {
      const code = String(it.code ?? "").toLowerCase();
      if (SYSTEM_HANDLED_CODES.has(code)) continue;
      const g = GROUPS.find((g) => g.codes.includes(code));
      if (g) out.set(g.key, (out.get(g.key) ?? 0) + 1);
    }
    return out;
  }, [issues]);

  if (!enabled) return null;

  const blockersTotal = Array.from(grouped.values()).reduce(
    (sum, n) => sum + n,
    0,
  );
  if (blockersTotal <= 0) return null;

  const supplierPct = trust.supplierConfirmedCoverage;
  const trustState = trust.trustState;
  const costPolicy = trust.costTrustPolicy;

  return (
    <Alert variant="destructive" className={className}>
      <AlertTriangle className="h-4 w-4" />
      <AlertTitle>Финальный финансовый результат еще не закрыт.</AlertTitle>
      <AlertDescription className="space-y-2">
        <div className="flex flex-wrap gap-1.5 text-[11px]">
          {blockersTotal != null && (
            <Badge variant="outline">блокеров: {blockersTotal}</Badge>
          )}
          {supplierPct != null && (
            <Badge variant="outline">
              Подтверждено поставщиком: {supplierPct.toFixed(1)}%
            </Badge>
          )}
          {trustState && (
            <Badge variant="outline">
              Статус доверия: {trustStateLabel(trustState)}
            </Badge>
          )}
          {costPolicy && (
            <Badge variant="outline">
              Политика себестоимости: {costPolicyLabel(costPolicy)}
            </Badge>
          )}
        </div>

        <ul className="text-sm space-y-1">
          {GROUPS.map((g) => {
            const n = grouped.get(g.key) ?? 0;
            return (
              <li
                key={g.key}
                className="flex items-center justify-between gap-2"
              >
                <span className={n > 0 ? "" : "text-muted-foreground"}>
                  {g.label}
                </span>
                <Badge
                  variant={n > 0 ? "destructive" : "outline"}
                  className="text-[10px]"
                >
                  {n}
                </Badge>
              </li>
            );
          })}
        </ul>

        <div>
          <Button asChild size="sm" variant="outline" className="h-7">
            <Link to="/data-fix">
              Открыть исправление данных <ArrowRight className="h-3 w-3 ml-1" />
            </Link>
          </Button>
        </div>
      </AlertDescription>
    </Alert>
  );
}
