# Experiments Reality Audit

Date: 2026-06-23

Finance already had a minimal experiment/change ledger:

- `experiment_events` stores product change notes with `before_json`, `after_json`, `changed_at`, `account_id`, and `nm_id`.
- `result_events` is the existing Results ledger used by Action Center, Product 360 history, claims, reputation, grouping, and stock flows.
- `/portal/products/{nm_id}/events`, `/portal/experiments/events`, and `/portal/results` already expose event/history surfaces.

The old ledger was not a full experiment system. It did not have experiment definitions, frozen baseline snapshots, intervention records, post-window snapshots, evaluation records, settings, progress, or scheduler processing.

Available real metric sources:

- `mart_sku_daily`: revenue, for-pay, estimated profit, margin, orders, sales, returns, WB expenses, ads spend/clicks/views, stock fields copied into SKU mart.
- `mart_stock_daily`: stock quantity and days-of-stock guardrails.
- `wb_card_funnel_daily`: product views, carts, orders, and funnel conversion.
- `result_events`: outcome surface, not a metric source by itself.

Constraints confirmed:

- No frontend repo is present here, so UI call-site compliance must be audited separately.
- No real controlled split assignment table exists; `controlled_split` must remain `not_supported` until real variant assignment and variant metrics exist.
- Marketplace-changing operations remain outside this module. Experiments only record local Finance state and observations.

