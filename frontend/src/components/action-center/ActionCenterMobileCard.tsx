// @ts-nocheck
/**
 * Компактная мобильная карточка задачи Центра действий.
 * Использует те же props, что и ActionCenterRow, но с упрощённой вертикальной раскладкой,
 * оптимизированной под узкие экраны.
 */
import { Link } from "@tanstack/react-router";
import {
  AlertTriangle,
  ArrowRight,
  CalendarClock,
  Info,
  Lock,
  UserRound,
  Wrench,
} from "lucide-react";
import { EvidenceButton } from "@/components/EvidenceDrawer";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { EVIDENCE_STATE_CLASS } from "@/components/action-center/ActionCenterEvidenceControls";
import { DynamicProblemRowResultBadge } from "@/components/action-center/DynamicProblemRowResultBadge";
import {
  actionCenterResultPageForItem,
  type ActionCenterItem,
} from "@/lib/action-center-contract";
import {
  primaryActionForItem,
  primaryDisabledActionForItem,
} from "@/lib/action-center-actions";
import {
  PRIO_COLORS,
  canUpdateReasonLabel,
  priorityLabel,
} from "@/lib/action-center-labels";
import {
  actionEvidenceLedger,
  assigneeLabel,
  effectiveResultStatus,
  formatDeadline,
  isClaimsAction,
  isDynamicProblemAction,
  isOverdueAction,
  statusOptionsForAction,
} from "@/lib/action-center-status";
import {
  ROW_RESULT_STATUS_CLASS,
  type ProblemRowResultStatus,
} from "@/lib/action-center-results";
import { formatMoney } from "@/lib/format";
import type { EvidenceLedger } from "@/lib/evidence";
import type { PortalResultEventsPage } from "@/lib/portal";
import { problemResultStatusLabel } from "@/lib/problem-ux-copy";

type Props = {
  action: ActionCenterItem;
  rowKey: string;
  claimsEnabled: boolean;
  currentUserId: number | null;
  now: Date;
  problemResultsPage?: PortalResultEventsPage | null;
  busy: string | null;
  onOpenTask: (action: ActionCenterItem, rowKey: string) => void;
  onOpenEvidence: (title: string, ledger: EvidenceLedger | null) => void;
  onStatusChange: (
    rowKey: string,
    action: ActionCenterItem,
    status: string,
  ) => void;
};

export function ActionCenterMobileCard({
  action: a,
  rowKey,
  claimsEnabled,
  currentUserId,
  now,
  problemResultsPage,
  busy,
  onOpenTask,
  onOpenEvidence,
  onStatusChange,
}: Props) {
  const canUpdate = a.can_update;
  const dynamicProblem = isDynamicProblemAction(a);
  const statusOptions = statusOptionsForAction(a);
  const claimsAction = isClaimsAction(a);
  const claimsLocked = claimsAction && !claimsEnabled;
  const actionLedger = actionEvidenceLedger(a);
  const rowResultPage = dynamicProblem
    ? actionCenterResultPageForItem(a, problemResultsPage)
    : null;
  const primaryAction = primaryActionForItem(a);
  const disabledPrimaryAction = primaryDisabledActionForItem(a);
  const deadline = formatDeadline(a, now);
  const overdue = isOverdueAction(a, now);
  const resultStatus: ProblemRowResultStatus = effectiveResultStatus(
    a,
    problemResultsPage,
  );
  const productText = [a.nm_id ? `nm ${a.nm_id}` : null, a.vendor_code]
    .filter(Boolean)
    .join(" / ");
  const evidenceInsufficient =
    a.evidence_state === "partial_evidence" ||
    a.evidence_state === "missing_evidence";

  return (
    <Card
      data-testid="action-row"
      data-action-row="1"
      data-mobile-action-card="1"
      className={overdue ? "border-destructive/35 bg-destructive/5" : ""}
    >
      <CardContent className="p-3 space-y-3">
        <div className="flex flex-wrap items-center gap-1.5">
          {a.priority ? (
            <Badge
              variant="outline"
              className={PRIO_COLORS[a.priority] ?? ""}
            >
              {priorityLabel(a.priority)}
            </Badge>
          ) : null}
          {a.status && a.status !== "open" ? (
            <Badge variant="secondary" className="text-[10px]">
              {a.status_label}
            </Badge>
          ) : null}
          {dynamicProblem ? (
            <DynamicProblemRowResultBadge
              action={a}
              resultPage={rowResultPage}
            />
          ) : (
            <Badge
              variant="outline"
              className={`text-[10px] ${ROW_RESULT_STATUS_CLASS[resultStatus]}`}
            >
              {problemResultStatusLabel(resultStatus)}
            </Badge>
          )}
          {overdue ? (
            <Badge variant="destructive" className="text-[10px]">
              Просрочено
            </Badge>
          ) : null}
        </div>

        <div className="text-sm font-semibold leading-snug">{a.title}</div>

        {productText || a.nm_id ? (
          <div className="text-xs text-muted-foreground truncate">
            {a.nm_id ? (
              <Link
                to="/products/$nmId"
                params={{ nmId: String(a.nm_id) }}
                className="font-medium text-foreground hover:underline"
              >
                {productText || `nm ${a.nm_id}`}
              </Link>
            ) : (
              productText
            )}
          </div>
        ) : null}

        {claimsLocked ? (
          <Button
            size="sm"
            variant="outline"
            className="w-full min-h-10 text-xs"
            disabled
          >
            <Lock className="mr-1 h-3.5 w-3.5" /> Модуль отключён
          </Button>
        ) : primaryAction?.href ? (
          primaryAction.external ? (
            <Button asChild size="sm" className="w-full min-h-10 text-xs">
              <a href={primaryAction.href} target="_blank" rel="noreferrer">
                <Wrench className="mr-1 h-3.5 w-3.5" />
                {primaryAction.label}
              </a>
            </Button>
          ) : (
            <Button asChild size="sm" className="w-full min-h-10 text-xs">
              <Link to={primaryAction.href}>
                <Wrench className="mr-1 h-3.5 w-3.5" />
                {primaryAction.label}
              </Link>
            </Button>
          )
        ) : disabledPrimaryAction ? (
          <Button
            size="sm"
            className="w-full min-h-10 text-xs justify-start"
            disabled
          >
            <Lock className="mr-1 h-3.5 w-3.5" />
            <span className="truncate">
              {disabledPrimaryAction.label ?? "Действие недоступно"}
            </span>
          </Button>
        ) : null}

        <div className="grid grid-cols-2 gap-2">
          <Button
            size="sm"
            variant="outline"
            className="min-h-10 text-xs"
            onClick={() => onOpenTask(a, rowKey)}
          >
            Открыть задачу <ArrowRight className="ml-1 h-3.5 w-3.5" />
          </Button>
          {actionLedger || evidenceInsufficient ? (
            <Button
              size="sm"
              variant="outline"
              className={`min-h-10 text-xs ${evidenceInsufficient ? EVIDENCE_STATE_CLASS[a.evidence_state] : ""}`}
              onClick={() =>
                onOpenEvidence(a.title ?? "Действие", actionLedger)
              }
            >
              {evidenceInsufficient ? (
                <AlertTriangle className="mr-1 h-3.5 w-3.5" />
              ) : null}
              Как посчитано?
            </Button>
          ) : null}
        </div>

        <div className="grid grid-cols-1 gap-1.5 text-[11px] text-muted-foreground border-t pt-2">
          <span className="inline-flex items-center gap-1">
            <UserRound className="h-3.5 w-3.5 shrink-0" />
            {assigneeLabel(a, currentUserId)}
          </span>
          <span
            className={`inline-flex items-center gap-1 ${overdue ? "font-medium text-destructive" : ""}`}
          >
            <CalendarClock className="h-3.5 w-3.5 shrink-0" />
            {deadline.label}
            {deadline.detail ? (
              <span className="text-muted-foreground">{deadline.detail}</span>
            ) : null}
          </span>
          {a.money_impact_amount != null ? (
            <span className="font-medium text-foreground">
              {formatMoney(a.money_impact_amount)}
            </span>
          ) : null}
        </div>

        {canUpdate && !claimsLocked ? (
          <Select
            value={a.status && a.status !== "open" ? a.status : undefined}
            disabled={busy === rowKey}
            onValueChange={(v) => onStatusChange(rowKey, a, v)}
          >
            <SelectTrigger
              className="w-full min-h-10 text-xs"
              aria-label="Изменить статус"
            >
              <SelectValue placeholder="Изменить статус" />
            </SelectTrigger>
            <SelectContent>
              {statusOptions.map((s) => (
                <SelectItem key={s.value} value={s.value} className="text-xs">
                  {s.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        ) : claimsLocked ? null : (
          <Badge
            variant="outline"
            className="text-[10px] border-muted-foreground/30 text-muted-foreground w-fit"
          >
            <Info className="mr-1 h-3 w-3" />
            {canUpdateReasonLabel(a.can_update_reason)}
          </Badge>
        )}
      </CardContent>
    </Card>
  );
}
