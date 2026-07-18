import type { MetricCatalogItem } from "@/lib/problem-rules";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { MetricSelect } from "./MetricChipGroups";
import {
  NUMERIC_OPERATOR_LABELS,
  type NumericBuilderState,
  type NumericOperator,
  type NumericTransform,
  type OperandKind,
  optionText,
} from "./ProblemRulesAdminShared";

export function ImpactFormulaBuilder({
  metrics,
  value,
  onChange,
}: {
  metrics: MetricCatalogItem[];
  value: NumericBuilderState;
  onChange: (value: NumericBuilderState) => void;
}) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-6 gap-2">
      <div className="md:col-span-2">
        <MetricSelect
          metrics={metrics}
          value={value.metric}
          onChange={(metric) => onChange({ ...value, metric })}
        />
      </div>
      <Select
        value={value.operator}
        onValueChange={(operator) =>
          onChange({ ...value, operator: operator as NumericOperator })
        }
      >
        <SelectTrigger>
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {["none", "+", "-", "*", "/", "max", "min", "percent_change"].map(
            (item) => (
              <SelectItem key={item} value={item}>
                {optionText(NUMERIC_OPERATOR_LABELS, item)}
              </SelectItem>
            ),
          )}
        </SelectContent>
      </Select>
      <Select
        value={value.operandKind}
        onValueChange={(operandKind) =>
          onChange({ ...value, operandKind: operandKind as OperandKind })
        }
      >
        <SelectTrigger>
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="literal">число</SelectItem>
          <SelectItem value="metric">метрика</SelectItem>
        </SelectContent>
      </Select>
      {value.operandKind === "metric" ? (
        <MetricSelect
          metrics={metrics}
          value={value.operandMetric}
          onChange={(operandMetric) => onChange({ ...value, operandMetric })}
        />
      ) : (
        <Input
          value={value.operandValue}
          onChange={(event) =>
            onChange({ ...value, operandValue: event.target.value })
          }
          placeholder="значение"
          disabled={value.operator === "none"}
        />
      )}
      <Select
        value={value.transform}
        onValueChange={(transform) =>
          onChange({ ...value, transform: transform as NumericTransform })
        }
      >
        <SelectTrigger>
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="none">как есть</SelectItem>
          <SelectItem value="abs">модуль</SelectItem>
          <SelectItem value="round">округлить</SelectItem>
        </SelectContent>
      </Select>
    </div>
  );
}
