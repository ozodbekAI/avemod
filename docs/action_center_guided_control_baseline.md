# Action Center Guided Control Baseline

Date: 2026-07-09

Scope: observation-only baseline for the current Finance / Control Tower Action
Center product loop. No product behavior was changed for this report.

Target loop:

`Problem -> evidence -> exact guided action -> task status/history -> re-check -> result`

## Executive Summary

Action Center already has the main pieces of the loop. Dynamic
`problem_engine` rows are the strongest path: they appear in `GET
/portal/actions`, carry problem identity, expose evidence ledgers and allowed
actions, support task status/history updates, can be re-checked, and have a
canonical result ledger at `GET /portal/problems/{problem_instance_id}/results`.

The current blocking gaps are mostly contract consistency gaps, not missing UI
sections:

- The frontend status selector is not transition-aware, while the backend
  enforces a transition graph. The E2E mock allows transitions such as
  `new -> done` that the real backend rejects.
- Seeded problem rules define specific action verbs, but the UI normalizes many
  of them into broad route aliases. This can send the seller to a module without
  preserving the exact guided operation.
- Static API fixtures still describe older finance/action examples and do not
  prove the dynamic problem contract: they often lack `allowed_actions`,
  `evidence_ledger`, `evidence_state`, `money_trust` and canonical result
  linkage.
- Some mock/test examples over-confirm impact and trust compared with seed
  semantics, especially for stock risk and negative-profit examples.
- Result ledgers are canonical for dynamic problems, but rows and older actions
  can still fall back to embedded `payload.result_summary`, so a task can look
  loop-complete without a canonical ledger.

Acceptance risk: guided solving is not blocked by a missing drawer or missing
result page. It is blocked by inconsistent contracts between rules, samples,
mocks, adapters and the backend transition model.

## Sources Inspected

Frontend:

- `frontend/src/lib/action-center-contract.ts`
- `frontend/src/lib/action-center-actions.ts`
- `frontend/src/lib/action-center-results.ts`
- `frontend/src/lib/action-center-status.ts`
- `frontend/src/lib/portal.ts`
- `frontend/src/hooks/action-center/useActionCenterData.ts`
- `frontend/src/hooks/action-center/useActionCenterMutations.ts`
- `frontend/src/routes/_authenticated/action-center.tsx`
- `frontend/src/components/action-center/ActionCenterPageContainer.tsx`
- `frontend/src/components/action-center/ActionCenterRow.tsx`
- `frontend/src/components/action-center/ActionCenterList.tsx`
- `frontend/src/components/action-center/ActionCenterDrawerContent.tsx`
- `frontend/src/components/action-center/ActionCenterTaskDrawer.tsx`
- `frontend/src/components/action-center/ActionCenterEvidenceControls.tsx`
- `frontend/src/components/EvidenceDrawer.tsx`
- `frontend/src/lib/problem-ux-copy.ts`
- `frontend/e2e/mock-api.ts`
- `frontend/e2e/action-center-professional.spec.ts`
- `frontend/tests/actionCenterContract.test.mjs`
- `frontend/tests/actionCenterBackendIntegration.test.mjs`
- `frontend/src/product-acceptance/action-center-drawer.fixtures.ts`

Backend:

- `backend/app/schemas/portal.py`
- `backend/app/modules/portal/router.py`
- `backend/app/services/portal.py`
- `backend/app/services/result_tracking.py`
- `backend/app/services/problem_engine/problem_seeds.py`
- `backend/alembic/versions/20260706_000058_seed_initial_dynamic_problem_rules.py`
- `backend/alembic/versions/20260706_000061_seed_remaining_dynamic_problem_rules.py`
- `backend/tests/api/test_portal_action_center_contract.py`
- `backend/tests/unit/test_problem_engine_initial_rules.py`
- `backend/tests/unit/test_problem_engine_portal_integration.py`

Endpoint and fixture samples:

- `backend/tests/fixtures/portal/actions_page_ok.json`
- `backend/tests/fixtures/portal/results_unified_ok.json`
- `backend/tests/fixtures/portal/product_360_contract_ok.json`
- `backend/tests/fixtures/portal/result_summary_windows_ok.json`
- `backend/tests/fixtures/portal/action_update_ok.json`

## Current Action List Contract

Primary endpoint:

`GET /portal/actions`

Current query surface:

- `account_id`
- `date_from`
- `date_to`
- `status`
- `source_module[]`
- `priority[]`
- `nm_id`
- `action_type[]`
- `problem_code[]`
- `trust_state[]`
- `impact_type[]`
- `include_beta`
- `limit`
- `offset`

`include_beta=true` is admin-only. Seller users do not receive beta/test-only
signals by default.

Response shape:

`PortalActionsPage`

- `total`
- `limit`
- `offset`
- `items`
- `unavailable_sources`

Each item is a `PortalActionRead`. Important fields used by Action Center:

- identity: `id`, `source`, `source_module`, `source_id`, `external_id`
- product identity: `account_id`, `nm_id`, `sku_id`, `vendor_code`,
  `product_name`, `product_identity`
- problem identity: `action_type`, `detector_code`, `problem_code`,
  `source_references`
- visible copy: `title`, `reason`, `next_step`
- severity and state: `priority`, `severity`, `status`, `review_status`
- money and trust: `expected_effect_amount`, `expected_impact_amount`,
  `priority_score`, `confidence`, `impact_type`, `trust_state`, `money_trust`
- task management: `assigned_to_user_id`, `assigned_to_display_name`,
  `assigned_to_avatar_url`, `deadline_at`, `last_comment`, `status_reason`
- SLA: `is_overdue`, `due_in_hours`, `sla_state`
- editability: `can_execute`, `can_update_status`, `can_update`,
  `can_update_reason`, `source_sync_state`
- guided solving: `guided_fix`, `allowed_actions`, `recheck_rule`
- evidence: `evidence_ledger`, `evidence_state`
- result fallback/context: `payload`, `raw`

Backend sources currently aggregated into this list:

- dynamic `problem_engine` problem instances;
- finance and money recommendations;
- money data blockers;
- data-quality actions;
- costs actions;
- checker/card-quality bridge items;
- persisted `unified_actions` and shadow task state;
- Product Doctor generated actions;
- beta/read-only module signals when permitted.

Frontend normalization:

- `fetchPortalActions` reads `GET /portal/actions`.
- `useActionCenterData` loads list rows, assignable users and result summaries.
- `ActionCenterPageContainer` adapts `PortalAction` into `ActionCenterItem`.
- Dynamic row result badges are computed from
  `GET /portal/results?source_module=problem_engine&limit=500` when matching
  result events exist.
- Embedded `payload.result_summary` remains a fallback when canonical result
  events are absent.

Current list-row loop coverage:

- Problem: visible through title, source, problem code, severity, trust and
  product identity.
- Evidence: row can open `Как посчитано?` when an evidence ledger exists.
- Guided action: row shows allowed action buttons or a guided-fix route.
- Task state: row exposes status, assignee/deadline/SLA and drawer entry.
- Re-check: row/drawer exposes re-check only for supported problem-like items.
- Result: row badge uses canonical result events first, fallback summary second.

Blocking contract gaps in the list:

- `allowed_actions` are string verbs, not fully described action objects. The
  UI must infer route, label and safety behavior from aliases.
- Static samples do not include enough dynamic-problem fields to prove the
  product-grade list contract.
- Some source rows can be mutable only through shadow state. `source_sync_state`
  exists, but the row does not always explain how far shadow state is from the
  source system.

## Current Task Drawer Contract

Canonical frontend detail view:

- `ActionCenterTaskDrawer.tsx`
- `ActionCenterDrawerContent.tsx`

Visible drawer sections:

1. Header: title, status, severity/priority, source, trust, product identity and
   impact badges.
2. `Карта решения`: evidence readiness, working screen/action, task save step,
   re-check/result step and blocked/read-only reason.
3. `Что произошло?`
4. `Почему платформа так решила?`
5. `На что влияет?`
6. `Что сделать сейчас?`
7. `Назначение и срок`
8. `Статус и комментарий`
9. `История`
10. `Повторная проверка`
11. `Результат после действия`

Result loading contract:

- Dynamic problems call
  `GET /portal/problems/{problem_instance_id}/results`.
- Non-dynamic persisted actions call
  `GET /portal/actions/{action_id}/results`.
- Dynamic problem result reads ensure a before snapshot when the drawer opens.
- Embedded `payload.result_summary` is fallback context, not the preferred
  ledger.

Update contract:

- If `source_module` and `source_id` exist, the frontend calls
  `PATCH /portal/actions/by-source`.
- Otherwise it calls `PATCH /portal/actions/{action_id}`.
- Payload fields include:
  - `account_id`
  - `status`
  - `comment`
  - `status_reason`
  - `assigned_to_user_id`
  - `deadline_at`
  - `event_type` in selected flows

Re-check contract:

- Dynamic problems call `POST /portal/problems/{problem_id}/recheck`.
- Checker fallback can call `PATCH /portal/actions/by-source` with
  `event_type: "recheck"`.

Status lifecycle contract:

Backend transition map:

- `new -> acknowledged | in_progress | ignored | postponed | blocked`
- `acknowledged -> in_progress | ignored | postponed | blocked`
- `in_progress -> done | blocked | postponed | ignored`
- `done -> resolved | reopened`
- `ignored -> reopened`
- `postponed -> in_progress | ignored | reopened`
- `blocked -> in_progress`
- `resolved -> reopened`
- `dismissed -> reopened`
- `reopened -> acknowledged | in_progress | ignored | postponed | blocked`

Current drawer blocker:

The frontend status selector is not transition-aware. `statusOptionsForAction`
returns almost all statuses for problem-like rows, while the backend validates
the transition graph above. The E2E mock currently accepts a direct `new ->
done` path. Real backend behavior rejects that path. This is the clearest gap
blocking reliable guided solving.

## Evidence Contract

Canonical backend model:

`EvidenceLedger`

- `value`
- `value_type`
- `confidence`
- `impact_type`
- `formula_human`
- `formula_code`
- `formula_id`
- `input_facts[]`
- `source_references[]`
- `trust_notes[]`
- `missing_data[]`
- `next_fix_action`
- `recheck_rule`
- `recheck_rule_human`
- `calculation_warnings[]`
- `money_trust`
- `is_synthetic`

Action Center evidence states:

- `full_evidence`
- `partial_evidence`
- `missing_evidence`
- `read_only_signal`

Frontend evidence behavior:

- `EvidenceDrawer` renders formula, facts, sources, trust notes, missing data,
  fix action and re-check rule.
- `ActionCenterEvidenceControls` provides inline summary and evidence drawer
  entry.
- Raw JSON is hidden in seller mode and only exposed in admin/debug context.
- Evidence is considered full only when the ledger has enough formula, input
  facts and source detail, and is not synthetic or warning-heavy.

Backend fallback behavior:

- `PortalActionRead` can synthesize an evidence ledger when a source action has
  expected impact but no canonical evidence.
- Synthetic ledgers are useful for compatibility, but they are not equivalent to
  product-grade evidence because formula/source/fact detail may be generic.

Evidence blockers:

- Unsafe price and promo-like actions depend on price-safety or margin evidence.
- The frontend can render unsafe actions disabled when evidence is missing.
- Server/client parity is not fully proven for all legacy/source-backed actions:
  the UI may block a risky route while the generic update endpoint can still
  accept status/comment changes.

## Allowed Actions By Problem Code

Seeded dynamic problem rules define these raw action verbs:

| problem_code | Seeded allowed actions | Default impact/trust |
| --- | --- | --- |
| `missing_cost_blocks_profit` | `upload_cost`, `map_sku`, `create_task`, `recheck`, `dismiss` | `data_blocker` / `blocked` |
| `negative_unit_profit` | `review_price`, `review_cost`, `review_ads`, `review_promo`, `create_task`, `recheck`, `dismiss` | `probable_loss` / `estimated` |
| `overstock_slow_moving` | `safe_promo`, `review_price`, `bundle`, `review_ads`, `review_content`, `create_task`, `recheck`, `dismiss` | `blocked_cash` / `estimated` |
| `low_stock_risk` | `plan_supply`, `reduce_promo`, `reduce_ads`, `create_task`, `recheck`, `dismiss` | `lost_sales_risk` / `provisional` |
| `ads_spend_without_profit` | `pause_ads`, `lower_ads`, `check_card_quality`, `review_bids`, `review_price`, `create_task`, `recheck`, `dismiss` | `probable_loss` / `provisional` |
| `promo_not_profitable` | `review_promo`, `reduce_promo`, `review_price`, `review_cost`, `create_task`, `recheck`, `dismiss` | `probable_loss` / `estimated` |
| `price_below_safe_margin` | `review_price`, `pricing_review`, `review_cost`, `create_task`, `recheck`, `dismiss` | `probable_loss` / `estimated` |
| `dead_stock` | `safe_promo`, `bundle`, `review_content`, `review_ads`, `create_task`, `recheck`, `dismiss` | `blocked_cash` / `estimated` |
| `fast_stock_depletion` | `plan_supply`, `reduce_promo`, `reduce_ads`, `create_task`, `recheck`, `dismiss` | `lost_sales_risk` / `provisional` |

Frontend/backend action aliasing currently collapses many verbs:

| Raw verbs | Canonical UI action |
| --- | --- |
| `review_price`, `pricing_review`, `wb_price_change` | `open_price_review` |
| `review_cost`, `open_costs`, `cost_review` | `upload_cost` |
| `review_promo`, `safe_promo`, `reduce_promo`, `bundle` and promo start/stop/create variants | `open_promo_planner` |
| `plan_supply`, `supply_review` | `open_supply_planner` |
| `review_ads`, `pause_ads`, `lower_ads`, `review_bids`, `reduce_ads`, `ads_review`, `ad_bid_change` | `open_ads_dashboard` |
| `check_card_quality`, `review_content`, `content_check`, `wb_content_apply` | `run_checker` |
| `trigger_recheck`, `mark_system_wait` | `recheck` |
| `data_fix` | `open_data_fix` |

Allowed-action blocker:

The seeded rules know the seller should do something specific, such as
`pause_ads`, `plan_supply`, `safe_promo` or `map_sku`. After normalization, the
row often only knows a broad destination such as ads dashboard, promo planner or
cost upload. This is not yet an exact guided action contract because it lacks:

- exact destination route and parameters;
- action owner module;
- prerequisite evidence;
- whether the action is local-only or writes to WB;
- preview/diff/confirm/audit requirements;
- success condition and expected re-check metric;
- disabled reason per action, not just per row.

## Result Ledger Contract

Primary endpoints:

- `GET /portal/results`
- `GET /portal/problems/{problem_instance_id}/results`
- `GET /portal/actions/{action_id}/results`
- `POST /portal/actions/{action_id}/result-event`

`GET /portal/results` filters:

- `action_id`
- `problem_instance_id`
- `problem_code`
- `nm_id`
- `source_module`
- `event_type`
- `result_status`
- `date_from`
- `date_to`
- `trust_state`
- `impact_type`
- `limit`
- `offset`

`ResultEvent` read fields:

- `id`
- `account_id`
- `action_id`
- `problem_instance_id`
- `problem_code`
- `source_module`
- `source_id`
- `external_id`
- `nm_id`
- `sku_id`
- `event_type`
- `outcome`
- `comparison`
- `product_identity`
- `before_snapshot`
- `after_snapshot`
- `snapshot_day`
- `message`
- `payload`
- `confidence`
- `calculation_note`
- `created_by`
- `created_at`
- `warnings`

Dynamic problem result service behavior:

- `ensure_problem_before_snapshot` creates a before snapshot when a problem
  timeline is opened.
- `create_problem_status_event` records status/action state.
- `create_problem_completed_event` records completion without claiming saved
  money.
- `create_problem_recheck_event` records re-check outcome and comparison.
- Problem-scoped result responses expose a professional timeline summary with
  problem identity, before/after snapshots, action events, re-check events,
  measured comparison, `result_status`, confidence, warnings, evidence ledger,
  correlation disclaimer, and canonical frontend links.
- `result_status=pending_data` means action/re-check activity exists but
  measured after-data is not available yet. `not_enough_data` means after-data
  exists but still cannot produce a measured comparison.
- `saved_money_claimed` remains false for expected impact and done tasks; it can
  only be true for a measured result with after-data, comparison metrics and
  visible confidence.

Required result disclaimer:

`Сравнение показывает связь по данным после действия, но не доказывает причинность само по себе.`

Result-ledger risks:

- Canonical dynamic problem results exist, but row-level result badges can still
  use embedded fallback summaries.
- Legacy action timelines depend on `action_id`; source-backed rows without a
  stable action id may not have an action-scoped ledger.
- Result improvement labels can be operational, such as stock-day improvement,
  and must not be read as saved money.
- `saved_money_claimed` is guarded in backend events, but stale fallback payload
  copy can still make impact look more certain than the ledger proves.

## Screenshots And UX Issues

Screenshots captured from the current E2E/browser flow:

- [Action Center task drawer](action_center_guided_control_baseline_assets/action_center_task_drawer.png)
- [Results problem timeline](action_center_guided_control_baseline_assets/results_problem_timeline.png)
- [Product360 problem preview](action_center_guided_control_baseline_assets/product360_problem_preview.png)

Action Center task drawer observations:

- The drawer contains the expected loop sections, including history, re-check
  and result.
- The full loop is spread across a long scroll. A seller cannot see evidence,
  exact action, status save, re-check and result at once.
- `Карта решения` improves orientation, but its usefulness depends on inferred
  `allowed_actions` and route aliases.
- Toast messages can overlay the top-right of the task surface.
- The dark sheet overlay hides list context while some background controls remain
  visually present.

Results page observations:

- The Results page can show the same problem timeline with before/action/recheck
  and the correlation disclaimer.
- Summary cards mix module/outcome counts with money-looking values such as
  `0₽`; this can be read as financial impact even when the timeline is
  operational or count-based.
- A single problem timeline can sit next to aggregate counters such as
  `Улучшилось 2`, because non-problem experiment/result events are counted in
  the same page context.

Product360 observations:

- Product360 can show the same problem and link back to the Action Center task.
- The problem card is dense and small compared with the task content.
- Evidence entry is present, but it competes with many other product page
  controls.
- The same problem can appear both as a business problem preview and as an
  action item, which creates duplicate entry points.

## Mismatches Between Seed Rules And API Samples

Static `actions_page_ok.json`:

- Contains finance and claims actions, but no dynamic `problem_engine` action.
- Does not explicitly include `allowed_actions`, `evidence_ledger`,
  `evidence_state`, `source_references` or `money_trust`.
- Uses `guided_fix.route_key` values such as `product_360_money` and
  `claims_case_from_signal`. Current frontend route mapping recognizes broader
  keys such as `data_fix`, `costs`, `product`, `claims`, `reputation` and
  `photo`, so these sample values do not prove exact navigation.

Static `action_update_ok.json`:

- Has `allowed_actions: []`.
- Uses synthetic/English fallback evidence text.
- Uses English re-check copy.
- Uses a generic money trust amount label.

Static `product_360_contract_ok.json`:

- Has empty business issues.
- Still contains English group titles such as `Profitability`, `Stock`,
  `Price`, `Ads/Promo` and `Data Blockers`.
- Does not demonstrate Product360 problem-to-ledger parity for dynamic problems.

E2E mock mismatch: `low_stock_risk`

- Mock uses `trust_state: confirmed` and `impact_type: confirmed_loss`.
- Seed default is `trust_state_default: provisional` and
  `impact_type_default: lost_sales_risk`.
- Mock allowed actions are `open_product`, `recheck`, `dismiss`.
- Seed actions are `plan_supply`, `reduce_promo`, `reduce_ads`, `create_task`,
  `recheck`, `dismiss`.

E2E mock mismatch: `missing_cost_blocks_profit`

- Mock uses `open_data_fix`, `upload_cost`, `recheck`.
- Seed actions are `upload_cost`, `map_sku`, `create_task`, `recheck`,
  `dismiss`.
- The mock is useful for Data Fix linkage, but it does not prove mapping/SKU
  guided work or dismiss/task handling.

E2E mock mismatch: `overstock_slow_moving`

- Mock uses `impact_type: opportunity`.
- Seed default is `impact_type_default: blocked_cash`.
- Mock allowed actions are mostly `safe_promo` and `recheck`.
- Seed actions include promo, price, bundle, ads, content, task and dismiss.

Frontend/backend tests:

- Some contract fixtures use confirmed-loss examples for problems whose seed
  semantics are estimated/provisional.
- Backend unit fixtures still use English problem copy and re-check copy in
  local problem-engine tests. The UI adapter repairs some seller copy, but the
  fixture itself is not the seller-facing contract.

## Impact And Trust Semantic Risks

Confirmed loss:

- Should represent reliable measured loss, not high confidence alone.
- Current mocks/tests sometimes use `confirmed_loss` for low-stock or negative
  unit profit examples where seeds use `lost_sales_risk`, `probable_loss`,
  `estimated` or `provisional`.

Blocked cash:

- Overstock and dead-stock seeds use `blocked_cash`, which should not be summed
  into saved money or confirmed loss.
- If adapter/fallback data reclassifies these as opportunity, the row can look
  less urgent or more speculative than intended.

Opportunity:

- Legacy/synthetic fallback ledgers can classify expected effects as
  opportunity even when no canonical result ledger exists.
- That is useful for older actions, but not enough for professional guided
  solving.

Money trust override:

- Frontend impact bucketing reads `money_trust.impact_kind` first when present.
- A stale or synthetic `money_trust` payload can override safer seed semantics.

Result confidence:

- `effect_summary` can mark improved/worse based on before/after event snapshots
  even when full finance windows are missing.
- UI copy includes the correlation disclaimer, but row badges can still feel
  definitive.

Operational outcomes:

- Stock-day and order-count improvements are not saved money.
- These outcomes need labels that keep them separate from confirmed ruble impact.

## Guided Solving Blockers

These gaps block the target loop from being fully product-grade:

1. Frontend status choices do not enforce backend transition rules. A seller can
   choose a state path the real API rejects.
2. The E2E mock accepts invalid status transitions, so current acceptance tests
   can pass while the real backend flow fails.
3. `allowed_actions` are strings rather than typed guided-action objects with
   route, prerequisites, disabled reason, confirmation requirements and success
   metric.
4. Seed-specific verbs collapse into broad module routes, losing exact action
   intent.
5. Static endpoint fixtures do not prove the dynamic problem list, evidence,
   allowed-action or result-ledger contracts.
6. Mock datasets overstate impact/trust in several problem examples.
7. Result rows can fall back to embedded summaries, so canonical ledger coverage
   is not guaranteed for every visible result badge.
8. Legacy/source-backed actions can use shadow state. Drift from the source
   module is possible and not always explained at the point of action.
9. Evidence fallback ledgers can make old actions render as explainable even
   when the proof is generic/synthetic.
10. Price/promo safety is UI-visible, but action-level server/client parity is
    not proven for every legacy/write-capable path.
11. Product360 and Results linkage exists, but fixtures lag behind the current
    dynamic problem workflow.
12. UX density makes the loop hard to scan: the drawer has all sections, but the
    seller must scroll through a long task surface to connect them.

## Current Verification

The baseline screenshots were captured from the current Playwright Action
Center flow and copied to
`docs/action_center_guided_control_baseline_assets/`.

Frontend checks:

- `npm run test:action-center-contract` - passed.
- `npm run test:action-center-filters` - passed.
- `npm run test:action-center-backend-contract` - passed.
- `npm run test:problem-copy` - passed.
- `npm run test:problem-loop` - passed.
- `npm run test:problem-rules-admin` - passed.
- `npx playwright test e2e/action-center-professional.spec.ts --project=desktop`
  - passed: 8 tests.
- `npx playwright test e2e/navigation.spec.ts --project=mobile -g "mobile Action Center"`
  - passed: 1 test.
- `npm run build` - passed.

Backend checks:

- `.venv/bin/python -m pytest -q backend/tests/unit/test_result_tracking_service.py backend/tests/unit/test_portal_service.py backend/tests/unit/test_problem_engine_initial_rules.py backend/tests/unit/test_problem_engine_portal_integration.py backend/tests/api/test_portal_action_center_contract.py backend/tests/api/test_action_center_result_ledger_integration.py`
  - passed: 122 tests, 1 warning from `passlib`/Python `crypt`
    deprecation.

Non-fatal command output:

- Playwright emitted `NO_COLOR` ignored because `FORCE_COLOR` is set.
- Build emitted existing Vite/TanStack unused-import warnings from external
  dependencies and Lovable context skip notices.
