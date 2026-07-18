# Data Readiness and Sync Status Contract

These portal endpoints are the source of truth for seller-facing data readiness. Frontend screens must not infer freshness from empty UI state.

## GET `/api/v1/portal/data-readiness`

Required query:

- `account_id`

Optional query:

- `date_from`
- `date_to`

The response contains high-level readiness plus `sources[]`. Each source reports whether data is usable for Money, Data Fix, Action Center, Product360, Settings, Checker, and the problem engine.

`sources[]` item contract:

- `source_code`
- `title`
- `status`: `fresh`, `stale`, `missing`, `not_configured`, or `error`
- `last_synced_at`
- `freshness_minutes`
- `freshness_hours`
- `required_for[]`
- `blocks_calculation[]`
- `missing_reason`
- `next_action_code`
- `next_action_label`
- `target_href`

Implemented source codes:

- `finance_reports_wb`
- `sales_orders`
- `product_cards_content`
- `stocks`
- `prices`
- `ads`
- `manual_costs`
- `expenses`
- `documents`
- `checker_card_quality`
- `data_fix`
- `problem_engine`

Rules:

- `fresh` means the backend found a successful sync/local signal and it is inside the freshness window where applicable.
- `stale` means data exists but is older than the configured freshness window.
- `missing` means the source is configured or local, but data is not available.
- `not_configured` means a required token/module/rule setup is missing.
- `error` means the latest relevant sync failed.
- If a source is not `fresh`, `blocks_calculation[]` tells the frontend which calculations must be treated as blocked or provisional.

## GET `/api/v1/portal/data-sync/status`

Required query:

- `account_id`

The response keeps legacy `domains[]` and adds frontend-facing status fields:

- `user_facing_status`
- `sources[]`
- `current_sync_runs[]`
- `last_successful_sync_by_source`
- `failed_syncs[]`
- `queued_syncs[]`
- `active_sync_progress[]`

Allowed user-facing status text:

- `Синхронизация идёт`
- `Данные свежие`
- `Нужна синхронизация`
- `Ошибка синхронизации`
- `Источник не настроен`

`domains[]` remains useful for technical drill-down. Each domain now also includes:

- `source_code`
- `title`
- `source_status`
- `user_facing_status`
- `freshness_minutes`
- `freshness_hours`
- `missing_reason`
- `blocks_calculation[]`
- `next_action_code`
- `next_action_label`
- `target_href`

## Non-Faking Policy

The backend must never report missing data as confirmed or fresh. If no successful sync, cursor, raw response, local source row, or active problem-rule setup exists, the status must be `missing` or `not_configured`.
