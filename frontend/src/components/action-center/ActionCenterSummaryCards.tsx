import type { ReactNode } from "react";
import {
  AlertTriangle,
  CalendarClock,
  ListChecks,
  TimerReset,
  TrendingUp,
} from "lucide-react";

import { Card, CardContent } from "@/components/ui/card";

export type ActionCenterDeskStats = {
  urgent: number;
  inProgress: number;
  recheck: number;
  overdue: number;
  result: number;
};

function SummaryCard({
  title,
  value,
  detail,
  tone = "border-border bg-card",
  icon,
}: {
  title: string;
  value: number | string;
  detail: string;
  tone?: string;
  icon?: ReactNode;
}) {
  return (
    <Card className={tone}>
      <CardContent className="p-4">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <div className="text-xs font-medium text-muted-foreground">
              {title}
            </div>
            <div className="mt-2 text-2xl font-semibold tabular-nums">
              {value}
            </div>
          </div>
          {icon ? <div className="text-muted-foreground">{icon}</div> : null}
        </div>
        <div className="mt-2 text-xs text-muted-foreground">{detail}</div>
      </CardContent>
    </Card>
  );
}

export function ActionCenterSummaryCards({
  stats,
}: {
  stats: ActionCenterDeskStats;
}) {
  return (
    <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
      <SummaryCard
        title="Срочно"
        value={stats.urgent}
        detail="P0/P1 или высокий риск"
        tone="border-destructive/25 bg-destructive/5"
        icon={<AlertTriangle className="h-4 w-4" />}
      />
      <SummaryCard
        title="В работе"
        value={stats.inProgress}
        detail="Есть активный исполнительный статус"
        tone="border-primary/25 bg-primary/5"
        icon={<ListChecks className="h-4 w-4" />}
      />
      <SummaryCard
        title="Ждёт перепроверки"
        value={stats.recheck}
        detail="Действие сделано, результата ещё нет"
        tone="border-sky-500/25 bg-sky-500/5"
        icon={<TimerReset className="h-4 w-4" />}
      />
      <SummaryCard
        title="Просрочено"
        value={stats.overdue}
        detail="Срок прошёл, задача не закрыта"
        tone="border-amber-500/35 bg-amber-500/10"
        icon={<CalendarClock className="h-4 w-4" />}
      />
      <SummaryCard
        title="Результат есть"
        value={stats.result}
        detail="Есть улучшение, ухудшение или нейтральный итог"
        tone="border-success/25 bg-success/5"
        icon={<TrendingUp className="h-4 w-4" />}
      />
    </div>
  );
}
