import type { MetricCatalogItem } from "@/lib/problem-rules";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectSeparator,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  METRIC_AREA_LABELS,
  groupMetricsByArea,
} from "./ProblemRulesAdminShared";

export function MetricChipGroups({
  metrics,
  selected,
  onPickMetric,
  compact = false,
}: {
  metrics: MetricCatalogItem[];
  selected: string[];
  onPickMetric: (metricCode: string) => void;
  compact?: boolean;
}) {
  const groups = groupMetricsByArea(metrics);
  return (
    <div className="rounded-md border p-3" data-admin-rule-metric-groups="1">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div>
          <div className="text-sm font-medium">Метрики по бизнес-областям</div>
          <div className="text-xs text-muted-foreground">
            Нажмите метрику, чтобы добавить её в условие и доказательства правила.
          </div>
        </div>
        <Badge variant="outline">{selected.length} выбрано</Badge>
      </div>
      <div className="grid gap-3 md:grid-cols-2">
        {groups.map(({ area, items }) => (
          <div key={area} className="rounded-md border bg-muted/20 p-2">
            <div className="mb-2 text-xs font-medium text-muted-foreground">
              {METRIC_AREA_LABELS[area]}
            </div>
            <div className="flex flex-wrap gap-1.5">
              {(compact ? items.slice(0, 8) : items).map((metric) => {
                const active = selected.includes(metric.metric_code);
                return (
                  <Button
                    key={metric.metric_code}
                    type="button"
                    size="sm"
                    variant={active ? "default" : "outline"}
                    className="h-7 max-w-full text-[11px]"
                    title={metric.metric_code}
                    onClick={() => onPickMetric(metric.metric_code)}
                  >
                    <span className="truncate">
                      {metric.title || metric.metric_code}
                    </span>
                  </Button>
                );
              })}
              {items.length === 0 ? (
                <span className="text-xs text-muted-foreground">Нет метрик</span>
              ) : null}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export function MetricSelect({
  metrics,
  value,
  onChange,
}: {
  metrics: MetricCatalogItem[];
  value: string;
  onChange: (value: string) => void;
}) {
  const safeValue = value || metrics[0]?.metric_code || "stock_qty";
  return (
    <Select value={safeValue} onValueChange={onChange}>
      <SelectTrigger>
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {metrics.length === 0 ? (
          <SelectItem value={safeValue}>{safeValue}</SelectItem>
        ) : (
          groupMetricsByArea(metrics).map(({ area, items }, index) => (
            <SelectGroup key={area}>
              {index > 0 ? <SelectSeparator /> : null}
              <SelectLabel>{METRIC_AREA_LABELS[area]}</SelectLabel>
              {items.map((metric) => (
                <SelectItem key={metric.metric_code} value={metric.metric_code}>
                  {metric.title
                    ? `${metric.title} (${metric.metric_code})`
                    : metric.metric_code}
                </SelectItem>
              ))}
            </SelectGroup>
          ))
        )}
      </SelectContent>
    </Select>
  );
}
