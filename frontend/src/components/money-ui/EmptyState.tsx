/**
 * @deprecated Используйте `EmptyState` из `@/components/shell/EmptyState`.
 * Этот файл оставлен как совместимость. API сохранён: title/hint/onRetry/retryLabel.
 */
import {
  EmptyState as SharedEmptyState,
  type EmptyStateProps as SharedProps,
} from "@/components/shell/EmptyState";

export interface EmptyStateProps {
  title?: string;
  hint?: string;
  onRetry?: () => void;
  retryLabel?: string;
}

export function EmptyState({
  title,
  hint,
  onRetry,
  retryLabel,
}: EmptyStateProps) {
  const props: SharedProps = {
    variant: "no_data",
    title,
    hint,
    onRetry,
    retryLabel,
  };
  return <SharedEmptyState {...props} />;
}
