import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { Info } from "lucide-react";
import { cn } from "@/lib/utils";
import { humanizeBlockedReason } from "@/lib/copy";
import { formatMoney, formatPercent, formatNumber } from "@/lib/format";

type Format = "money" | "percent" | "number";

interface Props {
  value: number | null | undefined;
  reason?: string | null;
  format?: Format;
  className?: string;
  /**
   * If true (default), a 0 with a non-empty reason is shown as «Hisoblanmagan».
   * Set false for fields where 0 is a real business value (e.g. ad_spend after allocation).
   */
  treatZeroWithReasonAsNotComputable?: boolean;
  fallbackLabel?: string;
}

function fmt(v: number, f: Format) {
  if (f === "percent") return formatPercent(v);
  if (f === "number")  return formatNumber(v);
  return formatMoney(v);
}

export function NotComputableValue({
  value, reason, format = "money", className,
  treatZeroWithReasonAsNotComputable = true,
  fallbackLabel = "Не посчитано",
}: Props) {
  const isNull = value === null || value === undefined || Number.isNaN(value as number);
  const isZeroWithReason = !isNull && (value as number) === 0 && !!reason && treatZeroWithReasonAsNotComputable;

  if (!isNull && !isZeroWithReason) {
    return <span className={cn("tabular-nums", className)}>{fmt(value as number, format)}</span>;
  }

  const tipText = reason ? humanizeBlockedReason(reason) : "Эндпоинт пока не вернул значение";
  const label = isZeroWithReason ? fallbackLabel : (reason ? "Не посчитано" : "Нет данных");

  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <span className={cn("inline-flex items-center gap-1 italic text-muted-foreground", className)}>
            {label}<Info className="h-3 w-3 opacity-60" />
          </span>
        </TooltipTrigger>
        <TooltipContent className="max-w-xs text-xs">
          <span className="font-medium">Почему: </span>{tipText}
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}
