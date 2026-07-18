import { Badge } from "@/components/ui/badge";
import type { ActionCenterItem } from "@/lib/action-center-contract";
import {
  resultIsCorrelationOnly,
  resultStatusFromSummary,
  resultSummaryFromAction,
  ROW_RESULT_STATUS_CLASS,
} from "@/lib/action-center-results";
import type { PortalResultEventsPage } from "@/lib/portal";
import { problemResultStatusLabel } from "@/lib/problem-ux-copy";

export function DynamicProblemRowResultBadge({
  action,
  resultPage,
}: {
  action: ActionCenterItem;
  resultPage?: PortalResultEventsPage | null;
}) {
  const summary = resultSummaryFromAction(action, resultPage);
  const status = resultStatusFromSummary(summary);
  const correlationOnly = resultIsCorrelationOnly(summary);
  return (
    <span
      data-problem-row-result="1"
      className="inline-flex flex-wrap items-center gap-1"
    >
      <Badge
        variant="outline"
        className={`text-[10px] ${ROW_RESULT_STATUS_CLASS[status]}`}
      >
        {problemResultStatusLabel(status)}
      </Badge>
      {correlationOnly ? (
        <Badge
          variant="outline"
          className="text-[10px] border-muted-foreground/30 text-muted-foreground"
        >
          корреляция
        </Badge>
      ) : null}
    </span>
  );
}
