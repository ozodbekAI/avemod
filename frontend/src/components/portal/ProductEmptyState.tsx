/**
 * Product360 — единый набор пустых/промежуточных состояний.
 *
 * Оборачивает shared EmptyState с product-level копиями. Не заменяет
 * реальные ошибки API — их продолжаем показывать через Alert + retry.
 */
import type { ReactNode } from "react";
import {
  EmptyState,
  type EmptyStateVariant,
} from "@/components/shell/EmptyState";

export type ProductEmptyKind =
  | "needs_sync"
  | "no_data"
  | "no_problems"
  | "missing_data"
  | "disabled"
  | "beta"
  | "error";

const COPY: Record<
  ProductEmptyKind,
  { variant: EmptyStateVariant; title: string; hint: string }
> = {
  needs_sync: {
    variant: "needs_sync",
    title: "Нужна синхронизация",
    hint: "Обновите данные по товару, чтобы платформа смогла найти проблемы.",
  },
  no_data: {
    variant: "no_data",
    title: "Нет данных по товару",
    hint: "Платформа пока не получила данные для анализа этого товара.",
  },
  no_problems: {
    variant: "no_problems",
    title: "Проблем не найдено",
    hint: "По текущим данным активных проблем по товару нет.",
  },
  missing_data: {
    variant: "missing_data",
    title: "Не хватает данных",
    hint: "Часть расчётов недоступна без себестоимости, связки SKU или свежей синхронизации.",
  },
  disabled: {
    variant: "disabled",
    title: "Модуль отключён",
    hint: "Проверка товара недоступна для текущего аккаунта или роли.",
  },
  beta: {
    variant: "beta",
    title: "Бета-модуль",
    hint: "Этот сигнал доступен только в бета-режиме или для администратора.",
  },
  error: {
    variant: "error",
    title: "Не удалось загрузить товар",
    hint: "Проверьте подключение или повторите попытку.",
  },
};

export interface ProductEmptyStateProps {
  kind: ProductEmptyKind;
  title?: string;
  hint?: ReactNode;
  action?: ReactNode;
  onRetry?: () => void;
  retryLabel?: string;
  className?: string;
}

export function ProductEmptyState({
  kind,
  title,
  hint,
  action,
  onRetry,
  retryLabel,
  className,
}: ProductEmptyStateProps) {
  const cfg = COPY[kind];
  return (
    <EmptyState
      variant={cfg.variant}
      title={title ?? cfg.title}
      hint={hint ?? cfg.hint}
      action={action}
      onRetry={onRetry}
      retryLabel={retryLabel}
      className={className}
    />
  );
}
