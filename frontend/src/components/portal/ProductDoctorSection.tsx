// @ts-nocheck
import { useMemo, useState } from "react";
import { Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  ChevronDown,
  ShieldCheck,
} from "lucide-react";
import { useIsMobile } from "@/hooks/use-mobile";
import { ProductEmptyState } from "@/components/portal/ProductEmptyState";

import {
  fetchResults,
  type PortalAction,
  type PortalDataBlock,
  type ProblemResultEvent,
  type PortalResultEventsPage,
  type ProblemResultStatus,
} from "@/lib/portal";
import {
  portalActionToActionCenterItem,
  product360ProblemToActionCenterLink,
  type ActionCenterItem,
} from "@/lib/action-center-contract";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EvidenceDrawer } from "@/components/EvidenceDrawer";
import { ProductProblemDrawer } from "@/components/portal/ProductProblemDrawer";
import { type EvidenceLedger } from "@/lib/evidence";
import { formatMoney } from "@/lib/format";
import { useAuth } from "@/lib/auth-context";
import { useAccounts } from "@/lib/account-context";
import {
  isTestOnlyProblem,
  problemCode,
  ProblemEmptyState,
  SellerProblemCard,
} from "@/components/problem/SellerProblemUX";
import {
  problemGroupLabel,
  problemRecheckStatusLabel,
  problemResultStatusLabel,
  problemStatusLabel,
} from "@/lib/problem-ux-copy";
import {
  problemResultBadgeStatus,
  problemResultContractValue,
  problemResultForAction,
  problemResultSummaryFromPage,
} from "@/lib/problem-results";
import { dedupeProblemItems } from "@/lib/problem-dedupe";
import {
  primaryActionForItem,
  primaryDisabledActionForItem,
  resultsHrefForAction,
} from "@/lib/action-center-actions";

type ProductDoctorSectionProps = {
  block?: PortalDataBlock | null;
  actions?: PortalAction[];
  resultHistory?: PortalDataBlock | PortalResultEventsPage | null;
  cardQuality?: any;
  nmId: number | string;
  className?: string;
};

const GROUP_TITLES: Record<string, string> = {
  profitability: problemGroupLabel("profitability"),
  stock: problemGroupLabel("stock"),
  price: problemGroupLabel("price"),
  ads_promo: problemGroupLabel("ads_promo"),
  card_quality: problemGroupLabel("card_quality"),
  data_blockers: problemGroupLabel("data_blockers"),
  system_checks: problemGroupLabel("system_checks"),
};

const GROUP_ORDER = [
  "profitability",
  "stock",
  "price",
  "ads_promo",
  "card_quality",
  "data_blockers",
  "system_checks",
];
const CHECKER_SECTION_DESCRIPTION =
  "Контентные возможности проверки карточки показаны отдельно от финансовых проблем.";

const RESULT_BADGE_CLASS: Record<ProblemResultStatus, string> = {
  pending_data:
    "border-sky-500/35 bg-sky-500/10 text-sky-700 dark:text-sky-300",
  improved:
    "border-emerald-500/40 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
  worse: "border-destructive/35 bg-destructive/10 text-destructive",
  neutral: "border-border bg-muted text-muted-foreground",
  not_enough_data:
    "border-amber-500/45 bg-amber-500/10 text-amber-800 dark:text-amber-200",
};

type ProductDoctorBackendGroup = {
  key?: unknown;
  title?: unknown;
  items?: unknown[];
  open_count?: unknown;
  resolved_count?: unknown;
};

type ProductDoctorData = {
  open?: unknown[];
  resolved?: unknown[];
  groups?: ProductDoctorBackendGroup[];
  summary?: {
    open_count?: unknown;
    resolved_count?: unknown;
    money_impact?: {
      confirmed_loss_amount?: unknown;
      lost_sales_risk_amount?: unknown;
      blocked_cash_amount?: unknown;
      opportunity_amount?: unknown;
      currency?: unknown;
    };
  };
  empty_state?: {
    kind?: unknown;
    message?: unknown;
  };
};

type ProductResultHistoryData = {
  result_events?: unknown[];
  items?: unknown[];
  recent_events?: unknown[];
  result_summary?: Record<string, unknown>;
  summary?: Record<string, unknown>;
  status?: unknown;
  by_module?: Record<string, unknown>;
  by_outcome?: Record<string, unknown>;
  pending_followups?: Record<string, unknown>[];
  finance_windows?: Record<string, unknown>;
  disclaimer?: string | null;
  unavailable_sources?: string[];
};

type ProductDoctorGroup = {
  key: string;
  title: string;
  items: ActionCenterItem[];
  open_count: number;
  resolved_count: number;
};

function sectionData<T = unknown>(section: unknown): T | null {
  if (section == null) return null;
  if (typeof section === "object" && "data" in section)
    return (section.data ?? null) as T | null;
  return section as T;
}

function text(value: unknown, fallback = ""): string {
  const raw = String(value ?? "").trim();
  return raw || fallback;
}

function formatPreviewDate(value: unknown): string | null {
  if (!value) return null;
  const date = new Date(String(value));
  if (Number.isNaN(date.getTime())) return null;
  return date.toLocaleString("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatTaskDeadline(value: unknown): string | null {
  if (!value) return null;
  const date = new Date(String(value));
  if (Number.isNaN(date.getTime())) return null;
  return date.toLocaleDateString("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  });
}

function resultPageFromHistory(value: unknown): PortalResultEventsPage | null {
  const data = sectionData<ProductResultHistoryData>(value);
  if (!data) return null;
  const rawItems = Array.isArray(data.result_events)
    ? data.result_events
    : Array.isArray(data.items)
      ? data.items
      : Array.isArray(data.recent_events)
        ? data.recent_events
        : [];
  const items = rawItems.filter(
    (item): item is ProblemResultEvent => !!item && typeof item === "object",
  );
  if (!items.length && !data.result_summary && !data.summary) return null;
  const summary = data.result_summary ?? data.summary ?? {};
  return {
    status: String(data.status ?? "ok"),
    total: items.length,
    limit: items.length,
    offset: 0,
    items,
    recent_events: items,
    summary,
    by_module: data.by_module ?? {},
    by_outcome: data.by_outcome ?? {},
    pending_followups: data.pending_followups ?? [],
    finance_windows: data.finance_windows ?? {},
    disclaimer: data.disclaimer ?? null,
    unavailable_sources: data.unavailable_sources ?? [],
  };
}

function toActionCenterProblem(value: unknown): ActionCenterItem | null {
  if (!value || typeof value !== "object") return null;
  if ("source_kind" in value && "evidence_state" in value) {
    return value as ActionCenterItem;
  }
  return portalActionToActionCenterItem(value as PortalAction);
}

function normalizeProblemItems(
  items: unknown[] | undefined,
): ActionCenterItem[] {
  return (Array.isArray(items) ? items : [])
    .map(toActionCenterProblem)
    .filter((item): item is ActionCenterItem => !!item);
}

function actionCategory(action: ActionCenterItem): string {
  const raw = text(action.source_kind).toLowerCase();
  const code = problemCode(action);
  const impact = text(action.impact_type).toLowerCase();
  const module = text((action as any).source_module).toLowerCase();
  const joined = `${raw} ${code} ${impact} ${module}`;
  if (
    impact === "system_warning" ||
    joined.includes("system") ||
    joined.includes("sync") ||
    joined.includes("freshness") ||
    joined.includes("reconciliation") ||
    joined.includes("admin")
  )
    return "system_checks";
  if (
    joined.includes("card_quality") ||
    joined.includes("content") ||
    joined.includes("photo") ||
    raw === "checker"
  )
    return "card_quality";
  if (
    joined.includes("data") ||
    joined.includes("missing_cost") ||
    joined.includes("blocker") ||
    joined.includes("unmatched_sku")
  )
    return "data_blockers";
  if (
    joined.includes("stock") ||
    joined.includes("overstock") ||
    joined.includes("depletion")
  )
    return "stock";
  if (joined.includes("price") || joined.includes("margin")) return "price";
  if (joined.includes("ads") || joined.includes("promo")) return "ads_promo";
  return "profitability";
}

function isResolved(action: ActionCenterItem): boolean {
  const raw = text(action.status).toLowerCase();
  return ["done", "resolved", "dismissed", "ignored", "closed"].includes(raw);
}

function isCheckerProblemBridge(action: ActionCenterItem): boolean {
  return action.source_kind === "checker" && action.is_problem_like;
}

function emptyKind(value: unknown): string {
  const raw = text(value).toLowerCase();
  if (raw === "sync_not_completed") return "sync_required";
  if (raw === "data_missing") return "missing_data";
  return raw || "no_issues";
}

function latestStatusChange(
  action: ActionCenterItem,
  resultPage?: PortalResultEventsPage | null,
): string {
  const summary = resultPage ? problemResultSummaryFromPage(resultPage) : null;
  const latest = summary?.status_history
    ?.slice()
    .reverse()
    .find((item) => {
      const type = text(item.event_type).toLowerCase();
      return [
        "action_started",
        "status_changed",
        "action_completed",
        "recheck_result",
      ].includes(type);
    });
  if (latest) {
    const label = problemStatusLabel(
      latest.new_status ?? latest.status ?? latest.event_type,
    );
    const date = formatPreviewDate(latest.created_at);
    return date ? `${label} · ${date}` : label;
  }
  const fallbackDate = formatPreviewDate(
    action.last_status_changed_at ?? action.created_at,
  );
  return fallbackDate
    ? `Последнее изменение · ${fallbackDate}`
    : "Изменений ещё не было";
}

function recheckPreview(
  action: ActionCenterItem,
  resultPage?: PortalResultEventsPage | null,
): string {
  const events = Array.isArray(resultPage?.items)
    ? (resultPage?.items ?? [])
    : Array.isArray(resultPage?.recent_events)
      ? (resultPage?.recent_events ?? [])
      : [];
  const event = events.find((item) => item.event_type === "recheck_result");
  if (event) {
    const date = formatPreviewDate(event.created_at);
    const label = problemRecheckStatusLabel(event.outcome);
    return date ? `${label} · ${date}` : label;
  }
  const actions = action.allowed_actions;
  return actions.includes("recheck")
    ? "Можно перепроверить"
    : "Перепроверка ещё не запускалась";
}

function currentStatus(action: ActionCenterItem): string {
  return problemStatusLabel(action.status ?? "new");
}

function ProductProblemPreview({
  action,
  resultPage,
  resultStatus,
}: {
  action: ActionCenterItem;
  resultPage?: PortalResultEventsPage | null;
  resultStatus: ProblemResultStatus;
}) {
  return (
    <div
      className="rounded-md border bg-muted/20 p-2 text-xs"
      data-product-doctor-preview="1"
    >
      <div className="flex flex-wrap gap-1.5">
        <Badge variant="outline" className="text-[10px]">
          Статус: {currentStatus(action)}
        </Badge>
        <Badge variant="outline" className="text-[10px]">
          Изменение: {latestStatusChange(action, resultPage)}
        </Badge>
        <Badge variant="outline" className="text-[10px]">
          Проверка: {recheckPreview(action, resultPage)}
        </Badge>
        <Badge
          variant="outline"
          className={`text-[10px] ${RESULT_BADGE_CLASS[resultStatus]}`}
        >
          Результат: {problemResultStatusLabel(resultStatus)}
        </Badge>
      </div>
    </div>
  );
}

function Product360ProblemCard({
  action,
  resultPage,
  resultStatus,
  onEvidence,
  onOpenProblem,
}: {
  action: ActionCenterItem;
  resultPage?: PortalResultEventsPage | null;
  resultStatus: ProblemResultStatus;
  onEvidence: (title: string, ledger: EvidenceLedger | null) => void;
  onOpenProblem?: (action: ActionCenterItem) => void;
}) {
  const primaryAction = primaryActionForItem(action);
  const disabledPrimaryAction = primaryDisabledActionForItem(action);
  const actionCenterSearch = product360ProblemToActionCenterLink(action);
  const resultHref = resultsHrefForAction(action);
  const assignee = action.assigned_to_user_name?.trim()
    ? action.assigned_to_user_name
    : action.assigned_to_user_id != null
      ? `Пользователь #${action.assigned_to_user_id}`
      : "Не назначено";
  const deadline = formatTaskDeadline(action.deadline_at);
  const disabledReason =
    disabledPrimaryAction?.disabled_reason ||
    disabledPrimaryAction?.label ||
    "Действие пока недоступно.";

  return (
    <div
      className="space-y-2 rounded-md border bg-background p-3"
      data-testid="product360-problem-card"
      data-problem-code={
        action.problem_code ?? action.detector_code ?? action.action_type ?? ""
      }
      data-problem-instance-id={action.problem_instance_id ?? ""}
    >
      <ProductProblemPreview
        action={action}
        resultPage={resultPage}
        resultStatus={resultStatus}
      />

      <SellerProblemCard
        problem={action}
        result={resultPage ? problemResultContractValue(resultPage) : undefined}
        showActions={false}
        showActionCenterLink={false}
        className="border-0 bg-transparent p-0 shadow-none"
        onEvidence={onEvidence}
      />

      <div
        className="flex flex-wrap items-center gap-1.5 text-xs"
        data-testid="product360-problem-task-meta"
      >
        <Badge variant="outline" className="text-[10px]">
          Ответственный: {assignee}
        </Badge>
        <Badge variant="outline" className="text-[10px]">
          {deadline ? `Срок: ${deadline}` : "Без срока"}
        </Badge>
      </div>

      <div className="flex flex-wrap gap-1.5 pt-1">
        {onOpenProblem ? (
          <Button
            type="button"
            size="sm"
            variant="secondary"
            className="h-8 text-xs"
            onClick={() => onOpenProblem(action)}
            data-testid="product360-problem-open-drawer"
          >
            Подробнее
          </Button>
        ) : null}
        {primaryAction?.href ? (
          primaryAction.external ? (
            <Button asChild size="sm" className="h-8 text-xs">
              <a
                href={primaryAction.href}
                target="_blank"
                rel="noreferrer"
                data-testid="product360-primary-action"
              >
                {primaryAction.label}
                <ArrowRight className="ml-1 h-3.5 w-3.5" />
              </a>
            </Button>
          ) : (
            <Button asChild size="sm" className="h-8 text-xs">
              <Link
                to={primaryAction.href}
                data-testid="product360-primary-action"
              >
                {primaryAction.label}
                <ArrowRight className="ml-1 h-3.5 w-3.5" />
              </Link>
            </Button>
          )
        ) : disabledPrimaryAction?.href ? (
          <Button
            type="button"
            size="sm"
            className="h-8 max-w-full justify-start text-left text-xs"
            disabled
            title={disabledReason}
            data-testid="product360-primary-action-disabled"
          >
            {disabledPrimaryAction.label}: {disabledReason}
          </Button>
        ) : null}

        <Button asChild size="sm" variant="outline" className="h-8 text-xs">
          <Link to={resultHref} data-testid="product360-results-link">
            Открыть результаты
            <ArrowRight className="ml-1 h-3.5 w-3.5" />
          </Link>
        </Button>

        <Button asChild size="sm" variant="ghost" className="h-8 text-xs">
          <Link
            to="/action-center"
            search={actionCenterSearch}
            data-testid="product360-open-task-link"
          >
            Открыть задачу
            <ArrowRight className="ml-1 h-3.5 w-3.5" />
          </Link>
        </Button>
      </div>
    </div>
  );
}

function CardQualityGroupSummary({
  cardQuality,
  nmId,
}: {
  cardQuality?: any;
  nmId: number | string;
}) {
  if (!cardQuality) return null;
  const data = sectionData<any>(cardQuality) ?? {};
  const status = text(
    (cardQuality?.status ?? data?.status),
    "",
  ).toLowerCase();
  if (status === "not_configured" || status === "disabled") return null;
  const score =
    typeof data.score === "number"
      ? data.score
      : typeof data.checker_score === "number"
        ? data.checker_score
        : null;
  const issues: any[] = Array.isArray(data.issues) ? data.issues : [];
  const analyzedAt =
    data.analyzed_at ?? data.updated_at ?? data.last_analyzed_at ?? null;
  const analyzedText = formatPreviewDate(analyzedAt);
  const topIssues = issues.slice(0, 3);
  const nothingToShow =
    score == null && issues.length === 0 && !analyzedText;
  if (nothingToShow) return null;
  return (
    <div
      className="rounded-md border bg-muted/30 p-2.5 text-xs space-y-2"
      data-testid="card-quality-group-summary"
    >
      <div className="flex flex-wrap items-center gap-1.5">
        <Badge variant="outline" className="text-[10px]">
          <ShieldCheck className="mr-1 h-3 w-3" /> Возможность / оценка
        </Badge>
        {score != null ? (
          <Badge variant="outline" className="text-[10px]">
            Оценка: {Math.round(Number(score))}
          </Badge>
        ) : null}
        <Badge variant="outline" className="text-[10px]">
          Открытых проблем: {issues.length}
        </Badge>
        {analyzedText ? (
          <Badge variant="outline" className="text-[10px]">
            Проверено: {analyzedText}
          </Badge>
        ) : null}
      </div>
      <div className="text-[11px] text-muted-foreground">
        Сигналы карточки — возможности роста, не подтверждённый убыток.
      </div>
      {topIssues.length > 0 ? (
        <ul className="list-disc pl-4 space-y-0.5 text-[11px] text-foreground/80">
          {topIssues.map((it: any, idx: number) => (
            <li key={String(it.id ?? it.code ?? idx)} className="truncate">
              {text(it.title ?? it.name ?? it.code ?? it.message, "Проблема карточки")}
            </li>
          ))}
        </ul>
      ) : null}
      <div className="flex flex-wrap gap-1.5">
        <Button asChild size="sm" variant="outline" className="h-7 text-xs">
          <Link to="/checker/$nmId" params={{ nmId: String(nmId) }}>
            Проверить карточку <ArrowRight className="ml-1 h-3 w-3" />
          </Link>
        </Button>
        <Button asChild size="sm" variant="ghost" className="h-7 text-xs">
          <Link to="/checker/$nmId" params={{ nmId: String(nmId) }}>
            Открыть Checker
          </Link>
        </Button>
      </div>
    </div>
  );
}

function ProblemGroupShell({
  title,
  openCount,
  resolvedCount,
  isMobile,
  defaultOpen,
  children,
}: {
  title: string;
  openCount: number;
  resolvedCount: number;
  isMobile: boolean;
  defaultOpen: boolean;
  children: React.ReactNode;
}) {
  const header = (
    <div className="flex items-center justify-between gap-2 w-full">
      <div className="flex items-center gap-2 text-xs font-semibold uppercase text-muted-foreground">
        {isMobile ? <ChevronDown className="h-3.5 w-3.5 transition-transform group-open:rotate-180" /> : null}
        {title}
      </div>
      <div className="flex gap-1">
        <Badge variant="outline" className="text-[10px]">
          открыто {openCount}
        </Badge>
        <Badge variant="outline" className="text-[10px]">
          решено {resolvedCount}
        </Badge>
      </div>
    </div>
  );
  if (isMobile) {
    return (
      <details open={defaultOpen} className="group space-y-2">
        <summary className="cursor-pointer list-none">{header}</summary>
        <div className="pt-2 space-y-2">{children}</div>
      </details>
    );
  }
  return (
    <div className="space-y-2">
      {header}
      {children}
    </div>
  );
}

export function ProductDoctorSection({
  block,
  actions,
  resultHistory,
  cardQuality,
  nmId,
  className,
}: ProductDoctorSectionProps) {
  const isMobile = useIsMobile();
  const { user } = useAuth();
  const { activeId } = useAccounts();
  const [drawer, setDrawer] = useState<{
    title: string;
    ledger: EvidenceLedger | null;
  } | null>(null);
  const [problemDrawer, setProblemDrawer] = useState<ActionCenterItem | null>(null);
  const canSeeTestRules = !!user?.is_superuser;
  const data = sectionData<ProductDoctorData>(block) ?? {};
  const visible = (items: ActionCenterItem[]) =>
    items.filter((item) => canSeeTestRules || !isTestOnlyProblem(item));
  const visibleActions = dedupeProblemItems(
    visible(normalizeProblemItems(actions)),
  );
  const fallbackActions = visibleActions.filter(
    (action) => action.source_module === "problem_engine",
  );
  const checkerActions = visibleActions.filter(isCheckerProblemBridge);
  const open = dedupeProblemItems(
    visible(
      data.open
        ? normalizeProblemItems(data.open)
        : fallbackActions.filter((action) => !isResolved(action)),
    ),
  );
  const resolved = dedupeProblemItems(
    visible(
      data.resolved
        ? normalizeProblemItems(data.resolved)
        : fallbackActions.filter(isResolved),
    ),
  );
  const groups = useMemo(() => {
    const fromBackend = Array.isArray(data.groups) ? data.groups : [];
    const grouped = new Map<string, ProductDoctorGroup>();
    for (const key of GROUP_ORDER) {
      grouped.set(key, {
        key,
        title: GROUP_TITLES[key],
        items: [],
        open_count: 0,
        resolved_count: 0,
      });
    }
    if (fromBackend.length > 0) {
      for (const group of fromBackend) {
        const items = dedupeProblemItems(
          visible(normalizeProblemItems(group.items)),
        );
        const key = text(
          group.key,
          items[0] ? actionCategory(items[0]) : "profitability",
        ).toLowerCase();
        const safeKey = GROUP_TITLES[key]
          ? key
          : items[0]
            ? actionCategory(items[0])
            : "profitability";
        grouped.set(safeKey, {
          key: safeKey,
          title: GROUP_TITLES[safeKey] ?? problemGroupLabel(safeKey),
          items,
          open_count: items.filter((item) => !isResolved(item)).length,
          resolved_count: items.filter(isResolved).length,
        });
      }
      return GROUP_ORDER.map((key) => grouped.get(key));
    }
    for (const action of [...open, ...resolved]) {
      const key = actionCategory(action);
      const group = grouped.get(key)!;
      group.items.push(action);
      if (isResolved(action)) group.resolved_count += 1;
      else group.open_count += 1;
    }
    // Fold checker bridge items into the "Качество карточки" group so we
    // don't render a duplicate standalone section below.
    const cardGroup = grouped.get("card_quality")!;
    const alreadyIn = new Set(cardGroup.items.map((i: any) => String(i.id ?? i.source_id ?? "")));
    for (const action of checkerActions) {
      const key = String(action.id ?? action.source_id ?? "");
      if (key && alreadyIn.has(key)) continue;
      cardGroup.items.push(action);
      if (isResolved(action)) cardGroup.resolved_count += 1;
      else cardGroup.open_count += 1;
    }
    return GROUP_ORDER.map((key) => grouped.get(key));
  }, [canSeeTestRules, data.groups, open, resolved, checkerActions]);

  const summary = data.summary ?? {};
  const emptyState = data.empty_state ?? {};
  const hasBusinessProblems = open.length > 0 || resolved.length > 0;
  const hasProblems = hasBusinessProblems || checkerActions.length > 0;
  const checkerOpenCount = checkerActions.filter(
    (item) => !isResolved(item),
  ).length;
  const checkerResolvedCount = checkerActions.filter(isResolved).length;
  const receivedResultPage = useMemo(
    () => resultPageFromHistory(resultHistory),
    [resultHistory],
  );
  const resultsQ = useQuery({
    queryKey: ["portal-results", "product-doctor", activeId, String(nmId)],
    queryFn: () =>
      fetchResults(activeId, {
        source_module: "problem_engine",
        nm_id: String(nmId),
        limit: 300,
        offset: 0,
      }),
    enabled: !!activeId && hasBusinessProblems,
    retry: false,
    staleTime: 30_000,
    initialData: receivedResultPage ?? undefined,
  });
  const productResultPage = resultsQ.data ?? receivedResultPage;
  const status = text(
    block?.status,
    hasProblems ? "ok" : "empty",
  ).toLowerCase();
  const statusIcon =
    status === "blocked" || status === "warning" ? (
      <AlertTriangle className="h-4 w-4" />
    ) : hasProblems ? (
      <Activity className="h-4 w-4" />
    ) : (
      <CheckCircle2 className="h-4 w-4" />
    );

  return (
    <>
      <Card className={className} data-testid="product-doctor-section">
        <CardContent className="space-y-4 p-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <div className="flex items-center gap-2 text-sm font-semibold">
                {statusIcon}
                Проблемы товара
              </div>
              <div className="text-xs text-muted-foreground">
                Платформа проверяет прибыльность, остатки, цену, рекламу, промо,
                качество карточки и блокеры данных по этому товару.
              </div>
            </div>
            <div className="flex flex-wrap items-center justify-end gap-2">
              <Badge variant="outline" className="text-[10px]">
                открыто {Number(summary.open_count ?? open.length)}
              </Badge>
              <Badge variant="outline" className="text-[10px]">
                решено {Number(summary.resolved_count ?? resolved.length)}
              </Badge>
              {checkerActions.length > 0 ? (
                <Badge variant="outline" className="text-[10px]">
                  карточка {checkerOpenCount} / {checkerResolvedCount}
                </Badge>
              ) : null}
              {summary?.money_impact?.confirmed_loss_amount ? (
                <Badge
                  variant="outline"
                  className="border-destructive/30 bg-destructive/10 text-[10px] text-destructive"
                >
                  подтвержденный убыток{" "}
                  {formatMoney(
                    Number(summary.money_impact.confirmed_loss_amount),
                  )}
                </Badge>
              ) : null}
              {summary?.money_impact?.lost_sales_risk_amount ? (
                <Badge
                  variant="outline"
                  className="border-amber-500/35 bg-amber-500/10 text-[10px] text-amber-800 dark:text-amber-300"
                >
                  риск потери продаж{" "}
                  {formatMoney(
                    Number(summary.money_impact.lost_sales_risk_amount),
                  )}
                </Badge>
              ) : null}
              {summary?.money_impact?.blocked_cash_amount ? (
                <Badge
                  variant="outline"
                  className="border-orange-500/35 bg-orange-500/10 text-[10px] text-orange-800 dark:text-orange-300"
                >
                  замороженные деньги{" "}
                  {formatMoney(
                    Number(summary.money_impact.blocked_cash_amount),
                  )}
                </Badge>
              ) : null}
            </div>
          </div>

          {!hasProblems ? (
            <ProductEmptyState
              kind={
                emptyKind(emptyState.kind) === "sync_required"
                  ? "needs_sync"
                  : emptyKind(emptyState.kind) === "missing_data"
                    ? "missing_data"
                    : "no_problems"
              }
              hint={text(emptyState.message) || undefined}
            />
          ) : (
            <div className="space-y-4">
              {groups.map((group) => {
                if (!group) return null;
                const items = group.items;
                const openC = Number(
                  group.open_count ??
                    items.filter((item) => !isResolved(item)).length,
                );
                const resolvedC = Number(
                  group.resolved_count ?? items.filter(isResolved).length,
                );
                const defaultOpen = openC > 0;
                return (
                  <ProblemGroupShell
                    key={group.key ?? group.title}
                    title={
                      GROUP_TITLES[group.key] ??
                      problemGroupLabel(group.key ?? group.title)
                    }
                    openCount={openC}
                    resolvedCount={resolvedC}
                    isMobile={isMobile}
                    defaultOpen={defaultOpen}
                  >
                    {group.key === "card_quality" ? (
                      <CardQualityGroupSummary
                        cardQuality={cardQuality}
                        nmId={nmId}
                      />
                    ) : null}
                    {items.length === 0 ? (
                      <div className="rounded border border-dashed px-3 py-2 text-xs text-muted-foreground">
                        В этой группе проблем нет.
                      </div>
                    ) : (
                      <div className="grid gap-2 lg:grid-cols-2">
                        {items.map((action, index) => {
                          const resultPage = problemResultForAction(
                            action,
                            productResultPage,
                          );
                          const status = resultPage
                            ? problemResultBadgeStatus(resultPage)
                            : "pending_data";
                          return (
                            <Product360ProblemCard
                              key={String(
                                action.id ??
                                  action.source_id ??
                                  `${group.key}-${index}`,
                              )}
                              action={action}
                              resultPage={resultPage}
                              resultStatus={status}
                              onEvidence={(title, ledger) =>
                                setDrawer({ title, ledger })
                              }
                              onOpenProblem={(a) => setProblemDrawer(a)}
                            />
                          );
                        })}
                      </div>
                    )}
                  </ProblemGroupShell>
                );
              })}
            </div>
          )}
        </CardContent>
      </Card>
      <EvidenceDrawer
        open={!!drawer}
        onOpenChange={(open) => {
          if (!open) setDrawer(null);
        }}
        title={drawer?.title}
        ledger={drawer?.ledger}
      />
      <ProductProblemDrawer
        open={!!problemDrawer}
        onOpenChange={(open) => {
          if (!open) setProblemDrawer(null);
        }}
        problem={problemDrawer}
        resultPage={
          problemDrawer
            ? problemResultForAction(problemDrawer, productResultPage)
            : null
        }
        onEvidence={(title, ledger) => setDrawer({ title, ledger })}
      />
    </>
  );
}
