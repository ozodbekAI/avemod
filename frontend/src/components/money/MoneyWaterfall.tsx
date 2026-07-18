// Prompt 3 (Etap 3): Money waterfall.
// Revenue → -COGS → -Direct WB → -Ads → = Card-level profit
//          → -Unallocated → = Owner-level estimated profit

import { Card, CardContent } from "@/components/ui/card";
import { ArrowDown, Equal } from "lucide-react";
import { formatMoney } from "@/lib/format";
import { cn } from "@/lib/utils";

export interface MoneyWaterfallProps {
  revenue: number | null;
  cogs: number | null;
  wbExpenses: number | null;
  adsSpend: number | null;
  cardLevelProfit: number | null;
  unallocated: number | null;
  ownerProfit: number | null;
  ownerProfitEstimated?: boolean;
}

interface Row {
  kind: "base" | "neg" | "subtotal" | "total";
  label: string;
  value: number | null;
  hint?: string;
  estimated?: boolean;
}

export function MoneyWaterfall(p: MoneyWaterfallProps) {
  const rows: Row[] = [
    { kind: "base",     label: "Выручка",                     value: p.revenue },
    { kind: "neg",      label: "− Себестоимость (COGS)",       value: neg(p.cogs) },
    { kind: "neg",      label: "− Удержания WB",               value: neg(p.wbExpenses) },
    { kind: "neg",      label: "− Реклама",                    value: neg(p.adsSpend) },
    { kind: "subtotal", label: "= Прибыль на уровне карточек",  value: p.cardLevelProfit, hint: "Card-level profit: до общих расходов аккаунта" },
    { kind: "neg",      label: "− Нераспределённые расходы",    value: neg(p.unallocated) },
    { kind: "total",    label: "= Прибыль владельца (оценка)",  value: p.ownerProfit, estimated: p.ownerProfitEstimated },
  ];

  return (
    <Card>
      <CardContent className="p-4 space-y-1.5">
        {rows.map((r, i) => (
          <Row key={i} row={r} />
        ))}
      </CardContent>
    </Card>
  );
}

function Row({ row }: { row: Row }) {
  const sign = row.value != null && row.value < 0 ? "neg" : row.value != null && row.value > 0 ? "pos" : "zero";
  const isSub = row.kind === "subtotal";
  const isTot = row.kind === "total";
  return (
    <div
      className={cn(
        "flex items-center justify-between gap-3 px-3 py-2 rounded-md text-sm tabular-nums",
        isSub && "bg-muted/50 font-medium border-t",
        isTot && "bg-primary/10 font-semibold border-t border-primary/30",
        !isSub && !isTot && "hover:bg-muted/30",
      )}
    >
      <div className="flex items-center gap-2 min-w-0">
        {isSub ? <Equal className="h-3.5 w-3.5 text-muted-foreground shrink-0" /> :
         isTot ? <Equal className="h-3.5 w-3.5 text-primary shrink-0" /> :
         row.kind === "neg" ? <ArrowDown className="h-3.5 w-3.5 text-destructive shrink-0" /> :
         null}
        <span className="truncate">{row.label}</span>
        {row.estimated && (
          <span className="text-[10px] font-medium uppercase tracking-wide text-warning border border-warning/40 bg-warning/10 px-1.5 py-0.5 rounded">
            оценка
          </span>
        )}
      </div>
      <div
        className={cn(
          "shrink-0",
          isTot && (sign === "neg" ? "text-destructive" : sign === "pos" ? "text-success" : ""),
          !isTot && row.kind === "neg" && "text-destructive",
        )}
      >
        {formatMoney(row.value)}
      </div>
    </div>
  );
}

function neg(v: number | null | undefined): number | null {
  if (v == null) return null;
  return -Math.abs(v);
}
