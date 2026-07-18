// «Экономика товаров» на /money. Агрегированная юнит-экономика за период.
// Никаких выдуманных значений — если бэкенд не дал цифру, показываем «—».
// Если нет вообще ни выручки, ни расходов — показываем EmptyState.
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { AlertTriangle } from "lucide-react";
import { formatMoney } from "@/lib/format";
import { EmptyState } from "@/components/shell/EmptyState";
import { Button } from "@/components/ui/button";

export interface UnitEconomicsCardProps {
  revenue: number | null | undefined;
  cogs: number | null | undefined;
  sellerOther?: number | null | undefined;
  wbExpenses: number | null | undefined;
  adSpend: number | null | undefined;
  unallocated: number | null | undefined;
  netProfit: number | null | undefined;
  marginPercent: number | null | undefined;
  costPriceCoverage: number | null | undefined; // % SKU с подтверждённой себестоимостью
  ordersCount?: number | null | undefined;
}

function fmt(v: number | null | undefined): string {
  return v == null ? "—" : formatMoney(v);
}

function perOrder(total: number | null | undefined, orders: number | null | undefined): number | null {
  if (total == null || orders == null || !orders) return null;
  return total / orders;
}

export function UnitEconomicsCard(p: UnitEconomicsCardProps) {
  const orders = p.ordersCount ?? null;
  const rows: Array<{ label: string; total: number | null | undefined; sign: "+" | "-"; note?: string }> = [
    { label: "Выручка", total: p.revenue, sign: "+" },
    { label: "Себестоимость", total: p.cogs, sign: "-", note: p.costPriceCoverage != null && p.costPriceCoverage < 100 ? `покрытие себестоимости: ${p.costPriceCoverage.toFixed(0)}%` : undefined },
    { label: "Прочие расходы продавца", total: p.sellerOther, sign: "-" },
    { label: "Комиссии и логистика WB без нераспределённых", total: p.wbExpenses, sign: "-" },
    { label: "Реклама", total: p.adSpend, sign: "-" },
    { label: "Нераспределённые расходы", total: p.unallocated, sign: "-" },
  ];

  const costPriceUnsafe = p.costPriceCoverage != null && p.costPriceCoverage < 80;
  const costMissing = p.costPriceCoverage == null || (p.cogs == null && p.costPriceCoverage < 20);
  const noData =
    p.revenue == null && p.cogs == null && p.sellerOther == null && p.wbExpenses == null &&
    p.adSpend == null && p.netProfit == null;

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-base flex items-center gap-2">
          Экономика товаров
          {orders != null ? <Badge variant="outline" className="text-[10px]">заказов: {orders}</Badge> : null}
          <Badge variant="outline" className="text-[10px]">Оценка</Badge>
        </CardTitle>
        <div className="text-xs text-muted-foreground">
          Что остаётся с одной продажи после WB-комиссий, себестоимости и рекламы.
          Это не финальная прибыль — она уточняется после закрытия финансового отчёта.
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {noData ? (
          <EmptyState
            variant="no_data"
            title="Нет данных по экономике товаров"
            hint="Платформа покажет маржу и прибыль после загрузки себестоимости и финансовых данных."
          />
        ) : (<>
        {costMissing ? (
          <div className="flex items-start justify-between gap-2 rounded-md border border-warning/30 bg-warning/5 p-2 text-xs">
            <div className="flex items-start gap-2">
              <AlertTriangle className="h-4 w-4 text-warning shrink-0 mt-0.5" />
              <div>
                <div className="font-medium">Не хватает себестоимости</div>
                <div className="text-muted-foreground">
                  Пока себестоимость не загружена, «товар в минус» не показываем — это была бы фейковая цифра.
                </div>
              </div>
            </div>
            <Button asChild size="sm" variant="outline">
              <a href="/data-fix?tab=cost">Загрузить себестоимость</a>
            </Button>
          </div>
        ) : null}
        {costPriceUnsafe ? (
          <div className="flex items-start gap-2 rounded-md border border-destructive/30 bg-destructive/5 p-2 text-xs">
            <AlertTriangle className="h-4 w-4 text-destructive shrink-0 mt-0.5" />
            <div>
              <div className="font-medium text-destructive">Себестоимость подтверждена не для всех SKU</div>
              <div className="text-muted-foreground">
                Пока покрытие себестоимости ниже 80% ({p.costPriceCoverage!.toFixed(0)}%),
                маржа и прибыль остаются оценкой. Не используйте эти числа для решений о цене.
              </div>
            </div>
          </div>
        ) : null}
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-[11px] uppercase text-muted-foreground">
              <tr>
                <th className="text-left font-medium py-1">Статья</th>
                <th className="text-right font-medium py-1">За период</th>
                <th className="text-right font-medium py-1">На заказ</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.label} className="border-t border-border/40">
                  <td className="py-1.5">
                    <div>{r.label}</div>
                    {r.note ? <div className="text-[10px] text-muted-foreground">{r.note}</div> : null}
                  </td>
                  <td className="py-1.5 text-right tabular-nums">
                    {r.total == null ? "—" : `${r.sign === "-" ? "−" : ""}${fmt(r.total)}`}
                  </td>
                  <td className="py-1.5 text-right tabular-nums text-muted-foreground">
                    {(() => { const v = perOrder(r.total, orders); return v == null ? "—" : `${r.sign === "-" ? "−" : ""}${formatMoney(v)}`; })()}
                  </td>
                </tr>
              ))}
              <tr className="border-t border-border/60 font-semibold">
                <td className="py-1.5">Чистый результат</td>
                <td className="py-1.5 text-right tabular-nums">{fmt(p.netProfit)}</td>
                <td className="py-1.5 text-right tabular-nums">
                  {(() => { const v = perOrder(p.netProfit, orders); return v == null ? "—" : formatMoney(v); })()}
                </td>
              </tr>
              <tr>
                <td className="py-1.5 text-muted-foreground text-xs">Маржа</td>
                <td className="py-1.5 text-right tabular-nums text-xs" colSpan={2}>
                  {p.marginPercent == null ? "—" : `${p.marginPercent.toFixed(1)}%`}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <div className="text-[11px] text-muted-foreground">
          Значения — оценка на текущих данных. Ноль показывается только если бэкенд вернул ноль.
          Пустая ячейка означает, что источник ещё не подтвердил цифру.
        </div>
        </>)}
      </CardContent>
    </Card>
  );
}
