# Action Center Baseline Audit

Date: 2026-07-07

Scope: current Action Center backend and frontend before product logic changes.

Target product loop:

`problem -> evidence -> allowed action -> status/history -> re-check -> result`

## Executive Summary

Action Center is already the main operational task surface. It lists dynamic
problem-engine problems, checker/card quality bridge items, finance/data quality
/ costs items, legacy/unified actions, and beta/read-only module signals. The
current implementation is stronger than the earlier baseline in several areas:

- Dynamic problem rows now have a visible result badge.
- The old unreachable inline detail state is no longer present in
  `action-center.tsx`; the drawer is the canonical task detail.
- The drawer contains evidence, allowed actions, status update, assignment,
  deadline, re-check, result panel, result timeline, and work history.
- Product Doctor and Data Fix already read dynamic problem result events.
- Seller-facing copy is mostly Russian via `problem-ux-copy.ts`.

The main remaining risk is consistency of source-of-truth boundaries:

- Dynamic problem status is canonical in `problem_instances`, but result summary
  is still partly embedded in Action Center payloads.
- Non-dynamic sources may use a `UnifiedAction` shadow status even when the
  source object also has state, so drift is possible and not always visible.
- Assignment/deadline/comment history is not fully represented in the canonical
  result ledger.
- Some UI fallbacks still expose raw technical values.

## Current Data Flow

### List Load

Frontend:

- `src/routes/_authenticated/action-center.tsx` calls
  `fetchPortalActions(activeId, queryFilters, dateRange)`.
- `fetchPortalActions` calls `GET /portal/actions`.
- Query filters include status, source_module, priority, problem_code,
  trust_state, impact_type, nm_id, and include_beta.
- `problem_instance_id` is accepted from route search but is filtered locally in
  the frontend, not sent to the backend.
- The page hides beta/test/system-handled signals unless the user is allowed and
  toggles beta sources.

Backend:

- `PortalService.actions` gathers actions from dynamic problem instances,
  finance/money, data quality, costs, checker, module beta sources, unified
  shadow actions, and Product Doctor generated actions.
- Dynamic problem actions are built from `problem_instances` through
  `_problem_instance_action`.
- Legacy problem-like cards are suppressed when a matching dynamic problem
  exists, and can be globally hidden by `show_legacy_problem_cards`.
- Shadow statuses from `unified_actions` are applied over generated/source
  actions by `_apply_shadow_status`.

### Row Behavior

Each Action Center row currently shows:

- product link (`nm` button) when `nm_id` exists;
- status badge;
- beta badge when applicable;
- money trust badge;
- problem badges for dynamic/checker problem-like rows;
- dynamic problem result badge for problem-engine rows;
- allowed action buttons for problem-like rows;
- guided fix button for non-problem rows;
- status select when updateable;
- read-only badge when not updateable;
- task drawer button;
- evidence button when an evidence ledger exists.

The result badge is computed from `/portal/results?source_module=problem_engine`
when matching events exist, otherwise from embedded `payload.result_summary`.

### Drawer Behavior

The drawer is the canonical visible detail view. It contains:

- problem summary and problem lifecycle blocks;
- result panel with before/current/completed status fields;
- result timeline when result events exist;
- money-at-risk panel with correlation disclaimer;
- evidence section and EvidenceDrawer trigger;
- allowed/guided actions;
- status, assignee, deadline, comment form;
- re-check rule and re-check button.

For dynamic problems, drawer results come from
`GET /portal/problems/{problem_instance_id}/results`.

For non-dynamic persisted actions, drawer results come from
`GET /portal/actions/{action_id}/results`.

### Status Update Flow

Frontend mutation:

- If `source_module` and `source_id` exist, Action Center calls
  `PATCH /portal/actions/by-source`.
- Otherwise it falls back to `PATCH /portal/actions/{action_id}`.
- It optimistically patches the local actions cache and then invalidates Action
  Center, result, Product Doctor, Data Fix, Money blockers, and dashboard data
  health queries.

Backend by-source flow:

- `source_module=problem_engine`: updates `problem_instances.status`, writes
  `problem_instance_history`, writes result events for status/completion/recheck,
  and stores assignee/deadline/comment in
  `calculation_snapshot_json.action_center`.
- `source_module=finance`: updates `ActionRecommendation` when source id maps
  to a legacy action.
- `source_module=checker`: updates card quality issue status and may append a
  card quality status-history row for recheck markers.
- `source_module=data_quality`: maps Action Center statuses to DQ classify,
  resolve, or reopen operations.
- `source_module=costs`: appends review context to the cost row and can mark a
  cost as business trusted when done.
- `source_module=reputation`: attempts a reputation shadow update.
- Other shadow modules can be locally tracked in `unified_actions`.
- A `local_action_status_updated` `result_events` row is added for non-dynamic
  by-source updates.

Backend by-id flow:

- First tries legacy `ActionRecommendation`.
- Falls back to `UnifiedAction`.
- Creates before snapshot on `in_progress`.
- Creates action completed result event on `done`.

### Re-check Flow

Dynamic problem re-check:

- Frontend calls `POST /portal/problems/{problem_id}/recheck`.
- Backend runs `ProblemEvaluationRunnerService.recheck_problem_instance`.
- The runner evaluates the relevant product or account, appends
  `ProblemInstanceHistory(event_type="recheck")`, creates a
  `result_events.recheck_result`, and creates `action_completed` if the re-check
  resolves the problem.

Checker bridge re-check:

- Frontend calls `PATCH /portal/actions/by-source` with `event_type="recheck"`.
- Backend records a card-quality status-history marker. It does not appear to
  run a fresh checker analysis from this endpoint.

Non-problem re-check:

- The drawer shows re-check for non-problem rows. Dynamic problem rows only show
  it when `allowed_actions` includes `recheck`.

### Evidence Flow

Evidence sources:

- Dynamic problems carry `evidence_ledger_json`.
- Checker bridge actions carry bridge evidence ledger.
- Generic actions can get an automatically synthesized evidence ledger in
  `PortalActionRead.fill_frontend_contract_defaults`.

Frontend:

- `EvidenceButton` uses seller-default `Как посчитано?`.
- `EvidenceDrawer` shows formula, input facts, sources, trust/missing data,
  warnings, fix action, and re-check rule.
- Raw JSON is gated behind `debug`.

### Result Flow

Canonical ledger:

- Stored in `result_events`.
- Dynamic problem events include `problem_instance_id`, `problem_code`,
  `source_module=problem_engine`, snapshots, comparison, confidence, warnings,
  and correlation note.
- `/portal/results` supports filters by `action_id`, `problem_instance_id`,
  `problem_code`, `nm_id`, `source_module`, and `event_type`.
- `/portal/problems/{problem_instance_id}/results` ensures a dynamic problem
  before snapshot before listing events.

Embedded fallback:

- `_problem_instance_action` embeds `payload.result_summary` for Action Center
  payloads.
- This summary includes status flow, before/current snapshots, status history,
  finance windows, money at risk, and disclaimers.
- `ActionResultPanel` prefers canonical result events, but falls back to the
  embedded summary when no result events exist.
- `SellerProblemUX` can also derive result blocks from embedded
  `result_summary`.

## Current Endpoint Contract

### `GET /portal/actions`

Purpose: Action Center list.

Query:

- `account_id?: int`
- `date_from?: date`
- `date_to?: date`
- `status?: string`
- `source_module?: list[string]`
- `priority?: list[string]`
- `nm_id?: int`
- `action_type?: list[string]`
- `problem_code?: list[string]`
- `trust_state?: list[string]`
- `impact_type?: list[string]`
- `include_beta?: bool`
- `limit?: int = 50`
- `offset?: int = 0`

Response: `PortalActionsPage { total, limit, offset, items,
unavailable_sources }`.

Notes:

- `include_beta=true` requires admin role.
- No server-side `problem_instance_id` filter exists today.

### `PATCH /portal/actions/by-source`

Purpose: preferred Action Center status update path when a row has
`source_module` and `source_id`.

Body:

- `account_id: int`
- `source_module: string`
- `source_id: string`
- `status: new | in_progress | done | postponed | ignored | blocked`
- `comment?: string`
- `assigned_to_user_id?: int`
- `deadline_at?: datetime`
- `review_status?: new | in_progress | review | closed | dismissed`
- `event_type?: status_change | dismiss | assign | comment | recheck`

Response: `PortalActionRead`.

Notes:

- Requires operator role.
- Dynamic problem updates are canonical.
- Non-dynamic updates may update source object and also write/update a
  `UnifiedAction` shadow.

### `PATCH /portal/actions/{action_id}`

Purpose: fallback update path for legacy `ActionRecommendation` or
`UnifiedAction`.

Body:

- `status`
- `comment?`
- `assigned_to_user_id?`
- `deadline_at?`
- `review_status?`
- `event_type?`

Response: `PortalActionRead`.

Notes:

- Creates a before snapshot on `in_progress`.
- Creates `action_completed` event on `done`.

### `POST /portal/problems/{problem_id}/recheck`

Purpose: canonical dynamic problem re-check.

Response: refreshed dynamic problem as `PortalActionRead`.

Notes:

- Requires operator role on the problem account.
- Runs the problem evaluator, records history, records `recheck_result`, and may
  record completion when the problem resolves.

### `GET /portal/results`

Purpose: canonical result ledger and Results page.

Query:

- `account_id?: int`
- `action_id?: int`
- `problem_instance_id?: int`
- `problem_code?: string`
- `nm_id?: int`
- `source_module?: string`
- `event_type?: string`
- `limit?: int = 50`
- `offset?: int = 0`

Response: `PortalResultEventsPage`.

Notes:

- Result service aliases `result_tracking` and `action_center` for generic
  action result events.
- Dynamic problem filtering by `source_module=problem_engine` works.

### `GET /portal/problems/{problem_instance_id}/results`

Purpose: dynamic problem result timeline.

Query:

- `limit?: int = 50`
- `offset?: int = 0`

Response: `PortalResultEventsPage`.

Notes:

- Ensures a `before_snapshot` event before returning.
- Filters source module to `problem_engine`.

### `GET /portal/actions/{action_id}/results`

Purpose: legacy/unified action result timeline.

Query:

- `limit?: int = 50`
- `offset?: int = 0`

Response: `PortalResultEventsPage`.

### `POST /portal/actions/{action_id}/result-event`

Purpose: manual result event creation for an action.

Current Action Center usage: endpoint exists in client constants/backend but is
not used by the Action Center page.

## Canonical And Updateable Action Types

### Dynamic `problem_engine` Problems

Canonical object:

- `problem_instances`

Update path:

- `PATCH /portal/actions/by-source` with `source_module=problem_engine`

Re-check path:

- `POST /portal/problems/{problem_id}/recheck`

Result ledger:

- `result_events` with `source_module=problem_engine` and
  `problem_instance_id`.

Current quality:

- Strongest canonical flow.
- Status, history, re-check, and result events are tied to the problem instance.
- Still embeds computed `result_summary` into action payloads for list/drawer
  fallback.

### Checker/Card Quality Bridge

Canonical object:

- Card quality issue/status history.

Update path:

- `PATCH /portal/actions/by-source` with `source_module=checker`.

Re-check path:

- Currently a by-source status/history marker from Action Center. It does not
  clearly trigger fresh checker analysis.

Result ledger:

- Generic local status events for by-source updates.
- Product Doctor attempts to match checker bridges against problem-engine
  result events by code/nm, so checker-specific result history can look pending.

Current quality:

- Good bridge UX.
- Re-check semantics need clearer "marker vs real analysis" distinction.

### Finance/Data Quality/Costs Actions

Finance:

- Canonical source can be `ActionRecommendation`.
- By-source and by-id updates can update source action.
- Result events are generic result-tracking/action-center events.

Data quality:

- Canonical source is `DataQualityIssue`.
- Action Center statuses map to DQ statuses/classification, not one-to-one.
- Data Fix can trigger guided actions/re-check from the DQ endpoint and links
  back to Action Center.

Costs:

- Canonical source is `ManualCost`, but it has no true Action Center status
  column.
- Status lives mostly in `UnifiedAction` shadow, while cost row comments/trust
  fields may be updated.
- `source_sync_state=source_updated` can be misleading because the business
  source was touched but the status is still shadow state.

### Legacy/Unified/Manual Actions

Canonical object:

- `ActionRecommendation` for legacy finance/control tower.
- `UnifiedAction` for persisted local/shadow tasks.

Update path:

- `PATCH /portal/actions/{action_id}` or by-source when source identity exists.

Result ledger:

- Generic `result_tracking` events with action id/source id.

Current quality:

- Usable and updateable when ids exist.
- Generated Product Doctor rows are read-only unless a safe local status route
  exists.

### Beta/Read-only Actions

Sources:

- `grouping_beta`, `reputation`, `claims`, `photo`, `stockops`,
  `experiments`, plus test-only dynamic rules.

Visibility:

- Hidden by default for sellers.
- Admin can include beta sources.

Updateability:

- Many use shadow status in `UnifiedAction`.
- Claims is explicitly locked when module visibility is disabled.

Current quality:

- Beta visibility is controlled.
- Read-only/shadow reasons can leak raw technical strings.

## Status Drift Risks

1. Dynamic problem status is safest, but duplicate status/history exists:
   `problem_instances.status`, `problem_instance_history`,
   `calculation_snapshot_json.action_center`, embedded `payload.status_history`,
   and `result_events`.

2. Non-dynamic by-source updates can write a `UnifiedAction` shadow even when a
   source object was updated. Future source recomputation can disagree with the
   shadow row, and `_apply_shadow_status` will display the shadow status.

3. Data quality maps Action Center status to DQ classification values
   (`real_issue`, `expected_lag`, `ignored_with_reason`, resolved/reopened).
   These are not the same enum, so a source-side DQ change can be normalized
   differently on the next list load.

4. Costs have no native task status. Status is effectively shadow state plus
   comments/trust flags on `ManualCost`.

5. Checker re-check from Action Center records history but does not clearly run
   fresh analysis. The UI can imply "re-check" while backend performed a local
   marker.

6. Assignment, deadline, and comments for dynamic problems are stored in
   `calculation_snapshot_json.action_center` and `problem_instance_history`, but
   canonical result events do not yet contain a complete assignment/deadline
   timeline.

7. Frontend optimistic updates can show a transient status before the canonical
   backend response and query invalidations arrive. This is acceptable but should
   not be treated as source truth.

## Embedded Result Tracking

Places where result state is still embedded instead of purely read from the
ledger:

- Backend `_problem_instance_action.payload.result_summary`.
- Backend `_problem_instance_result_summary`, which computes status flow,
  before/current snapshots, finance windows, and money-at-risk directly for the
  action payload.
- Frontend `resultSummaryFromAction`, which reads
  `action.payload.result_summary` and `action.raw.result_summary`.
- Frontend `SellerProblemUX.resultSummary`, which can show result blocks from a
  problem object's embedded `result_summary`.
- Product surfaces can still inherit embedded summaries through
  `SellerProblemCard` when a ledger result is not passed.

This fallback is useful for MVP continuity, but professional-grade behavior
should make `/portal/results` the single timeline for every dynamic problem.

## UI Consistency Findings

### Already Good

- Action Center title, filters, row controls, drawer labels, status labels, and
  evidence button are mostly Russian.
- `EvidenceButton` is now `Как посчитано?`.
- `SellerProblemUX` answer labels are Russian and match the target product loop.
- Product Doctor section is now `Проблемы товара` with Russian group labels.
- Data Fix uses a guided Russian workbench and links result state back to Action
  Center.
- Estimated/preliminary impact is visually separated in `SellerProblemUX`.
- Results page guards "saved money" style behind after-data and confidence.
- Row-level dynamic problem result badge exists.
- Drawer-level result timeline exists.

### Remaining Inconsistencies

- Raw technical strings can leak through `can_update_reason`, for example
  `read_only_recommendation` or generated/shadow reason keys.
- `source_sync_state` is not shown in the row/drawer, so users cannot tell
  source-updated vs shadow-only vs shadow-updated.
- EvidenceDrawer humanizes source/table names by replacing underscores; this is
  still technical for seller-facing controls.
- Results page still has a few raw/English-facing terms such as `Baseline`,
  `nm_id`, placeholders like `overstock_slow_moving`, and raw problem codes
  when no translation exists.
- Data Fix support details correctly hide raw IDs behind `<details>`, but audit
  rows can show raw `actionType` and raw `status`.
- Data Fix "Затронутые деньги" shows a large amount next to trust state, but
  does not visually distinguish confirmed loss vs blocked/estimated risk as
  strongly as `SellerProblemUX`.
- Action Center row does not show assignee/deadline summary or overdue state.
  The drawer has the fields, but list triage cannot scan ownership yet.
- Assignment/deadline changes are not first-class result ledger events, so the
  drawer history can become status/result-centric rather than full task history.
- Read-only state is understandable for disabled Claims, but generic read-only
  rows still need seller-friendly reasons.

## Current Gaps

### P0

1. Make dynamic problem results ledger-first.

   Action Center, Product Doctor, Data Fix, and Results already can read
   `/portal/results`, but dynamic problem action payloads still embed
   `result_summary`. Keep payload summary only as compatibility fallback.

2. Translate source/shadow update state for sellers.

   The backend already emits `source_sync_state`. The UI should show friendly
   labels for `source_updated`, `shadow_updated`, `shadow_only`, and unknown
   read-only reasons.

3. Preserve full task history in one place.

   Status/re-check/completion are in result events. Assignment/deadline/comment
   should also be represented in the canonical timeline or a clearly separate
   task ledger.

4. Make re-check semantics explicit per source.

   Dynamic re-check runs evaluator. Checker re-check currently looks like a
   marker. The UI and backend should not imply fresh analysis unless it happens.

### P1

1. Add server-side Action Center filter for `problem_instance_id`.

   Current route deep-link filters locally after `GET /portal/actions`.

2. Add row-level ownership/deadline preview.

   Drawer has assignment/deadline controls. Operational work-center scanning
   needs assignee, due date, and overdue/blocked badges in rows.

3. Normalize Data Fix and Results technical labels.

   Keep support IDs behind details, but translate audit action/status values and
   result placeholders.

4. Tighten estimated money styling in Data Fix.

   Mirror `SellerProblemUX` confirmed-vs-estimated distinction for
   `Затронутые деньги`.

5. Make checker bridge result source explicit.

   If checker has no problem-engine result event, show "результат Checker пока
   не измеряется" instead of only pending dynamic result.

### P2

1. Reduce loose `any` in Action Center, Product Doctor, Data Fix, and
   `SellerProblemUX`.

2. Make backend result event types explicit for task events:
   `assigned`, `deadline_changed`, `comment_added`, `recheck_requested`.

3. Consider result-event indexes for heavy filters by
   `(account_id, source_module, created_at)` and `(account_id, nm_id,
   source_module)`.

4. Decide whether generated `profit_doctor` rows should remain read-only or be
   converted to persisted `UnifiedAction` tasks on first open.

## Safe Implementation Order

1. Ledger-first read path.

   Keep existing payload fallback, but make Action Center/Product Doctor/Data Fix
   prefer `/portal/results` everywhere and add tests proving embedded
   `result_summary` is not required for dynamic problem result badges/drawers.

2. Task history completeness.

   Add canonical result/task events for assignment, deadline, comment, and
   recheck request. Then render one merged timeline in the drawer.

3. Source sync transparency.

   Translate `source_sync_state` and `can_update_reason`, and show a small badge
   or drawer note for shadow-only/shadow-updated rows.

4. Re-check semantics.

   Keep dynamic problem re-check as evaluator-backed. For checker and other
   modules, either trigger the actual source re-check or label the action as
   "запросить повторную проверку" / "отметить к перепроверке".

5. Action Center scan ergonomics.

   Add assignee/deadline/overdue row badges and filters after source truth is
   clear.

6. Payload cleanup.

   Once all surfaces use the ledger, deprecate dynamic problem
   `payload.result_summary` or keep it as a small cache that is never treated as
   canonical.

7. UI copy cleanup.

   Translate remaining raw status/action/source strings in Results, Data Fix
   audit rows, EvidenceDrawer source labels, and read-only badges.

## Verification

Frontend:

- Command: `npm run build` from `frontend/`.
- Result: passed.
- Notes: Vite reported large chunk warnings, including the main app chunk above
  500 kB. No build failure.

Backend:

- Command:
  `.venv/bin/python -m pytest tests/api/test_portal_action_center_contract.py tests/unit/test_portal_action_source_sync.py tests/unit/test_result_tracking_service.py tests/unit/test_problem_engine_portal_integration.py tests/unit/test_problem_engine_runner.py`
  from `backend/`.
- Result: 46 passed.
- Notes: two warnings from Starlette/httpx deprecation and Python `crypt`
  deprecation.

## Acceptance State

- `docs/action_center_baseline_audit.md` exists.
- Product logic was not changed in this step.
- Current Action Center data flow, endpoint contract, updateability boundaries,
  drift risks, embedded-result fallbacks, UI inconsistencies, and next safe
  implementation steps are documented.
