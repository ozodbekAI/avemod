// @ts-nocheck
import { createFileRoute, Link, useParams } from "@tanstack/react-router";
import { normalizeTrust } from "@/lib/trust";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type MCardDetail } from "@/lib/api";
import { fetchArticleDetail } from "@/lib/money-endpoints";
import {
  analyzeProductCardQuality,
  fetchProduct360,
  type PortalProduct360Read,
} from "@/lib/portal";
import { useAccounts } from "@/lib/account-context";
import { useAuth } from "@/lib/auth-context";
import { PageShell } from "@/components/PageShell";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { MoneyWaterfall, TrustStatusBanner } from "@/components/money-ui";
import { BusinessActionCard } from "@/components/money/BusinessActionCard";
import { formatMoney, formatPercent, formatNumber } from "@/lib/format";
import { humanizeAction, humanizeAdsStatus } from "@/lib/copy";
import {
  ArrowLeft,
  AlertTriangle,
  Wallet,
  Megaphone,
  Package,
  Tag,
  Activity,
  Layers,
  ListChecks,
  TrendingUp,
  ArrowRight,
  Code2,
  ShieldCheck,
} from "lucide-react";
import { EndpointError } from "@/components/EndpointError";
import { useDateRange } from "@/lib/date-range-context";
import { toast } from "sonner";
import { DataDependencyNotice } from "@/components/data-health/DataCoveragePanel";
import { ProductDoctorSection } from "@/components/portal/ProductDoctorSection";
import { LegacyDiagnosticNotice } from "@/components/LegacyDiagnosticNotice";
import { canAccessLegacyDiagnostics } from "@/lib/legacy-diagnostics";

export const Route = createFileRoute("/_authenticated/cards/$nmId")({
  component: ArticleDetailPage,
  errorComponent: ({ error, reset }) => (
    <EndpointError error={error} reset={reset} />
  ),
});

function ArticleDetailPage() {
  const { nmId } = useParams({ from: "/_authenticated/cards/$nmId" });
  const { activeId } = useAccounts();
  const { user } = useAuth();
  const nm = Number(nmId);
  const legacyAllowed = canAccessLegacyDiagnostics(user?.is_superuser);

  const { from: dateFrom, to: dateTo } = useDateRange();

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["money-article-detail", activeId, nm, dateFrom, dateTo],
    enabled: !!activeId && Number.isFinite(nm) && legacyAllowed,
    queryFn: () =>
      fetchArticleDetail(nm, {
        accountId: activeId!,
        dateFrom,
        dateTo,
      }) as Promise<MCardDetail>,
  });
  const productDoctorQuery = useQuery({
    queryKey: ["portal-product-detail", activeId, nm, dateFrom, dateTo],
    enabled: !!activeId && Number.isFinite(nm) && legacyAllowed,
    queryFn: () => fetchProduct360(nm, activeId, { dateFrom, dateTo }),
    staleTime: 60_000,
  });

  if (!legacyAllowed) {
    return (
      <PageShell>
        <Alert data-testid="legacy-card-detail-hidden">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>Карточка открывается в Product360</AlertTitle>
          <AlertDescription className="space-y-3">
            <div>
              Старый экран карточки скрыт, чтобы не показывать параллельные
              hardcoded-флаги. Динамические проблемы товара доступны в карточке
              товара и Центре действий.
            </div>
            <div className="flex flex-wrap gap-2">
              <Button asChild size="sm">
                <Link
                  to={"/products/$nmId" as any}
                  params={{ nmId: String(nm) } as any}
                >
                  Открыть товар
                </Link>
              </Button>
              <Button asChild size="sm" variant="outline">
                <Link
                  to={"/action-center" as any}
                  search={{ nm_id: String(nm) } as any}
                >
                  Открыть Центр действий
                </Link>
              </Button>
            </div>
          </AlertDescription>
        </Alert>
      </PageShell>
    );
  }

  return (
    <PageShell>
      <div className="mb-3">
        <Button asChild variant="ghost" size="sm">
          <Link to="/cards">
            <ArrowLeft className="h-4 w-4 mr-1" /> Все карточки
          </Link>
        </Button>
      </div>

      <LegacyDiagnosticNotice surfaceId="legacy_card_detail_flags" />

      {activeId && (
        <DataDependencyNotice
          accountId={activeId}
          domains={[
            "product_cards",
            "sales",
            "orders",
            "finance",
            "stocks",
            "prices",
            "ads",
          ]}
        />
      )}

      {isLoading && (
        <div className="grid gap-3">
          {[1, 2, 3, 4].map((i) => (
            <Skeleton key={i} className="h-32" />
          ))}
        </div>
      )}
      {isError && (
        <Alert variant="destructive">
          <AlertTitle>Ошибка</AlertTitle>
          <AlertDescription>{(error as Error)?.message}</AlertDescription>
        </Alert>
      )}

      {data && (
        <Body
          d={data}
          nm={nm}
          accountId={activeId}
          product360={productDoctorQuery.data}
        />
      )}
    </PageShell>
  );
}

type DecisionKey =
  "REORDER" | "LIQUIDATE" | "WATCH" | "DO_NOT_BUY" | "DATA_FIX" | "";
const DECISION_LABEL: Record<Exclude<DecisionKey, "">, string> = {
  REORDER: "Дозаказать",
  LIQUIDATE: "Ликвидировать",
  WATCH: "Наблюдать",
  DO_NOT_BUY: "Не закупать",
  DATA_FIX: "Сначала data-fix",
};

function mapDecision(raw: string | undefined): DecisionKey {
  const r = (raw || "").toUpperCase();
  if (!r) return "";
  if (r.includes("REORDER") || r.includes("SCALE")) return "REORDER";
  if (r.includes("LIQUIDAT") || r.includes("DISCOUNT_TO_CLEAR"))
    return "LIQUIDATE";
  if (r.includes("STOP") || r.includes("DO_NOT")) return "DO_NOT_BUY";
  if (r.includes("DATA") || r.includes("FIX")) return "DATA_FIX";
  if (r.includes("WATCH") || r.includes("MONITOR")) return "WATCH";
  return "";
}

function trustOf(state: string | undefined): {
  tone: "success" | "warning" | "danger" | "muted";
  label: string;
} {
  const s = (state || "").toLowerCase();
  if (!s) return { tone: "muted", label: "—" };
  if (
    s === "final" ||
    s === "trusted" ||
    s === "financial_final" ||
    s === "operational_final"
  ) {
    return {
      tone: "success",
      label:
        s === "financial_final"
          ? "Финансово подтверждено"
          : s === "operational_final"
            ? "Операционно подтверждено"
            : "Финально",
    };
  }
  if (s === "operational_trusted")
    return { tone: "success", label: "Операционно доверенные" };
  if (
    s === "provisional" ||
    s === "preliminary" ||
    s === "operational_provisional" ||
    s === "financial_provisional" ||
    s === "test_only"
  ) {
    return {
      tone: "warning",
      label:
        s === "operational_provisional"
          ? "Операционно предварительно"
          : s === "financial_provisional"
            ? "Финансово предварительно"
            : "Предварительно",
    };
  }
  if (s === "blocked" || s === "data_blocked")
    return { tone: "danger", label: "Данные заблокированы" };
  return { tone: "muted", label: state || "—" };
}

function ToneBadge({
  tone,
  children,
}: {
  tone: "success" | "warning" | "danger" | "info" | "muted";
  children: React.ReactNode;
}) {
  const tones: Record<string, string> = {
    success: "bg-success/15 text-success border-success/30",
    warning: "bg-warning/15 text-warning border-warning/30",
    danger: "bg-destructive/15 text-destructive border-destructive/30",
    info: "bg-primary/10 text-primary border-primary/30",
    muted: "bg-muted text-muted-foreground border-border",
  };
  return (
    <Badge
      variant="outline"
      className={`text-[10px] border px-1.5 py-0.5 ${tones[tone]}`}
    >
      {children}
    </Badge>
  );
}

function Body({
  d,
  nm,
  accountId,
  product360,
}: {
  d: MCardDetail;
  nm: number;
  accountId?: number | null;
  product360?: PortalProduct360Read;
}) {
  const queryClient = useQueryClient();
  const analyzeMutation = useMutation({
    mutationFn: () =>
      analyzeProductCardQuality(nm, accountId, { force: false }),
    onSuccess: () => {
      toast.success("Проверка карточки выполнена");
      queryClient.invalidateQueries({ queryKey: ["money-article-detail"] });
      queryClient.invalidateQueries({ queryKey: ["portal-product-detail"] });
      queryClient.invalidateQueries({ queryKey: ["checker-product-quality"] });
    },
    onError: (error: any) =>
      toast.error(error?.message ?? "Не удалось проверить карточку"),
  });
  const m: any = d.money;
  const op = d.operations;
  const f = d.funnel;
  const id = d.identity;
  const _trust = normalizeTrust(d);
  const trust = (_trust.trustState ?? "") as string;
  const trustView = trustOf(trust);
  const financialFinal = _trust.financialFinal;
  const decision = mapDecision((d.answer as any).decision);
  const moneyAnswer = d.answer?.short_text || d.answer?.title || "";
  const nextStep =
    d.answer?.main_next_step || d.next_actions?.[0]?.what_to_do || "";
  const adsUnallocated = (m.ads?.unallocated_spend ?? 0) > 0;
  const wbExpenses = m.wb_expenses ?? {};
  const accountLevelLogistics =
    wbExpenses.account_level_logistics ?? wbExpenses.unallocated_logistics ?? 0;
  const directLogistics =
    (wbExpenses.wb_logistics ?? 0) +
    (wbExpenses.wb_logistics_rebill ?? 0) +
    (wbExpenses.logistics ?? 0);
  const logisticsNotLinked =
    accountLevelLogistics > 0 &&
    (directLogistics <= 0 ||
      wbExpenses.logistics_mapping_status === "not_linked_to_sku" ||
      wbExpenses.logistics_mapping_status === "partial_account_level" ||
      wbExpenses.reason === "wb_logistics_not_linked_to_sku" ||
      wbExpenses.reason === "wb_logistics_partially_linked_to_sku" ||
      wbExpenses.status === "account_level_logistics_not_allocated" ||
      wbExpenses.status === "account_level_logistics_partially_allocated");
  const overhead = m.allocated_overhead ?? null;
  const variants = d.variant_breakdown ?? [];

  // SECTION 1 — Header summary
  return (
    <>
      {/* === 1. HEADER === */}
      <Card className="border-2">
        <CardHeader className="pb-3">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <CardTitle className="text-xl">
                {id.title || `nm ${nm}`}
              </CardTitle>
              <div className="text-xs text-muted-foreground font-mono mt-1">
                nm {nm}
                {id.vendor_code ? ` · ${id.vendor_code}` : ""}
                {id.brand ? ` · ${id.brand}` : ""}
                {id.subject_name ? ` · ${id.subject_name}` : ""}
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              {decision && (
                <ToneBadge
                  tone={
                    decision === "REORDER"
                      ? "success"
                      : decision === "LIQUIDATE" || decision === "DO_NOT_BUY"
                        ? "danger"
                        : decision === "DATA_FIX"
                          ? "warning"
                          : "info"
                  }
                >
                  {decision} · {DECISION_LABEL[decision]}
                </ToneBadge>
              )}
              <ToneBadge
                tone={trustView.tone === "muted" ? "muted" : trustView.tone}
              >
                {trustView.label}
              </ToneBadge>
              <Button
                size="sm"
                variant="outline"
                onClick={() => analyzeMutation.mutate()}
                disabled={!accountId || analyzeMutation.isPending}
              >
                <ShieldCheck className="h-3.5 w-3.5 mr-1" /> Проверить
              </Button>
              <Button asChild size="sm">
                <Link to="/checker/$nmId" params={{ nmId: String(nm) }}>
                  <ListChecks className="h-3.5 w-3.5 mr-1" /> Проверка карточки
                </Link>
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-2">
          {moneyAnswer && (
            <div className="text-sm">
              <span className="font-semibold">Деньги по карточке: </span>
              {moneyAnswer}
            </div>
          )}
          {nextStep && (
            <div className="text-sm">
              <span className="font-semibold">Следующий шаг: </span>
              {nextStep}
            </div>
          )}
          {!financialFinal && (
            <div className="text-sm text-warning font-medium">
              Финальная прибыль предварительная — финал ещё не подтверждён
              финансовым отчётом.
            </div>
          )}
        </CardContent>
      </Card>

      {/* Top-level trust banner with all warnings */}
      <div className="mt-4">
        <TrustStatusBanner
          trust={{
            operational_trusted: (d.meta as any).operational_trusted,
            financial_final: financialFinal,
            business_status: (d.meta as any).business_status,
            trust_label: (d.meta as any).data_trust?.human_message,
            trust_reasons: (d.meta as any).trust_reasons,
          }}
          quality={{
            finance_reconciliation_status: d.reconciliation?.status,
            supplier_confirmed_cost_coverage_percent: m.cogs?.supplier_confirmed
              ? 100
              : 0,
            ads_allocation_status: m.ads?.allocation_status,
            open_issues_total:
              (d as any).open_issues?.length ?? d.problems?.length ?? 0,
          }}
        />
      </div>

      {product360 ? (
        <ProductDoctorSection
          className="mt-4"
          block={product360.business_issues}
          actions={product360.actions}
          resultHistory={product360.result_history}
          nmId={nm}
        />
      ) : null}

      {/* === 2. MONEY WATERFALL === */}
      <Card className="mt-4">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Wallet className="h-4 w-4" /> Денежный водопад по карточке
          </CardTitle>
          <CardDescription>
            По прямым расходам карточки — не финальная прибыль. Полный каскад с
            распределением общих расходов аккаунта смотрите на странице{" "}
            <a href="/money" className="underline">
              Деньги
            </a>
            .
          </CardDescription>
        </CardHeader>
        <CardContent>
          <MoneyWaterfall
            revenue={m.revenue ?? null}
            forPay={m.for_pay ?? null}
            cogs={m.cogs?.estimated_cogs ?? null}
            wbExpenses={m.wb_expenses_total ?? null}
            adsSpend={m.ads?.source_spend ?? null}
            overhead={overhead}
            profitAfterAds={m.profit?.after_ads ?? null}
            ownerProfit={m.owner_profit_after_overhead ?? null}
          />
          <div className="mt-3 flex flex-wrap items-center gap-2 text-xs">
            <span className="text-muted-foreground">Прибыль до рекламы:</span>
            <span className="font-medium tabular-nums">
              {formatMoney(m.profit?.before_ads ?? null)}
            </span>
            <span className="text-muted-foreground">· Маржа:</span>
            <span className="tabular-nums">
              {formatPercent(m.profit?.margin_after_ads_percent)}
            </span>
            <span className="text-muted-foreground">· ROI:</span>
            <span className="tabular-nums">
              {formatPercent(m.profit?.roi_after_ads_percent)}
            </span>
            <span className="ml-auto">
              <ToneBadge tone="warning">
                по прямым расходам, не финальная прибыль
              </ToneBadge>
            </span>
          </div>
          {logisticsNotLinked && (
            <Alert className="mt-3 border-warning/40 bg-warning/5">
              <AlertTriangle className="h-4 w-4 text-warning" />
              <AlertTitle className="text-warning">
                Логистика WB не привязана к SKU/карточке
              </AlertTitle>
              <AlertDescription>
                В финансовом отчете есть логистика {formatMoney(accountLevelLogistics)}, но она пришла без прямой привязки SKU/баркода.
                Прибыль карточки предварительная, пока логистика не распределена.
              </AlertDescription>
            </Alert>
          )}
        </CardContent>
      </Card>

      {/* === 3. ADS === */}
      {m.ads && (
        <Card className="mt-4">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Megaphone className="h-4 w-4" /> Реклама
            </CardTitle>
            <CardDescription>
              Куда уходят рекламные деньги по этой карточке.
            </CardDescription>
          </CardHeader>
          <CardContent className="grid gap-3 md:grid-cols-4">
            <Stat label="Расход рекламы (источник)">
              {formatMoney(m.ads.source_spend)}
            </Stat>
            <Stat label="Разнесено на карточку">
              {formatMoney(m.ads.allocated_spend)}
            </Stat>
            <Stat label="Не привязано">
              <span
                className={adsUnallocated ? "text-warning font-semibold" : ""}
              >
                {formatMoney(m.ads.unallocated_spend)}
              </span>
            </Stat>
            <Stat label="ДРР (источник)">
              {formatPercent(m.ads.drr_percent_source)}
            </Stat>
            <Stat label="Просмотры">
              {m.ads.views == null ? "—" : formatNumber(m.ads.views)}
            </Stat>
            <Stat label="Клики">
              {m.ads.clicks == null ? "—" : formatNumber(m.ads.clicks)}
            </Stat>
            <Stat label="Заказы с рекламы">
              {m.ads.orders == null ? "—" : formatNumber(m.ads.orders)}
            </Stat>
            <Stat label="Привязка рекламы">
              <ToneBadge
                tone={
                  m.ads.allocation_status === "ok"
                    ? "success"
                    : adsUnallocated
                      ? "warning"
                      : "muted"
                }
              >
                {humanizeAdsStatus(m.ads.allocation_status || "") || "—"}
              </ToneBadge>
            </Stat>
          </CardContent>
          {(adsUnallocated || m.ads.allocation_status === "overallocated") && (
            <CardContent className="pt-0">
              <Alert className="border-warning/40 bg-warning/5">
                <AlertTriangle className="h-4 w-4 text-warning" />
                <AlertTitle className="text-warning">
                  Реклама не полностью привязана
                </AlertTitle>
                <AlertDescription>
                  {adsUnallocated && (
                    <>
                      Не привязано {formatMoney(m.ads.unallocated_spend)} —
                      прибыль предварительная.{" "}
                    </>
                  )}
                  {m.ads.allocation_status === "overallocated" && (
                    <>Возможное двойное распределение по nm_id.</>
                  )}
                </AlertDescription>
              </Alert>
            </CardContent>
          )}
        </Card>
      )}

      {/* === 4. STOCK === */}
      {d.stock &&
        (() => {
          const st: any = d.stock;
          const isOverstock =
            st.stock_status === "overstock" || (st.overstock_value ?? 0) > 0;
          const isOOSRisk =
            st.stock_status === "oos" ||
            st.stock_status === "low" ||
            st.oos_risk === true ||
            st.oos_risk === "yes";
          return (
            <Card className="mt-4">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Package className="h-4 w-4" /> Остатки
                </CardTitle>
                <CardDescription>
                  Сколько денег заморожено и где есть риск остаться без товара.
                </CardDescription>
              </CardHeader>
              <CardContent className="grid gap-3 md:grid-cols-4">
                <Stat label="Остаток, шт.">
                  {formatNumber(st.quantity_full ?? st.quantity)}
                </Stat>
                <Stat label="Стоимость остатка, ₽">
                  {formatMoney(st.stock_value)}
                </Stat>
                <Stat label="В пути, шт.">
                  {formatNumber(st.in_transit_qty)}
                </Stat>
                <Stat label="В пути, ₽">
                  {formatMoney(st.in_transit_value)}
                </Stat>
                <Stat label="Дней запаса">{st.days_of_stock ?? "—"}</Stat>
                <Stat label="Скорость продаж, шт/день">
                  {st.sales_velocity ?? "—"}
                </Stat>
                <Stat label="Сверхзапас, ₽">
                  {formatMoney(st.overstock_value ?? null)}
                </Stat>
                <Stat label="Статус остатка">{st.stock_status ?? "—"}</Stat>
              </CardContent>
              {(isOverstock || isOOSRisk) && (
                <CardContent className="pt-0 space-y-2">
                  {isOverstock && (
                    <Alert className="border-warning/40 bg-warning/5">
                      <AlertTitle className="text-warning">
                        Перетарка / сверхзапас
                      </AlertTitle>
                      <AlertDescription>
                        Заморожено{" "}
                        {formatMoney(st.overstock_value ?? st.stock_value)}.
                        Рассмотрите ликвидацию или скидку.
                      </AlertDescription>
                    </Alert>
                  )}
                  {isOOSRisk && (
                    <Alert variant="destructive">
                      <AlertTitle>Риск остаться без товара</AlertTitle>
                      <AlertDescription>
                        Запаса хватит на {st.days_of_stock ?? "—"} дн.
                        Запланируйте дозаказ.
                      </AlertDescription>
                    </Alert>
                  )}
                </CardContent>
              )}
            </Card>
          );
        })()}

      {/* === 5. PRICE SAFETY === */}
      {d.price &&
        (() => {
          const p: any = d.price;
          const calcState =
            p.calculation_state ||
            p.status ||
            (p.not_computable_reason ? "not_computable" : "ready");
          const calcTone = ["ready", "estimated_safe", "ok"].includes(calcState)
            ? "success"
            : calcState === "not_computable"
              ? "warning"
              : "danger";
          const breakEven =
            p.break_even_price_final ?? p.break_even_price ?? null;
          const tgt =
            p.target_margin_price_final ?? p.target_margin_price ?? null;
          const gap = p.safe_price_gap_final ?? p.safe_price_gap ?? null;
          return (
            <Card className="mt-4">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Tag className="h-4 w-4" /> Безопасный коридор цены
                </CardTitle>
                <CardDescription className="flex flex-wrap items-center gap-2">
                  <ToneBadge tone={calcTone}>Расчёт: {calcState}</ToneBadge>
                  {p.price_source && (
                    <span className="text-xs text-muted-foreground">
                      источник: {p.price_source}
                    </span>
                  )}
                </CardDescription>
              </CardHeader>
              <CardContent className="grid gap-3 md:grid-cols-4">
                <Stat label="Текущая цена">{formatMoney(p.current_price)}</Stat>
                <Stat label="Со скидкой">
                  {formatMoney(p.current_discounted_price)}
                </Stat>
                <Stat label="Break-even">
                  {breakEven != null ? (
                    formatMoney(breakEven)
                  ) : (
                    <NotComputable reason={p.not_computable_reason} />
                  )}
                </Stat>
                <Stat label="Цена целевой маржи">
                  {tgt != null ? (
                    formatMoney(tgt)
                  ) : (
                    <NotComputable reason={p.not_computable_reason} />
                  )}
                </Stat>
                <Stat label="Запас (gap)">
                  {gap != null ? (
                    formatMoney(gap)
                  ) : (
                    <NotComputable reason={p.not_computable_reason} />
                  )}
                </Stat>
                <Stat label="Скидка">{formatPercent(p.discount)}</Stat>
              </CardContent>
              {calcState === "not_computable" && (
                <CardContent className="pt-0">
                  <Alert className="border-warning/40 bg-warning/5">
                    <AlertTitle className="text-warning">
                      Цены безопасности не рассчитаны
                    </AlertTitle>
                    <AlertDescription>
                      {p.not_computable_reason ||
                        "Недостаточно данных по себестоимости/комиссиям."}
                    </AlertDescription>
                  </Alert>
                </CardContent>
              )}
            </Card>
          );
        })()}

      {/* === 6. FUNNEL === */}
      <Card className="mt-4">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Activity className="h-4 w-4" /> Воронка
          </CardTitle>
          <CardDescription>
            Как просмотры превращаются в выкупы.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-3 md:grid-cols-4">
          <Stat label="Просмотры">{formatNumber(f.open_count)}</Stat>
          <Stat label="В корзину, %">
            {formatPercent(f.cart_conversion_percent)}
          </Stat>
          <Stat label="Заказали, %">
            {formatPercent(f.order_conversion_percent)}
          </Stat>
          <Stat label="Выкуп, %">{formatPercent(f.buyout_rate_percent)}</Stat>
          <Stat label="Заказы">{formatNumber(op.orders_count)}</Stat>
          <Stat label="Отмены, %">{formatPercent(op.cancel_rate_percent)}</Stat>
          <Stat label="Продажи">{formatNumber(op.sales_count)}</Stat>
          <Stat label="Возвраты, %">
            {formatPercent(op.return_rate_percent)}
          </Stat>
        </CardContent>
        {(op.cancel_rate_percent > 50 || op.return_rate_percent > 20) && (
          <CardContent className="pt-0 space-y-2">
            {op.cancel_rate_percent > 50 && (
              <Alert variant="destructive">
                <AlertTitle>
                  Высокий процент отмен ({formatPercent(op.cancel_rate_percent)}
                  )
                </AlertTitle>
                <AlertDescription>
                  Проверьте контент, цену, остатки и размерную сетку.
                </AlertDescription>
              </Alert>
            )}
            {op.return_rate_percent > 20 && (
              <Alert className="border-warning/40 bg-warning/5">
                <AlertTitle className="text-warning">
                  Высокий процент возвратов (
                  {formatPercent(op.return_rate_percent)})
                </AlertTitle>
                <AlertDescription>
                  Проверьте качество, описание и размерную сетку.
                </AlertDescription>
              </Alert>
            )}
          </CardContent>
        )}
      </Card>

      {/* === 7. SIZE / SKU breakdown (collapsible) === */}
      {variants.length > 0 && (
        <details className="mt-4 group">
          <summary className="cursor-pointer rounded-md border bg-card px-4 py-3 text-sm font-medium hover:bg-muted/40 flex items-center gap-2">
            <Layers className="h-4 w-4" />
            Размеры и SKU ({variants.length}) — раскрыть
          </summary>
          <Card className="mt-2 rounded-t-none">
            <CardContent className="p-0 overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>SKU / баркод / размер</TableHead>
                    <TableHead className="text-right">Остаток</TableHead>
                    <TableHead className="text-right">Продажи</TableHead>
                    <TableHead className="text-right">Выручка</TableHead>
                    <TableHead className="text-right">Прибыль</TableHead>
                    <TableHead className="text-right">Проблемы</TableHead>
                    <TableHead className="w-10"></TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {variants.map((v: any) => (
                    <TableRow key={v.sku_id ?? v.barcode}>
                      <TableCell>
                        <div className="text-xs font-mono">
                          {v.vendor_code || v.title || `SKU ${v.sku_id ?? "—"}`}
                        </div>
                        <div className="text-[10px] text-muted-foreground font-mono">
                          {v.barcode ?? `SKU ${v.sku_id}`}
                          {v.tech_size ? ` · ${v.tech_size}` : ""}
                        </div>
                      </TableCell>
                      <TableCell className="text-right tabular-nums text-xs">
                        {formatNumber(v.stock_qty)}
                      </TableCell>
                      <TableCell className="text-right tabular-nums text-xs">
                        {formatNumber(v.sales_qty ?? v.net_units ?? null)}
                      </TableCell>
                      <TableCell className="text-right tabular-nums text-xs">
                        {formatMoney(v.revenue)}
                      </TableCell>
                      <TableCell className="text-right tabular-nums text-xs">
                        <span
                          className={
                            v.net_profit_after_source_ads < 0
                              ? "text-destructive"
                              : v.net_profit_after_source_ads > 0
                                ? "text-success"
                                : ""
                          }
                        >
                          {formatMoney(v.net_profit_after_source_ads)}
                        </span>
                      </TableCell>
                      <TableCell className="text-right tabular-nums text-xs">
                        {v.open_issue_count ?? 0}
                      </TableCell>
                      <TableCell className="text-right">
                        {v.sku_id && (
                          <Button
                            asChild
                            variant="ghost"
                            size="sm"
                            className="h-7 w-7 p-0"
                          >
                            <Link
                              to={"/sku/$id" as any}
                              params={{ id: String(v.sku_id) } as any}
                            >
                              <ArrowRight className="h-4 w-4" />
                            </Link>
                          </Button>
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </details>
      )}

      {/* === 8. DATA ISSUES === */}
      {(() => {
        const probs = d.problems ?? [];
        const issues = ((d as any).open_issues ??
          (d as any).dq_issues ??
          []) as any[];
        if (!probs.length && !issues.length) return null;
        return (
          <Card className="mt-4">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <AlertTriangle className="h-4 w-4" /> Проблемы данных
              </CardTitle>
              <CardDescription>
                Финансовый расчёт остаётся предварительным, пока не закрыты.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              {probs.map((p, i) => (
                <div
                  key={`p-${i}`}
                  className={`border-l-4 pl-3 py-1 ${p.severity === "critical" ? "border-l-destructive" : "border-l-warning"}`}
                >
                  <div className="flex items-center gap-2">
                    <ToneBadge
                      tone={p.severity === "critical" ? "danger" : "warning"}
                    >
                      {(
                        {
                          critical: "критично",
                          error: "ошибка",
                          warning: "предупр.",
                          info: "инфо",
                        } as Record<string, string>
                      )[p.severity] ?? p.severity}
                    </ToneBadge>
                    <span className="font-medium text-sm">{p.title}</span>
                  </div>
                  {p.business_impact && (
                    <div className="text-xs text-muted-foreground mt-1">
                      {p.business_impact}
                    </div>
                  )}
                  {p.fix_hint && (
                    <div className="text-xs mt-1">
                      <span className="font-medium">Как починить:</span>{" "}
                      {p.fix_hint}
                    </div>
                  )}
                </div>
              ))}
              {issues.map((it, i) => (
                <div
                  key={`i-${i}`}
                  className="flex items-start justify-between gap-3 border-l-4 pl-3 py-1 border-l-warning"
                >
                  <div>
                    <div className="flex items-center gap-2">
                      <ToneBadge tone="warning">
                        {it.severity ?? it.priority ?? "issue"}
                      </ToneBadge>
                      <span className="font-medium text-sm">
                        {it.title ?? it.code}
                      </span>
                    </div>
                    {it.business_meaning && (
                      <div className="text-xs text-muted-foreground mt-1">
                        {it.business_meaning}
                      </div>
                    )}
                  </div>
                  <Button asChild size="sm" variant="outline">
                    <Link
                      to={"/data-fix" as any}
                      search={{ issue_code: it.code, nm_id: nm } as any}
                    >
                      Исправление данных <ArrowRight className="h-3 w-3 ml-1" />
                    </Link>
                  </Button>
                </div>
              ))}
            </CardContent>
          </Card>
        );
      })()}

      {/* === 9. TOP 3 ACTIONS === */}
      {(d.next_actions?.length ?? 0) > 0 && (
        <Card className="mt-4">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <ListChecks className="h-4 w-4" /> Что сделать с этой карточкой
            </CardTitle>
            <CardDescription>
              Top {Math.min(3, d.next_actions.length)} действий по приоритету и
              эффекту на деньги.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {d.next_actions.slice(0, 3).map((a, i) => (
              <BusinessActionCard key={a.id || i} action={a} />
            ))}
            {d.next_actions.length === 0 && (
              <div className="text-sm text-muted-foreground flex items-center gap-2">
                <TrendingUp className="h-4 w-4" /> Рекомендаций нет — карточка в
                стабильном состоянии.
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* Technical response (collapsed) */}
      {import.meta.env.DEV && (
        <details className="mt-4">
          <summary className="cursor-pointer text-xs text-muted-foreground inline-flex items-center gap-1">
            <Code2 className="h-3 w-3" /> Технический ответ API (для разработки)
          </summary>
          <pre className="text-[11px] font-mono bg-muted/30 p-3 rounded-md overflow-auto max-h-[500px] whitespace-pre-wrap break-all mt-2">
            {JSON.stringify(d, null, 2)}
          </pre>
        </details>
      )}

      {/* eslint-disable-next-line @typescript-eslint/no-unused-vars */}
      {false && humanizeAction("noop")}
    </>
  );
}

function Stat({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-0.5">
      <div className="text-[10px] uppercase tracking-wider text-muted-foreground">
        {label}
      </div>
      <div className="text-sm font-medium tabular-nums">{children}</div>
    </div>
  );
}

function NotComputable({ reason }: { reason?: string | null }) {
  return (
    <span className="text-muted-foreground text-xs">
      Не рассчитано{reason ? ` · ${reason}` : ""}
    </span>
  );
}
