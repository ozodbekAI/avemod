import { Badge } from "@/components/ui/badge";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { ShieldCheck, AlertTriangle, ShieldAlert } from "lucide-react";
import { cn } from "@/lib/utils";
import { TRUST_STATE_COPY, humanizeBlockedReason, type DataTrustState, type Confidence } from "@/lib/copy";

export interface DataTrustBadgeProps {
  state: DataTrustState;
  confidence?: Confidence | null;
  blockedReasons?: string[];
  compact?: boolean;
  className?: string;
}

const TONE_CLASS: Record<"success" | "warning" | "danger", string> = {
  success: "bg-success/15 text-success border-success/30",
  warning: "bg-warning/15 text-warning border-warning/30",
  danger:  "bg-destructive/15 text-destructive border-destructive/30",
};

export function DataTrustBadge({ state, confidence, blockedReasons, compact, className }: DataTrustBadgeProps) {
  const copy = TRUST_STATE_COPY[state] ?? TRUST_STATE_COPY.test_only;
  const Icon = state === "trusted" ? ShieldCheck : state === "data_blocked" ? ShieldAlert : AlertTriangle;
  const label = compact ? copy.label : confidence ? `${copy.label} · ${confidenceLabel(confidence)}` : copy.label;
  const reasons = (blockedReasons || []).slice(0, 6);

  const badge = (
    <Badge variant="outline" className={cn("gap-1.5 font-medium border", TONE_CLASS[copy.tone], className)}>
      <Icon className="h-3 w-3" />
      {label}
    </Badge>
  );

  if (!reasons.length) return badge;

  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild><span className="inline-flex">{badge}</span></TooltipTrigger>
        <TooltipContent className="max-w-xs">
          <div className="font-medium mb-1">Что блокирует:</div>
          <ul className="text-xs space-y-0.5">
            {reasons.map((r) => <li key={r}>• {humanizeBlockedReason(r)}</li>)}
          </ul>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}

function confidenceLabel(c: Confidence): string {
  return c === "high" ? "надёжно" : c === "medium" ? "приблизительно" : "низкая";
}
