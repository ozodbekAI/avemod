import { AlertTriangle, RefreshCw, LogIn, Server, FileWarning, Search, ShieldOff } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { ApiError } from "@/lib/api";

/**
 * Friendly fallback for any route whose data fetch fails.
 * Shows status-specific guidance + the failing endpoint path so the user
 * (and us) can see exactly what the backend rejected — never a blank page.
 *
 *   401 → relogin
 *   404 → frontend endpoint mapping bug
 *   422 → validation details
 *   500 → backend incident
 */
export function EndpointError({
  error,
  reset,
  title,
}: {
  error: unknown;
  reset?: () => void;
  title?: string;
}) {
  const status = error instanceof ApiError ? error.status : undefined;
  const path = error instanceof ApiError ? error.path : undefined;
  const body = error instanceof ApiError ? error.body : undefined;
  const message = error instanceof Error ? error.message : "Неизвестная ошибка";

  let icon = <AlertTriangle className="h-5 w-5 text-destructive shrink-0 mt-0.5" />;
  let resolvedTitle = title ?? "Не удалось загрузить страницу";
  let hint: React.ReactNode = null;
  let action: React.ReactNode = null;

  if (status === 401) {
    icon = <LogIn className="h-5 w-5 text-warning shrink-0 mt-0.5" />;
    resolvedTitle = title ?? "Требуется вход";
    hint = "Сессия истекла. Войдите снова, чтобы продолжить.";
    action = (
      <Button size="sm" onClick={() => { window.location.href = "/login"; }}>
        <LogIn className="h-3.5 w-3.5 mr-1.5" /> Войти
      </Button>
    );
  } else if (status === 403) {
    icon = <ShieldOff className="h-5 w-5 text-destructive shrink-0 mt-0.5" />;
    resolvedTitle = title ?? "Нет доступа";
    hint = "У вашего аккаунта нет прав на этот ресурс. Обратитесь к администратору.";
  } else if (status === 404) {
    icon = <Search className="h-5 w-5 text-destructive shrink-0 mt-0.5" />;
    resolvedTitle = title ?? "Ошибка сопоставления эндпоинта во фронтенде";
    hint = "Эндпоинт не найден на бэкенде. Это ошибка маппинга в фронте — проверьте src/lib/endpoints.ts.";

  } else if (status === 422) {
    icon = <FileWarning className="h-5 w-5 text-warning shrink-0 mt-0.5" />;
    resolvedTitle = title ?? "Ошибка валидации (422)";
    hint = renderValidation(body);
  } else if (status && status >= 500) {
    icon = <Server className="h-5 w-5 text-destructive shrink-0 mt-0.5" />;
    resolvedTitle = title ?? "Серверная ошибка";
    hint = "Бэкенд вернул ошибку. Повторите попытку или сообщите команде бэкенда.";
  }

  return (
    <div className="p-6">
      <Card className="border-destructive/40">
        <CardContent className="p-6 space-y-3">
          <div className="flex items-start gap-3">
            {icon}
            <div className="space-y-1 min-w-0">
              <div className="font-semibold text-base">{resolvedTitle}</div>
              {hint ? <div className="text-sm text-muted-foreground">{hint}</div> : null}
              {!hint && message ? <div className="text-sm text-muted-foreground">{message}</div> : null}
              {path ? (
                <div className="text-xs font-mono text-muted-foreground break-all">
                  эндпоинт: {path}
                  {status ? ` · ${status}` : ""}
                </div>
              ) : null}
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            {action}
            {reset ? (
              <Button size="sm" variant="outline" onClick={reset}>
                <RefreshCw className="h-3.5 w-3.5 mr-1.5" /> Повторить
              </Button>
            ) : null}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function renderValidation(body: unknown): React.ReactNode {
  if (!body || typeof body !== "object") return "Проверьте параметры запроса.";
  const detail = (body as { detail?: unknown }).detail;
  if (Array.isArray(detail)) {
    return (
      <ul className="list-disc pl-4 space-y-0.5">
        {detail.slice(0, 6).map((d: any, i) => (
          <li key={i} className="text-xs">
            <span className="font-mono">{Array.isArray(d?.loc) ? d.loc.join(".") : "?"}</span>: {d?.msg ?? "invalid"}
          </li>
        ))}
      </ul>
    );
  }
  if (typeof detail === "string") return detail;
  return "Проверьте параметры запроса.";
}
