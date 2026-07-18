import { useEffect, useState } from "react";
import { Loader2 } from "lucide-react";

/**
 * Показывает "расчёт выполняется" если активный запрос идёт дольше `thresholdMs`.
 * Использовать рядом со скелетоном:
 *   {isLoading ? <><SkeletonTable /><LongRunningHint active={isFetching} /></> : ...}
 */
export function LongRunningHint({
  active,
  thresholdMs = 3000,
  label = "расчёт выполняется…",
}: {
  active: boolean;
  thresholdMs?: number;
  label?: string;
}) {
  const [show, setShow] = useState(false);
  useEffect(() => {
    if (!active) { setShow(false); return; }
    const t = setTimeout(() => setShow(true), thresholdMs);
    return () => clearTimeout(t);
  }, [active, thresholdMs]);
  if (!show) return null;
  return (
    <div className="inline-flex items-center gap-2 text-xs text-muted-foreground mt-2">
      <Loader2 className="h-3.5 w-3.5 animate-spin" />
      <span>{label}</span>
    </div>
  );
}
