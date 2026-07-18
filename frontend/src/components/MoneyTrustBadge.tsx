import { Badge } from "@/components/ui/badge";
import {
  evidenceTrustLabel,
  evidenceTrustStateFrom,
  moneyTrustFrom,
  moneyTrustTone,
  type MoneyTrustInfo,
} from "@/lib/money-trust";
import { problemImpactLabel, problemTrustLabel } from "@/lib/problem-ux-copy";
import { cn } from "@/lib/utils";

export function MoneyTrustBadge({
  trust,
  fallback,
  className,
  contextLabel,
}: {
  trust?: MoneyTrustInfo | null;
  fallback?: unknown;
  className?: string;
  contextLabel?: string;
}) {
  const resolved = moneyTrustFrom(trust, fallback);
  const label = contextLabel
    ? `${contextLabel}: ${problemImpactLabel(resolved.impact_kind)}`
    : resolved.display_label;
  return (
    <Badge
      variant="outline"
      className={cn("gap-1 text-[10px]", moneyTrustTone(resolved), className)}
      title={
        contextLabel
          ? "Тип денежного влияния, не уровень доверия к данным"
          : undefined
      }
    >
      {label}
    </Badge>
  );
}

export function EvidenceTrustBadge({
  trust,
  fallback,
  className,
  contextLabel,
}: {
  trust?: MoneyTrustInfo | null;
  fallback?: unknown;
  className?: string;
  contextLabel?: string;
}) {
  const state = evidenceTrustStateFrom(trust, fallback);
  const label = evidenceTrustLabel(state);
  if (!label) return null;
  const displayLabel = contextLabel
    ? `${contextLabel}: ${problemTrustLabel(String(state ?? ""))}`
    : label;
  return (
    <Badge
      variant="outline"
      className={cn(
        "gap-1 text-[10px] border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
        className,
      )}
      title={
        contextLabel
          ? "Доверие к источникам и входным данным, не подтверждение денежного эффекта"
          : undefined
      }
    >
      {displayLabel}
    </Badge>
  );
}
