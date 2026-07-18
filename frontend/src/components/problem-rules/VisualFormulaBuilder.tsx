import type { ReactNode } from "react";
import { Plus } from "lucide-react";

import type { MetricCatalogItem } from "@/lib/problem-rules";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ImpactFormulaBuilder } from "./ImpactFormulaBuilder";
import { MetricSelect } from "./MetricChipGroups";
import {
  CLAUSE_OPERATOR_LABELS,
  SEVERITY_LABELS,
  SEVERITY_OPTIONS,
  TRUST_LABELS,
  TRUST_OPTIONS,
  type ClauseOperator,
  type ConditionClause,
  type MatchMode,
  type RuleBuilderState,
  optionText,
} from "./ProblemRulesAdminShared";

export type HumanRuleFormula = {
  condition: string;
  impact: string;
  severity: string;
  confidence: string;
};

export function VisualFormulaBuilder({
  metrics,
  builder,
  humanFormula,
  onChange,
  conditionTitle = "Когда показывать проблему",
  impactTitle = "Как считать влияние",
  severityTitle = "Серьёзность и доверие",
}: {
  metrics: MetricCatalogItem[];
  builder: RuleBuilderState;
  humanFormula: HumanRuleFormula;
  onChange: (builder: RuleBuilderState) => void;
  conditionTitle?: string;
  impactTitle?: string;
  severityTitle?: string;
}) {
  return (
    <>
      <FormulaBuilderSection
        title={conditionTitle}
        formula={humanFormula.condition}
      >
        <ConditionBuilder
          metrics={metrics}
          mode={builder.matchMode}
          clauses={builder.clauses}
          onModeChange={(matchMode) => onChange({ ...builder, matchMode })}
          onChange={(clauses) => onChange({ ...builder, clauses })}
        />
      </FormulaBuilderSection>

      <FormulaBuilderSection title={impactTitle} formula={humanFormula.impact}>
        <ImpactFormulaBuilder
          metrics={metrics}
          value={builder.impact}
          onChange={(impact) => onChange({ ...builder, impact })}
        />
      </FormulaBuilderSection>

      <FormulaBuilderSection
        title={severityTitle}
        formula={`${humanFormula.severity} / ${humanFormula.confidence}`}
      >
        <SeverityConfidenceBuilder
          metrics={metrics}
          builder={builder}
          onChange={onChange}
        />
      </FormulaBuilderSection>
    </>
  );
}

function FormulaBuilderSection({
  title,
  formula,
  children,
}: {
  title: string;
  formula: string;
  children: ReactNode;
}) {
  return (
    <div className="rounded-md border p-3">
      <div className="mb-3 flex flex-wrap items-start justify-between gap-2">
        <div className="text-sm font-medium">{title}</div>
        <div className="max-w-full rounded-md border bg-muted/30 px-2 py-1 text-xs">
          <span className="font-medium">Предпросмотр: </span>
          <span className="text-muted-foreground">{formula || "не настроено"}</span>
        </div>
      </div>
      {children}
    </div>
  );
}

function ConditionBuilder({
  metrics,
  mode,
  clauses,
  onModeChange,
  onChange,
}: {
  metrics: MetricCatalogItem[];
  mode: MatchMode;
  clauses: ConditionClause[];
  onModeChange: (mode: MatchMode) => void;
  onChange: (clauses: ConditionClause[]) => void;
}) {
  const metricCode = metrics[0]?.metric_code ?? "stock_qty";
  const updateClause = (id: string, patch: Partial<ConditionClause>) => {
    onChange(
      clauses.map((clause) =>
        clause.id === id ? { ...clause, ...patch } : clause,
      ),
    );
  };
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <Label className="text-xs">Логика</Label>
        <Select
          value={mode}
          onValueChange={(value) => onModeChange(value as MatchMode)}
        >
          <SelectTrigger className="w-[150px]">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="and">все условия</SelectItem>
            <SelectItem value="or">любое условие</SelectItem>
          </SelectContent>
        </Select>
        <Button
          size="sm"
          variant="outline"
          onClick={() =>
            onChange([
              ...clauses,
              {
                id: cryptoId(),
                metric: metricCode,
                operator: ">",
                value: "0",
                valueTo: "",
              },
            ])
          }
        >
          <Plus className="mr-1.5 h-4 w-4" />
          Добавить условие
        </Button>
      </div>
      <div className="space-y-2">
        {clauses.map((clause, index) => (
          <div
            key={clause.id}
            className="grid grid-cols-1 lg:grid-cols-[72px_minmax(0,1fr)_140px_140px_140px_80px] gap-2"
          >
            <div className="flex items-center">
              <Badge
                variant={index === 0 ? "default" : "outline"}
                className="w-full justify-center"
              >
                {index === 0 ? "IF" : mode === "and" ? "AND" : "OR"}
              </Badge>
            </div>
            <MetricSelect
              metrics={metrics}
              value={clause.metric}
              onChange={(metric) => updateClause(clause.id, { metric })}
            />
            <Select
              value={clause.operator}
              onValueChange={(operator) =>
                updateClause(clause.id, {
                  operator: operator as ClauseOperator,
                })
              }
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {[
                  ">",
                  ">=",
                  "<",
                  "<=",
                  "==",
                  "!=",
                  "between",
                  "in",
                  "missing",
                  "present",
                ].map((item) => (
                  <SelectItem key={item} value={item}>
                    {optionText(CLAUSE_OPERATOR_LABELS, item)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Input
              disabled={
                clause.operator === "missing" || clause.operator === "present"
              }
              value={clause.value}
              onChange={(event) =>
                updateClause(clause.id, { value: event.target.value })
              }
              placeholder={clause.operator === "in" ? "a,b,c" : "значение"}
            />
            <Input
              disabled={clause.operator !== "between"}
              value={clause.valueTo}
              onChange={(event) =>
                updateClause(clause.id, { valueTo: event.target.value })
              }
              placeholder="до"
            />
            <Button
              size="sm"
              variant="outline"
              onClick={() =>
                onChange(clauses.filter((item) => item.id !== clause.id))
              }
            >
              Удалить
            </Button>
          </div>
        ))}
      </div>
    </div>
  );
}

function SeverityConfidenceBuilder({
  metrics,
  builder,
  onChange,
}: {
  metrics: MetricCatalogItem[];
  builder: RuleBuilderState;
  onChange: (builder: RuleBuilderState) => void;
}) {
  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
      <div className="rounded-md border p-3">
        <div className="mb-2 text-sm font-medium">Серьёзность</div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
          <Select
            value={builder.severityMode}
            onValueChange={(severityMode) =>
              onChange({
                ...builder,
                severityMode: severityMode as RuleBuilderState["severityMode"],
              })
            }
          >
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="constant">фиксированное значение</SelectItem>
              <SelectItem value="threshold">по порогу метрики</SelectItem>
            </SelectContent>
          </Select>
          <Select
            value={builder.severityConstant}
            onValueChange={(severityConstant) =>
              onChange({ ...builder, severityConstant })
            }
          >
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {SEVERITY_OPTIONS.map((item) => (
                <SelectItem key={item} value={item}>
                  {optionText(SEVERITY_LABELS, item)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          {builder.severityMode === "threshold" && (
            <>
              <MetricSelect
                metrics={metrics}
                value={builder.severityMetric}
                onChange={(severityMetric) =>
                  onChange({ ...builder, severityMetric })
                }
              />
              <Input
                value={builder.severityThreshold}
                onChange={(event) =>
                  onChange({
                    ...builder,
                    severityThreshold: event.target.value,
                  })
                }
                placeholder="порог"
              />
              <Select
                value={builder.severityHigh}
                onValueChange={(severityHigh) =>
                  onChange({ ...builder, severityHigh })
                }
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {SEVERITY_OPTIONS.map((item) => (
                    <SelectItem key={item} value={item}>
                      {optionText(SEVERITY_LABELS, item)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Select
                value={builder.severityOtherwise}
                onValueChange={(severityOtherwise) =>
                  onChange({ ...builder, severityOtherwise })
                }
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {SEVERITY_OPTIONS.map((item) => (
                    <SelectItem key={item} value={item}>
                      {optionText(SEVERITY_LABELS, item)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </>
          )}
        </div>
      </div>
      <div className="rounded-md border p-3">
        <div className="mb-2 text-sm font-medium">Уверенность / доверие</div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
          <Select
            value={builder.confidenceMode}
            onValueChange={(confidenceMode) =>
              onChange({
                ...builder,
                confidenceMode:
                  confidenceMode as RuleBuilderState["confidenceMode"],
              })
            }
          >
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="constant">фиксированное значение</SelectItem>
              <SelectItem value="threshold">по порогу метрики</SelectItem>
            </SelectContent>
          </Select>
          <Select
            value={builder.confidenceConstant}
            onValueChange={(confidenceConstant) =>
              onChange({ ...builder, confidenceConstant })
            }
          >
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {TRUST_OPTIONS.map((item) => (
                <SelectItem key={item} value={item}>
                  {optionText(TRUST_LABELS, item)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          {builder.confidenceMode === "threshold" && (
            <>
              <MetricSelect
                metrics={metrics}
                value={builder.confidenceMetric}
                onChange={(confidenceMetric) =>
                  onChange({ ...builder, confidenceMetric })
                }
              />
              <Input
                value={builder.confidenceThreshold}
                onChange={(event) =>
                  onChange({
                    ...builder,
                    confidenceThreshold: event.target.value,
                  })
                }
                placeholder="порог"
              />
              <Select
                value={builder.confidenceHigh}
                onValueChange={(confidenceHigh) =>
                  onChange({ ...builder, confidenceHigh })
                }
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {TRUST_OPTIONS.map((item) => (
                    <SelectItem key={item} value={item}>
                      {optionText(TRUST_LABELS, item)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Select
                value={builder.confidenceOtherwise}
                onValueChange={(confidenceOtherwise) =>
                  onChange({ ...builder, confidenceOtherwise })
                }
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {TRUST_OPTIONS.map((item) => (
                    <SelectItem key={item} value={item}>
                      {optionText(TRUST_LABELS, item)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function cryptoId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto)
    return crypto.randomUUID();
  return Math.random().toString(36).slice(2);
}
