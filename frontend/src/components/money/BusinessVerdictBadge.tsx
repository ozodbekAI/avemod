import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { CARD_STATUS_COPY } from "@/lib/copy";

const TONE: Record<string, string> = {
  success: "bg-success/15 text-success border-success/30",
  warning: "bg-warning/15 text-warning border-warning/30",
  danger:  "bg-destructive/15 text-destructive border-destructive/30",
  info:    "bg-primary/10 text-primary border-primary/30",
  muted:   "bg-muted text-muted-foreground border-border",
};

export function BusinessVerdictBadge({ status, label, className }: { status: string; label?: string; className?: string }) {
  const cfg = CARD_STATUS_COPY[status] ?? CARD_STATUS_COPY.watch;
  return (
    <Badge variant="outline" className={cn("text-[11px] border", TONE[cfg.tone], className)}>
      {label || cfg.title}
    </Badge>
  );
}
