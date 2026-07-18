# Dynamic Problem Engine Completion Audit

Date: 2026-07-07

## Result

The Dynamic Problem Engine rollout is implemented and re-verified across backend
and frontend. The remaining gap found during this audit was that four designed
problem codes were present in docs/frontend mappings but were not fully seeded
as active backend dynamic rules. That gap is now closed.

## Gap Closed In This Pass

| Gap | Resolution |
| --- | --- |
| `promo_not_profitable` missing as seeded dynamic rule | Added service seed, Alembic seed migration, evaluator tests, evidence coverage, and rollout docs. |
| `price_below_safe_margin` missing as seeded dynamic rule | Added service seed, Alembic seed migration, evaluator tests, price-safety target-price coverage, and rollout docs. |
| `dead_stock` missing as seeded dynamic rule | Added service seed, Alembic seed migration, evaluator tests, evidence coverage, and price-safety guard for liquidation/promo action. |
| `fast_stock_depletion` missing as seeded dynamic rule | Added service seed, Alembic seed migration, evaluator tests, evidence coverage, and rollout docs. |

## Prompt Checklist

| Area | Status | Evidence |
| --- | --- | --- |
| Baseline inventory before refactor | Done | `docs/dynamic_problem_engine_inventory.md` and legacy migration map document existing sources, APIs, UI, and hardcoded areas. |
| Target architecture document | Done | `docs/dynamic_problem_engine.md` defines concepts, statuses, trust states, impact types, safety rules, and first problem codes. |
| DB models and migrations | Done | Migrations `20260706_000056` through `20260706_000061`; DB current revision verified at `20260706_000061 (head)`. |
| Safe formula engine | Done | `FormulaEvaluator` plus unit coverage for operators, missing metrics, and unsafe input rejection. |
| Metric catalog and resolver | Done | `MetricCatalogService`, `ProductMetricResolver`, seeded metrics, and tests. |
| Evidence ledger contract | Done | `EvidenceLedgerBuilder`, `EvidenceDrawer`, and backend/frontend evidence coverage. |
| Dynamic evaluator | Done | `ProblemEvaluatorService` handles create/update/dedup/preserve/resolve/test mode. |
| Seeded product/business rules | Done | Nine seeded codes: `missing_cost_blocks_profit`, `negative_unit_profit`, `overstock_slow_moving`, `low_stock_risk`, `ads_spend_without_profit`, `promo_not_profitable`, `price_below_safe_margin`, `dead_stock`, `fast_stock_depletion`. |
| Action Center integration | Done | Dynamic instances are surfaced as canonical actions; status updates write back to `problem_instances`. |
| Product360/Product Doctor | Done | Product Doctor groups dynamic issues and opens evidence. |
| Admin APIs | Done | Admin rule CRUD/validate/backtest/publish/pause/archive/evaluate endpoints are implemented with RBAC tests. |
| Admin UI | Done | `ProblemRulesAdminPanel` supports definition editing, formula builder, evidence editor, backtest, and lifecycle controls. |
| Data Fix integration | Done | `DataFixProblemBridge` mirrors selected DQ blockers into dynamic instances with fix metadata and evidence. |
| Price/promo safety | Done | `PriceSafetyCalculator` blocks unsafe price decreases and computes target prices; this pass extends the guard to `dead_stock`. |
| Automatic/scheduled evaluation | Done | `ProblemEvaluationRunnerService`, run logs, sync hooks, admin manual trigger, and portal re-check endpoint are present. |
| Seller UX consistency | Done | `SellerProblemUX`, `EvidenceDrawer`, Product Doctor, Action Center, and Data Fix workbench surface badges, allowed actions, evidence, and empty states. |
| Legacy migration/fallback | Done | Feature flags and duplicate suppression are documented; dynamic problems take precedence. |
| Product-level acceptance tests | Done | Acceptance and unit suites cover missing cost, negative profit, overstock, low stock, Action Center, re-check, admin publish, Data Fix bridge, and the remaining seeded rules. |
| Final rollout report | Done | `docs/dynamic_problem_engine_rollout_report.md` updated with migration `000061`, nine rules, verification results, limitations, and next rules. |

## Verification

- `backend/.venv/bin/python -m py_compile ...`
  - passed
- `cd backend && .venv/bin/alembic upgrade head && .venv/bin/alembic current`
  - migration applied cleanly; current revision is `20260706_000061 (head)`
- `backend/.venv/bin/pytest ...dynamic problem engine suites... -q`
  - `100 passed, 1 warning`
- `backend/.venv/bin/ruff check ...`
  - passed
- `cd frontend && npm run test:contracts`
  - `10/10` endpoint schemas OK
- `cd frontend && npm run build`
  - passed
  - known warning: one client chunk is larger than 500 kB

## Known Remaining Limits

- Evaluator is still product-focused; account/campaign/warehouse/category grains
  are schema-ready but not fully operational.
- Data Fix bridge covers key blockers, but not every historical DQ text card is
  formula-defined yet.
- Checker/card-quality issue generation remains its own workflow until metric
  and evidence normalization are designed for it.
- Legacy generators remain as fallback behind feature flags and duplicate
  suppression.
- Frontend build still reports the existing large chunk warning.
