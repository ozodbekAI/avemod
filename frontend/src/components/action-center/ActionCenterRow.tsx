// @ts-nocheck
import { Link } from "@tanstack/react-router";
import {
  AlertTriangle,
  ArrowRight,
  CalendarClock,
  ExternalLink,
  Info,
  Lock,
  UserRound,
  Wrench,
} from "lucide-react";
import { EvidenceButton } from "@/components/EvidenceDrawer";
import {
  EvidenceTrustBadge,
  MoneyTrustBadge,
} from "@/components/MoneyTrustBadge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { EVIDENCE_STATE_CLASS } from "@/components/action-center/ActionCenterEvidenceControls";
import { DynamicProblemRowResultBadge } from "@/components/action-center/DynamicProblemRowResultBadge";
import {
  actionCenterResultPageForItem,
  dataFreshnessBlocksAction,
  dataFreshnessStatusLabel,
  type ActionCenterItem,
} from "@/lib/action-center-contract";
import {
  actionRequirementText,
  primaryActionForItem,
  primaryDisabledActionForItem,
} from "@/lib/action-center-actions";
import {
  PRIO_COLORS,
  canUpdateReasonLabel,
  priorityLabel,
  sourceSyncStateLabel,
} from "@/lib/action-center-labels";
import {
  actionEvidenceLedger,
  assigneeLabel,
  effectiveResultStatus,
  formatDeadline,
  isBetaAction,
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
import {
  problemImpactLabel,
  problemResultStatusLabel,
  problemTrustLabel,
} from "@/lib/problem-ux-copy";

type ActionCenterRowProps = {
  action: ActionCenterItem;
  rowKey: string;
  canBulkManage: boolean;
  selected: boolean;
  claimsEnabled: boolean;
  currentUserId: number | null;
  now: Date;
  problemResultsPage?: PortalResultEventsPage | null;
  busy: string | null;
  onSelectedChange: (rowKey: string, checked: boolean) => void;
  onOpenTask: (action: ActionCenterItem, rowKey: string) => void;
  onOpenEvidence: (title: string, ledger: EvidenceLedger | null) => void;
  onStatusChange: (
    rowKey: string,
    action: ActionCenterItem,
    status: string,
  ) => void;
};

export function ActionCenterRow({
  action: a,
  rowKey,
  canBulkManage,
  selected,
  claimsEnabled,
  currentUserId,
  now,
  problemResultsPage,
  busy,
  onSelectedChange,
  onOpenTask,
  onOpenEvidence,
  onStatusChange,
}: ActionCenterRowProps) {
  const canUpdate = a.can_update;
  const dynamicProblem = isDynamicProblemAction(a);
  const statusOptions = statusOptionsForAction(a);
  const claimsAction = isClaimsAction(a);
  const betaAction = isBetaAction(a);
  const claimsLocked = claimsAction && !claimsEnabled;
  const actionLedger = actionEvidenceLedger(a);
  const rowResultPage = dynamicProblem
    ? actionCenterResultPageForItem(a, problemResultsPage)
    : null;
  const moneyTrust = a.money_trust;
  const primaryAction = primaryActionForItem(a);
  const deadline = formatDeadline(a, now);
  const overdue = isOverdueAction(a, now);
  const resultStatus: ProblemRowResultStatus = effectiveResultStatus(
    a,
    problemResultsPage,
  );
  const productText = [a.nm_id ? `nm ${a.nm_id}` : null, a.vendor_code]
    .filter(Boolean)
    .join(" / ");
  const disabledPrimaryAction = primaryDisabledActionForItem(a);
  const evidenceInsufficient =
    a.evidence_state === "partial_evidence" ||
    a.evidence_state === "missing_evidence";
  const disabledPrimaryReason =
    disabledPrimaryAction?.disabled_reason ?? "Действие сейчас недоступно.";
  const disabledPrimaryLabel = disabledPrimaryReason.replace(/\.$/, "");
  const sourceNeedsSync = dataFreshnessBlocksAction(a.data_freshness);
  const sourceFreshnessLabel = sourceNeedsSync
    ? dataFreshnessStatusLabel(a.data_freshness)
    : a.source_sync_state && a.source_sync_state !== "unknown"
      ? sourceSyncStateLabel(a.source_sync_state)
      : null;
  const sourceFreshnessClass = sourceNeedsSync
    ? "border-amber-500/45 bg-amber-500/10 text-amber-800 dark:text-amber-300"
    : "border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300";
  const impactLabel = a.impact_type ? problemImpactLabel(a.impact_type) : null;
  const moneyTrustLabel =
    moneyTrust && typeof moneyTrust.display_label === "string"
      ? moneyTrust.display_label
      : null;
  const showImpactBadge = impactLabel && impactLabel !== moneyTrustLabel;

  return (
    <div
      key={rowKey}
      data-mobile-action-card="1"
      className={`rounded-md border bg-background p-3 ${
        overdue ? "border-destructive/35 bg-destructive/5" : "border-border"
      }`}
    >
      <div
        data-testid="action-row"
        data-action-row="1"
        data-can-update={canUpdate ? "1" : "0"}
        data-source-module={a.source_module ?? ""}
        data-source-id={a.source_id != null ? String(a.source_id) : ""}
        data-status={a.status ?? ""}
        className="grid gap-3 md:grid-cols-[minmax(0,1fr)_auto] md:items-center"
      >
        <div className="min-w-0 space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            {canBulkManage ? (
              <Checkbox
                checked={selected}
                onCheckedChange={(checked) =>
                  onSelectedChange(rowKey, checked === true)
                }
                aria-label={`Выбрать: ${a.title}`}
              />
            ) : null}
            {a.priority ? (
              <Badge variant="outline" className={PRIO_COLORS[a.priority] ?? ""}>
                {priorityLabel(a.priority)}
              </Badge>
            ) : null}
            <Badge variant="secondary" className="text-[10px]">
              {a.status_label}
            </Badge>
            {overdue ? (
              <Badge variant="destructive" className="text-[10px]">
                Просрочено
              </Badge>
            ) : null}
          </div>
          <div className="line-clamp-2 text-sm font-semibold leading-snug">
            {a.title}
          </div>
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
            {a.nm_id ? (
              <Link
                to="/products/$nmId"
                params={{ nmId: String(a.nm_id) }}
                className="font-medium text-foreground hover:underline"
              >
                {productText || `nm ${a.nm_id}`}
              </Link>
            ) : (
              <span>{productText || "Товар не указан"}</span>
            )}
            {a.money_impact_amount != null ? (
              <span className="font-medium text-foreground">
                {formatMoney(a.money_impact_amount)}
              </span>
            ) : null}
            {sourceFreshnessLabel ? <span>{sourceFreshnessLabel}</span> : null}
          </div>
        </div>

        <Button
          size="sm"
          variant="outline"
          className="min-h-10 w-full text-xs md:w-auto"
          onClick={() => onOpenTask(a, rowKey)}
        >
          Открыть
          <ArrowRight className="ml-1 h-3.5 w-3.5" />
        </Button>
        </div>
      </div>
  );
}
