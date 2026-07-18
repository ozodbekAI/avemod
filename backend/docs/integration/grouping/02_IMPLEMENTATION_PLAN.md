# Grouping Beta Implementation Plan

## Completed In This Increment

1. Add finance-owned grouping tables and migration.
2. Add local normalization and deterministic candidate generation.
3. Persist run snapshots and candidates from Finance product cards.
4. Preserve existing portal grouping contracts.
5. Add local candidate review status endpoint.
6. Add Action Center and module-health integration.
7. Add unit/API regression coverage for the new behavior.

## Next Steps

1. Add list/detail endpoints for grouping runs and candidates.
2. Add export endpoint for merge-preview JSON/XLSX payloads.
3. Port more legacy ranking/rebalance logic where it remains read-only and evidence-based.
4. Add source freshness and performance metrics for large accounts.
5. Add Product 360 UI wiring against the existing Finance portal endpoint.

## Non-Goals

- No WB merge.
- No automatic card mutation.
- No expected money effect unless a measured model is added later.
