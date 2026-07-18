# Product Polish Baseline: Dynamic Problem UI and Result Flow

Date: 2026-07-07

## Executive Baseline

Dynamic Problem Engine is already wired into the important product surfaces:
Action Center, Product360/Product Doctor, Data Fix, Money, Checker evidence
drawers, admin problem rules, re-checks, and backend result tracking.

The current baseline risk is product consistency, not missing core detection
plumbing. The seller can still see mixed language, raw technical identifiers,
non-canonical result state, and different versions of the same problem
lifecycle across pages.

Target loop for every seller-facing problem:

`problem -> evidence -> action -> status -> re-check -> result`

Current result baseline:

- Dynamic problem result summaries are embedded into Action Center problem
  payloads.
- Generic result events exist, but they are keyed by action/module/source
  fields and are not yet a canonical dynamic problem ledger.
- `/portal/results` can filter by `action_id`, `nm_id`, `source_module`, and
  `event_type`, but not by `problem_instance_id` or `problem_code`.
- Product360/Product Doctor does not yet show the same result preview as the
  Action Center drawer.

## Surfaces Inspected

- Action Center:
  `frontend/src/routes/_authenticated/action-center.tsx`
- Product360 / Product Doctor:
  `frontend/src/components/portal/ProductDoctorSection.tsx`
- Reusable seller problem UX:
  `frontend/src/components/problem/SellerProblemUX.tsx`
- Evidence UI:
  `frontend/src/components/EvidenceDrawer.tsx`
- Data Fix:
  `frontend/src/routes/_authenticated/data-fix.tsx`,
  `frontend/src/components/data-fix/DataFixWorkbench.tsx`
- Money:
  `frontend/src/routes/_authenticated/money.tsx`,
  `frontend/src/components/money/BusinessActionCard.tsx`,
  `frontend/src/components/money/NextActionCard.tsx`,
  `frontend/src/components/money-ui/MetricCard.tsx`,
  `frontend/src/components/money-ui/ActionCard.tsx`
- Checker:
  `frontend/src/routes/_authenticated/checker.$nmId.tsx`
- Admin Problem Rules:
  `frontend/src/components/problem-rules/ProblemRulesAdminPanel.tsx`
- Results page and portal API usage:
  `frontend/src/routes/_authenticated/results.tsx`,
  `frontend/src/lib/portal.ts`,
  `backend/app/modules/portal/router.py`,
  `backend/app/services/result_tracking.py`,
  `backend/app/services/portal.py`,
  `backend/app/models/operator.py`

## Mixed Seller-Facing Labels

### SellerProblemUX

SellerProblemUX still contains English copy in reusable problem cards:

- Action labels: `Create task`, `Assign`, `Re-check`, `Dismiss`,
  `Open Data Fix`, `Open Price Review`, `Open Promo Planner`, `Run Checker`,
  `Upload Cost`, `Map SKU`, `Open Ads`, `Open Supply`.
- Fallback title/body copy: `Business issue`, `The platform found this
  problem from synced marketplace and finance data.`
- Money labels: `Confirmed money impact`, `Estimated or provisional impact`.
- Problem answer headings: `What happened?`, `Why do we think so?`,
  `How much does it affect?`, `Confirmed or estimated?`,
  `What should I do now?`, `Can I fix it here?`,
  `How will it be rechecked?`.
- Empty states: `Sync required`, `No data`, `No issues found`,
  `Data missing`, `Module disabled`, `Beta module`.
- Button/fallback text: `Action Center`, plus unknown action codes converted
  from raw code strings.

### Product360 / Product Doctor

Product Doctor is visible to sellers but still reads like an English plugin:

- `Product Doctor / Business Issues`
- `Dynamic problem rules for nm ... profit, stock, price, ads and data blockers`
- Group titles: `Profitability`, `Stock`, `Price`, `Ads/Promo`,
  `Data Blockers`
- Counters/statuses: `open`, `resolved`, `confirmed loss`
- Empty group text: `No issues in this group.`

### EvidenceDrawer / EvidenceButton

EvidenceButton mixes three languages in one seller-facing control:

- `How calculated? / Qayerdan keldi? / Как посчитано?`

The drawer is mostly Russian, but some technical English remains visible:

- `Endpoint`
- formula `ID`
- raw `formula_code`
- metric/source field codes

### Data Fix

Data Fix is mostly Russian and is the strongest guided flow, but still exposes
technical or English terms in seller-facing places:

- `re-check`
- `account_id`
- `cost_id`
- `source_endpoint`
- `API-источник`
- `problem #id`
- raw `status`
- raw blocker/problem codes
- frequent `nm_id`, `sku`, `vendor_code`, `xlsx`, `SRID`, `data issues`

Some of these are valid domain identifiers, but they should not be the primary
seller text where a human label is available.

### Money

Money is mostly Russian, but action cards still have English leftovers:

- `Recheck rule: compare KPI windows after the action is completed.`
- `Affected stock`
- `Lead time`
- `Safety stock`
- `data issues`

Some fallback cards display raw codes as the visible text.

### Checker

Checker has a visible evidence/status/recheck flow, but mixed labels remain:

- `Clean`
- `Confidence`
- `Disabled reason`
- `Exact fix`
- `Human check`
- `Photo Studio`
- raw `issue.source`
- prompt text that asks for `user id`

### Admin Problem Rules

Admin can tolerate more technical language, but the create/publish flow still
mixes product copy with raw implementation terms:

- `Definition`
- `Rule version`
- `condition_json`
- `impact_json`
- `evidence_template_json`
- `problem_code`
- `source_module`
- `dedupe_key_template`
- visible `code` values next to most metric/action options

This is acceptable in advanced mode, but too prominent for the normal no-code
admin path.

### Results Page

Results is mostly Russian, but the experiment block still shows English labels:

- `Baseline`
- technical module/source/outcome badges

## Dead Or Unreachable UI States

### Action Center Inline Details

`action-center.tsx` defines `detailsOpen` and renders a rich inline details
block, but no visible control calls `setDetailsOpen`.

The reachable detail path is the task drawer opened by the row action button.
The unreachable inline block contains problem/evidence/action/history/recheck
content and should either be removed or exposed. The recommended Phase 1 choice
is to keep the drawer as canonical and remove the dead inline detail path.

### Action Center Result Fetch Path For Dynamic Problems

The drawer can fetch canonical action results only for numeric `action_id`.
Dynamic problem actions are emitted as ids like `problem_engine:{id}` and carry
their result summary inside `payload.result_summary`. That means the UI result
story is reachable, but it does not come from the same result ledger as normal
result events.

## Estimated Money Presented Too Strongly

Backend result tracking is cautious and says expected impact is not saved money.
Several UI paths already respect this, but a few places still style expected or
estimated amounts like confirmed gain/loss.

### Safe Or Mostly Safe

- Money page finality buckets split confirmed, provisional, and estimated
  amounts.
- `MetricCard` uses dashed amber styling and a provisional label for estimated
  money.
- Action Center result drawer includes a correlation disclaimer and separates
  money-at-risk from measured result language.

### Needs Polish

- `BusinessActionCard` renders positive `expected_effect_amount` in green
  success styling without a visible trust/finality distinction.
- `NextActionCard` renders positive `expected_effect_amount` in green success
  styling without a visible trust/finality distinction.
- `money-ui/ActionCard` uses green styling for positive expected effect even
  when the amount is provisional; it does show a separate warning in some
  cases, but the money pill still reads visually like a win.
- Results page colors `effect_amount` green/red by sign and does not visually
  separate measured confirmed effect from low-confidence or correlational
  effect strongly enough.
- Admin backtest/result rows show estimated money impact without the seller
  money-trust styling used elsewhere.

Phase 1 should make `confirmed_loss`, `probable_loss`, `blocked_cash`,
`lost_sales_risk`, and `opportunity` visually distinct everywhere.

## Raw IDs And Codes Too Prominent

Raw identifiers are useful for admin/debugging, but sellers currently see them
too often as primary labels.

### Action Center

- Row metadata shows `nm {id}` and vendor identifiers prominently.
- Status badges can display raw `a.status`.
- Recheck state can show raw `ok/error`.
- Result money-at-risk can show raw `impact_type` and `trust_state`.
- User prompts include `ID пользователя`.

### SellerProblemUX

- Unknown action fallback converts raw action codes into visible text.
- The component accepts broad payloads and can surface raw fallback values when
  seller copy is missing.

### EvidenceDrawer

- Formula ids, formula codes, metric codes, endpoint names, row keys, snapshot
  ids, and sync ids are visible in the seller evidence drawer.

### Product Doctor

- Product-specific context uses `nm` language in the subtitle.
- Group/status labels are English rather than business-language Russian.

### Data Fix

- `problem #id`, `problem_code`, raw `status`, issue codes, dynamic problem
  codes, `source_endpoint`, `account_id`, and `cost_id` are prominent.

### Money

- Some blocker/warning fallback text displays `code` values directly.
- Ads/data issue status text can expose raw status values.

### Checker

- `issue.source`, user id prompts, and several confidence/source fields are
  visible without seller-language mapping.

### Admin Problem Rules

- Raw codes are expected in advanced/admin context, but they should move behind
  advanced affordances in the default no-code path.

## Loop Fit By Page

| Surface | Current loop fit | Main gap |
| --- | --- | --- |
| Action Center | Good problem/evidence/action/status/recheck/result drawer | Dead inline details; row lacks result badge; result summary is embedded, not canonical ledger |
| Product360 / Product Doctor | Shows grouped product problems, evidence, and Action Center link | No result preview, weak status story, English labels |
| SellerProblemUX | Defines reusable problem blocks for what/why/impact/action/recheck | English labels, no result block, permissive payload typing |
| EvidenceDrawer | Strong evidence explanation and source facts | Evidence is not action/status/result; button mixes languages; raw codes visible |
| Data Fix | Strongest guided workbench: issue, facts, fix form, preview/apply, audit, recheck | Raw ids/statuses; result linkage back to Action Center is not prominent |
| Money | Uses evidence/trust in multiple cards and separates some finality buckets | Expected effect cards can look like confirmed money; not every money problem has status/recheck/result |
| Checker | Has evidence, status, fix/recheck controls, and Product Doctor integration | Mostly separate from result ledger; mixed English labels; no financial result story unless linked elsewhere |
| Admin Problem Rules | Definitions, validation, backtest, publish, warnings | Normal admin create path still too code-oriented; result loop not the purpose of this page |
| Results | Shows result events, before/after evidence, confidence, correlation notes | Cannot filter by `problem_instance_id` or `problem_code`; not yet canonical for dynamic problems |

## Existing Tests Covering The Flow

Backend and static UI tests already cover a large part of the engine contract:

- `backend/tests/acceptance/test_dynamic_problem_engine_product_acceptance.py`
  covers missing cost, negative profit, overstock, low stock, status
  preservation, re-check resolution, and admin draft/publish/generate flow.
- `backend/tests/unit/test_problem_engine_portal_integration.py` covers
  evidence ledger contract, legacy fallback/suppression, feature flags,
  Action Center dynamic actions, status/history/dismiss/recheck, filters, and
  Product business issue grouping.
- `backend/tests/unit/test_data_fix_dynamic_problem_bridge.py` covers Data Fix
  mapping to dynamic problem instances and resolution.
- `backend/tests/unit/test_result_tracking_service.py` covers before/after
  comparison, idempotent snapshots, honest missing after-data, module filters,
  finance windows, effect summaries, and result center product identity.
- `backend/tests/api/test_portal_action_center_contract.py` covers Action
  Center contract shape, include-beta permissions, filters, patch-by-source,
  and audit status transitions.
- `backend/tests/api/test_portal_routes.py` includes portal result route
  account access coverage.
- `backend/tests/unit/test_problem_rules_admin_ui_static.py` covers admin
  problem rule UI wiring and required flow pieces.
- `backend/tests/unit/test_checker_status_only_ui_static.py` covers Checker
  evidence/status/recheck visibility and source issue editing boundaries.
- `backend/tests/unit/test_data_quality_guided_workflows.py` covers guided Data
  Fix definitions, audit history, affected rows, and resolution context.
- `frontend/e2e/navigation.spec.ts` includes navigation coverage for `/results`
  and stubs the portal results API.

## Missing Tests

The product polish gaps are mostly under-tested at frontend/product level.
Missing coverage:

- Action Center dynamic problem drawer with result panel, evidence, allowed
  actions, status change, and re-check.
- Guard that `detailsOpen` inline state is either reachable or removed.
- SellerProblemUX Russian seller copy and no raw fallback labels in normal
  seller mode.
- Product Doctor grouped issue card with Russian labels, status preview, result
  badge, and Action Center link.
- EvidenceButton seller text should be `Как посчитано?`.
- EvidenceDrawer seller mode should hide or demote formula ids, endpoints,
  row keys, snapshot ids, sync ids, and raw metric codes.
- Data Fix dynamic issue bridge should assert Russian statuses and no primary
  `problem #id` seller title.
- Money cards should visually distinguish confirmed loss, probable loss,
  blocked cash, lost sales risk, opportunity, and measured saved money.
- Results page should distinguish measured/correlational/low-confidence money
  effects and support dynamic problem filters after Phase 2.
- Checker dynamic problem integration should cover evidence, status, re-check,
  and result handoff when a finding affects sales/profit.
- Admin rule builder no-code path should be tested without relying on raw JSON.

## Phase 1 Must Change

Phase 1 should be seller UX alignment without changing detection logic:

- Russianize SellerProblemUX labels, action names, empty states, and fallbacks.
- Russianize Product Doctor title, group names, counters, statuses, and empty
  states.
- Change EvidenceButton seller text to `Как посчитано?`.
- Remove the unreachable Action Center inline detail state or add a clear
  `Подробнее` / `Свернуть` control. Recommended: remove it and keep the drawer
  canonical.
- Add an Action Center row-level result status hint.
- Replace raw seller statuses with shared Russian status labels.
- Demote raw ids/codes in seller mode and keep them for admin/debug drawers.
- Make estimated/opportunity/blocked-cash money visually distinct from
  confirmed loss or measured saved money.
- Standardize empty states around `Нужна синхронизация`, `Нет данных`,
  `Проблем не найдено`, `Не хватает данных`, `Модуль отключён`,
  `Бета-модуль`.

## Phase 2 Must Change

Phase 2 should make result tracking canonical for dynamic problems:

- Add result events keyed by `problem_instance_id`.
- Add result filters for `problem_instance_id`, `problem_code`, `nm_id`, and
  `source_module=problem_engine`.
- Store a before snapshot when a dynamic problem is opened or moved to
  `in_progress`.
- Store action-started, action-completed, re-check, after snapshot, measured
  comparison, confidence, and correlation note events in the same ledger.
- Make Action Center, Product360/Product Doctor, and Results page consume the
  same result endpoint.
- Add Product360 result preview badges: `ожидает данных`, `есть улучшение`,
  `стало хуже`, `нет данных`.

## Verification

Frontend build:

- Command: `npm run build` from `frontend`.
- Result: passed.
- Notes: Vite reported existing chunk-size warnings for chunks over 500 kB.

Focused backend tests:

- Initial `python -m pytest ...` could not run because `python` is not on PATH.
- `python3 -m pytest ...` could not run because system Python has no `pytest`
  module.
- Command used successfully:
  `/home/ozodbek/AVEMOD_PROJECTS/Finance/.venv/bin/pytest ...` from `backend`.
- Result: 78 passed, 2 failed, 1 warning.

Failing tests:

- `tests/unit/test_problem_rules_admin_ui_static.py::test_admin_problem_rules_ui_is_wired_into_admin_page`
- `tests/unit/test_problem_rules_admin_ui_static.py::test_problem_rules_admin_ui_covers_required_flow`

Failure reason:

- Both are static marker assertions expecting old English/admin strings such as
  `Problem Rules`, `Problem Definition Editor`, `Rule Version Editor`,
  `Condition formula`, and similar markers.
- The failure is consistent with the baseline finding that Admin Problem Rules
  has moved toward a more Russian/no-code UI while some tests still assert old
  copy markers.

All other selected backend tests passed, including Dynamic Problem Engine
acceptance, portal integration, Data Fix bridge, result tracking, Action Center
contract, result route access, Checker static flow, and guided Data Fix
workflows.
