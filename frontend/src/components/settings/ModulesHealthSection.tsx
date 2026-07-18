import { Link } from "@tanstack/react-router";
import { useModulesHealth, type PortalModuleHealth } from "@/lib/modules-health";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import {
  CheckCircle2, AlertTriangle, PowerOff, Settings as SettingsIcon, Info,
  ArrowRight, FlaskConical, XCircle, Clock,
} from "lucide-react";
import { legacyDiagnosticsEnabled } from "@/lib/legacy-diagnostics";

type ModuleDef = {
  key: string;
  label: string;
  href?: string;
  description: string;
  /** Что пользователь получает, когда модуль включён. */
  benefit: string;
  /** Подсказка, когда модуль не настроен. */
  setupHint?: string;
};

const MODULES: ModuleDef[] = [
  { key: "finance",    label: "Финансы",          href: "/dashboard",      description: "Финансовая сводка и P&L.",
    benefit: "Чистая прибыль и сверка с финотчётом Wildberries." },
  { key: "doctor",     label: "Диагностика прибыли legacy", href: "/doctor", description: "Админская проверка старых сигналов прибыли.",
    benefit: "Помогает сравнить legacy-диагностику с динамическими проблемами." },
  { key: "actions",    label: "Центр действий",   href: "/action-center",  description: "Очередь действий и рекомендаций.",
    benefit: "Единый список задач со статусами «В работе / Выполнено»." },
  { key: "products",   label: "Товары",           href: "/products",       description: "Карточки, выручка, прибыль.",
    benefit: "Сводка по каждой карточке на странице товара." },
  { key: "checker",    label: "Проверка карточек",                         description: "Качество карточек: фото, описание, характеристики.",
    benefit: "Видите проблемы карточки и рекомендации на странице товара.",
    setupHint: "Подключите проверку карточек, чтобы видеть качество карточки на странице товара." },
  { key: "stockops",   label: "Остатки",                                   description: "Остатки, OOS, переизбыток.",
    benefit: "Подсказки по закупкам и риску стока.",
    setupHint: "Подключите StockOps, чтобы получать предупреждения по остаткам." },
  { key: "grouping",   label: "Группировка",                               description: "Группировка карточек и SKU.",
    benefit: "Видите карточки одной группы как единый товар." },
  { key: "reputation", label: "Репутация",        href: "/reputation",     description: "Отзывы, вопросы, чаты.",
    benefit: "Видите неотвеченные отзывы и негатив." },
  { key: "claims",     label: "Претензии",        href: "/claims",         description: "Претензии и доказательства.",
    benefit: "Готовите претензии и фиксируете возврат денег." },
  { key: "photo",      label: "Фотостудия",                                description: "Фото-проверки и обновления.",
    benefit: "Автоматическая проверка соответствия фото требованиям." },
  { key: "experiments", label: "Эксперименты",                             description: "Эксперименты с ценой и контентом.",
    benefit: "Замер эффекта изменений до раскатки на всё." },
  { key: "results",    label: "Результаты",       href: "/results",        description: "Журнал событий и эффектов.",
    benefit: "История того, что сделал оператор и какой был эффект." },
];

type NormStatus = "ok" | "warning" | "not_configured" | "disabled" | "unavailable" | "error" | "unknown";
type RuntimeStatus =
  | "disabled"
  | "not_configured"
  | "beta_readonly"
  | "beta_draft_only"
  | "enabled_safe"
  | "enabled_write_actions"
  | "unknown";

const STATUS_META: Record<NormStatus, { label: string; tone: string; icon: any }> = {
  ok:             { label: "Подключен",        tone: "border-success/30 bg-success/10 text-success",        icon: CheckCircle2 },
  warning:        { label: "Требует внимания", tone: "border-warning/30 bg-warning/10 text-warning",        icon: AlertTriangle },
  not_configured: { label: "Не настроен",      tone: "border-muted-foreground/30 bg-muted text-muted-foreground", icon: SettingsIcon },
  disabled:       { label: "Отключен",         tone: "border-muted-foreground/30 bg-muted text-muted-foreground", icon: PowerOff },
  unavailable:    { label: "Недоступен",       tone: "border-destructive/30 bg-destructive/10 text-destructive",  icon: XCircle },
  error:          { label: "Ошибка",           tone: "border-destructive/30 bg-destructive/10 text-destructive",  icon: XCircle },
  unknown:        { label: "Неизвестно",       tone: "border-muted-foreground/30 bg-muted text-muted-foreground", icon: Info },
};

const RUNTIME_META: Record<RuntimeStatus, { label: string; tone: string; description: string }> = {
  disabled: {
    label: "disabled",
    tone: "border-muted-foreground/30 bg-muted text-muted-foreground",
    description: "модуль выключен",
  },
  not_configured: {
    label: "not configured",
    tone: "border-muted-foreground/30 bg-muted text-muted-foreground",
    description: "нужна настройка",
  },
  beta_readonly: {
    label: "beta readonly",
    tone: "border-muted-foreground/30 bg-muted text-muted-foreground",
    description: "только просмотр и рекомендации",
  },
  beta_draft_only: {
    label: "beta draft",
    tone: "border-primary/30 bg-primary/10 text-primary",
    description: "черновики без записи в маркетплейс",
  },
  enabled_safe: {
    label: "safe",
    tone: "border-success/30 bg-success/10 text-success",
    description: "безопасный рабочий режим",
  },
  enabled_write_actions: {
    label: "write gated",
    tone: "border-warning/30 bg-warning/10 text-warning",
    description: "запись только через права, preview/diff, confirm и audit",
  },
  unknown: {
    label: "unknown",
    tone: "border-muted-foreground/30 bg-muted text-muted-foreground",
    description: "режим не получен",
  },
};

/**
 * Нормализуем поле status из бекенда в одну из 7 категорий.
 * Никогда не возвращаем "ok" для disabled/not_configured/error модулей —
 * пользователь не должен думать, что отключённый модуль работает.
 */
export function normalizeModuleStatus(h?: PortalModuleHealth | null): NormStatus {
  if (!h) return "unknown";
  const raw = (h.status ?? "").toLowerCase();
  if (raw === "disabled" || h.enabled === false) return "disabled";
  if (raw === "not_configured" || h.configured === false) return "not_configured";
  if (raw === "unavailable") return "unavailable";
  if (raw === "error") return "error";
  if (raw === "warning" || raw === "degraded") return "warning";
  if (raw === "ok") return "ok";
  return "unknown";
}

function normalizeRuntimeStatus(h?: PortalModuleHealth | null): RuntimeStatus {
  const raw = String(h?.runtime_status ?? "").toLowerCase();
  if (
    raw === "disabled" ||
    raw === "not_configured" ||
    raw === "beta_readonly" ||
    raw === "beta_draft_only" ||
    raw === "enabled_safe" ||
    raw === "enabled_write_actions"
  ) {
    return raw;
  }
  return "unknown";
}

function pickMessage(h?: PortalModuleHealth | null): string | null {
  if (!h) return null;
  const m = h.message ?? (h as any).detail ?? (h as any).reason;
  return m ? String(m) : null;
}

function ModuleCard({ def, health }: { def: ModuleDef; health?: PortalModuleHealth }) {
  const status = normalizeModuleStatus(health);
  const runtimeStatus = normalizeRuntimeStatus(health);
  const meta = STATUS_META[status];
  const runtimeMeta = RUNTIME_META[runtimeStatus];
  const Icon = meta.icon;
  const message = pickMessage(health);
  const beta = !!health?.beta;
  const isOk = status === "ok";
  const isOff = status === "disabled" || status === "not_configured";
  const isBroken = status === "unavailable" || status === "error";

  return (
    <div data-module-card={def.key} data-module-status={status} data-module-runtime-status={runtimeStatus}>
    <Card
      className={isOff ? "border-dashed" : isBroken ? "border-destructive/40" : ""}
    >
      <CardContent className="p-4 space-y-2">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <div className="text-sm font-semibold">{def.label}</div>
              {beta && (
                <Badge variant="outline" className="text-[10px] border-primary/30 text-primary">
                  <FlaskConical className="h-3 w-3 mr-1" />Beta
                </Badge>
              )}
              <Badge variant="outline" className={`text-[10px] ${runtimeMeta.tone}`} data-module-runtime-badge>
                {runtimeMeta.label}
              </Badge>
            </div>
            <div className="text-xs text-muted-foreground mt-0.5">{def.description}</div>
          </div>
          <Badge variant="outline" className={`text-[10px] shrink-0 ${meta.tone}`} data-module-badge>
            <Icon className="h-3 w-3 mr-1" />
            {meta.label}
          </Badge>
        </div>

        <div className="text-xs text-muted-foreground">
          <span className="font-medium text-foreground">Что даёт: </span>{def.benefit}
        </div>

        <div className="text-xs text-muted-foreground">
          <span className="font-medium text-foreground">Режим: </span>{runtimeMeta.description}
        </div>

        {(status === "not_configured" && def.setupHint) && (
          <div className="text-xs text-foreground border-l-2 border-warning/50 pl-2">
            {def.setupHint}
          </div>
        )}

        {status === "disabled" && (
          <div className="text-xs text-muted-foreground border-l-2 border-border pl-2">
            Модуль отключён. Это не ошибка — соответствующая страница пока не получает данные.
          </div>
        )}

        {isBroken && message && (
          <div className="text-xs text-destructive border-l-2 border-destructive/50 pl-2">
            {message}
          </div>
        )}

        <div className="flex items-center gap-2 pt-1 flex-wrap">
          {isOk && def.href && (
            <Button asChild size="sm" variant="outline" className="h-7 text-xs">
              <Link to={def.href}>Открыть <ArrowRight className="h-3 w-3 ml-1" /></Link>
            </Button>
          )}
          {status === "warning" && def.href && (
            <Button asChild size="sm" variant="outline" className="h-7 text-xs">
              <Link to={def.href}>Открыть как есть <ArrowRight className="h-3 w-3 ml-1" /></Link>
            </Button>
          )}
          {status === "not_configured" && (
            <Badge variant="outline" className="text-[10px] border-muted-foreground/30 text-muted-foreground">
              <SettingsIcon className="h-3 w-3 mr-1" />Нужна настройка администратором
            </Badge>
          )}
          {status === "disabled" && (
            <Badge variant="outline" className="text-[10px] text-muted-foreground border-muted-foreground/30">
              <Clock className="h-3 w-3 mr-1" />Включить позже{beta ? " · Beta" : ""}
            </Badge>
          )}
          {isBroken && (
            <Badge variant="outline" className="text-[10px] border-destructive/30 text-destructive">
              <XCircle className="h-3 w-3 mr-1" />Сообщите команде платформы
            </Badge>
          )}
        </div>
      </CardContent>
    </Card>
    </div>
  );
}

export function ModulesHealthSection() {
  const { data, isLoading, error } = useModulesHealth();
  const byKey = new Map<string, PortalModuleHealth>();
  (data ?? []).forEach((m) => byKey.set(m.module, m));
  const visibleModules = MODULES.filter((def) => def.key !== "doctor" || legacyDiagnosticsEnabled());

  return (
    <Card className="mb-4" data-modules-health-section>
      <CardHeader>
        <CardTitle>Интеграции и модули</CardTitle>
        <CardDescription>
          Состояние модулей портала. Если страница в меню пустая — посмотрите статус здесь.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {isLoading && (
          <div className="grid gap-3 md:grid-cols-2">
            {Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-24 w-full" />)}
          </div>
        )}
        {error && (
          <Alert variant="destructive">
            <AlertTriangle className="h-4 w-4" />
            <AlertTitle>Не удалось получить статус модулей</AlertTitle>
            <AlertDescription>{(error as Error).message}</AlertDescription>
          </Alert>
        )}
        {!isLoading && !error && (
          <>
            <Alert>
              <Info className="h-4 w-4" />
              <AlertDescription className="text-xs">
                Отключённые и ненастроенные модули — это не ошибка. Это значит, что соответствующая страница пока не получает данные.
              </AlertDescription>
            </Alert>
            <div className="grid gap-3 md:grid-cols-2">
              {visibleModules.map((def) => {
                // Не скрываем карточку, даже если backend сказал visible=false:
                // пользователь должен понимать, почему модуль не виден в навигации.
                const h = byKey.get(def.key);
                return <ModuleCard key={def.key} def={def} health={h} />;
              })}
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}
