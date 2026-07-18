/**
 * CheckerIssueDrawer — детальный дровер по одной проблеме карточки.
 *
 * 11 заголовков A–K по спецификации Phase 7.2:
 *   A. Что произошло?
 *   B. Почему платформа так решила?
 *   C. На что влияет?
 *   D. Это факт или оценка?
 *   E. Что сделать сейчас?
 *   F. Предпросмотр исправления
 *   G. Локальное исправление
 *   H. Отправка в WB
 *   I. Связь с задачей
 *   J. Повторная проверка
 *   K. Результат
 *
 * Не переиспользует money-oriented копии EvidenceDrawer.
 * Money/Data Fix/Product360 продолжают использовать общий EvidenceDrawer.
 * Кнопка «Как посчитано?» в секции B открывает shared EvidenceDrawer как
 * подпанель с деталями расчёта — для сохранения доступа к сырым доказательствам.
 */
import { useState, type ReactNode } from "react";
import {
  CheckCircle2,
  ExternalLink,
  FileCheck2,
  ListChecks,
  RefreshCw,
  Save,
  ShieldAlert,
  ShieldCheck,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { EvidenceDrawer } from "@/components/EvidenceDrawer";
import { EvidenceButton } from "@/components/shell/EvidenceButton";
import { coerceEvidenceLedger, type EvidenceLedger } from "@/lib/evidence";
import { cn } from "@/lib/utils";

type Issue = Record<string, any>;

interface CheckerIssueDrawerProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  issue?: Issue | null;
  ledger?: EvidenceLedger | null;
  nmId?: string | number | null;
  title?: string;
  /** Опционально: колбэки от родителя. Не вызываются, если не переданы. */
  onAcceptLocal?: () => void;
  onMarkFixed?: () => void;
  onSaveDraft?: () => void;
  onPreviewWb?: () => void;
  onApplyWb?: () => void;
  onRecheck?: () => void;
}

function n(x: unknown): string {
  return x === null || x === undefined ? "" : String(x);
}
function norm(x: unknown): string {
  return n(x).trim().toLowerCase();
}

function impactLabel(issue: Issue | null | undefined): string {
  const t = norm(issue?.impact_type);
  if (t === "data_blocker") return "Блокер данных";
  if (t === "system_warning") return "Системное предупреждение";
  if (t === "opportunity") return "Возможность роста";
  if (t === "estimated") return "Оценка";
  const sev = norm(issue?.severity);
  if (sev === "low" || sev === "improvement" || sev === "info")
    return "Возможность роста";
  return "Оценка";
}

function trustLabel(issue: Issue | null | undefined): string {
  const s = norm(issue?.trust_state ?? issue?.confidence);
  if (s === "blocked" || s === "data_blocked" || s === "data_blocker")
    return "Не хватает данных";
  const kind = norm(issue?.suggestion_kind ?? issue?.detector_kind);
  if (kind === "rule") return "Проверка по правилу";
  if (kind === "ai") return "AI-рекомендация";
  if (kind === "wb" || kind === "wb_validation") return "WB-валидация";
  if (kind === "candidate" || issue?.requires_human_check === true)
    return "Требует проверки человеком";
  if (s === "estimated" || s === "provisional") return "Предварительная оценка";
  const t = norm(issue?.impact_type);
  if (t === "opportunity") return "Возможность, не факт убытка";
  return "Предварительная оценка";
}

function isDataBlocker(issue: Issue | null | undefined): boolean {
  if (norm(issue?.impact_type) === "data_blocker") return true;
  if (issue?.is_data_blocker === true) return true;
  if (issue?.blocks_calculation === true) return true;
  return norm(issue?.trust_state ?? issue?.confidence) === "blocked";
}

function Section({
  letter,
  title,
  children,
}: {
  letter: string;
  title: string;
  children?: ReactNode;
}) {
  return (
    <section className="rounded-md border p-3">
      <div className="mb-2 flex items-center gap-2">
        <span className="inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full border text-[10px] font-semibold text-muted-foreground">
          {letter}
        </span>
        <h3 className="text-sm font-semibold">{title}</h3>
      </div>
      <div className="space-y-2 text-sm leading-relaxed text-foreground/90">
        {children}
      </div>
    </section>
  );
}

function Empty({ text }: { text: string }) {
  return <p className="text-sm text-muted-foreground">{text}</p>;
}

export function CheckerIssueDrawer(props: CheckerIssueDrawerProps) {
  const {
    open,
    onOpenChange,
    issue,
    ledger,
    nmId,
    title,
    onAcceptLocal,
    onMarkFixed,
    onSaveDraft,
    onPreviewWb,
    onApplyWb,
    onRecheck,
  } = props;

  const [evidenceOpen, setEvidenceOpen] = useState(false);

  const l = coerceEvidenceLedger(ledger);
  const iss = issue ?? {};
  const headTitle =
    title || n(iss?.title) || n(iss?.code) || "Проблема карточки";

  const problemId = n(iss?.problem_instance_id ?? iss?.id ?? iss?.issue_id);
  const nmIdStr = n(nmId ?? iss?.nm_id ?? iss?.nmID);
  const field = n(iss?.field_name ?? iss?.field_path);
  const current = n(iss?.current_value ?? iss?.actual_value);
  const suggested = n(iss?.ai_suggested_value ?? iss?.suggested_value);
  const description = n(iss?.description ?? iss?.details ?? l?.formula_human);
  const rule =
    n(iss?.rule_human ?? iss?.rule_name ?? iss?.detector_human) ||
    n(iss?.reason) ||
    n(l?.formula_human);
  const aiReason = n(iss?.ai_reason ?? iss?.ai_explanation);
  const wbValidation = n(iss?.wb_validation_message ?? iss?.wb_validation);
  const affected = n(iss?.impact_human ?? iss?.affected_area);
  const trustReason = n(iss?.trust_reason ?? l?.confidence_reason);

  const wbSupported = iss?.can_apply_to_wb === true;
  const wbBlockedReason = n(
    iss?.wb_apply_blocked_reason ?? iss?.wb_blocked_reason,
  );

  const taskId = n(iss?.action_center_task_id ?? iss?.task_id ?? problemId);
  const taskStatus = n(iss?.task_status);
  const taskAssignee = n(iss?.task_assignee ?? iss?.assignee);
  const taskDeadline = n(iss?.task_deadline ?? iss?.deadline);
  const taskLastChange = n(iss?.task_status_changed_at ?? iss?.status_updated_at);

  const lastRecheck = n(iss?.last_checked_at ?? iss?.last_recheck_at);
  const recheckStatus = n(iss?.recheck_status);
  const recheckRule = n(
    iss?.recheck_rule_human ?? l?.recheck_rule_human ?? l?.recheck_rule,
  );
  const recheckSupported = iss?.can_recheck !== false;

  const scoreBefore = iss?.score_before;
  const scoreAfter = iss?.score_after;
  const openBefore = iss?.open_issues_before;
  const openAfter = iss?.open_issues_after;
  const resultBucket = norm(iss?.result_bucket ?? iss?.result_status);
  const resultHuman: Record<string, string> = {
    improved: "Есть улучшение",
    worse: "Стало хуже",
    same: "Без изменений",
    no_data: "Нет данных",
    waiting: "Ждём данных",
  };
  const resultLabel = resultBucket
    ? (resultHuman[resultBucket] ?? "Ждём данных")
    : scoreBefore != null && scoreAfter != null
      ? scoreAfter > scoreBefore
        ? "Есть улучшение"
        : scoreAfter < scoreBefore
          ? "Стало хуже"
          : "Без изменений"
      : "Ждём данных";
  const wbApplyStatus = n(iss?.wb_apply_status);

  const ctxQ = problemId
    ? `problem_instance_id=${encodeURIComponent(problemId)}`
    : "";
  const linkTask = ctxQ ? `/action-center?${ctxQ}` : "/action-center";
  const linkResult = ctxQ ? `/results?${ctxQ}` : "/results";
  const linkProduct = nmIdStr
    ? `/products/${encodeURIComponent(nmIdStr)}`
    : "/products";
  const linkCard = nmIdStr
    ? `/checker/${encodeURIComponent(nmIdStr)}${ctxQ ? `?${ctxQ}` : ""}`
    : "/checker";
  const linkDataFix = (() => {
    const parts: string[] = [];
    if (problemId)
      parts.push(`problem_instance_id=${encodeURIComponent(problemId)}`);
    if (nmIdStr) parts.push(`nm_id=${encodeURIComponent(nmIdStr)}`);
    return parts.length ? `/data-fix?${parts.join("&")}` : "/data-fix";
  })();

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        side="right"
        data-testid="checker-issue-drawer"
        className="inset-0 h-[100dvh] w-screen max-w-none overflow-y-auto border-l-0 p-4 sm:inset-y-0 sm:left-auto sm:right-0 sm:h-full sm:w-full sm:max-w-2xl sm:border-l sm:p-6"
      >
        <SheetHeader className="pr-8">
          <SheetTitle className="break-words">{headTitle}</SheetTitle>
          <SheetDescription>
            Подробный разбор проблемы карточки: что произошло, почему платформа
            так решила, что можно сделать и как это повлияет на карточку.
          </SheetDescription>
        </SheetHeader>

        <div className="mt-4 flex flex-wrap gap-1.5">
          <Badge variant="outline" className="text-[11px]">
            На что влияет: {impactLabel(iss)}
          </Badge>
          <Badge variant="outline" className="text-[11px]">
            Это факт или оценка: {trustLabel(iss)}
          </Badge>
          {field ? (
            <Badge variant="secondary" className="text-[11px] font-mono break-all">
              {field}
            </Badge>
          ) : null}
        </div>

        <div className="mt-4 space-y-3">
          {/* A */}
          <Section letter="A" title="Что произошло?">
            <p className="font-medium break-words">{headTitle}</p>
            {field ? (
              <p className="text-xs text-muted-foreground">
                Поле: <span className="font-mono break-all">{field}</span>
              </p>
            ) : null}
            {current ? (
              <p className="text-xs text-muted-foreground break-words">
                Текущее значение: {current}
              </p>
            ) : null}
            {description ? (
              <p>{description}</p>
            ) : (
              <Empty text="Короткое описание пока не передано бэкендом." />
            )}
          </Section>

          {/* B */}
          <Section letter="B" title="Почему платформа так решила?">
            {rule ? <p>{rule}</p> : null}
            {aiReason ? (
              <p className="text-xs text-muted-foreground">
                AI: {aiReason}
              </p>
            ) : null}
            {wbValidation ? (
              <p className="text-xs text-muted-foreground">
                WB-валидация: {wbValidation}
              </p>
            ) : null}
            {!rule && !aiReason && !wbValidation ? (
              <Empty text="Правило проверки не передано. Ждём данных от бэкенда." />
            ) : null}
            {l ? (
              <div className="pt-1">
                <EvidenceButton onClick={() => setEvidenceOpen(true)} />
              </div>
            ) : null}
          </Section>

          {/* C */}
          <Section letter="C" title="На что влияет?">
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="outline" className="text-[11px]">
                {impactLabel(iss)}
              </Badge>
              {affected ? <span className="text-sm">{affected}</span> : null}
            </div>
            <p className="text-xs text-muted-foreground">
              Это влияние на качество карточки. Денежный эффект — не
              подтверждённый убыток, а оценка потенциала.
            </p>
          </Section>

          {/* D */}
          <Section letter="D" title="Это факт или оценка?">
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="outline" className="text-[11px]">
                {trustLabel(iss)}
              </Badge>
              {trustReason ? (
                <span className="text-xs text-muted-foreground">
                  {trustReason}
                </span>
              ) : null}
            </div>
          </Section>

          {/* E */}
          <Section letter="E" title="Что сделать сейчас?">
            <p>
              Проверьте рекомендованное значение и примите его локально внутри
              платформы. Карточка WB не изменяется.
            </p>
            {suggested ? (
              <p className="text-xs text-muted-foreground break-words">
                Рекомендация: <span className="font-medium">{suggested}</span>
              </p>
            ) : (
              <p className="text-xs text-muted-foreground">
                Рекомендация пока не сформирована.
              </p>
            )}
            <div className="flex flex-wrap gap-1.5 pt-1">
              <Button asChild size="sm" variant="outline">
                <a href={linkTask}>Открыть задачу</a>
              </Button>
              <Button asChild size="sm" variant="outline">
                <a href={linkResult}>Открыть результат</a>
              </Button>
              <Button asChild size="sm" variant="outline">
                <a href={linkProduct}>Открыть товар</a>
              </Button>
              {isDataBlocker(iss) ? (
                <Button asChild size="sm" variant="outline">
                  <a href={linkDataFix}>
                    <ListChecks className="mr-1 h-3.5 w-3.5" />
                    Открыть исправление данных
                  </a>
                </Button>
              ) : null}
            </div>
          </Section>

          {/* F */}
          <Section letter="F" title="Предпросмотр исправления">
            {field ? (
              <p className="text-xs text-muted-foreground">
                Поле: <span className="font-mono break-all">{field}</span>
              </p>
            ) : null}
            {current || suggested ? (
              <div className="grid gap-2 sm:grid-cols-2">
                <div className="rounded border bg-muted/30 px-2 py-1.5 text-xs">
                  <div className="text-muted-foreground">Сейчас</div>
                  <div className="font-medium break-words">
                    {current || "—"}
                  </div>
                </div>
                <div className="rounded border bg-primary/5 px-2 py-1.5 text-xs">
                  <div className="text-muted-foreground">Рекомендация</div>
                  <div className="font-medium break-words">
                    {suggested || "—"}
                  </div>
                </div>
              </div>
            ) : (
              <Empty text="Рекомендация пока не сформирована." />
            )}
            {Array.isArray(iss?.allowed_values) && iss.allowed_values.length ? (
              <p className="text-xs text-muted-foreground break-words">
                Допустимые значения: {iss.allowed_values.slice(0, 8).join(", ")}
              </p>
            ) : null}
            {Array.isArray(iss?.warnings) && iss.warnings.length ? (
              <ul className="list-disc pl-4 text-xs text-amber-800 dark:text-amber-300">
                {iss.warnings.map((w: any, i: number) => (
                  <li key={i}>{n(w)}</li>
                ))}
              </ul>
            ) : null}
          </Section>

          {/* G */}
          <Section letter="G" title="Локальное исправление">
            <p className="text-xs text-muted-foreground">
              Карточка WB не изменяется. Меняется только статус и рекомендация
              внутри платформы.
            </p>
            <div className="flex flex-wrap gap-1.5 pt-1">
              <Button
                size="sm"
                variant="default"
                disabled={!onAcceptLocal || !suggested}
                onClick={onAcceptLocal}
              >
                <FileCheck2 className="mr-1 h-3.5 w-3.5" />
                Принять рекомендацию локально
              </Button>
              <Button
                size="sm"
                variant="outline"
                disabled={!onMarkFixed}
                onClick={onMarkFixed}
              >
                <CheckCircle2 className="mr-1 h-3.5 w-3.5" />
                Отметить как исправлено
              </Button>
              <Button
                size="sm"
                variant="outline"
                disabled={!onSaveDraft}
                onClick={onSaveDraft}
              >
                <Save className="mr-1 h-3.5 w-3.5" />
                Сохранить черновик
              </Button>
            </div>
          </Section>

          {/* H */}
          <Section letter="H" title="Отправка в WB">
            {!wbSupported ? (
              <div className="flex items-start gap-2 rounded border border-amber-500/30 bg-amber-500/5 px-3 py-2 text-xs text-amber-900 dark:text-amber-200">
                <ShieldAlert className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                <span>
                  Отправка в WB недоступна для этого поля или токена.
                  {wbBlockedReason ? ` ${wbBlockedReason}` : ""}
                </span>
              </div>
            ) : (
              <>
                <p className="text-xs text-muted-foreground">
                  Требования перед отправкой:
                </p>
                <ul className="list-disc pl-4 text-xs text-muted-foreground">
                  <li>Предпросмотр изменений</li>
                  <li>Подтверждение</li>
                  <li>Проверка прав</li>
                  <li>Запись в историю</li>
                </ul>
                <div className="flex flex-wrap gap-1.5 pt-1">
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={!onPreviewWb}
                    onClick={onPreviewWb}
                  >
                    Предпросмотр изменений
                  </Button>
                  <Button
                    size="sm"
                    variant="default"
                    disabled={!onApplyWb}
                    onClick={onApplyWb}
                  >
                    <ShieldCheck className="mr-1 h-3.5 w-3.5" />
                    Отправить в WB
                  </Button>
                </div>
              </>
            )}
          </Section>

          {/* I */}
          <Section letter="I" title="Связь с задачей">
            {problemId ? (
              <>
                <a
                  className="inline-flex items-center gap-1 text-sm text-primary hover:underline"
                  href={linkTask}
                >
                  Задача №{taskId || problemId} в Action Center
                  <ExternalLink className="h-3 w-3" />
                </a>
                <div className="grid gap-1 text-xs text-muted-foreground sm:grid-cols-2">
                  {taskStatus ? <span>Статус: {taskStatus}</span> : null}
                  {taskAssignee ? (
                    <span>Ответственный: {taskAssignee}</span>
                  ) : null}
                  {taskDeadline ? <span>Срок: {taskDeadline}</span> : null}
                  {taskLastChange ? (
                    <span>Изменён: {taskLastChange}</span>
                  ) : null}
                </div>
              </>
            ) : (
              <Empty text="Связанной задачи пока нет. Она появится, когда проблема будет отправлена в работу." />
            )}
          </Section>

          {/* J */}
          <Section letter="J" title="Повторная проверка">
            {lastRecheck ? (
              <p className="text-xs text-muted-foreground">
                Последняя проверка: {lastRecheck}
                {recheckStatus ? ` · ${recheckStatus}` : ""}
              </p>
            ) : null}
            {recheckRule ? <p>{recheckRule}</p> : null}
            {!recheckSupported ? (
              <p className="text-xs text-amber-800 dark:text-amber-300">
                Повторная проверка недоступна для этого поля.
              </p>
            ) : (
              <Button
                size="sm"
                variant="outline"
                disabled={!onRecheck}
                onClick={onRecheck}
              >
                <RefreshCw className="mr-1 h-3.5 w-3.5" />
                Проверить ещё раз
              </Button>
            )}
            {!lastRecheck && !recheckRule ? (
              <Empty text="После действия запустите проверку карточки повторно, чтобы платформа обновила статус." />
            ) : null}
          </Section>

          {/* K */}
          <Section letter="K" title="Результат">
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="outline" className="text-[11px]">
                {resultLabel}
              </Badge>
              {wbApplyStatus ? (
                <Badge variant="outline" className="text-[11px]">
                  WB: {wbApplyStatus}
                </Badge>
              ) : null}
            </div>
            {scoreBefore != null || scoreAfter != null ? (
              <p className="text-xs text-muted-foreground">
                Оценка карточки: {scoreBefore ?? "—"} → {scoreAfter ?? "—"}
              </p>
            ) : null}
            {openBefore != null || openAfter != null ? (
              <p className="text-xs text-muted-foreground">
                Открытых проблем: {openBefore ?? "—"} → {openAfter ?? "—"}
              </p>
            ) : null}
            <a
              className={cn(
                "inline-flex items-center gap-1 text-sm text-primary hover:underline",
                !problemId && !nmIdStr && "pointer-events-none opacity-60",
              )}
              href={problemId ? linkResult : nmIdStr ? linkCard : "#"}
            >
              Открыть результаты по карточке
              <ExternalLink className="h-3 w-3" />
            </a>
          </Section>
        </div>

        {/* Shared EvidenceDrawer как под-панель для деталей расчёта */}
        <EvidenceDrawer
          open={evidenceOpen}
          onOpenChange={setEvidenceOpen}
          ledger={l}
          title={headTitle}
        />
      </SheetContent>
    </Sheet>
  );
}
