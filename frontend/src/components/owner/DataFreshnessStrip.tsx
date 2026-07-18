import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { DatabaseZap } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { API_ENDPOINTS } from "@/lib/endpoints";
import { api, type SyncCursor } from "@/lib/api";
import { useAccounts } from "@/lib/account-context";
import {
  formatSyncTime,
  type DataFreshnessDomain,
  type DataFreshnessItem,
} from "@/lib/owner-ux";
import { cn } from "@/lib/utils";

const DOMAINS: Record<DataFreshnessDomain, { label: string; match: string[] }> =
  {
    sales: {
      label: "Продажи",
      match: ["sales", "sale", "orders", "realization"],
    },
    finance: {
      label: "Финансы",
      match: ["finance", "report", "reconciliation"],
    },
    stocks: { label: "Остатки", match: ["stock", "warehouse", "inventory"] },
    ads: {
      label: "Реклама",
      match: ["ads", "advert", "campaign", "promotion"],
    },
    costs: { label: "Себестоимость", match: ["cost", "cogs", "manual_cost"] },
  };

function unwrapCursors(data: unknown): SyncCursor[] {
  if (Array.isArray(data)) return data as SyncCursor[];
  const maybePage = (data ?? {}) as { items?: unknown; rows?: unknown };
  if (Array.isArray(maybePage.items)) return maybePage.items as SyncCursor[];
  if (Array.isArray(maybePage.rows)) return maybePage.rows as SyncCursor[];
  return [];
}

function toTs(value: string | null | undefined): number {
  if (!value) return 0;
  const ts = Date.parse(value);
  return Number.isFinite(ts) ? ts : 0;
}

function pickFreshness(
  cursors: SyncCursor[],
  domain: DataFreshnessDomain,
): DataFreshnessItem {
  const cfg = DOMAINS[domain];
  const matched = cursors
    .filter((cursor) => {
      const hay =
        `${cursor.domain ?? ""} ${cursor.cursor_key ?? ""}`.toLowerCase();
      return cfg.match.some((needle) => hay.includes(needle));
    })
    .sort((a, b) => toTs(b.last_synced_at) - toTs(a.last_synced_at));

  const best = matched[0];
  return {
    label: cfg.label,
    lastSyncedAt: best?.last_synced_at ?? null,
    status: best?.status ?? null,
    source: best
      ? [best.domain, best.cursor_key].filter(Boolean).join(" / ")
      : null,
  };
}

function tone(item: DataFreshnessItem): string {
  const status = (item.status ?? "").toLowerCase();
  if (!item.lastSyncedAt)
    return "border-border/80 bg-muted/35 text-muted-foreground";
  if (status.includes("error") || status.includes("fail"))
    return "border-red-500/35 bg-red-500/10 text-red-700";
  const ageHours = (Date.now() - toTs(item.lastSyncedAt)) / 3_600_000;
  if (ageHours > 24)
    return "border-amber-500/40 bg-amber-500/10 text-amber-800";
  return "border-emerald-500/35 bg-emerald-500/10 text-emerald-700";
}

function statusLabel(status: string | null | undefined): string {
  const key = (status ?? "").toLowerCase();
  if (!key) return "статус неизвестен";
  if (key === "ok" || key === "success" || key === "done") return "готово";
  if (key === "running" || key === "in_progress" || key === "queued")
    return "обновляется";
  if (key.includes("error") || key.includes("fail")) return "ошибка";
  return key.replaceAll("_", " ");
}

export function DataFreshnessStrip() {
  const { activeId } = useAccounts();
  const query = useQuery({
    queryKey: ["owner-data-freshness", activeId],
    enabled: !!activeId,
    queryFn: () =>
      api(API_ENDPOINTS.sync.cursors, {
        query: { account_id: activeId, limit: 200 },
      }),
    staleTime: 60_000,
  });

  const freshness = useMemo(() => {
    const cursors = unwrapCursors(query.data);
    return (Object.keys(DOMAINS) as DataFreshnessDomain[]).map((domain) =>
      pickFreshness(cursors, domain),
    );
  }, [query.data]);

  if (!activeId) return null;

  return (
    <div className="border-b border-border/60 bg-background/80 px-3 py-2 sm:px-5">
      <div className="flex items-center gap-2 overflow-x-auto text-xs [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
        <span className="inline-flex h-7 items-center gap-1.5 rounded-lg border border-border/70 bg-card px-2.5 font-medium text-muted-foreground shadow-sm shadow-black/[0.015]">
          <DatabaseZap className="h-3.5 w-3.5" />
          Данные
        </span>
        {freshness.map((item) => (
          <Badge
            key={item.label}
            variant="outline"
            className={cn(
              "h-7 shrink-0 gap-1 rounded-lg px-2 font-normal",
              tone(item),
            )}
            title={
              item.source
                ? `${item.source}: ${statusLabel(item.status)}`
                : "Источник синхронизации не найден"
            }
          >
            <span className="font-medium">{item.label}</span>
            <span>{formatSyncTime(item.lastSyncedAt)}</span>
          </Badge>
        ))}
      </div>
    </div>
  );
}
