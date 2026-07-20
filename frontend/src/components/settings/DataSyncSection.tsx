import { DataCoveragePanel } from "@/components/data-health/DataCoveragePanel";

export function DataSyncSection({ accountId }: { accountId: number | null }) {
  return (
    <DataCoveragePanel
      accountId={accountId}
      title="Покрытие данных"
      description="Какие источники Вайлдберриз подключены, свежие ли данные, хватает ли прав токена и что делать дальше."
    />
  );
}
