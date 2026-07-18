import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Link } from "@tanstack/react-router";
import { ArrowRight, TrendingUp } from "lucide-react";
import { cn } from "@/lib/utils";
import { PRIORITY_COPY, humanizeAction } from "@/lib/copy";
import { formatMoney } from "@/lib/format";
import { PriceSafetyMissingNotice, priceSafetyNeededFromText } from "@/components/PriceSafetyPanel";

export interface NextActionCardProps {
  priority: "critical" | "high" | "medium" | "low";
  actionType?: string;
  title?: string;
  whatToDo?: string;
  why?: string;
  expectedEffectAmount?: number | null;
  confidence?: string;
  isDataFix?: boolean;
  linkLabel?: string;
  linkHref?: string;
  className?: string;
}

const PRIO_BAR: Record<string, string> = {
  critical: "bg-destructive",
  high:     "bg-warning",
  medium:   "bg-primary",
  low:      "bg-muted-foreground",
};

const PRIO_BADGE: Record<string, string> = {
  critical: "bg-destructive/15 text-destructive border-destructive/30",
  high:     "bg-warning/15 text-warning border-warning/30",
  medium:   "bg-primary/10 text-primary border-primary/30",
  low:      "bg-muted text-muted-foreground border-border",
};

export function NextActionCard({
  priority, actionType, title, whatToDo, why, expectedEffectAmount,
  isDataFix, linkLabel, linkHref, className,
}: NextActionCardProps) {
  const prioCopy = PRIORITY_COPY[priority] ?? PRIORITY_COPY.medium;
  const displayTitle = title || (actionType ? humanizeAction(actionType) : "Действие");
  const needsPriceSafety = priceSafetyNeededFromText(actionType, title, whatToDo, why);

  return (
    <Card className={cn("relative overflow-hidden", className)}>
      <div className={cn("absolute left-0 top-0 bottom-0 w-1", PRIO_BAR[priority])} />
      <CardContent className="p-4 space-y-3 pl-5">
        <div className="flex items-start justify-between gap-2 flex-wrap">
          <div className="flex items-center gap-2 flex-wrap">
            <Badge variant="outline" className={cn("border text-[10px] uppercase", PRIO_BADGE[priority])}>
              {prioCopy.label}
            </Badge>
            {isDataFix && (
              <Badge variant="outline" className="text-[10px] uppercase border-warning/30 text-warning bg-warning/10">
                Починка данных
              </Badge>
            )}
          </div>
          {expectedEffectAmount != null && (
            <div className="flex items-center gap-1 rounded-md border border-dashed border-amber-500/45 bg-amber-500/10 px-2 py-1 text-xs font-medium text-amber-800 dark:text-amber-200">
              <TrendingUp className="h-3 w-3" /> Оценка эффекта: {formatMoney(expectedEffectAmount)}
            </div>
          )}
        </div>

        {needsPriceSafety ? <PriceSafetyMissingNotice compact /> : null}

        <div>
          <div className="font-medium text-sm leading-snug">{displayTitle}</div>
          {whatToDo && <div className="text-sm text-muted-foreground mt-1">{whatToDo}</div>}
        </div>

        {why && (
          <div className="text-xs text-muted-foreground border-l-2 border-muted pl-2">
            <span className="font-medium">Почему: </span>{why}
          </div>
        )}

        {linkHref && (
          <Button asChild size="sm" variant="outline" className="h-7 text-xs">
            <Link to={linkHref as any}>
              {linkLabel || "Открыть"} <ArrowRight className="h-3 w-3 ml-1" />
            </Link>
          </Button>
        )}
      </CardContent>
    </Card>
  );
}
