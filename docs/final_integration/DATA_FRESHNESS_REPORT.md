# Data Freshness Report

Generated as a static/runtime-gated report on 2026-06-25.

## Runtime Status

This pass did not connect to the production/staging PostgreSQL database and did not call WB APIs. Real row counts, latest dates, and account coverage remain runtime-gated.

Static verification completed:

- sync routes exist;
- sync runs and cursors exist;
- scheduler jobs exist for major WB domains;
- rate-limit observations are captured into run details;
- raw WB responses are stored through `RawResponseService`;
- stale running cursors/runs are reset before new sync attempts;
- manual HTTP sync lifecycle was corrected to `POST -> 202 queued run -> worker/background processor -> GET status`.

## Freshness Matrix

| Domain | Expected Scheduler | Cursor Support | Run Support | Rate Limit Evidence | Runtime Freshness |
| --- | --- | --- | --- | --- | --- |
| product_cards | daily 01:00 | yes | yes | via `DomainSyncBase.runtime_details()` | needs DB query |
| prices | 02:00, 14:00 | yes | yes | via runtime details | needs DB query |
| orders | every 30 min | yes | yes | via runtime details | needs DB query |
| sales | every 30 min | yes | yes | via runtime details | needs DB query |
| stocks | every 3 hours | yes | yes | via runtime details | needs DB query |
| finance | daily 03:00 | yes | yes | via runtime details | needs DB query |
| supplies | every 30 min | yes | yes | via runtime details | needs DB query |
| ads | 06:00, 12:00, 18:00 | yes | yes | fullstats interval and WB retry tracking | needs DB query |
| analytics | every 2 hours | yes | yes | via runtime details | needs DB query |
| tariffs | daily 05:00 | yes | yes | via runtime details | needs DB query |
| documents | daily 07:00 | yes | yes | via runtime details | needs DB query |
| reputation | every 2 hours at minute 20 | module-local | module-local | adapter/service dependent | needs DB query |
| data_quality | daily 08:30 | n/a | service run | n/a | needs DB query |
| marts | daily 08:15 | n/a | service run | n/a | needs DB query |
| money/operator snapshots | every 10 min | n/a | service run | n/a | needs DB query |

## SQL Runtime Checklist

Run these against the configured Finance PostgreSQL database with sensitive values suppressed.

```sql
select id, name, is_active from wb_accounts order by id;

select account_id, category, is_active, created_at, updated_at
from wb_api_tokens
order by account_id, category;

select account_id, domain, status, max(started_at) as latest_started_at, max(finished_at) as latest_finished_at
from wb_sync_runs
group by account_id, domain, status
order by account_id, domain, status;

select account_id, domain, cursor_key, status, last_synced_at, updated_at
from wb_sync_cursors
order by account_id, domain, cursor_key;
```

For each domain table, collect row counts by account and latest source date. Use domain-specific timestamp/date columns rather than `created_at` when possible.

## Freshness Acceptance

A source can be marked fresh only when:

- latest successful run is within the domain SLA;
- cursor is not stale/running beyond `SYNC_RUNNING_CURSOR_STALE_HOURS`;
- row count is non-zero when the account is expected to have data;
- latest source date is plausible for WB reporting latency;
- no blocking DQ issue exists for the same domain/account;
- optional rate-limit failures are either resolved or explicitly treated as non-blocking with last successful data.

## Current Gaps

- Real row counts not collected in this pass.
- Latest business dates not collected in this pass.
- Account coverage not collected in this pass.
- WB token category coverage not collected in this pass.
- Runtime proof for queued manual sync requires a configured database and at least one active account/token.
