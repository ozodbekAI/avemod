import {
  Calculator,
  Database,
  ExternalLink,
  FileText,
  ShieldAlert,
} from "lucide-react";
import type { MouseEvent, ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import {
  coerceEvidenceLedger,
  evidenceNeedsWarning,
  type EvidenceFixAction,
  type EvidenceInputFact,
  type EvidenceLedger,
  type EvidenceSourceReference,
} from "@/lib/evidence";
import { moneyTrustFrom, moneyTrustTone } from "@/lib/money-trust";
import {
  EVIDENCE_BUTTON_LABEL,
  problemImpactLabel,
  problemTrustLabel,
} from "@/lib/problem-ux-copy";
import { cn } from "@/lib/utils";

type EvidenceDrawerProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  ledger?: EvidenceLedger | null;
  title?: string;
  debug?: boolean;
};

type EvidenceButtonProps = {
  ledger?: EvidenceLedger | null;
  onClick: (event: MouseEvent<HTMLButtonElement>) => void;
  className?: string;
  disabled?: boolean;
  allowEmpty?: boolean;
};

const VALUE_TYPE_LABEL: Record<string, string> = {
  money: "деньги",
  number: "число",
  count: "количество",
  days: "дни",
  boolean: "да/нет",
  percent: "процент",
  date: "дата",
  status: "статус",
  text: "текст",
};

function evidenceTrustTone(state: string): string {
  if (["confirmed", "trusted", "final", "high"].includes(state)) {
    return "border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300";
  }
  if (["blocked", "data_blocked", "data_blocker", "low"].includes(state)) {
    return "border-amber-500/35 bg-amber-500/10 text-amber-800 dark:text-amber-300";
  }
  if (state === "test_only" || state === "test") {
    return "border-slate-500/30 bg-slate-500/10 text-slate-700 dark:text-slate-300";
  }
  return "border-amber-500/30 bg-amber-500/10 text-amber-800 dark:text-amber-300";
}

export function EvidenceButton({
  ledger,
  onClick,
  className,
  disabled,
  allowEmpty = false,
}: EvidenceButtonProps) {
  const hasLedger = !!coerceEvidenceLedger(ledger);
  return (
    <Button
      type="button"
      size="sm"
      variant="outline"
      className={cn(
        "h-auto min-h-9 max-w-full whitespace-normal px-2 py-1 text-left text-xs leading-tight sm:min-h-7 sm:max-w-[240px] sm:text-[11px]",
        className,
      )}
      disabled={disabled || (!hasLedger && !allowEmpty)}
      onClick={onClick}
    >
      <Calculator className="h-3.5 w-3.5" />
      <span>{EVIDENCE_BUTTON_LABEL}</span>
    </Button>
  );
}

export function EvidenceDrawer({
  open,
  onOpenChange,
  ledger,
  title = "Как посчитано",
  debug = false,
}: EvidenceDrawerProps) {
  const normalized = coerceEvidenceLedger(ledger);
  const canShowRaw = debug;

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        side="right"
        data-testid="evidence-drawer"
        className="inset-0 h-[100dvh] w-screen max-w-none overflow-y-auto border-l-0 p-4 sm:inset-y-0 sm:left-auto sm:right-0 sm:h-full sm:w-full sm:max-w-2xl sm:border-l sm:p-6"
      >
        <SheetHeader className="pr-8">
          <SheetTitle>{title}</SheetTitle>
          <SheetDescription>
            Формула, входные числа, источники данных и понятный способ
            перепроверить результат.
          </SheetDescription>
        </SheetHeader>

        {!normalized ? (
          <div className="mt-6 rounded-md border bg-muted/30 p-4 text-sm text-muted-foreground">
            Для этого элемента источник расчёта ещё не передан бэкендом.
          </div>
        ) : (
          <div className="mt-6 space-y-5">
            <EvidenceSummary ledger={normalized} />
            <FormulaBlock ledger={normalized} />
            <InputFacts
              facts={normalized.input_facts ?? []}
              references={normalized.source_references ?? []}
            />
            <SourceReferences references={normalized.source_references ?? []} />
            <MissingDataBlock ledger={normalized} />
            <ActionabilityBlock ledger={normalized} />
            <RecheckBlock
              action={normalized.next_fix_action}
              recheckRule={
                normalized.recheck_rule_human ?? normalized.recheck_rule
              }
            />
            {canShowRaw ? (
              <details className="rounded-md border bg-muted/20 p-3 text-xs">
                <summary className="cursor-pointer select-none font-medium">
                  Сырые данные источника (админ)
                </summary>
                <pre className="mt-2 max-h-80 overflow-auto rounded bg-background p-2 text-[11px] text-muted-foreground whitespace-pre-wrap">
                  {JSON.stringify(normalized, null, 2)}
                </pre>
              </details>
            ) : null}
          </div>
        )}
      </SheetContent>
    </Sheet>
  );
}

function EvidenceSummary({ ledger }: { ledger: EvidenceLedger }) {
  const moneyTrust = moneyTrustFrom(ledger.money_trust, ledger);
  const dataTrustState = String(
    moneyTrust.evidence_trust_state ?? ledger.confidence ?? moneyTrust.state,
  ).toLowerCase();
  const impactTrustState = String(
    moneyTrust.impact_trust_state ?? ledger.confidence ?? moneyTrust.state,
  ).toLowerCase();
  const warning =
    evidenceNeedsWarning(ledger) ||
    [
      "estimated",
      "test_only",
      "blocked",
      "data_blocked",
      "data_blocker",
    ].includes(impactTrustState);
  const impactKind = String(
    ledger.impact_type ?? moneyTrust.impact_kind ?? "probable_risk",
  ).toLowerCase();
  const dataTrustLabel = problemTrustLabel(dataTrustState);
  const impactTypeLabel = problemImpactLabel(impactKind);
  return (
    <section className="rounded-md border p-3">
      <SectionTitle>Короткий вывод</SectionTitle>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <Badge
          variant="outline"
          className={cn("text-[11px]", evidenceTrustTone(dataTrustState))}
          data-testid="evidence-data-trust"
        >
          Доверие к данным: {dataTrustLabel}
        </Badge>
        <Badge
          variant="outline"
          className={cn("text-[11px]", moneyTrustTone(moneyTrust))}
          data-testid="evidence-impact-type"
        >
          Тип влияния: {impactTypeLabel}
        </Badge>
        {ledger.value_type ? (
          <Badge variant="secondary" className="text-[11px]">
            {VALUE_TYPE_LABEL[String(ledger.value_type)] ?? ledger.value_type}
          </Badge>
        ) : null}
      </div>
      <p className="text-sm leading-relaxed">
        Платформа посчитала: {impactTypeLabel.toLowerCase()}.
        {ledger.value !== null && ledger.value !== undefined
          ? ` Расчётное значение: ${formatValue(ledger.value)}.`
          : ""}{" "}
        Денежный смысл: {impactTypeLabel.toLowerCase()}.
      </p>
      <p className="mt-2 text-xs text-muted-foreground">
        Данные могут быть подтверждены, но денежный эффект остаётся оценкой до
        результата после действия.
      </p>
      {moneyTrust.reason ? (
        <p className="mt-2 text-xs text-muted-foreground">
          {moneyTrust.reason}
        </p>
      ) : null}
      {warning ? (
        <div className="mt-3 flex items-start gap-2 rounded border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-900 dark:text-amber-200">
          <ShieldAlert className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          <span>
            Это значение нельзя читать как подтверждённые деньги: денежный
            эффект — {problemTrustLabel(impactTrustState)}.
          </span>
        </div>
      ) : null}
    </section>
  );
}

function FormulaBlock({ ledger }: { ledger: EvidenceLedger }) {
  return (
    <section className="rounded-md border p-3">
      <SectionTitle icon={<Calculator className="h-4 w-4" />}>
        Формула
      </SectionTitle>
      {ledger.formula_human ? (
        <p className="text-sm leading-relaxed">{ledger.formula_human}</p>
      ) : (
        <p className="text-sm text-muted-foreground">
          Формула не передана для этого расчёта.
        </p>
      )}
      {ledger.formula_code || ledger.formula_id ? (
        <div className="mt-2 rounded bg-muted/40 px-2.5 py-2 text-xs text-muted-foreground">
          {ledger.formula_id ? (
            <div>
              <span className="font-medium text-foreground">ID:</span>{" "}
              {ledger.formula_id}
            </div>
          ) : null}
          {ledger.formula_code ? (
            <div className="break-words font-mono">{ledger.formula_code}</div>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}

function InputFacts({
  facts,
  references,
}: {
  facts: EvidenceInputFact[];
  references: EvidenceSourceReference[];
}) {
  return (
    <section className="space-y-2">
      <SectionTitle icon={<FileText className="h-4 w-4" />}>
        Какие числа использовали
      </SectionTitle>
      {!facts.length ? (
        <div className="rounded-md border bg-muted/20 p-3 text-sm text-muted-foreground">
          Входные числа не переданы. Откройте задачу как сигнал и дождитесь
          обновления доказательств.
        </div>
      ) : null}
      {facts.map((fact, index) => (
        <div key={index} className="rounded-md border p-3">
          <FactRow fact={fact} index={index} references={references} />
          <SampleRows rows={fact.sample_rows ?? []} />
        </div>
      ))}
    </section>
  );
}

function FactRow({
  fact,
  index,
  references,
}: {
  fact: EvidenceInputFact;
  index: number;
  references: EvidenceSourceReference[];
}) {
  const ref = matchingReferenceForFact(fact, references);
  const technicalSource = technicalSourceLabel(fact, ref);
  return (
    <>
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <div className="font-medium">{fact.label ?? `Факт ${index + 1}`}</div>
        <div className="flex flex-wrap gap-1.5">
          {fact.metric_code ? (
            <Badge variant="secondary" className="text-[11px] font-mono">
              {fact.metric_code}
            </Badge>
          ) : null}
          {fact.trust_state ? (
            <Badge variant="outline" className="text-[11px]">
              {problemTrustLabel(fact.trust_state)}
            </Badge>
          ) : null}
          {fact.row_count != null ? (
            <Badge variant="outline" className="text-[11px]">
              строк: {formatValue(fact.row_count)}
            </Badge>
          ) : null}
        </div>
      </div>
      <div className="grid gap-3 text-xs sm:grid-cols-2 lg:grid-cols-4">
        <KV label="Число" value={formatValue(fact.value, fact.unit)} />
        <KV
          label="Период"
          value={formatDateRange(fact.date_range ?? ref?.date_range)}
        />
        <KV label="Источник" value={sellerSourceLabel(fact, ref)} />
        <KV label="Свежесть" value={freshnessLabel(fact, ref)} />
      </div>
      {technicalSource !== "—" || hasDisplayableObject(fact.filters) ? (
        <div className="mt-2 space-y-1 text-[11px] text-muted-foreground">
          {technicalSource !== "—" ? <div>{technicalSource}</div> : null}
          {hasDisplayableObject(fact.filters) ? (
            <div>Фильтры: {formatObject(fact.filters)}</div>
          ) : null}
        </div>
      ) : null}
    </>
  );
}

function SourceReferences({
  references,
}: {
  references: EvidenceSourceReference[];
}) {
  if (!references.length) return null;
  return (
    <section className="space-y-2">
      <SectionTitle icon={<Database className="h-4 w-4" />}>
        Откуда взяли данные
      </SectionTitle>
      <div className="grid gap-2">
        {references.map((ref, index) => (
          <div key={index} className="rounded-md border px-3 py-2 text-xs">
            <div className="font-medium">{sellerSourceLabel(ref)}</div>
            <div className="mt-1 grid gap-1 text-muted-foreground sm:grid-cols-2">
              <span>{technicalSourceLabel(ref)}</span>
              <span>Период: {formatDateRange(ref.date_range)}</span>
              <span>Строк: {formatValue(ref.row_count)}</span>
              <span>Свежесть: {freshnessLabel(ref)}</span>
              {ref.primary_key || ref.id ? (
                <span>
                  Ключ строки: {formatValue(ref.primary_key ?? ref.id)}
                </span>
              ) : null}
              {ref.raw_snapshot_id ? (
                <span>Снимок: {formatValue(ref.raw_snapshot_id)}</span>
              ) : null}
              {ref.sync_run_id ? (
                <span>Загрузка: {formatValue(ref.sync_run_id)}</span>
              ) : null}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

function MissingDataBlock({ ledger }: { ledger: EvidenceLedger }) {
  const missing = ledger.missing_data ?? [];
  return (
    <section
      className={cn(
        "rounded-md border p-3",
        missing.length ? "border-amber-500/30 bg-amber-500/5" : "",
      )}
    >
      <SectionTitle>Чего не хватает</SectionTitle>
      {missing.length ? (
        <ul className="space-y-1 text-sm text-amber-900 dark:text-amber-200">
          {missing.map((item, index) => (
            <li key={index}>{item}</li>
          ))}
        </ul>
      ) : (
        <p className="text-sm text-muted-foreground">
          Недостающих данных для этого расчёта нет.
        </p>
      )}
    </section>
  );
}

function ActionabilityBlock({ ledger }: { ledger: EvidenceLedger }) {
  const notes = ledger.trust_notes ?? [];
  const missing = ledger.missing_data ?? [];
  const warnings = ledger.calculation_warnings ?? [];
  const confidence = String(ledger.confidence ?? "provisional").toLowerCase();
  const blocked =
    missing.length > 0 ||
    confidence === "blocked" ||
    confidence === "test_only";
  const cautious =
    blocked || warnings.length > 0 || evidenceNeedsWarning(ledger);
  const action =
    typeof ledger.next_fix_action === "object" && ledger.next_fix_action
      ? ledger.next_fix_action
      : null;
  const href = action?.href ?? action?.screen_path;
  return (
    <section
      className={cn(
        "rounded-md border p-3",
        cautious ? "border-amber-500/30 bg-amber-500/5" : "",
      )}
    >
      <SectionTitle>Почему можно/нельзя действовать</SectionTitle>
      <p className="text-sm leading-relaxed">
        {blocked
          ? "Нельзя безопасно применять рискованные действия, пока не закрыты недостающие данные."
          : cautious
            ? "Можно разбирать задачу и готовить действие, но перед рискованным изменением проверьте предупреждения."
            : "Данных достаточно, чтобы перейти к рабочему действию и затем перепроверить результат."}
      </p>
      {notes.length ? (
        <ul className="mt-2 space-y-1 text-xs text-muted-foreground">
          {notes.map((note, index) => (
            <li key={index}>{note}</li>
          ))}
        </ul>
      ) : null}
      {warnings.length ? (
        <ul className="mt-2 space-y-1 text-xs text-amber-900 dark:text-amber-200">
          {warnings.map((item, index) => (
            <li key={index}>{item}</li>
          ))}
        </ul>
      ) : null}
      {typeof ledger.next_fix_action === "string" ? (
        <p className="mt-2 text-sm">{ledger.next_fix_action}</p>
      ) : null}
      {action ? (
        <div className="mt-2 space-y-1 text-sm">
          <div>{action.label ?? "Следующее действие"}</div>
          {href ? (
            <a
              className="inline-flex items-center gap-1 text-xs text-primary hover:underline"
              href={href}
            >
              Открыть экран действия <ExternalLink className="h-3 w-3" />
            </a>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}

function RecheckBlock({
  action,
  recheckRule,
}: {
  action?: EvidenceFixAction | string | null;
  recheckRule?: string | null;
}) {
  void action;
  return (
    <section className="rounded-md border p-3">
      <SectionTitle>Как перепроверим</SectionTitle>
      {recheckRule ? (
        <div className="rounded bg-muted/35 px-2.5 py-2 text-sm text-muted-foreground">
          {recheckRule}
        </div>
      ) : (
        <p className="text-sm text-muted-foreground">
          Правило повторной проверки не передано. После действия обновите
          источники и вернитесь к задаче.
        </p>
      )}
    </section>
  );
}

function SectionTitle({
  children,
  icon,
}: {
  children: ReactNode;
  icon?: ReactNode;
}) {
  return (
    <div className="mb-2 flex items-center gap-2 text-sm font-semibold">
      {icon}
      {children}
    </div>
  );
}

function matchingReferenceForFact(
  fact: EvidenceInputFact,
  references: EvidenceSourceReference[],
): EvidenceSourceReference | null {
  return (
    references.find((ref) => {
      const refTable = ref.source_table ?? ref.table;
      const refEndpoint = ref.source_endpoint ?? ref.wb_endpoint;
      return (
        (!!fact.source_table && fact.source_table === refTable) ||
        (!!fact.source_endpoint && fact.source_endpoint === refEndpoint)
      );
    }) ??
    references.find((ref) => {
      const refText = `${ref.source_table ?? ref.table ?? ""} ${
        ref.source_endpoint ?? ref.wb_endpoint ?? ""
      }`.toLowerCase();
      const factText =
        `${fact.metric_code ?? ""} ${fact.label ?? ""}`.toLowerCase();
      return factText
        .split(/[\s_]+/)
        .filter((part) => part.length > 3)
        .some((part) => refText.includes(part));
    }) ??
    null
  );
}

function sellerSourceLabel(
  primary: EvidenceInputFact | EvidenceSourceReference,
  secondary?: EvidenceSourceReference | null,
): string {
  const text = [
    "source" in primary ? primary.source : null,
    primary.source_table,
    "table" in primary ? primary.table : null,
    primary.source_endpoint,
    "wb_endpoint" in primary ? primary.wb_endpoint : null,
    secondary?.source_table,
    secondary?.table,
    secondary?.source_endpoint,
    secondary?.wb_endpoint,
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();

  if (/stock|остат/.test(text)) return "Остатки Вайлдберриз";
  if (/sales|order|заказ|продаж/.test(text))
    return "Заказы и продажи Вайлдберриз";
  if (/manual_cost|cost|себесто/.test(text)) return "Себестоимость";
  if (/price|цена/.test(text)) return "Цены";
  if (/promo|promotion|акци/.test(text)) return "Промо";
  if (/ads|advert|реклам/.test(text)) return "Реклама";
  if (/card|content|checker|карточ/.test(text)) return "Карточка товара";
  if (/finance|report|финанс/.test(text)) return "Финансы Вайлдберриз";
  if ("source" in primary && primary.source) return humanize(primary.source);
  return "Данные платформы";
}

function technicalSourceLabel(
  primary: EvidenceInputFact | EvidenceSourceReference,
  secondary?: EvidenceSourceReference | null,
): string {
  const table =
    primary.source_table ??
    ("table" in primary ? primary.table : null) ??
    secondary?.source_table ??
    secondary?.table;
  const endpoint =
    primary.source_endpoint ??
    ("wb_endpoint" in primary ? primary.wb_endpoint : null) ??
    secondary?.source_endpoint ??
    secondary?.wb_endpoint;
  const parts = [
    table ? `Таблица: ${humanize(table)}` : null,
    endpoint ? `API: ${endpoint}` : null,
  ].filter(Boolean);
  return parts.length ? parts.join("; ") : "—";
}

function freshnessLabel(
  primary: EvidenceInputFact | EvidenceSourceReference,
  secondary?: EvidenceSourceReference | null,
): string {
  const explicitStatus =
    firstString(primary.source_status, primary.freshness_status) ??
    firstString(secondary?.source_status, secondary?.freshness_status) ??
    freshnessStatusFromObject(primary.freshness) ??
    freshnessStatusFromObject(secondary?.freshness);
  const statusLabel = sourceStatusLabel(explicitStatus);
  if (statusLabel) return statusLabel;

  const syncedAt =
    firstString(primary.last_synced_at, primary.loaded_at) ??
    firstString(secondary?.last_synced_at, secondary?.loaded_at) ??
    freshnessDateFromObject(primary.freshness) ??
    freshnessDateFromObject(secondary?.freshness);
  if (syncedAt) return `Обновлено: ${formatValue(syncedAt)}`;

  if ("trust_state" in primary && primary.trust_state) {
    const trust = String(primary.trust_state).toLowerCase();
    if (trust === "confirmed") return "Данные подтверждены";
    if (trust === "blocked") return "Данных не хватает";
    if (trust === "estimated") return "Данные оценочные";
  }
  return "Данные предварительные";
}

function sourceStatusLabel(value: string | null | undefined): string | null {
  const normalized = String(value ?? "")
    .trim()
    .toLowerCase();
  if (!normalized) return null;
  if (["fresh", "completed", "ok", "confirmed"].includes(normalized)) {
    return "Данные свежие";
  }
  if (["stale", "old"].includes(normalized)) return "Нужна синхронизация";
  if (["missing", "not_configured", "failed"].includes(normalized)) {
    return "Данных не хватает";
  }
  if (["estimated", "provisional"].includes(normalized)) {
    return "Данные предварительные";
  }
  return humanize(normalized);
}

function freshnessStatusFromObject(value: unknown): string | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const record = value as Record<string, unknown>;
  return firstString(
    record.source_status,
    record.freshness_status,
    record.status,
  );
}

function freshnessDateFromObject(value: unknown): string | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const record = value as Record<string, unknown>;
  const cursor =
    record.sync_cursor && typeof record.sync_cursor === "object"
      ? (record.sync_cursor as Record<string, unknown>)
      : {};
  return firstString(
    record.last_synced_at,
    record.latest_updated_at,
    record.loaded_at,
    cursor.last_synced_at,
    cursor.updated_at,
  );
}

function firstString(...values: unknown[]): string | null {
  for (const value of values) {
    if (typeof value === "string" && value.trim()) return value;
    if (typeof value === "number" && Number.isFinite(value))
      return String(value);
  }
  return null;
}

function hasDisplayableObject(value: unknown): boolean {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  return Object.values(value).some((item) => item != null && item !== "");
}

function SampleRows({ rows }: { rows: Array<Record<string, unknown>> }) {
  if (!rows.length) return null;
  const columns = Array.from(
    new Set(rows.flatMap((row) => Object.keys(row))),
  ).slice(0, 6);
  if (!columns.length) return null;
  return (
    <div className="mt-3 overflow-x-auto rounded-md border">
      <table className="w-full min-w-[420px] text-left text-[11px]">
        <thead className="bg-muted/60 text-muted-foreground">
          <tr>
            {columns.map((column) => (
              <th key={column} className="px-2 py-1 font-medium">
                {humanize(column)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.slice(0, 5).map((row, rowIndex) => (
            <tr key={rowIndex} className="border-t">
              {columns.map((column) => (
                <td key={column} className="max-w-[220px] truncate px-2 py-1">
                  {formatValue(row[column])}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function KV({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="min-w-0">
      <div className="text-[11px] text-muted-foreground">{label}</div>
      <div className="break-words text-sm">{value}</div>
    </div>
  );
}

function formatValue(value: unknown, unit?: string | null): string {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "number" && Number.isFinite(value)) {
    return `${value.toLocaleString("ru-RU")}${unit ? ` ${unit}` : ""}`;
  }
  if (typeof value === "boolean") return value ? "да" : "нет";
  if (typeof value === "string") return unit ? `${value} ${unit}` : value;
  return formatObject(value);
}

function formatDateRange(value: unknown): string {
  if (!value || typeof value !== "object") return "—";
  const range = value as Record<string, unknown>;
  const from = range.date_from ?? range.from ?? range.start;
  const to = range.date_to ?? range.to ?? range.end;
  if (!from && !to) return formatObject(value);
  return `${formatValue(from)} → ${formatValue(to)}`;
}

function formatObject(value: unknown): string {
  if (!value) return "—";
  if (typeof value !== "object") return String(value);
  const entries = Object.entries(value as Record<string, unknown>).filter(
    ([, item]) => item != null && item !== "",
  );
  if (!entries.length) return "—";
  return entries
    .slice(0, 6)
    .map(([key, item]) => `${humanize(key)}: ${formatValue(item)}`)
    .join(", ");
}

function humanize(value: unknown): string {
  return String(value ?? "—").replaceAll("_", " ");
}
