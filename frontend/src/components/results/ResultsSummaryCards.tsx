// @ts-nocheck
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { formatMoney } from "@/lib/format";
import type {
  ResultOutcomeKey,
  ResultSummaryCounts,
} from "./resultsClassify";

type CardKey = ResultOutcomeKey | "measured";

interface Cfg {
  key: CardKey;
  title: string;
  hint: string;
  tone: string;
}

const CARDS: Cfg[] = [
  {
    key: "pending_data",
    title: "Ждём данных",
    hint: "Задачи выполнены, но свежих данных после действия пока нет.",
    tone: "border-warning/40",
  },
  {
    key: "improved",
    title: "Есть улучшение",
    hint: "По данным после действия метрика улучшилась.",
    tone: "border-success/40",
  },
  {
    key: "worse",
    title: "Стало хуже",
    hint: "По данным после действия ситуация ухудшилась.",
    tone: "border-destructive/40",
  },
  {
    key: "neutral",
    title: "Без изменений",
    hint: "Действие выполнено, метрика существенно не изменилась.",
    tone: "border-border",
  },
  {
    key: "not_enough_data",
    title: "Нет данных",
    hint: "Не удалось собрать сравнение до/после.",
    tone: "border-border",
  },
  {
    key: "measured",
    title: "Измеренный эффект",
    hint: "Только суммы, подтверждённые данными после перепроверки. Не включает ожидаемый эффект.",
    tone: "border-primary/40",
  },
];

export function ResultsSummaryCards({
  counts,
  activeFilter,
  onSelect,
}: {
  counts: ResultSummaryCounts;
  activeFilter?: string | null;
  onSelect?: (key: ResultOutcomeKey | "measured" | null) => void;
}) {
  return (
    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-2">
      {CARDS.map((c) => {
        const value =
          c.key === "measured"
            ? counts.measured_count
            : counts[c.key];
        const secondary =
          c.key === "measured"
            ? formatMoney(counts.measured_amount)
            : null;
        const isActive =
          activeFilter === c.key ||
          (c.key !== "measured" && activeFilter === c.key);
        return (
          <button
            key={c.key}
            type="button"
            onClick={() => onSelect?.(isActive ? null : c.key)}
            className={cn(
              "text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded-lg",
            )}
          >
            <Card
              className={cn(
                "h-full border",
                c.tone,
                isActive && "ring-2 ring-primary/40",
              )}
            >
              <CardContent className="p-3 space-y-1">
                <div className="text-[10px] uppercase tracking-wide text-muted-foreground">
                  {c.title}
                </div>
                <div className="text-xl font-semibold tabular-nums">
                  {value}
                </div>
                {secondary ? (
                  <div className="text-xs font-medium tabular-nums text-primary">
                    {secondary}
                  </div>
                ) : null}
                <div className="text-[11px] leading-snug text-muted-foreground">
                  {c.hint}
                </div>
              </CardContent>
            </Card>
          </button>
        );
      })}
    </div>
  );
}
