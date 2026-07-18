// @ts-nocheck
import { Link } from "@tanstack/react-router";
import type { ReactNode } from "react";
import { AlertTriangle, ArrowRight, CheckCircle2, ClipboardList, Database, FileQuestion, RefreshCw, Tag, Upload, UserPlus, Wrench, X } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EvidenceButton } from "@/components/EvidenceDrawer";
import { PriceSafetyMissingNotice, PriceSafetyPanel } from "@/components/PriceSafetyPanel";
import { formatMoney } from "@/lib/format";
import type { PortalAction } from "@/lib/portal";
import {
  actionCenterItemToSellerProblemContract,
  portalActionToActionCenterItem,
  product360ProblemToActionCenterLink,
  type ActionCenterItem,
} from "@/lib/action-center-contract";
import type {
  EvidenceLedger,
  SellerProblemContract,
  SellerProblemResultContract,
} from "@/lib/problem-contracts";
import {
  PROBLEM_ANSWER_LABELS,
  PROBLEM_EMPTY_STATE_COPY,
  problemActionLabel,
  problemImpactLabel,
  problemResultStatusLabel,
  problemSeverityLabel,
  problemStatusLabel,
  problemTrustLabel,
  seededProblemSellerNextStep,
} from "@/lib/problem-ux-copy";
import { cn } from "@/lib/utils";

export type SellerProblemLike = SellerProblemContract | ActionCenterItem | PortalAction;

export type SellerProblemTrust =
  | "confirmed"
  | "provisional"
  | "estimated"
  | "opportunity"
  | "blocked"
  | "test_only"
  | string;

export type SellerProblemImpact =
  | "confirmed_loss"
  | "probable_loss"
  | "blocked_cash"
  | "lost_sales_risk"
  | "opportunity"
  | "data_blocker"
  | "system_warning"
  | string;

export type SellerProblemResultStatus = SellerProblemResultContract["status"];

export type SellerProblemEvidenceQuality = "full" | "partial";
export type { SellerProblemContract };

const SEVERITY_CLASS: Record<string, string> = {
  critical: "border-destructive/35 bg-destructive/10 text-destructive",
  high: "border-warning/45 bg-warning/10 text-warning",
  medium: "border-primary/35 bg-primary/10 text-primary",
  low: "border-border bg-muted text-muted-foreground",
};

const TRUST_CLASS: Record<string, string> = {
  confirmed: "border-emerald-500/40 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
  provisional: "border-sky-500/35 bg-sky-500/10 text-sky-700 dark:text-sky-300",
  estimated: "border-amber-500/45 bg-amber-500/10 text-amber-700 dark:text-amber-300",
  opportunity: "border-primary/35 bg-primary/10 text-primary",
  blocked: "border-amber-500/45 bg-amber-500/10 text-amber-800 dark:text-amber-200",
  test_only: "border-slate-500/35 bg-slate-500/10 text-slate-700 dark:text-slate-300",
};

const IMPACT_CLASS: Record<string, string> = {
  confirmed_loss: "border-destructive/35 bg-destructive/10 text-destructive",
  probable_loss: "border-warning/45 bg-warning/10 text-warning",
  blocked_cash: "border-amber-500/45 bg-amber-500/10 text-amber-700 dark:text-amber-300",
  lost_sales_risk: "border-warning/45 bg-warning/10 text-warning",
  data_blocker: "border-slate-500/35 bg-slate-500/10 text-slate-700 dark:text-slate-300",
  system_warning: "border-slate-500/35 bg-slate-500/10 text-slate-700 dark:text-slate-300",
  loss: "border-destructive/35 bg-destructive/10 text-destructive",
  risk: "border-warning/45 bg-warning/10 text-warning",
  "blocked cash": "border-amber-500/45 bg-amber-500/10 text-amber-700 dark:text-amber-300",
  opportunity: "border-primary/35 bg-primary/10 text-primary",
  "data blocker": "border-slate-500/35 bg-slate-500/10 text-slate-700 dark:text-slate-300",
};

const RESULT_CLASS: Record<SellerProblemResultStatus, string> = {
  pending_data: "border-sky-500/35 bg-sky-500/10 text-sky-700 dark:text-sky-300",
  improved: "border-emerald-500/40 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
  worse: "border-destructive/35 bg-destructive/10 text-destructive",
  neutral: "border-border bg-muted text-muted-foreground",
  not_enough_data: "border-amber-500/45 bg-amber-500/10 text-amber-800 dark:text-amber-200",
};

export function normalizeProblemText(value: unknown, fallback = ""): string {
  const text = String(value ?? "").trim();
  return text || fallback;
}

function isSellerProblemContract(value: unknown): value is SellerProblemContract {
  return (
    !!value &&
    typeof value === "object" &&
    "why" in value &&
    "nextStep" in value &&
    "impactText" in value
  );
}

function isActionCenterItem(value: unknown): value is ActionCenterItem {
  return (
    !!value &&
    typeof value === "object" &&
    "source_kind" in value &&
    "evidence_state" in value &&
    "money_trust" in value
  );
}

function actionCenterItemFrom(problem: SellerProblemLike): ActionCenterItem {
  return isActionCenterItem(problem)
    ? problem
    : portalActionToActionCenterItem(problem as PortalAction);
}

function contractFromProblem(
  problem: SellerProblemLike | null | undefined,
  options: {
    ledger?: EvidenceLedger | null;
    recheckRule?: string | null;
    result?: SellerProblemContract["result"];
  } = {},
): SellerProblemContract {
  if (!problem) {
    return {
      title: "Проблема товара",
      why: "Платформа нашла проблему по подключённым операционным данным.",
      impactText: "Риск",
      impactAmount: null,
      trustState: "provisional",
      impactType: "probable_loss",
      severity: "medium",
      status: null,
      nextStep: "Откройте рекомендованный сценарий и выполните безопасное действие.",
      canFixHere: false,
      canFixHereText: "Не напрямую. Исправьте исходные данные или дождитесь синхронизации.",
      recheckRule: options.recheckRule ?? "После изменения исходных данных запустите повторную проверку.",
      result: options.result ?? null,
      showResultBlock: Boolean(options.result),
      evidenceLedger: options.ledger ?? null,
      evidenceQuality: "partial",
      allowedActions: [],
      sourceLabel: null,
      moneyTrust: null,
      priceSafety: null,
      needsPriceSafety: false,
    };
  }
  if (isSellerProblemContract(problem)) {
    return {
      ...problem,
      evidenceLedger: options.ledger ?? problem.evidenceLedger ?? null,
      recheckRule: options.recheckRule ?? problem.recheckRule,
      result: options.result ?? problem.result ?? null,
      showResultBlock:
        problem.showResultBlock || Boolean(options.result ?? problem.result),
    };
  }
  return actionCenterItemToSellerProblemContract(actionCenterItemFrom(problem), {
    result: options.result,
  });
}

export function problemCode(problem: SellerProblemLike | null | undefined): string {
  return normalizeProblemText(contractFromProblem(problem).actionCenterSearch?.code).toLowerCase();
}

export function problemSeverity(problem: SellerProblemLike | null | undefined): string {
  const raw = normalizeProblemText(contractFromProblem(problem).severity, "medium").toLowerCase();
  if (raw === "p0") return "critical";
  if (raw === "p1" || raw === "p2") return "high";
  if (raw === "p4") return "low";
  return ["critical", "high", "medium", "low"].includes(raw) ? raw : "medium";
}

export function problemTrust(problem: SellerProblemLike | null | undefined, ledger?: EvidenceLedger | null): string {
  const contract = contractFromProblem(problem, { ledger });
  const raw = normalizeProblemText(contract.trustState, "provisional").toLowerCase();
  return ["confirmed", "provisional", "estimated", "opportunity", "blocked", "test_only"].includes(raw) ? raw : "provisional";
}

export function problemImpactKind(problem: SellerProblemLike | null | undefined, ledger?: EvidenceLedger | null): string {
  const contract = contractFromProblem(problem, { ledger });
  const raw = normalizeProblemText(contract.impactType, "risk").toLowerCase();
  if (["confirmed_loss", "probable_loss", "blocked_cash", "lost_sales_risk", "opportunity", "data_blocker", "system_warning"].includes(raw)) return raw;
  if (raw.includes("confirmed_loss")) return "confirmed_loss";
  if (raw.includes("probable_loss")) return "probable_loss";
  if (raw.includes("lost_sales_risk")) return "lost_sales_risk";
  if (raw.includes("blocked_cash")) return "blocked_cash";
  if (raw.includes("data_blocker") || raw.includes("blocker")) return "data_blocker";
  if (raw.includes("system_warning")) return "system_warning";
  if (raw.includes("loss")) return "probable_loss";
  if (raw.includes("risk") || raw.includes("warning")) return "risk";
  if (raw.includes("opportunity")) return "opportunity";
  return raw.replaceAll("_", " ") || "risk";
}

export function problemEvidence(problem: SellerProblemLike | null | undefined): EvidenceLedger | null {
  return contractFromProblem(problem).evidenceLedger ?? null;
}

export function isTestOnlyProblem(problem: SellerProblemLike | null | undefined): boolean {
  const contract = contractFromProblem(problem);
  return (
    normalizeProblemText(contract.trustState).toLowerCase() === "test_only" ||
    normalizeProblemText(contract.status).toLowerCase() === "test_only" ||
    normalizeProblemText(contract.moneyTrust?.state).toLowerCase() === "test_only"
  );
}

export function allowedActions(problem: SellerProblemLike | null | undefined): string[] {
  return contractFromProblem(problem).allowedActions.map((item) => String(item).trim()).filter(Boolean);
}

export function actionLabel(code: string): string {
  return problemActionLabel(code);
}

export function actionHref(code: string, problem?: SellerProblemLike | null): string | null {
  const contract = contractFromProblem(problem);
  const nmId = contract.actionCenterSearch?.nm_id;
  if (["open_data_fix", "data_fix"].includes(code)) return "/data-fix";
  if (["upload_cost", "review_cost", "map_sku"].includes(code)) return "/costs";
  if (["open_price_review", "review_price", "pricing_review"].includes(code)) return nmId ? `/products/${nmId}` : "/pricing";
  if (["open_promo_planner", "promo_planner", "review_promo", "safe_promo", "reduce_promo", "bundle"].includes(code)) return "/pricing";
  if (["run_checker", "check_card_quality", "review_content"].includes(code)) return nmId ? `/checker/${nmId}` : "/products";
  if (["review_ads", "pause_ads", "lower_ads", "review_bids"].includes(code)) return "/ads";
  if (code === "plan_supply") return "/stock-control";
  return null;
}

export function problemCanFixHere(problem: SellerProblemLike | null | undefined): boolean {
  return contractFromProblem(problem).canFixHere;
}

export function problemAmount(problem: SellerProblemLike | null | undefined): number | null {
  return contractFromProblem(problem).impactAmount ?? null;
}

export function problemTitle(problem: SellerProblemLike | null | undefined): string {
  return contractFromProblem(problem).title;
}

export function problemWhy(problem: SellerProblemLike | null | undefined, ledger?: EvidenceLedger | null): string {
  return contractFromProblem(problem, { ledger }).why;
}

export function problemNextStep(problem: SellerProblemLike | null | undefined): string {
  const contract = contractFromProblem(problem);
  return (
    seededProblemSellerNextStep(problemCode(problem), contract.nextStep, {}) ??
    contract.nextStep
  );
}

export function problemRecheckRule(problem: SellerProblemLike | null | undefined, ledger?: EvidenceLedger | null, fallback?: string | null): string {
  return contractFromProblem(problem, { ledger, recheckRule: fallback }).recheckRule;
}

export function problemContractFrom(
  problem: SellerProblemLike | null | undefined,
  options: {
    ledger?: EvidenceLedger | null;
    recheckRule?: string | null;
    result?: SellerProblemContract["result"];
  } = {},
): SellerProblemContract {
  return contractFromProblem(problem, options);
}

export function ProblemBadgeRow({ problem, ledger, className }: { problem: SellerProblemLike; ledger?: EvidenceLedger | null; className?: string }) {
  const contract = problemContractFrom(problem, { ledger });
  return <ProblemBadgeRowFromContract contract={contract} className={className} />;
}

function ProblemBadgeRowFromContract({ contract, className }: { contract: SellerProblemContract; className?: string }) {
  const severity = contract.severity;
  const trust = contract.trustState;
  const impact = contract.impactType;
  return (
    <div className={cn("flex flex-wrap gap-1.5", className)}>
      <Badge variant="outline" className={cn("text-[10px]", SEVERITY_CLASS[severity])}>{problemSeverityLabel(severity)}</Badge>
      <Badge variant="outline" className={cn("text-[10px]", TRUST_CLASS[trust])}>{problemTrustLabel(trust)}</Badge>
      <Badge variant="outline" className={cn("text-[10px]", IMPACT_CLASS[impact] ?? IMPACT_CLASS.risk)}>{problemImpactLabel(impact)}</Badge>
    </div>
  );
}

function isConfirmedMoney(contract: SellerProblemContract): boolean {
  return contract.impactType === "confirmed_loss" && contract.trustState === "confirmed";
}

function ImpactValue({ contract }: { contract: SellerProblemContract }) {
  if (contract.impactAmount == null) return <>{contract.impactText}</>;
  const confirmed = isConfirmedMoney(contract);
  return (
    <div className="space-y-1">
      <div>{problemImpactLabel(contract.impactType)}</div>
      <div
        className={cn(
          "inline-flex rounded-md border px-2 py-1 text-sm font-semibold tabular-nums",
          confirmed
            ? "border-destructive/35 bg-destructive/10 text-destructive"
            : "border-dashed border-amber-500/45 bg-amber-500/10 text-amber-800 dark:text-amber-200",
        )}
      >
        {formatMoney(contract.impactAmount)}
      </div>
      {!confirmed ? (
        <div className="text-[11px] text-muted-foreground">
          Оценка, возможность или блокер. Это не измеренный результат после действия.
        </div>
      ) : null}
    </div>
  );
}

export function ImpactAmount({ problem, ledger, className }: { problem: SellerProblemLike; ledger?: EvidenceLedger | null; className?: string }) {
  const contract = problemContractFrom(problem, { ledger });
  if (contract.impactAmount == null) return null;
  const confirmed = isConfirmedMoney(contract);
  return (
    <div className={cn(
      "rounded-md border px-3 py-2 text-sm",
      confirmed ? "border-destructive/35 bg-destructive/10" : "border-dashed border-amber-500/45 bg-amber-500/10",
      className,
    )}>
      <div className="text-[10px] font-medium uppercase text-muted-foreground">
        {confirmed ? "Подтверждённое влияние на деньги" : "Оценка или предварительный риск"}
      </div>
      <div className={cn("mt-0.5 font-semibold", confirmed ? "text-destructive" : "text-amber-700 dark:text-amber-300")}>
        {formatMoney(contract.impactAmount)}
      </div>
    </div>
  );
}

function ResultValue({ contract }: { contract: SellerProblemContract }) {
  const result = contract.result ?? { status: "pending_data" as const, detail: null };
  return (
    <div className="space-y-1">
      <Badge variant="outline" className={cn("text-[10px]", RESULT_CLASS[result.status])}>
        {problemResultStatusLabel(result.status)}
      </Badge>
      {result.amount != null ? (
        <div className="font-semibold tabular-nums">{formatMoney(result.amount)}</div>
      ) : null}
      <div className="text-sm leading-snug">{result.detail || "Ждём данные после действия и повторной проверки."}</div>
    </div>
  );
}

function ProblemBlock({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="rounded-md border bg-background/70 p-3">
      <div className="text-[10px] font-medium uppercase text-muted-foreground">{label}</div>
      <div className="mt-1 text-sm leading-snug">{children}</div>
    </div>
  );
}

export function problemContractBlocks(contract: SellerProblemContract, includeResult = true): Array<{ label: string; value: ReactNode }> {
  const blocks: Array<{ label: string; value: ReactNode }> = [
    { label: PROBLEM_ANSWER_LABELS.whatHappened, value: contract.title },
    { label: PROBLEM_ANSWER_LABELS.why, value: contract.why },
    { label: PROBLEM_ANSWER_LABELS.impact, value: <ImpactValue contract={contract} /> },
    { label: PROBLEM_ANSWER_LABELS.trust, value: problemTrustLabel(contract.trustState) },
    { label: PROBLEM_ANSWER_LABELS.nextStep, value: contract.nextStep },
    { label: PROBLEM_ANSWER_LABELS.canFixHere, value: contract.canFixHereText },
    { label: PROBLEM_ANSWER_LABELS.recheck, value: contract.recheckRule },
  ];
  if (includeResult && contract.showResultBlock) {
    blocks.push({ label: PROBLEM_ANSWER_LABELS.result, value: <ResultValue contract={contract} /> });
  }
  return blocks;
}

export function SellerProblemLifecycle({
  problem,
  contract: providedContract,
  ledger,
  recheckRule,
  result,
  onEvidence,
  className,
  showHeader = true,
  showEvidenceButton = true,
  includeResult = true,
}: {
  problem?: SellerProblemLike | null;
  contract?: SellerProblemContract;
  ledger?: EvidenceLedger | null;
  recheckRule?: string | null;
  result?: SellerProblemContract["result"];
  onEvidence?: (title: string, ledger: EvidenceLedger | null) => void;
  className?: string;
  showHeader?: boolean;
  showEvidenceButton?: boolean;
  includeResult?: boolean;
}) {
  const contract = providedContract ?? problemContractFrom(problem, { ledger, recheckRule, result });
  return (
    <div className={cn("space-y-3", className)} data-problem-ux-contract="1">
      {showHeader ? (
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div className="min-w-0 flex-1">
            <div className="text-sm font-semibold leading-snug">{contract.title}</div>
            <div className="mt-1 flex flex-wrap items-center gap-1.5">
              <ProblemBadgeRowFromContract contract={contract} />
              {contract.status ? (
                <Badge variant="outline" className="text-[10px]">
                  {problemStatusLabel(contract.status)}
                </Badge>
              ) : null}
              <Badge
                variant="outline"
                className={cn(
                  "text-[10px]",
                  contract.evidenceQuality === "full"
                    ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300"
                    : "border-dashed border-amber-500/45 bg-amber-500/10 text-amber-800 dark:text-amber-200",
                )}
              >
                {contract.evidenceQuality === "full" ? "Полные доказательства" : "Частичные доказательства"}
              </Badge>
            </div>
          </div>
          {showEvidenceButton ? (
            <EvidenceButton
              ledger={contract.evidenceLedger}
              allowEmpty
              className="max-w-[180px]"
              onClick={() => onEvidence?.(contract.title, contract.evidenceLedger ?? null)}
            />
          ) : null}
        </div>
      ) : null}
      <div className="grid gap-2 md:grid-cols-2 xl:grid-cols-3">
        {problemContractBlocks(contract, includeResult).map((item) => (
          <ProblemBlock key={item.label} label={item.label}>{item.value}</ProblemBlock>
        ))}
      </div>
    </div>
  );
}

export function ProblemAnswerGrid({
  problem,
  ledger,
  recheckRule,
  includeResult = false,
  className,
}: {
  problem: SellerProblemLike;
  ledger?: EvidenceLedger | null;
  recheckRule?: string | null;
  includeResult?: boolean;
  className?: string;
}) {
  const contract = problemContractFrom(problem, { ledger, recheckRule });
  return (
    <div className={cn("grid gap-2 md:grid-cols-2 xl:grid-cols-3", className)}>
      {problemContractBlocks(contract, includeResult).map((item) => (
        <ProblemBlock key={item.label} label={item.label}>{item.value}</ProblemBlock>
      ))}
    </div>
  );
}

export function ProblemActionButtons({
  problem,
  onRecheck,
  onDismiss,
  onAssign,
  className,
}: {
  problem: SellerProblemLike;
  onRecheck?: () => void;
  onDismiss?: () => void;
  onAssign?: () => void;
  className?: string;
}) {
  const actions = allowedActions(problem);
  if (!actions.length) return null;
  return (
    <div className={cn("flex flex-wrap gap-1.5", className)}>
      {actions.map((code) => {
        const href = actionHref(code, problem);
        const label = actionLabel(code);
        const iconClass = "mr-1 h-3.5 w-3.5";
        const icon = code === "upload_cost" ? <Upload className={iconClass} />
          : code === "map_sku" ? <Tag className={iconClass} />
            : code === "assign" ? <UserPlus className={iconClass} />
              : code === "create_task" ? <ClipboardList className={iconClass} />
                : code === "dismiss" ? <X className={iconClass} />
                  : code === "recheck" ? <RefreshCw className={iconClass} />
                    : <Wrench className={iconClass} />;
        if (href) {
          return (
            <Button asChild key={code} size="sm" variant="outline" className="h-7 text-xs">
              <Link to={href}>{icon}{label}</Link>
            </Button>
          );
        }
        if (code === "recheck" && onRecheck) {
          return <Button key={code} size="sm" variant="outline" className="h-7 text-xs" onClick={onRecheck}>{icon}{label}</Button>;
        }
        if (code === "dismiss" && onDismiss) {
          return <Button key={code} size="sm" variant="outline" className="h-7 text-xs" onClick={onDismiss}>{icon}{label}</Button>;
        }
        if (code === "assign" && onAssign) {
          return <Button key={code} size="sm" variant="outline" className="h-7 text-xs" onClick={onAssign}>{icon}{label}</Button>;
        }
        return <Badge key={code} variant="outline" className="h-7 rounded-md px-2 py-1 text-[10px]">{label}</Badge>;
      })}
    </div>
  );
}

export function SellerProblemCard({
  problem,
  onEvidence,
  className,
  showActions = true,
  showActionCenterLink = true,
  actionCenterLabel = "Открыть задачу",
  result,
}: {
  problem: SellerProblemLike;
  onEvidence?: (title: string, ledger: EvidenceLedger | null) => void;
  className?: string;
  showActions?: boolean;
  showActionCenterLink?: boolean;
  actionCenterLabel?: string;
  result?: SellerProblemContract["result"];
}) {
  const ledger = problemEvidence(problem);
  const contract = problemContractFrom(problem, { ledger, result });
  const priceSafety = contract.priceSafety;
  const needsPriceSafety = contract.needsPriceSafety === true;
  const resolved = ["done", "resolved", "dismissed", "ignored", "closed"].includes(normalizeProblemText(contract.status).toLowerCase());
  const actionCenterSearch =
    contract.actionCenterSearch ?? product360ProblemToActionCenterLink(contract);

  return (
    <article className={cn("rounded-md border bg-background p-3", resolved && "bg-muted/20 opacity-80", className)}>
      <div className="space-y-3">
        <SellerProblemLifecycle
          contract={contract}
          onEvidence={onEvidence}
        />
        {priceSafety ? (
          <PriceSafetyPanel priceSafety={priceSafety} compact />
        ) : needsPriceSafety ? (
          <PriceSafetyMissingNotice compact />
        ) : null}
        {showActions ? <ProblemActionButtons problem={problem} /> : null}
        {showActionCenterLink ? (
          <Button asChild size="sm" variant="ghost" className="h-7 text-xs">
            <Link
              to="/action-center"
              search={actionCenterSearch}
            >
              {actionCenterLabel} <ArrowRight className="ml-1 h-3.5 w-3.5" />
            </Link>
          </Button>
        ) : null}
      </div>
    </article>
  );
}

export function ProblemEmptyState({
  kind,
  message,
  beta,
  className,
}: {
  kind?: "sync_required" | "no_data" | "no_issues" | "data_missing" | "missing_data" | "module_disabled" | "beta_module" | string | null;
  message?: string | null;
  beta?: boolean;
  className?: string;
}) {
  const normalized = beta ? "beta_module" : normalizeProblemText(kind, "no_issues");
  const copy: Record<string, { title: string; body: string; icon: ReactNode }> = {
    sync_required: { ...PROBLEM_EMPTY_STATE_COPY.sync_required, icon: <RefreshCw className="h-4 w-4" /> },
    no_data: { ...PROBLEM_EMPTY_STATE_COPY.no_data, icon: <Database className="h-4 w-4" /> },
    no_issues: { ...PROBLEM_EMPTY_STATE_COPY.no_issues, icon: <CheckCircle2 className="h-4 w-4" /> },
    data_missing: { ...PROBLEM_EMPTY_STATE_COPY.data_missing, icon: <FileQuestion className="h-4 w-4" /> },
    missing_data: { ...PROBLEM_EMPTY_STATE_COPY.missing_data, icon: <FileQuestion className="h-4 w-4" /> },
    module_disabled: { ...PROBLEM_EMPTY_STATE_COPY.module_disabled, icon: <AlertTriangle className="h-4 w-4" /> },
    beta_module: { ...PROBLEM_EMPTY_STATE_COPY.beta_module, icon: <AlertTriangle className="h-4 w-4" /> },
  };
  const item = copy[normalized] ?? copy.no_issues;
  return (
    <div className={cn("rounded-md border border-dashed bg-muted/20 p-4 text-sm", className)}>
      <div className="flex items-center gap-2 font-medium">{item.icon}{item.title}</div>
      <div className="mt-1 text-xs text-muted-foreground">{message || item.body}</div>
    </div>
  );
}
