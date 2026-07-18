import { useMemo } from "react";
import { AlertTriangle, FlaskConical, Loader2 } from "lucide-react";

import type { JsonObject } from "@/lib/api";
import { formatMoneyCompact, formatNumber } from "@/lib/format";
import type {
  ProblemRuleVersion,
  RuleBacktestResponse,
} from "@/lib/problem-rules";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import {
  AdminRuleStepper,
  Field,
  IMPACT_LABELS,
  InfoTile,
  SeverityBadge,
  TRUST_LABELS,
  labelFor,
} from "./ProblemRulesAdminShared";

export function BacktestPreview({
  selectedVersion,
  form,
  onFormChange,
  backtest,
  pending,
  sellerPreviewReviewed,
  onSellerPreviewReviewedChange,
  onRun,
}: {
  selectedVersion: ProblemRuleVersion | null;
  form: {
    account_id: string;
    date_from: string;
    date_to: string;
    nm_id: string;
    sample_limit: string;
  };
  onFormChange: (form: {
    account_id: string;
    date_from: string;
    date_to: string;
    nm_id: string;
    sample_limit: string;
  }) => void;
  backtest: RuleBacktestResponse | null;
  pending: boolean;
  sellerPreviewReviewed: boolean;
  onSellerPreviewReviewedChange: (reviewed: boolean) => void;
  onRun: () => void;
}) {
  const impactGroups = useMemo(
    () => (backtest ? groupBacktestImpact(backtest) : []),
    [backtest],
  );
  const topWarnings = backtest?.warnings.slice(0, 5) ?? [];
  return (
    <div className="rounded-md border p-3">
      <AdminRuleStepper activeStep={8} />
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div className="text-sm font-medium">
          9. Тестовый прогон: предварительная проверка
        </div>
        <Button
          size="sm"
          onClick={onRun}
          disabled={!selectedVersion || pending}
        >
          {pending ? (
            <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />
          ) : (
            <FlaskConical className="mr-1.5 h-4 w-4" />
          )}
          Запустить тестовый прогон
        </Button>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-5 gap-2">
        <Field label="Аккаунт">
          <Input
            value={form.account_id}
            onChange={(event) =>
              onFormChange({ ...form, account_id: event.target.value })
            }
          />
        </Field>
        <Field label="Дата с">
          <Input
            type="date"
            value={form.date_from}
            onChange={(event) =>
              onFormChange({ ...form, date_from: event.target.value })
            }
          />
        </Field>
        <Field label="Дата по">
          <Input
            type="date"
            value={form.date_to}
            onChange={(event) =>
              onFormChange({ ...form, date_to: event.target.value })
            }
          />
        </Field>
        <Field label="nm_id">
          <Input
            value={form.nm_id}
            onChange={(event) =>
              onFormChange({ ...form, nm_id: event.target.value })
            }
            placeholder="необязательно"
          />
        </Field>
        <Field label="Размер примера">
          <Input
            value={form.sample_limit}
            onChange={(event) =>
              onFormChange({ ...form, sample_limit: event.target.value })
            }
          />
        </Field>
      </div>
      {!backtest && (
        <div className="mt-3 rounded-md border border-dashed p-4 text-center">
          <div className="text-sm font-medium">Backtest ещё не запускался</div>
          <div className="mt-1 text-xs text-muted-foreground">
            Запустите проверку на исторических данных перед публикацией.
          </div>
        </div>
      )}
      {backtest && (
        <div className="mt-3 space-y-3">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
            <InfoTile
              label="Найдено"
              value={`${formatNumber(backtest.matched_count)} / ${formatNumber(backtest.evaluated_count)}`}
            />
            <InfoTile
              label="Влияние"
              value={formatMoneyCompact(
                Number(backtest.total_impact_amount ?? 0),
              )}
            />
            <InfoTile
              label="Тестовый запуск"
              value={
                backtest.test_run_id
                  ? `#${backtest.test_run_id}`
                  : "не сохранён"
              }
            />
            <InfoTile label="Предупреждения" value={String(backtest.warnings.length)} />
          </div>
          {Object.keys(backtest.missing_metric_stats).length > 0 && (
            <div>
              <div className="mb-1 text-xs font-medium">
                Статистика пропущенных метрик
              </div>
              <div className="flex flex-wrap gap-1.5">
                {Object.entries(backtest.missing_metric_stats).map(
                  ([metric, count]) => (
                    <Badge key={metric} variant="secondary">
                      {metric}: {count}
                    </Badge>
                  ),
                )}
              </div>
            </div>
          )}

          {impactGroups.length > 0 && (
            <div>
              <div className="mb-1 text-xs font-medium">
                Оценка влияния по типу и доверию
              </div>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
                {impactGroups.map((group) => (
                  <InfoTile
                    key={group.key}
                    label={`${labelFor(IMPACT_LABELS, group.impactType)} · ${labelFor(TRUST_LABELS, group.trustState)}`}
                    value={`${formatMoneyCompact(group.total)} · ${group.count} карточек`}
                  />
                ))}
              </div>
            </div>
          )}

          {topWarnings.length > 0 && (
            <Alert>
              <AlertTriangle className="h-4 w-4" />
              <AlertTitle>Главные предупреждения</AlertTitle>
              <AlertDescription>
                <ul className="list-disc pl-4">
                  {topWarnings.map((warning) => (
                    <li key={warning}>{warning}</li>
                  ))}
                </ul>
              </AlertDescription>
            </Alert>
          )}

          <div data-admin-rule-seller-card-preview="1">
            <div className="mb-2 text-sm font-medium">
              8. Карточки продавца: как проблема будет выглядеть после публикации
            </div>
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-2">
              {backtest.sample_issues.map((issue, index) => (
                <SellerSampleProblemCard
                  key={`${issue.dedup_key ?? index}`}
                  issue={issue}
                />
              ))}
            </div>
            {backtest.sample_issues.length === 0 && (
              <div className="rounded-md border px-3 py-6 text-center text-sm text-muted-foreground">
                В примере проблем нет.
              </div>
            )}
            <label className="mt-3 flex items-start gap-2 rounded-md border px-3 py-2 text-sm">
              <Checkbox
                checked={sellerPreviewReviewed}
                onCheckedChange={(checked) =>
                  onSellerPreviewReviewedChange(Boolean(checked))
                }
              />
              <span>
                Я проверил(а), как карточка будет выглядеть для продавца.
              </span>
            </label>
          </div>
        </div>
      )}
    </div>
  );
}

function SellerSampleProblemCard({ issue }: { issue: JsonObject }) {
  const evidence = isJsonObject(issue.evidence_ledger_json)
    ? issue.evidence_ledger_json
    : {};
  const formulaHuman = String(evidence.formula_human ?? "").trim();
  const warnings = Array.isArray(evidence.calculation_warnings)
    ? evidence.calculation_warnings
    : [];
  const title = String(issue.title ?? issue.problem_code ?? "Проблема товара");
  const recommendation = String(
    issue.recommendation ?? "Проверьте данные и запустите перепроверку.",
  );
  const explanation = String(
    issue.explanation ?? "Проблема найдена по правилу.",
  );
  return (
    <div className="rounded-md border p-3 text-sm">
      <div className="mb-2 flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="font-medium">{title}</div>
          <div className="text-xs text-muted-foreground">
            nmID {String(issue.nm_id ?? "—")}
          </div>
        </div>
        <SeverityBadge severity={String(issue.severity ?? "medium")} />
      </div>
      <div className="mb-2 flex flex-wrap gap-1.5">
        <Badge variant="outline">
          {labelFor(IMPACT_LABELS, String(issue.impact_type ?? "system_warning"))}
        </Badge>
        <Badge variant="outline">
          {labelFor(TRUST_LABELS, String(issue.trust_state ?? "estimated"))}
        </Badge>
        <Badge variant="secondary">
          {formatMoneyCompact(Number(issue.money_impact_amount ?? 0))}
        </Badge>
      </div>
      <div className="mb-2 rounded-md border bg-muted/20 p-2">
        <div className="mb-1 text-xs font-medium">
          Предпросмотр строки Центра действий
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <SeverityBadge severity={String(issue.severity ?? "medium")} />
          <span className="font-medium">{title}</span>
          <Badge variant="outline">{String(issue.status ?? "new")}</Badge>
          <Badge variant="secondary">ждём данных</Badge>
          <Button
            size="sm"
            variant="outline"
            className="h-auto max-w-full whitespace-normal text-left"
            disabled
          >
            {recommendation}
          </Button>
        </div>
      </div>
      <div className="mb-2 rounded-md border bg-background p-2">
        <div className="mb-1 text-xs font-medium">
          Предпросмотр drawer Центра действий
        </div>
        <div className="space-y-1 text-xs text-muted-foreground">
          <div>
            <span className="font-medium text-foreground">Что произошло? </span>
            {explanation}
          </div>
          <div>
            <span className="font-medium text-foreground">Карта решения: </span>
            {recommendation}
          </div>
          <div>
            <span className="font-medium text-foreground">Как перепроверим? </span>
            {String(evidence.recheck_rule_human ?? "Повторно запустим правило после действия.")}
          </div>
        </div>
      </div>
      <div className="space-y-2 text-xs">
        <div>
          <div className="font-medium">Что произошло?</div>
          <div className="text-muted-foreground">
            {explanation}
          </div>
        </div>
        <div>
          <div className="font-medium">Что сделать сейчас?</div>
          <div className="text-muted-foreground">
            {recommendation}
          </div>
        </div>
        <div className="rounded-md border bg-muted/30 p-2">
          <div className="font-medium">Как посчитано?</div>
          <div className="text-muted-foreground">
            {formulaHuman || "Формула будет показана из доказательств правила."}
          </div>
        </div>
        {warnings.length > 0 && (
          <div className="text-amber-700">
            {warnings.slice(0, 2).map((warning) => String(warning)).join("; ")}
          </div>
        )}
      </div>
    </div>
  );
}

function groupBacktestImpact(backtest: RuleBacktestResponse) {
  const groups = new Map<
    string,
    {
      key: string;
      impactType: string;
      trustState: string;
      total: number;
      count: number;
    }
  >();
  for (const issue of backtest.sample_issues) {
    const impactType = String(issue.impact_type ?? "system_warning");
    const trustState = String(issue.trust_state ?? "estimated");
    const key = `${impactType}:${trustState}`;
    const current =
      groups.get(key) ??
      { key, impactType, trustState, total: 0, count: 0 };
    current.total += Number(issue.money_impact_amount ?? 0);
    current.count += 1;
    groups.set(key, current);
  }
  return Array.from(groups.values()).sort((a, b) => b.total - a.total);
}

function isJsonObject(value: unknown): value is JsonObject {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}
