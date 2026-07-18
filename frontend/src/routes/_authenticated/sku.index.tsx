// @ts-nocheck
import { createFileRoute, Link } from "@tanstack/react-router";
import { normalizeTrust } from "@/lib/trust";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, type CoreSKUListItem, type Paginated } from "@/lib/api";
import { useAccounts } from "@/lib/account-context";
import { useDateRange } from "@/lib/date-range-context";
import { PageHeader, PageShell } from "@/components/PageShell";
import { Pager, fmtMoney, fmtNum } from "@/components/Pager";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { ArrowDown, ArrowUp, ArrowUpDown, Loader2, X } from "lucide-react";
import { EndpointError } from "@/components/EndpointError";
import { DataDependencyNotice } from "@/components/data-health/DataCoveragePanel";

export const Route = createFileRoute("/_authenticated/sku/")({
  component: SkuDirectoryPage,
  errorComponent: ({ error, reset }) => <EndpointError error={error} reset={reset} />,
});

const LIMIT = 50;
type SortKey = "vendor_code" | "nm_id" | "brand" | "subject_name" | "title" | "status" | "barcode" | "id";

const SORTABLE: { key: SortKey; label: string }[] = [
  { key: "vendor_code", label: "Артикул" },
  { key: "nm_id", label: "Артикул" },
  { key: "title", label: "Название" },
  { key: "brand", label: "Бренд" },
  { key: "subject_name", label: "Категория" },
  { key: "status", label: "Статус" },
  { key: "barcode", label: "Штрихкод" },
  { key: "id", label: "ID" },
];

type CostStatus = { label: string; className: string; title: string };

// Strict mapping per /core-sku contract. cost_truth_level wins; flags only
// resolve ambiguity when the level is missing. has_manual_cost=true alone is
// NEVER treated as a final/supplier-confirmed cost.
function classifyCostStatus(s: any): CostStatus {
  const t = normalizeTrust(s);
  const truthLevelRaw = (t.costTrustPolicy ?? s.cost_truth_level ?? "").toString().toLowerCase();
  const costSource = String(s.cost_source ?? "").toLowerCase();
  const supplier = String(s.supplier ?? "");

  // Resolve truth_level from explicit field, else derive from flags.
  let level = truthLevelRaw;
  if (!level) {
    if (s.has_real_manual_cost === true) level = "supplier_confirmed";
    else if (s.has_placeholder_cost === true || /AUTO_TEMPLATE/i.test(supplier)) level = "placeholder";
    else if (costSource === "operator_baseline") level = "operator_baseline";
    else if (s.has_manual_cost === true) level = "manual_untrusted";
    else level = "missing";
  }

  switch (level) {
    case "supplier_confirmed":
      return {
        label: "Подтверждено поставщиком",
        className: "border-success/40 text-success bg-success/10",
        title: "Себестоимость подтверждена поставщиком",
      };
    case "operator_baseline":
      return {
        label: "Операторская себестоимость",
        className: "border-blue-500/40 text-blue-600 bg-blue-500/10",
        title: "Операторская базовая стоимость — отдельно от подтверждённой поставщиком",
      };
    case "placeholder":
      return {
        label: "Тестовая себестоимость",
        className: "border-orange-500/40 text-orange-600 bg-orange-500/10",
        title: "Автоматическая тестовая себестоимость — не финальная цифра",
      };
    case "missing":
      return {
        label: "Нет себестоимости",
        className: "border-destructive/40 text-destructive bg-destructive/10",
        title: "Себестоимость не задана",
      };
    case "manual_untrusted":
      return {
        label: "Не подтверждено",
        className: "border-muted-foreground/40 text-muted-foreground bg-muted/40",
        title: "Себестоимость введена вручную, но не подтверждена поставщиком",
      };
    case "ambiguous":
      return {
        label: "Неоднозначная",
        className: "border-purple-500/40 text-purple-600 bg-purple-500/10",
        title: "Себестоимость помечена как неоднозначная",
      };
    default:
      return {
        label: "Не подтверждено",
        className: "border-muted-foreground/40 text-muted-foreground bg-muted/40",
        title: `cost_truth_level=${level || "—"}`,
      };
  }
}

function SkuDirectoryPage() {
  const { activeId } = useAccounts();
  const { from: dateFrom, to: dateTo } = useDateRange();
  const [search, setSearch] = useState("");
  const [nmId, setNmId] = useState("");
  const [vendorCode, setVendorCode] = useState("");
  const [barcode, setBarcode] = useState("");
  const [brand, setBrand] = useState("");
  const [subject, setSubject] = useState("");
  const [status, setStatus] = useState("");
  const [hasCost, setHasCost] = useState(false);
  const [hasIssues, setHasIssues] = useState(false);
  const [hasPrice, setHasPrice] = useState(false);
  const [hasSales, setHasSales] = useState(false);
  const [hasRevenue, setHasRevenue] = useState(false);
  const [hasStock, setHasStock] = useState(false);
  const [sortBy, setSortBy] = useState<SortKey | undefined>(undefined);
  const [sortDir, setSortDir] = useState<"asc" | "desc">("asc");
  const [offset, setOffset] = useState(0);

  const toggleSort = (k: SortKey) => {
    setOffset(0);
    if (sortBy !== k) { setSortBy(k); setSortDir("asc"); }
    else if (sortDir === "asc") setSortDir("desc");
    else { setSortBy(undefined); setSortDir("asc"); }
  };

  const reset = () => {
    setSearch(""); setNmId(""); setVendorCode(""); setBarcode(""); setBrand("");
    setSubject(""); setStatus("");
    setHasCost(false); setHasIssues(false); setHasPrice(false);
    setHasSales(false); setHasRevenue(false); setHasStock(false);
    setSortBy(undefined); setSortDir("asc"); setOffset(0);
  };

  const query = {
    account_id: activeId ?? undefined,
    search: search || undefined,
    nm_id: nmId ? Number(nmId) : undefined,
    vendor_code: vendorCode || undefined,
    barcode: barcode || undefined,
    brand: brand || undefined,
    subject_name: subject || undefined,
    status: status || undefined,
    date_from: dateFrom || undefined,
    date_to: dateTo || undefined,
    has_manual_cost: hasCost || undefined,
    has_open_issues: hasIssues || undefined,
    has_price: hasPrice || undefined,
    has_sales: hasSales || undefined,
    has_revenue: hasRevenue || undefined,
    has_stock: hasStock || undefined,
    sort_by: sortBy,
    sort_dir: sortBy ? sortDir : undefined,
    limit: LIMIT,
    offset,
  };

  const { data, isLoading } = useQuery({
    queryKey: ["core-sku", query],
    queryFn: () => api<Paginated<CoreSKUListItem>>("/core-sku", { query }),
    enabled: !!activeId,
  });

  const renderSortHead = (label: string, key?: SortKey, align?: "right") => {
    if (!key) return <TableHead className={align === "right" ? "text-right" : ""}>{label}</TableHead>;
    const active = sortBy === key;
    const Icon = active ? (sortDir === "asc" ? ArrowUp : ArrowDown) : ArrowUpDown;
    return (
      <TableHead className={align === "right" ? "text-right" : ""}>
        <button type="button" onClick={() => toggleSort(key)} className={`inline-flex items-center gap-1 hover:text-foreground ${active ? "text-foreground" : ""}`}>
          {label}<Icon className="h-3 w-3 opacity-60" />
        </button>
      </TableHead>
    );
  };

  return (
    <PageShell>
      <PageHeader title="Справочник SKU" description="Каталог Core SKU и ключевые показатели" />
      {activeId && <DataDependencyNotice accountId={activeId} domains={["product_cards", "prices", "sales", "stocks", "finance"]} />}
      <Card className="mb-3">
        <CardContent className="p-3 flex flex-wrap items-end gap-3">
          <div className="flex-1 min-w-[220px]"><Label className="text-xs">Поиск</Label><Input
            placeholder="название, артикул, артикул WB, штрихкод"
            value={search}
            onChange={(e) => { setSearch(e.target.value); setOffset(0); }}
          /></div>
          <div><Label className="text-xs">Артикул WB</Label><Input className="w-32" value={nmId} onChange={(e) => { setNmId(e.target.value); setOffset(0); }} /></div>
          <div><Label className="text-xs">Артикул</Label><Input className="w-36" value={vendorCode} onChange={(e) => { setVendorCode(e.target.value); setOffset(0); }} /></div>
          <div><Label className="text-xs">Штрихкод</Label><Input className="w-36" value={barcode} onChange={(e) => { setBarcode(e.target.value); setOffset(0); }} /></div>
          <div><Label className="text-xs">Бренд</Label><Input className="w-36" value={brand} onChange={(e) => { setBrand(e.target.value); setOffset(0); }} /></div>
          <div><Label className="text-xs">Категория</Label><Input className="w-36" value={subject} onChange={(e) => { setSubject(e.target.value); setOffset(0); }} /></div>
          <div><Label className="text-xs">Статус</Label><Input className="w-28" value={status} onChange={(e) => { setStatus(e.target.value); setOffset(0); }} /></div>
          {/* Период — из глобального фильтра в верхней панели. */}

          <div className="flex items-center gap-2 pb-1.5">
            <Checkbox id="hp" checked={hasPrice} onCheckedChange={(v) => { setHasPrice(!!v); setOffset(0); }} />
            <Label htmlFor="hp" className="text-sm">Есть цена</Label>
          </div>
          <div className="flex items-center gap-2 pb-1.5">
            <Checkbox id="hsa" checked={hasSales} onCheckedChange={(v) => { setHasSales(!!v); setOffset(0); }} />
            <Label htmlFor="hsa" className="text-sm">Есть продажи</Label>
          </div>
          <div className="flex items-center gap-2 pb-1.5">
            <Checkbox id="hr" checked={hasRevenue} onCheckedChange={(v) => { setHasRevenue(!!v); setOffset(0); }} />
            <Label htmlFor="hr" className="text-sm">Есть выручка</Label>
          </div>
          <div className="flex items-center gap-2 pb-1.5">
            <Checkbox id="hst" checked={hasStock} onCheckedChange={(v) => { setHasStock(!!v); setOffset(0); }} />
            <Label htmlFor="hst" className="text-sm">Есть остаток</Label>
          </div>
          <div className="flex items-center gap-2 pb-1.5">
            <Checkbox id="hc" checked={hasCost} onCheckedChange={(v) => { setHasCost(!!v); setOffset(0); }} />
            <Label htmlFor="hc" className="text-sm">Есть себестоимость</Label>
          </div>
          <div className="flex items-center gap-2 pb-1.5">
            <Checkbox id="hi" checked={hasIssues} onCheckedChange={(v) => { setHasIssues(!!v); setOffset(0); }} />
            <Label htmlFor="hi" className="text-sm">Есть проблемы</Label>
          </div>

          <div className="flex items-center gap-2 pb-1.5 ml-auto">
            <Label className="text-xs">Сортировка:</Label>
            {SORTABLE.slice(0, 4).map((s) => {
              const active = sortBy === s.key;
              const Icon = active ? (sortDir === "asc" ? ArrowUp : ArrowDown) : ArrowUpDown;
              return (
                <Button key={s.key} variant={active ? "secondary" : "ghost"} size="sm" onClick={() => toggleSort(s.key)}>
                  {s.label}<Icon className="h-3 w-3 ml-1 opacity-70" />
                </Button>
              );
            })}
            <Button variant="ghost" size="sm" onClick={reset}><X className="h-3.5 w-3.5 mr-1" />Сбросить</Button>
          </div>
        </CardContent>
      </Card>


      <Card>
        <CardContent className="p-0">
          {isLoading && <div className="p-6 flex items-center gap-2 text-sm text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin" /> Загрузка…</div>}
          {!isLoading && data && (
            <>
              <div className="overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow>
                      {renderSortHead("SKU", "vendor_code")}
                      {renderSortHead("Артикул", "nm_id")}
                      {renderSortHead("Бренд / Категория", "brand")}
                      <TableHead className="text-right">Цена</TableHead>
                      <TableHead className="text-right">Остаток</TableHead>
                      <TableHead className="text-right">Продажи 30д</TableHead>
                      <TableHead className="text-right">Выручка 30д</TableHead>
                      <TableHead>Себест.</TableHead>
                      <TableHead>Статус себест.</TableHead>
                      <TableHead>Проблемы</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {data.items.map((s) => {
                      const cost = classifyCostStatus(s as any);
                      return (
                      <TableRow key={s.id} className="cursor-pointer">
                        <TableCell>
                          <Link to="/sku/$id" params={{ id: String(s.id) }} className="block">
                            <div className="font-medium truncate max-w-[260px]">{s.title || s.vendor_code || `SKU #${s.id}`}</div>
                            <div className="text-xs text-muted-foreground font-mono">{s.vendor_code} · {s.barcode}</div>
                          </Link>
                        </TableCell>
                        <TableCell className="font-mono text-xs">{s.nm_id ?? "—"}</TableCell>
                        <TableCell className="text-xs">{s.brand ?? "—"}<div className="text-muted-foreground">{s.subject_name ?? ""}</div></TableCell>
                        <TableCell className="text-right tabular-nums">{fmtMoney(s.current_discounted_price ?? s.current_price)}</TableCell>
                        <TableCell className="text-right tabular-nums">{fmtNum(s.latest_quantity)}</TableCell>
                        <TableCell className="text-right tabular-nums">{fmtNum(s.last_30d_sales_qty)}</TableCell>
                        <TableCell className="text-right tabular-nums">{fmtMoney(s.last_30d_revenue)}</TableCell>
                        <TableCell className="text-right tabular-nums text-xs">
                          {fmtMoney((s as any).total_unit_cost ?? (s as any).cost_price) ?? "—"}
                        </TableCell>
                        <TableCell>
                          <Badge variant="outline" className={cost.className} title={cost.title}>{cost.label}</Badge>
                        </TableCell>
                        <TableCell>{s.open_issue_count > 0 ? <Badge variant="destructive">{s.open_issue_count}</Badge> : <span className="text-muted-foreground text-xs">0</span>}</TableCell>
                      </TableRow>
                      );
                    })}
                    {data.items.length === 0 && <TableRow><TableCell colSpan={10} className="text-center text-muted-foreground py-8">Ничего не найдено</TableCell></TableRow>}
                  </TableBody>
                </Table>
              </div>
              <div className="px-3 pb-3"><Pager total={data.total} limit={LIMIT} offset={offset} onChange={setOffset} /></div>
            </>
          )}
        </CardContent>
      </Card>
    </PageShell>
  );
}
