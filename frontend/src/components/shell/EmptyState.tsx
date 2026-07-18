/**
 * Единый компонент пустого/промежуточного состояния.
 *
 * Отвечает на 4 вопроса продавца:
 *   1. Что произошло?
 *   2. Почему нет результата?
 *   3. Что можно сделать?
 *   4. Основное безопасное действие (если применимо).
 */
import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  FlaskConical,
  Inbox,
  Info,
  PowerOff,
  RefreshCw,
  ShieldAlert,
} from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export type EmptyStateVariant =
  | "needs_sync"
  | "no_data"
  | "no_problems"
  | "missing_data"
  | "disabled"
  | "beta"
  | "error";

const VARIANT: Record<
  EmptyStateVariant,
  {
    title: string;
    hint: string;
    icon: LucideIcon;
    tone: string;
  }
> = {
  needs_sync: {
    title: "Нужна синхронизация",
    hint: "Данные ещё не подтянулись из Wildberries. Запустите синхронизацию, чтобы увидеть актуальную картину.",
    icon: RefreshCw,
    tone: "text-warning bg-warning/10 border-warning/30",
  },
  no_data: {
    title: "Нет данных за выбранный период",
    hint: "Попробуйте другой период или запустите синхронизацию.",
    icon: Inbox,
    tone: "text-muted-foreground bg-muted border-border",
  },
  no_problems: {
    title: "Проблем не найдено",
    hint: "Платформа не увидела рисков по этому разрезу. Всё под контролем.",
    icon: CheckCircle2,
    tone: "text-success bg-success/10 border-success/30",
  },
  missing_data: {
    title: "Не хватает данных",
    hint: "Часть источников не подключена или пустая. Заполните их, чтобы расчёт стал точнее.",
    icon: ShieldAlert,
    tone: "text-warning bg-warning/10 border-warning/30",
  },
  disabled: {
    title: "Модуль отключён",
    hint: "Функция доступна, но выключена для этого аккаунта. Включите её в настройках.",
    icon: PowerOff,
    tone: "text-muted-foreground bg-muted border-border",
  },
  beta: {
    title: "Бета-модуль",
    hint: "Функция в тестовом режиме. Данные и поведение могут меняться.",
    icon: FlaskConical,
    tone: "text-primary bg-primary/10 border-primary/30",
  },
  error: {
    title: "Ошибка загрузки",
    hint: "Не удалось получить данные. Проверьте подключение и попробуйте снова.",
    icon: AlertTriangle,
    tone: "text-destructive bg-destructive/10 border-destructive/30",
  },
};

export interface EmptyStateProps {
  variant?: EmptyStateVariant;
  title?: string;
  hint?: ReactNode;
  icon?: LucideIcon;
  action?: ReactNode;
  onRetry?: () => void;
  retryLabel?: string;
  className?: string;
}

export function EmptyState({
  variant = "no_data",
  title,
  hint,
  icon,
  action,
  onRetry,
  retryLabel = "Обновить",
  className,
}: EmptyStateProps) {
  const cfg = VARIANT[variant];
  const Icon = icon ?? cfg.icon;
  return (
    <Card className={cn("border-dashed", className)}>
      <CardContent className="p-8 flex flex-col items-center text-center gap-3">
        <div
          className={cn(
            "h-11 w-11 rounded-full flex items-center justify-center border",
            cfg.tone,
          )}
        >
          <Icon className="h-5 w-5" />
        </div>
        <div className="max-w-md">
          <div className="font-semibold text-base">{title ?? cfg.title}</div>
          <div className="text-sm text-muted-foreground mt-1">
            {hint ?? cfg.hint}
          </div>
        </div>
        {(action || onRetry) && (
          <div className="flex flex-wrap justify-center gap-2 pt-1">
            {action}
            {onRetry ? (
              <Button size="sm" variant="outline" onClick={onRetry}>
                <RefreshCw className="h-3.5 w-3.5 mr-1.5" /> {retryLabel}
              </Button>
            ) : null}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export function InfoHint({ children }: { children: ReactNode }) {
  return (
    <div className="flex items-start gap-2 rounded-md border border-info/30 bg-info/5 px-3 py-2 text-xs text-info">
      <Info className="h-3.5 w-3.5 mt-0.5 shrink-0" />
      <span className="text-foreground/80">{children}</span>
    </div>
  );
}
