// @ts-nocheck
/**
 * Product360 — детальная панель проблемы.
 *
 * Единый Sheet/Drawer с продуктовыми секциями A–H:
 *   A. Что произошло?
 *   B. Почему платформа так решила?
 *   C. На что влияет?
 *   D. Это факт или оценка?
 *   E. Что сделать сейчас?
 *   F. Связь с задачей
 *   G. Повторная проверка
 *   H. Результат
 *
 * Не тянет данные сам. Работает с ActionCenterItem (нормализованным
 * контрактом проблемы) и агрегированной страницей результатов.
 */
import { Link } from "@tanstack/react-router";
import { ArrowRight, ExternalLink } from "lucide-react";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EvidenceButton } from "@/components/shell/EvidenceButton";
import type { ActionCenterItem } from "@/lib/action-center-contract";
import type { EvidenceLedger } from "@/lib/evidence";
import type {
  PortalResultEventsPage,
  ProblemResultStatus,
} from "@/lib/portal";
import { evidenceFrom } from "@/lib/evidence";
import {
  problemRecheckStatusLabel,
  problemResultStatusLabel,
  problemStatusLabel,
} from "@/lib/problem-ux-copy";
import {
  problemResultBadgeStatus,
  problemResultSummaryFromPage,
} from "@/lib/problem-results";
import {
  primaryActionForItem,
  primaryDisabledActionForItem,
  resultsHrefForAction,
} from "@/lib/action-center-actions";
import { product360ProblemToActionCenterLink } from "@/lib/action-center-contract";

const IMPACT_LABEL: Record<string, string> = {
  confirmed_loss: "Подтверждённый убыток",
  probable_loss: "Вероятный убыток",
  blocked_cash: "Замороженные деньги",
  lost_sales_risk: "Риск потери продаж",
  opportunity: "Возможность роста",
  data_blocker: "Блокер данных",
  system_warning: "Системное предупреждение",
};

const TRUST_LABEL: Record<string, string> = {
  confirmed: "Подтверждено данными",
  provisional: "Предварительно",
  estimated: "Оценка",
  opportunity: "Возможность",
  test_only: "Только для тестов",
  blocked: "Заблокировано данными",
};

function txt(v: unknown, fb = ""): string {
  const s = String(v ?? "").trim();
  return s || fb;
}

function formatDate(v: unknown): string | null {
  if (!v) return null;
  const d = new Date(String(v));
  if (Number.isNaN(d.getTime())) return null;
  return d.toLocaleString("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function Section({
  letter,
  title,
  children,
}: {
  letter: string;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="space-y-1.5 border-t pt-3 first:border-0 first:pt-0">
      <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        {letter}. {title}
      </div>
      <div className="text-sm leading-relaxed">{children}</div>
    </section>
  );
}

export interface ProductProblemDrawerProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  problem: ActionCenterItem | null;
  resultPage?: PortalResultEventsPage | null;
  onEvidence: (title: string, ledger: EvidenceLedger | null) => void;
}

export function ProductProblemDrawer({
  open,
  onOpenChange,
  problem,
  resultPage,
  onEvidence,
}: ProductProblemDrawerProps) {
  if (!problem) {
    return (
      <Sheet open={open} onOpenChange={onOpenChange}>
        <SheetContent side="right" className="w-full sm:max-w-xl" />
      </Sheet>
    );
  }

  const title = txt(problem.title, "Проблема товара");
  const why = txt(problem.why ?? problem.short_summary ?? problem.description);
  const impactType = txt(problem.impact_type).toLowerCase();
  const impactLabel = IMPACT_LABEL[impactType] ?? "Влияние";
  const trust = txt(problem.evidence_state ?? problem.trust_state).toLowerCase();
  const trustLabel = TRUST_LABEL[trust] ?? "Состояние доказательств";
  const severity = txt(problem.severity);
  const statusLabel = problemStatusLabel(problem.status ?? "new");

  const ledger = evidenceFrom(problem.evidence_ledger, problem);
  const primary = primaryActionForItem(problem);
  const disabledPrimary = primaryDisabledActionForItem(problem);
  const resultHref = resultsHrefForAction(problem);
  const actionCenterSearch = product360ProblemToActionCenterLink(problem);

  const resultStatus: ProblemResultStatus = resultPage
    ? problemResultBadgeStatus(resultPage)
    : "pending_data";

  const summary = resultPage ? problemResultSummaryFromPage(resultPage) : null;
  const lastChange = summary?.status_history?.slice().reverse()[0];
  const events = Array.isArray(resultPage?.items)
    ? resultPage?.items ?? []
    : Array.isArray(resultPage?.recent_events)
      ? resultPage?.recent_events ?? []
      : [];
  const recheckEvent = events.find((e: any) => e?.event_type === "recheck_result");
  const canRecheck = (problem.allowed_actions ?? []).includes("recheck");

  const assignee = problem.assigned_to_user_name?.trim()
    ? problem.assigned_to_user_name
    : problem.assigned_to_user_id != null
      ? `Пользователь #${problem.assigned_to_user_id}`
      : null;
  const deadline = formatDate(problem.deadline_at);

  const missingData: string[] = Array.isArray(ledger?.missing_data)
    ? (ledger?.missing_data as string[])
    : [];

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        side="right"
        className="w-full overflow-y-auto sm:max-w-xl"
        data-testid="product-problem-drawer"
      >
        <SheetHeader className="space-y-2 pr-8">
          <SheetTitle className="text-base leading-snug">{title}</SheetTitle>
          <div className="flex flex-wrap items-center gap-1.5">
            {severity ? (
              <Badge variant="outline" className="text-[10px]">
                {severity}
              </Badge>
            ) : null}
            <Badge variant="outline" className="text-[10px]">
              Статус: {statusLabel}
            </Badge>
            <Badge variant="outline" className="text-[10px]">
              Доверие: {trustLabel}
            </Badge>
            <Badge variant="outline" className="text-[10px]">
              Влияние: {impactLabel}
            </Badge>
            <Badge variant="outline" className="text-[10px]">
              Результат: {problemResultStatusLabel(resultStatus)}
            </Badge>
          </div>
        </SheetHeader>

        <div className="mt-4 space-y-4">
          <Section letter="A" title="Что произошло?">
            {why || "Платформа зафиксировала сигнал по этому товару."}
          </Section>

          <Section letter="B" title="Почему платформа так решила?">
            <div className="space-y-2">
              <div className="text-muted-foreground">
                Расчёт основан на данных выручки, себестоимости, комиссий и
                логистики за выбранный период.
              </div>
              <EvidenceButton
                onClick={() => onEvidence(title, ledger ?? null)}
                missing={!ledger}
              />
            </div>
          </Section>

          <Section letter="C" title="На что влияет?">
            <div className="space-y-1">
              <div>{impactLabel}.</div>
              {impactType === "opportunity" || impactType === "data_blocker" ? (
                <div className="text-xs text-muted-foreground">
                  Это не подтверждённый убыток. Влияние на деньги появится после
                  проверки и повторного расчёта.
                </div>
              ) : null}
            </div>
          </Section>

          <Section letter="D" title="Это факт или оценка?">
            <div className="space-y-1">
              <div>{trustLabel}.</div>
              {missingData.length > 0 ? (
                <div className="text-xs text-amber-800 dark:text-amber-200">
                  Не хватает: {missingData.join(", ")}.
                </div>
              ) : null}
              {trust === "estimated" || trust === "provisional" ? (
                <div className="text-xs text-muted-foreground">
                  Часть значений — оценка. Не считайте это подтверждённой
                  потерей денег.
                </div>
              ) : null}
            </div>
          </Section>

          <Section letter="E" title="Что сделать сейчас?">
            <div className="flex flex-wrap gap-1.5">
              {primary?.href ? (
                primary.external ? (
                  <Button asChild size="sm" className="h-8 text-xs">
                    <a href={primary.href} target="_blank" rel="noreferrer">
                      {primary.label}
                      <ArrowRight className="ml-1 h-3.5 w-3.5" />
                    </a>
                  </Button>
                ) : (
                  <Button asChild size="sm" className="h-8 text-xs">
                    <Link to={primary.href}>
                      {primary.label}
                      <ArrowRight className="ml-1 h-3.5 w-3.5" />
                    </Link>
                  </Button>
                )
              ) : disabledPrimary ? (
                <Button
                  size="sm"
                  className="h-8 text-xs"
                  disabled
                  title={
                    disabledPrimary.disabled_reason ||
                    "Раздел пока недоступен."
                  }
                >
                  {disabledPrimary.label}: раздел пока недоступен
                </Button>
              ) : (
                <Button asChild size="sm" variant="outline" className="h-8 text-xs">
                  <Link to="/action-center" search={actionCenterSearch}>
                    Открыть задачу
                  </Link>
                </Button>
              )}
            </div>
          </Section>

          <Section letter="F" title="Связь с задачей">
            <div className="space-y-2">
              <div className="flex flex-wrap items-center gap-1.5 text-xs">
                {problem.problem_instance_id != null ? (
                  <>
                    <Badge variant="outline" className="text-[10px]">
                      Задача #{String(problem.problem_instance_id)}
                    </Badge>
                    {assignee ? (
                      <Badge variant="outline" className="text-[10px]">
                        Ответственный: {assignee}
                      </Badge>
                    ) : null}
                    {deadline ? (
                      <Badge variant="outline" className="text-[10px]">
                        Срок: {deadline}
                      </Badge>
                    ) : null}
                    {lastChange ? (
                      <Badge variant="outline" className="text-[10px]">
                        Изменение: {formatDate(lastChange.created_at) ?? "—"}
                      </Badge>
                    ) : null}
                  </>
                ) : (
                  <span className="text-muted-foreground">
                    Задачи пока нет.
                  </span>
                )}
              </div>
              <div className="flex flex-wrap gap-1.5">
                <Button asChild size="sm" variant="outline" className="h-8 text-xs">
                  <Link to="/action-center" search={actionCenterSearch}>
                    Открыть задачу
                    <ArrowRight className="ml-1 h-3.5 w-3.5" />
                  </Link>
                </Button>
              </div>
            </div>
          </Section>

          <Section letter="G" title="Повторная проверка">
            <div className="space-y-1 text-xs">
              {recheckEvent ? (
                <div>
                  Последняя проверка:{" "}
                  {problemRecheckStatusLabel(recheckEvent.outcome)} ·{" "}
                  {formatDate(recheckEvent.created_at) ?? "—"}
                </div>
              ) : (
                <div className="text-muted-foreground">
                  Перепроверка ещё не запускалась.
                </div>
              )}
              {!canRecheck ? (
                <div className="text-muted-foreground">
                  Ручная перепроверка недоступна для этой проблемы.
                </div>
              ) : null}
            </div>
          </Section>

          <Section letter="H" title="Результат">
            <div className="space-y-2">
              <Badge variant="outline" className="text-[10px]">
                {problemResultStatusLabel(resultStatus)}
              </Badge>
              <div className="text-xs text-muted-foreground">
                Сравнение показывает связь по данным после действия, но не
                доказывает причинность само по себе.
              </div>
              <Button asChild size="sm" variant="outline" className="h-8 text-xs">
                <Link to={resultHref}>
                  Открыть результаты
                  <ExternalLink className="ml-1 h-3.5 w-3.5" />
                </Link>
              </Button>
            </div>
          </Section>
        </div>
      </SheetContent>
    </Sheet>
  );
}
