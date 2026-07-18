import type { ReactNode } from "react";
import { ChevronDown, ChevronUp, Wrench } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { formatMoney } from "@/lib/format";
import type { ActionCenterItem } from "@/lib/action-center-contract";
import type { ActionCenterGroup } from "@/lib/action-center-view-utils";
import { problemCodeLabel } from "@/lib/problem-ux-copy";

type ActionCenterRowProps = {
  action: ActionCenterItem;
  index: number;
  parentKey: string;
  renderRow: (
    action: ActionCenterItem,
    index: number,
    parentKey: string,
  ) => ReactNode;
};

export function ActionCenterRow({
  action,
  index,
  parentKey,
  renderRow,
}: ActionCenterRowProps) {
  return <>{renderRow(action, index, parentKey)}</>;
}

type ActionCenterListProps = {
  groups: ActionCenterGroup[];
  expanded: Record<string, boolean>;
  onToggleGroup: (groupKey: string, open: boolean) => void;
  renderRow: (
    action: ActionCenterItem,
    index: number,
    parentKey: string,
  ) => ReactNode;
  priorityClassName: (priority: string | null | undefined) => string;
  priorityLabel: (priority: string | null | undefined) => string;
  sourceModuleLabel: (sourceModule: string | null | undefined) => string;
  isBetaAction: (action: ActionCenterItem) => boolean;
  groupFixLabel?: (group: ActionCenterGroup) => string | null;
  onFixGroup?: (group: ActionCenterGroup) => void;
};

export function ActionCenterList({
  groups,
  expanded,
  onToggleGroup,
  renderRow,
  priorityClassName,
  priorityLabel,
  sourceModuleLabel,
  isBetaAction,
  groupFixLabel,
  onFixGroup,
}: ActionCenterListProps) {
  return (
    <div className="space-y-3">
      {groups.map((group) => {
        const head = group.items[0];
        if (!head) return null;
        const count = group.items.length;
        const isOpen = expanded[group.key] ?? count === 1;
        const fixLabel = groupFixLabel?.(group) ?? null;
        if (count === 1) {
          return (
            <ActionCenterRow
              key={group.key}
              action={head}
              index={0}
              parentKey={group.key}
              renderRow={renderRow}
            />
          );
        }
        return (
          <Card key={group.key}>
            <CardContent className="p-4 space-y-3">
              <div className="flex items-start justify-between gap-3 flex-wrap">
                <div className="flex items-center gap-2 flex-wrap min-w-0">
                  {head.priority && (
                    <Badge
                      variant="outline"
                      className={priorityClassName(head.priority)}
                    >
                      {priorityLabel(head.priority)}
                    </Badge>
                  )}
                  {count > 1 && (
                    <Badge variant="secondary" className="text-[10px]">
                      ×{count}
                    </Badge>
                  )}
                </div>
                {count > 1 && (
                  <div className="flex flex-wrap items-center gap-2">
                    {fixLabel && onFixGroup ? (
                      <Button
                        size="sm"
                        className="h-8 text-xs"
                        onClick={() => onFixGroup(group)}
                      >
                        <Wrench className="mr-1 h-3.5 w-3.5" />
                        {fixLabel}
                      </Button>
                    ) : null}
                    <Button
                      size="sm"
                      variant="ghost"
                      className="h-7 text-xs"
                      onClick={() => onToggleGroup(group.key, !isOpen)}
                    >
                      {isOpen ? (
                        <>
                          Свернуть <ChevronUp className="h-3 w-3 ml-1" />
                        </>
                      ) : (
                        <>
                          Раскрыть <ChevronDown className="h-3 w-3 ml-1" />
                        </>
                      )}
                    </Button>
                  </div>
                )}
              </div>

              <div>
                <div className="font-medium text-sm">
                  {group.problem_code
                    ? problemCodeLabel(group.problem_code)
                    : head.title ?? "Задача"}
                </div>
                <div className="text-xs text-muted-foreground mt-1">
                  {count} товар(ов) требуют одного действия
                  {group.total_impact_amount != null
                    ? ` · ${formatMoney(group.total_impact_amount)}`
                    : ""}
                </div>
              </div>

              {isOpen ? (
                <div className="space-y-2">
                  {group.items.map((action, index) => (
                    <ActionCenterRow
                      key={`${group.key}-${index}`}
                      action={action}
                      index={index}
                      parentKey={group.key}
                      renderRow={renderRow}
                    />
                  ))}
                </div>
              ) : (
                <div className="text-xs text-muted-foreground">
                  Откройте группу, чтобы посмотреть товары.
                </div>
              )}
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}
