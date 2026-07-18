# Dynamic Problem Definition Baseline

Date: 2026-07-06

Purpose: safe inventory before introducing a Dynamic Problem Definition Engine.
This document is documentation-only. No product or business logic was changed.

## Repo Shape

Backend:

- `backend/app/api/router.py` wires the modular FastAPI routers.
- `backend/app/modules/*/router.py` exposes API endpoints.
- `backend/app/services/*.py` contains most calculations, hardcoded business rules, and aggregation.
- `backend/app/schemas/*.py` defines response contracts.
- `backend/app/models/*.py` defines persisted action, alert, and source tables.

Frontend:

- `frontend/src/lib/endpoints.ts` is the central endpoint map.
- `frontend/src/lib/money-endpoints.ts` wraps money, purchase, price, ads, cost, and finance calls.
- `frontend/src/lib/portal.ts` wraps Portal, Product 360, Action Center, and card quality calls.
- `frontend/src/lib/copy.ts` contains many user-facing mappings from technical codes to business copy.
- `frontend/src/routes/_authenticated/*` contains the product pages.
- `frontend/src/components/*` contains shared action, evidence, data-fix, money, and quality components.

## Current Problem Sources

| Source | Files | Creates or exposes | Notes |
| --- | --- | --- | --- |
| Control Tower | `backend/app/services/control_tower.py`, `backend/app/modules/control_tower/router.py`, `backend/app/schemas/control_tower.py`, `backend/app/models/control_tower.py` | Persisted `ActionRecommendation` rows, `AlertEvent` rows, purchase plan, price safety, ads efficiency | Main hardcoded business recommendation source today. |
| Money Management | `backend/app/services/money_management.py`, `backend/app/modules/money_management/router.py`, `backend/app/schemas/money_management.py` | Money summary, card/article verdicts, `CardProblem`, `NextActionRead`, data blockers | Mixes persisted Control Tower actions with synthesized fallback actions. |
| Data Quality | `backend/app/services/data_quality.py`, `backend/app/modules/data_quality/router.py`, `backend/app/schemas/data_quality.py` | `DataQualityIssueRead`, issue summaries, resolution contexts, guided fix actions | Many issue codes and fix definitions are service/schema hardcoded. |
| Manual Costs | `backend/app/services/manual_costs.py`, `backend/app/modules/manual_costs/router.py` | Missing/unresolved cost workflows | Feeds missing-cost blockers and cost-fix actions. |
| Portal Aggregator | `backend/app/services/portal.py`, `backend/app/modules/portal/router.py`, `backend/app/schemas/portal.py` | `/portal/actions`, `/portal/products/{nm_id}`, Product 360 actions | Aggregates finance actions, DQ, costs, checker, StockOps, claims, reputation, experiments. |
| Card Quality / Checker | `backend/app/services/card_quality.py`, Portal card-quality routes, `frontend/src/routes/_authenticated/checker.$nmId.tsx` | Card quality issues and `CARD_QUALITY_FIX` actions | Hardcoded issue-to-action mapping and UI buckets. |
| Stock / Product Recommendations | `backend/app/services/control_tower.py`, `backend/app/services/stockops_adapter.py`, stock control modules | Purchase decisions, stock protection, liquidation, StockOps candidates | Control Tower owns finance-aware purchase rules; StockOps adds operational stock actions. |
| Pricing / Promo / Ads | `backend/app/services/control_tower.py`, `backend/app/modules/prices`, `backend/app/modules/ads`, `backend/app/modules/ab_tests`, `backend/app/services/ab_tests.py` | Price safety, ads efficiency, AB/promotion endpoints | No standalone named `PROMO_NOT_PROFITABLE` problem was found; promo risk is currently represented through price, liquidation, ads, and experiment flows. |
| Frontend Presentation | `frontend/src/lib/copy.ts`, `frontend/src/routes/_authenticated/dashboard.tsx`, `frontend/src/routes/_authenticated/action-center.tsx`, pricing/ads/purchase/product/card routes | Business copy, deep links, filters, fallback classifiers | Some user-visible hardcoding exists outside the backend. |

## Current API Endpoints

Control Tower and finance-aware actions:

- `GET /dashboard/owner -> OwnerDashboardRead`
- `GET /skus -> Page[ControlTowerSkuRow]`
- `GET /skus/{sku_id} -> ControlTowerSkuDetail`
- `GET /actions -> Page[ActionRecommendationListItem]`
- `GET /actions/{action_id} -> ActionRecommendationRead`
- `PATCH /actions/{action_id} -> ActionRecommendationRead`
- `POST /actions/bulk -> BulkMutationResponse`
- `GET /alerts -> Page[AlertRead]`
- `PATCH /alerts/{alert_id} -> AlertRead`
- `POST /alerts/bulk -> BulkMutationResponse`
- `GET /inventory/purchase-plan -> PurchasePlanPage`
- `GET /pricing/safety -> PriceSafetyPage`
- `POST /pricing/simulate -> PriceSimulationResponse`
- `GET /ads/efficiency -> AdsEfficiencyPage`
- `GET /settings/business -> BusinessSettingsRead`
- `GET /settings/business/policies -> BusinessPoliciesRead`

Money Management:

- `GET /money/summary -> MoneySummaryRead`
- `GET /money/profit-cascade -> ProfitCascadeRead`
- `GET /money/expenses/breakdown -> ExpenseBreakdownSummaryRead`
- `GET /money/expenses/logistics -> MoneyExpenseLogisticsRead`
- `GET /money/expenses/report-rows -> Page[ExpenseReportRowRead]`
- `GET /money/cards -> MoneyCardPage`
- `GET /money/cards/{sku_id} -> MoneyCardDetailRead`
- `GET /money/articles -> MoneyArticlePage`
- `GET /money/articles/{nm_id} -> MoneyArticleDetailRead`
- `GET /money/actions -> TodayActionsPage`
- `GET /money/actions/today -> TodayActionsPage`
- `GET /money/data-blockers -> DataBlockersRead`
- `GET /money/filters -> MoneyFiltersRead`

Data quality and data fix:

- `GET /dq/issues -> Page[DataQualityIssueRead]`
- `GET /dq/issues/summary -> DataQualityIssueSummaryResponse`
- `GET /dq/issues/{id}/resolution-context -> DataQualityResolutionContext`
- `GET /dq/issues/{id}/affected-rows.csv`
- `POST /dq/issues/{id}/guided-action -> GuidedFixActionResponse`
- `GET /dq/issues/investigator -> Page[DataQualityIssueRead]`
- `POST /dq/run -> DataQualityRunResponse`
- Bulk resolve, reopen, comment, classify endpoints are also exposed by the DQ router.

Costs:

- `POST /costs/upload`
- `GET /costs/imports`
- `GET /costs/rows`
- `GET /costs/template`
- `GET /costs/missing`
- `GET /costs/uploads/{id}/preview`
- `POST /costs/uploads/{id}/confirm`
- `POST /costs/inline-save`
- `PATCH /costs/{id}`
- `POST /costs/{id}/mark-supplier-confirmed`
- `POST /costs/relink`

Portal and Product 360:

- `GET /portal/doctor -> ProfitDoctorOut`
- `GET /portal/overview -> PortalOverviewRead`
- `GET /portal/data-readiness -> PortalDataReadinessRead`
- `GET /portal/data-sync/status -> PortalDataSyncStatusRead`
- `GET /portal/actions -> PortalActionsPage`
- `PATCH /portal/actions/by-source -> PortalActionRead`
- `PATCH /portal/actions/{action_id} -> PortalActionRead`
- `GET /portal/results`
- `GET /portal/actions/{id}/results`
- `POST /portal/actions/{id}/result-event`
- `GET /portal/products -> PortalProductsPage`
- `GET /portal/products/{nm_id} -> PortalProduct360Read`
- `GET /portal/products/{nm_id}/quality -> PortalProductQualityRead`
- `/portal/card-quality/*` routes for analysis, issue queues, status updates, previews, fixes, fixed-file flows, and runs.

Other relevant endpoint families:

- `GET /dashboard/sku-profitability`
- `GET /dashboard/article-audit`
- `GET /dashboard/data-health`
- `/stocks/*`, `/supplies/*`, and `/portal/stock-control/*`
- `/prices/*`
- `/ads/campaigns`, `/ads/stats`
- `/promotion/*` for AB test and promotion flows

## Current Response Shapes

Important backend contracts already carry enough structure for a future engine:

- `ActionRecommendationRead`: `action_type`, `category`, `priority`, `status`, `reason_code`, `reason`, `reason_short`, `reason_full`, `business_reason`, `next_step`, `calculation_basis`, `expected_effect_amount`, `priority_score`, `confidence`, `trust_state`, `financial_final`, `blocked_reasons`, `payload`, `money_effect`, linked entity fields, source hash/date fields, and seller visibility fields.
- `ActionRecommendationListItem`: compact action rows with status, priority, action type, title, short reason, expected effect, confidence, trust, linked SKU/nm fields, and timestamps.
- `AlertRead`: alert type, severity, status, title, message, confidence, payload, snooze/resolve timestamps, and optional action link.
- `PurchasePlanRow`: stock, velocity, lead/safety days, recommended quantity, required cash, expected profit, risk, reason, next step, missing/wait data, trust, financial finality, cost truth, and `money_effect`.
- `PriceSafetyRow`: current prices, break-even, target-margin price, safe price gap, margin, confidence, calculation state, not-computable reasons, `action_hint`, source, and mapping/data state.
- `AdsEfficiencyRow`: ad spend, source/allocated/unallocated/overallocated spend, DRR, profit, stock, confidence, `action_hint`, `action_label`, trust, blocked reasons, and campaign stats.
- `MoneySummaryRead`: owner summary with trust, revenue sources, reconciliation, cost coverage, KPIs, expenses, profit cascade, risk summary, top cards, next actions, blockers, and evidence ledger.
- `NextActionRead`: action type/group/category, priority/status, title, what/why/how, business reason, next step, effect/cash/recommended quantity, confidence, financial finality, linked entity, blockers, money effect, source endpoint, evidence ledger, and money trust.
- `CardProblem`: code, severity, title, business impact, and fix hint. This is useful but lighter than action/evidence shapes.
- `DataBlockerRead`: code, priority, title, affected counts/amounts, business impact, how to fix, first action, success check, endpoint/screen hints, calculation title/formula/inputs, source endpoints, resolver, evidence ledger, and money trust.
- `PortalActionRead`: source/source module/source id, action type, title, priority/severity/status, reason, next step, expected effect, score, confidence, linked product/SKU, guided fix, source references, recheck rule, trust, evidence ledger, money trust, and raw payload.
- `PortalProduct360Read`: sectioned Product 360 response with identity, money, costs, ads, stock, pricing, data quality, card quality, reputation, claims, photo, experiments, grouping, actions, next best action, module health, history, and evidence.
- `DataQualityIssueRead`: issue code/severity/status/domain/source table, affected entity fields, payload, financial finality blocker flags, resolver/evidence fields.
- `CardQualityIssueRead`: issue code/category/severity/status/title/business explanation/recommended fix/current/expected/suggested values, fingerprint, suggestion kind, actionability, evidence, and money trust.

## Existing Hardcoded Business Problems

These are the main items to migrate to a dynamic engine.

| Problem / rule | Current source | Current output | Evidence already present |
| --- | --- | --- | --- |
| Missing cost blocks profit | `money_management.py`, `control_tower.py`, `manual_costs.py`, DQ checks | `FIX_COST_TRUST`, `DATA_FIX_REQUIRED`, cost blockers, missing-cost DQ issues | Cost coverage, affected SKU/article counts, affected revenue/amount, calculation fields, source endpoints, resolver hints. |
| Unmatched SKU blocks calculations | `money_management.py`, `control_tower.py`, `data_quality.py`, `portal.py` | `MAP_UNMATCHED_SKU`, DQ issue/action, data blocker | Affected rows, SKU/nm ids, DQ payload, guided fix context. |
| Latest stocks/sync incomplete | `money_management.py`, `control_tower.py`, sync/data readiness logic | `FIX_STOCK_SYNC`, data blocker, wait-data purchase rows | Sync/data readiness fields, affected products, wait reasons. |
| Finance reconciliation mismatch | `money_management.py`, `dashboard.py`, `data_quality.py`, `portal.py` | `RECONCILE_FINANCE`, `RECONCILIATION_REVIEW`, card/article problems | Audit totals, mart vs finance difference, root-cause candidates, finance status. |
| Overstock | `control_tower.py`, `money_management.py`, product/card UI fallbacks | Purchase status `LIQUIDATE`, action `LIQUIDATE_STOCK`, card verdict `overstock` | Days of stock, velocity, stock value, expected profit, `money_effect`, calculation basis. |
| Low stock risk | `control_tower.py`, `money_management.py`, product/card UI fallbacks | Purchase status/action `REORDER` or `PROTECT_STOCK`, card verdict `stock_risk`/`protect_stock` | Days of stock, lead/safety days, recommended quantity, required cash, expected profit. |
| Negative unit/card profit | `control_tower.py`, `money_management.py` | `PRICE_INCREASE_REVIEW` if below safe price, otherwise `DO_NOT_REORDER`; card verdict `loss` | Net profit, margin, safe price gap, current price, unit cost, expected amount. |
| Price below break-even / unsafe price | `control_tower.py`, pricing UI | `PRICE_INCREASE_REVIEW`, price safety `action_hint`, price-risk badges | Break-even price, target-margin price, safe price gap, not-computable reasons. |
| Price not computable | `control_tower.py`, money/card detail UI | `FIX_PRICE_MAPPING` or data-fix hints | Missing price/cost/revenue/unit reasons, price source and mapping state. |
| Ads spend without profit | `control_tower.py`, `money_management.py`, ads UI fallback classifier | `AD_PAUSE_REVIEW`, ads efficiency `action_hint`/`action_label`, card verdict `ad_risk` | Ad spend, DRR, profit after ads, source/allocated spend, confidence. |
| Ads allocation not final | `money_management.py`, `control_tower.py`, `portal.py`, ads UI | `FIX_AD_ALLOCATION`, data warnings `ads_overallocated_to_profitability` and `ads_not_allocated_to_profitability` | Source spend, allocated/unallocated/overallocated spend, allocation status. |
| Promo not profitable | No standalone named problem found | Represented indirectly by price safety, liquidation/discount-to-clear copy, ads efficiency, and AB/promotion flows | Price and profit evidence exists; no dedicated promo profitability evidence contract found. |
| Card content/checker quality | `card_quality.py`, `portal.py`, checker route | `CARD_QUALITY_FIX`, checker issue cards, quality action rows | Issue code, category, severity, business explanation, recommended fix, score impact, evidence. |
| High cancel/return rate | `money_management.py`, SKU/card UI | `CardProblem` and visible alerts in card detail | Operation rates and counts; currently lighter evidence than action rows. |
| Data quality issue codes | `data_quality.py`, `schemas/data_quality.py`, `portal.py`, `DataFixWorkbench` | DQ issues, guided fixes, Portal `DATA_FIX` actions | Affected rows, source table, payload, resolver, evidence ledger. |
| High priority action alert | `control_tower.py` | `AlertEvent` derived from critical/high `ActionRecommendation` | Alert mirrors action title/reason/trust payload; alerts do not have independent rule logic. |

Key hardcoded locations:

- `backend/app/services/control_tower.py`
  - Business thresholds in `DEFAULT_SETTINGS`.
  - SKU status classification in `_classify_sku_status`.
  - Purchase decisions in `_purchase_status_and_reason`.
  - Price safety and not-computable reasons in `_safe_price_metrics` and `_price_not_computable_reasons`.
  - Ads action labels/hints in ads efficiency helpers.
  - Action playbook copy in `_action_business_copy`.
  - Blocked-reason to action-type mapping in `_blocked_action_type`.
  - Persistent action creation in `_sync_recommendations`.
  - Alert creation in `_sync_alerts_from_actions`.
- `backend/app/services/money_management.py`
  - Blocked-reason actions in `_blocked_reason_to_action`.
  - Card verdicts in `_build_card_verdict`.
  - Fallback row actions in `_synthesized_row_action` and `_default_row_action`.
  - Article/card `CardProblem` creation.
  - Data blocker and warning creation in `data_blockers`.
  - Owner action grouping/title/priority helpers.
- `backend/app/services/data_quality.py`
  - DQ check definitions, issue codes, severities, and guided fix actions.
- `backend/app/schemas/data_quality.py`
  - Issue display metadata and resolution guide metadata.
- `backend/app/services/card_quality.py`
  - Checker issue recommendation/fix/action mapping.
- `backend/app/services/portal.py`
  - Aggregation and conversion to `PortalActionRead`.
  - User-actionable DQ code list.
  - Cost action titles/reasons.
  - Checker setup/action generation.
- `backend/app/services/stockops_adapter.py`
  - StockOps candidate to Portal action mapping.
- `frontend/src/lib/copy.ts`
  - Card status copy, action copy, blocker copy, DQ copy, price/ads/stock/cost labels.
- `frontend/src/routes/_authenticated/dashboard.tsx`
  - Repair playbooks and dashboard data-fix card mapping.
- `frontend/src/routes/_authenticated/action-center.tsx`
  - Source labels, priority/status labels, system-handled action hiding, issue focus patterns, and code-to-route deep links.
- `frontend/src/routes/_authenticated/pricing.tsx`
  - Price action labels, filters, and fallback stats.
- `frontend/src/routes/_authenticated/ads.tsx`
  - Ads hint copy and fallback `classifyHint`.
- `frontend/src/routes/_authenticated/purchase-plan.tsx`
  - Purchase status labels, actionable filters, and missing data labels.
- `frontend/src/routes/_authenticated/cards.$nmId.tsx` and `frontend/src/routes/_authenticated/sku.$id.tsx`
  - Article/SKU decision mapping, overstock/OOS alerts, high cancel/return alerts, and problem display.
- `frontend/src/routes/_authenticated/products.$nmId.tsx`
  - Product 360 section status derivation, action visibility, data quality grouping, and next-best-action display.
- `frontend/src/components/money-ui/ActionCard.tsx`
  - Action status/confidence/blocker labels.
- `frontend/src/components/data-fix/DataFixWorkbench.tsx`
  - Guided fix owner/component/field/category display copy.

## Current UI Surfaces

| Page/component | Main data | Displays |
| --- | --- | --- |
| `/dashboard` | Money summary, actions today, data blockers, data health | Owner repair cards, risks, data-fix workbench, top actions. |
| `/money` | `/money/summary`, `/money/actions/today`, `/money/data-blockers`, `/money/articles` | Money cockpit, blockers, top actions, top cards, evidence/finality signals. |
| `/action-center` | `/portal/actions` | Unified action queue with grouping, guided fixes, evidence, status updates, source filters. |
| `/products` | `/portal/products` | Product list with revenue/profit/card quality/open actions/top action. |
| `/products/$nmId` | `/portal/products/{nm_id}` | Product 360 sections, next best action, section evidence, data quality, card quality, stock, claims, reputation, actions. |
| `/cards` and `/cards/$nmId` | `/money/articles`, `/money/articles/{nm_id}` | Article-level money view, problems, next actions, stock/price/ads/profit blocks. |
| `/sku/$id` | `/money/cards/{sku_id}`, `/core-sku/{sku_id}`, purchase plan | SKU-level investigation, problems, next actions, purchase slice. |
| `/data-fix` and `DataFixWorkbench` | `/money/data-blockers`, `/dq/*` | Data blockers, issue resolution context, affected rows, guided actions. |
| `/costs` | `/costs/*` | Missing and unresolved costs. |
| `/purchase-plan` | `/inventory/purchase-plan` | Reorder/liquidate/wait-data/do-not-buy/watch decisions. |
| `/pricing` | `/pricing/safety`, `/pricing/simulate` | Price safety, break-even gaps, price increase hints, not-computable rows. |
| `/ads` | `/ads/efficiency`, `/ads/stats`, `/ads/campaigns`, `/money/summary` | Ads profitability, allocation problems, pause/scale/watch/data-fix hints. |
| `/checker/$nmId` | `/portal/card-quality/*` | Card quality issues, previews, fixes, queue progress, action-center invalidation. |
| `/stock-control` | `/portal/stock-control/*` | Operational stock tasks and stock movement workflows. |
| `/ab-tests` | `/promotion/*` | Promotion/AB test management and stats. |

## Evidence And Calculation Payloads

Already strong:

- Control Tower actions carry `calculation_basis`, `payload`, `money_effect`, expected amount, trust, blocked reasons, and source hash/date fields.
- Purchase, pricing, and ads pages expose row-level calculation inputs and derived metrics.
- Money actions and data blockers auto-fill `evidence_ledger` and `money_trust`.
- Portal actions can carry `evidence_ledger`, `guided_fix`, `source_references`, `recheck_rule`, and raw payload.
- DQ issues expose affected rows and guided resolution context.
- Card quality issues expose issue codes, score impact, recommended fixes, and evidence/money trust.
- Dashboard repair cards already surface calculation title/formula/inputs when backend provides them.

Gaps to watch:

- `CardProblem` is lighter than `NextActionRead` and usually lacks explicit evidence ledger.
- Alerts are derived from actions and do not have their own rule/evidence model.
- Frontend copy and route mapping duplicate backend action/problem semantics.
- Promo profitability is not a first-class problem source today.
- Some frontend pages contain fallback classifiers that can diverge from backend rules.

## Migration Targets For The New Engine

The Dynamic Problem Definition Engine should eventually own:

- Problem code and stable identity.
- Trigger conditions and thresholds.
- Severity/priority and confidence.
- Evidence facts and calculation basis.
- Action playbook: what to do, why, next step, how to fix.
- Resolver/guided-fix metadata.
- Entity scope: account, nm_id, sku_id, campaign, cost row, DQ issue, checker issue.
- UI route/deep-link metadata.
- Trust and financial-finality behavior.
- Seller/operator visibility rules.

Highest-priority migration points:

1. `control_tower.py` recommendation creation and alert derivation.
2. `money_management.py` synthesized actions, card verdicts, `CardProblem`, and data blockers.
3. DQ issue metadata and guided fix definitions.
4. Portal action conversion rules and user-actionable code lists.
5. Frontend copy/deep-link maps that currently encode business semantics.
6. Price, purchase, ads, and card/SKU route fallback classifiers.

Compatibility recommendation:

- Preserve existing API fields while adding an engine-owned `problem_code`, `definition_id`, `evidence`, and `resolver` shape.
- Keep `action_type`, `reason_code`, `priority`, `status`, `payload`, and `money_effect` during migration so current UI surfaces do not break.
- Move frontend-only business classifications to backend-provided fields before removing local fallback logic.

## Verification Baseline

Backend tests:

- Command: `cd backend && ./.venv/bin/python -m pytest`
- Result: failed with 1 existing unit failure.
- Summary: `1 failed, 979 passed, 4 xfailed, 2 warnings`.
- Failure: `tests/unit/test_manual_costs_service.py::test_list_missing_costs_filters_to_revenue_skus_and_summarizes_coverage`.
- Failure detail: the mocked `session.execute` side effect is exhausted in `ManualCostService.list_missing_costs`, raising `StopAsyncIteration` after an unexpected additional query. This was not fixed in this baseline step.

Frontend build:

- Command: `cd frontend && npm run build`
- Result: passed.
- Notes: Vite/Rollup emitted existing warnings about some large chunks and unused imports in generated/external SSR bundles plus an unused `Code2` import in `cards.$nmId.tsx`. Build completed successfully.

## Baseline Conclusion

Current alerts and recommendations are created mainly in Control Tower, Money Management, Data Quality, Manual Costs, Card Quality, StockOps, and Portal aggregation. They are displayed across Dashboard, Money, Action Center, Product 360, Cards/SKU detail, Data Fix, Costs, Purchase Plan, Pricing, Ads, Checker, and Stock Control.

The future dynamic engine should migrate both backend rule creation and frontend presentation mappings. Otherwise the hardcoded behavior will remain visible even if backend recommendation generation is centralized.
