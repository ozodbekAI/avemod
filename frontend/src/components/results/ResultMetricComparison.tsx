// @ts-nocheck
import { cn } from "@/lib/utils";
import type { MetricRow } from "@/lib/results-metric-templates";

export function ResultMetricComparison({
  rows,
  className,
}: {
  rows: MetricRow[];
  className?: string;
}) {
  const allMissing = rows.every((r) => r.state === "missing");
  if (allMissing) {
    return (
      <div className="rounded-md border bg-muted/20 p-3 text-xs text-muted-foreground">
        Недостаточно данных для сравнения
      </div>
    );
  }
  return (
    <div className={cn("rounded-md border overflow-hidden", className)}>
      <table className="w-full text-xs">
        <thead className="bg-muted/40 text-[10px] uppercase tracking-wide text-muted-foreground">
          <tr>
            <th className="text-left px-2 py-1.5 font-medium">Показатель</th>
            <th className="text-right px-2 py-1.5 font-medium">До</th>
            <th className="text-right px-2 py-1.5 font-medium">После</th>
            <th className="text-right px-2 py-1.5 font-medium">Изменение</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.label} className="border-t">
              <td className="px-2 py-1.5 text-muted-foreground">{r.label}</td>
              <td className="px-2 py-1.5 text-right tabular-nums">{r.before}</td>
              <td className="px-2 py-1.5 text-right tabular-nums">{r.after}</td>
              <td
                className={cn(
                  "px-2 py-1.5 text-right tabular-nums font-medium",
                  r.state === "improved" && "text-success",
                  r.state === "worse" && "text-destructive",
                  r.state === "neutral" && "text-muted-foreground",
                  r.state === "missing" && "text-muted-foreground",
                )}
              >
                {r.state === "missing"
                  ? "—"
                  : r.deltaLabel ?? (r.state === "neutral" ? "без изм." : "—")}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
