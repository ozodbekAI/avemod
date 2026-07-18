# Professional Platform Audit: Dynamic Problem Engine and Action Center

Date: 2026-07-07

## Executive Verdict

Dynamic Problem Engine is technically strong and already connected to the main
product surfaces: Action Center, Product360/Product Doctor, Data Fix, Money,
Checker evidence drawers, admin rule catalog, re-checks, and backend result
tracking.

The remaining risk is product-grade consistency, not missing core backend
plumbing. Today the platform is close to a professional operational control
center, but a seller can still feel several different products inside one
system:

- Action Center mostly speaks Russian and has task/result flow.
- Product Doctor and reusable problem cards still contain English labels.
- Data Fix is a guided Russian workbench and feels more mature.
- Result tracking exists, but dynamic problem results are partly embedded into
  Action Center payloads instead of being a first-class result ledger for every
  dynamic problem.
- Some detail UI state exists but is not reachable from the visible interface.

Target product standard:

`problem -> evidence -> allowed action -> status/history -> re-check -> result`

Every page must follow this same loop.

## What Already Fits The Platform

### Backend

- `problem_instances` are exposed as normal Action Center actions through
  `PortalService`.
- Dynamic problem status is canonical. Action Center status updates write back
  to `problem_instances.status`.
- `problem_instance_history` stores status changes, comments, assignment,
  dismiss and re-check events.
- Evidence ledger is present in dynamic problem payloads and includes formula,
  facts, sources, missing data, trust notes and warnings.
- `ProblemEvaluationRunnerService` supports account/product/all-product
  evaluation, manual admin trigger and seller re-check endpoint.
- `ResultTrackingService` exists and correctly avoids fake causality. It uses
  before/after comparison as correlation only.
- Price safety exists for price decrease, promo and price increase
  recommendations.
- Feature flags exist for gradual rollout and legacy fallback.

### Frontend

- Action Center can show dynamic problems, filters by source/problem/trust/
  impact/status, update status, re-check, open evidence and open a task drawer.
- Action Center task drawer now has a result panel with status flow, money at
  risk, before/after comparison and a correlation disclaimer.
- Product360 has a Product Doctor section that groups dynamic business issues.
- Data Fix has a real workbench: issue detail, affected rows, source facts,
  fix form, preview/apply path, audit and re-check.
- EvidenceDrawer is reused across Action Center, Data Fix, Checker, Product360
  and Money.
- Admin Problem Rules UI exists and supports creation, formula building,
  evidence template, validation, backtest and publish controls.

## Professional-Grade Gaps

### P0: Seller Language Must Be Unified

The seller-facing platform should not mix English, Uzbek and Russian in the same
workflow. Current examples:

- `SellerProblemUX.tsx` uses labels like `What happened?`, `Can I fix it here?`
  and `Confirmed money impact`.
- `ProductDoctorSection.tsx` uses `Product Doctor / Business Issues`,
  `Profitability`, `Stock`, `Data Blockers`, `open`, `resolved`,
  `No issues in this group`.
- Evidence button shows all three languages in one button:
  `How calculated? / Qayerdan keldi? / Как посчитано?`.

Professional target:

- Seller UI default language: Russian.
- Uzbek can be used in product notes/support, but not mixed inside controls.
- Admin/debug copy can be technical, but seller copy must be simple and direct.

Required replacement examples:

| Current | Target |
| --- | --- |
| Product Doctor / Business Issues | Проблемы товара |
| Profitability | Прибыльность |
| Stock | Остатки |
| Price | Цена |
| Ads/Promo | Реклама и промо |
| Data Blockers | Блокеры данных |
| What happened? | Что произошло? |
| Why do we think so? | Почему платформа так решила? |
| How much does it affect? | На что влияет? |
| Confirmed or estimated? | Это факт или оценка? |
| What should I do now? | Что сделать сейчас? |
| Can I fix it here? | Можно исправить здесь? |
| How will it be rechecked? | Как проверим повторно? |
| How calculated? / Qayerdan keldi? / Как посчитано? | Как посчитано? |

### P0: Action Center Detail Toggle Is Not Reachable

`action-center.tsx` has `detailsOpen` state and a rich inline details block, but
there is no visible control that calls `setDetailsOpen`. The seller can open the
drawer, but the inline expanded workflow is effectively dead UI.

Decision needed:

- either remove the dead inline block and make the drawer the only detail view;
- or add a clear `Подробнее` / `Свернуть` button on each row.

Recommended choice: keep the drawer as the canonical task detail, because it is
more professional and already contains result/evidence/action sections.

### P0: Result Ledger Should Become Canonical For Dynamic Problems

Action Center currently receives `result_summary` inside dynamic problem action
payloads. This is useful, but it is not the same as a first-class result ledger.

Professional target:

- every dynamic problem should have a canonical result timeline:
  - before snapshot;
  - action started;
  - action completed;
  - re-check result;
  - after snapshot;
  - measured comparison;
  - confidence/correlation note.
- `/results` should be able to filter by `problem_instance_id`,
  `problem_code`, `nm_id`, `source_module=problem_engine`.
- Action Center, Product360 and Results page should all read the same result
  ledger.

Short-term state is acceptable for MVP, but this must be hardened before calling
the platform "professional-grade".

### P0: Never Present Estimated Risk As Saved Money

Backend is already careful: expected impact is not converted to saved money
until after data is measured. UI must keep this rule everywhere.

Professional display rules:

- `confirmed_loss` may use strong red money styling.
- `probable_loss`, `blocked_cash`, `lost_sales_risk`, `opportunity` must look
  visually different from confirmed loss.
- before/after charts must say correlation, not proof.
- no result card should say "saved" unless it is backed by measured after-data
  and the confidence label is visible.

### P1: Product360 Needs The Same Result Layer As Action Center

Product Doctor cards currently show problem, evidence and next action. They do
not yet show the same before/after result story as the Action Center drawer.

Professional target:

- Product360 problem card shows:
  - current status;
  - last status change;
  - re-check state;
  - result badge: `ожидает данных`, `есть улучшение`, `стало хуже`,
    `нет данных`;
  - link to full Action Center task.

### P1: Data Fix Is Good, But Labels Should Match Dynamic Problems

Data Fix workbench is the strongest guided flow. It already shows:

- what is wrong;
- why the platform thinks so;
- affected rows;
- source facts;
- what user can fix;
- safety warning when manual edits are forbidden;
- re-check.

Gap:

- It still displays some raw problem identifiers like `problem #id` and status
  codes in English-like values.
- It should use the same Russian status labels as Action Center:
  `Новая`, `В работе`, `Выполнено`, `Отложено`, `Отклонено`,
  `Решено`, `Заблокировано`.

### P1: Admin Rule Builder Needs A Stronger No-Code Formula Experience

Admin UI is improved and usable, but professional no-code creation needs:

- scenario templates first;
- metric chips grouped by business area;
- drag/select formula building for normal admins;
- raw JSON only in advanced mode;
- immediate human formula preview;
- clear warnings:
  - too many matched products;
  - missing metrics are common;
  - mostly estimated impact;
  - no evidence fields selected;
  - price recommendation may violate safe margin.

This is especially important because the user explicitly said "Создать
проблему" is still hard to understand.

### P1: Page-Level Empty States Need One Standard

Current app has empty states, but they are not fully unified.

Professional standard:

- `Нужна синхронизация`
- `Нет данных`
- `Проблем не найдено`
- `Не хватает данных`
- `Модуль отключён`
- `Бета-модуль`

Each empty state must answer:

- what happened;
- why there is no result;
- what user can do now.

### P2: Frontend Type Quality Needs Cleanup

Several dynamic problem UI paths rely on `any` and permissive payload parsing.
That helped rollout speed, but it makes product-level refactors risky.

Recommended:

- create typed `DynamicProblemAction`, `ProblemResultSummary`,
  `ProblemStatusHistoryItem`, `AllowedActionCode`;
- make `SellerProblemUX` accept typed contracts;
- reduce `no-explicit-any` in Action Center and problem components.

### P2: Legacy/Fallback UI Should Be Visually Marked

Dynamic problems should take precedence. Legacy fallback is correct, but seller
or admin should be able to distinguish:

- dynamic issue with full evidence;
- legacy fallback issue with partial evidence;
- beta/internal signal.

Seller should not see raw technical source names unless useful.

## Page-by-Page Product Fit

### Action Center

Current grade: B+

Strong:

- dynamic problems appear as operational tasks;
- status can be changed;
- evidence is available;
- allowed dynamic actions are respected;
- result drawer exists;
- before/after comparison is cautious and professional.

Must fix:

- remove or expose dead inline detail state;
- Russianize reusable problem grid labels;
- show result status hint in the row, not only inside drawer;
- hide test-only/beta by default, keep admin toggle only.

### Product360 / Product Doctor

Current grade: B-

Strong:

- groups product-level problems;
- hides test-only rules from sellers;
- opens evidence drawer;
- links to Action Center.

Must fix:

- Russianize title, groups, counters and empty states;
- add status/result preview;
- make `Проблемы товара` feel like part of the product page, not an English
  plugin block.

### Data Fix

Current grade: A-

Strong:

- closest to professional workbench quality;
- affected rows and source facts are clear;
- safe-to-apply and system-only cases are explicit;
- re-check is visible.

Must fix:

- unify statuses and evidence button language;
- avoid showing raw IDs as primary seller information;
- connect result/re-check outcome back to Action Center row more visibly.

### Money

Current grade: B

Strong:

- EvidenceDrawer exists in money cards.
- Dynamic problem migration map covers money/profit/cost/stock/ads/promo.

Must fix:

- confirmed vs estimated money styling must be audited on every money card;
- legacy cards must stay fallback only;
- no card should recommend discount without price-safety evidence.

### Checker / Card Quality

Current grade: B-

Strong:

- Checker has EvidenceDrawer integration.
- Card quality issue workflow has status history.

Must fix:

- card quality problems are still mostly separate from Dynamic Problem Engine;
- when a card issue affects sales/profit, it should become an operational
  problem/action with evidence and re-check;
- keep content quality findings separate from financial loss unless evidence
  exists.

### Admin Problem Rules

Current grade: B

Strong:

- definitions, versions, validation, backtest and publish are present.
- admin can create and publish rules without backend code changes.

Must fix:

- improve no-code formula building;
- make impact preview unavoidable;
- make selected metrics and affected business area visually obvious;
- make publish blockers clearer.

## Backend Reliability Assessment

Current grade: A-

Good:

- safe formula evaluator avoids SQL/eval/code execution;
- metric catalog prevents arbitrary fields;
- missing data is explicit;
- evidence ledger is required;
- dedupe key and account/problem/entity uniqueness prevent duplicates;
- status preservation avoids losing user decisions;
- re-check and runner logs exist;
- price-safety service protects dangerous recommendations.

Remaining hardening:

- canonical result ledger for dynamic problems;
- typed result events for problem instances, not just legacy/unified actions;
- more indexes may be needed if problem_instances grows large and filters by
  trust/impact/status are heavily used;
- broader frontend product-level tests for Russian copy and drawer/result flow.

## Target UX Contract For Every Problem Card

Every problem card across Product360, Action Center, Data Fix, Money and Checker
must show these blocks:

1. `Что произошло?`
2. `Почему платформа так решила?`
3. `На что влияет?`
4. `Это факт или оценка?`
5. `Что сделать сейчас?`
6. `Можно исправить здесь?`
7. `Как проверим повторно?`
8. `Результат после действия`

The first seven are required before action. The eighth appears when task status
is `in_progress`, `done` or `resolved`, or when enough after-data exists.

## Result Model Required For Professional Platform

For recommendations like price decrease, promo, ads pause or price increase,
the platform must prove value carefully:

- Before:
  - status;
  - price;
  - stock;
  - sales/orders;
  - revenue;
  - profit or trust state;
  - money at risk;
  - formula/evidence.
- Action:
  - who changed status;
  - what was done;
  - when;
  - comment;
  - applied workflow link if available.
- After:
  - re-check outcome;
  - 7-day and 14-day comparison;
  - measured delta;
  - confidence;
  - explanation that this is correlation, not guaranteed causality.

## Recommended Roadmap

### Phase 1: Seller UX Alignment

Timebox: 1-2 days.

- Russianize `SellerProblemUX.tsx`.
- Russianize `ProductDoctorSection.tsx`.
- Change EvidenceButton to seller-default `Как посчитано?`.
- Remove or expose Action Center inline details.
- Add row-level result status badge in Action Center.
- Standardize empty states and status labels.

Acceptance:

- Seller sees one language and one problem structure everywhere.
- No raw JSON or English labels appear in normal seller mode.

### Phase 2: Canonical Problem Result Ledger

Timebox: 2-4 days.

- Add result events for `problem_instance_id`.
- Extend results API filters by `problem_instance_id`, `problem_code`,
  `source_module=problem_engine`.
- Store before snapshot when problem is first opened or moved to `in_progress`.
- Store completed/re-check events in the same ledger.
- Make Action Center, Product360 and Results consume the same result endpoint.

Acceptance:

- A seller can see before/after status and metrics from any problem entry point.
- Refresh does not lose result state.

### Phase 3: Admin Rule Builder Polish

Timebox: 3-5 days.

- Add template-driven create flow.
- Add visual formula builder with metric chips and operator blocks.
- Add impact preview and missing metric warnings inline.
- Keep raw JSON editor under advanced/admin mode.

Acceptance:

- Admin can create a useful rule without reading JSON.
- Invalid/potentially dangerous rules are blocked before publish.

### Phase 4: Product-Level Acceptance Tests

Timebox: 1-2 days.

- Add frontend tests/story fixtures for:
  - Action Center dynamic problem drawer;
  - Product Doctor grouped issue;
  - Data Fix linked dynamic issue;
  - EvidenceDrawer seller mode;
  - estimated vs confirmed money styling.

Acceptance:

- Product loop is protected from regression, not only backend contracts.

## Final Readiness Rating

Technical engine readiness: high.

Backend safety readiness: high.

Seller UX readiness: medium-high.

Professional platform readiness: not final until Phase 1 and Phase 2 are done.

The project has the right architecture. The next work should not be another
new detector. The next work should make the existing detector lifecycle feel
like one professional product:

`Проблема -> доказательства -> действие -> статус -> повторная проверка -> результат`.
