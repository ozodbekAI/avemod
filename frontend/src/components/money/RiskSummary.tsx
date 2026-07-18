import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { AlertTriangle } from "lucide-react";
import { cn } from "@/lib/utils";
import type { MRisk } from "@/lib/api";
import { PRIORITY_COPY } from "@/lib/copy";

const TONE: Record<string, string> = {
  danger:  "border-destructive/30 bg-destructive/5",
  warning: "border-warning/30 bg-warning/5",
  info:    "border-primary/30 bg-primary/5",
  muted:   "border-muted bg-muted/30",
};
const BADGE_TONE: Record<string, string> = {
  danger:  "bg-destructive/15 text-destructive border-destructive/30",
  warning: "bg-warning/15 text-warning border-warning/30",
  info:    "bg-primary/10 text-primary border-primary/30",
  muted:   "bg-muted text-muted-foreground border-border",
};

export function RiskSummary({ criticalCount, risks }: { criticalCount: number; risks: MRisk[] }) {
  if (!risks.length) {
    return (
      <Card><CardContent className="p-4 text-sm text-muted-foreground">Критических рисков нет.</CardContent></Card>
    );
  }
  return (
    <div className="space-y-2">
      <div className="text-xs text-muted-foreground">Критических рисков: <span className="font-semibold text-destructive">{criticalCount}</span></div>
      {risks.map((r) => {
        const prio = PRIORITY_COPY[r.priority || "medium"] ?? PRIORITY_COPY.medium;
        return (
          <Card key={r.code} className={cn("border-l-4", TONE[prio.tone])}>
            <CardContent className="p-4 space-y-2">
              <div className="flex items-start gap-2">
                <AlertTriangle className="h-4 w-4 mt-0.5 text-destructive shrink-0" />
                <div className="flex-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <Badge variant="outline" className={cn("text-[10px] uppercase border", BADGE_TONE[prio.tone])}>{prio.label}</Badge>
                    <span className="text-sm font-semibold">{r.title}</span>
                  </div>
                  {r.business_impact && <div className="text-sm text-muted-foreground mt-1">{r.business_impact}</div>}
                </div>
              </div>
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}
