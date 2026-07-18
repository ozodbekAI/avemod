// @ts-nocheck
import { Link } from "@tanstack/react-router";
import type { ReactNode } from "react";
import {
  AlertTriangle,
  ArrowRight,
  CalendarClock,
  CheckCircle2,
  ExternalLink,
  Info,
  Lock,
  RefreshCw,
  Save,
  TrendingDown,
  TrendingUp,
  Wrench,
} from "lucide-react";
import { EvidenceButton } from "@/components/EvidenceDrawer";
import {
  EvidenceTrustBadge,
  MoneyTrustBadge,
} from "@/components/MoneyTrustBadge";
import {
  ActionCenterEvidenceControls,
  DataFreshnessBadge,
  EVIDENCE_STATE_CLASS,
  EvidenceStateBadge,
  InfoBlock,
} from "@/components/action-center/ActionCenterEvidenceControls";
import { ActionCenterTaskDrawer } from "@/components/action-center/ActionCenterTaskDrawer";
import { ProblemBadgeRow } from "@/components/problem/SellerProblemUX";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import {
  actionRequirementText,
  allowedActionLabel,
  primaryActionForItem,
  renderableActionFromItem,
  type ActionDraft,
  type RecheckResult,
  type RenderableAction,
} from "@/lib/action-center-actions";
import {
  PRIO_COLORS,
  canUpdateReasonLabel,
  priorityLabel,
  sourceModuleLabel,
  sourceSyncStateLabel,
} from "@/lib/action-center-labels";
import {
  actionAllowedActions,
  actionEvidenceLedger,
  actionProductIdentity,
  actionRecheckRule,
  formatDeadline,
  isClaimsAction,
  isOverdueAction,
  isProblemLikeAction,
  statusOptionsForAction,
} from "@/lib/action-center-status";
import {
  formatResultDate,
  latestRecheckEventFromPage,
  metricDeltaLabel,
  metricValueLabel,
  problemResultTimelineLabel,
  problemResultTimelineMessage,
  resultEventsFromPage,
  resultPageHasCanonicalData,
  resultStatusFromSummary,
  resultTimelineData,
  resultsLinkSearch,
  type ResultMetricRow,
} from "@/lib/action-center-results";
import {
  firstText,
  formatMoneyField,
  moneyValue,
} from "@/lib/action-center-utils";
import { formatMoney } from "@/lib/format";
import type {
  ActionCenterItem,
  ActionCenterSolveMapStep,
} from "@/lib/action-center-contract";
import {
  dataFreshnessBlockingLabel,
  dataFreshnessBlocksAction,
} from "@/lib/action-center-contract";
import type { EvidenceLedger } from "@/lib/evidence";
import { evidenceTrustLabel, evidenceTrustStateFrom } from "@/lib/money-trust";
import type {
  PortalAssignableUser,
  PortalResultEventsPage,
} from "@/lib/portal";
import {
  problemImpactLabel,
  problemRecheckStatusLabel,
  problemResultStatusLabel,
  problemStatusLabel,
  problemTrustLabel,
} from "@/lib/problem-ux-copy";
import {
  PROBLEM_RESULT_CORRELATION_DISCLAIMER,
  problemResultTimelineStoryFromEvents,
} from "@/lib/problem-results";
import { sellerSafeMessage } from "@/lib/results-i18n";

type StatusOption = ReturnType<typeof statusOptionsForAction>[number];
type AllowedActionItem = ActionCenterItem["allowed_action_items"][number];

type ActionDrawerSectionProps = {
  title: string;
  description?: string;
  children: ReactNode;
};

export function ActionDrawerSection({
  title,
  description,
  children,
}: ActionDrawerSectionProps) {
  return (
    <section className="rounded-md border p-3 space-y-3 sm:p-4">
      <div>
        <div className="text-sm font-semibold">{title}</div>
        {description ? (
          <div className="mt-1 text-xs text-muted-foreground">
            {description}
          </div>
        ) : null}
      </div>
      {children}
    </section>
  );
}

export function ActionDrawerHeader({ title }: { title?: string | null }) {
  return (
    <div className="shrink-0 border-b px-4 py-4 pr-12 sm:border-b-0 sm:px-0 sm:py-0">
      <SheetHeader className="text-left" aria-label="Header">
        <SheetTitle className="line-clamp-2 leading-snug">
          {title ?? "Действие"}
        </SheetTitle>
        <SheetDescription>
          Единая карточка задачи: проблема, доказательства, действие,
          ответственный, история, перепроверка и результат.
        </SheetDescription>
      </SheetHeader>
    </div>
  );
}

function guideToneClass(tone: "ready" | "warning" | "blocked") {
  if (tone === "ready") return "border-success/30 bg-success/[0.06]";
  if (tone === "blocked") return "border-destructive/30 bg-destructive/[0.05]";
  return "border-warning/35 bg-warning/[0.06]";
}

function guideIconClass(tone: "ready" | "warning" | "blocked") {
  if (tone === "ready") return "bg-success/10 text-success";
  if (tone === "blocked") return "bg-destructive/10 text-destructive";
  return "bg-warning/10 text-warning";
}

function solveStepTone(
  step: ActionCenterSolveMapStep,
): "ready" | "warning" | "blocked" {
  if (step.status === "blocked") return "blocked";
  if (step.status === "waiting_for_data") return "warning";
  return "ready";
}

function solveStepStatusLabel(step: ActionCenterSolveMapStep): string {
  if (step.status === "done") return "Готово";
  if (step.status === "ready") return "Готово";
  if (step.status === "available") return "Можно открыть";
  if (step.status === "waiting_for_data") return "Нужна синхронизация";
  return "Недоступно";
}

type FallbackStep = { title: string; detail: string };

const PROBLEM_SOLVE_MAP_FALLBACK: Record<string, FallbackStep[]> = {
  missing_cost_blocks_profit: [
    { title: "Проверить доказательства", detail: "Откройте «Как посчитано?» — какие данные о себестоимости отсутствуют." },
    { title: "Открыть исправление данных", detail: "Перейдите в раздел исправления данных с контекстом задачи." },
    { title: "Загрузить или сопоставить себестоимость", detail: "Заполните недостающую себестоимость или свяжите SKU." },
    { title: "Перепроверить прибыльность", detail: "Запустите повторную проверку и дождитесь свежих данных." },
  ],
  negative_unit_profit: [
    { title: "Посмотреть расчёт маржи", detail: "Откройте разложение цены → комиссии → логистика → реклама." },
    { title: "Проверить себестоимость, комиссии, логистику, рекламу и промо", detail: "Найдите статью, которая делает маржу отрицательной." },
    { title: "Открыть проверку цены", detail: "Скорректируйте цену или создайте задачу менеджеру." },
    { title: "Перепроверить маржу после изменений", detail: "Запустите перепроверку и сравните до/после." },
  ],
  overstock_slow_moving: [
    { title: "Проверить остаток и скорость продаж", detail: "Оцените дни запаса и текущую воронку." },
    { title: "Проверить безопасную цену и маржу", detail: "Промо и цена меняются только после расчёта безопасной цены." },
    { title: "Настроить промо или проверить карточку", detail: "Если промо небезопасно, сначала улучшите карточку." },
    { title: "Перепроверить дни запаса и скорость продаж", detail: "Дождитесь свежих продаж и запустите перепроверку." },
  ],
  low_stock_risk: [
    { title: "Проверить остаток и дни запаса", detail: "Уточните критичные SKU и текущий поток продаж." },
    { title: "Открыть план поставки", detail: "Сформируйте поставку с учётом дней запаса." },
    { title: "Назначить ответственного и срок", detail: "Зафиксируйте кто и когда закрывает задачу." },
    { title: "Перепроверить остатки после синхронизации", detail: "Дождитесь свежих остатков и запустите перепроверку." },
  ],
  ads_spend_without_profit: [
    { title: "Проверить расходы на рекламу и прибыль после рекламы", detail: "Оцените ROMI и вклад рекламы в маржу." },
    { title: "Открыть рекламу", detail: "Перейдите в раздел рекламы с контекстом задачи." },
    { title: "Снизить ставку, остановить кампанию или запустить проверку карточки", detail: "Выберите безопасное действие в зависимости от причины." },
    { title: "Перепроверить прибыль после рекламы", detail: "Запустите перепроверку после изменений." },
  ],
  promo_not_profitable: [
    { title: "Проверить цену промо и маржу", detail: "Откройте разложение и оцените маржу при промо-цене." },
    { title: "Проверить безопасную цену", detail: "Убедитесь, что промо не уводит цену ниже безопасной." },
    { title: "Изменить или остановить промо", detail: "Скорректируйте условия или отключите промо." },
    { title: "Перепроверить маржу и продажи", detail: "Запустите перепроверку и сравните до/после." },
  ],
  price_below_safe_margin: [
    { title: "Проверить расчёт безопасной цены", detail: "Откройте «Как посчитано?» — как получена безопасная цена." },
    { title: "Открыть проверку цены", detail: "Перейдите к сценарию изменения цены." },
    { title: "Обновить цену или создать задачу менеджеру", detail: "Зафиксируйте новое значение или поручите смену." },
    { title: "Перепроверить маржу", detail: "Дождитесь свежих данных и запустите перепроверку." },
  ],
  dead_stock: [
    { title: "Проверить остаток и продажи", detail: "Убедитесь, что продажи действительно остановились." },
    { title: "Запустить проверку карточки", detail: "Проверьте карточку и рекомендации по улучшению." },
    { title: "Проверить промо/цену только если маржа безопасна", detail: "Не двигайте цену вниз, если маржа уже критична." },
    { title: "Перепроверить продажи и остаток", detail: "Дождитесь свежих данных и запустите перепроверку." },
  ],
};

export function problemSolveMapFallbackSteps(
  problemCode: string | null | undefined,
): FallbackStep[] | null {
  const code = String(problemCode ?? "").trim().toLowerCase();
  if (!code) return null;
  if (PROBLEM_SOLVE_MAP_FALLBACK[code]) return PROBLEM_SOLVE_MAP_FALLBACK[code];
  if (
    code.startsWith("checker_") ||
    code.startsWith("card_quality") ||
    code.includes("card_quality")
  ) {
    return [
      { title: "Проверить проблему карточки", detail: "Откройте задачу и убедитесь, в каком поле карточки нарушение." },
      { title: "Посмотреть рекомендацию и доказательства", detail: "Изучите «Как посчитано?» и рекомендуемое изменение." },
      { title: "Сделать локальное исправление или предпросмотр", detail: "Внесите правку с предпросмотром до отправки в WB." },
      { title: "Отправить в WB через подтверждение", detail: "Публикация возможна только через явное подтверждение." },
      { title: "Перепроверить карточку", detail: "Запустите повторную проверку карточки после публикации." },
    ];
  }
  return null;
}

function ActionDrawerSolveMap({
  action: a,
  primaryAction,
  firstBlockedAction,
  showRecheck,
  readOnlyReason,
}: {
  action: ActionCenterItem;
  primaryAction: RenderableAction | null;
  firstBlockedAction: AllowedActionItem | null;
  showRecheck: boolean;
  readOnlyReason: string | null;
}) {
  const solveMap = a.solve_map;
  if (solveMap?.steps.length) {
    const steps = solveMap.steps
      .slice()
      .sort((left, right) => left.order - right.order);
    return (
      <ActionDrawerSection
        title="F. Карта решения"
        description={
          solveMap.summary ||
          "Проблемный маршрут: доказательства, рабочий экран, фиксация действия и перепроверка."
        }
      >
        <div className="grid gap-2 sm:grid-cols-2">
          {steps.map((step) => {
            const tone = solveStepTone(step);
            const actionHref =
              step.target_href &&
              (step.status === "available" || step.status === "ready")
                ? step.target_href
                : null;
            return (
              <div
                key={step.step_id}
                className={`flex min-h-[128px] gap-3 rounded-md border p-3 ${guideToneClass(tone)}`}
              >
                <div
                  className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-xs font-semibold ${guideIconClass(tone)}`}
                >
                  {tone === "ready" ? (
                    <CheckCircle2 className="h-4 w-4" />
                  ) : (
                    step.order
                  )}
                </div>
                <div className="min-w-0 space-y-2">
                  <div>
                    <div className="flex flex-wrap items-center gap-2">
                      <div className="text-sm font-medium leading-snug">
                        {step.title}
                      </div>
                      <Badge variant="outline" className="text-[11px]">
                        {solveStepStatusLabel(step)}
                      </Badge>
                    </div>
                    <div className="mt-1 line-clamp-3 break-words text-xs text-muted-foreground">
                      {step.description}
                    </div>
                  </div>
                  {step.blocking_reason ? (
                    <div className="rounded-md border border-warning/30 bg-warning/[0.06] px-2 py-1 text-xs text-warning-foreground">
                      {step.blocking_reason}
                    </div>
                  ) : null}
                  {step.required_metrics.length ? (
                    <div className="flex flex-wrap gap-1">
                      {step.required_metrics.slice(0, 4).map((metric) => (
                        <Badge
                          key={metric}
                          variant="secondary"
                          className="text-[11px]"
                        >
                          {metric}
                        </Badge>
                      ))}
                    </div>
                  ) : null}
                  {step.completion_signal ? (
                    <div className="text-[11px] text-muted-foreground">
                      Сигнал готовности: {step.completion_signal}
                    </div>
                  ) : null}
                  {actionHref ? (
                    <Button
                      asChild
                      size="sm"
                      variant="outline"
                      className="h-8 w-fit"
                    >
                      <Link to={actionHref}>
                        <ArrowRight className="mr-2 h-3.5 w-3.5" />
                        Открыть
                      </Link>
                    </Button>
                  ) : null}
                </div>
              </div>
            );
          })}
        </div>
      </ActionDrawerSection>
    );
  }

  const freshnessBlocked = dataFreshnessBlocksAction(a.data_freshness);
  const evidenceReady =
    a.evidence_state === "full_evidence" && !freshnessBlocked;
  const problemLike = isProblemLikeAction(a);
  const blockedLabel = firstBlockedAction
    ? allowedActionLabel(firstBlockedAction.code)
    : null;
  const blockedReason =
    firstBlockedAction?.disabled_reason ??
    (firstBlockedAction ? actionRequirementText(firstBlockedAction) : null);
  const actionTone = primaryAction
    ? "ready"
    : firstBlockedAction || readOnlyReason
      ? "blocked"
      : "warning";

  const problemCode = String(a.problem_code ?? a.issue_code ?? "")
    .trim()
    .toLowerCase();
  const problemFallback = problemSolveMapFallbackSteps(problemCode);

  const steps = problemFallback
    ? problemFallback.map((step, idx) => ({
        key: `p-${idx}`,
        label: String(idx + 1),
        title: step.title,
        detail: step.detail,
        tone:
          idx === 0
            ? evidenceReady
              ? "ready"
              : "warning"
            : idx === problemFallback.length - 1
              ? showRecheck
                ? "ready"
                : "warning"
              : idx === 1 && primaryAction
                ? "ready"
                : "warning",
      }))
    : ([
        {
          key: "evidence",
          label: "1",
          title: evidenceReady
            ? "Доказательства готовы"
            : freshnessBlocked
              ? "Обновите источники"
              : "Проверить доказательства",
          detail: evidenceReady
            ? "Формула, факты и источники доступны в «Как посчитано?»."
            : freshnessBlocked
              ? dataFreshnessBlockingLabel(a.data_freshness)
              : "Перед действием откройте «Как посчитано?» и проверьте недостающие данные.",
          tone: evidenceReady ? "ready" : "warning",
        },
        {
          key: "action",
          label: "2",
          title: primaryAction
            ? `Сделайте: ${primaryAction.label}`
            : blockedLabel
              ? `${blockedLabel} недоступно`
              : "Создать задачу",
          detail: primaryAction
            ? "Откройте рабочий экран, выполните действие и вернитесь к задаче."
            : (blockedReason ??
              readOnlyReason ??
              "Назначьте ответственного и уточните данные перед действием."),
          tone: actionTone,
        },
        {
          key: "assign",
          label: "3",
          title: "Назначить ответственного",
          detail: a.can_update
            ? "Зафиксируйте статус, ответственного и срок в разделах ниже."
            : (readOnlyReason ??
              "Источник нельзя обновить напрямую, состояние ведётся как сигнал."),
          tone: a.can_update ? "ready" : "warning",
        },
        {
          key: "result",
          label: "4",
          title: showRecheck
            ? "Перепроверить результат"
            : "Дождаться результата",
          detail: showRecheck
            ? "Запустите повторную проверку и откройте журнал для сравнения «до/после»."
            : problemLike
              ? "Результат появится после свежих данных и события в журнале."
              : "Для этого действия результат зависит от связанного модуля.",
          tone: showRecheck ? "ready" : "warning",
        },
      ] as const);


  return (
    <ActionDrawerSection
      title="F. Карта решения"
      description="Короткий путь от причины до результата, чтобы не искать следующий шаг по всему экрану."
    >
      <div className="grid gap-2 sm:grid-cols-2">
        {steps.map((step) => {
          const tone = step.tone;
          return (
            <div
              key={step.key}
              className={`flex min-h-[104px] gap-3 rounded-md border p-3 ${guideToneClass(tone)}`}
            >
              <div
                className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-xs font-semibold ${guideIconClass(tone)}`}
              >
                {tone === "ready" ? (
                  <CheckCircle2 className="h-4 w-4" />
                ) : (
                  step.label
                )}
              </div>
              <div className="min-w-0">
                <div className="text-sm font-medium leading-snug">
                  {step.title}
                </div>
                <div className="mt-1 line-clamp-3 break-words text-xs text-muted-foreground">
                  {step.detail}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </ActionDrawerSection>
  );
}

export function ActionDrawerProblemStory({
  action: a,
  claimsLocked,
  onOpenEvidence,
}: {
  action: ActionCenterItem;
  claimsLocked: boolean;
  onOpenEvidence: (title: string, ledger: EvidenceLedger | null) => void;
}) {
  const problemLike = isProblemLikeAction(a);
  const actionLedger = actionEvidenceLedger(a);
  const whyNow = firstText(a.short_explanation, a.reason, a.summary);
  const moneyTrust = a.money_trust;
  const productIdentity = actionProductIdentity(a);

  return (
    <>
      <section className="rounded-md border p-3 space-y-3 sm:p-4">
        <div className="flex flex-wrap items-center gap-2">
          {a.priority ? (
            <Badge variant="outline" className={PRIO_COLORS[a.priority] ?? ""}>
              {priorityLabel(a.priority)}
            </Badge>
          ) : null}
          {a.source_module ? (
            <Badge variant="outline">
              {sourceModuleLabel(a.source_module)}
            </Badge>
          ) : null}
          {a.status ? (
            <Badge variant="secondary">{a.status_label}</Badge>
          ) : null}
          <MoneyTrustBadge trust={moneyTrust} contextLabel="Тип влияния" />
          <EvidenceTrustBadge
            trust={moneyTrust}
            fallback={actionLedger}
            contextLabel="Доверие к данным"
          />
          <DataFreshnessBadge freshness={a.data_freshness} />
          {a.impact_type ? (
            <Badge variant="outline">{problemImpactLabel(a.impact_type)}</Badge>
          ) : null}
          {a.trust_state ? (
            <Badge variant="outline">{problemTrustLabel(a.trust_state)}</Badge>
          ) : null}
          <EvidenceStateBadge state={a.evidence_state} />
          {a.is_beta || a.is_test_only ? (
            <Badge variant="outline" className="border-warning/40 text-warning">
              Бета/тест
            </Badge>
          ) : null}
          {problemLike ? (
            <ProblemBadgeRow problem={a} ledger={actionLedger} />
          ) : null}
        </div>
        <div className="grid gap-2 text-xs sm:grid-cols-2">
          <InfoBlock
            label="Товар"
            value={productIdentity || "Товар не указан"}
          />
          <InfoBlock
            label="Источник"
            value={a.source_module ? sourceModuleLabel(a.source_module) : "—"}
          />
          <InfoBlock
            label="Приоритет"
            value={`${a.priority ? priorityLabel(a.priority) : "—"} / ${
              a.severity ?? "—"
            }`}
          />
          <InfoBlock
            label="Код проблемы"
            value={a.problem_code ?? a.detector_code ?? a.issue_code}
          />
          <InfoBlock
            label="Синхронизация"
            value={sourceSyncStateLabel(a.source_sync_state)}
          />
          <InfoBlock
            label="Свежесть источников"
            value={dataFreshnessBlockingLabel(a.data_freshness)}
          />
        </div>
      </section>

      <ActionDrawerSection title="A. Что произошло?">
        <div className="text-sm text-muted-foreground">
          {whyNow ??
            "Причина не передана. Проверьте связанный экран исправления."}
        </div>
      </ActionDrawerSection>

      <ActionDrawerSection title="B. Почему платформа так решила?">
        <ActionCenterEvidenceControls
          ledger={actionLedger}
          state={a.evidence_state}
          freshness={a.data_freshness}
          trustLabel={
            evidenceTrustLabel(
              evidenceTrustStateFrom(moneyTrust, actionLedger),
            ) ??
            (a.trust_state
              ? problemTrustLabel(a.trust_state)
              : moneyTrust.display_label)
          }
        />
        {a.evidence_state === "full_evidence" && actionLedger ? (
          <EvidenceButton
            ledger={actionLedger}
            onClick={() => onOpenEvidence(a.title ?? "Действие", actionLedger)}
          />
        ) : (
          <Button
            size="sm"
            variant="outline"
            className={`min-h-10 text-xs sm:min-h-8 ${EVIDENCE_STATE_CLASS[a.evidence_state]}`}
            onClick={() => onOpenEvidence(a.title ?? "Действие", actionLedger)}
          >
            <AlertTriangle className="mr-1 h-3.5 w-3.5" />
            {a.evidence_state === "read_only_signal"
              ? "Только сигнал"
              : "Доказательств недостаточно"}
          </Button>
        )}
      </ActionDrawerSection>

      <ActionDrawerSection title="C. На что влияет?">
        <div className="grid gap-2 text-xs sm:grid-cols-2">
          <InfoBlock
            label="Сумма влияния"
            value={formatMoneyField(moneyValue(a))}
          />
          <InfoBlock
            label="Тип влияния"
            value={a.impact_type ? problemImpactLabel(a.impact_type) : "—"}
          />
          <InfoBlock
            label="Доверие к сумме"
            value={`${moneyTrust.amount_label}: ${
              moneyTrust.reason ?? moneyTrust.display_label
            }`}
            wide
          />
        </div>
        <Alert>
          <Info className="h-4 w-4" />
          <AlertTitle>Это не подтверждённый денежный результат</AlertTitle>
          <AlertDescription>
            Ожидаемый риск или возможность показываются отдельно.{" "}
            {
              "Окна «до/после» показывают корреляцию, а не гарантированную причинность."
            }
            Денежный результат можно назвать результатом только после
            измеренного сравнения «до/после».
          </AlertDescription>
        </Alert>
      </ActionDrawerSection>

      <ActionDrawerSection
        title="D. Это факт или оценка?"
        description="Сначала смотрим, насколько данным можно доверять: подтверждённые факты или предварительная оценка. Ожидаемый эффект — это оценка, а не сохранённая сумма."
      >
        <div className="flex flex-wrap items-center gap-2">
          <Badge
            variant="outline"
            className={
              a.evidence_state === "full_evidence"
                ? "border-success/30 text-success"
                : a.evidence_state === "read_only_signal"
                  ? "border-muted-foreground/30 text-muted-foreground"
                  : "border-warning/40 text-warning"
            }
          >
            {a.evidence_state === "full_evidence"
              ? "Факты подтверждены"
              : a.evidence_state === "partial_evidence"
                ? "Частичные доказательства"
                : a.evidence_state === "missing_evidence"
                  ? "Доказательств недостаточно"
                  : "Только сигнал"}
          </Badge>
          {a.trust_state ? (
            <Badge variant="outline" className="text-xs">
              Доверие: {problemTrustLabel(a.trust_state)}
            </Badge>
          ) : null}
          {moneyTrust ? (
            <Badge variant="outline" className="text-xs">
              {moneyTrust.amount_label}
              {moneyTrust.display_label
                ? ` · ${moneyTrust.display_label}`
                : ""}
            </Badge>
          ) : null}
        </div>
        <div className="text-xs text-muted-foreground">
          {a.evidence_state === "full_evidence"
            ? "Расчёт опирается на полные данные из журналов. Сумма влияния всё равно остаётся оценкой до подтверждения после действия."
            : "Данных пока недостаточно для окончательного вывода. Проверьте «Как посчитано?» и заполните пропуски перед действием."}
        </div>
      </ActionDrawerSection>
    </>
  );
}

export function ActionDrawerAllowedActions({
  action: a,
  primaryAction,
  allowedActionButtons,
  readOnlyReason,
}: {
  action: ActionCenterItem;
  primaryAction: RenderableAction | null;
  allowedActionButtons: RenderableAction[];
  readOnlyReason: string | null;
}) {
  const exactNextStep = firstText(
    a.next_step,
    primaryAction?.label,
    primaryAction?.href
      ? "Откройте связанный экран и выполните подсвеченное действие."
      : null,
  );

  return (
    <ActionDrawerSection title="E. Что сделать сейчас?">
      <div className="text-sm text-muted-foreground">
        {exactNextStep ??
          "Откройте связанный экран и выполните первое рекомендованное действие."}
      </div>
      <div className="flex flex-wrap gap-2">
        {primaryAction?.href ? (
          primaryAction.external ? (
            <Button asChild size="sm" className="min-h-10 sm:min-h-8">
              <a href={primaryAction.href} target="_blank" rel="noreferrer">
                <Wrench className="h-3.5 w-3.5 mr-1.5" />
                {primaryAction.label}
                <ExternalLink className="h-3.5 w-3.5 ml-1.5" />
              </a>
            </Button>
          ) : (
            <Button asChild size="sm" className="min-h-10 sm:min-h-8">
              <Link to={primaryAction.href}>
                <Wrench className="h-3.5 w-3.5 mr-1.5" />
                {primaryAction.label}
              </Link>
            </Button>
          )
        ) : null}
        {allowedActionButtons.map((item) =>
          item.enabled ? (
            <Button
              asChild
              key={item.code}
              size="sm"
              variant="outline"
              className="min-h-10 sm:min-h-8"
            >
              <Link to={item.href}>
                <Wrench className="h-3.5 w-3.5 mr-1.5" />
                {item.label}
              </Link>
            </Button>
          ) : (
            <TooltipProvider key={item.code}>
              <Tooltip>
                <TooltipTrigger asChild>
                  <span>
                    <Button
                      size="sm"
                      variant="outline"
                      className="min-h-10 sm:min-h-8"
                      disabled
                      aria-disabled="true"
                    >
                      <Lock className="h-3.5 w-3.5 mr-1.5" />
                      {item.label}
                    </Button>
                  </span>
                </TooltipTrigger>
                <TooltipContent className="max-w-xs text-xs">
                  {item.disabled_reason ?? "Действие сейчас недоступно."}
                  {actionRequirementText(item) ? (
                    <span className="mt-1 block">
                      {actionRequirementText(item)}
                    </span>
                  ) : null}
                </TooltipContent>
              </Tooltip>
            </TooltipProvider>
          ),
        )}
      </div>
      {a.allowed_action_items.some(
        (item) =>
          item.requires_preview ||
          item.requires_diff ||
          item.requires_confirm ||
          item.requires_audit,
      ) ? (
        <Alert>
          <Info className="h-4 w-4" />
          <AlertTitle>
            Маркетплейс-изменения только через безопасный шаг
          </AlertTitle>
          <AlertDescription>
            Потенциально опасные действия открывают рабочий экран, где нужен
            предпросмотр, сравнение изменений, подтверждение и запись в аудит.
          </AlertDescription>
        </Alert>
      ) : null}
      {readOnlyReason || (!primaryAction && !allowedActionButtons.length) ? (
        <Alert>
          <Info className="h-4 w-4" />
          <AlertTitle>Действие только для чтения</AlertTitle>
          <AlertDescription>
            {readOnlyReason ??
              "Для этого сигнала нет безопасного действия внутри платформы."}
          </AlertDescription>
        </Alert>
      ) : null}
    </ActionDrawerSection>
  );
}

export function ActionDrawerAssignmentDeadline({
  action: a,
  users,
  draft,
  saveDisabled,
  claimsLocked,
  readOnlyReason,
  now,
  onDraftChange,
}: {
  action: ActionCenterItem;
  users?: PortalAssignableUser[] | null;
  draft: ActionDraft;
  saveDisabled: boolean;
  claimsLocked: boolean;
  readOnlyReason: string | null;
  now: Date;
  onDraftChange: (patch: Partial<ActionDraft>) => void;
}) {
  const canUpdate = a.can_update;
  const deadline = formatDeadline(a, now);
  const overdue = isOverdueAction(a, now);

  return (
    <ActionDrawerSection title="G. Назначение и срок">
      {!canUpdate || claimsLocked ? (
        <Alert>
          <Info className="h-4 w-4" />
          <AlertTitle>Назначение недоступно</AlertTitle>
          <AlertDescription>
            {readOnlyReason ?? "У задачи нет безопасного пути обновления."}
          </AlertDescription>
        </Alert>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="space-y-1">
            <div className="text-xs font-medium">Ответственный</div>
            {users?.length ? (
              <Select
                value={draft.assigned_to_user_id || "__none__"}
                disabled={saveDisabled}
                onValueChange={(v) =>
                  onDraftChange({
                    assigned_to_user_id: v === "__none__" ? "" : v,
                  })
                }
              >
                <SelectTrigger
                  aria-label="Ответственный пользователь"
                  className="min-h-10"
                >
                  <SelectValue placeholder="Не назначен" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="__none__">Не назначен</SelectItem>
                  {users.map((u) => (
                    <SelectItem key={u.id} value={String(u.id)}>
                      {u.full_name || u.email || `Пользователь ${u.id}`}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            ) : (
              <Input
                type="number"
                min={1}
                value={draft.assigned_to_user_id}
                disabled={saveDisabled}
                onChange={(e) =>
                  onDraftChange({ assigned_to_user_id: e.target.value })
                }
                placeholder="ID пользователя"
                className="min-h-10"
              />
            )}
          </div>
          <div className="space-y-1">
            <div className="text-xs font-medium">Срок</div>
            <Input
              type="datetime-local"
              value={draft.deadline_at}
              disabled={saveDisabled}
              className="min-h-10"
              onChange={(e) => onDraftChange({ deadline_at: e.target.value })}
            />
          </div>
        </div>
      )}
      {overdue ? (
        <Alert variant="destructive">
          <CalendarClock className="h-4 w-4" />
          <AlertTitle>Срок просрочен</AlertTitle>
          <AlertDescription>
            Дедлайн был {deadline.label}. Обновите срок или передайте задачу
            ответственному.
          </AlertDescription>
        </Alert>
      ) : (
        <div className="text-xs text-muted-foreground">
          Текущий срок: {deadline.label}
        </div>
      )}
    </ActionDrawerSection>
  );
}

export function ActionDrawerStatusComment({
  action: a,
  draft,
  statusOptions,
  saveDisabled,
  claimsLocked,
  readOnlyReason,
  busy,
  rowKey,
  onDraftChange,
  onSave,
}: {
  action: ActionCenterItem;
  draft: ActionDraft;
  statusOptions: StatusOption[];
  saveDisabled: boolean;
  claimsLocked: boolean;
  readOnlyReason: string | null;
  busy: string | null;
  rowKey: string;
  onDraftChange: (patch: Partial<ActionDraft>) => void;
  onSave: () => void;
}) {
  const canUpdate = a.can_update;

  return (
    <ActionDrawerSection title="H. Статус и комментарий">
      {!canUpdate || claimsLocked ? (
        <Alert>
          <Info className="h-4 w-4" />
          <AlertTitle>Статус нельзя изменить</AlertTitle>
          <AlertDescription>
            {readOnlyReason ?? "У задачи нет безопасного пути обновления."}
          </AlertDescription>
        </Alert>
      ) : (
        <div className="grid gap-3">
          <div className="space-y-1">
            <div className="text-xs font-medium">Статус</div>
            <Select
              value={draft.status}
              disabled={saveDisabled}
              onValueChange={(v) => onDraftChange({ status: v })}
            >
              <SelectTrigger aria-label="Статус задачи" className="min-h-10">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {statusOptions.map((s) => (
                  <SelectItem key={s.value} value={s.value}>
                    {s.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1">
            <div className="text-xs font-medium">Комментарий</div>
            <Textarea
              value={draft.last_comment}
              disabled={saveDisabled}
              className="min-h-24"
              onChange={(e) => onDraftChange({ last_comment: e.target.value })}
              placeholder="Что сделали или кому передали"
            />
          </div>
          <Button disabled={saveDisabled} className="min-h-10" onClick={onSave}>
            <Save className="h-4 w-4 mr-1.5" />
            {busy === rowKey ? "Сохраняем" : "Сохранить"}
          </Button>
        </div>
      )}
    </ActionDrawerSection>
  );
}

function ActionCenterHistoryTimeline({
  action,
  resultPage,
  loading,
  error,
  recheckResult,
}: {
  action: ActionCenterItem;
  resultPage?: PortalResultEventsPage | null;
  loading?: boolean;
  error?: unknown;
  recheckResult?: RecheckResult;
}) {
  const sourceHistory = action.history_summary?.items ?? [];
  const resultEvents = resultEventsFromPage(resultPage);
  const rows = [
    ...sourceHistory.map((item, index) => {
      const label =
        item.new_status || item.status
          ? `Статус: ${problemStatusLabel(item.new_status ?? item.status)}`
          : item.event_type === "assignment_changed"
            ? "Назначение"
            : item.event_type === "deadline_changed"
              ? "Срок"
              : item.event_type === "recheck"
                ? "Повторная проверка"
                : item.comment
                  ? "Комментарий"
                  : "Событие";
      const statusMove =
        item.old_status || item.new_status
          ? `${problemStatusLabel(item.old_status)} → ${problemStatusLabel(
              item.new_status,
            )}`
          : null;
      return {
        key: `history-${index}`,
        label,
        at: item.created_at,
        detail: [statusMove, item.comment].filter(Boolean).join(" · "),
      };
    }),
    ...resultEvents.map((event) => ({
      key: `result-${event.id ?? event.event_type}-${event.created_at ?? ""}`,
      label: problemResultTimelineLabel(event.event_type),
      at: event.created_at,
      detail: [
        event.outcome
          ? problemResultStatusLabel(
              resultStatusFromSummary({ outcome: event.outcome }),
            )
          : null,
        problemResultTimelineMessage(event),
      ]
        .filter(Boolean)
        .join(" · "),
    })),
    ...(recheckResult
      ? [
          {
            key: "local-recheck",
            label: "Повторная проверка",
            at: recheckResult.checkedAt,
            detail: recheckResult.message,
          },
        ]
      : []),
  ]
    .filter((row) => row.label || row.detail)
    .sort(
      (a, b) =>
        new Date(String(b.at ?? "")).getTime() -
        new Date(String(a.at ?? "")).getTime(),
    );

  if (loading) {
    return (
      <div className="space-y-2">
        <Skeleton className="h-12 w-full" />
        <Skeleton className="h-12 w-full" />
      </div>
    );
  }

  const errorNotice = error ? (
    <Alert variant="destructive">
      <AlertTriangle className="h-4 w-4" />
      <AlertTitle>Историю результата не удалось загрузить</AlertTitle>
      <AlertDescription>
        {sellerSafeMessage(error, "Попробуйте обновить задачу позже.")}
      </AlertDescription>
    </Alert>
  ) : null;

  if (error && !rows.length) {
    return errorNotice;
  }

  if (!rows.length) {
    return (
      <Alert>
        <Info className="h-4 w-4" />
        <AlertTitle>История пока пустая</AlertTitle>
        <AlertDescription>
          События появятся после изменения статуса, назначения, комментария,
          перепроверки или записи результата.
        </AlertDescription>
      </Alert>
    );
  }

  return (
    <div className="space-y-2">
      {errorNotice}
      {rows.slice(0, 10).map((row) => (
        <div
          key={row.key}
          className="grid grid-cols-[128px_minmax(0,1fr)] gap-3 rounded-md border bg-background p-2 text-xs"
        >
          <div className="font-medium">{row.label}</div>
          <div className="min-w-0 text-muted-foreground">
            <div>{formatResultDate(row.at)}</div>
            {row.detail ? (
              <div className="mt-0.5 break-words">{row.detail}</div>
            ) : null}
          </div>
        </div>
      ))}
    </div>
  );
}

export function ActionDrawerHistory(
  props: Parameters<typeof ActionCenterHistoryTimeline>[0],
) {
  return <ActionCenterHistoryTimeline {...props} />;
}

function ResultBarPair({ metric }: { metric: ResultMetricRow }) {
  const max = Math.max(Math.abs(metric.before), Math.abs(metric.after), 1);
  const beforeWidth = Math.max(
    4,
    Math.round((Math.abs(metric.before) / max) * 100),
  );
  const afterWidth = Math.max(
    4,
    Math.round((Math.abs(metric.after) / max) * 100),
  );
  const improved = metric.direction === "improved" || metric.delta > 0;
  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between gap-3 text-xs">
        <span className="font-medium">{metric.label}</span>
        <span
          className={
            improved
              ? "text-success"
              : metric.delta < 0
                ? "text-destructive"
                : "text-muted-foreground"
          }
        >
          {metric.delta > 0 ? "+" : ""}
          {metricDeltaLabel(metric)}
        </span>
      </div>
      <div className="grid grid-cols-[52px_minmax(0,1fr)_96px] items-center gap-2 text-[11px]">
        <span className="text-muted-foreground">До</span>
        <div className="h-2 rounded bg-muted">
          <div
            className="h-2 rounded bg-muted-foreground/50"
            style={{ width: `${beforeWidth}%` }}
          />
        </div>
        <span className="text-right tabular-nums">
          {metricValueLabel(metric, metric.before)}
        </span>
        <span className="text-muted-foreground">После</span>
        <div className="h-2 rounded bg-muted">
          <div
            className="h-2 rounded bg-primary"
            style={{ width: `${afterWidth}%` }}
          />
        </div>
        <span className="text-right tabular-nums">
          {metricValueLabel(metric, metric.after)}
        </span>
      </div>
    </div>
  );
}

function ActionCenterResultTimeline({
  action,
  resultPage,
  loading,
}: {
  action: ActionCenterItem;
  resultPage?: PortalResultEventsPage | null;
  loading?: boolean;
}) {
  const timeline = resultTimelineData(action, resultPage);
  const { summary, rows, resultEvents, history, statusFlow, before, current } =
    timeline;
  const story = problemResultTimelineStoryFromEvents(resultEvents);
  const afterReady = story.after || timeline.hasAfterData;
  const comparisonReady = story.comparison || timeline.hasMeasuredComparison;
  const confidenceReady = story.confidence || !!timeline.confidence;
  const status = timeline.status;

  return (
    <section className="rounded-md border p-3 space-y-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <div className="text-sm font-semibold">
            Результат и доказательство эффекта
          </div>
          <div className="mt-1 text-xs text-muted-foreground">
            Сначала фиксируем состояние «до», потом сравниваем с «после» по
            данным продаж/финансов.
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {status === "improved" ? (
            <Badge variant="outline" className="border-success/30 text-success">
              <TrendingUp className="mr-1 h-3 w-3" /> Есть улучшение
            </Badge>
          ) : status === "worse" ? (
            <Badge
              variant="outline"
              className="border-destructive/30 text-destructive"
            >
              <TrendingDown className="mr-1 h-3 w-3" /> Стало хуже
            </Badge>
          ) : (
            <Badge variant="outline">ждём данных</Badge>
          )}
          <Button asChild size="sm" variant="outline" className="h-8">
            <Link to="/results" search={resultsLinkSearch(action)}>
              Открыть в результатах{" "}
              <ArrowRight className="ml-1.5 h-3.5 w-3.5" />
            </Link>
          </Button>
        </div>
      </div>

      <div className="grid gap-2 sm:grid-cols-4">
        <InfoBlock
          label="Было"
          value={problemStatusLabel(
            statusFlow.initial_status ?? before.status ?? "new",
          )}
        />
        <InfoBlock
          label="Сейчас"
          value={problemStatusLabel(
            statusFlow.current_status ?? current.status ?? action.status,
          )}
        />
        <InfoBlock
          label="Начали"
          value={formatResultDate(
            statusFlow.started_at ?? before.first_seen_at,
          )}
        />
        <InfoBlock
          label="Завершили"
          value={formatResultDate(
            statusFlow.completed_at ?? current.resolved_at,
          )}
        />
      </div>

      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
        <InfoBlock
          label="Снимок до"
          value={
            story.before || Object.keys(before).length > 0
              ? "зафиксирован"
              : "ждём снимок"
          }
        />
        <InfoBlock
          label="Действие"
          value={story.action ? "записано" : "ещё не записано"}
        />
        <InfoBlock
          label="Перепроверка"
          value={story.recheck ? "есть событие" : "не запускалась"}
        />
        <InfoBlock
          label="Снимок после"
          value={afterReady ? "есть after-data" : "ждём данных"}
        />
        <InfoBlock
          label="Измеренное сравнение"
          value={comparisonReady ? "построено" : "ещё нет"}
        />
        <InfoBlock
          label="Уверенность"
          value={
            confidenceReady ? (timeline.confidence ?? "указана") : "ждём данных"
          }
        />
      </div>

      {resultEvents.length > 0 ? (
        <div className="rounded-md border bg-background p-3">
          <div className="text-xs font-semibold uppercase text-muted-foreground">
            Таймлайн результата
          </div>
          <div className="mt-2 space-y-2">
            {resultEvents
              .slice()
              .reverse()
              .map((event) => (
                <div
                  key={event.id ?? `${event.event_type}-${event.created_at}`}
                  className="grid grid-cols-[140px_minmax(0,1fr)] gap-2 text-xs"
                >
                  <div className="font-medium">
                    {problemResultTimelineLabel(event.event_type)}
                  </div>
                  <div className="text-muted-foreground">
                    {formatResultDate(event.created_at)}
                    {event.outcome
                      ? ` · ${problemResultStatusLabel(
                          resultStatusFromSummary({ outcome: event.outcome }),
                        )}`
                      : ""}
                    {problemResultTimelineMessage(event)
                      ? ` · ${problemResultTimelineMessage(event)}`
                      : ""}
                  </div>
                </div>
              ))}
          </div>
        </div>
      ) : null}

      <div className="rounded-md border bg-muted/20 p-3">
        <div className="text-xs font-semibold uppercase text-muted-foreground">
          Деньги под риском
        </div>
        <div className="mt-1 flex flex-wrap items-baseline gap-2">
          <span className="text-lg font-semibold tabular-nums">
            {timeline.expectedLoss == null
              ? "—"
              : formatMoney(timeline.expectedLoss)}
          </span>
          <span className="text-xs text-muted-foreground">
            {problemImpactLabel(action.impact_type)} ·{" "}
            {problemTrustLabel(action.trust_state)}
          </span>
        </div>
        <div className="mt-1 text-xs text-muted-foreground">
          Это ожидаемый риск/потеря из карточки проблемы. Измеренный денежный
          результат показывается только после сравнения «до/после».
        </div>
      </div>

      {loading ? (
        <div className="space-y-2">
          <Skeleton className="h-14 w-full" />
          <Skeleton className="h-14 w-full" />
        </div>
      ) : rows.length > 0 ? (
        <div className="space-y-3">
          <div className="text-xs font-semibold uppercase text-muted-foreground">
            Измеренное сравнение
          </div>
          {rows.map((row) => (
            <ResultBarPair key={row.key} metric={row} />
          ))}
        </div>
      ) : (
        <Alert>
          <Info className="h-4 w-4" />
          <AlertTitle>Пока рано считать результат</AlertTitle>
          <AlertDescription>
            {timeline.hasWindows
              ? "Окно после действия ещё неполное или нет строк в финансовой витрине."
              : "Переведите задачу в работу/выполнено и дождитесь 7-14 дней данных, чтобы увидеть график результата."}
          </AlertDescription>
        </Alert>
      )}

      {history.length > 0 ? (
        <div className="rounded-md border bg-background p-3">
          <div className="text-xs font-semibold uppercase text-muted-foreground">
            История работы
          </div>
          <div className="mt-2 space-y-2">
            {history.map((item, index) => (
              <div
                key={`${item.event_type ?? "event"}-${index}`}
                className="grid grid-cols-[120px_minmax(0,1fr)] gap-2 text-xs"
              >
                <div className="font-medium">
                  {problemStatusLabel(
                    item.new_status ?? item.status ?? item.event_type,
                  )}
                </div>
                <div className="text-muted-foreground">
                  {formatResultDate(item.created_at)}
                  {item.comment ? ` · ${item.comment}` : ""}
                </div>
              </div>
            ))}
          </div>
        </div>
      ) : null}

      <div className="text-[11px] text-muted-foreground">
        {summary.disclaimer ??
          summary.calculation_note ??
          PROBLEM_RESULT_CORRELATION_DISCLAIMER}
      </div>
    </section>
  );
}

function ActionResultPanel(
  props: Parameters<typeof ActionCenterResultTimeline>[0],
) {
  return <ActionCenterResultTimeline {...props} />;
}

function ResultTimelineStrip({
  action,
  latestRecheckEvent,
  recheckResult,
}: {
  action: ActionCenterItem;
  latestRecheckEvent: ReturnType<typeof latestRecheckEventFromPage>;
  recheckResult?: RecheckResult;
}) {
  const history = Array.isArray(action.status_history)
    ? action.status_history
    : [];
  const firstEvent = history[0] as { at?: string | null } | undefined;
  const lastEvent = history[history.length - 1] as
    | { at?: string | null; status?: string | null }
    | undefined;
  const startedAt = action.first_seen_at ?? firstEvent?.at ?? null;
  const actionAt =
    (action as any).last_status_changed_at ?? lastEvent?.at ?? null;
  const recheckAt =
    recheckResult?.completed_at ??
    latestRecheckEvent?.created_at ??
    null;
  const resolvedAt =
    (action as any).resolved_at ??
    (lastEvent?.status === "done" || lastEvent?.status === "resolved"
      ? lastEvent?.at
      : null);

  const resultStatus = String(
    (action as any).result_status ?? "",
  ).toLowerCase();
  const outcomeLabel =
    resultStatus === "improved"
      ? "Есть улучшение"
      : resultStatus === "worse"
        ? "Стало хуже"
        : resultStatus === "neutral"
          ? "Без изменений"
          : resultStatus === "not_enough_data"
            ? "Нет данных"
            : "Ждём данных";
  const outcomeTone: "ready" | "warning" | "blocked" =
    resultStatus === "improved"
      ? "ready"
      : resultStatus === "worse"
        ? "blocked"
        : "warning";

  const steps: Array<{
    key: string;
    label: string;
    detail: string;
    tone: "ready" | "warning" | "blocked";
  }> = [
    {
      key: "before",
      label: "До действия",
      detail: startedAt
        ? `Первое появление: ${formatResultDate(startedAt)}`
        : "Снимок «до» не зафиксирован",
      tone: startedAt ? "ready" : "warning",
    },
    {
      key: "action",
      label: "Действие",
      detail: actionAt
        ? `Изменение статуса: ${formatResultDate(actionAt)}`
        : "Действие ещё не зафиксировано",
      tone: actionAt ? "ready" : "warning",
    },
    {
      key: "recheck",
      label: "Перепроверка",
      detail: recheckAt
        ? `Последняя перепроверка: ${formatResultDate(recheckAt)}`
        : "Перепроверка не запускалась",
      tone: recheckAt ? "ready" : "warning",
    },
    {
      key: "after",
      label: "После действия",
      detail: resolvedAt
        ? `Итог зафиксирован: ${formatResultDate(resolvedAt)}`
        : "Ждём подтверждающие данные после действия",
      tone: resolvedAt ? "ready" : "warning",
    },
    {
      key: "compare",
      label: "Сравнение",
      detail: outcomeLabel,
      tone: outcomeTone,
    },
  ];

  return (
    <div className="space-y-2">
      <div className="grid gap-2 sm:grid-cols-5">
        {steps.map((step, idx) => (
          <div
            key={step.key}
            className={`relative rounded-md border p-3 ${guideToneClass(step.tone)}`}
          >
            <div className="flex items-center gap-2">
              <div
                className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-[11px] font-semibold ${guideIconClass(step.tone)}`}
              >
                {step.tone === "ready" ? (
                  <CheckCircle2 className="h-3.5 w-3.5" />
                ) : (
                  idx + 1
                )}
              </div>
              <div className="text-xs font-semibold">{step.label}</div>
            </div>
            <div className="mt-1.5 text-[11px] text-muted-foreground">
              {step.detail}
            </div>
          </div>
        ))}
      </div>
      <div className="text-[11px] text-muted-foreground">
        Сравнение показывает связь по данным после действия, но не доказывает
        причинность само по себе. «Сэкономлено» отображается только при
        измеренных данных «после».
      </div>
    </div>
  );
}


export function ActionDrawerResultSection({
  action,
  resultPage,
  loading,
  error,
  endpointAvailable,
}: {
  action: ActionCenterItem;
  resultPage?: PortalResultEventsPage | null;
  loading?: boolean;
  error?: unknown;
  endpointAvailable: boolean;
}) {
  if (loading) {
    return (
      <div className="space-y-2">
        <Skeleton className="h-20 w-full" />
        <Skeleton className="h-16 w-full" />
      </div>
    );
  }

  if (error) {
    return (
      <Alert variant="destructive">
        <AlertTriangle className="h-4 w-4" />
        <AlertTitle>Результат не удалось загрузить</AlertTitle>
        <AlertDescription>
          {sellerSafeMessage(
            error,
            "Канонический журнал результата сейчас недоступен.",
          )}
        </AlertDescription>
      </Alert>
    );
  }

  if (endpointAvailable && !resultPageHasCanonicalData(resultPage)) {
    return (
      <Alert>
        <Info className="h-4 w-4" />
        <AlertTitle>Канонический журнал результата пока пуст</AlertTitle>
        <AlertDescription>
          Задача сохранена, но событий «до/после» ещё нет. Переведите задачу в
          работу или выполнено, запустите перепроверку и дождитесь свежих
          данных.
        </AlertDescription>
      </Alert>
    );
  }

  return (
    <ActionResultPanel
      action={action}
      resultPage={resultPage}
      loading={loading}
    />
  );
}

function ActionDrawerRecheckSection({
  recheckRule,
  recheckResult,
  latestRecheckEvent,
  showRecheck,
  onRecheck,
}: {
  recheckRule: string;
  recheckResult?: RecheckResult;
  latestRecheckEvent: ReturnType<typeof latestRecheckEventFromPage>;
  showRecheck: boolean;
  onRecheck: () => void;
}) {
  return (
    <ActionDrawerSection title="J. Повторная проверка">
      <div className="text-xs text-muted-foreground">{recheckRule}</div>
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant="outline" className="text-[10px]">
          {recheckResult
            ? problemRecheckStatusLabel(recheckResult.status)
            : latestRecheckEvent?.outcome
              ? problemResultStatusLabel(
                  resultStatusFromSummary({
                    outcome: latestRecheckEvent.outcome,
                  }),
                )
              : "Проверка не запускалась"}
        </Badge>
        {showRecheck ? (
          <Button
            size="sm"
            variant="outline"
            className="min-h-10 sm:min-h-8"
            onClick={onRecheck}
          >
            <RefreshCw className="h-3.5 w-3.5 mr-1.5" /> Перепроверить
          </Button>
        ) : null}
      </div>
      {recheckResult || latestRecheckEvent ? (
        <div className="text-xs text-muted-foreground">
          {recheckResult
            ? `${recheckResult.checkedAt} · ${recheckResult.message}`
            : `${formatResultDate(latestRecheckEvent?.created_at)} · ${
                problemResultTimelineMessage(latestRecheckEvent) ??
                latestRecheckEvent?.message ??
                "Последняя перепроверка записана в журнал результата."
              }`}
        </div>
      ) : null}
    </ActionDrawerSection>
  );
}

function ActionDrawerStickyActions({
  primaryAction,
  showRecheck,
  canUpdate,
  claimsLocked,
  saveDisabled,
  busy,
  rowKey,
  onRecheck,
  onSave,
}: {
  primaryAction: RenderableAction | null;
  showRecheck: boolean;
  canUpdate: boolean;
  claimsLocked: boolean;
  saveDisabled: boolean;
  busy: string | null;
  rowKey: string;
  onRecheck: () => void;
  onSave: () => void;
}) {
  return (
    <div
      data-testid="action-drawer-sticky-actions"
      className="shrink-0 border-t bg-background/95 p-3 backdrop-blur sm:hidden"
    >
      <div className="grid grid-cols-2 gap-2">
        {primaryAction?.href ? (
          primaryAction.external ? (
            <Button asChild size="sm" className="min-h-10 w-full">
              <a href={primaryAction.href} target="_blank" rel="noreferrer">
                <Wrench className="mr-1.5 h-3.5 w-3.5" />
                {primaryAction.label}
              </a>
            </Button>
          ) : (
            <Button asChild size="sm" className="min-h-10 w-full">
              <Link to={primaryAction.href}>
                <Wrench className="mr-1.5 h-3.5 w-3.5" />
                {primaryAction.label}
              </Link>
            </Button>
          )
        ) : null}
        {showRecheck ? (
          <Button
            size="sm"
            variant="outline"
            className="min-h-10 w-full"
            onClick={onRecheck}
          >
            <RefreshCw className="mr-1.5 h-3.5 w-3.5" />
            Перепроверить
          </Button>
        ) : null}
        {canUpdate && !claimsLocked ? (
          <Button
            size="sm"
            className="col-span-2 min-h-10 w-full"
            disabled={saveDisabled}
            onClick={onSave}
          >
            <Save className="mr-1.5 h-4 w-4" />
            {busy === rowKey ? "Сохраняем" : "Сохранить изменения"}
          </Button>
        ) : null}
      </div>
    </div>
  );
}

export function ActionCenterDrawerContent({
  open,
  onOpenChange,
  action: a,
  rowKey,
  users,
  claimsEnabled,
  busy,
  mutationPending,
  now,
  draft,
  resultPage,
  resultLoading,
  resultError,
  resultEndpointAvailable,
  recheckResult,
  onDraftChange,
  onSave,
  onRecheck,
  onOpenEvidence,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  action: ActionCenterItem;
  rowKey: string;
  users?: PortalAssignableUser[] | null;
  claimsEnabled: boolean;
  busy: string | null;
  mutationPending: boolean;
  now: Date;
  draft: ActionDraft;
  resultPage?: PortalResultEventsPage | null;
  resultLoading: boolean;
  resultError?: unknown;
  resultEndpointAvailable: boolean;
  recheckResult?: RecheckResult;
  onDraftChange: (patch: Partial<ActionDraft>) => void;
  onSave: () => void;
  onRecheck: () => void;
  onOpenEvidence: (title: string, ledger: EvidenceLedger | null) => void;
}) {
  const problemLike = isProblemLikeAction(a);
  const allowedActions = actionAllowedActions(a);
  const allowedSet = new Set(allowedActions);
  const canUpdate = a.can_update;
  const primaryAction = primaryActionForItem(a);
  const allowedActionButtons = a.allowed_action_items
    .map((item) => renderableActionFromItem(item, a))
    .filter(
      (item): item is RenderableAction =>
        !!item && (!primaryAction?.href || item.href !== primaryAction.href),
    );
  const firstBlockedAction =
    a.allowed_action_items.find((item) => !item.enabled) ?? null;
  const showRecheck =
    a.can_recheck || !problemLike || allowedSet.has("recheck");
  const statusOptions = statusOptionsForAction(a);
  const actionLedger = actionEvidenceLedger(a);
  const claimsLocked = isClaimsAction(a) && !claimsEnabled;
  const saveDisabled =
    busy === rowKey || mutationPending || !canUpdate || claimsLocked;
  const recheckRule = actionRecheckRule(a, actionLedger);
  const latestRecheckEvent = latestRecheckEventFromPage(resultPage);
  const readOnlyReason = claimsLocked
    ? "Модуль претензий отключён."
    : ((a.can_update_reason
        ? canUpdateReasonLabel(a.can_update_reason)
        : null) ??
      (a.is_read_only ? "У задачи нет безопасного пути обновления." : null));

  return (
    <ActionCenterTaskDrawer open={open} onOpenChange={onOpenChange}>
      <SheetContent
        side="right"
        data-testid="action-center-task-sheet"
        className="inset-0 flex h-[100dvh] w-screen max-w-none flex-col overflow-hidden border-l-0 p-0 sm:inset-y-0 sm:left-auto sm:right-0 sm:h-full sm:w-full sm:max-w-2xl sm:border-l sm:p-6"
      >
        <ActionDrawerHeader title={a.title} />

        <div className="min-h-0 flex-1 overflow-y-auto px-4 pb-32 pt-4 sm:px-0 sm:pb-0 sm:pt-6">
          <div className="space-y-5">
            <ActionDrawerProblemStory
              action={a}
              claimsLocked={claimsLocked}
              onOpenEvidence={onOpenEvidence}
            />

            <ActionDrawerAllowedActions
              action={a}
              primaryAction={primaryAction}
              allowedActionButtons={allowedActionButtons}
              readOnlyReason={readOnlyReason}
            />

            <ActionDrawerSolveMap
              action={a}
              primaryAction={primaryAction}
              firstBlockedAction={firstBlockedAction}
              showRecheck={showRecheck}
              readOnlyReason={readOnlyReason}
            />

            <ActionDrawerAssignmentDeadline
              action={a}
              users={users}
              draft={draft}
              saveDisabled={saveDisabled}
              claimsLocked={claimsLocked}
              readOnlyReason={readOnlyReason}
              now={now}
              onDraftChange={onDraftChange}
            />

            <ActionDrawerStatusComment
              action={a}
              draft={draft}
              statusOptions={statusOptions}
              saveDisabled={saveDisabled}
              claimsLocked={claimsLocked}
              readOnlyReason={readOnlyReason}
              busy={busy}
              rowKey={rowKey}
              onDraftChange={onDraftChange}
              onSave={onSave}
            />

            <ActionDrawerSection title="I. История">
              <ActionDrawerHistory
                action={a}
                resultPage={resultPage}
                loading={resultLoading}
                error={resultError}
                recheckResult={recheckResult}
              />
            </ActionDrawerSection>

            <ActionDrawerRecheckSection
              recheckRule={recheckRule}
              recheckResult={recheckResult}
              latestRecheckEvent={latestRecheckEvent}
              showRecheck={showRecheck}
              onRecheck={onRecheck}
            />

            <ActionDrawerSection
              title="K. Результат после действия"
              description="Сравнение показывает связь по данным после действия, но не доказывает причинность само по себе."
            >
              <ResultTimelineStrip
                action={a}
                latestRecheckEvent={latestRecheckEvent}
                recheckResult={recheckResult}
              />
              <ActionDrawerResultSection
                action={a}
                resultPage={resultPage}
                loading={resultLoading}
                error={resultError}
                endpointAvailable={resultEndpointAvailable}
              />
            </ActionDrawerSection>
          </div>
        </div>



        <ActionDrawerStickyActions
          primaryAction={primaryAction}
          showRecheck={showRecheck}
          canUpdate={canUpdate}
          claimsLocked={claimsLocked}
          saveDisabled={saveDisabled}
          busy={busy}
          rowKey={rowKey}
          onRecheck={onRecheck}
          onSave={onSave}
        />
      </SheetContent>
    </ActionCenterTaskDrawer>
  );
}
