import { Button } from "@/components/ui/button";
import type { ActionCenterView } from "@/lib/action-center-filters";

export type ActionCenterSavedView = {
  value: ActionCenterView;
  label: string;
};

type ActionCenterSavedViewsProps = {
  views: readonly ActionCenterSavedView[];
  activeView: ActionCenterView;
  counts: Record<ActionCenterView, number>;
  onViewChange: (view: ActionCenterView) => void;
};

export function ActionCenterSavedViews({
  views,
  activeView,
  counts,
  onViewChange,
}: ActionCenterSavedViewsProps) {
  return (
    <div
      className="flex max-w-full gap-1 overflow-x-auto rounded-md bg-muted/50 p-1 md:flex-wrap"
      aria-label="Быстрые фильтры"
    >
      {views.map((filter) => (
        <Button
          key={filter.value}
          size="sm"
          variant={activeView === filter.value ? "default" : "ghost"}
          className="h-9 shrink-0 gap-1 whitespace-nowrap text-xs md:h-8"
          onClick={() => onViewChange(filter.value)}
        >
          {filter.label}
          <span className="rounded bg-background/80 px-1.5 py-0.5 text-[10px] text-muted-foreground">
            {counts[filter.value] ?? 0}
          </span>
        </Button>
      ))}
    </div>
  );
}
