import { useState } from "react";
import { Link } from "@tanstack/react-router";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  AlertTriangle,
  ChevronDown,
  ChevronRight,
  ExternalLink,
  Truck,
} from "lucide-react";
import {
  categoryLabel,
  formatMoneyRu,
  formatPercent,
  type BreakdownItem,
  type BreakdownResponse,
  type ProfitCascadeResponse,
  type ProfitCascadeGroup,
  type ProfitCascadeChild,
} from "@/lib/queries/expenses";

export interface WaterfallInput {
  /** Revenue fallback if no cascade/breakdown. */
  revenue?: number | null;
  /** Breakdown response from /money/expenses/breakdown (fallback). */
  breakdownData?: BreakdownResponse | null;
  /** Cascade response from /money/profit-cascade (primary source of truth). */
  cascadeData?: ProfitCascadeResponse | null;

  // ── Legacy props (per-card views without breakdown endpoint) ─────────
  forPay?: number | null;
  cogs?: number | null;
  wbExpenses?: number | null;
  adsSpend?: number | null;
  overhead?: number | null;
  profitAfterAds?: number | null;
  ownerProfit?: number | null;
}

// Categories that drill down to /expenses report-rows view.
const LOGISTICS_CODES = new Set([
  "wb_logistics",
  "wb_logistics_rebill",
  "logistics",
]);

function reportRowsSearch(category: string, from?: string, to?: string) {
  return {
    category,
    date_from: from,
    date_to: to,
  };
}

/** Build cascade groups from breakdown items as a fallback when /profit-cascade is unavailable.
 * Groups by canonical parent code so parent amounts always equal child sums.
 * Never collapses everything into one "Все расходы" bucket. */
function groupsFromBreakdown(
  b: BreakdownResponse | null | undefined,
): ProfitCascadeGroup[] {
  const items: BreakdownItem[] = Array.isArray(b?.items) ? b!.items! : [];
  if (items.length === 0) return [];

  const SELLER_COGS = new Set(["seller_cogs"]);
  const SELLER_OTHER = new Set([
    "seller_other_expense",
    "seller_other_expenses",
  ]);
  const ADS = new Set(["marketing_deduction", "ad_spend", "ads"]);
  const ADDITIONAL = new Set([
    "compensation",
    "surcharge",
    "additional_payment",
    "additional_income",
  ]);

  type Bucket = {
    code: string;
    label: string;
    sign: "expense" | "income";
    children: ProfitCascadeChild[];
  };
  const buckets: Bucket[] = [
    {
      code: "seller_cogs",
      label: "Себестоимость",
      sign: "expense",
      children: [],
    },
    {
      code: "seller_other_expenses",
      label: "Прочие расходы продавца",
      sign: "expense",
      children: [],
    },
    {
      code: "wb_direct_expenses",
      label: "Прямые расходы WB",
      sign: "expense",
      children: [],
    },
    {
      code: "ad_expenses",
      label: "Реклама / продвижение",
      sign: "expense",
      children: [],
    },
    {
      code: "additional_income",
      label: "Доплаты / компенсации",
      sign: "income",
      children: [],
    },
  ];
  const find = (code: string) => buckets.find((b) => b.code === code)!;

  for (const it of items) {
    const code = (it.category || "other") as string;
    const child: ProfitCascadeChild = {
      code,
      label: it.category_label || categoryLabel(code),
      amount: it.amount ?? 0,
      source: it.source ?? null,
      share_percent: it.share_percent ?? null,
    };
    if (SELLER_COGS.has(code)) find("seller_cogs").children.push(child);
    else if (SELLER_OTHER.has(code))
      find("seller_other_expenses").children.push(child);
    else if (ADS.has(code)) find("ad_expenses").children.push(child);
    else if (ADDITIONAL.has(code))
      find("additional_income").children.push(child);
    else find("wb_direct_expenses").children.push(child);
  }

  return buckets
    .filter((b) => b.children.length > 0)
    .map((b) => ({
      code: b.code,
      label: b.label,
      sign: b.sign,
      amount: b.children.reduce((s, c) => s + (c.amount ?? 0), 0),
      children: b.children,
    }));
}

export function MoneyWaterfall(
  p: WaterfallInput & { dateFrom?: string; dateTo?: string },
) {
  const cascadeBody = p.cascadeData?.cascade ?? null;
  const backendGroups: ProfitCascadeGroup[] = cascadeBody?.groups ?? [];

  // Fallback path: synthesize from breakdown or legacy props.
  const syntheticBreakdown: BreakdownResponse | null =
    !p.breakdownData &&
    !cascadeBody &&
    (p.cogs != null ||
      p.wbExpenses != null ||
      p.adsSpend != null ||
      p.overhead != null)
      ? {
          revenue_final: p.revenue ?? null,
          net_profit_after_all_expenses: p.ownerProfit ?? null,
          items: [
            p.cogs != null ? { category: "seller_cogs", amount: p.cogs } : null,
            p.overhead != null
              ? { category: "seller_other_expense", amount: p.overhead }
              : null,
            p.wbExpenses != null
              ? {
                  category: "wb_other",
                  amount: p.wbExpenses,
                  category_label: "Прямые расходы WB",
                }
              : null,
            p.adsSpend != null
              ? { category: "marketing_deduction", amount: p.adsSpend }
              : null,
          ].filter((item): item is BreakdownItem => item != null),
        }
      : null;
  const effectiveBreakdown = p.breakdownData ?? syntheticBreakdown;

  const groups: ProfitCascadeGroup[] =
    backendGroups.length > 0
      ? backendGroups
      : groupsFromBreakdown(effectiveBreakdown);

  const revenue =
    cascadeBody?.revenue?.amount ??
    cascadeBody?.totals?.gross_revenue ??
    p.breakdownData?.revenue_final ??
    p.revenue ??
    null;

  const netProfit =
    cascadeBody?.totals?.net_profit_after_all_expenses ??
    p.breakdownData?.net_profit_after_all_expenses ??
    (revenue == null
      ? null
      : revenue -
        groups
          .filter((g) => (g.sign ?? "expense") === "expense")
          .reduce((s, g) => s + Math.abs(g.amount ?? 0), 0) +
        groups
          .filter((g) => g.sign === "income")
          .reduce((s, g) => s + Math.abs(g.amount ?? 0), 0));

  const validation = cascadeBody?.validation;
  const showMismatch =
    validation?.groups_match_children === false ||
    validation?.profit_formula_valid === false;
  const issues = validation?.issues ?? [];

  const [open, setOpen] = useState<Record<string, boolean>>({});
  const toggle = (code: string) => setOpen((o) => ({ ...o, [code]: !o[code] }));

  return (
    <Card>
      <CardHeader className="pb-2 flex flex-row items-center justify-between">
        <CardTitle className="text-base">Каскад прибыли</CardTitle>
        {showMismatch ? (
          <Badge
            variant="outline"
            className="gap-1 text-amber-700 border-amber-500/40 bg-amber-500/10"
          >
            <AlertTriangle className="h-3 w-3" /> Расхождение в данных
          </Badge>
        ) : null}
      </CardHeader>
      <CardContent className="space-y-1">
        {showMismatch && issues.length > 0 ? (
          <div className="mb-2 text-xs text-amber-800 bg-amber-50 border border-amber-200 rounded px-2 py-1.5 space-y-0.5">
            {issues.map((it, i) => (
              <div key={i}>• {it}</div>
            ))}
          </div>
        ) : null}

        {/* Revenue */}
        <RowLine
          label={cascadeBody?.revenue?.label || "Выручка"}
          value={revenue}
          kind="income"
          bold
        />

        {groups.map((g) => {
          const isIncome = g.sign === "income";
          const sign = isIncome ? "+" : "−";
          const colorCls = isIncome ? "text-emerald-700" : "text-red-600";
          const amount = Math.abs(g.amount ?? 0);
          const children = g.children ?? [];
          const canExpand = children.length > 0;
          const isOpen = !!open[g.code];

          return (
            <div key={g.code}>
              <div
                className={`flex items-center justify-between py-1.5 px-2 rounded ${canExpand ? "cursor-pointer hover:bg-muted/40" : ""}`}
                onClick={canExpand ? () => toggle(g.code) : undefined}
              >
                <div className="text-sm flex items-center gap-1">
                  {canExpand ? (
                    isOpen ? (
                      <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
                    ) : (
                      <ChevronRight className="h-3.5 w-3.5 text-muted-foreground" />
                    )
                  ) : (
                    <span className="w-3.5" />
                  )}
                  <span>
                    {sign} {g.label}
                  </span>
                  {canExpand ? (
                    <span className="text-[11px] text-muted-foreground ml-1">
                      ({children.length})
                    </span>
                  ) : null}
                </div>
                <div className={`text-sm tabular-nums ${colorCls}`}>
                  {sign}
                  {formatMoneyRu(amount)}
                </div>
              </div>
              {canExpand && isOpen ? (
                <div className="ml-6 mb-1 border-l pl-3 space-y-1">
                  {children
                    .slice()
                    .sort(
                      (a, b) =>
                        Math.abs(b.amount ?? 0) - Math.abs(a.amount ?? 0),
                    )
                    .map((it, k) => {
                      const rawAmt = it.amount ?? 0;
                      // Negative amount within an expense bucket = income/correction (and vice versa).
                      const childIsIncome = isIncome ? rawAmt >= 0 : rawAmt < 0;
                      const childSign = childIsIncome ? "+" : "−";
                      const childCls = childIsIncome
                        ? "text-emerald-700"
                        : "text-red-600";
                      const childAmt = Math.abs(rawAmt);
                      const isHL = LOGISTICS_CODES.has(it.code);
                      return (
                        <Link
                          key={k}
                          to="/expenses"
                          search={reportRowsSearch(
                            it.code,
                            p.dateFrom,
                            p.dateTo,
                          )}
                          className={`flex items-center justify-between text-xs py-1 px-1.5 rounded hover:bg-muted/40 ${isHL ? "bg-amber-50 border-l-2 border-amber-400 -ml-[2px] pl-[6px]" : ""}`}
                        >
                          <div className="flex items-center gap-2 min-w-0">
                            {isHL ? (
                              <Truck className="h-3.5 w-3.5 text-amber-600 shrink-0" />
                            ) : null}
                            <span className="truncate">
                              {it.label || categoryLabel(it.code)}
                            </span>
                            {childIsIncome !== isIncome ? (
                              <Badge
                                variant="outline"
                                className="text-[10px] border-emerald-500/40 text-emerald-700 bg-emerald-50"
                              >
                                корр.
                              </Badge>
                            ) : null}
                            {it.source ? (
                              <Badge
                                variant="outline"
                                className="text-[10px] border-muted-foreground/30 text-muted-foreground"
                              >
                                {it.source}
                              </Badge>
                            ) : null}
                            <ExternalLink className="h-3 w-3 text-muted-foreground/60 shrink-0" />
                          </div>
                          <div className="flex items-center gap-3 shrink-0">
                            <span
                              className={`tabular-nums w-28 text-right ${childCls}`}
                            >
                              {childSign}
                              {formatMoneyRu(childAmt)}
                            </span>
                            {it.share_percent != null &&
                            it.share_percent > 0 ? (
                              <span className="text-[11px] text-muted-foreground tabular-nums w-12 text-right">
                                {formatPercent(it.share_percent)}
                              </span>
                            ) : null}
                          </div>
                        </Link>
                      );
                    })}
                </div>
              ) : null}
            </div>
          );
        })}

        {/* Final net profit */}
        <div
          className={`flex items-center justify-between py-2 px-2 mt-1 rounded font-semibold ${netProfit != null && netProfit < 0 ? "bg-red-50" : "bg-emerald-50"}`}
        >
          <div className="text-sm">= Чистая прибыль после всех расходов</div>
          <div
            className={`text-sm tabular-nums ${netProfit != null && netProfit < 0 ? "text-red-700" : "text-emerald-700"}`}
          >
            {netProfit == null
              ? "—"
              : (netProfit < 0 ? "−" : "") + formatMoneyRu(Math.abs(netProfit))}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function RowLine({
  label,
  value,
  kind,
  bold,
}: {
  label: string;
  value: number | null | undefined;
  kind: "income" | "expense";
  bold?: boolean;
}) {
  const cls = kind === "income" ? "text-emerald-700" : "text-red-600";
  return (
    <div
      className={`flex items-center justify-between py-1.5 px-2 rounded ${bold ? "font-semibold" : ""}`}
    >
      <div className="text-sm">{label}</div>
      <div className={`text-sm tabular-nums ${cls}`}>
        {value == null ? "—" : formatMoneyRu(value)}
      </div>
    </div>
  );
}

// ── Boss-friendly insight card ──────────────────────────────────────────
export interface BossInsightInput {
  logisticsTotal?: number | null;
  logisticsSharePercent?: number | null;
  totalWbExpenses?: number | null;
  netProfit?: number | null;
}
export function BossInsightCard(p: BossInsightInput) {
  const share = p.logisticsSharePercent;
  const net = p.netProfit;
  const logisticsAlert = share != null && share >= 70;
  const lossAlert = net != null && net < 0;

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-base">Главный вывод</CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
          <Metric
            label="Логистика Вайлдберриз"
            value={formatMoneyRu(p.logisticsTotal)}
          />
          <Metric
            label="Доля логистики"
            value={formatPercent(p.logisticsSharePercent)}
            tone={logisticsAlert ? "warn" : undefined}
          />
          <Metric
            label="Расходы Вайлдберриз"
            value={formatMoneyRu(p.totalWbExpenses)}
          />
          <Metric
            label="Чистая прибыль"
            value={
              net == null
                ? "—"
                : (net < 0 ? "−" : "") + formatMoneyRu(Math.abs(net))
            }
            tone={
              lossAlert ? "bad" : net != null && net > 0 ? "good" : undefined
            }
          />
        </div>
        {logisticsAlert ? (
          <div className="text-sm bg-amber-50 border border-amber-300 text-amber-900 rounded px-3 py-2">
            Основной источник расходов — логистика WB. Нужно разбирать отмены,
            возвраты и обратную логистику.
          </div>
        ) : null}
        {lossAlert ? (
          <div className="text-sm bg-red-50 border border-red-300 text-red-900 rounded px-3 py-2">
            С учетом всех расходов период убыточный.
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}

function Metric({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: "good" | "bad" | "warn";
}) {
  const c =
    tone === "good"
      ? "text-emerald-700"
      : tone === "bad"
        ? "text-red-700"
        : tone === "warn"
          ? "text-amber-700"
          : "";
  return (
    <div>
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className={`text-base font-semibold tabular-nums ${c}`}>{value}</div>
    </div>
  );
}
