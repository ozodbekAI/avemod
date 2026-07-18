import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { CONFIDENCE_COPY, type Confidence } from "@/lib/copy";

const TONE: Record<string, string> = {
  success: "bg-success/15 text-success border-success/30",
  warning: "bg-warning/15 text-warning border-warning/30",
  danger:  "bg-destructive/15 text-destructive border-destructive/30",
};

export function ConfidenceBadge({ value, className }: { value?: Confidence | string | null; className?: string }) {
  if (!value) return null;
  const cfg = CONFIDENCE_COPY[value as Confidence];
  if (!cfg) return null;
  return (
    <Badge variant="outline" className={cn("text-[10px] uppercase border", TONE[cfg.tone], className)}>
      {cfg.label}
    </Badge>
  );
}
