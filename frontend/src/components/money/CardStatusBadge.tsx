import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { CARD_STATUS_COPY, type CardStatus } from "@/lib/copy";

const TONE: Record<"success" | "warning" | "danger" | "info" | "muted", string> = {
  success: "bg-success/15 text-success border-success/30",
  warning: "bg-warning/15 text-warning border-warning/30",
  danger:  "bg-destructive/15 text-destructive border-destructive/30",
  info:    "bg-primary/10 text-primary border-primary/30",
  muted:   "bg-muted text-muted-foreground border-border",
};

export function CardStatusBadge({ status, className }: { status: CardStatus | string; className?: string }) {
  const key = (status as CardStatus) in CARD_STATUS_COPY ? (status as CardStatus) : "watch";
  const copy = CARD_STATUS_COPY[key];
  return (
    <Badge variant="outline" className={cn("border font-medium", TONE[copy.tone], className)}>
      {copy.title}
    </Badge>
  );
}
