import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { PageHeader, PageShell } from "@/components/PageShell";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { DataBrowser, type Column } from "@/components/DataBrowser";
import { fmtDate, fmtMoney, fmtNum } from "@/components/Pager";
import { formatMoney } from "@/lib/format";
import { fetchMoneyArticles } from "@/lib/money-endpoints";
import { useAccounts } from "@/lib/account-context";
import { MoneyPageHeader, rangeFor, type DateRange } from "@/components/money/MoneyPageHeader";
import { BusinessVerdictBadge } from "@/components/money/BusinessVerdictBadge";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { MCardItem, Row } from "@/lib/api";
import { Search, X } from "lucide-react";
import { EndpointError } from "@/components/EndpointError";
import { DataDependencyNotice } from "@/components/data-health/DataCoveragePanel";

export const Route = createFileRoute("/_authenticated/catalog")({ component: CatalogPage, errorComponent: ({ error, reset }) => <EndpointError error={error} reset={reset} /> });

type Bucket = "all" | "profitable" | "loss" | "data_blocked" | "stock_risk" | "overstock" | "price_risk";

const BUCKETS: { id: Bucket; label: string }[] = [
  { id: "all",          label: "Все" },
  { id: "profitable",   label: "Прибыльные" },
  { id: "loss",         label: "Убыточные" },
  { id: "stock_risk",   label: "Риск остатков" },
  { id: "overstock",    label: "Сверхнорма" },
  { id: "price_risk",   label: "Риск цены" },
  { id: "data_blocked", label: "Блокеры данных" },
];

function bucketMatches(b: Bucket, c: MCardItem): boolean {
  if (b === "all") return true;
  const verdict = (c.business_verdict?.status ?? "").toLowerCase();
  const stock = (c.stock?.stock_status ?? "").toLowerCase();
  const price = (c.price?.status ?? "").toLowerCase();
  const profit = c.money?.profit?.after_ads ?? 0;
  if (b === "profitable")   return profit > 0 && verdict !== "data_blocked";
  if (b === "loss")         return profit < 0;
  if (b === "data_blocked") return verdict === "data_blocked";
  if (b === "stock_risk")   return stock === "low" || stock === "out_of_stock" || stock === "stockout";
  if (b === "overstock")    return stock === "overstock" || (c.stock?.days_of_stock ?? 0) > 120;
  if (b === "price_risk")   return price === "below_break_even" || price === "risk" || price === "loss";
  return true;
}

function BusinessTab() {
  const { activeId } = useAccounts();
  const [range, setRange] = useState<DateRange>(() => rangeFor(30));
  const [bucket, setBucket] = useState<Bucket>("all");
  const [search, setSearch] = useState("");

  const q = useQuery<any>({
    queryKey: ["catalog-money-articles", activeId, range.from, range.to],
    enabled: !!activeId,
    queryFn: () =>
      fetchMoneyArticles({
        accountId: activeId!,
        dateFrom: range.from,
        dateTo: range.to,
        limit: 200,
      }),
    staleTime: 60_000,
  });

  const items: MCardItem[] = Array.isArray(q.data) ? q.data : (q.data?.items ?? []);
  const summary = q.data?.summary;
  const refresh = () => q.refetch();

  // counts per bucket (derived once)
  const counts: Record<Bucket, number> = {
    all: items.length,
    profitable:   summary?.profitable_count   ?? items.filter((c) => bucketMatches("profitable", c)).length,
    loss:         summary?.loss_count         ?? items.filter((c) => bucketMatches("loss", c)).length,
    data_blocked: summary?.data_blocked_count ?? items.filter((c) => bucketMatches("data_blocked", c)).length,
    stock_risk:   summary?.stock_risk_count   ?? items.filter((c) => bucketMatches("stock_risk", c)).length,
    overstock:    summary?.overstock_count    ?? items.filter((c) => bucketMatches("overstock", c)).length,
    price_risk:   summary?.price_risk_count   ?? items.filter((c) => bucketMatches("price_risk", c)).length,
  };

  const s = search.trim().toLowerCase();
  const filtered = items.filter((c) => {
    if (!bucketMatches(bucket, c)) return false;
    if (!s) return true;
    return (
      (c.title ?? "").toLowerCase().includes(s) ||
      (c.vendor_code ?? "").toLowerCase().includes(s) ||
      (c.barcode ?? "").toLowerCase().includes(s) ||
      String(c.nm_id ?? "").includes(s)
    );
  });
  // sort by priority score desc
  filtered.sort((a, b) => (b.priority_score ?? 0) - (a.priority_score ?? 0));

  return (
    <div className="space-y-4">
      <MoneyPageHeader
        title=""
        subtitle=""
        range={range}
        onRangeChange={setRange}
        trustState="trusted"
        trustConfidence="medium"
        blockedReasons={[]}
        lastUpdated={q.dataUpdatedAt ? new Date(q.dataUpdatedAt).toISOString() : null}
        onRefresh={refresh}
        isRefreshing={q.isFetching}
      />

      {/* Bucket chips */}
      <div className="flex flex-wrap items-center gap-2">
        {BUCKETS.map((b) => {
          const active = bucket === b.id;
          return (
            <button
              key={b.id}
              type="button"
              onClick={() => setBucket(b.id)}
              className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs border transition-colors ${
                active ? "bg-primary text-primary-foreground border-primary" : "bg-card hover:bg-accent"
              }`}
            >
              {b.label}
              <Badge variant={active ? "secondary" : "outline"} className="text-[10px] px-1.5">
                {fmtNum(counts[b.id])}
              </Badge>
            </button>
          );
        })}
        <div className="ml-auto relative">
          <Search className="absolute left-2 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Поиск артикул / название"
            className="pl-7 w-64 h-9"
          />
          {search && (
            <button
              type="button"
              onClick={() => setSearch("")}
              className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          )}
        </div>
      </div>

      {!activeId && <div className="text-sm text-muted-foreground">Сначала выберите аккаунт.</div>}
      {q.isLoading && (
        <div className="space-y-2">{[1,2,3,4,5,6].map((i) => <Skeleton key={i} className="h-12 w-full" />)}</div>
      )}

      {!q.isLoading && activeId && (
        <Card>
          <CardContent className="p-0">
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Артикул</TableHead>
                    <TableHead>Статус</TableHead>
                    <TableHead className="text-right">Выручка</TableHead>
                    <TableHead className="text-right">Прибыль</TableHead>
                    <TableHead className="text-right">Маржа</TableHead>
                    <TableHead className="text-right">Остаток ₽</TableHead>
                    <TableHead className="text-right">Дней стока</TableHead>
                    <TableHead className="text-right">Отмены %</TableHead>
                    <TableHead className="text-right">Возвраты %</TableHead>
                    <TableHead className="text-right">Реклама</TableHead>
                    <TableHead></TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {filtered.slice(0, 200).map((c) => {
                    const profit = c.money?.profit?.after_ads ?? 0;
                    const margin = c.money?.profit?.margin_after_ads_percent;
                    const dos = c.stock?.days_of_stock;
                    const dosTone =
                      dos == null ? "" :
                      dos < 7 ? "text-destructive" :
                      dos < 14 ? "text-warning" :
                      dos > 120 ? "text-warning" : "";
                    const cancelRate = (c as any).operations?.cancel_rate_percent as number | null | undefined;
                    const returnRate = (c as any).operations?.return_rate_percent as number | null | undefined;
                    const cancelTone = cancelRate != null && cancelRate > 50 ? "text-destructive" : cancelRate != null && cancelRate > 20 ? "text-warning" : "";
                    const returnTone = returnRate != null && returnRate > 20 ? "text-destructive" : returnRate != null && returnRate > 10 ? "text-warning" : "";
                    return (
                      <TableRow key={c.sku_id} className="hover:bg-accent/40">
                        <TableCell className="max-w-[280px]">
                          <div className="text-sm font-medium truncate">{c.title || c.vendor_code || "—"}</div>
                          <div className="text-[11px] text-muted-foreground font-mono truncate">
                            {c.vendor_code ?? "—"} {c.nm_id ? `· nm ${c.nm_id}` : ""}
                          </div>
                          {c.business_verdict?.short_text && (
                            <div className="text-[10px] text-muted-foreground truncate mt-0.5">{c.business_verdict.short_text}</div>
                          )}
                        </TableCell>
                        <TableCell><BusinessVerdictBadge status={c.business_verdict?.status ?? "unknown"} /></TableCell>
                        <TableCell className="text-right tabular-nums">{formatMoney(c.money?.revenue ?? 0)}</TableCell>
                        <TableCell className={`text-right tabular-nums ${profit < 0 ? "text-destructive" : profit > 0 ? "text-success" : ""}`}>
                          {formatMoney(profit)}
                        </TableCell>
                        <TableCell className="text-right tabular-nums">
                          {margin != null ? `${margin.toFixed(1)}%` : "—"}
                        </TableCell>
                        <TableCell className="text-right tabular-nums">
                          {c.stock?.stock_value ? formatMoney(c.stock.stock_value) : <span className="text-muted-foreground italic">—</span>}
                        </TableCell>
                        <TableCell className={`text-right tabular-nums ${dosTone}`}>{dos != null ? fmtNum(dos) : "—"}</TableCell>
                        <TableCell className={`text-right tabular-nums ${cancelTone}`}>{cancelRate != null ? `${cancelRate.toFixed(1)}%` : "—"}</TableCell>
                        <TableCell className={`text-right tabular-nums ${returnTone}`}>{returnRate != null ? `${returnRate.toFixed(1)}%` : "—"}</TableCell>
                        <TableCell className="text-right tabular-nums">{c.ads?.spend ? formatMoney(c.ads.spend) : "—"}</TableCell>
                        <TableCell className="text-right">
                          <Button asChild variant="ghost" size="sm" className="h-7 text-xs">
                            <Link to={`/sku/${c.sku_id}` as any}>Открыть</Link>
                          </Button>
                        </TableCell>
                      </TableRow>
                    );
                  })}
                  {filtered.length === 0 && (
                    <TableRow>
                      <TableCell colSpan={11} className="text-center text-muted-foreground py-10 text-sm">
                        Нет карточек в этом фильтре.
                      </TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            </div>
            {filtered.length > 200 && (
              <div className="px-4 py-2 text-xs text-muted-foreground border-t">
                Показано 200 из {fmtNum(filtered.length)} — уточните фильтр или поиск.
              </div>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}

/* ─── Raw browser columns (preserved) ──────────────────────────────────── */

const productCols: Column<Row>[] = [
  { header: "nm_id", sortKey: "nm_id", cell: (r) => <span className="font-mono text-xs">{(r.nm_id as number) ?? "—"}</span> },
  { header: "Артикул", sortKey: "vendor_code", cell: (r) => <span className="text-xs">{(r.vendor_code as string) ?? "—"}</span> },
  { header: "Название", sortKey: "title", cell: (r) => <span className="text-sm font-medium truncate max-w-[280px] block">{(r.title as string) ?? "—"}</span> },
  { header: "Бренд", sortKey: "brand", cell: (r) => <span className="text-xs">{(r.brand as string) ?? "—"}</span> },
  { header: "Категория", sortKey: "subject_name", cell: (r) => <span className="text-xs">{(r.subject_name as string) ?? "—"}</span> },
  { header: "Обновлён", sortKey: "source_updated_at", cell: (r) => <span className="text-xs">{fmtDate((r.source_updated_at as string | null) ?? (r.updated_at as string | null))}</span> },
];

const priceCols: Column<Row>[] = [
  { header: "nm_id", sortKey: "nm_id", cell: (r) => <span className="font-mono text-xs">{(r.nm_id as number) ?? "—"}</span> },
  { header: "Артикул", sortKey: "vendor_code", cell: (r) => <span className="text-xs">{(r.vendor_code as string) ?? "—"}</span> },
  { header: "Цена", sortKey: "price", align: "right", cell: (r) => fmtMoney(r.price as number) },
  { header: "Со скидкой", sortKey: "discounted_price", align: "right", cell: (r) => fmtMoney(r.discounted_price as number) },
  { header: "Скидка", sortKey: "discount", align: "right", cell: (r) => r.discount != null ? `${r.discount}%` : "—" },
  { header: "Клуб", sortKey: "club_discount", align: "right", cell: (r) => r.club_discount != null ? `${r.club_discount}%` : "—" },
  { header: "Валюта", sortKey: "currency", cell: (r) => <span className="text-xs">{(r.currency as string) ?? "RUB"}</span> },
];

const stockCols: Column<Row>[] = [
  { header: "Дата среза", sortKey: "snapshot_at", cell: (r) => <span className="text-xs">{fmtDate((r.snapshot_at as string | null) ?? (r.date as string | null))}</span> },
  { header: "nm_id", sortKey: "nm_id", cell: (r) => <span className="font-mono text-xs">{(r.nm_id as number) ?? "—"}</span> },
  { header: "Штрихкод", sortKey: "barcode", cell: (r) => <span className="text-xs">{(r.barcode as string) ?? "—"}</span> },
  { header: "Склад", sortKey: "warehouse_name", cell: (r) => <span className="text-xs">{(r.warehouse_name as string) ?? "—"}</span> },
  { header: "Остаток", sortKey: "quantity", align: "right", cell: (r) => fmtNum(r.quantity as number) },
  { header: "Полн.", sortKey: "quantity_full", align: "right", cell: (r) => fmtNum(r.quantity_full as number) },
  { header: "В пути", sortKey: "in_way_to_client", align: "right", cell: (r) => fmtNum(r.in_way_to_client as number) },
];

function CatalogPage() {
  const { activeId } = useAccounts();

  return (
    <PageShell>
      <PageHeader title="Каталог" description="Бизнес-обзор карточек, цены и остатки" />
      {activeId && <DataDependencyNotice accountId={activeId} domains={["product_cards", "prices", "stocks", "sales", "finance", "ads"]} />}
      <Tabs defaultValue="business">
        <TabsList className="flex flex-wrap h-auto">
          <TabsTrigger value="business">Бизнес-обзор</TabsTrigger>
          <TabsTrigger value="products">Товары</TabsTrigger>
          <TabsTrigger value="prices">Цены</TabsTrigger>
          <TabsTrigger value="stocks">Остатки</TabsTrigger>
        </TabsList>
        <TabsContent value="business">
          <BusinessTab />
        </TabsContent>
        <TabsContent value="products">
          <DataBrowser
            path="/products"
            columns={productCols}
            withNmId withSearch
            extraFilters={[
              { key: "vendor_code", label: "Артикул", type: "text" },
              { key: "barcode", label: "Штрихкод", type: "text" },
              { key: "brand", label: "Бренд", type: "text" },
              { key: "subject_name", label: "Категория", type: "text" },
            ]}
            queryKey="products"
          />
        </TabsContent>
        <TabsContent value="prices">
          <DataBrowser
            path="/prices"
            columns={priceCols}
            withNmId withSearch
            extraFilters={[
              { key: "vendor_code", label: "Артикул", type: "text" },
              { key: "currency", label: "Валюта", type: "text", width: "w-24" },
              { key: "is_bad_turnover", label: "Плохая оборачиваемость", type: "bool" },
            ]}
            queryKey="prices"
          />
        </TabsContent>
        <TabsContent value="stocks">
          <DataBrowser
            path="/stocks/snapshots"
            columns={stockCols}
            withNmId withSearch withDateRange
            extraFilters={[
              { key: "barcode", label: "Штрихкод", type: "text" },
              { key: "warehouse_name", label: "Склад", type: "text" },
              { key: "brand", label: "Бренд", type: "text" },
              { key: "subject", label: "Категория", type: "text" },
              { key: "in_stock_only", label: "Только в наличии", type: "bool" },
            ]}
            queryKey="stocks"
          />
        </TabsContent>
      </Tabs>
    </PageShell>
  );
}
