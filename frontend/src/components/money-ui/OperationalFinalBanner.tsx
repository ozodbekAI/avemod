// Two separate status cards: Operational vs Final profit.
// Never merge into one "OK / blocked" badge.
//
// Source: GET /dashboard/data-health (+ optional /money/data-blockers count)
// Reads:
//   - operational_trusted: boolean
//   - financial_final: boolean
//   - financial_final_blockers_total: number
//
// If a field is missing, we degrade gracefully but never invent "OK".

import { Card, CardContent } from "@/components/ui/card";
import { CheckCircle2, AlertTriangle, Clock } from "lucide-react";
import { Link } from "@tanstack/react-router";

export interface OperationalFinalInputs {
  operational_trusted?: boolean | null;
  financial_final?: boolean | null;
  final_blockers_total?: number | null;
  /** When true, show an "Открыть исправление данных" link. Default true. */
  showDataFixLink?: boolean;
}

export function OperationalFinalBanner({
  operational_trusted,
  financial_final,
  final_blockers_total,
  showDataFixLink = true,
}: OperationalFinalInputs) {
  const opOk = operational_trusted === true;
  const finOk = financial_final === true;
  const blockers = Number(final_blockers_total ?? 0);

  return (
    <div className="grid gap-3 md:grid-cols-2">
      <Card className={opOk ? "border-success/40 bg-success/5" : "border-warning/40 bg-warning/5"}>
        <CardContent className="p-4">
          <div className="flex items-start gap-3">
            {opOk ? (
              <CheckCircle2 className="h-5 w-5 text-success mt-0.5 shrink-0" />
            ) : (
              <AlertTriangle className="h-5 w-5 text-warning mt-0.5 shrink-0" />
            )}
            <div className="min-w-0">
              <div className="text-sm font-semibold">
                {opOk ? "Операционно можно работать" : "Операционные данные ещё не подтверждены"}
              </div>
              <div className="text-xs text-muted-foreground mt-1">
                {opOk
                  ? "Данных достаточно для ежедневных решений."
                  : "Нужно дождаться синхронизации или починить базовые источники."}
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      <Card className={finOk ? "border-success/40 bg-success/5" : "border-warning/40 bg-warning/5"}>
        <CardContent className="p-4">
          <div className="flex items-start gap-3">
            {finOk ? (
              <CheckCircle2 className="h-5 w-5 text-success mt-0.5 shrink-0" />
            ) : (
              <Clock className="h-5 w-5 text-warning mt-0.5 shrink-0" />
            )}
            <div className="min-w-0 flex-1">
              <div className="text-sm font-semibold">
                {finOk
                  ? "Финальная прибыль подтверждена"
                  : "Финальная прибыль пока предварительная"}
              </div>
              <div className="text-xs text-muted-foreground mt-1">
                {finOk
                  ? "Все блокеры финальной сверки закрыты."
                  : blockers > 0
                    ? `Есть ${blockers} блокер${pluralEnd(blockers)} финальной сверки.`
                    : "Есть блокеры финальной сверки."}
              </div>
              {!finOk && showDataFixLink && (
                <Link
                  to="/data-fix"
                  className="text-xs text-primary hover:underline mt-2 inline-block"
                >
                  Открыть исправление данных →
                </Link>
              )}
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function pluralEnd(n: number): string {
  const a = Math.abs(n) % 100;
  const b = a % 10;
  if (a > 10 && a < 20) return "ов";
  if (b > 1 && b < 5) return "а";
  if (b === 1) return "";
  return "ов";
}
