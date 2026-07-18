import { AlertTriangle } from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { formatNumber } from "@/lib/format";
import type {
  EvidenceDateRange,
  EvidenceInputFact,
  EvidenceLedger,
  EvidenceSourceReference,
} from "@/lib/evidence";
import type {
  ActionCenterDataFreshness,
  ActionCenterEvidenceState,
} from "@/lib/action-center-contract";
import {
  actionCenterSourceFreshnessLabel,
  dataFreshnessBlockingLabel,
  dataFreshnessBlocksAction,
  dataFreshnessStatusLabel,
} from "@/lib/action-center-contract";
import { firstText, renderValue } from "@/lib/action-center-utils";

export const EVIDENCE_STATE_CLASS: Record<ActionCenterEvidenceState, string> = {
  full_evidence: "border-success/35 bg-success/10 text-success",
  partial_evidence:
    "border-amber-500/45 bg-amber-500/10 text-amber-700 dark:text-amber-300",
  missing_evidence: "border-destructive/35 bg-destructive/10 text-destructive",
  read_only_signal:
    "border-muted-foreground/30 bg-muted/30 text-muted-foreground",
};

export function evidenceStateLabel(state: ActionCenterEvidenceState): string {
  const labels: Record<ActionCenterEvidenceState, string> = {
    full_evidence: "Есть доказательства",
    partial_evidence: "Доказательств недостаточно",
    missing_evidence: "Доказательств недостаточно",
    read_only_signal: "Только сигнал",
  };
  return labels[state];
}

export function evidenceDateRangeLabel(
  range?: EvidenceDateRange | null,
): string {
  if (!range) return "—";
  const from = firstText(range.from, range.start, range.date_from);
  const to = firstText(range.to, range.end, range.date_to);
  if (from && to) return `${from} — ${to}`;
  return from ?? to ?? "—";
}

export function evidenceSourceLabel(
  item?: EvidenceInputFact | EvidenceSourceReference | null,
): string {
  if (!item) return "—";
  return (
    firstText(
      (item as EvidenceInputFact).source,
      item.source_table,
      (item as EvidenceSourceReference).table,
      item.source_endpoint,
      (item as EvidenceSourceReference).wb_endpoint,
    ) ?? "—"
  );
}

export function evidenceRowCount(
  ledger: EvidenceLedger | null,
  firstFact?: EvidenceInputFact,
  firstRef?: EvidenceSourceReference,
): string {
  const count = firstRef?.row_count ?? firstFact?.row_count;
  if (typeof count === "number" && Number.isFinite(count)) {
    return formatNumber(count);
  }
  const sampleRows = firstFact?.sample_rows;
  if (Array.isArray(sampleRows) && sampleRows.length > 0) {
    return formatNumber(sampleRows.length);
  }
  const ledgerRows = ledger?.sample_rows;
  if (Array.isArray(ledgerRows) && ledgerRows.length > 0) {
    return formatNumber(ledgerRows.length);
  }
  return "—";
}

export function compactEvidenceList(values?: unknown[] | null): string {
  if (!Array.isArray(values) || !values.length) return "—";
  return values
    .map((item) => firstText(item))
    .filter(Boolean)
    .slice(0, 4)
    .join("; ");
}

export function EvidenceStateBadge({
  state,
}: {
  state: ActionCenterEvidenceState;
}) {
  return (
    <Badge
      variant="outline"
      className={`text-[10px] ${EVIDENCE_STATE_CLASS[state]}`}
    >
      {evidenceStateLabel(state)}
    </Badge>
  );
}

export function DataFreshnessBadge({
  freshness,
}: {
  freshness: ActionCenterDataFreshness | null | undefined;
}) {
  if (!dataFreshnessBlocksAction(freshness)) return null;
  return (
    <Badge
      variant="outline"
      className="text-[10px] border-amber-500/45 bg-amber-500/10 text-amber-800 dark:text-amber-300"
    >
      {dataFreshnessStatusLabel(freshness)}
    </Badge>
  );
}

export function InfoBlock({
  label,
  value,
  wide = false,
}: {
  label: string;
  value: unknown;
  wide?: boolean;
}) {
  return (
    <div className={wide ? "md:col-span-2" : ""}>
      <div className="text-[10px] font-medium uppercase text-muted-foreground">
        {label}
      </div>
      <div className="mt-1 break-words text-sm">{renderValue(value)}</div>
    </div>
  );
}

export function EvidenceInlineSummary({
  ledger,
  state,
  trustLabel,
  freshness,
}: {
  ledger: EvidenceLedger | null;
  state: ActionCenterEvidenceState;
  trustLabel: string;
  freshness?: ActionCenterDataFreshness | null;
}) {
  const facts = Array.isArray(ledger?.input_facts) ? ledger.input_facts : [];
  const refs = Array.isArray(ledger?.source_references)
    ? ledger.source_references
    : [];
  const firstFact = facts[0];
  const firstRef = refs[0];
  const dateRange =
    evidenceDateRangeLabel(firstFact?.date_range) !== "—"
      ? evidenceDateRangeLabel(firstFact?.date_range)
      : evidenceDateRangeLabel(firstRef?.date_range);

  if (!ledger) {
    return (
      <Alert className="border-destructive/30 bg-destructive/5">
        <AlertTriangle className="h-4 w-4" />
        <AlertTitle>Доказательств недостаточно</AlertTitle>
        <AlertDescription>
          Источник расчёта не передан. Задача доступна только как сигнал, пока
          бэкенд не вернёт формулу, факты и источник данных.
        </AlertDescription>
      </Alert>
    );
  }

  return (
    <div className="space-y-3">
      {dataFreshnessBlocksAction(freshness) ? (
        <Alert className="border-amber-500/35 bg-amber-500/10">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>{dataFreshnessStatusLabel(freshness)}</AlertTitle>
          <AlertDescription>
            {dataFreshnessBlockingLabel(freshness)}.{" "}
            {freshness?.freshness_notes?.length
              ? freshness.freshness_notes.slice(0, 2).join(" ")
              : "Доказательства и денежное влияние остаются предварительными до обновления источников."}
          </AlertDescription>
        </Alert>
      ) : null}
      {state !== "full_evidence" ? (
        <Alert className="border-amber-500/35 bg-amber-500/10">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>{evidenceStateLabel(state)}</AlertTitle>
          <AlertDescription>
            Сигнал можно изучить, но доказательная база неполная. Не применяйте
            рискованные действия без проверки недостающих данных.
          </AlertDescription>
        </Alert>
      ) : null}
      <div className="grid gap-2 text-xs sm:grid-cols-2">
        <InfoBlock
          label="Формула"
          value={ledger.formula_human ?? ledger.formula_code ?? "—"}
          wide
        />
        <InfoBlock
          label="Входные факты"
          value={
            facts.length
              ? facts
                  .slice(0, 3)
                  .map((fact) =>
                    [
                      fact.label ?? fact.metric_code ?? "Факт",
                      renderValue(fact.value),
                      fact.unit,
                    ]
                      .filter(Boolean)
                      .join(": "),
                  )
                  .join("; ")
              : "—"
          }
          wide
        />
        <InfoBlock
          label="Источник"
          value={evidenceSourceLabel(firstRef ?? firstFact)}
        />
        <InfoBlock label="Период" value={dateRange} />
        <InfoBlock
          label="Строк"
          value={evidenceRowCount(ledger, firstFact, firstRef)}
        />
        <InfoBlock label="Доверие" value={trustLabel} />
        <InfoBlock
          label="Свежесть источников"
          value={
            dataFreshnessBlocksAction(freshness)
              ? dataFreshnessBlockingLabel(freshness)
              : freshness?.required_sources?.length
                ? `Свежие: ${freshness.required_sources
                    .map((source) => actionCenterSourceFreshnessLabel(source))
                    .join(", ")}`
                : "—"
          }
          wide
        />
        <InfoBlock
          label="Не хватает данных"
          value={compactEvidenceList(ledger.missing_data)}
          wide
        />
        <InfoBlock
          label="Заметки доверия"
          value={compactEvidenceList(ledger.trust_notes)}
          wide
        />
        <InfoBlock
          label="Предупреждения расчёта"
          value={compactEvidenceList(ledger.calculation_warnings)}
          wide
        />
      </div>
    </div>
  );
}

export function ActionCenterEvidenceControls(props: Parameters<typeof EvidenceInlineSummary>[0]) {
  return <EvidenceInlineSummary {...props} />;
}
