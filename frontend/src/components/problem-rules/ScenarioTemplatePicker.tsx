import { Badge } from "@/components/ui/badge";

export type ScenarioTemplate = {
  id: string;
  title: string;
  description: string;
  impactSummary: string;
  metricCodes: string[];
  /** Явные метаданные шаблона — показываются на карточке до применения. */
  impactTypeLabel?: string;
  trustLabel?: string;
  typicalActionLabel?: string;
  surfaceTag?: string;
  requiredMetrics?: string[];
};

export function ScenarioTemplatePicker<TTemplate extends ScenarioTemplate>({
  templates,
  selectedTemplateId,
  onApplyTemplate,
}: {
  templates: TTemplate[];
  selectedTemplateId: string;
  onApplyTemplate: (template: TTemplate) => void;
}) {
  return (
    <div className="space-y-2">
      <div>
        <div className="text-sm font-medium">1. Выберите сценарий</div>
        <div className="text-xs text-muted-foreground">
          Это не финальная логика: любой шаблон можно изменить ниже.
        </div>
      </div>
      <div className="grid gap-2">
        {templates.map((template) => {
          const required = template.requiredMetrics ?? template.metricCodes;
          return (
            <button
              key={template.id}
              type="button"
              onClick={() => onApplyTemplate(template)}
              className={`rounded-md border p-3 text-left transition-colors hover:bg-muted/60 ${
                selectedTemplateId === template.id
                  ? "border-primary bg-primary/5"
                  : ""
              }`}
            >
              <div className="flex items-start justify-between gap-2">
                <div className="text-sm font-medium">{template.title}</div>
                {selectedTemplateId === template.id ? (
                  <Badge variant="outline">выбрано</Badge>
                ) : null}
              </div>
              <div className="mt-1 text-xs text-muted-foreground">
                {template.description}
              </div>

              {/* Метаданные сценария: тип влияния / доверие / типичное действие / поверхность */}
              <div className="mt-2 flex flex-wrap gap-1">
                {template.impactTypeLabel ? (
                  <Badge variant="outline" className="text-[10px]">
                    Влияние: {template.impactTypeLabel}
                  </Badge>
                ) : null}
                {template.trustLabel ? (
                  <Badge variant="outline" className="text-[10px]">
                    Доверие: {template.trustLabel}
                  </Badge>
                ) : null}
                {template.typicalActionLabel ? (
                  <Badge variant="outline" className="text-[10px]">
                    Действие: {template.typicalActionLabel}
                  </Badge>
                ) : null}
                {template.surfaceTag ? (
                  <Badge variant="outline" className="text-[10px]">
                    Поверхность: {template.surfaceTag}
                  </Badge>
                ) : null}
              </div>

              <div className="mt-2 text-xs">
                <span className="font-medium">На что влияет: </span>
                <span className="text-muted-foreground">
                  {template.impactSummary}
                </span>
              </div>

              {required.length > 0 ? (
                <div className="mt-2">
                  <div className="text-[10px] uppercase tracking-wide text-muted-foreground">
                    Обязательные метрики
                  </div>
                  <div className="mt-1 flex flex-wrap gap-1">
                    {required.slice(0, 4).map((metric) => (
                      <Badge
                        key={metric}
                        variant="secondary"
                        className="text-[10px]"
                      >
                        {metric}
                      </Badge>
                    ))}
                    {required.length > 4 ? (
                      <Badge variant="secondary" className="text-[10px]">
                        +{required.length - 4}
                      </Badge>
                    ) : null}
                  </div>
                </div>
              ) : null}
            </button>
          );
        })}
      </div>
    </div>
  );
}
