# Action Center Product-Grade Rollout Report

Date: 2026-07-07

## Executive Summary

Action Center has moved from a mixed issue list toward a professional work
center. The product loop is now represented end to end:

`Проблема -> доказательства -> действие -> статус/история -> повторная проверка -> результат`

The strongest path is dynamic `problem_engine` problems. They have canonical
problem instances, evidence ledgers, allowed actions, status history, re-checks
and result timelines. Legacy, checker, finance, data quality and cost actions
are adapted into the same frontend contract and remain backward compatible.

## 1. UI Layout

Action Center is now structured as an operational desk instead of a raw list.

- Top work summary cards show:
  - `Срочно`
  - `В работе`
  - `Ждёт перепроверки`
  - `Просрочено`
  - `Результат есть`
- Daily digest shows:
  - new today;
  - due today;
  - overdue;
  - re-check completed;
  - improved and worse result signals.
- Weekly summary shows closed tasks, reopened tasks, measured outcomes and
  handled estimated opportunities.
- Trust-aware impact summary separates:
  - confirmed loss;
  - probable risk;
  - blocked cash;
  - growth opportunity;
  - data blockers.
- The UI deliberately does not combine those categories into fake saved money.
- Rows show priority/severity, title, product identity, source, trust, impact,
  evidence state, status, assignee, deadline/SLA state, result status and next
  available action.
- Seller users do not see beta/test-only rows by default. Admin users can enable
  `Показать бета/тестовые сигналы`.
- Desktop keeps summary, filters, rows and side drawer. Mobile/tablet use compact
  cards, collapsed filters and a full-screen task sheet.

## 2. Task Drawer

The drawer is the canonical task detail view. Inline dead detail state has been
removed from the workflow.

Drawer sections follow the professional task story:

1. Header: title, status, severity/priority, source, product identity, trust and
   impact badges.
2. `Что произошло?`
3. `Почему платформа так решила?`
   - short evidence summary;
   - `Как посчитано?`.
4. `На что влияет?`
   - impact amount when available;
   - trust explanation;
   - explicit warning that expected impact is not confirmed saved money.
5. `Что сделать сейчас?`
   - primary allowed action;
   - secondary allowed actions;
   - disabled/read-only reason when applicable.
6. `Назначение и срок`
   - assignee control;
   - deadline control;
   - overdue warning.
7. `Статус и комментарий`
   - status control;
   - comment;
   - save.
8. `История`
   - status changes;
   - comments;
   - assignment changes;
   - deadlines;
   - re-checks;
   - result events.
9. `Повторная проверка`
   - current re-check state;
   - re-check button;
   - last run result.
10. `Результат после действия`
   - before snapshot;
   - action events;
   - after snapshot;
   - measured comparison;
   - correlation disclaimer.

The drawer loads canonical result timelines from
`/portal/problems/{problem_instance_id}/results` for dynamic problems and
`/portal/actions/{action_id}/results` for legacy actions when an action id
exists. Embedded `payload.result_summary` is treated as fallback context.

## 3. Status Lifecycle

Backend status validation is centralized for Action Center updates.

Canonical statuses:

- `new`
- `acknowledged`
- `in_progress`
- `done`
- `postponed`
- `ignored`
- `blocked`
- `resolved`
- `dismissed`
- `reopened`

Allowed transitions:

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

For `problem_engine`, `problem_instances.status` is canonical. For mutable
legacy/unified actions, source status is updated directly. When a source is
read-only, Action Center uses shadow state and exposes source sync state.

Every update is normalized into semantic event types such as:

- `status_changed`
- `assigned`
- `deadline_changed`
- `comment_added`
- `dismissed`
- `postponed`
- `blocked`
- `recheck_requested`
- `recheck_completed`
- `result_measured`
- `reopened`

Moving a task to `done` creates an action completed/result event, but does not
claim saved money.

## 4. Assignment And Deadline Tracking

Action Center update payloads support:

- `assigned_to_user_id`
- `deadline_at`
- `comment` / `last_comment`
- `status_reason`
- `review_status`
- `event_type`

The backend exposes assignable users through `/portal/assignable-users`.

Action responses or the frontend adapter expose SLA fields:

- `is_overdue`
- `due_in_hours`
- `sla_state`: `ok | due_soon | overdue | no_deadline`

Rows show:

- assignee name/avatar fallback, or `Не назначено`;
- `Сегодня`, `Завтра`, `Просрочено`, or `Без срока`;
- quick filters for mine, unassigned, overdue and due today.

Manager/admin bulk controls are present in the frontend and execute through the
same update contract. They are intentionally scoped to safe management actions:
assign, set deadline, move to `in_progress`, and dismiss with reason.

## 5. Evidence Transparency

Every Action Center item is adapted to an evidence state:

- `full_evidence`
- `partial_evidence`
- `missing_evidence`
- `read_only_signal`

Rows show:

- `Как посчитано?` when evidence exists;
- `Доказательств недостаточно` for partial or missing evidence;
- read-only signal state for beta/internal signals.

Evidence drawer shows seller-readable fields:

- formula;
- input facts;
- source table/service/endpoint;
- date range;
- row count;
- missing data;
- trust notes;
- calculation warnings;
- re-check rule.

Raw JSON is hidden from seller mode and only shown behind admin/debug mode.

Actions are blocked or rendered read-only when evidence is missing and the
operation is unsafe. Price and promo recommendations require price-safety
evidence before enabling risky downstream actions.

## 6. Result Ledger

Dynamic problem result tracking is now canonical through `ResultEvent` records
linked to:

- `problem_instance_id`
- `problem_code`
- `source_module`
- `nm_id`

The ledger supports:

- before snapshot;
- status/action events;
- `action_completed`;
- `recheck_result`;
- after snapshot;
- measured comparison;
- confidence;
- warnings;
- correlation disclaimer.

`/portal/problems/{problem_instance_id}/results` ensures a before snapshot when
the drawer opens. Moving to `in_progress` or `done` can create status/completion
events. Re-check creates re-check result events and can resolve or reopen the
problem according to rule logic.

The UI result badges use shared status labels:

- `ждём данных`
- `есть улучшение`
- `стало хуже`
- `без изменений`
- `нет данных`

The result copy uses the required disclaimer:

`Сравнение показывает связь по данным после действия, но не доказывает причинность само по себе.`

No UI or result event should call expected impact saved money unless after-data
is measured and confidence is visible.

## 7. Filters And Saved Views

Action Center supports search across:

- title;
- explanation;
- recommendation;
- `nm_id`;
- vendor code;
- problem code;
- assignee.

Filters include:

- status;
- source module;
- severity;
- priority;
- trust state;
- impact type;
- problem code;
- assignee;
- deadline/SLA state;
- result status;
- beta/test-only visibility.

Sorting supports:

- severity/priority;
- money impact;
- deadline;
- `last_seen_at`;
- `last_status_changed_at`;
- result status.

Saved views are represented in URL-compatible state:

- `Все`
- `Сегодня`
- `Мои задачи`
- `Без ответственного`
- `Просрочено`
- `Блокеры данных`
- `Ждёт перепроверки`
- `Улучшилось`
- `Стало хуже`

## 8. Data Fix, Product360 And Results Linkage

Data Fix:

- Links dynamic data blockers to Action Center tasks.
- Shows affected rows, source facts, missing data and safe fix controls.
- Reads canonical problem results with `fetchProblemResults`.
- Shows status/re-check linkage back to the task.

Product360 / Product Doctor:

- Uses Russian seller labels.
- Groups business problems by area.
- Opens evidence.
- Links back to full Action Center task.
- Reads canonical problem result ledger for status/result preview.

Results:

- Can filter and group by dynamic problem identity.
- Renders problem timelines with before/action/re-check/after comparison.
- Keeps saved-money guardrails: estimated impact remains estimated until
  measured after-data exists.

## 9. Backend APIs Used

Primary Action Center APIs:

- `GET /portal/actions`
  - query: `account_id`, `date_from`, `date_to`, `status`, `source_module`,
    `priority`, `nm_id`, `action_type`, `problem_code`, `trust_state`,
    `impact_type`, `include_beta`, `limit`, `offset`.
  - `include_beta=true` requires admin role.
- `GET /portal/assignable-users`
  - returns account/team users with role and display name.
- `PATCH /portal/actions/by-source`
  - source-aware update path for dynamic problems and source-backed actions.
- `PATCH /portal/actions/{action_id}`
  - legacy/unified action update path.
- `POST /portal/problems/{problem_id}/recheck`
  - seller/admin re-check endpoint for dynamic problem instances.
- `GET /portal/results`
  - filters: `action_id`, `problem_instance_id`, `problem_code`, `nm_id`,
    `source_module`, `event_type`, `result_status`, `date_from`, `date_to`,
    `trust_state`, `impact_type`, `limit`, `offset`.
- `GET /portal/problems/{problem_instance_id}/results`
  - canonical timeline for a dynamic problem.
  - summary includes problem identity, before snapshot, action events,
    re-check events, after snapshot, measured comparison, result status,
    confidence, warnings, evidence ledger, correlation disclaimer and frontend
    links.
- `GET /portal/actions/{action_id}/results`
  - canonical timeline for legacy/unified actions.
- `POST /portal/actions/{action_id}/result-event`
  - manual/legacy result event creation path.

Related entry points:

- `GET /portal/products/{nm_id}` for Product360.
- Data Fix endpoints used by `DataFixWorkbench` for guided fixes and re-checks.
- Problem engine runner/admin APIs for evaluating and seeding dynamic problems.

## 10. Migrations Added

Relevant rollout migrations:

- `20260619_000036_unified_action_task_fields.py`
  - Adds assignment, deadline, review status, comments, close/dismiss timestamps
    and indexes to `unified_actions`.
- `20260706_000056_dynamic_problem_engine.py`
  - Adds metric catalog, problem definitions, problem rule versions,
    `problem_instances`, `problem_instance_history` and admin rule test runs.
- `20260706_000057_seed_dynamic_problem_metrics.py`
  - Seeds dynamic problem metric catalog.
- `20260706_000058_seed_initial_dynamic_problem_rules.py`
  - Seeds initial dynamic problem rules.
- `20260706_000059_problem_rule_admin_audit.py`
  - Adds admin rule audit support.
- `20260706_000060_problem_evaluation_run_logs.py`
  - Adds evaluation run logging.
- `20260706_000061_seed_remaining_dynamic_problem_rules.py`
  - Seeds remaining dynamic rules.
- `20260707_000062_problem_result_events.py`
  - Links `result_events` to `problem_instance_id` and `problem_code` and adds
    supporting indexes.

No additional database migration was needed for this final report-only step.

## 11. Tests Added And Results

New acceptance coverage:

- `frontend/e2e/action-center-professional.spec.ts`
  - dynamic problem row badges/evidence/result badge;
  - drawer assignment, deadline, status, comment and refresh persistence;
  - done status creates result event without saved-money claim;
  - re-check creates event and updates result badge;
  - data blocker opens Data Fix and suppresses negative-profit claim when cost is
    missing;
  - unsafe promo disabled without margin evidence;
  - beta/test-only hidden for seller and visible with admin toggle;
  - Russian seller copy and raw JSON hidden by default.
- `frontend/e2e/mock-api.ts`
  - stateful no-network Action Center mock for the professional workflow.

Relevant supporting tests and checks:

- `frontend/tests/actionCenterContract.test.mjs`
- `frontend/tests/actionCenterFilters.test.mjs`
- `frontend/scripts/check-problem-ux-copy.mjs`
- `frontend/scripts/check-problem-loop-acceptance.mjs`
- `backend/tests/unit/test_result_tracking_service.py`
- `backend/tests/unit/test_portal_service.py`

Latest verification run:

- `npx playwright test e2e/action-center-professional.spec.ts --project=desktop`
  - 8 passed.
- `npx playwright test e2e/navigation.spec.ts --project=mobile -g "mobile Action Center"`
  - 1 passed.
- `npm run test:action-center-contract`
  - passed.
- `npm run test:action-center-filters`
  - passed.
- `npm run test:action-center-backend-contract`
  - passed.
- `npm run test:problem-copy`
  - passed.
- `npm run test:problem-loop`
  - passed.
- `.venv/bin/python -m pytest -q tests/unit/test_result_tracking_service.py tests/unit/test_portal_service.py`
  - 80 passed.
- `npm run build`
  - passed.
  - Latest run did not emit the previous Vite chunk-size warning.

## 12. Known Limitations

- Dynamic `problem_engine` problems are the cleanest canonical path. Some
  legacy/checker/finance/cost actions still rely on adapter normalization and
  shadow status when the source cannot be updated directly.
- Bulk actions are implemented as manager/admin UI workflows over the existing
  update contract, not as a dedicated portal bulk API.
- Result timelines depend on source freshness. A task can be `done` while the
  result remains `ждём данных` until after-data is available.
- Before/after comparison is correlation only. The platform intentionally does
  not claim causality.
- Some result/detail summaries may still include fallback embedded payload data
  when no canonical ledger exists for older actions.
- Large Action Center and app chunks should still be reviewed later for code
  splitting if route payload grows again.
- Price, promo, ads and WB write flows remain guarded; dangerous changes should
  continue to require preview/diff/confirm/audit in their destination modules.

## 13. Manual QA Checklist

Use a seller account with dynamic problem rules enabled and fresh enough source
data to evaluate at least one product-level problem.

1. Create or evaluate a dynamic problem.
   - Run the problem engine for one account/product.
   - Confirm a `problem_instance` is created with title, status, evidence and
     allowed actions.
2. See it in Action Center.
   - Open `Action Center`.
   - Confirm the row is visible.
   - Check severity, source, trust, impact, status, assignee/deadline and result
     badge.
3. Open evidence.
   - Click `Как посчитано?`.
   - Confirm formula, input facts, sources, date range, row count, missing data,
     trust notes and warnings are readable.
   - Confirm raw JSON is hidden for seller mode.
4. Assign user.
   - Open `Открыть задачу`.
   - Select an assignee.
   - Save.
   - Refresh the page and confirm the assignee persisted.
5. Set deadline.
   - Set a deadline in the drawer.
   - Save.
   - Refresh and confirm deadline/SLA state persists.
   - Test an overdue date and confirm row warning.
6. Change status.
   - Move `new -> in_progress`.
   - Add a comment.
   - Save and refresh.
   - Confirm status, comment and history event persist.
7. Re-check.
   - Click re-check from the drawer.
   - Confirm a re-check event appears in history/result timeline.
   - Confirm the problem resolves or reopens according to rule result.
8. See result timeline.
   - Move task to `done`.
   - Confirm result section shows before snapshot, action event and waiting state
     if after-data is missing.
   - After fresh data is available, confirm measured comparison and confidence.
   - Confirm no expected impact is called saved money.
9. Open same problem from Product360.
   - Open the product page.
   - Find `Проблемы товара`.
   - Confirm same problem status/result preview appears.
   - Open the Action Center task link.
10. Open same result from Results page.
    - Open `/results?problem_instance_id=<id>`.
    - Confirm the same problem timeline appears.
    - Verify before/action/re-check/after comparison matches the Action Center
      drawer.

Rollout is acceptable when the same problem can be followed from every entry
point through:

`Проблема -> доказательства -> действие -> статус/история -> повторная проверка -> результат`.

## 14. Follow-Up UI/UX Copy Audit

Follow-up audit on 2026-07-07 checked the seller-visible problem workflow again.
The main rule is now stricter: route names, backend keys and test names may stay
English internally, but normal seller-facing copy should be Russian and should
describe the user action, not the engineering module name.

Fixed seller-visible copy:

- `Action Center` -> `Центр действий` in navigation, dashboard hints, Doctor
  links, Data Fix linkage and result module labels.
- `Data Fix` -> `исправление данных` where it is shown as the next user action.
- `Checker` -> `проверка карточки/проверка карточек` in Product360,
  Product Doctor, cards, settings and fallback module messages.
- `Baseline` -> `До действия` on the Results page.
- `auto-merge выключен` -> `автообъединение выключено`.
- Seller-facing result/history load errors now use safe Russian fallback text
  instead of raw backend English messages.
- Sidebar beta badges now use Russian labels: `Бета`, `Безопасно`, `Запись`,
  `Чтение`, `Черновик`.
- Adjacent seller entry points were aligned as well: `Photo Studio` -> `Фотостудия`,
  `Grouping Beta` -> `Группировка`.

Internal English that intentionally remains:

- route paths such as `/action-center`, `/data-fix`, `/results`;
- API keys and TypeScript identifiers such as `source_module`, `problem_code`,
  `isCheckerProblemBridge`;
- acceptance test names and source comments where they do not reach seller UI;
- marketplace/domain abbreviations such as `WB`, `API`, `nmID`.

Latest follow-up verification:

- `npm run test:problem-copy` passed.
- `npm run test:problem-loop` passed.
- `npm run test:action-center-contract` passed.
- `npm run test:action-center-filters` passed.
- `npm run test:action-center-backend-contract` passed.
- `npx playwright test e2e/action-center-professional.spec.ts --project=desktop`
  passed: 8 tests.
- `npx playwright test e2e/navigation.spec.ts --project=desktop` passed:
  5 passed, 1 mobile-only test skipped.
- `npx playwright test e2e/navigation.spec.ts --project=mobile -g "mobile Action Center"`
  passed: 1 test.
- `.venv/bin/python -m pytest -q tests/unit/test_result_tracking_service.py tests/unit/test_portal_service.py`
  passed: 80 tests.
- `npm run build` passed. Latest run did not emit the previous Vite chunk-size
  warning.

## 15. WB Card Write Flow Audit

Follow-up audit on 2026-07-09 checked the Action Center -> Checker -> WB card
edit path against the official WB Content API documentation.

Official WB API constraints for `POST /content/v2/cards/update`:

- Uses the Content API token and `https://content-api.wildberries.ru`.
- The request body is an array of listing snapshots.
- The listing is overwritten on update, so unchanged supported fields must be
  preserved in the request.
- Required fields include `nmID`, `vendorCode` and `sizes`.
- Supported edit fields include `kizMarked`, brand/title/description,
  dimensions, characteristics and sizes.
- The method cannot update/delete size SKUs, `photos`, `video`, `tags`, or item
  prices.
- Successful `200` response can still leave a draft/error state; rejected
  listing edits should be checked through failed listing errors.
- Current documented limit for card update is 10 requests per minute with a
  6-second interval and burst 5.

Platform flow confirmed:

- Action Center content/card problems send the seller to `/checker/{nm_id}`.
- Checker keeps local fix and WB write as separate actions.
- Normal `Применить` saves the fix/status locally and does not mutate WB.
- `Отправить в WB` first requests preview diff, then requires explicit
  confirmation.
- Backend write path uses `CardQualityAnalysisService._submit_wb_card_update`
  and sends `POST /content/v2/cards/update`.

Hardening added:

- WB update payload now keeps only official update top-level fields before
  submission.
- Read-only/non-updatable fields such as subject metadata, media, tags and
  update timestamps are removed from the WB update payload.
- Existing `kizMarked` state is preserved from the stored card model when an
  older snapshot does not contain it.
- Connector inventory now includes `product_cards.update_card`.
- Unit coverage now checks official-field sanitization and `kizMarked`
  preservation.

Verification:

- `.venv/bin/python -m pytest -q tests/unit/test_card_quality_service.py`
  passed: 39 tests.
- `.venv/bin/python -m pytest -q tests/unit/test_card_quality_service.py tests/unit/test_result_tracking_service.py tests/unit/test_portal_service.py`
  passed: 119 tests.
- `npm run test:action-center-contract` passed.
- `npm run test:action-center-filters` passed.
- `npm run test:action-center-backend-contract` passed.
- `npm run test:problem-copy` passed.
- `npm run test:problem-loop` passed.
- `npx playwright test e2e/action-center-professional.spec.ts --project=desktop`
  passed: 8 tests.
- `npx playwright test e2e/navigation.spec.ts --project=mobile -g "mobile Action Center"`
  passed: 1 test.
- `npm run build` passed.

## 16. Problem-Solving UI/UX Follow-Up

Follow-up audit on 2026-07-09 checked the seller problem-solving flow in the
browser and tightened the parts where the next action could still feel implicit.

Action Center drawer improvements:

- Added `Карта решения` near the top of the task drawer.
- The map shows the operational sequence:
  - evidence readiness;
  - concrete working screen/action;
  - status/comment/assignment save step;
  - re-check/result step.
- Blocked or read-only actions now surface the blocked reason inside that map,
  instead of leaving the seller to infer it from disabled controls.
- The map deliberately points to `Как посчитано?` without duplicating formulas,
  so evidence remains canonical in one place.

Problem rule / formula UX improvements:

- Added `Карта качества правила` to the create-rule wizard.
- The checklist validates, before creation, whether the new problem has:
  - seller-facing title/explanation/next step;
  - at least one detection condition;
  - enough evidence metrics for `Как посчитано?`;
  - price/promo safety metrics when price or promo actions are selected;
  - a re-check rule and closing metric;
  - a draft rule version.
- This makes new problem detection formulas easier to review before they reach
  sellers.

Verification:

- `npx playwright test e2e/action-center-professional.spec.ts --project=desktop`
  passed: 8 tests.
- `npx playwright test e2e/navigation.spec.ts --project=mobile -g "mobile Action Center"`
  passed: 1 test.
- `npm run test:action-center-contract` passed.
- `npm run test:action-center-filters` passed.
- `npm run test:action-center-backend-contract` passed.
- `node tests/problemRulesAdminPanel.test.mjs` passed.
- `npm run test:problem-loop` passed.
- `npm run test:problem-copy` passed.
- `npm run build` passed.

## 17. Admin Problem Rules Publish Gate

Follow-up hardening on 2026-07-10 made the admin rule publisher responsible for
preventing confusing or non-actionable seller problems before they can become
active.

Backend publish gates now require:

- seller-facing title, explanation and exact next step;
- detection condition;
- impact/trust semantics;
- evidence formula and selected evidence metrics;
- `solve_map_template` with ordered seller steps;
- human-readable re-check rule;
- at least one primary safe action that opens a real work screen;
- successful backtest with sample card preview;
- missing-data rate metadata from the backtest.

Unsafe price or promo actions still require margin/cost/safe-price metrics. A
rule whose backtest is missing a required metric for more than half of checked
products is blocked before publish.

Admin UI improvements:

- New draft versions generate a basic `solve_map_template`.
- The create-rule checklist now includes the solution map requirement.
- Publish blockers mirror backend gates for missing solve map, missing evidence,
  missing seller preview, missing primary safe action and price/promo safety.
- Backtest preview now shows the seller-facing Action Center row/card and drawer
  preview before the publish confirmation.

Custom admin-authored problem codes now carry the solve-map template through the
problem evaluator into the portal Action Center payload, so published rules do
not fall back to generic `open product` semantics.

Verification:

- `.venv/bin/python -m pytest -q backend/tests/unit/test_problem_engine_admin_rules.py backend/tests/acceptance/test_dynamic_problem_engine_product_acceptance.py -q`
  passed: 16 tests.
- `npm run test:problem-rules-admin` passed.
- `npm run test:problem-loop` passed.
- `npm run test:problem-copy` passed.
- `npm run test:action-center-backend-contract` passed.
- `npm run build` passed.

## 18. Guided Control Panel Verification

Follow-up verification on 2026-07-10 checked the full guided control-panel
behavior with deterministic no-network frontend fixtures and backend-backed
problem/result/checker suites.

Frontend hardening:

- Target workbench routes now preserve numeric query context such as
  `problem_instance_id=42` and `nm_id=245405620` instead of requiring quoted
  router search values.
- The same normalization is used by Action Center, Data Fix, Costs, Checker,
  Product360, Ads, Results and Stock Control route search parsing.
- No primary solve action should lose task context when opened from a backend
  `solve_map` href.

No-network E2E coverage now verifies:

- low stock is shown as `lost_sales_risk`, opens seller evidence, points to the
  supply planner, persists assignment/deadline/status and updates result after
  re-check;
- missing cost opens Data Fix, suppresses negative-profit claims, continues into
  the Costs missing-cost workbench, appends task history and shows recalculated
  margin metrics;
- overstock blocks promo without safe margin, shows checker/content review as
  the alternative path, and compares days of stock plus sales velocity;
- checker/card-quality keeps local fix separate from WB write, requires preview
  and explicit confirmation for WB, and leaves the result waiting for WB
  validation;
- Action Center, Product360 and Results show the same problem status/result.

Verification:

- `npx playwright test e2e/action-center-professional.spec.ts --project=desktop`
  passed: 14 tests, 2 desktop-skipped mobile checks.
- `npx playwright test e2e/action-center-professional.spec.ts --project=mobile`
  passed: 2 tests, 14 mobile-skipped desktop workflow checks.
- `.venv/bin/python -m pytest -q backend/tests/acceptance/test_dynamic_problem_engine_product_acceptance.py backend/tests/unit/test_problem_engine_portal_integration.py backend/tests/unit/test_result_tracking_service.py backend/tests/unit/test_card_quality_service.py`
  passed: 95 tests.
- `npm run test:action-center-contract` passed.
- `npm run test:action-center-filters` passed.
- `npm run test:action-center-backend-contract` passed.
- `npm run test:problem-loop` passed.
- `npm run build` passed.
