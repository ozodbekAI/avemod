import { Loader2, Plus, Search } from "lucide-react";

import { formatDateTime } from "@/lib/format";
import type {
  ProblemDefinition,
  ProblemDefinitionDetail,
} from "@/lib/problem-rules";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  ACTION_LABELS,
  CATEGORY_LABELS,
  ENTITY_LABELS,
  InfoTile,
  IMPACT_LABELS,
  StatusBadge,
  SeverityBadge,
  TemplatePreview,
  TRUST_LABELS,
  labelFor,
  optionText,
} from "./ProblemRulesAdminShared";

export function ProblemRulesList({
  definitions,
  selectedId,
  loading,
  search,
  onSearch,
  onSelect,
  onCreate,
}: {
  definitions: ProblemDefinition[];
  selectedId: number | null;
  loading: boolean;
  search: string;
  onSearch: (value: string) => void;
  onSelect: (id: number) => void;
  onCreate: () => void;
}) {
  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between gap-2">
          <div>
            <CardTitle className="text-base">Каталог проблем</CardTitle>
            <CardDescription className="text-xs">
              Правила, которые автоматически создают задачи и подсказки для
              продавца
            </CardDescription>
          </div>
          <Button size="sm" onClick={onCreate}>
            <Plus className="mr-1.5 h-4 w-4" />
            Создать из шаблона
          </Button>
        </div>
        <div className="relative">
          <Search className="absolute left-2 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input
            className="pl-8"
            value={search}
            onChange={(event) => onSearch(event.target.value)}
            placeholder="Поиск по коду, категории или статусу"
          />
        </div>
      </CardHeader>
      <CardContent className="p-0">
        {loading ? (
          <div className="p-6 text-sm text-muted-foreground">
            <Loader2 className="mr-2 inline h-4 w-4 animate-spin" />
            Загружаем правила
          </div>
        ) : (
          <div className="max-h-[640px] overflow-y-auto">
            {definitions.map((definition) => (
              <button
                key={definition.id}
                type="button"
                onClick={() => onSelect(definition.id)}
                className={`w-full border-b px-4 py-3 text-left transition-colors hover:bg-muted/60 ${
                  selectedId === definition.id ? "bg-primary/5" : ""
                }`}
              >
                <div className="flex items-center justify-between gap-2">
                  <div className="min-w-0">
                    <div className="truncate text-sm font-medium">
                      {definition.problem_code}
                    </div>
                    <div className="mt-1 flex flex-wrap gap-1.5">
                      <StatusBadge status={definition.status} />
                      <Badge variant="outline">
                        {labelFor(CATEGORY_LABELS, definition.category)}
                      </Badge>
                    </div>
                  </div>
                  <SeverityBadge severity={definition.severity_default} />
                </div>
              </button>
            ))}
            {definitions.length === 0 && (
              <div className="p-4">
                <div className="rounded-md border border-dashed p-6 text-center">
                  <div className="text-sm font-medium">Правил пока нет</div>
                  <div className="mt-1 text-xs text-muted-foreground">
                    Создайте первое правило из шаблона или начните с пустого сценария.
                  </div>
                </div>
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export function ProblemRuleDefinitionSummary({
  detail,
  loading,
  selectedVersionId,
  onSelectVersion,
}: {
  detail: ProblemDefinitionDetail | null;
  loading: boolean;
  selectedVersionId: number | null;
  onSelectVersion: (id: number) => void;
}) {
  if (loading) {
    return (
      <Card>
        <CardContent className="p-6 text-sm text-muted-foreground">
          <Loader2 className="mr-2 inline h-4 w-4 animate-spin" />
          Загружаем проблему
        </CardContent>
      </Card>
    );
  }
  if (!detail) {
    return (
      <Card>
        <CardContent className="p-6 text-sm text-muted-foreground">
          Выберите проблему слева или создайте новую.
        </CardContent>
      </Card>
    );
  }
  return (
    <div className="space-y-3">
      <Card>
        <CardHeader className="pb-3">
          <div className="flex flex-wrap items-start justify-between gap-2">
            <div>
              <CardTitle className="text-base">{detail.problem_code}</CardTitle>
              <CardDescription className="text-xs">
                {detail.title_template}
              </CardDescription>
            </div>
            <div className="flex flex-wrap gap-1.5">
              <StatusBadge status={detail.status} />
              <SeverityBadge severity={detail.severity_default} />
              <Badge variant="outline">
                {labelFor(TRUST_LABELS, detail.trust_state_default)}
              </Badge>
              <Badge variant="outline">
                {labelFor(IMPACT_LABELS, detail.impact_type_default)}
              </Badge>
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-3 text-sm">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
            <InfoTile
              label="Категория"
              value={optionText(CATEGORY_LABELS, detail.category)}
            />
            <InfoTile
              label="Сущность"
              value={optionText(ENTITY_LABELS, detail.entity_type)}
            />
            <InfoTile label="Источник" value={detail.source_module} />
          </div>
          <TemplatePreview
            title="Объяснение для продавца"
            value={detail.description_template}
          />
          <TemplatePreview
            title="Рекомендация"
            value={detail.recommendation_template}
          />
          <div className="flex flex-wrap gap-1.5">
            {detail.allowed_actions_json.map((action) => (
              <Badge key={action} variant="secondary">
                {optionText(ACTION_LABELS, action)}
              </Badge>
            ))}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Версии правила</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Версия</TableHead>
                <TableHead>Статус</TableHead>
                <TableHead>Период</TableHead>
                <TableHead>Опубликовано</TableHead>
                <TableHead />
              </TableRow>
            </TableHeader>
            <TableBody>
              {detail.versions.map((version) => (
                <TableRow
                  key={version.id}
                  data-state={
                    selectedVersionId === version.id ? "selected" : undefined
                  }
                >
                  <TableCell className="font-mono text-xs">
                    v{version.version}
                  </TableCell>
                  <TableCell>
                    <StatusBadge status={version.status} />
                  </TableCell>
                  <TableCell>{version.lookback_days} дн.</TableCell>
                  <TableCell className="text-xs">
                    {formatDateTime(version.published_at)}
                  </TableCell>
                  <TableCell className="text-right">
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => onSelectVersion(version.id)}
                    >
                      Открыть
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
              {detail.versions.length === 0 && (
                <TableRow>
                  <TableCell
                    colSpan={5}
                    className="py-6 text-center text-muted-foreground"
                  >
                    Версий пока нет.
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Журнал изменений</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          {detail.audit.slice(0, 8).map((event) => (
            <div
              key={event.id}
              className="flex items-center justify-between gap-3 rounded-md border px-3 py-2 text-sm"
            >
              <div className="min-w-0">
                <div className="font-medium">{event.event_type}</div>
                <div className="text-xs text-muted-foreground">
                  {event.object_type} #{event.object_id}
                </div>
              </div>
              <div className="text-xs text-muted-foreground">
                {formatDateTime(event.created_at)}
              </div>
            </div>
          ))}
          {detail.audit.length === 0 && (
            <div className="text-sm text-muted-foreground">
              Событий пока нет.
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
