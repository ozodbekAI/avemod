// @ts-nocheck
import { Link } from "@tanstack/react-router";
import { ArrowLeft, ListChecks } from "lucide-react";

import {
  actionCenterTaskHref,
  actionCenterTaskSearch,
  type ActionCenterRouteContext,
} from "@/lib/action-center-routing";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";

type Props = ActionCenterRouteContext & {
  title?: string;
  description?: string;
  className?: string;
};

export function ActionCenterReturnLink({
  action_id,
  problem_instance_id,
  nm_id,
  source,
  source_id,
  code,
  title = "Открыто из Центра действий",
  description = "Контекст задачи сохранён. Вернитесь к той же задаче после локального действия или проверки.",
  className,
}: Props) {
  const browserSearch =
    typeof window === "undefined"
      ? null
      : new URLSearchParams(window.location.search);
  const effectiveProblemInstanceId =
    problem_instance_id ?? browserSearch?.get("problem_instance_id") ?? null;
  const effectiveActionId = action_id ?? browserSearch?.get("action_id") ?? null;
  const effectiveNmId = nm_id ?? browserSearch?.get("nm_id") ?? null;
  const effectiveSource = source ?? browserSearch?.get("source") ?? null;
  const effectiveSourceId = source_id ?? browserSearch?.get("source_id") ?? null;
  const effectiveCode = code ?? browserSearch?.get("code") ?? null;
  const ctx = {
    action_id: effectiveActionId,
    problem_instance_id: effectiveProblemInstanceId,
    nm_id: effectiveNmId,
    source: effectiveSource,
    source_id: effectiveSourceId,
    code: effectiveCode,
  };
  const href = actionCenterTaskHref(ctx);
  if (!effectiveActionId && !effectiveProblemInstanceId && !effectiveSourceId && !effectiveCode) return null;

  return (
    <Alert data-testid="action-center-return-link" className={className}>
      <ListChecks className="h-4 w-4" />
      <AlertTitle>{title}</AlertTitle>
      <AlertDescription className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <span>{description}</span>
        <Button asChild size="sm" variant="outline" className="shrink-0">
          <Link
            to="/action-center"
            search={actionCenterTaskSearch(ctx)}
          >
            <ArrowLeft className="mr-1.5 h-4 w-4" />
            Вернуться к задаче
          </Link>
        </Button>
        <span className="sr-only">{href}</span>
      </AlertDescription>
    </Alert>
  );
}
