// @ts-nocheck
import { Check, Clock, ArrowRight } from "lucide-react";
import { cn } from "@/lib/utils";

type Step = {
  key: "before" | "action" | "recheck" | "after" | "comparison";
  label: string;
  ready: boolean;
  hint?: string | null;
};

export function ResultTimeline({
  before,
  action,
  recheck,
  after,
  comparison,
  className,
}: {
  before: boolean;
  action: boolean;
  recheck: boolean;
  after: boolean;
  comparison: boolean;
  className?: string;
}) {
  const steps: Step[] = [
    { key: "before", label: "До действия", ready: before },
    { key: "action", label: "Действие", ready: action },
    { key: "recheck", label: "Перепроверка", ready: recheck },
    { key: "after", label: "После действия", ready: after },
    { key: "comparison", label: "Сравнение", ready: comparison },
  ];

  return (
    <ol
      className={cn(
        // mobile: vertical stack; sm/tablet: 2 cols; md: 3 cols; lg+: 5-col horizontal
        "grid gap-2 grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-5 lg:gap-0",
        className,
      )}
      aria-label="Таймлайн результата"
    >
      {steps.map((s, i) => (
        <li
          key={s.key}
          className={cn(
            "flex items-start gap-2 lg:flex-col lg:items-center lg:text-center lg:relative lg:px-1",
          )}
        >
          <div
            className={cn(
              "flex h-6 w-6 items-center justify-center rounded-full border text-[10px] font-medium shrink-0",
              s.ready
                ? "bg-success/15 border-success/40 text-success"
                : "bg-muted border-border text-muted-foreground",
            )}
            aria-label={s.ready ? "готово" : "ждём"}
          >
            {s.ready ? (
              <Check className="h-3 w-3" />
            ) : (
              <Clock className="h-3 w-3" />
            )}
          </div>
          <div className="flex-1 min-w-0 lg:mt-1">
            <div className="text-xs font-medium leading-tight break-words">{s.label}</div>
            <div className="text-[11px] text-muted-foreground leading-tight">
              {s.ready ? "готово" : "ждём"}
            </div>
          </div>
          {i < steps.length - 1 ? (
            <ArrowRight className="hidden lg:block absolute right-0 top-2 h-3 w-3 text-muted-foreground/60 translate-x-1/2" />
          ) : null}
        </li>
      ))}
    </ol>
  );
}
