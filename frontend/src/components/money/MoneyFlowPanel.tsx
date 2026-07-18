import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { TrendingUp, TrendingDown, Wallet, Info } from "lucide-react";
import { cn } from "@/lib/utils";
import type { MMoneyFlowItem } from "@/lib/api";
import { formatMoney } from "@/lib/format";
import { humanizeBlockedReason, CONFIDENCE_COPY } from "@/lib/copy";

interface Props {
  incoming: MMoneyFlowItem[];
  outgoing: MMoneyFlowItem[];
  cashAndStock: MMoneyFlowItem[];
}

const CONF_TONE: Record<string, string> = {
  success: "bg-success/15 text-success border-success/30",
  warning: "bg-warning/15 text-warning border-warning/30",
  danger:  "bg-destructive/15 text-destructive border-destructive/30",
};

function FlowRow({ item }: { item: MMoneyFlowItem }) {
  const conf = CONFIDENCE_COPY[item.confidence] ?? CONFIDENCE_COPY.medium;
  const hasReason = !!item.reason;
  return (
    <li className="flex items-start justify-between gap-3 py-2 border-b last:border-b-0">
      <div className="flex-1 min-w-0">
        <div className="text-sm font-medium truncate">{item.label}</div>
        <div className="mt-1 flex items-center gap-1.5 flex-wrap">
          <Badge variant="outline" className={cn("text-[10px] uppercase border", CONF_TONE[conf.tone])}>
            {conf.label}
          </Badge>
          {hasReason && (
            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger asChild>
                  <span className="inline-flex items-center gap-0.5 text-[10px] text-muted-foreground italic cursor-help">
                    <Info className="h-3 w-3" /> {humanizeBlockedReason(item.reason!)}
                  </span>
                </TooltipTrigger>
                <TooltipContent className="max-w-xs text-xs">{humanizeBlockedReason(item.reason!)}</TooltipContent>
              </Tooltip>
            </TooltipProvider>
          )}
        </div>
      </div>
      <div className="text-sm font-semibold tabular-nums whitespace-nowrap">
        {item.amount === 0 && hasReason ? (
          <span className="italic text-muted-foreground">Не посчитано</span>
        ) : (
          formatMoney(item.amount)
        )}
      </div>
    </li>
  );
}

function Column({ title, icon: Icon, tone, items }: { title: string; icon: typeof TrendingUp; tone: "success" | "danger" | "info"; items: MMoneyFlowItem[] }) {
  const total = items.reduce((s, x) => s + (Number.isFinite(x.amount) ? x.amount : 0), 0);
  const TONE: Record<string, string> = {
    success: "border-l-success",
    danger:  "border-l-destructive",
    info:    "border-l-primary",
  };
  return (
    <Card className={cn("border-l-4", TONE[tone])}>
      <CardContent className="p-4">
        <div className="flex items-center gap-2 mb-2">
          <Icon className="h-4 w-4" />
          <h3 className="text-sm font-semibold">{title}</h3>
          <span className="ml-auto text-xs tabular-nums text-muted-foreground">Итого: {formatMoney(total)}</span>
        </div>
        {items.length === 0 ? (
          <div className="text-xs text-muted-foreground py-4 text-center">Нет данных</div>
        ) : (
          <ul>
            {items.map((i, idx) => <FlowRow key={`${i.code}-${idx}`} item={i} />)}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

export function MoneyFlowPanel({ incoming, outgoing, cashAndStock }: Props) {
  return (
    <div className="grid gap-3 md:grid-cols-3">
      <Column title="Поступления" icon={TrendingUp} tone="success" items={incoming} />
      <Column title="Расходы" icon={TrendingDown} tone="danger"  items={outgoing} />
      <Column title="Где деньги сейчас" icon={Wallet} tone="info" items={cashAndStock} />
    </div>
  );
}
