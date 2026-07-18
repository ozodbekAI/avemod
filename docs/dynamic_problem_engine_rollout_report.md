# Dynamic Problem Engine Rollout Report

Date: 2026-07-07

## Executive Summary

The Dynamic Problem Engine is implemented as a controlled replacement path for
hardcoded product/business alert cards. It stores metric definitions, problem
definitions, versioned safe formulas, generated problem instances, evidence
ledgers, action-center lifecycle status, admin backtests, admin audit records,
and evaluation run logs.

The current rollout is deliberately gradual:

- dynamic problems are canonical when present;
- mapped legacy cards remain as fallback while the rollout flag allows them;
- generated issues carry evidence and can be rechecked;
- price/promo recommendations are bounded by unit economics;
- admin-created rules remain draft/test-only until validated, backtested, and
  published.

## Implemented Architecture

Flow:

1. `metric_catalog` defines approved metrics and source references.
2. `ProductMetricResolver` resolves requested product metrics from existing
   marts/services and reports missing data explicitly.
3. `FormulaEvaluator` evaluates JSONLogic-style formulas with whitelisted
   operators only.
4. `ProblemEvaluatorService` loads active rule versions, resolves metrics,
   evaluates conditions, computes impact/severity/confidence, renders templates,
   applies price-safety checks, builds evidence, and upserts
   `problem_instances` by dedup key.
5. `EvidenceLedgerBuilder` records formula, input facts, source references,
   missing data, trust notes, re-check rule, and calculation warnings.
6. `ProblemEvaluationRunnerService` runs evaluation after sync/import, nightly,
   manually from admin, or from seller re-check.
7. `PortalService` exposes dynamic instances as normal Action Center/Product360
   actions and keeps `problem_instances.status` canonical.
8. Frontend surfaces dynamic problems in Action Center, Product Doctor,
   Data Fix, and reusable seller problem cards with an evidence drawer.

Safety rules implemented:

- no raw SQL or Python `eval`;
- unknown formula operators and unknown metrics are rejected;
- only catalog metrics and whitelisted actions are allowed;
- generated problem instances require evidence;
- missing cost blocks negative-profit evaluation;
- price decrease/promo suggestions are blocked when `min_safe_price` would be
  violated or required cost/fee data is missing.

## DB Migrations

| Revision | File | Purpose |
| --- | --- | --- |
| `20260706_000056` | `backend/alembic/versions/20260706_000056_dynamic_problem_engine.py` | Adds `metric_catalog`, `problem_definitions`, `problem_rule_versions`, `problem_instances`, `problem_instance_history`, `admin_rule_test_runs`, indexes, and uniqueness constraints. |
| `20260706_000057` | `backend/alembic/versions/20260706_000057_seed_dynamic_problem_metrics.py` | Seeds initial metric catalog rows. |
| `20260706_000058` | `backend/alembic/versions/20260706_000058_seed_initial_dynamic_problem_rules.py` | Seeds the first five dynamic problem definitions and active rule versions. |
| `20260706_000059` | `backend/alembic/versions/20260706_000059_problem_rule_admin_audit.py` | Adds `problem_rule_admin_audit` for admin create/update/backtest/publish/pause/archive history. |
| `20260706_000060` | `backend/alembic/versions/20260706_000060_problem_evaluation_run_logs.py` | Adds `problem_evaluation_run_logs` for scheduled/manual/re-check run accounting. |
| `20260706_000061` | `backend/alembic/versions/20260706_000061_seed_remaining_dynamic_problem_rules.py` | Seeds `promo_not_profitable`, `price_below_safe_margin`, `dead_stock`, and `fast_stock_depletion` definitions/rules. |

Important constraints/indexes:

- `metric_catalog.metric_code` unique.
- `problem_definitions.problem_code` unique.
- `problem_rule_versions(problem_definition_id, version)` unique.
- `problem_instances(account_id, problem_code, entity_type, entity_id, dedup_key)`
  unique.
- Action Center filters use indexes on account/status, account/problem code,
  dedup key, severity, impact type, trust state, and timestamps.

## New Backend Services

| Service | Responsibility |
| --- | --- |
| `FormulaEvaluator` | Safe expression evaluation for conditions and numeric/string formulas. Supports `and`, `or`, `not`, comparisons, arithmetic, `max`, `min`, `abs`, `round`, `coalesce`, `missing`, `case`, `in`, `between`, and `percent_change`. |
| `MetricCatalogService` | Seeds, lists, and validates allowed metrics. |
| `ProductMetricResolver` | Resolves product-level metrics from marts/prices/ads/funnel/manual-cost sources and returns value plus evidence or missing diagnostics. |
| `EvidenceLedgerBuilder` | Builds required `evidence_ledger_json`. |
| `ProblemEvaluatorService` | Converts active rule versions into persisted or preview problem instances. |
| `ProblemTemplateRenderer` | Safely renders allowed placeholders in title/explanation/recommendation/dedup templates. |
| `PriceSafetyCalculator` | Computes `min_safe_price`, `max_safe_discount_pct`, target price, margin after discount, and blocks unsafe price decreases. |
| `ProblemRuleAdminService` | Admin CRUD, validation, backtest, publish/pause/archive, and audit. |
| `ProblemEvaluationRunnerService` | Scheduled/manual/sync-triggered evaluation and portal re-checks with run logs. |
| `DynamicProblemSeedService` | Seeds initial definitions and rule versions. |
| `DataFixProblemBridge` | Mirrors selected Data Fix/DQ issues into dynamic `problem_instances` with guided fix metadata and evidence. |

Existing services updated:

- `PortalService`: maps dynamic instances to portal actions, Product Doctor
  groups, status updates, duplicate suppression, and legacy fallback logic.
- `DataQualityService`: syncs eligible Data Fix issues to dynamic instances.
- Sync/manual-cost jobs and routers: trigger evaluation behind rollout flags.

## New and Updated APIs

Admin-only, superuser-required:

- `GET /admin/problem-rules/metrics`
- `POST /admin/problem-rules/evaluate`
- `GET /admin/problem-rules/definitions`
- `POST /admin/problem-rules/definitions`
- `GET /admin/problem-rules/definitions/{definition_id}`
- `PATCH /admin/problem-rules/definitions/{definition_id}`
- `POST /admin/problem-rules/definitions/{definition_id}/versions`
- `POST /admin/problem-rules/versions/{version_id}/validate`
- `POST /admin/problem-rules/versions/{version_id}/backtest`
- `POST /admin/problem-rules/versions/{version_id}/publish`
- `POST /admin/problem-rules/versions/{version_id}/pause`
- `POST /admin/problem-rules/versions/{version_id}/archive`

Seller/operator-facing updates:

- `GET /portal/actions` now includes dynamic problem instances as normal
  actions/issues and supports filters for source module, problem code, trust
  state, impact type, and status.
- `PATCH /portal/actions/by-source` updates dynamic problem status when
  `source_module="problem_engine"`.
- `POST /portal/problems/{problem_id}/recheck` re-runs the relevant rule and
  returns the refreshed portal action.
- `GET /portal/products/{nm_id}` includes Product Doctor / Business Issues
  data grouped by category with open/resolved problems and summary counts.
- Data Fix responses can include `dynamic_problem_instance` references.

## Frontend Pages and Components

| UI | File | Purpose |
| --- | --- | --- |
| Admin Problem Rules tab | `frontend/src/routes/_authenticated/admin.tsx` | Adds the Problem Rules admin workspace. |
| Problem Rules admin panel | `frontend/src/components/problem-rules/ProblemRulesAdminPanel.tsx` | Rule list, definition editor, rule version workspace, formula builder, evidence template editor, validation, backtest preview, publish/pause/archive controls, and performance view. |
| Problem Rules API client | `frontend/src/lib/problem-rules.ts` | Typed client for admin rule APIs. |
| Evidence Drawer/Button | `frontend/src/components/EvidenceDrawer.tsx` | Shows formula, facts, sources, missing data, trust notes, warnings, fix/re-check info, and admin/debug raw JSON. |
| Seller problem UX | `frontend/src/components/problem/SellerProblemUX.tsx` | Consistent badges, answer grid, allowed actions, money/trust presentation, empty states, and cards. |
| Product Doctor | `frontend/src/components/portal/ProductDoctorSection.tsx` | Product360 business issue section grouped by category with evidence. |
| Action Center | `frontend/src/routes/_authenticated/action-center.tsx` | Dynamic problem filters, evidence drawer, allowed action handling, status updates, and re-check. |
| Data Fix workbench | `frontend/src/components/data-fix/DataFixWorkbench.tsx` | Shows linked dynamic problem evidence, affected rows, fix forms, preview/apply/re-check paths. |
| Price safety panel | `frontend/src/components/PriceSafetyPanel.tsx` | Displays safe price range and safety/unsafe rationale where used. |

## Seeded Metrics

Seeded metric codes:

- `stock_qty`
- `avg_daily_sales_7d`
- `avg_daily_sales_14d`
- `avg_daily_sales_30d`
- `days_of_stock`
- `revenue_7d`
- `avg_daily_revenue_7d`
- `revenue_30d`
- `orders_7d`
- `orders_30d`
- `price_current`
- `price_after_discount`
- `commission_per_unit`
- `logistics_per_unit`
- `acquiring_per_unit`
- `storage_fee_per_unit`
- `ad_spend_7d`
- `ad_spend_30d`
- `promo_spend_30d`
- `cost_price`
- `unit_profit`
- `margin_pct`
- `return_rate`
- `conversion_rate`
- `views_30d`
- `sales_7d`
- `sales_30d`
- `units_sold_7d`
- `unit_profit_after_ads`

Metric source policy:

- Values are resolved from existing marts/services when available.
- Missing or unknown values are returned as missing diagnostics.
- No fake business values are generated.
- Evidence includes source table/service, endpoint when known, date range,
  row count where possible, filters, and freshness/sync metadata where possible.

## Seeded Problem Rules

| Code | Category | Condition | Impact | Trust / notes |
| --- | --- | --- | --- | --- |
| `missing_cost_blocks_profit` | `data_quality` | `cost_price` missing and `revenue_30d > 0` | `data_blocker`, revenue amount as blocked context | `blocked`; recommends upload/map cost; allowed actions include `upload_cost`, `map_sku`, `create_task`, `recheck`, `dismiss`. |
| `negative_unit_profit` | `profitability` | `cost_price` exists and (`unit_profit < 0` or `margin_pct < 10`) | `probable_loss = abs(unit_profit * sales_30d)` when unit profit is negative | `estimated`; intentionally does not trigger when cost is missing. Price increase target is calculated when unit economics are complete. |
| `overstock_slow_moving` | `stock` | `stock_qty > 50` and `days_of_stock > 60` and `avg_daily_sales_14d < 2` | `blocked_cash = max(stock_qty - 50, 0) * cost_price` | `estimated`; promo/discount only stays available if price safety passes. |
| `low_stock_risk` | `stock` | `days_of_stock < 7` and `avg_daily_sales_7d > 1` | `lost_sales_risk = avg_daily_revenue_7d * max(7 - days_of_stock, 0)` | `provisional`; recommends supply/replenishment or reducing promo/ads. |
| `ads_spend_without_profit` | `ads` | `ad_spend_7d > 500` and `unit_profit_after_ads < 0` | `probable_loss = abs(unit_profit_after_ads) * units_sold_7d` | `estimated`; recommends pausing/lowering ads, checking card quality, bids, and price. |
| `promo_not_profitable` | `promo` | `cost_price` exists, `promo_spend_30d > 0`, and (`unit_profit < 0` or `margin_pct < 10`) | `probable_loss = max(promo_spend_30d, abs(unit_profit * sales_30d))` when unit profit is negative | `estimated`; deeper discounts are blocked when price safety fails or cost/fee data is missing. |
| `price_below_safe_margin` | `price` | `cost_price` exists, `price_after_discount > 0`, and `margin_pct < 10` | `probable_loss = abs(unit_profit * sales_30d)` when unit profit is negative | `estimated`; target price is calculated from cost plus unit fees. |
| `dead_stock` | `stock` | `stock_qty > 0`, `sales_30d = 0`, and `days_of_stock > 90` | `blocked_cash = stock_qty * cost_price` | `estimated`; liquidation/promo actions are guarded by `min_safe_price`. |
| `fast_stock_depletion` | `stock` | `days_of_stock < 3` and `avg_daily_sales_7d > 2` | `lost_sales_risk = avg_daily_revenue_7d * max(7 - days_of_stock, 0)` | `provisional`; recommends urgent replenishment or reducing promo/ads. |

All nine seeded product/business codes are visible in the admin rule catalog
after migrations.

## Feature Flags

Configured in `backend/app/core/config.py`:

- `dynamic_problem_engine_enabled`
  - Global kill switch for automatic/admin dynamic evaluation.
- `dynamic_problem_engine_test_account_ids`
  - Optional account allowlist. When non-empty, dynamic evaluation runs only for
    those accounts.
- `show_legacy_problem_cards`
  - Keeps mapped legacy cards as fallback. When false, mapped legacy problem
    cards are hidden even if dynamic instances are absent.

Default rollout behavior:

- dynamic engine is enabled;
- allowlist can restrict to admin/test accounts;
- legacy fallback remains available until explicitly disabled.

## How to Add a New Problem Rule

Admin UI path:

1. Open Admin -> Problem Rules.
2. Click Create problem.
3. Fill problem definition fields:
   - `problem_code`
   - category
   - entity type
   - title template
   - explanation template
   - recommendation template
   - default severity, trust state, and impact type
   - allowed actions
4. Select metrics from the Metric Catalog.
5. Build the condition formula in the Rule Builder.
6. Build the impact formula.
7. Configure severity and confidence formulas.
8. Configure re-check rule and evidence template.
9. Save a draft rule version.
10. Run Validate. Unsafe operators, unknown metrics, and invalid formulas are
    rejected.
11. Run Backtest against an account/date range. Review matched count, sample
    issues, total impact, warnings, and missing metric stats.
12. Publish the rule. Publish requires:
    - valid formulas;
    - evidence `formula_human`;
    - human-readable re-check rule;
    - allowed actions;
    - at least one successful backtest or explicit admin override.
13. Run Admin Evaluate or wait for sync/nightly evaluation.
14. Published matches appear for sellers in Action Center and Product360.

Backend API path is the same flow through:

- `POST /admin/problem-rules/definitions`
- `POST /admin/problem-rules/definitions/{id}/versions`
- `POST /admin/problem-rules/versions/{id}/validate`
- `POST /admin/problem-rules/versions/{id}/backtest`
- `POST /admin/problem-rules/versions/{id}/publish`
- `POST /admin/problem-rules/evaluate`

## Evidence, Trust, and Re-check

Evidence:

- Every generated `problem_instance` must include `evidence_ledger_json`.
- The ledger includes:
  - `formula_human`
  - `formula_code` or `formula_id`
  - `input_facts[]`
  - `source_references[]`
  - `missing_data[]`
  - `trust_notes[]`
  - `recheck_rule_human`
  - `calculation_warnings[]`
- Seller UI shows this through the Evidence Drawer as "How calculated?" /
  "Qayerdan keldi?" / "Как посчитано?".
- Raw JSON is not shown to sellers by default.

Trust:

- Rule definitions provide default trust state.
- Confidence formulas can drive trust values.
- Missing-data blocker problems use `blocked`.
- Estimated/provisional money is visually and semantically separated from
  confirmed loss in Product Doctor summaries.
- `test_only` rules are hidden from sellers unless admin/debug mode allows them.

Re-check:

- Rule versions carry `recheck_rule_json`, including human text and optional
  `resolved_when`.
- Re-check runs through `ProblemEvaluationRunnerService`.
- If the condition no longer matches and `resolved_when` passes, the instance is
  marked `resolved`.
- If configured for cautious closure, the instance can become
  `candidate_resolved`.
- Re-check and Action Center status updates create `problem_instance_history`
  records.

## Tests and Results

Recent verification:

- `backend/.venv/bin/python -m py_compile backend/app/services/problem_engine/price_safety.py backend/app/services/problem_engine/problem_seeds.py backend/app/services/problem_engine/evaluator.py backend/alembic/versions/20260706_000061_seed_remaining_dynamic_problem_rules.py`
  - passed
- `cd backend && .venv/bin/alembic upgrade head && .venv/bin/alembic current`
  - migration applied cleanly; current revision is `20260706_000061 (head)`
- `backend/.venv/bin/pytest backend/tests/acceptance/test_dynamic_problem_engine_product_acceptance.py backend/tests/unit/test_problem_engine_models.py backend/tests/unit/test_problem_engine_formula_evaluator.py backend/tests/unit/test_problem_engine_metric_catalog.py backend/tests/unit/test_problem_engine_evidence_ledger.py backend/tests/unit/test_problem_engine_evaluator.py backend/tests/unit/test_problem_engine_initial_rules.py backend/tests/unit/test_problem_engine_portal_integration.py backend/tests/unit/test_problem_engine_runner.py backend/tests/unit/test_problem_engine_admin_rules.py backend/tests/unit/test_problem_engine_price_safety.py backend/tests/unit/test_data_fix_dynamic_problem_bridge.py -q`
  - `100 passed, 1 warning`
- `backend/.venv/bin/ruff check backend/app/services/problem_engine/price_safety.py backend/app/services/problem_engine/problem_seeds.py backend/alembic/versions/20260706_000061_seed_remaining_dynamic_problem_rules.py backend/tests/unit/test_problem_engine_initial_rules.py backend/tests/unit/test_problem_engine_price_safety.py backend/tests/acceptance/test_dynamic_problem_engine_product_acceptance.py`
  - passed
- `frontend npm run test:contracts`
  - `10/10` endpoint schemas OK
- `frontend npm run build`
  - passed
  - existing warning: one client chunk is larger than 500 kB

Notable test coverage:

- formula operators and unsafe input rejection;
- metric catalog listing and metric resolver missing diagnostics;
- evidence ledger required fields;
- seeded initial rules;
- evaluator create/update/dedup/status preservation/resolution/test mode;
- price safety blocking and target price calculation;
- Action Center integration/status/dismiss/filter/evidence;
- admin RBAC/validation/backtest/publish gates;
- Data Fix bridge issues;
- product-level acceptance scenarios for missing cost, negative profit,
  overstock, low stock, Action Center, re-check, and admin-published rules.

Known test caveats:

- Full Playwright E2E was not part of the latest verification run.
- Frontend build passes, but Vite reports the pre-existing large chunk warning.
- The backend test run reports a passlib Python 3.13 `crypt` deprecation warning.

## Known Limitations

- Current evaluator is product-focused. The schema supports account, campaign,
  warehouse, and category entities, but those grains are not fully evaluated yet.
- Some catalog metrics depend on existing marts/fresh sync data. Missing sources
  surface as diagnostics instead of fabricated values.
- Admin UI supports a practical builder and advanced JSON editing; very complex
  formulas may still require advanced JSON input.
- The first seeded rules are code/migration-seeded. After seeding, admins can
  create new rules, but editing the built-in seed catalog itself still requires
  care.
- Price safety currently assumes RUB and default target margin settings from the
  service.
- External WB write actions are not executed by the engine. They must still go
  through preview/diff/confirm/audit flows in their owning modules.
- Data Fix bridge maps several existing DQ issues, but not every historical DQ
  text/card is a fully formula-defined dynamic rule.
- Legacy action/card producers remain in the codebase as fallback.

## What Is Still Hardcoded

Still intentionally present as fallback or adjacent module logic:

- Legacy money/profit doctor actions and money page cards.
- Legacy Data Quality guided definitions and several resolver/fix workflows.
- Card quality/checker issue generation.
- Stock Control local recommendations and beta stock workflows.
- Some page-local pricing/promo helper copy around the dynamic definitions.
- UI action labels, filter labels, empty-state copy, and some source mappings.
- `PortalService.LEGACY_DYNAMIC_PROBLEM_MAP`, used to suppress duplicate legacy
  cards when dynamic instances exist.
- Whitelisted formula operators, allowed rule actions, and initial metric/rule
  seeds.

These should not be removed until equivalent dynamic rules and seller workflows
are proven in production.

## Next Recommended Rules

High-priority dynamic rules to add next:

1. `manual_cost_unresolved_sku`
   - Uploaded cost cannot be attached to a SKU/product.
2. `manual_cost_ambiguous_match`
   - Cost upload matches multiple possible SKUs.
3. `unmatched_sku`
   - Product/SKU cannot be matched across operational/finance/cost sources.
4. `expense_unclassified`
   - Seller expense is present but not classified for profitability.
5. `finance_reconciliation_mismatch`
   - Sales/orders and finance report disagree beyond tolerance.
6. `sale_without_finance`
   - Sale exists but no corresponding finance row is available after expected
     sync delay.
7. `finance_without_sale`
   - Finance row exists without a matching sale/order.
8. `high_return_rate_erodes_profit`
   - Return rate crosses threshold and materially reduces margin.
9. `low_conversion_high_views`
   - Views are high but conversion is below category/account benchmark.
10. `ads_drr_too_high`
   - Ads spend ratio is above threshold and unit economics are weak.
11. `storage_fee_pressure`
   - Storage fee per unit or total storage cost is materially eroding margin.

Recommended rollout order:

1. Finish Data Fix blockers first, because clean data improves trust for all
   profitability rules.
2. Promote formula-defined Data Fix blockers from bridge metadata to admin-owned
   rules where the source metrics are stable.
3. Add conversion/opportunity rules after source freshness is stable.
4. Move checker/card quality rules last, because they need their own metric
   catalog and quality-evidence normalization.
