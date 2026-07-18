// Small UI helpers to label data granularity (Article/NM vs SKU).
import { Badge } from "@/components/ui/badge";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Layers, Boxes, Info } from "lucide-react";

export type GranularityRow = {
  sku_id?: number | string | null;
  nm_id?: number | string | null;
  barcode?: string | null;
  size?: string | null;
  chrt_id?: number | string | null;
};

export type Granularity = "sku" | "nm" | "unknown";

export function getGranularity(r: GranularityRow): Granularity {
  if (r.sku_id != null && String(r.sku_id) !== "") return "sku";
  if (r.barcode || r.chrt_id || r.size) return "sku";
  if (r.nm_id != null && String(r.nm_id) !== "") return "nm";
  return "unknown";
}

export function GranularityBadge({ row, className = "" }: { row: GranularityRow; className?: string }) {
  const g = getGranularity(row);
  if (g === "sku") {
    return (
      <Badge variant="outline" className={`text-[10px] uppercase bg-primary/10 text-primary border-primary/30 ${className}`}>
        <Boxes className="h-3 w-3 mr-1" /> По размеру
      </Badge>
    );
  }
  if (g === "nm") {
    return (
      <Badge variant="outline" className={`text-[10px] uppercase bg-muted text-muted-foreground border-border ${className}`}>
        <Layers className="h-3 w-3 mr-1" /> По карточке
      </Badge>
    );
  }
  return (
    <Badge variant="outline" className={`text-[10px] uppercase border-border text-muted-foreground ${className}`}>
      —
    </Badge>
  );
}

/** Notice shown when WB cluster stats are empty (not an error — just no data). */
export function ClusterEmptyNotice({
  state, rows, className = "",
}: { state?: string | null; rows?: number | null; className?: string }) {
  const empty = (rows ?? null) === 0 || (state ?? "").toLowerCase() === "wb_no_data";
  if (!empty) return null;
  return (
    <Alert className={`border-muted bg-muted/30 ${className}`}>
      <Info className="h-4 w-4" />
      <AlertTitle>Кластерная статистика недоступна</AlertTitle>
      <AlertDescription className="text-xs">
        Кластерная статистика недоступна: WB вернул пустые данные. Реклама и аналитика по карточкам продолжают работать.
      </AlertDescription>
    </Alert>
  );
}

/** Per-row allocation status badge: allocated / nm_level / unallocated. */
export function AllocationStatusBadge({ status, className = "" }: { status?: string | null; className?: string }) {
  if (!status) return null;
  const s = status.toLowerCase();
  const cfg =
    s === "allocated" || s === "linked" || s === "matched"
      ? { label: "Привязано", cls: "bg-success/10 text-success border-success/30" }
    : s === "nm_level"
      ? { label: "По карточке", cls: "bg-muted text-muted-foreground border-border" }
    : s === "unallocated"
      ? { label: "Не привязано", cls: "bg-warning/10 text-warning border-warning/30" }
    : s === "overallocated"
      ? { label: "Переаллокация", cls: "bg-destructive/10 text-destructive border-destructive/30" }
    : { label: s, cls: "bg-muted text-muted-foreground border-border" };
  return (
    <Badge variant="outline" className={`text-[10px] uppercase ${cfg.cls} ${className}`}>
      {cfg.label}
    </Badge>
  );
}
