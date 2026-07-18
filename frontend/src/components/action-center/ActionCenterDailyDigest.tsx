import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";

export type ActionCenterDailyDigestData = {
  newToday: number;
  dueToday: number;
  overdue: number;
  recheckCompleted: number;
  resultImproved: number;
  resultWorse: number;
};

export type ActionCenterWeeklySummaryData = {
  closedTasks: number;
  reopenedTasks: number;
  confirmedMeasuredOutcomes: number;
  estimatedOpportunitiesHandled: number;
};

export function ActionCenterDailyDigest({
  dailyDigest,
  weeklySummary,
}: {
  dailyDigest: ActionCenterDailyDigestData;
  weeklySummary: ActionCenterWeeklySummaryData;
}) {
  return (
    <div className="grid gap-3 xl:grid-cols-[1.35fr_1fr]">
      <Card>
        <CardContent className="p-4 space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <div className="text-sm font-semibold">Дайджест на сегодня</div>
              <div className="text-xs text-muted-foreground">
                Что появилось, что горит по срокам и какие перепроверки уже
                дали сигнал.
              </div>
            </div>
            <Badge variant="outline" className="text-[10px]">
              Уведомления в Центре действий
            </Badge>
          </div>
          <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
            {[
              ["Новые сегодня", dailyDigest.newToday, "Свежие задачи в очереди"],
              ["Срок сегодня", dailyDigest.dueToday, "Нужно закрыть сегодня"],
              ["Просрочено", dailyDigest.overdue, "Требует внимания менеджера"],
              ["Перепроверка завершена", dailyDigest.recheckCompleted, "Есть новый статус проверки"],
              ["Улучшилось", dailyDigest.resultImproved, "Есть измеренный положительный сигнал"],
              ["Стало хуже", dailyDigest.resultWorse, "Нужно разобрать причину"],
            ].map(([label, value, detail]) => (
              <div key={label} className="rounded-md border p-3">
                <div className="text-xs text-muted-foreground">{label}</div>
                <div className="mt-1 text-xl font-semibold tabular-nums">
                  {value}
                </div>
                <div className="mt-1 text-[11px] text-muted-foreground">
                  {detail}
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="p-4 space-y-3">
          <div>
            <div className="text-sm font-semibold">Итоги недели</div>
            <div className="text-xs text-muted-foreground">
              Прогресс без превращения оценочного риска в денежный результат.
            </div>
          </div>
          <div className="grid gap-2 sm:grid-cols-2">
            {[
              ["Закрыто задач", weeklySummary.closedTasks],
              ["Переоткрыто", weeklySummary.reopenedTasks],
              ["Измеренных исходов", weeklySummary.confirmedMeasuredOutcomes],
              ["Возможностей обработано", weeklySummary.estimatedOpportunitiesHandled],
            ].map(([label, value]) => (
              <div key={label} className="rounded-md border p-3">
                <div className="text-xs text-muted-foreground">{label}</div>
                <div className="mt-1 text-xl font-semibold tabular-nums">
                  {value}
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
