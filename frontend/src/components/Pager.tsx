import { Button } from "@/components/ui/button";
import { ChevronLeft, ChevronRight } from "lucide-react";

export function Pager({
  total, limit, offset, onChange,
}: { total: number; limit: number; offset: number; onChange: (offset: number) => void }) {
  const page = Math.floor(offset / limit) + 1;
  const pages = Math.max(1, Math.ceil(total / limit));
  return (
    <div className="flex items-center justify-between gap-3 mt-3 text-sm">
      <div className="text-muted-foreground">
        {total === 0 ? "0" : `${offset + 1}–${Math.min(offset + limit, total)}`} / {total}
      </div>
      <div className="flex items-center gap-1.5">
        <Button variant="outline" size="sm" disabled={offset <= 0} onClick={() => onChange(Math.max(0, offset - limit))}>
          <ChevronLeft className="h-4 w-4" />
        </Button>
        <span className="text-xs text-muted-foreground tabular-nums px-1">Стр. {page} / {pages}</span>
        <Button variant="outline" size="sm" disabled={offset + limit >= total} onClick={() => onChange(offset + limit)}>
          <ChevronRight className="h-4 w-4" />
        </Button>
      </div>
    </div>
  );
}

export function fmtMoney(n: number | null | undefined, currency = "₽"): string {
  if (n == null || isNaN(Number(n))) return "—";
  const v = Number(n);
  return `${v.toLocaleString("ru-RU", { maximumFractionDigits: 2 })} ${currency}`;
}
export function fmtNum(n: number | null | undefined): string {
  if (n == null || isNaN(Number(n))) return "—";
  return Number(n).toLocaleString("ru-RU");
}
export function fmtPct(n: number | null | undefined): string {
  if (n == null) return "—";
  return `${Number(n).toFixed(1)}%`;
}
export function fmtDate(d: string | null | undefined): string {
  if (!d) return "—";
  try { return new Date(d).toLocaleString("ru-RU", { dateStyle: "short", timeStyle: "short" }); }
  catch { return d; }
}
