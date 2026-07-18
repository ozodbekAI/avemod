/**
 * @deprecated Используйте `TrustBadge` из `@/components/badges/StatusBadges`.
 * Этот файл оставлен как совместимость: старые импорты продолжают работать,
 * но теперь оборачивают единый бейдж на семантических токенах.
 */
import { TrustBadge as SharedTrustBadge } from "@/components/badges/StatusBadges";

export type TrustLevel =
  | "final"
  | "supplier_confirmed"
  | "business_accepted"
  | "operator_baseline"
  | "provisional"
  | "preliminary"
  | "needs_review"
  | "computed"
  | "not_computable"
  | "critical_mismatch"
  | "data_blocked";

// Маппинг старых финансовых уровней на общие ключи shared TrustBadge.
const LEVEL_ALIASES: Record<string, string> = {
  final: "confirmed",
  supplier_confirmed: "confirmed",
  business_accepted: "confirmed",
  operator_baseline: "provisional",
  provisional: "provisional",
  preliminary: "provisional",
  needs_review: "provisional",
  computed: "estimated",
  not_computable: "blocked",
  critical_mismatch: "blocked",
  data_blocked: "blocked",
};

export function TrustBadge({
  level,
  className = "",
}: {
  level: TrustLevel | string | null | undefined;
  className?: string;
}) {
  const key = (level ?? "provisional") as string;
  const mapped = LEVEL_ALIASES[key] ?? key;
  return <SharedTrustBadge value={mapped} className={className} />;
}
