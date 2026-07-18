# DB Data Quality Report

Generated as a static/runtime-gated report on 2026-06-25.

## Static Findings

Implemented safeguards discovered:

- `DataQualityService` exists and is scheduled daily.
- Sync failures can open scheduler DQ issues.
- Stale running sync state is reset before a new attempt.
- Raw WB API responses are stored with success/failure, status code, retry count, timestamps, response headers, and error text.
- Sync response schemas scrub sensitive cursor/run details.
- Money/dashboard services consume sync status and DQ signals when computing trust/blockers.

Fixed in this pass:

- Manual sync and backfill no longer run heavy WB sync inline in HTTP routes.
- `/sync/trigger` and `/sync/backfill` now return `202 Accepted` with a queued run.
- Queued runs are processed by a background task and by the scheduler fallback.

## Runtime DQ Checklist

For each account and source, verify:

- row count;
- latest source date;
- latest loaded date;
- last successful sync;
- failed sync domains;
- duplicate natural keys;
- orphan rows missing account/product/report parents;
- unmatched rows between product cards, SKU/marts, reports, orders/sales, stocks, costs;
- stale cursors;
- rate-limit count and retry-after observations;
- required field null counts;
- DQ issues open/closed by domain.

## Domain-Specific Checks

| Domain | DQ Checks |
| --- | --- |
| accounts/tokens | active account has required token categories; no token values exposed in query output |
| product_cards | unique `(account_id, nm_id)`; required title/vendor/category fields; sizes/characteristics present where expected |
| orders | duplicate WB order IDs; date range continuity; account/product references |
| sales/returns | duplicate sale IDs; returns represented; sales link to known products where possible |
| finance reports | report row uniqueness; operation type coverage; latest report period; reconciliation against marts |
| ads | campaign IDs unique; stats date coverage; ad item/product matching |
| stocks | latest snapshot age; warehouse/product matching; no negative impossible quantities unless WB source says so |
| supplies | supply IDs unique; goods rows linked; acceptance/discrepancy data present where expected |
| analytics | funnel/region dates present; region keys normalized |
| costs | missing active product costs; placeholder cost count; supplier-confirmed coverage |
| marts | mart row counts by date/account; stale mart refresh; reconciliation deltas |
| actions/results | actions linked to source signals where possible; result events account-scoped |

## Acceptance States

Use these states in follow-up runtime evidence:

- `pass`: verified with real DB query and no blocking issue.
- `warning`: data exists but is stale/partial/non-blocking.
- `blocked`: missing credentials, missing DB, or no active account.
- `fail`: query proves missing, duplicate, orphan, unsafe exposure, or stale data beyond SLA.

## Required Evidence Bundle Inputs

For final audit ZIP, include sanitized:

- source catalog;
- freshness table by account/domain;
- DQ issue summary by domain/severity/status;
- sync run and cursor summary;
- row-count and latest-date summary;
- unmatched/duplicate/orphan summaries;
- runtime endpoint smoke results.

Do not include:

- raw `.env`;
- decrypted WB tokens;
- authorization headers;
- raw DB dumps;
- buyer PII;
- raw WB payloads with sensitive fields.
