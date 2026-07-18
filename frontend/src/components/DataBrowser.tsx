import { useQuery, keepPreviousData } from "@tanstack/react-query";
import { useState, useEffect, type ReactNode } from "react";
import { api, type Paginated, type Row } from "@/lib/api";
import { useAccounts } from "@/lib/account-context";
import { useDateRange } from "@/lib/date-range-context";
import { Pager } from "@/components/Pager";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ArrowDown, ArrowUp, ArrowUpDown, Loader2, X } from "lucide-react";
import { Button } from "@/components/ui/button";

export interface Column<T> {
  header: string;
  cell: (r: T) => ReactNode;
  className?: string;
  align?: "left" | "right";
  sortKey?: string;
}

export type ExtraFilter =
  | { key: string; label: string; type: "text" | "number"; placeholder?: string; width?: string }
  | { key: string; label: string; type: "select"; options: { value: string; label: string }[]; width?: string }
  | { key: string; label: string; type: "bool"; width?: string };

interface Props<T extends Row> {
  path: string;
  columns: Column<T>[];
  withDateRange?: boolean;
  withNmId?: boolean;
  withSearch?: boolean;
  extraFilters?: ExtraFilter[];
  extraQuery?: Record<string, string | number | boolean | undefined>;
  limit?: number;
  emptyText?: string;
  queryKey: string;
  requireAccount?: boolean;
}

export function DataBrowser<T extends Row>({
  path, columns, withDateRange, withNmId, withSearch, extraFilters,
  extraQuery, limit = 50, emptyText = "Нет данных", queryKey, requireAccount = true,
}: Props<T>) {
  const { activeId } = useAccounts();
  const { from: gFrom, to: gTo } = useDateRange();
  // Business pages share one global period — DataBrowser reads it from context
  // when withDateRange is set. No per-page local date state.
  const dateFrom = withDateRange ? gFrom : "";
  const dateTo = withDateRange ? gTo : "";
  const [offset, setOffset] = useState(0);
  const [nmId, setNmId] = useState("");
  const [search, setSearch] = useState("");
  // Debounced copies — used in the query key + payload so typing doesn't
  // fire a request per keystroke.
  const [nmIdDebounced, setNmIdDebounced] = useState("");
  const [searchDebounced, setSearchDebounced] = useState("");
  const [extras, setExtras] = useState<Record<string, string | boolean>>({});
  const [sortBy, setSortBy] = useState<string | undefined>(undefined);
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");

  // Reset paging when global period changes so the new window starts at page 1.
  useEffect(() => { if (withDateRange) setOffset(0); }, [gFrom, gTo, withDateRange]);

  useEffect(() => {
    const t = setTimeout(() => { setSearchDebounced(search); setOffset(0); }, 350);
    return () => clearTimeout(t);
  }, [search]);
  useEffect(() => {
    const t = setTimeout(() => { setNmIdDebounced(nmId); setOffset(0); }, 350);
    return () => clearTimeout(t);
  }, [nmId]);

  const toggleSort = (key: string) => {
    setOffset(0);
    if (sortBy !== key) { setSortBy(key); setSortDir("desc"); }
    else if (sortDir === "desc") setSortDir("asc");
    else { setSortBy(undefined); setSortDir("desc"); }
  };

  const setExtra = (k: string, v: string | boolean) => {
    setOffset(0);
    setExtras((p) => {
      const n = { ...p };
      if (v === "" || v === false) delete n[k];
      else n[k] = v;
      return n;
    });
  };

  const reset = () => {
    setOffset(0); setNmId(""); setSearch(""); setNmIdDebounced(""); setSearchDebounced("");
    setExtras({});
    setSortBy(undefined); setSortDir("desc");
  };

  const extraVals: Record<string, string | number | boolean | undefined> = {};
  for (const [k, v] of Object.entries(extras)) {
    if (typeof v === "boolean") extraVals[k] = v;
    else if (v !== "") extraVals[k] = /^-?\d+$/.test(v) && (extraFilters?.find((f) => f.key === k)?.type === "number") ? Number(v) : v;
  }

  const query = {
    account_id: activeId ?? undefined,
    nm_id: withNmId && nmIdDebounced ? Number(nmIdDebounced) : undefined,
    search: withSearch && searchDebounced ? searchDebounced : undefined,
    date_from: withDateRange ? dateFrom || undefined : undefined,
    date_to: withDateRange ? dateTo || undefined : undefined,
    sort_by: sortBy,
    sort_dir: sortBy ? sortDir : undefined,
    limit, offset,
    ...extraVals,
    ...extraQuery,
  };

  const { data, isLoading, isFetching } = useQuery({
    queryKey: [queryKey, activeId, dateFrom, dateTo, searchDebounced, nmIdDebounced, extraVals, sortBy, sortDir, offset, limit],
    queryFn: () => api<Paginated<T>>(path, { query }),
    enabled: !requireAccount || !!activeId,
    placeholderData: keepPreviousData,
  });

  const hasFilters = withDateRange || withNmId || withSearch || (extraFilters?.length ?? 0) > 0;

  return (
    <div className="space-y-3">
      {hasFilters && (
        <Card>
          <CardContent className="p-3 flex flex-wrap items-end gap-3">
            {withSearch && (
              <div className="flex-1 min-w-[200px]">
                <Label className="text-xs">Поиск</Label>
                <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="название / артикул / штрихкод" />
              </div>
            )}
            {withNmId && (
              <div><Label className="text-xs">Артикул WB</Label><Input value={nmId} onChange={(e) => setNmId(e.target.value)} className="w-32" /></div>
            )}
            {/* Period comes from the global top-bar — no local date inputs. */}
            {extraFilters?.map((f) => {
              if (f.type === "select") {
                const v = (extras[f.key] as string | undefined) ?? "";
                return (
                  <div key={f.key} className={f.width ?? "min-w-[140px]"}>
                    <Label className="text-xs">{f.label}</Label>
                    <Select value={v || "__all"} onValueChange={(val) => setExtra(f.key, val === "__all" ? "" : val)}>
                      <SelectTrigger><SelectValue placeholder="Все" /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="__all">Все</SelectItem>
                        {f.options.map((o) => <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>)}
                      </SelectContent>
                    </Select>
                  </div>
                );
              }
              if (f.type === "bool") {
                const v = (extras[f.key] as boolean | undefined) ?? false;
                return (
                  <div key={f.key} className="flex items-center gap-1 pb-1.5">
                    <input type="checkbox" id={f.key} checked={v} onChange={(e) => setExtra(f.key, e.target.checked)} className="h-4 w-4" />
                    <Label htmlFor={f.key} className="text-xs">{f.label}</Label>
                  </div>
                );
              }
              return (
                <div key={f.key} className={f.width ?? "w-36"}>
                  <Label className="text-xs">{f.label}</Label>
                  <Input
                    type={f.type === "number" ? "number" : "text"}
                    value={(extras[f.key] as string | undefined) ?? ""}
                    onChange={(e) => setExtra(f.key, e.target.value)}
                    placeholder={f.placeholder}
                  />
                </div>
              );
            })}
            <Button variant="ghost" size="sm" onClick={reset} className="ml-auto"><X className="h-3.5 w-3.5 mr-1" />Сбросить</Button>
          </CardContent>
        </Card>
      )}
      <Card>
        <CardContent className="p-0">
          {isLoading && <div className="p-6 flex items-center gap-2 text-sm text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin" /> Загрузка…</div>}
          {!isLoading && data && (
            <div className="relative">
              {isFetching && (
                <div className="absolute top-2 right-3 z-10 flex items-center gap-1.5 text-[11px] text-muted-foreground bg-background/80 backdrop-blur px-2 py-0.5 rounded border">
                  <Loader2 className="h-3 w-3 animate-spin" /> обновление…
                </div>
              )}
              <div className="overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow>
                      {columns.map((c, i) => {
                        const active = c.sortKey && c.sortKey === sortBy;
                        const Icon = active ? (sortDir === "asc" ? ArrowUp : ArrowDown) : ArrowUpDown;
                        return (
                          <TableHead key={i} className={c.align === "right" ? "text-right" : c.className}>
                            {c.sortKey ? (
                              <button type="button" onClick={() => toggleSort(c.sortKey!)} className={`inline-flex items-center gap-1 hover:text-foreground ${active ? "text-foreground" : ""}`}>
                                {c.header}<Icon className="h-3 w-3 opacity-60" />
                              </button>
                            ) : c.header}
                          </TableHead>
                        );
                      })}
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {data.items.map((r, ri) => (
                      <TableRow key={(r as Row).id ?? ri}>
                        {columns.map((c, ci) => (
                          <TableCell key={ci} className={c.align === "right" ? "text-right tabular-nums" : c.className}>{c.cell(r)}</TableCell>
                        ))}
                      </TableRow>
                    ))}
                    {data.items.length === 0 && <TableRow><TableCell colSpan={columns.length} className="text-center text-muted-foreground py-8">{emptyText}</TableCell></TableRow>}
                  </TableBody>
                </Table>
              </div>
              <div className="px-3 pb-3"><Pager total={data.total} limit={limit} offset={offset} onChange={setOffset} /></div>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
