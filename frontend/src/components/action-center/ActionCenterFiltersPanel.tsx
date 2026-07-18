import { ChevronDown, ChevronUp, Search } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import type { PortalAssignableUser } from "@/lib/portal";
import type {
  ActionCenterFilterState,
  ActionCenterSortKey,
  ActionCenterView,
} from "@/lib/action-center-filters";
import { ActionCenterSavedViews, type ActionCenterSavedView } from "./ActionCenterSavedViews";

type FilterOption = {
  value: string;
  label: string;
};

type SortOption = {
  value: ActionCenterSortKey;
  label: string;
};

type ActionCenterFiltersPanelProps = {
  views: readonly ActionCenterSavedView[];
  deskFilter: ActionCenterView;
  deskFilterCounts: Record<ActionCenterView, number>;
  search: string;
  sortBy: ActionCenterSortKey;
  sortOptions: readonly SortOption[];
  advancedFiltersOpen: boolean;
  activeAdvancedFilterCount: number;
  statusFilter: string;
  statusOptions: readonly FilterOption[];
  sourceFilter: string;
  sourceOptions: readonly FilterOption[];
  severityFilter: string;
  severityOptions: readonly FilterOption[];
  priorityFilter: string;
  priorityOptions: readonly string[];
  priorityLabel: (value: string | null | undefined) => string;
  problemCodeFilter: string;
  problemCodeOptions: readonly FilterOption[];
  trustStateFilter: string;
  trustStateOptions: readonly FilterOption[];
  impactTypeFilter: string;
  impactTypeOptions: readonly FilterOption[];
  assigneeFilter: string;
  assigneeOptions: readonly FilterOption[];
  users?: PortalAssignableUser[];
  slaFilter: ActionCenterFilterState["sla"];
  slaOptions: readonly FilterOption[];
  resultStatusFilter: ActionCenterFilterState["result_status"];
  resultStatusOptions: readonly FilterOption[];
  canUseBeta: boolean;
  includeBeta: boolean;
  onAdvancedFiltersOpenChange: (open: boolean) => void;
  onUpdateFilterState: (patch: Partial<ActionCenterFilterState>) => void;
  onResetFilterState: () => void;
};

export function ActionCenterFiltersPanel({
  views,
  deskFilter,
  deskFilterCounts,
  search,
  sortBy,
  sortOptions,
  advancedFiltersOpen,
  activeAdvancedFilterCount,
  statusFilter,
  statusOptions,
  sourceFilter,
  sourceOptions,
  severityFilter,
  severityOptions,
  priorityFilter,
  priorityOptions,
  priorityLabel,
  problemCodeFilter,
  problemCodeOptions,
  trustStateFilter,
  trustStateOptions,
  impactTypeFilter,
  impactTypeOptions,
  assigneeFilter,
  assigneeOptions,
  users,
  slaFilter,
  slaOptions,
  resultStatusFilter,
  resultStatusOptions,
  canUseBeta,
  includeBeta,
  onAdvancedFiltersOpenChange,
  onUpdateFilterState,
  onResetFilterState,
}: ActionCenterFiltersPanelProps) {
  return (
    <Card>
      <CardContent className="p-3 space-y-3 sm:p-4">
        <div className="flex flex-col gap-3 xl:flex-row xl:items-center xl:justify-between">
          <ActionCenterSavedViews
            views={views}
            activeView={deskFilter}
            counts={deskFilterCounts}
            onViewChange={(view) => onUpdateFilterState({ view })}
          />
          <div className="grid min-w-0 flex-1 grid-cols-1 gap-2 md:grid-cols-[minmax(240px,1fr)_210px_auto] xl:max-w-4xl">
            <div className="relative min-w-0">
              <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
              <Input
                value={search}
                onChange={(event) => onUpdateFilterState({ q: event.target.value })}
                placeholder="Поиск: задача, рекомендация, nm_id, vendor, ответственный"
                className="min-h-10 pl-8 text-xs md:h-8 md:min-h-8"
              />
            </div>
            <Select
              value={sortBy}
              onValueChange={(value) =>
                onUpdateFilterState({ sort: value as ActionCenterSortKey })
              }
            >
              <SelectTrigger
                className="min-h-10 w-full text-xs md:h-8 md:min-h-8"
                aria-label="Сортировка"
              >
                <SelectValue placeholder="Сортировка" />
              </SelectTrigger>
              <SelectContent>
                {sortOptions.map((item) => (
                  <SelectItem key={item.value} value={item.value}>
                    {item.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Button
              size="sm"
              variant="outline"
              data-testid="action-center-filters-toggle"
              className="min-h-10 w-full justify-center md:h-8 md:min-h-8 md:w-auto"
              onClick={() => onAdvancedFiltersOpenChange(!advancedFiltersOpen)}
            >
              {advancedFiltersOpen ? (
                <ChevronUp className="mr-1 h-3.5 w-3.5" />
              ) : (
                <ChevronDown className="mr-1 h-3.5 w-3.5" />
              )}
              <span className="sm:hidden">Фильтры</span>
              <span className="hidden sm:inline">Расширенные фильтры</span>
              {activeAdvancedFilterCount > 0 ? (
                <span className="ml-1 rounded bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground">
                  {activeAdvancedFilterCount}
                </span>
              ) : null}
            </Button>
          </div>
        </div>

        {advancedFiltersOpen ? (
          <div
            data-testid="action-center-responsive-filters"
            className="grid gap-3 border-t pt-3 md:grid-cols-2 xl:grid-cols-4 2xl:grid-cols-6 [&_[role=combobox]]:min-h-10 [&_input]:min-h-10"
          >
            <Select
              value={statusFilter}
              onValueChange={(value) => onUpdateFilterState({ status: value })}
            >
              <SelectTrigger aria-label="Фильтр по статусу">
                <SelectValue placeholder="Статус" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Все статусы</SelectItem>
                {statusOptions.map((item) => (
                  <SelectItem key={item.value} value={item.value}>
                    {item.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select
              value={sourceFilter}
              onValueChange={(value) =>
                onUpdateFilterState({ source_module: value })
              }
            >
              <SelectTrigger aria-label="Фильтр по источнику">
                <SelectValue placeholder="Источник" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Все источники</SelectItem>
                {sourceOptions.map((item) => (
                  <SelectItem key={item.value} value={item.value}>
                    {item.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select
              value={severityFilter}
              onValueChange={(value) => onUpdateFilterState({ severity: value })}
            >
              <SelectTrigger aria-label="Фильтр по серьёзности">
                <SelectValue placeholder="Серьёзность" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Любая серьёзность</SelectItem>
                {severityOptions.map((item) => (
                  <SelectItem key={item.value} value={item.value}>
                    {item.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select
              value={priorityFilter}
              onValueChange={(value) => onUpdateFilterState({ priority: value })}
            >
              <SelectTrigger aria-label="Фильтр по приоритету">
                <SelectValue placeholder="Приоритет" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Все приоритеты</SelectItem>
                {priorityOptions.map((priority) => (
                  <SelectItem key={priority} value={priority}>
                    {priorityLabel(priority)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select
              value={problemCodeFilter}
              onValueChange={(value) =>
                onUpdateFilterState({ problem_code: value })
              }
            >
              <SelectTrigger aria-label="Фильтр по типу проблемы">
                <SelectValue placeholder="Проблема" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Все проблемы</SelectItem>
                {problemCodeOptions.map((item) => (
                  <SelectItem key={item.value} value={item.value}>
                    {item.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select
              value={trustStateFilter}
              onValueChange={(value) =>
                onUpdateFilterState({ trust_state: value })
              }
            >
              <SelectTrigger aria-label="Фильтр по доверию">
                <SelectValue placeholder="Доверие" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Любое доверие</SelectItem>
                {trustStateOptions
                  .filter((item) => canUseBeta || item.value !== "test_only")
                  .map((item) => (
                    <SelectItem key={item.value} value={item.value}>
                      {item.label}
                    </SelectItem>
                  ))}
              </SelectContent>
            </Select>
            <Select
              value={impactTypeFilter}
              onValueChange={(value) =>
                onUpdateFilterState({ impact_type: value })
              }
            >
              <SelectTrigger aria-label="Фильтр по эффекту">
                <SelectValue placeholder="Эффект" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Любой эффект</SelectItem>
                {impactTypeOptions.map((item) => (
                  <SelectItem key={item.value} value={item.value}>
                    {item.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select
              value={assigneeFilter}
              onValueChange={(value) => onUpdateFilterState({ assignee: value })}
            >
              <SelectTrigger aria-label="Фильтр по ответственному">
                <SelectValue placeholder="Ответственный" />
              </SelectTrigger>
              <SelectContent>
                {assigneeOptions.map((item) => (
                  <SelectItem key={item.value} value={item.value}>
                    {item.label}
                  </SelectItem>
                ))}
                {users?.map((user) => (
                  <SelectItem key={user.id} value={String(user.id)}>
                    {user.display_name || user.full_name || user.email}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select
              value={slaFilter}
              onValueChange={(value) =>
                onUpdateFilterState({
                  sla: value as ActionCenterFilterState["sla"],
                })
              }
            >
              <SelectTrigger aria-label="Фильтр по сроку">
                <SelectValue placeholder="Срок" />
              </SelectTrigger>
              <SelectContent>
                {slaOptions.map((item) => (
                  <SelectItem key={item.value} value={item.value}>
                    {item.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select
              value={resultStatusFilter}
              onValueChange={(value) =>
                onUpdateFilterState({
                  result_status: value as ActionCenterFilterState["result_status"],
                })
              }
            >
              <SelectTrigger aria-label="Фильтр по результату">
                <SelectValue placeholder="Результат" />
              </SelectTrigger>
              <SelectContent>
                {resultStatusOptions.map((item) => (
                  <SelectItem key={item.value} value={item.value}>
                    {item.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {canUseBeta && (
              <label className="flex items-center justify-between gap-2 rounded-md border px-3 py-2 text-xs">
                <span className="whitespace-nowrap">
                  Показать бета/тестовые сигналы
                </span>
                <Switch
                  checked={includeBeta}
                  onCheckedChange={(checked) =>
                    onUpdateFilterState({ include_beta: checked })
                  }
                />
              </label>
            )}
            <Button
              size="sm"
              variant="outline"
              className="h-10"
              onClick={onResetFilterState}
            >
              Сбросить
            </Button>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}
