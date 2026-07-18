/**
 * Единый набор бейджей для операционного контроля.
 *
 * Все подписи — на русском, только для UI продавца.
 * Технические ключи (severity/status/impact/trust/result/freshness) остаются
 * как есть — приходят с бэкенда без изменений.
 */
import type { LucideIcon } from "lucide-react";
import {
  AlertOctagon,
  AlertTriangle,
  CheckCircle2,
  Clock,
  Coins,
  FlaskConical,
  HelpCircle,
  Info,
  Loader2,
  Lock,
  MinusCircle,
  RefreshCw,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  TrendingDown,
  TrendingUp,
  XCircle,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

type Tone =
  | "critical"
  | "danger"
  | "warning"
  | "success"
  | "info"
  | "opportunity"
  | "muted"
  | "primary";

const TONE: Record<Tone, string> = {
  critical:
    "bg-destructive/15 text-destructive border-destructive/40 dark:text-destructive",
  danger:
    "bg-destructive/10 text-destructive border-destructive/30",
  warning:
    "bg-warning/15 text-[oklch(0.42_0.12_60)] dark:text-warning border-warning/40",
  success:
    "bg-success/15 text-success border-success/30",
  info:
    "bg-info/10 text-info border-info/30",
  opportunity:
    "bg-opportunity/10 text-opportunity border-opportunity/30",
  muted:
    "bg-muted text-muted-foreground border-border",
  primary:
    "bg-primary/10 text-primary border-primary/30",
};

function Chip({
  tone,
  icon: Icon,
  children,
  className,
  title,
}: {
  tone: Tone;
  icon?: LucideIcon;
  children: React.ReactNode;
  className?: string;
  title?: string;
}) {
  return (
    <Badge
      variant="outline"
      title={title}
      className={cn("gap-1 font-medium border", TONE[tone], className)}
    >
      {Icon ? <Icon className="h-3 w-3" /> : null}
      {children}
    </Badge>
  );
}

// ---------- Severity ----------
const SEVERITY: Record<
  string,
  { label: string; tone: Tone; icon: LucideIcon }
> = {
  critical: { label: "Критично", tone: "critical", icon: AlertOctagon },
  high: { label: "Высокий", tone: "danger", icon: AlertTriangle },
  medium: { label: "Средний", tone: "warning", icon: AlertTriangle },
  low: { label: "Низкий", tone: "muted", icon: Info },
};
export function SeverityBadge({
  value,
  className,
}: {
  value?: string | null;
  className?: string;
}) {
  const cfg = SEVERITY[(value ?? "").toLowerCase()] ?? SEVERITY.low;
  return (
    <Chip tone={cfg.tone} icon={cfg.icon} className={className}>
      {cfg.label}
    </Chip>
  );
}

// ---------- Status (task/action) ----------
const STATUS: Record<string, { label: string; tone: Tone; icon: LucideIcon }> = {
  new: { label: "Новая", tone: "info", icon: Sparkles },
  acknowledged: { label: "Принята", tone: "info", icon: CheckCircle2 },
  in_progress: { label: "В работе", tone: "primary", icon: Loader2 },
  done: { label: "Выполнено", tone: "success", icon: CheckCircle2 },
  resolved: { label: "Решено", tone: "success", icon: CheckCircle2 },
  postponed: { label: "Отложено", tone: "warning", icon: Clock },
  reopened: { label: "Переоткрыто", tone: "warning", icon: RefreshCw },
  ignored: { label: "Отклонено", tone: "muted", icon: XCircle },
  dismissed: { label: "Отклонено", tone: "muted", icon: XCircle },
  blocked: { label: "Заблокировано", tone: "danger", icon: Lock },
};
export function StatusBadge({
  value,
  className,
}: {
  value?: string | null;
  className?: string;
}) {
  const cfg = STATUS[(value ?? "").toLowerCase()] ?? STATUS.new;
  return (
    <Chip tone={cfg.tone} icon={cfg.icon} className={className}>
      {cfg.label}
    </Chip>
  );
}

// ---------- Trust ----------
const TRUST: Record<string, { label: string; tone: Tone; icon: LucideIcon }> = {
  confirmed: { label: "Подтверждено", tone: "success", icon: ShieldCheck },
  provisional: { label: "Предварительно", tone: "warning", icon: Clock },
  estimated: { label: "Оценка", tone: "info", icon: Info },
  opportunity: { label: "Возможность", tone: "opportunity", icon: Sparkles },
  blocked: { label: "Не хватает данных", tone: "danger", icon: ShieldAlert },
  test_only: { label: "Тестовое правило", tone: "muted", icon: FlaskConical },
};
export function TrustBadge({
  value,
  className,
}: {
  value?: string | null;
  className?: string;
}) {
  const key = (value ?? "").toLowerCase();
  const cfg = TRUST[key] ?? TRUST.provisional;
  return (
    <Chip
      tone={cfg.tone}
      icon={cfg.icon}
      className={className}
      title="Уровень доверия к данным"
    >
      {cfg.label}
    </Chip>
  );
}

// ---------- Impact ----------
const IMPACT: Record<string, { label: string; tone: Tone; icon: LucideIcon }> = {
  confirmed_loss: { label: "Подтверждённый убыток", tone: "danger", icon: TrendingDown },
  probable_loss: { label: "Вероятный риск", tone: "warning", icon: AlertTriangle },
  blocked_cash: { label: "Замороженные деньги", tone: "info", icon: Coins },
  lost_sales_risk: { label: "Риск потери продаж", tone: "warning", icon: TrendingDown },
  opportunity: { label: "Возможность роста", tone: "opportunity", icon: TrendingUp },
  data_blocker: { label: "Блокер данных", tone: "muted", icon: ShieldAlert },
  system_warning: { label: "Системное предупреждение", tone: "muted", icon: Info },
};
export function ImpactBadge({
  value,
  className,
}: {
  value?: string | null;
  className?: string;
}) {
  const cfg = IMPACT[(value ?? "").toLowerCase()] ?? IMPACT.system_warning;
  return (
    <Chip tone={cfg.tone} icon={cfg.icon} className={className}>
      {cfg.label}
    </Chip>
  );
}

// ---------- Result ----------
const RESULT: Record<string, { label: string; tone: Tone; icon: LucideIcon }> = {
  pending_data: { label: "Ждём данных", tone: "muted", icon: Clock },
  improved: { label: "Есть улучшение", tone: "success", icon: TrendingUp },
  worse: { label: "Стало хуже", tone: "danger", icon: TrendingDown },
  neutral: { label: "Без изменений", tone: "muted", icon: MinusCircle },
  not_enough_data: { label: "Нет данных", tone: "muted", icon: HelpCircle },
  correlation_only: { label: "Корреляция, не гарантия", tone: "info", icon: Info },
};
export function ResultBadge({
  value,
  className,
}: {
  value?: string | null;
  className?: string;
}) {
  const cfg = RESULT[(value ?? "").toLowerCase()] ?? RESULT.pending_data;
  return (
    <Chip tone={cfg.tone} icon={cfg.icon} className={className}>
      {cfg.label}
    </Chip>
  );
}

// ---------- Source freshness ----------
const FRESHNESS: Record<string, { label: string; tone: Tone; icon: LucideIcon }> = {
  fresh: { label: "Данные актуальны", tone: "success", icon: CheckCircle2 },
  stale: { label: "Данные предварительные", tone: "warning", icon: Clock },
  needs_sync: { label: "Нужна синхронизация", tone: "warning", icon: RefreshCw },
  missing: { label: "Не хватает данных", tone: "danger", icon: ShieldAlert },
  not_configured: { label: "Модуль не настроен", tone: "muted", icon: Info },
};
export function SourceFreshnessBadge({
  value,
  className,
}: {
  value?: string | null;
  className?: string;
}) {
  const cfg = FRESHNESS[(value ?? "").toLowerCase()] ?? FRESHNESS.fresh;
  return (
    <Chip tone={cfg.tone} icon={cfg.icon} className={className}>
      {cfg.label}
    </Chip>
  );
}

// ---------- Beta module ----------
export function BetaModuleBadge({ className }: { className?: string }) {
  return (
    <Chip
      tone="primary"
      icon={FlaskConical}
      className={className}
      title="Бета-модуль. Возможности и данные могут меняться."
    >
      Бета
    </Chip>
  );
}

// ---------- Read-only signal ----------
export function ReadOnlySignalBadge({ className }: { className?: string }) {
  return (
    <Chip
      tone="muted"
      icon={Lock}
      className={className}
      title="Только просмотр. Действия недоступны."
    >
      Только чтение
    </Chip>
  );
}
