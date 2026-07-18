# Grouping Beta Reality Audit

Date: 2026-06-23

## Current Finance State

- Finance owns auth, account scoping, product-card storage, portal aggregation, module health, Action Center, and Product 360.
- Existing `/portal/products/{nm_id}/grouping` and `/portal/grouping/preview` contracts are preserved.
- The previous `GroupingAdapter` remains a safe external-service fallback, but local mode no longer requires `GROUPING_BASE_URL`.
- Local Grouping Beta now reads Finance `wb_product_cards`, card characteristics, and card sizes as source of truth.

## Legacy Grouping Source

Reference archive: `_incoming_projects/groupingbackend.zip`.

Useful legacy concepts reviewed:

- `engine/core.py`: `article_core`, `article_base_core`, `imt_id_core`, `ranking_core`.
- `engine/constraints.py`: diversity and compatibility constraints.
- `engine/scoring.py`: similarity, stock/sales/novelty/manual weighting concepts.
- `engine/recommendations*.py`: recommendation payload shape and dry-run recommendation behavior.

Rejected legacy pieces:

- separate auth and product database;
- destructive product sync;
- `merge-wb`;
- public mutation endpoints outside Finance portal/account checks.

## Implemented Local Increment

- Added local persistence for settings, runs, snapshots, candidates, recommendations, review history, and export artifact metadata.
- `POST /portal/grouping/preview` runs a local read-only analysis and persists candidate groups.
- `GET /portal/products/{nm_id}/grouping` reads the latest local candidate state.
- `PATCH /portal/grouping/candidates/{candidate_id}/status` stores local review state only.
- Action Center can surface persisted local grouping candidates.
- Module health can report local grouping mode without external env configuration.

## Remaining Gaps

- No WB merge/apply exists by design.
- The local MVP algorithm uses deterministic article-base and `imt_id` blocking; deeper legacy ranking/rebalance is not fully ported yet.
- Export artifact content storage is modeled but not exposed as a download endpoint in this increment.
- Advanced finance effect modeling is intentionally not claimed.
