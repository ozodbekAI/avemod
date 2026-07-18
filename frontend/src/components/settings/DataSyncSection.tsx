import { DataCoveragePanel } from "@/components/data-health/DataCoveragePanel";

export function DataSyncSection({ accountId }: { accountId: number | null }) {
  return (
    <DataCoveragePanel
      accountId={accountId}
      title="Data Coverage"
      description="Какие WB источники подключены, свежие ли данные, хватает ли прав токена и что делать дальше."
    />
  );
}
