import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { Info } from "lucide-react";
import { cn } from "@/lib/utils";
import { formatMoney, formatPercent, formatNumber, formatConfidence } from "@/lib/format";
import { NullValue } from "./NullValue";
import type { Confidence } from "@/lib/copy";

export interface MoneyKpiCardProps {
  label: string;
  value: number | null | undefined;
  format: "money" | "percent" | "number";
  confidence?: Confidence | null;
  reason?: string | null;
  badge?: string;
  hint?: string;
  className?: string;
}

const CONF_TONE: Record<Confidence, string> = {
  high:   "bg-success/15 text-success border-success/30",
  medium: "bg-warning/15 text-warning border-warning/30",
  low:    "bg-destructive/15 text-destructive border-destructive/30",
};

export function MoneyKpiCard({ label, value, format, confidence, reason, badge, hint, className }: MoneyKpiCardProps) {
  const isNull = value === null || value === undefined;
  let display: React.ReactNode;
  if (isNull) {
    display = <NullValue reason={reason} className="text-base not-italic" />;
  } else if (format === "money") {
    display = formatMoney(value as number);
  } else if (format === "percent") {
    display = formatPercent(value as number);
  } else {
    display = formatNumber(value as number);
  }

  return (
    <Card className={cn("relative", className)}>
      <CardContent className="p-4 space-y-2">
        <div className="flex items-start justify-between gap-2">
          <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground flex items-center gap-1">
            {label}
            {hint && (
              <TooltipProvider>
                <Tooltip>
                  <TooltipTrigger asChild><Info className="h-3 w-3 opacity-60 cursor-help" /></TooltipTrigger>
                  <TooltipContent className="max-w-xs text-xs">{hint}</TooltipContent>
                </Tooltip>
              </TooltipProvider>
            )}
          </div>
          {badge && <Badge variant="outline" className="text-[10px]">{badge}</Badge>}
        </div>
        <div className="text-2xl font-semibold tabular-nums">{display}</div>
        {confidence && !isNull && (
          <Badge variant="outline" className={cn("text-[10px] border", CONF_TONE[confidence])}>
            {formatConfidence(confidence)}
          </Badge>
        )}
      </CardContent>
    </Card>
  );
}
