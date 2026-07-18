// Renders the strict "Status mismatch" red banner when Data Health says
// financial_final=true but DQ Summary still reports blocking issues.
// Also renders the "Есть блокеры финальной сверки" amber strip when there
// are any final_blockers > 0.
import { AlertTriangle } from "lucide-react";
import type { StrictFinalState } from "@/lib/queries/strict-final";

export function StrictFinalWarnings({ strict }: { strict: StrictFinalState }) {
  return (
    <div className="space-y-2">
      {strict.finalBlockers > 0 && (
        <div className="rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-sm text-amber-900 dark:text-amber-200 flex items-start gap-2">
          <AlertTriangle className="h-4 w-4 mt-0.5 shrink-0" />
          <span>Есть блокеры финальной сверки: {strict.finalBlockers}</span>
        </div>
      )}
      {strict.mismatch && (
        <div className="rounded-md border border-red-500/50 bg-red-500/10 px-3 py-2 text-sm text-red-700 dark:text-red-300 flex items-start gap-2">
          <AlertTriangle className="h-4 w-4 mt-0.5 shrink-0" />
          <span>Статус требует проверки: Data Health и DQ Summary расходятся.</span>
        </div>
      )}
    </div>
  );
}
