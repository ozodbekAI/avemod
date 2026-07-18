import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { RefreshCw } from "lucide-react";
import { DataTrustBadge } from "./DataTrustBadge";
import type { DataTrustState, Confidence } from "@/lib/copy";
import { formatDateTime } from "@/lib/format";

export interface DateRange { from: string; to: string }

export interface MoneyPageHeaderProps {
  title: string;
  subtitle?: string;
  range: DateRange;
  onRangeChange: (r: DateRange) => void;
  trustState?: DataTrustState;
  trustConfidence?: Confidence | null;
  blockedReasons?: string[];
  lastUpdated?: string | null;
  onRefresh?: () => void;
  isRefreshing?: boolean;
  rightSlot?: React.ReactNode;
}

const PRESETS = [
  { id: "7d",  label: "7 дней",  days: 7 },
  { id: "30d", label: "30 дней", days: 30 },
  { id: "90d", label: "90 дней", days: 90 },
] as const;

export function rangeFor(days: number): DateRange {
  const to = new Date();
  const from = new Date();
  from.setDate(from.getDate() - days + 1);
  const fmt = (d: Date) => d.toISOString().slice(0, 10);
  return { from: fmt(from), to: fmt(to) };
}

export function MoneyPageHeader(props: MoneyPageHeaderProps) {
  const { title, subtitle, range, onRangeChange, trustState, trustConfidence, blockedReasons, lastUpdated, onRefresh, isRefreshing, rightSlot } = props;
  const [preset, setPreset] = useState<string>("custom");

  useEffect(() => {
    for (const p of PRESETS) {
      if (range.from === rangeFor(p.days).from && range.to === rangeFor(p.days).to) {
        setPreset(p.id); return;
      }
    }
    setPreset("custom");
  }, [range.from, range.to]);

  return (
    <div className="border-b bg-card/40">
      <div className="px-6 py-4 space-y-3">
        <div className="flex items-start justify-between gap-3 flex-wrap">
          <div className="min-w-0">
            <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
            {subtitle && <p className="text-sm text-muted-foreground mt-0.5">{subtitle}</p>}
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            {trustState && <DataTrustBadge state={trustState} confidence={trustConfidence ?? undefined} blockedReasons={blockedReasons} />}
            {onRefresh && (
              <Button variant="outline" size="sm" onClick={onRefresh} disabled={isRefreshing}>
                <RefreshCw className={`h-3.5 w-3.5 mr-1.5 ${isRefreshing ? "animate-spin" : ""}`} />
                Обновить
              </Button>
            )}
            {rightSlot}
          </div>
        </div>

        <div className="flex items-end gap-3 flex-wrap">
          <div className="flex items-center gap-1">
            {PRESETS.map((p) => (
              <Button
                key={p.id}
                size="sm"
                variant={preset === p.id ? "default" : "outline"}
                className="h-8"
                onClick={() => onRangeChange(rangeFor(p.days))}
              >
                {p.label}
              </Button>
            ))}
            <Select value="custom" onValueChange={() => {}}>
              <SelectTrigger className="h-8 w-[110px] hidden">
                <SelectValue />
              </SelectTrigger>
              <SelectContent><SelectItem value="custom">Произвольный</SelectItem></SelectContent>
            </Select>
          </div>
          <div className="flex items-end gap-2">
            <div className="space-y-1">
              <Label className="text-[10px] uppercase tracking-wide text-muted-foreground">С</Label>
              <Input type="date" value={range.from} onChange={(e) => onRangeChange({ ...range, from: e.target.value })} className="h-8 w-[150px]" />
            </div>
            <div className="space-y-1">
              <Label className="text-[10px] uppercase tracking-wide text-muted-foreground">По</Label>
              <Input type="date" value={range.to} onChange={(e) => onRangeChange({ ...range, to: e.target.value })} className="h-8 w-[150px]" />
            </div>
          </div>
          {lastUpdated && (
            <div className="text-xs text-muted-foreground ml-auto">
              Последнее обновление: {formatDateTime(lastUpdated)}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
