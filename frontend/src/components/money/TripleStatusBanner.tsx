// Prompt 1 (Etap 3): three separate statuses at the top of /money.
// Never collapses into one "trusted" pill.

import { CheckCircle2, AlertTriangle, ShieldAlert, HelpCircle } from "lucide-react";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import type { ThreeStatuses, TriStatus } from "@/lib/trust";

const TONE: Record<TriStatus, { wrap: string; Icon: typeof CheckCircle2 }> = {
  ok:      { wrap: "bg-success/10 text-success border-success/30",            Icon: CheckCircle2 },
  warn:    { wrap: "bg-warning/10 text-warning border-warning/30",            Icon: AlertTriangle },
  bad:     { wrap: "bg-destructive/10 text-destructive border-destructive/30", Icon: ShieldAlert },
  unknown: { wrap: "bg-muted text-muted-foreground border-border",             Icon: HelpCircle },
};

export function TripleStatusBanner({ three }: { three: ThreeStatuses }) {
  return (
    <div className="grid gap-2 md:grid-cols-3">
      <Pill label="Бизнес-данные" value={three.business} />
      <Pill label="Финансы" value={three.finance} />
      <Pill label="Себестоимость" value={three.cost} />
    </div>
  );
}

function Pill({ label, value }: { label: string; value: ThreeStatuses["business"] }) {
  const tone = TONE[value.status] ?? TONE.unknown;
  const Icon = tone.Icon;

  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <div className={cn("flex items-center gap-2 rounded-md border px-3 py-2 text-sm cursor-help", tone.wrap)}>
            <Icon className="h-4 w-4 shrink-0" />
            <div className="min-w-0 flex-1">
              <div className="text-[10px] uppercase tracking-wider opacity-70 font-medium">{label}</div>
              <div className="font-medium truncate">{value.label}</div>
            </div>
          </div>
        </TooltipTrigger>
        <TooltipContent className="max-w-xs text-xs">{value.hint}</TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}
