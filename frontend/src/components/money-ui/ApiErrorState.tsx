import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { AlertTriangle, RefreshCw } from "lucide-react";
import { ApiError } from "@/lib/api";

export interface ApiErrorStateProps {
  error: unknown;
  endpoint?: string;
  onRetry?: () => void;
  title?: string;
}

function shortMessage(err: unknown, status?: number): string {
  if (status === 401) return "Сессия истекла — войдите снова.";
  if (status === 403) return "Нет доступа к этому разделу.";
  if (status === 404) return "Эндпоинт не найден на сервере.";
  if (status && status >= 500) return "Сервер временно недоступен.";
  if (err instanceof Error) return err.message;
  return "Неизвестная ошибка";
}

export function ApiErrorState({ error, endpoint, onRetry, title = "Не удалось загрузить данные" }: ApiErrorStateProps) {
  const status = error instanceof ApiError ? error.status : undefined;
  const path = endpoint ?? (error instanceof ApiError ? error.path : undefined);
  const msg = shortMessage(error, status);

  return (
    <Card className="border-destructive/40">
      <CardContent className="p-5 flex items-start gap-3">
        <AlertTriangle className="h-5 w-5 text-destructive shrink-0 mt-0.5" />
        <div className="flex-1 space-y-2 min-w-0">
          <div className="font-semibold">{title}</div>
          <div className="text-sm text-muted-foreground">{msg}</div>
          {(path || status) ? (
            <div className="text-xs font-mono text-muted-foreground break-all">
              {path ? `endpoint: ${path}` : ""}
              {status ? ` · HTTP ${status}` : ""}
            </div>
          ) : null}
          {onRetry ? (
            <Button size="sm" variant="outline" onClick={onRetry}>
              <RefreshCw className="h-3.5 w-3.5 mr-1.5" /> Повторить
            </Button>
          ) : null}
        </div>
      </CardContent>
    </Card>
  );
}
