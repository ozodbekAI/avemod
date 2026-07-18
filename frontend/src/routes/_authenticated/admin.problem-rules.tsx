import { useMemo, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";
import {
  AlertTriangle,
  CheckCircle2,
  FlaskConical,
  History,
  Layers,
  ListChecks,
  PauseCircle,
  PowerOff,
  ShieldCheck,
  Sparkles,
  Wallet,
} from "lucide-react";

import { PageHeader } from "@/components/shell/PageHeader";
import { EmptyState } from "@/components/shell/EmptyState";
import { EndpointError } from "@/components/EndpointError";
import { ProblemRulesAdminPanel } from "@/components/problem-rules/ProblemRulesAdminPanel";
import { useAdminRuleBacktest } from "@/components/problem-rules/adminRuleBacktestStore";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { useAuth } from "@/lib/auth-context";
import {
  fetchProblemDefinitions,
  type ProblemDefinition,
} from "@/lib/problem-rules";

export const Route = createFileRoute("/_authenticated/admin/problem-rules")({
  component: ProblemRulesAdminRoute,
  errorComponent: ({ error, reset }) => (
    <EndpointError error={error} reset={reset} />
  ),
});

function ProblemRulesAdminRoute() {
  const { user, loading } = useAuth();
  const isAdmin =
    !!user?.is_superuser ||
    (user?.roles ?? []).some((r) => r === "admin" || r === "superuser");

  if (loading) {
    return (
      <div className="px-6 py-6 max-w-[1600px] mx-auto">
        <PageHeader
          title="Правила проблем"
          subtitle="Создавайте и проверяйте правила, которые превращают данные в задачи для селлера."
          breadcrumbs={[
            { label: "Администрирование", to: "/admin" },
            { label: "Правила проблем" },
          ]}
        />
      </div>
    );
  }

  if (!isAdmin) {
    return (
      <div className="px-6 py-6 max-w-[1600px] mx-auto space-y-4">
        <PageHeader title="Недоступно" />
        <EmptyState
          variant="disabled"
          title="Конструктор правил недоступен"
          hint="Этот раздел доступен только администраторам."
        />
      </div>
    );
  }

  return (
    <div className="px-6 py-6 max-w-[1600px] mx-auto space-y-4">
      <PageHeader
        title="Правила проблем"
        subtitle="Создавайте и проверяйте правила, которые превращают данные в задачи для селлера."
        breadcrumbs={[
          { label: "Администрирование", to: "/admin" },
          { label: "Правила проблем" },
        ]}
      />
      <RulesOverviewSummary />
      <ProblemRulesAdminPanel />
      <SellerPreviewMultiSurface />
      <PublishSafetyChecklist />
      <RuleDetailExtras />
      <VersionComparePlaceholder />
    </div>
  );
}

// -----------------------------------------------------------------------------
// 1. Overview summary band — 6 cards
// -----------------------------------------------------------------------------

function RulesOverviewSummary() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["problem-rules", "definitions"],
    queryFn: fetchProblemDefinitions,
    staleTime: 60_000,
  });

  const counts = useMemo(() => summarise(data ?? []), [data]);

  if (isError) {
    return (
      <EmptyState
        variant="error"
        title="Не удалось загрузить правила"
        hint="Проверьте подключение или повторите попытку."
      />
    );
  }

  const cards: Array<{
    key: string;
    label: string;
    value: string;
    icon: React.ComponentType<{ className?: string }>;
    tone: string;
    note?: string;
  }> = [
    {
      key: "active",
      label: "Активные правила",
      value: fmt(counts.active, isLoading),
      icon: CheckCircle2,
      tone: "text-success",
    },
    {
      key: "draft",
      label: "Черновики",
      value: fmt(counts.draft, isLoading),
      icon: Layers,
      tone: "text-muted-foreground",
    },
    {
      key: "testing",
      label: "На тестировании",
      value: fmt(counts.testing, isLoading),
      icon: FlaskConical,
      tone: "text-primary",
    },
    {
      key: "review",
      label: "Требуют проверки",
      value: fmt(counts.review, isLoading),
      icon: AlertTriangle,
      tone: "text-warning",
      note: "Правила с блокерами данных или пометкой «оценка»",
    },
    {
      key: "disabled",
      label: "Отключены",
      value: fmt(counts.disabled, isLoading),
      icon: PowerOff,
      tone: "text-muted-foreground",
    },
    {
      key: "hits",
      label: "Последние срабатывания",
      value: "—",
      icon: History,
      tone: "text-muted-foreground",
      note: "Требуется бэкенд-эндпоинт статистики срабатываний",
    },
  ];

  return (
    <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-3">
      {cards.map(({ key, label, value, icon: Icon, tone, note }) => (
        <Card key={key} className="border-dashed">
          <CardContent className="p-3">
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <Icon className={`h-3.5 w-3.5 ${tone}`} />
              {label}
            </div>
            <div className="mt-1.5 text-2xl font-semibold tabular-nums">
              {value}
            </div>
            {note ? (
              <div className="mt-1 text-[11px] text-muted-foreground leading-snug">
                {note}
              </div>
            ) : null}
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

function fmt(n: number, loading: boolean): string {
  if (loading) return "…";
  return String(n);
}

function summarise(defs: ProblemDefinition[]) {
  let active = 0;
  let draft = 0;
  let testing = 0;
  let disabled = 0;
  let review = 0;
  for (const d of defs) {
    if (d.status === "active") active += 1;
    else if (d.status === "draft") draft += 1;
    else if (d.status === "testing") testing += 1;
    else if (d.status === "paused" || d.status === "archived") disabled += 1;
    if (
      d.trust_state_default === "blocked" ||
      d.trust_state_default === "test_only" ||
      d.impact_type_default === "data_blocker"
    ) {
      review += 1;
    }
  }
  return { active, draft, testing, disabled, review };
}

// -----------------------------------------------------------------------------
// 2. Multi-surface seller preview (5 surfaces)
// -----------------------------------------------------------------------------

function SellerPreviewMultiSurface() {
  const { backtest } = useAdminRuleBacktest();
  const sample = (backtest?.sample_issues?.[0] ?? null) as
    | Record<string, unknown>
    | null;

  const evidence =
    sample && typeof sample.evidence_ledger_json === "object" && sample.evidence_ledger_json
      ? (sample.evidence_ledger_json as Record<string, unknown>)
      : {};
  const title = sample ? String(sample.title ?? sample.problem_code ?? "Проблема товара") : null;
  const recommendation = sample
    ? String(sample.recommendation ?? "—")
    : null;
  const explanation = sample
    ? String(sample.explanation ?? "—")
    : null;
  const impactType = sample ? String(sample.impact_type ?? "system_warning") : null;
  const trust = sample ? String(sample.trust_state ?? "provisional") : null;
  const severity = sample ? String(sample.severity ?? "medium") : null;
  const nmId = sample ? String(sample.nm_id ?? "—") : null;
  const formulaHuman = String((evidence as Record<string, unknown>).formula_human ?? "").trim();
  const category = sample ? String(sample.category ?? "") : "";
  const isDataBlocker = impactType === "data_blocker";
  const isMoney =
    impactType === "confirmed_loss" ||
    impactType === "probable_loss" ||
    impactType === "blocked_cash" ||
    impactType === "lost_sales_risk";

  const surfaces: Array<{
    key: string;
    title: string;
    hint: string;
    applies: boolean;
    body: ReactNode;
  }> = [
    {
      key: "action-center",
      title: "A. Строка Action Center",
      hint: "Как проблема появится в списке задач продавца.",
      applies: true,
      body: sample ? (
        <div className="space-y-1 text-[11px]">
          <div className="font-medium">{title}</div>
          <div className="text-muted-foreground">
            severity: {severity} · trust: {trust} · impact: {impactType}
          </div>
          <div className="text-muted-foreground">{explanation}</div>
          <div className="text-muted-foreground italic">
            Статус и результат — плейсхолдеры до апдейта.
          </div>
        </div>
      ) : (
        <PreviewPending />
      ),
    },
    {
      key: "product360",
      title: "B. Карточка Product360",
      hint: "Проблема встраивается в карточку товара.",
      applies: true,
      body: sample ? (
        <div className="space-y-1 text-[11px]">
          <div className="text-muted-foreground">
            nmID {nmId} · категория {category || "—"}
          </div>
          <div className="font-medium">{title}</div>
          <div className="text-muted-foreground">Рекомендация: {recommendation}</div>
          <div className="text-muted-foreground italic">
            «Открыть задачу» — плейсхолдер.
          </div>
        </div>
      ) : (
        <PreviewPending />
      ),
    },
    {
      key: "data-fix",
      title: "C. Карточка Data Fix",
      hint: "Показывается только для правил с блокером данных.",
      applies: isDataBlocker,
      body: sample && isDataBlocker ? (
        <div className="space-y-1 text-[11px]">
          <div className="font-medium">{title}</div>
          <div className="text-muted-foreground">
            Тип блокера: {impactType}
          </div>
          <div className="text-muted-foreground italic">
            Затронутые строки — плейсхолдер.
          </div>
        </div>
      ) : sample ? (
        <NotApplicable />
      ) : (
        <PreviewPending />
      ),
    },
    {
      key: "money",
      title: "D. Карточка Money",
      hint: "Показывается только для финансовых правил.",
      applies: isMoney,
      body: sample && isMoney ? (
        <div className="space-y-1 text-[11px]">
          <div className="font-medium">{title}</div>
          <div className="text-muted-foreground">
            trust: {trust} · impact: {impactType}
          </div>
          <div className="text-muted-foreground">
            Ожидаемый эффект: {String(sample.impact_amount ?? "—")}
          </div>
          <div className="text-muted-foreground italic">
            Без утверждений «сэкономлено» — только ожидаемый эффект.
          </div>
        </div>
      ) : sample ? (
        <NotApplicable />
      ) : (
        <PreviewPending />
      ),
    },
    {
      key: "results",
      title: "E. Плитка Results",
      hint: "После апдейта результат правила виден в ленте «Что изменилось».",
      applies: true,
      body: sample ? (
        <div className="space-y-1 text-[11px]">
          <div className="text-muted-foreground">Ждём данных после апдейта.</div>
          <div className="text-muted-foreground">
            Ожидаемый эффект ≠ измеренный результат.
          </div>
          {formulaHuman ? (
            <div className="text-muted-foreground italic">{formulaHuman}</div>
          ) : null}
          <div className="text-muted-foreground italic">
            Дисклеймер по корреляции — плейсхолдер.
          </div>
        </div>
      ) : (
        <PreviewPending />
      ),
    },
  ];

  return (
    <Card>
      <CardContent className="p-4 space-y-3">
        <div className="flex items-center gap-2">
          <Sparkles className="h-4 w-4 text-primary" />
          <div className="text-sm font-medium">
            10. Seller preview — 5 поверхностей
          </div>
          <Badge variant="outline" className="ml-auto">
            Это preview. Проблема ещё не создана для продавцов.
          </Badge>
        </div>
        <div className="text-xs text-muted-foreground">
          Данные формируются из первой карточки-примера тестового прогона
          (backtest.sample_issues[0]). Если поверхность не применяется к типу
          правила — отобразится соответствующая пометка.
        </div>
        {!sample ? (
          <EmptyState
            variant="no_data"
            title="Backtest ещё не запускался"
            hint="Запустите проверку на исторических данных перед публикацией."
          />
        ) : null}
        <div className="grid gap-2 md:grid-cols-2 xl:grid-cols-5">
          {surfaces.map((s) => (
            <div key={s.key} className="rounded-md border p-3 bg-muted/20">
              <div className="text-xs font-medium">{s.title}</div>
              <div className="mt-1 text-[11px] text-muted-foreground leading-snug">
                {s.hint}
              </div>
              <div className="mt-2">{s.body}</div>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

function PreviewPending() {
  return (
    <div className="text-[11px] text-muted-foreground italic">
      Пример появится после тестового прогона.
    </div>
  );
}

function NotApplicable() {
  return (
    <div className="text-[11px] text-muted-foreground italic">
      Не применяется к этому типу правила.
    </div>
  );
}

// -----------------------------------------------------------------------------
// 3. Publish safety checklist — explicit blocker categories
// -----------------------------------------------------------------------------

function PublishSafetyChecklist() {
  const items = [
    {
      key: "dangerous_action",
      title: "Опасное действие",
      hint: "Если действие меняет цену, промо или объём поставки — обязательно должно быть предпросмотром/подтверждением, а не автоприменением.",
    },
    {
      key: "price_promo_evidence",
      title: "Доказательства цены и промо",
      hint: "Для правил с ценой или промо обязательно ссылки на прежнюю цену, комиссии и минимально допустимую цену.",
    },
    {
      key: "too_many_matches",
      title: "Слишком широкий охват",
      hint: "Если тестовый прогон нашёл более 20% карточек, требуется явное подтверждение с причиной.",
    },
    {
      key: "test_only_visibility",
      title: "Конфликт видимости test-only",
      hint: "Правило со статусом «Только тест» нельзя публиковать как видимое селлеру.",
    },
    {
      key: "missing_metric_rate",
      title: "Пропуски метрик",
      hint: "Если у более 30% карточек не хватает нужной метрики, надёжность результата под вопросом.",
    },
  ];

  return (
    <Card>
      <CardContent className="p-4 space-y-3">
        <div className="flex items-center gap-2">
          <ShieldCheck className="h-4 w-4 text-warning" />
          <div className="text-sm font-medium">
            Дополнительные блокеры публикации
          </div>
        </div>
        <div className="text-xs text-muted-foreground">
          Перед публикацией правило проверяется на эти условия. Часть проверок
          выполняется в блоке публикации выше, часть — вручную ответственным
          администратором.
        </div>
        <div className="grid gap-2 md:grid-cols-2 xl:grid-cols-3">
          {items.map((item) => (
            <div key={item.key} className="rounded-md border p-3">
              <div className="flex items-center gap-2 text-xs font-medium">
                <AlertTriangle className="h-3.5 w-3.5 text-warning" />
                {item.title}
              </div>
              <div className="mt-1 text-[11px] text-muted-foreground leading-snug">
                {item.hint}
              </div>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

// -----------------------------------------------------------------------------
// 4. Rule detail extras — backtest history & generated problems
// -----------------------------------------------------------------------------

function RuleDetailExtras() {
  return (
    <div className="grid gap-3 md:grid-cols-3">
      <Card>
        <CardContent className="p-4 space-y-3">
          <div className="flex items-center gap-2">
            <History className="h-4 w-4 text-muted-foreground" />
            <div className="text-sm font-medium">История backtest</div>
            <Badge variant="secondary" className="ml-auto">
              <PauseCircle className="h-3 w-3 mr-1" /> недоступно
            </Badge>
          </div>
          <EmptyState
            variant="missing_data"
            title="История backtest пока не сохраняется"
            hint="История backtest будет доступна после подключения API истории."
          />
        </CardContent>
      </Card>
      <Card>
        <CardContent className="p-4 space-y-3">
          <div className="flex items-center gap-2">
            <ListChecks className="h-4 w-4 text-muted-foreground" />
            <div className="text-sm font-medium">
              Проблемы, созданные правилом
            </div>
            <Badge variant="secondary" className="ml-auto">
              <Wallet className="h-3 w-3 mr-1" /> недоступно
            </Badge>
          </div>
          <EmptyState
            variant="missing_data"
            title="Список сгенерированных проблем пока не доступен"
            hint="Список сгенерированных проблем будет доступен после подключения API."
          />
        </CardContent>
      </Card>
      <Card>
        <CardContent className="p-4 space-y-3">
          <div className="flex items-center gap-2">
            <AlertTriangle className="h-4 w-4 text-muted-foreground" />
            <div className="text-sm font-medium">
              Доля отклонений и ложных срабатываний
            </div>
            <Badge variant="secondary" className="ml-auto">
              <PauseCircle className="h-3 w-3 mr-1" /> недоступно
            </Badge>
          </div>
          <EmptyState
            variant="missing_data"
            title="Показатели пока не считаются"
            hint="Доля отклонений появится после накопления истории."
          />
        </CardContent>
      </Card>
    </div>
  );
}

// -----------------------------------------------------------------------------
// 5. Version compare — disabled placeholder
// -----------------------------------------------------------------------------

function VersionComparePlaceholder() {
  return (
    <Card>
      <CardContent className="p-4 space-y-3">
        <div className="flex items-center gap-2">
          <Layers className="h-4 w-4 text-muted-foreground" />
          <div className="text-sm font-medium">Сравнение версий правила</div>
          <Badge variant="secondary" className="ml-auto">
            <PauseCircle className="h-3 w-3 mr-1" /> недоступно
          </Badge>
        </div>
        <EmptyState
          variant="disabled"
          title="Сравнение версий будет доступно позже"
          hint="Diff между версиями (условие, формула влияния, доказательства, действия) появится после появления эндпоинта /admin/problem-rules/definitions/{id}/versions/compare. Пока используйте журнал изменений."
        />
      </CardContent>
    </Card>
  );
}
