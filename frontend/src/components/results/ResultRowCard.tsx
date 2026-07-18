// @ts-nocheck
import { Link } from "@tanstack/react-router";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Clock, ExternalLink } from "lucide-react";
import {
  ResultBadge,
  TrustBadge,
  ImpactBadge,
} from "@/components/badges/StatusBadges";
import { formatMoney } from "@/lib/format";
import {
  humanizeEventType,
  humanizeMessage,
  humanizeModule,
} from "@/lib/results-i18n";
import { evidenceFrom } from "@/lib/evidence";
import { EvidenceButton } from "@/components/shell/EvidenceButton";
import {
  classifyOutcome,
  classifyTrust,
  isMeasuredEffect,
  measuredAmount,
} from "./resultsClassify";
import {
  buildContextLinks,
  formatConfidenceValue,
  hasEvidence,
} from "@/lib/results-metric-templates";

function isRecord(v: unknown): v is Record<string, unknown> {
  return !!v && typeof v === "object" && !Array.isArray(v);
}

function pick<T = unknown>(obj: unknown, keys: string[]): T | undefined {
  if (!isRecord(obj)) return undefined;
  for (const k of keys) {
    const v = obj[k];
    if (v != null && v !== "") return v as T;
  }
  return undefined;
}

function fmtDate(s?: string | null): string | null {
  if (!s) return null;
  const d = new Date(s);
  if (Number.isNaN(d.getTime())) return String(s);
  return d.toLocaleString("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function ResultRowCard({
  event,
  onOpen,
  onEvidence,
}: {
  event: unknown;
  onOpen: () => void;
  onEvidence?: () => void;
}) {
  const r = isRecord(event) ? event : {};
  const moduleKey = pick<string>(r, ["source_module", "module", "source"]);
  const eventType = pick<string>(r, ["event_type", "type", "event"]);
  const problemCode = pick<string>(r, ["problem_code"]);
  const impact = pick<string>(r, ["impact_type"]);
  const createdAt = pick<string>(r, [
    "created_at",
    "at",
    "occurred_at",
    "timestamp",
  ]);
  const lastRecheck = pick<string>(r, [
    "last_recheck_at",
    "recheck_at",
    "rechecked_at",
  ]);
  const productIdentity =
    pick<Record<string, unknown>>(r, ["product_identity"]) ?? {};
  const productTitle =
    pick<string>(productIdentity, ["title", "name"]) ??
    pick<string>(r, ["product_title", "nm_name"]);
  const nmId =
    pick<number | string>(productIdentity, ["nm_id"]) ??
    pick<number | string>(r, ["nm_id"]);
  const vendorCode = pick<string>(productIdentity, ["vendor_code", "article"]);

  const outcome = classifyOutcome(r);
  const trust = classifyTrust(r);
  const measured = isMeasuredEffect(r);
  const amount = measuredAmount(r);
  const before = isRecord(r.before_snapshot) && Object.keys(r.before_snapshot).length > 0;
  const after = isRecord(r.after_snapshot) && Object.keys(r.after_snapshot).length > 0;

  const humanEvent = humanizeEventType(eventType);
  const payload = isRecord(r.payload) ? r.payload : {};
  const ledger = evidenceFrom(r.evidence_ledger, payload.evidence_ledger);
  const hasProof = hasEvidence(r) || !!ledger;
  const confidenceStr = formatConfidenceValue(r);
  const links = buildContextLinks(r);

  const title = productTitle ?? humanEvent.label ?? "Событие";

  return (
    <Card className="cursor-pointer hover:border-primary/40 transition-colors">
      <CardContent className="p-3 space-y-2">
        <div
          role="button"
          tabIndex={0}
          onClick={onOpen}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") {
              e.preventDefault();
              onOpen();
            }
          }}
          className="space-y-2 focus-visible:outline-none"
        >
          {/* Primary line */}
          <div className="flex items-start justify-between gap-2 flex-wrap">
            <div className="min-w-0 flex-1 space-y-1">
              <div className="flex flex-wrap items-center gap-1.5">
                <ResultBadge value={outcome} />
                <TrustBadge
                  value={
                    trust === "confirmed"
                      ? "confirmed"
                      : trust === "estimated"
                        ? "estimated"
                        : "provisional"
                  }
                />
                {impact ? <ImpactBadge value={impact} /> : null}
              </div>
              <div className="text-sm font-medium truncate" title={humanEvent.raw ?? undefined}>
                {title}
              </div>
              <div className="text-xs text-muted-foreground flex flex-wrap items-center gap-x-2 gap-y-0.5">
                <span>{humanizeModule(moduleKey)}</span>
                {problemCode ? <span>· {problemCode}</span> : null}
                {nmId ? <span>· nmID {nmId}</span> : null}
                {vendorCode ? <span>· Артикул {vendorCode}</span> : null}
              </div>
            </div>
            <div className="text-right shrink-0 space-y-1">
              {measured && amount != null ? (
                <div className="rounded-md border border-primary/30 bg-primary/10 px-2 py-1 text-xs font-semibold tabular-nums text-primary">
                  <div className="text-[9px] uppercase font-medium">
                    Измеренный эффект
                  </div>
                  {amount >= 0 ? "+" : ""}
                  {formatMoney(amount)}
                </div>
              ) : (
                <Badge variant="outline" className="text-[10px]">
                  Ожидаемый эффект
                </Badge>
              )}
              {createdAt ? (
                <div className="text-[11px] text-muted-foreground flex items-center gap-1 justify-end">
                  <Clock className="h-3 w-3" /> {fmtDate(createdAt)}
                </div>
              ) : null}
            </div>
          </div>

          {/* Secondary line */}
          <div className="flex flex-wrap items-center gap-1.5 text-[11px] text-muted-foreground">
            <Badge variant="outline" className="text-[10px]">
              До: {before ? "есть" : "нет"}
            </Badge>
            <Badge variant="outline" className="text-[10px]">
              После: {after ? "есть" : "ждём"}
            </Badge>
            <Badge variant="outline" className="text-[10px]">
              Уверенность: {confidenceStr}
            </Badge>
            {lastRecheck ? (
              <span>Перепроверка: {fmtDate(lastRecheck)}</span>
            ) : null}
            {r.message ? (
              <span className="truncate max-w-[280px]">
                {humanizeMessage(r.message)}
              </span>
            ) : null}
          </div>
        </div>

        {/* Action row (not part of click zone) */}
        <div
          className="flex flex-wrap items-center gap-1.5 border-t pt-2"
          onClick={(e) => e.stopPropagation()}
        >
          <EvidenceButton
            onClick={() => onEvidence?.()}
            disabled={!hasProof}
            missing={!hasProof}
            label={hasProof ? "Как посчитано?" : "Как посчитано? (доказательств пока нет)"}
          />
          {links.map((lnk) => {
            if (lnk.disabled) {
              return (
                <Button
                  key={lnk.key}
                  size="sm"
                  variant="outline"
                  className="h-7 text-[11px]"
                  disabled
                  title={lnk.disabledReason}
                >
                  {lnk.label}
                </Button>
              );
            }
            return (
              <Button
                key={lnk.key}
                asChild
                size="sm"
                variant="outline"
                className="h-7 text-[11px]"
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
            );
          })}
          <Button
            size="sm"
            variant="ghost"
            className="h-7 text-[11px] ml-auto"
            onClick={onOpen}
          >
            Подробнее
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
