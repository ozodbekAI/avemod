import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Badge } from "@/components/ui/badge";
import {
  formatBreakdownPeriod,
  formatBreakdownValue,
  formatSyncTime,
  TRUST_LABEL,
  type MetricBreakdown,
} from "@/lib/owner-ux";
import { cn } from "@/lib/utils";

const OP_CLASS: Record<string, string> = {
  plus: "text-emerald-700 dark:text-emerald-300",
  minus: "text-red-700 dark:text-red-300",
  equals: "text-foreground font-semibold",
  info: "text-muted-foreground",
};

const OP_LABEL: Record<string, string> = {
  plus: "+",
  minus: "-",
  equals: "=",
  info: "",
};

export function MetricBreakdownDialog({
  breakdown,
  open,
  onOpenChange,
}: {
  breakdown: MetricBreakdown | null | undefined;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  if (!breakdown) return null;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <div className="flex flex-wrap items-center gap-2">
            <DialogTitle>{breakdown.title}</DialogTitle>
            <Badge variant="outline">{TRUST_LABEL[breakdown.trustState]}</Badge>
          </div>
          <DialogDescription>
            Формула, источники и доверие к метрике. Технические детали скрыты внутри блока источников.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="rounded-md border bg-muted/30 p-3">
            <div className="text-xs text-muted-foreground">Итог</div>
            <div className="text-2xl font-semibold">{formatBreakdownValue(breakdown.value)}</div>
          </div>

          <div>
            <div className="text-xs font-medium text-muted-foreground mb-2">Формула</div>
            <div className="rounded-md border p-3 text-sm">{breakdown.formula}</div>
          </div>

          <div className="rounded-md border divide-y">
            {breakdown.rows.map((row, idx) => {
              const op = row.operation ?? "info";
              return (
                <div key={`${row.label}-${idx}`} className="grid grid-cols-[28px_1fr_auto] gap-3 px-3 py-2 text-sm">
                  <div className={cn("tabular-nums", OP_CLASS[op])}>{OP_LABEL[op]}</div>
                  <div>
                    <div>{row.label}</div>
                    {row.note ? <div className="text-xs text-muted-foreground">{row.note}</div> : null}
                  </div>
                  <div className={cn("text-right tabular-nums", OP_CLASS[op])}>
                    {formatBreakdownValue(row.value)}
                  </div>
                </div>
              );
            })}
          </div>

          <div className="grid gap-3 md:grid-cols-3 text-xs">
            <div className="rounded-md border p-3">
              <div className="text-muted-foreground">Период</div>
              <div className="font-medium">{formatBreakdownPeriod(breakdown.period)}</div>
            </div>
            <div className="rounded-md border p-3">
              <div className="text-muted-foreground">Последняя синхронизация</div>
              <div className="font-medium">{formatSyncTime(breakdown.lastSyncedAt)}</div>
            </div>
            <div className="rounded-md border p-3">
              <div className="text-muted-foreground">Откуда взяты данные</div>
              <div className="font-medium">{breakdown.sources.join(", ")}</div>
            </div>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
