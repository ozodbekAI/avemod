# WB Data Source Catalog

Generated from Section 02 discovery on 2026-06-25.

## Source Of Truth Rule

Primary source is Finance PostgreSQL. WB API should be called only when:

- data is missing;
- sync is stale;
- current sync logic needs verification.

Token rule:

- use existing encrypted WB token infrastructure;
- never expose decrypted tokens to frontend, logs, docs, audit ZIPs, or smoke output.

## Sync Infrastructure

Core files:

- `backend/app/core/wb_sync.py`: shared WB sync base, token lookup, raw response storage, rate-limit observation.
- `backend/app/core/http.py`: WB HTTP client with retry/rate-limit behavior.
- `backend/app/services/sync.py`: sync orchestrator, runs, cursors, stale-running reset, advisory locks.
- `backend/app/modules/sync/router.py`: RBAC-protected sync API.
- `backend/app/jobs/sync_jobs.py`: scheduled and queued sync processors.
- `backend/app/jobs/registry.py`: scheduler job registration.
- `backend/app/models/sync.py`: `wb_sync_cursors`, `wb_sync_runs`.
- `backend/app/services/raw.py`: stores sanitized/raw WB response snapshots in DB.

## Domain Catalog

| Source | Local Tables/Models | Sync Domain | WB API Category | Route/Worker | Current Evidence |
| --- | --- | --- | --- | --- | --- |
| Accounts | `WBAccount` | n/a | n/a | `/accounts` | Account service/router exists |
| WB tokens | `WBAPIToken` | n/a | per token category | `/accounts/{id}/tokens` | Encrypted token service exists |
| Product cards | `WBProductCard` and related product card models | `product_cards` | content | `/sync/trigger`, scheduler `sync-product-cards` | Sync client/service exists |
| Characteristics/sizes | Product card payload/model fields | `product_cards` | content | same as product cards | Needs row-level runtime proof |
| Orders | `WBOrder` | `orders` | statistics | `/sync/trigger`, scheduler `sync-orders` | Sync client/service exists |
| Sales/returns | `WBSale` | `sales` | statistics | `/sync/trigger`, scheduler `sync-sales` | Sync client/service exists |
| Realization reports | finance realization report models | `finance` | statistics/finance | `/sync/trigger`, scheduler `sync-finance` | Sync client/service exists |
| Ads | ad campaign/stats models | `ads` | promotion | `/sync/trigger`, scheduler `sync-ads` | Sync client/service exists; long fullstats interval noted |
| Stock snapshots | stock snapshot models | `stocks` | statistics | `/sync/trigger`, scheduler `sync-stocks` | Sync client/service exists |
| Supplies | supply models | `supplies` | marketplace/statistics | `/sync/trigger`, scheduler `sync-supplies` | Sync client/service exists |
| Supply goods | supply payload/models | `supplies` | marketplace/statistics | same as supplies | Needs row-level runtime proof |
| Warehouse/region data | analytics/stock/supply/marts | `analytics`, `stocks`, `supplies` | analytics/statistics | scheduler jobs exist | Needs runtime proof |
| Prices | price models | `prices` | content/prices | scheduler `sync-prices` | Sync client/service exists |
| Analytics | funnel/region models | `analytics` | analytics | scheduler `sync-analytics` | Sync client/service exists |
| Tariffs | tariff models | `tariffs` | common/statistics | scheduler `sync-tariffs` | Sync client/service exists |
| Documents | document models | `documents` | documents | scheduler `sync-documents` | Sync client/service exists |
| Reviews/questions/chats | reputation models | local reputation sync | content/feedback | scheduler `sync-local-reputation` | Finance-owned local module exists |
| Costs | manual cost models | manual upload/import | n/a | `/costs/*` | Finance-owned; not WB sync |
| DQ issues | `DataQualityIssue` | DQ service | n/a | `/dq/run`, scheduler `run-data-quality` | Finance-owned |
| Marts | mart models | mart refresh | n/a | `/marts/refresh`, scheduler `refresh-marts` | Finance-owned derived data |
| Actions | operator/control tower models | operator services | n/a | `/portal/actions` | Finance-owned derived data |
| Results | `ResultEvent` | result tracking service | n/a | `/portal/results` | Finance-owned derived data |

## Lifecycle Finding

Before this pass, `/sync/trigger` and `/sync/backfill` executed sync inline in the HTTP request.

Fixed in this pass:

- manual trigger/backfill now enqueue `WBSyncRun` with `status=queued`;
- endpoints return `202 Accepted`;
- a background task starts processing the queued run;
- scheduler also processes queued runs every minute via `process-queued-wb-sync-runs`.

Scheduled domain sync still uses the existing inline orchestrator path inside the scheduler job, which is acceptable because it is not running inside an HTTP request.

## Required Runtime Columns

For every source above, collect:

- row count;
- latest business date;
- latest loaded/synced timestamp;
- latest successful sync run;
- cursor status and cursor age;
- account coverage;
- missing required fields;
- duplicate keys;
- orphan rows;
- unmatched rows;
- stale status against expected sync frequency.
