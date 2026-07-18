import type { MetricCatalogItem } from "@/lib/problem-rules";
import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Field, type RuleBuilderState } from "./ProblemRulesAdminShared";

export function EvidenceTemplateEditor({
  metrics,
  builder,
  selectedMetrics,
  onChange,
}: {
  metrics: MetricCatalogItem[];
  builder: RuleBuilderState;
  selectedMetrics: string[];
  onChange: (builder: RuleBuilderState) => void;
}) {
  const visibleMetrics = selectedMetrics.length
    ? metrics.filter((metric) => selectedMetrics.includes(metric.metric_code))
    : metrics.slice(0, 12);
  return (
    <div className="rounded-md border p-3">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div className="text-sm font-medium">
          6. Настройте доказательства для «Как посчитано?»
        </div>
        <Badge
          variant={builder.evidenceMetrics.length ? "outline" : "destructive"}
        >
          {builder.evidenceMetrics.length} полей доказательств
        </Badge>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <Field label="Формула простыми словами">
          <Textarea
            rows={3}
            value={builder.evidenceFormulaHuman}
            onChange={(event) =>
              onChange({ ...builder, evidenceFormulaHuman: event.target.value })
            }
          />
        </Field>
        <Field label="Как перепроверять">
          <Textarea
            rows={3}
            value={builder.recheckHuman}
            onChange={(event) =>
              onChange({ ...builder, recheckHuman: event.target.value })
            }
          />
        </Field>
        <Field label="Валюта денег">
          <Input
            value={builder.moneyCurrency}
            onChange={(event) =>
              onChange({ ...builder, moneyCurrency: event.target.value })
            }
          />
        </Field>
        <Field label="Пояснения к доверию">
          <Input
            value={builder.trustNotes}
            onChange={(event) =>
              onChange({ ...builder, trustNotes: event.target.value })
            }
            placeholder="через запятую"
          />
        </Field>
      </div>
      <div className="mt-3 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
        {visibleMetrics.map((metric) => (
          <label
            key={metric.metric_code}
            className="flex items-start gap-2 rounded-md border px-3 py-2 text-sm"
          >
            <Checkbox
              checked={builder.evidenceMetrics.includes(metric.metric_code)}
              onCheckedChange={(checked) => {
                const evidenceMetrics = checked
                  ? Array.from(
                      new Set([...builder.evidenceMetrics, metric.metric_code]),
                    )
                  : builder.evidenceMetrics.filter(
                      (code) => code !== metric.metric_code,
                    );
                onChange({ ...builder, evidenceMetrics });
              }}
            />
            <span className="min-w-0">
              <span className="block truncate font-medium">
                {metric.title || metric.metric_code}
              </span>
              <span className="block truncate text-xs text-muted-foreground">
                {metric.metric_code}
              </span>
            </span>
          </label>
        ))}
      </div>
    </div>
  );
}
