import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { Info } from "lucide-react";
import { cn } from "@/lib/utils";
import { humanizeBlockedReason } from "@/lib/copy";

interface NullValueProps {
  reason?: string | null;
  label?: string;
  className?: string;
}

export function NullValue({ reason, label = "Нет данных", className }: NullValueProps) {
  const content = (
    <span className={cn("inline-flex items-center gap-1 text-muted-foreground italic", className)}>
      {label}
      {reason && <Info className="h-3 w-3 opacity-60" />}
    </span>
  );
  if (!reason) return content;
  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild><span>{content}</span></TooltipTrigger>
        <TooltipContent className="max-w-xs text-xs">
          <span className="font-medium">Причина: </span>{humanizeBlockedReason(reason)}
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}
