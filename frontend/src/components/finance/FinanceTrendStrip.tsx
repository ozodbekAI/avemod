// Блок «Результаты по деньгам» — сколько финансовых проблем в каком состоянии.
// Не выдумывает измеренную экономию. Все счётчики — из уже загруженных блокеров/предупреждений.
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ArrowRight } from "lucide-react";
import { EmptyState } from "@/components/shell/EmptyState";
import type { MDataBlocker } from "@/lib/api";
import { isFinanceBlocker } from "./financeCategorize";

interface Buckets {
  closed: number;
  waiting_recheck: number;
  improved: number;
  worse: number;
  no_data: number;
}

function bucket(items: MDataBlocker[]): Buckets {
  const b: Buckets = { closed: 0, waiting_recheck: 0, improved: 0, worse: 0, no_data: 0 };
  for (const it of items) {
    const rs = String((it as any)?.result_state ?? "").toLowerCase();
    if (!rs) b.no_data += 1;
    else if (/closed|resolved|done/.test(rs)) b.closed += 1;
    else if (/wait|pending|recheck|verify/.test(rs)) b.waiting_recheck += 1;
    else if (/improv|better|success/.test(rs)) b.improved += 1;
    else if (/worse|regress|degrad/.test(rs)) b.worse += 1;
    else b.no_data += 1;
  }
  return b;
}

export interface FinanceTrendStripProps {
  blockers: MDataBlocker[] | null | undefined;
  warnings?: MDataBlocker[] | null | undefined;
  resultsLinkSupported?: boolean;
}

export function FinanceTrendStrip({ blockers, warnings, resultsLinkSupported = true }: FinanceTrendStripProps) {
  const all = [
    ...(Array.isArray(blockers) ? blockers : []),
    ...(Array.isArray(warnings) ? warnings : []),
  ].filter((b) => isFinanceBlocker(b?.code));

  return (
    <section className="space-y-2">
      <div className="space-y-0.5">
        <h2 className="text-base font-semibold">Результаты по деньгам</h2>
        <div className="text-xs text-muted-foreground">
          Сравнение показывает связь по данным после действия, но не доказывает причинность само по себе.
        </div>
      </div>
      {all.length === 0 ? (
        <EmptyState
          variant="no_problems"
          title="Результатов пока нет"
          hint="Закройте финансовую задачу или запустите перепроверку, чтобы увидеть результат."
        />
      ) : (() => {
        const b = bucket(all);
        const chips: Array<[string, number, string]> = [
          ["Закрыто финансовых проблем", b.closed,          "bg-emerald-500/15 text-emerald-700 dark:text-emerald-300"],
          ["Ждёт перепроверки",           b.waiting_recheck, "bg-sky-500/15 text-sky-700 dark:text-sky-300"],
          ["Есть улучшение",              b.improved,        "bg-emerald-500/15 text-emerald-700 dark:text-emerald-300"],
          ["Стало хуже",                  b.worse,           "bg-destructive/15 text-destructive"],
          ["Нет данных",                  b.no_data,         "bg-muted text-muted-foreground"],
        ];
        return (
          <Card>
            <CardContent className="p-3 flex flex-wrap items-center gap-2">
              {chips.map(([label, n, cls]) => (
                <Badge key={label} variant="outline" className={`text-[11px] ${cls}`}>
                  {label}: {n}
                </Badge>
              ))}
              {resultsLinkSupported ? (
                <Button asChild size="sm" variant="ghost" className="ml-auto">
                  <a href="/results?source_module=finance">
                    Все результаты по деньгам <ArrowRight className="h-3 w-3 ml-1" />
                  </a>
                </Button>
              ) : (
                <Button
                  size="sm"
                  variant="ghost"
                  disabled
                  className="ml-auto"
                  title="Фильтр по финансовым результатам будет доступен после подключения источника."
                >
                  Фильтр по деньгам недоступен
                </Button>
              )}
            </CardContent>
          </Card>
        );
      })()}
    </section>
  );
}
