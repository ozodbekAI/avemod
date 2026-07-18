import { createFileRoute } from "@tanstack/react-router";
import { PageHeader, PageShell } from "@/components/PageShell";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { DataBrowser, type Column } from "@/components/DataBrowser";
import { fmtDate, fmtMoney, fmtNum } from "@/components/Pager";
import { Badge } from "@/components/ui/badge";
import type { Row } from "@/lib/api";
import { EndpointError } from "@/components/EndpointError";

export const Route = createFileRoute("/_authenticated/marts")({ component: MartsPage, errorComponent: ({ error, reset }) => <EndpointError error={error} reset={reset} /> });

const skuDailyCols: Column<Row>[] = [
  { header: "Дата", sortKey: "date", cell: (r) => <span className="text-xs">{fmtDate(r.date as string)}</span> },
  { header: "Артикул", sortKey: "nm_id", cell: (r) => <span className="font-mono text-xs">{(r.nm_id as number) ?? "—"}</span> },
  { header: "Артикул", sortKey: "vendor_code", cell: (r) => <span className="text-xs">{(r.vendor_code as string) ?? "—"}</span> },
  { header: "Бренд", sortKey: "brand", cell: (r) => <span className="text-xs">{(r.brand as string) ?? "—"}</span> },
  { header: "Шт", sortKey: "units_sold", align: "right", cell: (r) => fmtNum(r.units_sold as number ?? r.gross_units as number) },
  { header: "Выручка", sortKey: "revenue", align: "right", cell: (r) => fmtMoney(r.revenue as number ?? r.realized_revenue as number) },
  { header: "Прибыль", sortKey: "profit", align: "right", cell: (r) => fmtMoney(r.profit as number ?? r.net_profit as number) },
];

const stockDailyCols: Column<Row>[] = [
  { header: "Дата", sortKey: "date", cell: (r) => <span className="text-xs">{fmtDate(r.date as string)}</span> },
  { header: "Артикул", sortKey: "nm_id", cell: (r) => <span className="font-mono text-xs">{(r.nm_id as number) ?? "—"}</span> },
  { header: "Штрихкод", sortKey: "barcode", cell: (r) => <span className="text-xs">{(r.barcode as string) ?? "—"}</span> },
  { header: "Склад", sortKey: "warehouse_name", cell: (r) => <span className="text-xs">{(r.warehouse_name as string) ?? "—"}</span> },
  { header: "Остаток", sortKey: "quantity", align: "right", cell: (r) => fmtNum(r.quantity as number) },
  { header: "Полн.", sortKey: "quantity_full", align: "right", cell: (r) => fmtNum(r.quantity_full as number) },
];

const expenseCols: Column<Row>[] = [
  { header: "Дата", sortKey: "date", cell: (r) => <span className="text-xs">{fmtDate(r.date as string)}</span> },
  { header: "Аккаунт", sortKey: "account_id", cell: (r) => <span className="text-xs">{(r.account_id as number)}</span> },
  { header: "Категория", sortKey: "category", cell: (r) => <span className="text-xs">{(r.category as string) ?? (r.expense_type as string) ?? "—"}</span> },
  { header: "Сумма", sortKey: "amount", align: "right", cell: (r) => fmtMoney(r.amount as number ?? r.expense as number) },
];

const finReconcCols: Column<Row>[] = [
  { header: "ID операции", sortKey: "srid", cell: (r) => <span className="font-mono text-xs truncate max-w-[140px] block">{(r.srid as string) ?? "—"}</span> },
  { header: "Артикул", sortKey: "nm_id", cell: (r) => <span className="font-mono text-xs">{(r.nm_id as number) ?? "—"}</span> },
  { header: "Дата", sortKey: "stat_date", cell: (r) => <span className="text-xs">{fmtDate(r.stat_date as string)}</span> },
  { header: "Статус", sortKey: "status", cell: (r) => <Badge variant="outline">{(r.status as string) ?? "—"}</Badge> },
  { header: "Продажи", sortKey: "sale_revenue", align: "right", cell: (r) => fmtMoney((r.sale_revenue as number) ?? (r.order_revenue as number)) },
  { header: "Финансы", sortKey: "finance_revenue", align: "right", cell: (r) => fmtMoney(r.finance_revenue as number) },
  { header: "Разница", sortKey: "revenue_delta", align: "right", cell: (r) => fmtMoney(r.revenue_delta as number) },
];

function MartsPage() {
  return (
    <PageShell>
      <PageHeader title="Витрины" description="Агрегированные данные по SKU, остаткам, расходам и сверке" />
      <Tabs defaultValue="sku">
        <TabsList className="flex-wrap h-auto">
          <TabsTrigger value="sku">SKU по дням</TabsTrigger>
          <TabsTrigger value="stock">Остатки по дням</TabsTrigger>
          <TabsTrigger value="expense">Расходы по аккаунту</TabsTrigger>
          <TabsTrigger value="fin-reconc">Сверка по финансам</TabsTrigger>
        </TabsList>
        <TabsContent value="sku">
          <DataBrowser
            path="/marts/sku-daily" columns={skuDailyCols} withDateRange withNmId withSearch
            extraFilters={[
              { key: "sku_id", label: "sku_id", type: "number" },
              { key: "vendor_code", label: "Артикул", type: "text" },
              { key: "barcode", label: "Штрихкод", type: "text" },
              { key: "brand", label: "Бренд", type: "text" },
              { key: "subject_name", label: "Категория", type: "text" },
              { key: "has_manual_cost", label: "С себест.", type: "bool" },
              { key: "has_open_issues", label: "С проблемами", type: "bool" },
            ]}
            queryKey="mart-sku"
          />
        </TabsContent>
        <TabsContent value="stock">
          <DataBrowser
            path="/marts/stock-daily" columns={stockDailyCols} withDateRange withNmId
            extraFilters={[
              { key: "sku_id", label: "sku_id", type: "number" },
              { key: "barcode", label: "Штрихкод", type: "text" },
              { key: "warehouse_name", label: "Склад", type: "text" },
            ]}
            queryKey="mart-stock"
          />
        </TabsContent>
        <TabsContent value="expense">
          <DataBrowser path="/marts/account-expense-daily" columns={expenseCols} withDateRange queryKey="mart-exp" />
        </TabsContent>
        <TabsContent value="fin-reconc">
          <DataBrowser
            path="/marts/finance-reconciliation" columns={finReconcCols} withDateRange withNmId
            extraFilters={[
              { key: "srid", label: "ID операции", type: "text" },
              { key: "barcode", label: "Штрихкод", type: "text" },
              { key: "status", label: "Статус", type: "text" },
            ]}
            queryKey="mart-fin"
          />
        </TabsContent>
      </Tabs>
    </PageShell>
  );
}
