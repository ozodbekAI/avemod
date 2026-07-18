// @ts-nocheck
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";

export type QuickFilterKey =
  | "all"
  | "pending_data"
  | "improved"
  | "worse"
  | "neutral"
  | "not_enough_data"
  | "needs_recheck"
  | "confirmed"
  | "estimated";

const CHIPS: { key: QuickFilterKey; label: string }[] = [
  { key: "all", label: "Все" },
  { key: "pending_data", label: "Ждём данных" },
  { key: "improved", label: "Есть улучшение" },
  { key: "worse", label: "Стало хуже" },
  { key: "neutral", label: "Без изменений" },
  { key: "not_enough_data", label: "Нет данных" },
  { key: "needs_recheck", label: "Требует перепроверки" },
  { key: "confirmed", label: "Подтверждённые" },
  { key: "estimated", label: "Оценочные" },
];

export function ResultsQuickFilterBar({
  value,
  onChange,
}: {
  value: QuickFilterKey;
  onChange: (v: QuickFilterKey) => void;
}) {
  return (
    <div
      className="flex flex-wrap gap-1.5"
      role="tablist"
      aria-label="Быстрые фильтры результатов"
    >
      {CHIPS.map((c) => {
        const active = c.key === value;
        return (
          <Button
            key={c.key}
            type="button"
            size="sm"
            variant={active ? "default" : "outline"}
            className={cn("h-7 text-xs px-3")}
            onClick={() => onChange(c.key)}
            aria-pressed={active}
          >
            {c.label}
          </Button>
        );
      })}
    </div>
  );
}
