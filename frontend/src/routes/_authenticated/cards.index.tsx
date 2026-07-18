import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useQuery, keepPreviousData } from "@tanstack/react-query";
import { useState, useMemo, useEffect } from "react";
import { api, type MArticlesResponse, type MFilters, type MArticleRow } from "@/lib/api";
import { fetchMoneyArticles } from "@/lib/money-endpoints";
import { useAccounts } from "@/lib/account-context";
import { useAuth } from "@/lib/auth-context";
import { PageShell, PageHeader } from "@/components/PageShell";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import { formatMoney, formatNumber, formatPercent } from "@/lib/format";
import { Search, AlertTriangle, ChevronLeft, ChevronRight } from "lucide-react";
import { useDateRange } from "@/lib/date-range-context";
import { cn } from "@/lib/utils";
import { EndpointError } from "@/components/EndpointError";
import { DataDependencyNotice } from "@/components/data-health/DataCoveragePanel";
import { LegacyDiagnosticNotice } from "@/components/LegacyDiagnosticNotice";
import { canAccessLegacyDiagnostics } from "@/lib/legacy-diagnostics";

export const Route = createFileRoute("/_authenticated/cards/")({
  component: CardsPage,
  errorComponent: ({ error, reset }) => <EndpointError error={error} reset={reset} />,
});

type TrustState = "final" | "provisional" | "blocked" | "";
type DecisionKey = "REORDER" | "LIQUIDATE" | "WATCH" | "DO_NOT_BUY" | "DATA_FIX" | "";
type Bucket = "" | "profitable" | "loss" | "provisional" | "data_blocked";

const DECISION_LABEL: Record<Exclude<DecisionKey, "">, string> = {
  REORDER: "Дозаказать",
  LIQUIDATE: "Ликвидировать",
  WATCH: "Наблюдать",
  DO_NOT_BUY: "Не заказывать",
  DATA_FIX: "Сначала data-fix",
};

function getDecision(r: MArticleRow): DecisionKey {
  const raw = (r.money_answer?.decision || r.next_action?.action_type || "").toUpperCase();
  if (raw.includes("REORDER")) return "REORDER";
  if (raw.includes("LIQUIDATE")) return "LIQUIDATE";
  if (raw.includes("DO_NOT") || raw.includes("DONOT") || raw.includes("STOP")) return "DO_NOT_BUY";
  if (raw.includes("DATA")) return "DATA_FIX";
  if (raw.includes("WATCH") || raw.includes("MONITOR")) return "WATCH";
  if (r.flags?.data_fix_required) return "DATA_FIX";
  return "";
}

function getTrust(r: MArticleRow): TrustState {
  const s = (r.profit_finality?.state ?? r.finality?.state ?? "") as TrustState;
  if (s === "final" || s === "provisional" || s === "blocked") return s;
  return "";
}

function CardsPage() {
  const { activeId } = useAccounts();
  const { user } = useAuth();
  const navigate = useNavigate();
  const legacyAllowed = canAccessLegacyDiagnostics(user?.is_superuser);
  const [search, setSearch] = useState("");
  const [searchDebounced, setSearchDebounced] = useState("");
  const [subject, setSubject] = useState<string>("");
  const [decision, setDecision] = useState<DecisionKey>("");
  const [trust, setTrust] = useState<TrustState>("");
  const [bucket, setBucket] = useState<Bucket>("");
  const [onlyOverstock, setOnlyOverstock] = useState(false);
  const [onlyAdsRisk, setOnlyAdsRisk] = useState(false);
  const [onlyFinanceMismatch, setOnlyFinanceMismatch] = useState(false);
  const [limit, setLimit] = useState(25);
  const [offset, setOffset] = useState(0);

  const { from: dateFrom, to: dateTo } = useDateRange();

  // Debounce search input — avoid one request per keystroke.
  useEffect(() => {
    const t = setTimeout(() => { setSearchDebounced(search); setOffset(0); }, 350);
    return () => clearTimeout(t);
  }, [search]);

  // Reset paging when server-side filters change so we never land on an empty page.
  useEffect(() => { setOffset(0); }, [subject, dateFrom, dateTo]);

  const filtersQ = useQuery({
    queryKey: ["money-filters", activeId],
    enabled: !!activeId && legacyAllowed,
    staleTime: 10 * 60 * 1000,
    queryFn: () => api<MFilters>("/money/filters", { query: { account_id: activeId! } }),
  });

  const { data, isLoading, isFetching } = useQuery({
    queryKey: ["money-articles", activeId, dateFrom, dateTo, searchDebounced, subject, limit, offset],
    enabled: !!activeId && legacyAllowed,
    staleTime: 60 * 1000,
    placeholderData: keepPreviousData,
    queryFn: async () => {
      const res = await fetchMoneyArticles({
        accountId: activeId!,
        dateFrom,
        dateTo,
        search: searchDebounced || undefined,
        subjectName: subject || undefined,
        limit,
        offset,
      });
      if (Array.isArray((res as any).items) && (res as any).summary) return res as unknown as MArticlesResponse;
      const items = ((res as any).items ?? (res as any)) as any[];
      const map = new Map<number, MArticleRow>();
      for (const it of items) {
        const nm = it.nm_id ?? 0;
        if (!nm) continue;
        const prev = map.get(nm);
        if (!prev) map.set(nm, { ...it, variant_count: 1 } as MArticleRow);
        else (prev as any).variant_count = (prev.variant_count ?? 1) + 1;
      }
      const grouped = Array.from(map.values());
      return {
        total: grouped.length, limit, offset,
        summary: { profitable_count: 0, loss_count: 0, data_blocked_count: 0, stock_risk_count: 0, overstock_count: 0, provisional_count: 0 },
        items: grouped,
      } as MArticlesResponse;
    },
  });

  const filters = filtersQ.data;
  const allRows = data?.items ?? [];

  const rows = useMemo(() => allRows.filter((r) => {
    const t = getTrust(r);
    const d = getDecision(r);
    if (decision && d !== decision) return false;
    if (trust && t !== trust) return false;
    if (bucket === "profitable" && !(r.money.profit.after_ads > 0)) return false;
    if (bucket === "loss" && !(r.money.profit.after_ads < 0)) return false;
    if (bucket === "provisional" && t !== "provisional") return false;
    if (bucket === "data_blocked" && !(t === "blocked" || r.flags?.data_fix_required)) return false;
    if (onlyOverstock && !(r.flags?.overstock || (r.stock as any)?.stock_status === "overstock")) return false;
    if (onlyAdsRisk && !(r.flags?.ads_risk || r.ads.unallocated_spend > 0)) return false;
    if (onlyFinanceMismatch && !(r.flags?.finance_mismatch || (r.money.finance_diff_amount ?? 0) !== 0)) return false;
    return true;
  }), [allRows, decision, trust, bucket, onlyOverstock, onlyAdsRisk, onlyFinanceMismatch]);

  const counts = useMemo(() => {
    const s = data?.summary;
    const econProfit = s?.economically_profitable_count ?? allRows.filter(r => r.money.profit.after_ads > 0).length;
    const econLoss = s?.economically_loss_count ?? allRows.filter(r => r.money.profit.after_ads < 0).length;
    const finalProfit = s?.final_profitable_count ?? allRows.filter(r => getTrust(r) === "final" && r.money.profit.after_ads > 0).length;
    const finalLoss = s?.final_loss_count ?? allRows.filter(r => getTrust(r) === "final" && r.money.profit.after_ads < 0).length;
    const provisional = s?.provisional_count ?? allRows.filter(r => getTrust(r) === "provisional").length;
    const dataBlocked = s?.data_blocked_count ?? allRows.filter(r => getTrust(r) === "blocked" || r.flags?.data_fix_required).length;
    return { total: data?.total ?? allRows.length, econProfit, econLoss, finalProfit, finalLoss, provisional, dataBlocked };
  }, [data, allRows]);

  const showEconVsFinalGap = counts.econProfit > 0 && counts.finalProfit === 0;

  if (!legacyAllowed) {
    return (
      <PageShell>
        <PageHeader
          title="Карточки переехали в Товары"
          description="Старый список карточек с hardcoded-флагами скрыт, чтобы не дублировать динамические проблемы."
        />
        <Alert data-testid="legacy-cards-hidden">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>Legacy-диагностика карточек недоступна</AlertTitle>
          <AlertDescription className="space-y-3">
            <div>
              Для продавца основная карточка товара находится в разделе Товары, а проблемы и действия — в Центре действий.
            </div>
            <div className="flex flex-wrap gap-2">
              <Button size="sm" onClick={() => navigate({ to: "/products" as any })}>Открыть товары</Button>
              <Button size="sm" variant="outline" onClick={() => navigate({ to: "/action-center" as any })}>
                Открыть Центр действий
              </Button>
            </div>
          </AlertDescription>
        </Alert>
      </PageShell>
    );
  }

  const summaryCards = [
    { l: "Карточек всего",          v: counts.total,        tone: "muted" as const },
    { l: "Экономически прибыльные", v: counts.econProfit,   tone: "success" as const },
    { l: "Экономически убыточные",  v: counts.econLoss,     tone: "danger" as const },
    { l: "Финально подтв. прибыль", v: counts.finalProfit,  tone: showEconVsFinalGap ? "warning" as const : "success" as const },
    { l: "Финально подтв. убыток",  v: counts.finalLoss,    tone: "danger" as const },
    { l: "Предварительные",         v: counts.provisional,  tone: "warning" as const },
    { l: "Data Blocked",            v: counts.dataBlocked,  tone: "danger" as const },
  ];

  return (
    <PageShell>
      <PageHeader
        title="Карточки — что приносит деньги, что забирает"
        description="Карточка = артикул WB (nm_id). Размеры/SKU/баркоды — внутри детали карточки."
      />

      <LegacyDiagnosticNotice surfaceId="legacy_cards_route" />

      {activeId && <DataDependencyNotice accountId={activeId} domains={["product_cards", "sales", "orders", "finance", "stocks", "prices", "ads"]} />}

      {!activeId && (
        <Alert><AlertTitle>Не выбран кабинет</AlertTitle>
          <AlertDescription>Выберите кабинет в шапке.</AlertDescription></Alert>
      )}

      {showEconVsFinalGap && (
        <Alert className="mb-4 border-warning/40 bg-warning/5">
          <AlertTriangle className="h-4 w-4 text-warning" />
          <AlertTitle>Прибыль есть, но не подтверждена финалом</AlertTitle>
          <AlertDescription>
            Экономически прибыльные карточки есть, но финальная прибыль предварительная из-за finance/cost/data issues.
            Экономически прибыльных: <b>{counts.econProfit}</b>. Финально подтверждённых: <b>0</b>.
          </AlertDescription>
        </Alert>
      )}

      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-2 mb-4">
        {summaryCards.map((c, i) => (
          <Card key={i} className={
            c.tone === "danger"  ? "border-destructive/30 bg-destructive/5" :
            c.tone === "warning" ? "border-warning/30 bg-warning/5" :
            c.tone === "success" ? "border-success/30 bg-success/5" :
                                   "border-border"}>
            <CardContent className="p-3">
              <div className="text-[10px] uppercase tracking-wider font-semibold text-muted-foreground">{c.l}</div>
              <div className="text-xl font-semibold tabular-nums">{formatNumber(c.v)}</div>
            </CardContent>
          </Card>
        ))}
      </div>

      <div className="flex flex-wrap items-center gap-3 mb-3">
        <div className="relative flex-1 min-w-[220px] max-w-md">
          <Search className="h-4 w-4 absolute left-2.5 top-2.5 text-muted-foreground" />
          <Input placeholder="Поиск: nm_id, vendor_code, название…" value={search} onChange={(e) => setSearch(e.target.value)} className="pl-9" />
        </div>

        <Select value={decision || "all"} onValueChange={(v) => setDecision((v === "all" ? "" : v) as DecisionKey)}>
          <SelectTrigger className="w-44"><SelectValue placeholder="Решение" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Любое решение</SelectItem>
            {(Object.keys(DECISION_LABEL) as Array<keyof typeof DECISION_LABEL>).map((k) => (
              <SelectItem key={k} value={k}>{DECISION_LABEL[k]}</SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select value={trust || "all"} onValueChange={(v) => setTrust((v === "all" ? "" : v) as TrustState)}>
          <SelectTrigger className="w-44"><SelectValue placeholder="Качество данных" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Любое качество</SelectItem>
            <SelectItem value="final">Финальные</SelectItem>
            <SelectItem value="provisional">Предварительные</SelectItem>
            <SelectItem value="blocked">Заблокированы данными</SelectItem>
          </SelectContent>
        </Select>

        <Select value={subject || "all"} onValueChange={(v) => setSubject(v === "all" ? "" : v)}>
          <SelectTrigger className="w-44"><SelectValue placeholder="Категория" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Все категории</SelectItem>
            {filters?.subjects?.map((s) => <SelectItem key={s.key} value={s.key}>{s.label}</SelectItem>)}
          </SelectContent>
        </Select>

        <Select value={bucket || "all"} onValueChange={(v) => setBucket((v === "all" ? "" : v) as Bucket)}>
          <SelectTrigger className="w-44"><SelectValue placeholder="Сегмент" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Все сегменты</SelectItem>
            <SelectItem value="profitable">Прибыльные</SelectItem>
            <SelectItem value="loss">Убыточные</SelectItem>
            <SelectItem value="provisional">Предварительные</SelectItem>
            <SelectItem value="data_blocked">Заблокированы данными</SelectItem>
          </SelectContent>
        </Select>
      </div>

      <div className="flex flex-wrap items-center gap-3 mb-4">
        <ToggleChip checked={onlyOverstock} onChange={setOnlyOverstock} label="Сверхзапас" />
        <ToggleChip checked={onlyAdsRisk} onChange={setOnlyAdsRisk} label="Риск рекламы" />
        <ToggleChip checked={onlyFinanceMismatch} onChange={setOnlyFinanceMismatch} label="Расхождение с финансами" />
      </div>

      <Card className="relative">
        {isFetching && !isLoading && (
          <div className="absolute top-2 right-3 z-10 text-[10px] text-muted-foreground bg-background/80 backdrop-blur px-2 py-0.5 rounded border">обновление…</div>
        )}
        <CardContent className="p-0 overflow-x-auto">
          {isLoading ? (
            <div className="p-6 space-y-2">{[1,2,3,4,5].map(i => <Skeleton key={i} className="h-10" />)}</div>
          ) : rows.length === 0 ? (
            <div className="p-10 text-center text-sm text-muted-foreground">
              <AlertTriangle className="h-8 w-8 mx-auto mb-2 text-muted-foreground/50" />
              По выбранным фильтрам ничего не найдено.
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="min-w-[260px]">Карточка</TableHead>
                  <TableHead className="text-right">Выручка</TableHead>
                  <TableHead className="text-right">Прибыль до рекл.</TableHead>
                  <TableHead className="text-right">Прибыль после рекл.</TableHead>
                  <TableHead className="text-right">Маржа</TableHead>
                  <TableHead className="text-right">ROI</TableHead>
                  <TableHead className="text-right">Реклама / DRR</TableHead>
                  <TableHead className="text-right">Остаток шт.</TableHead>
                  <TableHead className="text-right">Остаток ₽</TableHead>
                  <TableHead>Решение</TableHead>
                  <TableHead>Доверие</TableHead>
                  <TableHead className="min-w-[220px]">Следующий шаг</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((r) => (
                  <ArticleRow
                    key={r.nm_id}
                    r={r}
                    onClick={() => navigate({ to: "/cards/$nmId" as any, params: { nmId: String(r.nm_id) } as any })}
                  />
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      <div className="flex items-center justify-between mt-3 text-xs text-muted-foreground">
        <div>
          Показано {rows.length} из {counts.total}. Окно: {offset + 1}–{offset + (data?.items.length ?? 0)}.
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" disabled={offset === 0 || isLoading} onClick={() => setOffset(Math.max(0, offset - limit))}>
            <ChevronLeft className="h-3.5 w-3.5 mr-1" /> Назад
          </Button>
          <Button variant="outline" size="sm" disabled={isLoading || (data?.items.length ?? 0) < limit} onClick={() => setOffset(offset + limit)}>
            Далее <ChevronRight className="h-3.5 w-3.5 ml-1" />
          </Button>
          <Select value={String(limit)} onValueChange={(v) => { setLimit(Number(v)); setOffset(0); }}>
            <SelectTrigger className="w-24 h-8"><SelectValue /></SelectTrigger>
            <SelectContent>
              {[25, 50, 100, 200].map(n => <SelectItem key={n} value={String(n)}>{n} / стр.</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
      </div>
    </PageShell>
  );
}

function ToggleChip({ checked, onChange, label }: { checked: boolean; onChange: (b: boolean) => void; label: string }) {
  return (
    <div className="flex items-center gap-2 px-2.5 py-1.5 rounded-md border border-border bg-card">
      <Switch checked={checked} onCheckedChange={onChange} id={label} />
      <Label htmlFor={label} className="text-xs cursor-pointer">{label}</Label>
    </div>
  );
}

function FlagBadge({ tone, children }: { tone: "success" | "warning" | "danger" | "info" | "muted"; children: React.ReactNode }) {
  const tones: Record<string, string> = {
    success: "bg-success/15 text-success border-success/30",
    warning: "bg-warning/15 text-warning border-warning/30",
    danger:  "bg-destructive/15 text-destructive border-destructive/30",
    info:    "bg-primary/10 text-primary border-primary/30",
    muted:   "bg-muted text-muted-foreground border-border",
  };
  return <Badge variant="outline" className={cn("text-[10px] border px-1.5 py-0", tones[tone])}>{children}</Badge>;
}

function DecisionBadge({ d }: { d: DecisionKey }) {
  if (!d) return <span className="text-muted-foreground text-xs">—</span>;
  const tone: "success" | "warning" | "danger" | "info" | "muted" =
    d === "REORDER" ? "success" :
    d === "LIQUIDATE" ? "danger" :
    d === "DO_NOT_BUY" ? "danger" :
    d === "DATA_FIX" ? "warning" :
    "info";
  return <FlagBadge tone={tone}>{d}</FlagBadge>;
}

function TrustBadgeCell({ t }: { t: TrustState }) {
  if (t === "final") return <FlagBadge tone="success">Финальная</FlagBadge>;
  if (t === "provisional") return <FlagBadge tone="warning">Предварительная</FlagBadge>;
  if (t === "blocked") return <FlagBadge tone="danger">Данные заблокированы</FlagBadge>;
  return <span className="text-muted-foreground text-xs">—</span>;
}

function ArticleRow({ r, onClick }: { r: MArticleRow; onClick: () => void }) {
  const profit = r.money.profit.after_ads;
  const before = r.money.profit.before_ads;
  const negative = profit < 0;
  const positive = profit > 0;
  const adsUnallocated = r.ads.unallocated_spend > 0;
  const decision = getDecision(r);
  const trust = getTrust(r);
  const nextStep = r.money_answer?.main_next_step || r.next_action?.what_to_do || r.next_action?.title || "";
  const stockQty = (r.stock as any).quantity ?? (r.stock as any).quantity_full ?? null;

  return (
    <TableRow className="cursor-pointer hover:bg-muted/40" onClick={onClick}>
      <TableCell>
        <div className="font-medium text-sm truncate max-w-[260px]">{r.title || `nm ${r.nm_id}`}</div>
        <div className="text-[11px] text-muted-foreground font-mono">
          nm {r.nm_id}{r.vendor_code ? ` · ${r.vendor_code}` : ""}{r.brand ? ` · ${r.brand}` : ""}{r.subject_name ? ` · ${r.subject_name}` : ""}
        </div>
      </TableCell>
      <TableCell className="text-right tabular-nums">{formatMoney(r.money.revenue)}</TableCell>
      <TableCell className="text-right tabular-nums text-sm">{formatMoney(before)}</TableCell>
      <TableCell className="text-right tabular-nums">
        <Badge variant="outline" className={negative ? "bg-destructive/10 text-destructive border-destructive/30" : positive ? "bg-success/10 text-success border-success/30" : "bg-muted text-muted-foreground"}>
          {formatMoney(profit)}
        </Badge>
      </TableCell>
      <TableCell className="text-right tabular-nums text-sm">{formatPercent(r.money.profit.margin_after_ads_percent)}</TableCell>
      <TableCell className="text-right tabular-nums text-sm">{formatPercent(r.money.profit.roi_after_ads_percent)}</TableCell>
      <TableCell className="text-right tabular-nums text-xs">
        <div className={adsUnallocated ? "text-warning" : ""}>{formatMoney(r.ads.source_spend)}</div>
        <div className="text-[10px] text-muted-foreground">DRR {formatPercent(r.ads.drr_percent_source)}</div>
      </TableCell>
      <TableCell className="text-right tabular-nums text-sm">{stockQty == null ? "—" : formatNumber(stockQty)}</TableCell>
      <TableCell className="text-right tabular-nums text-sm">{formatMoney(r.stock.stock_value)}</TableCell>
      <TableCell><DecisionBadge d={decision} /></TableCell>
      <TableCell><TrustBadgeCell t={trust} /></TableCell>
      <TableCell className="text-xs max-w-[240px]">
        {nextStep
          ? <div className="truncate" title={nextStep}>{nextStep}</div>
          : <span className="text-muted-foreground">—</span>}
      </TableCell>
    </TableRow>
  );
}
