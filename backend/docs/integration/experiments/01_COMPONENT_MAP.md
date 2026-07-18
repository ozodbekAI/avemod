# Experiments Component Map

| Existing component | New role |
| --- | --- |
| `experiment_events` | Backward-compatible product change/event ledger. |
| `result_events` | Results surface for completed experiment evaluations. |
| Product 360 history | Shows legacy change events and result events. |
| Product 360 `experiments` block | Shows active experiments, latest results, recommendation, warnings, and last evaluation timestamp. |
| `mart_sku_daily` | Primary daily finance/orders/ads metric source. |
| `mart_stock_daily` | Stock guardrail metric source. |
| `wb_card_funnel_daily` | Funnel metric source when analytics data is synced. |
| scheduler registry | Daily due experiment evaluation job. |

New Finance-owned tables:

- `experiments`
- `experiment_interventions`
- `experiment_metric_snapshots`
- `experiment_evaluations`
- `experiment_settings`

New portal endpoints live under `/portal/experiments*`. Existing `/portal/experiments/events` remains as the legacy event ingestion endpoint.

