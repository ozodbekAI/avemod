// @ts-nocheck
import { Link } from "@tanstack/react-router";
import { useState } from "react";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { ExternalLink, Info } from "lucide-react";
import {
  ResultBadge,
  TrustBadge,
  ImpactBadge,
  StatusBadge,
} from "@/components/badges/StatusBadges";
import { EvidenceButton } from "@/components/shell/EvidenceButton";
import { EvidenceDrawer } from "@/components/EvidenceDrawer";
import { formatMoney } from "@/lib/format";
import {
  humanizeEventType,
  humanizeMessage,
  humanizeModule,
  translateTerm,
} from "@/lib/results-i18n";
import {
  PROBLEM_RESULT_CORRELATION_DISCLAIMER,
} from "@/lib/problem-results";
import { evidenceFrom } from "@/lib/evidence";
import { ResultTimeline } from "./ResultTimeline";
import { ResultMetricComparison } from "./ResultMetricComparison";
import {
  classifyOutcome,
  classifyTrust,
  isMeasuredEffect,
  measuredAmount,
  needsRecheck,
} from "./resultsClassify";
import {
  buildContextLinks,
  buildMetricRows,
  formatConfidenceValue,
  resolveMetricTemplate,
} from "@/lib/results-metric-templates";

function isRecord(v: unknown): v is Record<string, unknown> {
  return !!v && typeof v === "object" && !Array.isArray(v);
}

function fmtDate(s?: string | null): string | null {
  if (!s) return null;
  const d = new Date(s);
  if (Number.isNaN(d.getTime())) return String(s);
  return d.toLocaleString("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function pick<T = unknown>(obj: unknown, keys: string[]): T | undefined {
  if (!isRecord(obj)) return undefined;
  for (const k of keys) {
    const v = obj[k];
    if (v != null && v !== "") return v as T;
  }
  return undefined;
}

function fmtMetric(v: unknown): string {
  if (v == null || v === "") return "—";
  const n = Number(v);
  if (!Number.isFinite(n)) return translateTerm(String(v));
  return n.toLocaleString("ru-RU", { maximumFractionDigits: 2 });
}

function SnapshotBlock({
  title,
  snapshot,
  emptyHint,
}: {
  title: string;
  snapshot: unknown;
  emptyHint: string;
}) {
  const record = isRecord(snapshot) ? snapshot : {};
  const entries = Object.entries(record).filter(
    ([, v]) =>
      typeof v === "string" || typeof v === "number" || typeof v === "boolean",
  );
  return (
    <div className="rounded-md border bg-muted/20 p-3 space-y-2">
      <div className="text-[10px] uppercase tracking-wide text-muted-foreground">
        {title}
      </div>
      {entries.length === 0 ? (
        <div className="text-xs text-muted-foreground">{emptyHint}</div>
      ) : (
        <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-xs">
          {entries.slice(0, 12).map(([k, v]) => (
            <div key={k} className="flex justify-between gap-2">
              <span className="text-muted-foreground truncate">
                {translateTerm(k)}
              </span>
              <span className="font-medium tabular-nums">{fmtMetric(v)}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export function ResultDetailDrawer({
  open,
  onOpenChange,
  event,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  event: unknown;
}) {
  const [evidenceOpen, setEvidenceOpen] = useState(false);
  const r = isRecord(event) ? event : {};

  const outcome = classifyOutcome(r);
  const trust = classifyTrust(r);
  const measured = isMeasuredEffect(r);
  const amount = measuredAmount(r);

  const productIdentity = pick<Record<string, unknown>>(r, [
    "product_identity",
  ]) ?? {};
  const productTitle =
    pick<string>(productIdentity, ["title", "name"]) ??
    pick<string>(r, ["product_title", "nm_name"]);
  const nmId =
    pick<number | string>(productIdentity, ["nm_id"]) ??
    pick<number | string>(r, ["nm_id"]);
  const vendorCode = pick<string>(productIdentity, ["vendor_code", "article"]);

  const moduleKey = pick<string>(r, ["source_module", "module", "source"]);
  const eventType = pick<string>(r, ["event_type", "type", "event"]);
  const problemInstanceId = pick<string | number>(r, [
    "problem_instance_id",
  ]);
  const problemCode = pick<string>(r, ["problem_code"]);
  const actionId = pick<string | number>(r, ["action_id"]);
  const status = pick<string>(r, ["status", "result_status"]);
  const impact = pick<string>(r, ["impact_type"]);
  const createdAt = pick<string>(r, [
    "created_at",
    "at",
    "occurred_at",
    "timestamp",
  ]);
  const createdBy = pick<string>(r, ["created_by", "user_name", "actor"]);
  const message = pick<string>(r, [
    "message",
    "summary",
    "description",
    "note",
  ]);
  const before = pick<unknown>(r, ["before_snapshot"]);
  const after = pick<unknown>(r, ["after_snapshot"]);
  const payload = isRecord(r.payload) ? r.payload : {};
  const comparison =
    pick<unknown>(r, ["comparison"]) ??
    pick<unknown>(payload, ["comparison"]);

  const ledger = evidenceFrom(r.evidence_ledger, payload.evidence_ledger);

  const hasBefore =
    isRecord(before) && Object.keys(before).length > 0;
  const hasAfter = isRecord(after) && Object.keys(after).length > 0;
  const hasComparison =
    isRecord(comparison) && Object.keys(comparison).length > 0;
  const hasAction = eventType && String(eventType).includes("action");
  const hasRecheck = String(eventType ?? "").toLowerCase().includes("recheck");

  const humanEvent = humanizeEventType(eventType);
  const title =
    productTitle ??
    humanEvent.label ??
    "Результат";

  const meaningCopy: Record<string, string> = {
    improved: "Есть улучшение по данным после действия.",
    worse: "После действия ситуация ухудшилась.",
    neutral: "Существенных изменений не зафиксировано.",
    pending_data: "Задача выполнена, но свежих данных пока нет.",
    not_enough_data: "Данных недостаточно, чтобы сравнить до/после.",
  };

  return (
    <>
      <Sheet open={open} onOpenChange={onOpenChange}>
        <SheetContent
          side="right"
          data-testid="result-detail-drawer"
          className="inset-0 h-[100dvh] w-screen max-w-none overflow-y-auto border-l-0 p-4 sm:inset-y-0 sm:left-auto sm:right-0 sm:h-full sm:w-full sm:max-w-2xl sm:border-l sm:p-6"
        >
          <SheetHeader className="pr-8">
            <SheetTitle className="text-base">{title}</SheetTitle>
            <SheetDescription>
              Проблема · доказательства · действие · перепроверка · результат.
            </SheetDescription>
          </SheetHeader>

          <div className="mt-4 space-y-4">
            {/* A. Какая проблема была? */}
            <section className="space-y-2">
              <div className="text-[10px] uppercase tracking-wide text-muted-foreground">
                Какая проблема была?
              </div>
              <div className="flex flex-wrap gap-1.5">
                <Badge variant="outline" className="text-[10px]">
                  {humanizeModule(moduleKey)}
                </Badge>
                {problemCode ? (
                  <Badge variant="outline" className="text-[10px]">
                    Код: {problemCode}
                  </Badge>
                ) : null}
                {problemInstanceId ? (
                  <Badge variant="outline" className="text-[10px]">
                    ID проблемы: {String(problemInstanceId)}
                  </Badge>
                ) : null}
                <ResultBadge value={outcome} />
                <TrustBadge value={trust === "confirmed" ? "confirmed" : trust === "estimated" ? "estimated" : "provisional"} />
                {impact ? <ImpactBadge value={impact} /> : null}
                {status ? <StatusBadge value={status} /> : null}
                <Badge variant="outline" className="text-[10px]">
                  Уверенность: {formatConfidenceValue(r)}
                </Badge>
              </div>
              {productTitle || nmId || vendorCode ? (
                <div className="text-xs text-muted-foreground">
                  {productTitle ? <span>{productTitle}</span> : null}
                  {vendorCode ? <span> · Артикул {vendorCode}</span> : null}
                  {nmId ? <span> · nmID {nmId}</span> : null}
                </div>
              ) : null}
            </section>

            {/* B. Что сделали? */}
            <section className="space-y-2 border-t pt-3">
              <div className="text-[10px] uppercase tracking-wide text-muted-foreground">
                Что сделали?
              </div>
              <div className="text-sm">
                {humanEvent.label}
                {createdBy ? (
                  <span className="text-muted-foreground"> · {createdBy}</span>
                ) : null}
              </div>
              {createdAt ? (
                <div className="text-xs text-muted-foreground">
                  {fmtDate(createdAt)}
                </div>
              ) : null}
              {message ? (
                <div className="text-xs text-muted-foreground">
                  {humanizeMessage(message)}
                </div>
              ) : null}
              {actionId ? (
                <Button
                  asChild
                  size="sm"
                  variant="outline"
                  className="h-7 text-xs"
                >
                  <Link
                    to="/action-center"
                    search={{
                      action_id: String(actionId),
                      problem_instance_id: problemInstanceId
                        ? String(problemInstanceId)
                        : undefined,
                    }}
                  >
                    Открыть задачу
                    <ExternalLink className="h-3 w-3 ml-1" />
                  </Link>
                </Button>
              ) : null}
            </section>

            {/* C/E. До / После — problem-specific curated metrics if available */}
            {(() => {
              const template = resolveMetricTemplate(problemCode, moduleKey);
              if (template) {
                const rows = buildMetricRows(template, before, after);
                return (
                  <section className="space-y-2 border-t pt-3">
                    <div className="text-[10px] uppercase tracking-wide text-muted-foreground">
                      До / После действия
                    </div>
                    <ResultMetricComparison rows={rows} />
                    {!hasBefore || !hasAfter ? (
                      <div className="text-[11px] text-muted-foreground">
                        {!hasBefore && !hasAfter
                          ? "Недостаточно данных для сравнения."
                          : !hasAfter
                            ? "Ждём данных после действия."
                            : "Снимок «до действия» ещё не сохранён."}
                      </div>
                    ) : null}
                  </section>
                );
              }
              return (
                <section className="grid gap-2 sm:grid-cols-2 border-t pt-3">
                  <SnapshotBlock
                    title="До действия"
                    snapshot={before}
                    emptyHint="Снимок до действия ещё не сохранён."
                  />
                  <SnapshotBlock
                    title="После действия"
                    snapshot={after}
                    emptyHint={
                      hasBefore
                        ? "Ждём данных после действия."
                        : "Нет данных для сравнения."
                    }
                  />
                </section>
              );
            })()}

            {/* D. Повторная проверка */}
            <section className="space-y-2 border-t pt-3">
              <div className="text-[10px] uppercase tracking-wide text-muted-foreground">
                Повторная проверка
              </div>
              <div className="text-xs text-muted-foreground">
                {hasRecheck
                  ? `Событие перепроверки${createdAt ? ` · ${fmtDate(createdAt)}` : ""}.`
                  : outcome === "pending_data"
                    ? "Перепроверка ещё не запускалась или ждём данных."
                    : "Проверка выполнена по данным после действия."}
              </div>
            </section>

            {/* F. Сравнение — timeline */}
            <section className="space-y-2 border-t pt-3">
              <div className="text-[10px] uppercase tracking-wide text-muted-foreground">
                Сравнение
              </div>
              <ResultTimeline
                before={hasBefore}
                action={!!hasAction || !!createdAt}
                recheck={hasRecheck}
                after={hasAfter}
                comparison={hasComparison || measured}
              />
            </section>

            {/* G. Что это значит? */}
            <section className="space-y-2 border-t pt-3">
              <div className="text-[10px] uppercase tracking-wide text-muted-foreground">
                Что это значит?
              </div>
              <div className="text-sm">{meaningCopy[outcome]}</div>
              {measured && amount != null ? (
                <div className="text-sm font-medium">
                  Измеренный эффект: {amount >= 0 ? "+" : ""}
                  {formatMoney(amount)}
                </div>
              ) : null}
              {!measured ? (
                <div className="text-xs text-muted-foreground">
                  Это ожидаемый эффект, а не измеренная экономия.
                </div>
              ) : null}
            </section>

            {/* H. Корреляция */}
            <section className="border-t pt-3">
              <Alert>
                <Info className="h-4 w-4" />
                <AlertTitle className="text-xs">
                  Корреляция, не гарантия
                </AlertTitle>
                <AlertDescription className="text-xs">
                  {PROBLEM_RESULT_CORRELATION_DISCLAIMER}
                </AlertDescription>
              </Alert>
            </section>

            {/* I. Доказательства + Ссылки контекста */}
            <section className="space-y-2 border-t pt-3">
              <div className="text-[10px] uppercase tracking-wide text-muted-foreground">
                Доказательства и переходы
              </div>
              <div className="flex flex-wrap gap-2">
                <EvidenceButton
                  onClick={() => setEvidenceOpen(true)}
                  disabled={!ledger}
                  missing={!ledger}
                  label={ledger ? "Как посчитано?" : "Как посчитано? (доказательств пока нет)"}
                />
                {buildContextLinks(r).map((lnk) =>
                  lnk.disabled ? (
                    <Button
                      key={lnk.key}
                      size="sm"
                      variant="outline"
                      className="h-7 text-xs"
                      disabled
                      title={lnk.disabledReason}
                    >
                      {lnk.label}
                    </Button>
                  ) : (
                    <Button
                      key={lnk.key}
                      asChild
                      size="sm"
                      variant="outline"
                      className="h-7 text-xs"
                    >
                      <Link
                        to={lnk.to as any}
                        params={lnk.params as any}
                        search={lnk.search as any}
                      >
                        {lnk.label}
                        <ExternalLink className="h-3 w-3 ml-1" />
                      </Link>
                    </Button>
                  ),
                )}
              </div>
            </section>
          </div>
        </SheetContent>
      </Sheet>

      {ledger ? (
        <EvidenceDrawer
          open={evidenceOpen}
          onOpenChange={setEvidenceOpen}
          ledger={ledger}
        />
      ) : null}
    </>
  );
}
