import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

export interface LoadingSkeletonProps {
  variant?: "card" | "list" | "table" | "drawer" | "page";
  rows?: number;
  className?: string;
}

/**
 * Единый скелетон-загрузчик для промежуточных состояний.
 * Без английских подписей — только визуальные плейсхолдеры.
 */
export function LoadingSkeleton({
  variant = "card",
  rows = 4,
  className,
}: LoadingSkeletonProps) {
  if (variant === "card") {
    return (
      <Card className={className} aria-busy="true">
        <CardHeader className="space-y-2">
          <Skeleton className="h-4 w-1/3" />
          <Skeleton className="h-3 w-2/3" />
        </CardHeader>
        <CardContent className="space-y-2">
          <Skeleton className="h-3 w-full" />
          <Skeleton className="h-3 w-5/6" />
          <Skeleton className="h-3 w-4/6" />
        </CardContent>
      </Card>
    );
  }

  if (variant === "list") {
    return (
      <div className={cn("space-y-2", className)} aria-busy="true">
        {Array.from({ length: rows }).map((_, i) => (
          <div
            key={i}
            className="flex items-center gap-3 rounded-md border p-3"
          >
            <Skeleton className="h-8 w-8 rounded-md shrink-0" />
            <div className="flex-1 space-y-1.5">
              <Skeleton className="h-3 w-1/2" />
              <Skeleton className="h-3 w-3/4" />
            </div>
            <Skeleton className="h-6 w-16 shrink-0" />
          </div>
        ))}
      </div>
    );
  }

  if (variant === "table") {
    return (
      <div
        className={cn("rounded-md border overflow-hidden", className)}
        aria-busy="true"
      >
        <div className="grid grid-cols-5 gap-2 border-b bg-muted/50 p-3">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-3 w-full" />
          ))}
        </div>
        {Array.from({ length: rows }).map((_, r) => (
          <div key={r} className="grid grid-cols-5 gap-2 border-b p-3 last:border-0">
            {Array.from({ length: 5 }).map((_, c) => (
              <Skeleton key={c} className="h-3 w-full" />
            ))}
          </div>
        ))}
      </div>
    );
  }

  if (variant === "drawer") {
    return (
      <div className={cn("space-y-4 p-2", className)} aria-busy="true">
        <Skeleton className="h-5 w-2/3" />
        <Skeleton className="h-3 w-full" />
        <Skeleton className="h-3 w-5/6" />
        <div className="pt-4 space-y-2">
          <Skeleton className="h-16 w-full rounded-md" />
          <Skeleton className="h-16 w-full rounded-md" />
        </div>
      </div>
    );
  }

  // page
  return (
    <div className={cn("space-y-4", className)} aria-busy="true">
      <div className="space-y-2">
        <Skeleton className="h-6 w-1/3" />
        <Skeleton className="h-3 w-1/2" />
      </div>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {Array.from({ length: 3 }).map((_, i) => (
          <LoadingSkeleton key={i} variant="card" />
        ))}
      </div>
      <LoadingSkeleton variant="list" rows={rows} />
    </div>
  );
}
