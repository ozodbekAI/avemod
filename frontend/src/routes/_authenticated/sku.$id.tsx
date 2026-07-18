import { createFileRoute, Link, useParams } from "@tanstack/react-router";
import { normalizeTrust } from "@/lib/trust";
import { useQuery } from "@tanstack/react-query";
import { api, type MCardDetail, type CoreSKUDetail } from "@/lib/api";
import { useAccounts } from "@/lib/account-context";
import { PageShell, PageHeader } from "@/components/PageShell";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { AnswerCard } from "@/components/money/AnswerCard";
import { ConfidenceBadge } from "@/components/money/ConfidenceBadge";
import { NotComputableValue } from "@/components/money/NotComputableValue";
import { BusinessActionCard } from "@/components/money/BusinessActionCard";
import { BusinessVerdictBadge } from "@/components/money/BusinessVerdictBadge";
import { formatMoney, formatPercent, formatNumber } from "@/lib/format";
import { ADS_STATUS_COPY, COST_TRUTH_COPY, PRICE_STATUS_COPY, STOCK_STATUS_COPY, humanizeBlockedReason, humanizeBusinessStatus, humanizeDqCode } from "@/lib/copy";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { ArrowLeft, AlertTriangle, TrendingUp, Wallet, Boxes, Tag, Activity, Eye, ShoppingCart, FileWarning } from "lucide-react";
import { EndpointError } from "@/components/EndpointError";
import { API_ENDPOINTS, buildBizQuery } from "@/lib/endpoints";
import { useDateRange } from "@/lib/date-range-context";
import { DataDependencyNotice } from "@/components/data-health/DataCoveragePanel";

export const Route = createFileRoute("/_authenticated/sku/$id")({ component: SkuDetailPage, errorComponent: ({ error, reset }) => <EndpointError error={error} reset={reset} /> });

function SkuDetailPage() {
  const { id } = useParams({ from: "/_authenticated/sku/$id" });
  const { activeId } = useAccounts();
  const skuId = Number(id);
  const { from: dateFrom, to: dateTo } = useDateRange();

  // Primary: GET /api/v1/money/cards/{sku_id}
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["money-card-detail", activeId, skuId, dateFrom, dateTo],
    enabled: !!activeId && Number.isFinite(skuId),
    queryFn: () => api<MCardDetail>(API_ENDPOINTS.money.cardDetail(skuId), {
      query: buildBizQuery({ accountId: activeId, dateFrom, dateTo }),
    }),
  });

  // Supporting: GET /api/v1/core-sku/{sku_id}
  const { data: coreSku } = useQuery({
    queryKey: ["core-sku-detail", skuId, dateFrom, dateTo],
    enabled: Number.isFinite(skuId),
    queryFn: () => api<CoreSKUDetail>(API_ENDPOINTS.catalog.coreSkuDetail(skuId), {
      query: { date_from: dateFrom, date_to: dateTo },
    }),
    retry: false,
  });

  // Purchase plan slice for this SKU
  const { data: planRaw } = useQuery({
    queryKey: ["purchase-plan-for-sku", activeId, skuId, dateFrom, dateTo],
    enabled: !!activeId && Number.isFinite(skuId),
    queryFn: () => api<any>(API_ENDPOINTS.inventory.purchasePlan, {
      query: buildBizQuery({ accountId: activeId, dateFrom, dateTo }),
    }),
    retry: false,
  });

  const planItem = (() => {
    if (!planRaw) return null;
    const list: any[] = Array.isArray(planRaw) ? planRaw : (planRaw.items ?? planRaw.rows ?? planRaw.plan ?? []);
    const nmId = data?.identity?.nm_id;
    return list.find((it) => it.sku_id === skuId)
      || (nmId ? list.find((it) => it.nm_id === nmId) : null)
      || null;
  })();

  const _trust = normalizeTrust(data);
  const trustStateStr = _trust.trustState ?? "";
  const financialFinal = _trust.financialFinal;

  return (
    <PageShell>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <Button asChild variant="ghost" size="sm"><Link to="/products"><ArrowLeft className="h-4 w-4 mr-1" /> Все товары</Link></Button>
        {data?.identity?.nm_id ? (
          <Button asChild variant="default" size="sm">
            <Link to={"/products/$nmId" as any} params={{ nmId: String(data.identity.nm_id) } as any}>
              Открыть товар (nm_id {data.identity.nm_id})
            </Link>
          </Button>
        ) : null}
        {data && (
          <Badge
            variant="outline"
            className={`ml-auto ${financialFinal
              ? "bg-success/10 text-success border-success/30"
              : "bg-warning/10 text-warning border-warning/30"}`}
            title={financialFinal
              ? "Данные финально подтверждены финансовым отчётом"
              : "Operational provisional — финальный отчёт ещё не подтверждён"}
          >
            {financialFinal ? "Financial final" : "Не финально · operational provisional"}
          </Badge>
        )}
      </div>

      {activeId && <DataDependencyNotice accountId={activeId} domains={["product_cards", "prices", "sales", "stocks", "finance"]} />}

      {data && (
        <Alert className="mb-3">
          <AlertTitle>Это уровень размера / SKU</AlertTitle>
          <AlertDescription>
            Бизнес-решение принимается на уровне артикула. Откройте{" "}
            <Link className="underline" to={"/products/$nmId" as any} params={{ nmId: String(data.identity.nm_id) } as any}>товар nm_id {data.identity.nm_id}</Link>
            {" "}для полной картины. Здесь — расследование по конкретному баркоду/размеру.
          </AlertDescription>
        </Alert>
      )}

      {isLoading && <div className="grid gap-3">{[1,2,3,4].map(i => <Skeleton key={i} className="h-32" />)}</div>}
      {isError && (
        <Alert variant="destructive">
          <AlertTitle>Не удалось загрузить SKU</AlertTitle>
          <AlertDescription>
            <div className="mb-2">{(error as Error)?.message || "Сервер вернул ошибку. Попробуйте обновить страницу или открыть карточку артикула."}</div>
            <div className="font-mono text-[11px] opacity-70">GET /money/cards/{skuId}</div>
          </AlertDescription>
        </Alert>
      )}

      {data && <DetailBody d={data} coreSku={coreSku ?? null} planItem={planItem} />}
    </PageShell>
  );
}


function DetailBody({ d, coreSku, planItem }: { d: MCardDetail; coreSku: CoreSKUDetail | null; planItem: any }) {
  const trustState = d.meta.data_trust.state;
  const m = d.money;
  const op = d.operations;
  const f = d.funnel;
  const st = d.stock;
  const p = d.price;
  const cogsTruth = m.cogs.truth_level || (m.cogs.supplier_confirmed ? "supplier_confirmed" : "");
  const wbExpenses = m.wb_expenses;
  const accountLevelLogistics = wbExpenses?.account_level_logistics ?? wbExpenses?.unallocated_logistics ?? 0;
  const directLogistics = (wbExpenses?.wb_logistics ?? 0) + (wbExpenses?.wb_logistics_rebill ?? 0) + (wbExpenses?.logistics ?? 0);
  const logisticsNotLinked =
    accountLevelLogistics > 0 &&
    (directLogistics <= 0 ||
      wbExpenses?.logistics_mapping_status === "not_linked_to_sku" ||
      wbExpenses?.logistics_mapping_status === "partial_account_level" ||
      wbExpenses?.reason === "wb_logistics_not_linked_to_sku" ||
      wbExpenses?.reason === "wb_logistics_partially_linked_to_sku" ||
      wbExpenses?.status === "account_level_logistics_not_allocated" ||
      wbExpenses?.status === "account_level_logistics_partially_allocated");

  const cancelHigh = op.cancel_rate_percent > 30;
  const returnHigh = op.return_rate_percent > 15;

  const techSize = coreSku?.sku?.tech_size ?? null;
  const recentIssues = coreSku?.recent_issue_codes ?? [];

  return (
    <>
      <PageHeader
        title={d.identity.title || d.identity.vendor_code}
        description={
          <span className="font-mono text-xs">
            SKU {d.identity.sku_id} · {d.identity.vendor_code} · баркод {d.identity.barcode || "—"}
            {techSize ? <> · размер <b>{techSize}</b></> : null}
            {" "}· nm {d.identity.nm_id} · {d.identity.brand} · {d.identity.subject_name}
          </span>
        }
      />


      <AnswerCard
        trustState={trustState}
        title={d.answer.title}
        shortText={d.answer.short_text}
        mainProblem={d.meta.data_trust.human_message}
        mainNextStep={d.answer.main_next_step}
      />

      {/* Money breakdown */}
      <Card className="mt-4">
        <CardHeader>
          <CardTitle className="flex items-center gap-2"><Wallet className="h-4 w-4" /> Распределение денег</CardTitle>
          <CardDescription>
            <BusinessVerdictBadge status={d.answer.status} />
            <ConfidenceBadge value={m.profit.confidence} className="ml-2" />
            {!m.cogs.supplier_confirmed && (
              <span className="ml-2 text-xs text-warning">Предварительно — себестоимость не подтверждена</span>
            )}
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-3 md:grid-cols-4">
          <Stat label="Выручка"><NotComputableValue value={m.revenue} format="money" reason={m.revenue === 0 ? "finance_not_confirmed" : null} /></Stat>
          <Stat label="К выплате"><NotComputableValue value={m.for_pay} format="money" reason={m.for_pay === 0 ? "finance_not_confirmed" : null} /></Stat>
          <Stat label="WB удержания"><NotComputableValue value={m.wb_expenses_total} format="money" reason={m.wb_expenses_total === 0 ? "finance_not_confirmed" : null} /></Stat>
          <Stat label="Реклама">
            <NotComputableValue value={m.ads.spend} format="money" reason={m.ads.spend === 0 && m.ads.status !== "no_ads" ? "ads_not_allocated" : null} />
            <div className="text-[10px] text-muted-foreground">{ADS_STATUS_COPY[m.ads.status] ?? m.ads.status}</div>
          </Stat>
          <Stat label="Себестоимость (COGS)">
            <NotComputableValue value={m.cogs.estimated_cogs} format="money" reason={m.cogs.estimated_cogs === 0 ? "cost_not_confirmed" : null} />
            <Badge variant="outline" className={`mt-1 text-[10px] ${
              COST_TRUTH_COPY[cogsTruth]?.tone === "success" ? "border-success/30 text-success bg-success/10" :
              COST_TRUTH_COPY[cogsTruth]?.tone === "warning" ? "border-warning/30 text-warning bg-warning/10" :
                                                                "border-destructive/30 text-destructive bg-destructive/10"
            }`}>{COST_TRUTH_COPY[cogsTruth]?.label ?? "Нет данных"}</Badge>
          </Stat>
          <Stat label="Прибыль до рекламы"><NotComputableValue value={m.profit.before_ads} format="money" reason={m.profit.before_ads === 0 ? "finance_not_confirmed" : null} /></Stat>
          <Stat label="Прибыль после рекламы">
            <span className={m.profit.after_ads < 0 ? "text-destructive font-semibold" : m.profit.after_ads > 0 ? "text-success font-semibold" : ""}>
              <NotComputableValue value={m.profit.after_ads} format="money" reason={m.profit.after_ads === 0 ? "finance_not_confirmed" : null} />
            </span>
          </Stat>
          <Stat label="Маржа">{formatPercent(m.profit.margin_after_ads_percent)}</Stat>
          <Stat label="Окупаемость (ROI)">{formatPercent(m.profit.roi_after_ads_percent)}</Stat>
          <Stat label="Стоимость остатка">
            <NotComputableValue value={m.stock_value} format="money" reason={m.stock_value === 0 && st.quantity > 0 ? (st.stock_value_reason || "stock_value_not_computable") : null} />
          </Stat>
        </CardContent>
        {logisticsNotLinked && (
          <CardContent className="pt-0">
            <Alert className="border-warning/40 bg-warning/5">
              <AlertTriangle className="h-4 w-4 text-warning" />
              <AlertTitle>Логистика WB не привязана к этому SKU</AlertTitle>
              <AlertDescription>
                В финансовом отчете есть логистика {formatMoney(accountLevelLogistics)}, но по этому SKU нет прямой привязки SKU/баркода.
                Прибыль по SKU предварительная, пока логистика не распределена.
              </AlertDescription>
            </Alert>
          </CardContent>
        )}
        {m.wb_expenses_total === 0 && m.revenue > 0 && (
          <CardContent className="pt-0">
            <Alert variant="destructive"><AlertTriangle className="h-4 w-4" />
              <AlertTitle>WB удержания = 0, но есть продажи</AlertTitle>
              <AlertDescription>Проверьте распределение финансового отчёта.</AlertDescription>
            </Alert>
          </CardContent>
        )}
      </Card>

      {/* Operations */}
      <Card className="mt-4">
        <CardHeader><CardTitle className="flex items-center gap-2"><Activity className="h-4 w-4" /> Операции</CardTitle></CardHeader>
        <CardContent className="grid gap-3 md:grid-cols-4">
          <Stat label="Заказы">{formatNumber(op.orders_count)}</Stat>
          <Stat label="Отмены">{formatNumber(op.cancelled_orders_count)} ({formatPercent(op.cancel_rate_percent)})</Stat>
          <Stat label="Продажи">{formatNumber(op.sales_count)}</Stat>
          <Stat label="Возвраты">{formatNumber(op.returns_count)} ({formatPercent(op.return_rate_percent)})</Stat>
          <Stat label="Чистые единицы">{formatNumber(op.net_units)}</Stat>
        </CardContent>
        {(cancelHigh || returnHigh) && (
          <CardContent className="pt-0 space-y-2">
            {cancelHigh && (
              <Alert variant="destructive"><AlertTitle>Высокая доля отмен ({formatPercent(op.cancel_rate_percent)})</AlertTitle>
                <AlertDescription>Проверьте цену, остаток, склад, размерную сетку и описание.</AlertDescription></Alert>
            )}
            {returnHigh && (
              <Alert><AlertTitle>Высокая доля возвратов ({formatPercent(op.return_rate_percent)})</AlertTitle>
                <AlertDescription>Качество, размеры или несоответствие ожиданиям.</AlertDescription></Alert>
            )}
          </CardContent>
        )}
      </Card>

      {/* Funnel */}
      <Card className="mt-4">
        <CardHeader><CardTitle className="flex items-center gap-2"><Eye className="h-4 w-4" /> Воронка</CardTitle></CardHeader>
        <CardContent>
          <div className="grid grid-cols-4 gap-3 text-center">
            <FunnelStep label="Просмотры" value={f.open_count} />
            <FunnelStep label="В корзине" value={f.cart_count} pct={f.cart_conversion_percent} />
            <FunnelStep label="Заказали" value={f.order_count} pct={f.order_conversion_percent} />
            <FunnelStep label="Выкупили" value={f.buyout_count} pct={f.buyout_rate_percent} />
          </div>
          {f.issue && <div className="mt-3 text-xs text-muted-foreground">{f.issue}</div>}
        </CardContent>
      </Card>

      {/* Stock */}
      <Card className="mt-4">
        <CardHeader><CardTitle className="flex items-center gap-2"><Boxes className="h-4 w-4" /> Остаток</CardTitle></CardHeader>
        <CardContent className="grid gap-3 md:grid-cols-4">
          <Stat label="Количество">{formatNumber(st.quantity)}</Stat>
          <Stat label="Полный">{formatNumber(st.quantity_full)}</Stat>
          <Stat label="В пути к клиенту">{formatNumber(st.in_transit_qty)}</Stat>
          <Stat label="Дней остатка">{st.days_of_stock > 0 ? st.days_of_stock.toFixed(0) : "—"}</Stat>
          <Stat label="Статус">
            <Badge variant="outline">{STOCK_STATUS_COPY[st.stock_status]?.label ?? st.stock_status}</Badge>
          </Stat>
          <Stat label="Стоимость остатка">
            <NotComputableValue value={st.stock_value} format="money" reason={st.stock_value === 0 && st.quantity > 0 ? (st.stock_value_reason || "stock_value_not_computable") : null} />
            <ConfidenceBadge value={st.stock_value_confidence} className="ml-1" />
          </Stat>
        </CardContent>
        {st.quantity > 0 && st.stock_value === 0 && (
          <CardContent className="pt-0">
            <Alert><AlertTitle>Есть остаток, но стоимость не посчитана</AlertTitle>
              <AlertDescription>{humanizeBlockedReason(st.stock_value_reason || "stock_value_not_computable")}</AlertDescription></Alert>
          </CardContent>
        )}
      </Card>

      {/* Price */}
      <Card className="mt-4">
        <CardHeader>
          <CardTitle className="flex items-center gap-2"><Tag className="h-4 w-4" /> Цена и безопасность</CardTitle>
          <CardDescription>
            <Badge variant="outline">{PRICE_STATUS_COPY[p.status]?.label ?? p.status}</Badge>
            <ConfidenceBadge value={p.confidence} className="ml-2" />
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-3 md:grid-cols-4">
          <Stat label="Цена">{formatMoney(p.current_price)}</Stat>
          <Stat label="Со скидкой">{formatMoney(p.current_discounted_price)}</Stat>
          <Stat label="Скидка">{p.discount}%</Stat>
          <Stat label="Точка безубыточности">
            <NotComputableValue value={p.break_even_price} format="money" reason={p.break_even_price === 0 ? (p.not_computable_reason || "cost_not_confirmed") : null} />
          </Stat>
          <Stat label="Цена целевой маржи">
            <NotComputableValue value={p.target_margin_price} format="money" reason={p.target_margin_price === 0 ? (p.not_computable_reason || "cost_not_confirmed") : null} />
          </Stat>
          <Stat label="Безопасный запас">
            <NotComputableValue value={p.safe_price_gap} format="money" reason={p.safe_price_gap === 0 ? p.not_computable_reason : null} />
          </Stat>
        </CardContent>
        {p.not_computable_reason && (
          <CardContent className="pt-0">
            <Alert><AlertTitle>Цена не считается окончательно</AlertTitle>
              <AlertDescription>{humanizeBlockedReason(p.not_computable_reason)}</AlertDescription></Alert>
          </CardContent>
        )}
      </Card>

      {/* Reconciliation */}
      {d.reconciliation && (
        <Card className="mt-4">
          <CardHeader>
            <CardTitle>Сверка с источниками</CardTitle>
            <CardDescription>Совпадают ли mart, finance и операционные данные.</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-3 md:grid-cols-3">
            <Stat label="Витрина (mart)"><span className="tabular-nums">{formatMoney(d.reconciliation.mart_revenue_total)}</span></Stat>
            <Stat label="По карточке"><span className="tabular-nums">{formatMoney(d.reconciliation.article_revenue_total)}</span></Stat>
            <Stat label="Финотчёт WB"><span className="tabular-nums">{formatMoney(d.reconciliation.finance_report_revenue_total)}</span></Stat>
            <Stat label="Разница"><span className="tabular-nums text-destructive">{formatMoney(d.reconciliation.difference_amount)}</span></Stat>
            <Stat label="Разница, %">{formatPercent(d.reconciliation.difference_ratio_percent)}</Stat>
            <Stat label="Статус сверки"><Badge variant="outline" className="bg-destructive/10 text-destructive border-destructive/30">{humanizeBusinessStatus(d.reconciliation.status).label}</Badge></Stat>
          </CardContent>
          {d.reconciliation.root_cause_candidates?.length > 0 && (
            <CardContent className="pt-0">
              <div className="text-[10px] uppercase text-muted-foreground mb-1">Возможные причины</div>
              <ul className="text-xs list-disc list-inside space-y-1">
                {d.reconciliation.root_cause_candidates.map((s, i) => <li key={i}>{s}</li>)}
              </ul>
            </CardContent>
          )}
        </Card>
      )}

      {/* Purchase plan */}
      <Card className="mt-4">
        <CardHeader>
          <CardTitle className="flex items-center gap-2"><ShoppingCart className="h-4 w-4" /> План закупок</CardTitle>
          <CardDescription>Источник: <code>GET /inventory/purchase-plan</code></CardDescription>
        </CardHeader>
        <CardContent className="grid gap-3 md:grid-cols-4">
          {planItem ? (
            <>
              <Stat label="Статус"><Badge variant="outline">{planItem.status ?? planItem.bucket ?? "—"}</Badge></Stat>
              <Stat label="Рекомендуем заказать">{planItem.recommended_qty != null ? formatNumber(planItem.recommended_qty) : "—"}</Stat>
              <Stat label="Нужно денег">{planItem.required_cash != null ? formatMoney(planItem.required_cash) : "—"}</Stat>
              <Stat label="Ожидаемая прибыль">{planItem.expected_profit != null ? formatMoney(planItem.expected_profit) : "—"}</Stat>
              <Stat label="Риск"><Badge variant="outline">{planItem.risk ?? planItem.risk_level ?? "—"}</Badge></Stat>
              <Stat label="Причина"><span className="text-xs">{planItem.reason ?? planItem.why ?? "—"}</span></Stat>
            </>
          ) : (
            <div className="col-span-full text-sm text-muted-foreground space-y-2">
              <div>За выбранный период по этому SKU нет рекомендации на закупку.</div>
              <div className="text-xs">Это может означать одно из:</div>
              <ul className="text-xs list-disc list-inside space-y-0.5 ml-2">
                <li>остатков пока достаточно — закупать не нужно;</li>
                <li>по карточке мало продаж — модель не уверена в прогнозе;</li>
                <li>не подтверждена себестоимость или цена — расчёт заблокирован.</li>
              </ul>
              <div className="text-xs">Попробуйте расширить период сверху или проверить себестоимость и цену.</div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Data issues (recent codes from core-sku) */}
      {recentIssues.length > 0 && (() => {
        const counts = recentIssues.reduce<Record<string, number>>((acc, c) => { acc[c] = (acc[c] ?? 0) + 1; return acc; }, {});
        const unique = Object.entries(counts).sort((a, b) => b[1] - a[1]);
        return (
        <Card className="mt-4">
          <CardHeader>
            <CardTitle className="flex items-center gap-2"><FileWarning className="h-4 w-4" /> Проблемы качества данных</CardTitle>
            <CardDescription>Что мы заметили в данных по этому SKU за последний период. Наведите на карточку — увидите подробности и как это влияет на цифры.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-2">
            <TooltipProvider>
              {unique.map(([code, count]) => {
                const info = humanizeDqCode(code);
                return (
                  <Tooltip key={code}>
                    <TooltipTrigger asChild>
                      <div className="flex items-start justify-between gap-3 p-3 rounded-md border bg-warning/5 border-warning/30 cursor-help">
                        <div className="flex-1 min-w-0">
                          <div className="text-sm font-medium">{info.title}</div>
                          <div className="text-xs text-muted-foreground mt-0.5">{info.description}</div>
                        </div>
                        {count > 1 && (
                          <Badge variant="outline" className="text-xs shrink-0">Повторений: {count}</Badge>
                        )}
                      </div>
                    </TooltipTrigger>
                    <TooltipContent className="max-w-xs text-xs">
                      <div className="font-medium mb-1">Технический код: <code>{code}</code></div>
                      <div>{info.description}</div>
                    </TooltipContent>
                  </Tooltip>
                );
              })}
            </TooltipProvider>
          </CardContent>
        </Card>
        );
      })()}


      {/* Problems */}
      {d.problems?.length > 0 && (
        <Card className="mt-4">
          <CardHeader><CardTitle className="flex items-center gap-2"><AlertTriangle className="h-4 w-4" /> Проблемы</CardTitle></CardHeader>
          <CardContent className="space-y-3">
            {d.problems.map((p, i) => (
              <div key={i} className={`border-l-4 pl-3 py-1 ${p.severity === "critical" ? "border-l-destructive" : "border-l-warning"}`}>
                <div className="flex items-center gap-2">
                  <Badge variant="outline" className={p.severity === "critical" ? "text-[10px] bg-destructive/10 text-destructive border-destructive/30 uppercase" : "text-[10px] bg-warning/10 text-warning border-warning/30 uppercase"}>{({critical:"критично",error:"ошибка",warning:"предупр.",info:"инфо"} as Record<string,string>)[p.severity] ?? p.severity}</Badge>
                  <span className="font-medium text-sm">{p.title}</span>
                </div>
                {p.business_impact && <div className="text-xs text-muted-foreground mt-1">{p.business_impact}</div>}
                {p.fix_hint && <div className="text-xs mt-1"><span className="font-medium">Как починить:</span> {p.fix_hint}</div>}
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      {/* Next actions */}
      {d.next_actions?.length > 0 && (
        <Card className="mt-4">
          <CardHeader><CardTitle className="flex items-center gap-2"><TrendingUp className="h-4 w-4" /> Следующие шаги</CardTitle></CardHeader>
          <CardContent className="space-y-3">
            {d.next_actions.map((a, i) => <BusinessActionCard key={a.id || i} action={a} />)}
          </CardContent>
        </Card>
      )}
    </>
  );
}

function Stat({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-0.5">
      <div className="text-[10px] uppercase tracking-wider text-muted-foreground">{label}</div>
      <div className="text-sm font-medium tabular-nums">{children}</div>
    </div>
  );
}

function FunnelStep({ label, value, pct }: { label: string; value: number; pct?: number }) {
  return (
    <div>
      <div className="text-[10px] uppercase text-muted-foreground">{label}</div>
      <div className="text-lg font-semibold tabular-nums">{formatNumber(value)}</div>
      {pct != null && <div className="text-[10px] text-muted-foreground">{formatPercent(pct)}</div>}
      <Progress value={pct != null ? Math.min(100, pct) : 100} className="mt-1" />
    </div>
  );
}
