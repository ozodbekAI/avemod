// @ts-nocheck
// История расчётов stock-control: список runs + детальный просмотр.
import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { api } from "@/lib/api";
import { API_ENDPOINTS } from "@/lib/endpoints";
import { toast } from "sonner";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import {
  ChevronLeft,
  Download,
  AlertTriangle,
  RotateCcw,
  Eye,
} from "lucide-react";
import { formatNumber, formatDateTime } from "@/lib/format";

type Run = {
  id: number | string;
  run_type?: string | null; // return_excess | ship_from_hand | store_balance
  status?: string | null;
  created_at?: string | null;
  finished_at?: string | null;
  requested_by_user_id?: number | null;
  result_summary_json?: Record<string, unknown> | null;
  error_summary?: string | null;
};
type JsonRecord = Record<string, unknown>;

const KIND_LABEL: Record<string, string> = {
  return_excess: "Возврат лишнего",
  ship_from_hand: "Поставка по регионам",
  store_balance: "Баланс магазинов",
};

const STATUS_META: Record<string, { label: string; cls: string }> = {
  queued: {
    label: "В очереди",
    cls: "bg-muted text-muted-foreground border-border",
  },
  running: {
    label: "Выполняется",
    cls: "bg-primary/10 text-primary border-primary/30",
  },
  completed: {
    label: "Готово",
    cls: "bg-success/10 text-success border-success/30",
  },
  partial: {
    label: "Готово с предупреждениями",
    cls: "bg-warning/10 text-warning border-warning/30",
  },
  failed: {
    label: "Ошибка",
    cls: "bg-destructive/10 text-destructive border-destructive/30",
  },
  cancelled: {
    label: "Отменён",
    cls: "bg-muted text-muted-foreground border-border",
  },
};

export function HistoryTab({ accountId }: { accountId: number }) {
  const [kind, setKind] = useState<string>("all");
  const [status, setStatus] = useState<string>("all");
  const [openId, setOpenId] = useState<number | string | null>(null);

  const q = useQuery<{ items?: Run[] } | Run[]>({
    queryKey: ["stock-control-runs", accountId, kind, status],
    queryFn: () =>
      api(API_ENDPOINTS.portal.stockControlRuns, {
        query: {
          account_id: accountId,
          ...(kind !== "all" ? { run_type: kind } : {}),
          limit: 100,
        },
      }),
    staleTime: 30_000,
  });

  const items = useMemo(() => {
    const r: unknown = q.data;
    if (!r) return [] as Run[];
    if (Array.isArray(r)) return r as Run[];
    return isRecord(r) && Array.isArray(r.items) ? (r.items as Run[]) : [];
  }, [q.data]);

  if (openId != null) {
    return (
      <RunDetail
        accountId={accountId}
        runId={openId}
        onBack={() => setOpenId(null)}
      />
    );
  }

  return (
    <Card>
      <CardContent className="p-4 md:p-6 space-y-4">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h3 className="text-base font-semibold">История расчётов</h3>
            <p className="text-sm text-muted-foreground">
              Все запуски stock-control: возврат, поставка, баланс.
            </p>
          </div>
          <div className="flex gap-2 flex-wrap">
            <Select value={kind} onValueChange={setKind}>
              <SelectTrigger className="w-[200px] h-9 text-sm">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Все типы</SelectItem>
                <SelectItem value="return_excess">Возврат лишнего</SelectItem>
                <SelectItem value="ship_from_hand">
                  Поставка по регионам
                </SelectItem>
                <SelectItem value="store_balance">Баланс магазинов</SelectItem>
              </SelectContent>
            </Select>
            <Select value={status} onValueChange={setStatus}>
              <SelectTrigger className="w-[160px] h-9 text-sm">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Все статусы</SelectItem>
                <SelectItem value="completed">Готово</SelectItem>
                <SelectItem value="partial">
                  Готово с предупреждениями
                </SelectItem>
                <SelectItem value="running">Выполняется</SelectItem>
                <SelectItem value="queued">В очереди</SelectItem>
                <SelectItem value="failed">Ошибка</SelectItem>
              </SelectContent>
            </Select>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => q.refetch()}
              disabled={q.isFetching}
            >
              <RotateCcw className="h-3 w-3 mr-1" /> Обновить
            </Button>
          </div>
        </div>

        {q.isLoading && (
          <div className="space-y-2">
            {Array.from({ length: 6 }).map((_, i) => (
              <Skeleton key={i} className="h-10" />
            ))}
          </div>
        )}

        {q.isError && (
          <Alert variant="destructive">
            <AlertTriangle className="h-4 w-4" />
            <AlertTitle>Не удалось загрузить историю</AlertTitle>
            <AlertDescription>{(q.error as Error).message}</AlertDescription>
          </Alert>
        )}

        {!q.isLoading && !q.isError && items.length === 0 && (
          <Alert>
            <AlertTitle>История пуста</AlertTitle>
            <AlertDescription>
              Пока нет ни одного расчёта по выбранным фильтрам.
            </AlertDescription>
          </Alert>
        )}

        {!q.isLoading && items.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-xs uppercase text-muted-foreground border-b">
                  <th className="text-left py-2 pr-3">#</th>
                  <th className="text-left py-2 pr-3">Тип</th>
                  <th className="text-left py-2 pr-3">Статус</th>
                  <th className="text-left py-2 pr-3">Создан</th>
                  <th className="text-left py-2 pr-3">Завершён</th>
                  <th className="text-left py-2 pr-3">Пользователь</th>
                  <th className="text-right py-2 pr-3">Сводка</th>
                  <th className="text-right py-2"></th>
                </tr>
              </thead>
              <tbody>
                {items.map((r) => {
                  if (status !== "all" && r.status !== status) return null;
                  const meta =
                    STATUS_META[r.status ?? ""] ?? STATUS_META.queued;
                  return (
                    <tr
                      key={r.id}
                      className="border-b last:border-0 hover:bg-accent/30"
                    >
                      <td className="py-2 pr-3 font-mono text-xs">#{r.id}</td>
                      <td className="py-2 pr-3">
                        {KIND_LABEL[r.run_type ?? ""] ?? r.run_type ?? "—"}
                      </td>
                      <td className="py-2 pr-3">
                        <Badge variant="outline" className={meta.cls}>
                          {meta.label}
                        </Badge>
                      </td>
                      <td className="py-2 pr-3 tabular-nums text-xs">
                        {r.created_at ? formatDateTime(r.created_at) : "—"}
                      </td>
                      <td className="py-2 pr-3 tabular-nums text-xs">
                        {r.finished_at ? formatDateTime(r.finished_at) : "—"}
                      </td>
                      <td className="py-2 pr-3 text-xs text-muted-foreground">
                        {r.requested_by_user_id
                          ? `user #${r.requested_by_user_id}`
                          : "—"}
                      </td>
                      <td className="py-2 pr-3 text-right text-xs tabular-nums">
                        {summarize(r)}
                      </td>
                      <td className="py-2 text-right">
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => setOpenId(r.id)}
                        >
                          <Eye className="h-3 w-3 mr-1" /> Открыть
                        </Button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function summarize(r: Run): string {
  const s = r.result_summary_json ?? {};
  const parts: string[] = [];
  if (s.units_to_move != null)
    parts.push(`перемещ: ${formatNumber(s.units_to_move)}`);
  if (s.planned_units != null)
    parts.push(`план: ${formatNumber(s.planned_units)}`);
  if (s.shortage_units != null)
    parts.push(`деф: ${formatNumber(s.shortage_units)}`);
  if (s.excess_units != null)
    parts.push(`изл: ${formatNumber(s.excess_units)}`);
  return parts.length ? parts.join(" · ") : "—";
}

// ─── Детальный просмотр ──────────────────────────────────────────────
function RunDetail({
  accountId,
  runId,
  onBack,
}: {
  accountId: number;
  runId: number | string;
  onBack: () => void;
}) {
  const detail = useQuery({
    queryKey: ["stock-control-run", runId, "history-detail"],
    queryFn: () =>
      api<Run>(API_ENDPOINTS.portal.stockControlRunDetail(runId), {
        query: { account_id: accountId },
      }),
    staleTime: 60_000,
  });

  return (
    <Card>
      <CardContent className="p-4 md:p-6 space-y-4">
        <div className="flex items-center justify-between gap-3">
          <Button variant="outline" size="sm" onClick={onBack}>
            <ChevronLeft className="h-4 w-4 mr-1" /> К списку
          </Button>
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => void downloadStockControlExport(accountId, runId)}
            >
              <Download className="h-3 w-3 mr-1" /> Excel
            </Button>
          </div>
        </div>

        {detail.isLoading && (
          <div className="space-y-2">
            <Skeleton className="h-6 w-1/3" />
            <Skeleton className="h-20" />
          </div>
        )}

        {detail.isError && (
          <Alert variant="destructive">
            <AlertTriangle className="h-4 w-4" />
            <AlertTitle>Не удалось загрузить расчёт</AlertTitle>
            <AlertDescription>
              {(detail.error as Error).message}
            </AlertDescription>
          </Alert>
        )}

        {detail.data && (
          <>
            <div>
              <h3 className="text-base font-semibold">
                {KIND_LABEL[detail.data.run_type ?? ""] ?? "Расчёт"} #
                {detail.data.id}
              </h3>
              <div className="text-xs text-muted-foreground tabular-nums">
                {detail.data.created_at
                  ? formatDateTime(detail.data.created_at)
                  : "—"}
                {detail.data.finished_at
                  ? ` → ${formatDateTime(detail.data.finished_at)}`
                  : ""}
              </div>
            </div>

            {detail.data.result_summary_json && (
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                {Object.entries(detail.data.result_summary_json).map(
                  ([k, v]) => (
                    <Card key={k}>
                      <CardContent className="p-3 space-y-1">
                        <div className="text-[10px] uppercase tracking-wide text-muted-foreground">
                          {k}
                        </div>
                        <div className="text-lg font-semibold tabular-nums">
                          {typeof v === "number"
                            ? formatNumber(v)
                            : String(v ?? "—")}
                        </div>
                      </CardContent>
                    </Card>
                  ),
                )}
              </div>
            )}

            <Tabs defaultValue="rows" className="w-full">
              <TabsList>
                <TabsTrigger value="rows" className="text-xs">
                  Строки
                </TabsTrigger>
                <TabsTrigger value="movements" className="text-xs">
                  Перемещения
                </TabsTrigger>
              </TabsList>
              <TabsContent value="rows" className="mt-3">
                <RowsTable accountId={accountId} runId={runId} />
              </TabsContent>
              <TabsContent value="movements" className="mt-3">
                <MovementsTable accountId={accountId} runId={runId} />
              </TabsContent>
            </Tabs>
          </>
        )}
      </CardContent>
    </Card>
  );
}

function RowsTable({
  accountId,
  runId,
}: {
  accountId: number;
  runId: number | string;
}) {
  const q = useQuery<{ items?: JsonRecord[] } | JsonRecord[]>({
    queryKey: ["stock-control-run", runId, "history-rows"],
    queryFn: () =>
      api(API_ENDPOINTS.portal.stockControlRunRows(runId), {
        query: { account_id: accountId, limit: 200 },
      }),
    staleTime: 60_000,
  });
  const items = useMemo(() => {
    const r: unknown = q.data;
    if (!r) return [];
    if (Array.isArray(r)) return r;
    return isRecord(r) && Array.isArray(r.items) ? r.items : [];
  }, [q.data]);

  if (q.isLoading) return <Skeleton className="h-40" />;
  if (q.isError)
    return (
      <Alert variant="destructive">
        <AlertDescription>{(q.error as Error).message}</AlertDescription>
      </Alert>
    );
  if (items.length === 0)
    return (
      <div className="text-sm text-muted-foreground py-4 text-center">
        Нет строк
      </div>
    );

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-xs uppercase text-muted-foreground border-b">
            <th className="text-left py-1.5 pr-3">Товар</th>
            <th className="text-left py-1.5 pr-3">Регион</th>
            <th className="text-left py-1.5 pr-3">Склад</th>
            <th className="text-left py-1.5 pr-3">Размер</th>
            <th className="text-right py-1.5 pr-3">Остаток</th>
            <th className="text-right py-1.5 pr-3">Спрос</th>
            <th className="text-right py-1.5">Действие</th>
          </tr>
        </thead>
        <tbody>
          {items.map((r: JsonRecord, i: number) => (
            <tr key={r.id ?? i} className="border-b last:border-0">
              <td className="py-1.5 pr-3">
                {r.nm_id ? (
                  <Link
                    to="/products/$nmId"
                    params={{ nmId: String(r.nm_id) }}
                    className="text-primary hover:underline"
                  >
                    {r.vendor_code || r.nm_id}
                  </Link>
                ) : (
                  (r.vendor_code ?? "—")
                )}
              </td>
              <td className="py-1.5 pr-3">{r.region ?? "—"}</td>
              <td className="py-1.5 pr-3">
                {r.warehouse ?? r.warehouse_name ?? "—"}
              </td>
              <td className="py-1.5 pr-3">{r.size_name ?? "—"}</td>
              <td className="py-1.5 pr-3 text-right tabular-nums">
                {r.current_stock_qty != null
                  ? formatNumber(r.current_stock_qty)
                  : "—"}
              </td>
              <td className="py-1.5 pr-3 text-right tabular-nums">
                {r.orders_qty != null ? formatNumber(r.orders_qty) : "—"}
              </td>
              <td className="py-1.5 text-right tabular-nums font-semibold">
                {r.delta_qty != null ? formatNumber(r.delta_qty) : "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function MovementsTable({
  accountId,
  runId,
}: {
  accountId: number;
  runId: number | string;
}) {
  const q = useQuery<{ items?: JsonRecord[] } | JsonRecord[]>({
    queryKey: ["stock-control-run", runId, "movements"],
    queryFn: () =>
      api(API_ENDPOINTS.portal.stockControlRunMovements(runId), {
        query: { account_id: accountId, limit: 200 },
      }),
    staleTime: 60_000,
  });
  const items = useMemo(() => {
    const r: unknown = q.data;
    if (!r) return [];
    if (Array.isArray(r)) return r;
    return isRecord(r) && Array.isArray(r.items) ? r.items : [];
  }, [q.data]);

  if (q.isLoading) return <Skeleton className="h-40" />;
  if (q.isError)
    return (
      <Alert variant="destructive">
        <AlertDescription>{(q.error as Error).message}</AlertDescription>
      </Alert>
    );
  if (items.length === 0)
    return (
      <div className="text-sm text-muted-foreground py-4 text-center">
        Нет перемещений
      </div>
    );

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-xs uppercase text-muted-foreground border-b">
            <th className="text-left py-1.5 pr-3">Откуда</th>
            <th className="text-left py-1.5 pr-3">Куда</th>
            <th className="text-left py-1.5 pr-3">Товар</th>
            <th className="text-left py-1.5 pr-3">Размер</th>
            <th className="text-right py-1.5">Единиц</th>
          </tr>
        </thead>
        <tbody>
          {items.map((r: JsonRecord, i: number) => (
            <tr key={r.id ?? i} className="border-b last:border-0">
              <td className="py-1.5 pr-3">
                {r.donor_region ?? r.donor_warehouse ?? "—"}
              </td>
              <td className="py-1.5 pr-3">
                {r.recipient_region ?? r.recipient_warehouse ?? "—"}
              </td>
              <td className="py-1.5 pr-3">
                {r.nm_id ? (
                  <Link
                    to="/products/$nmId"
                    params={{ nmId: String(r.nm_id) }}
                    className="text-primary hover:underline"
                  >
                    {r.vendor_code || r.nm_id}
                  </Link>
                ) : (
                  (r.vendor_code ?? "—")
                )}
              </td>
              <td className="py-1.5 pr-3">{r.size_name ?? "—"}</td>
              <td className="py-1.5 text-right tabular-nums font-semibold">
                {r.quantity != null ? formatNumber(r.quantity) : "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function isRecord(value: unknown): value is JsonRecord {
  return !!value && typeof value === "object" && !Array.isArray(value);
}

async function downloadStockControlExport(
  accountId: number,
  runId: number | string,
) {
  try {
    const res = await api<{
      file_name: string;
      content_type: string;
      content_base64: string | null;
    }>(API_ENDPOINTS.portal.stockControlRunExport(runId), {
      query: { account_id: accountId },
    });
    if (!res.content_base64) throw new Error("Export artifact is empty");
    const raw = window.atob(res.content_base64);
    const bytes = new Uint8Array(raw.length);
    for (let i = 0; i < raw.length; i += 1) bytes[i] = raw.charCodeAt(i);
    const blob = new Blob([bytes], {
      type:
        res.content_type ||
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = res.file_name || `stock_control_run_${runId}.xlsx`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 30_000);
    toast.success("Excel скачивается");
  } catch (e) {
    toast.error(e instanceof Error ? e.message : "Не удалось скачать Excel");
  }
}
