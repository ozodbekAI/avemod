import { Card, CardContent } from "@/components/ui/card";
import { formatMoney } from "@/lib/format";

export type ActionCenterImpactBucket<K extends string = string> = {
  key: K;
  label: string;
  tone: string;
};

export type ActionCenterImpactSummary<K extends string = string> = Record<
  K,
  { amount: number; count: number; hasMoney: boolean }
>;

export function ActionCenterTrustImpactSummary<K extends string>({
  buckets,
  summary,
}: {
  buckets: Array<ActionCenterImpactBucket<K>>;
  summary: ActionCenterImpactSummary<K>;
}) {
  return (
    <Card>
      <CardContent className="p-4 space-y-3">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div>
            <div className="text-sm font-semibold">
              Деньги и блокеры по уровню доверия
            </div>
            <div className="text-xs text-muted-foreground">
              Категории не складываются в один денежный результат: это разные
              типы риска, возможности и качества данных.
            </div>
          </div>
        </div>
        <div className="grid gap-2 md:grid-cols-2 xl:grid-cols-5">
          {buckets.map((bucket) => {
            const item = summary[bucket.key];
            return (
              <div
                key={bucket.key}
                className={`rounded-md border p-3 ${bucket.tone}`}
              >
                <div className="text-xs font-medium">{bucket.label}</div>
                <div className="mt-1 text-lg font-semibold tabular-nums">
                  {item.hasMoney ? formatMoney(item.amount) : "—"}
                </div>
                <div className="mt-1 text-[11px] opacity-80">
                  {item.count} задач
                </div>
              </div>
            );
          })}
        </div>
      </CardContent>
    </Card>
  );
}
