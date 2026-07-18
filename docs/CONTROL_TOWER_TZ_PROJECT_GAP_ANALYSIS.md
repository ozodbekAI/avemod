# Control Tower TZ vs Project Gap Analysis

Source TZ: `/home/ozodbek/Downloads/Telegram Desktop/Control_Tower_Product_Vision_MVP_and_Roadmap.docx`

Extracted text: `docs/control_tower_tz_extracted.txt`

Analysis date: 2026-06-27

## Executive Verdict

Project is already close to the Control Tower direction technically, but the product surface is wider and noisier than the TZ MVP.

The strongest alignment is in:

- FastAPI modular monolith architecture.
- Auth, accounts, RBAC-like account access.
- WB account/token storage and sync jobs.
- Finance/Money, data quality, costs, exports.
- Legacy profit diagnostics.
- Action Center / unified actions.
- Product 360 and card quality/checker surfaces.
- Result tracking.

The main mismatch is product focus:

- TZ says MVP must be `Finance + Checker + Task Center`, with Photo Studio, A/B, Grouping and Supply/Stock deferred.
- Current app exposes many phase-2/phase-3 modules in navigation and portal routes.
- There is an operator model, but not yet a single clean `Issue -> Task -> Result` product object across all modules. Several parallel concepts still exist: `DataQualityIssue`, `ActionRecommendation`, `UnifiedAction`, `OperatorDiagnosis`, `ClaimCandidate`, `OperatorCase`.

## TZ Core Idea

The TZ positions the product as an operational AI control layer, not a dashboard:

`data connected -> issues found -> issues explained -> issues converted to tasks -> tasks closed -> money saved`

The key unit is `Issue`, not a chart. Every module should produce issues with money impact, explanation, recommendation, status, dedupe key and history. Tasks are created from issues or manually.

## Current Project Shape

Backend:

- `backend/app/modules/auth`, `accounts`: login, refresh, users, accounts, WB tokens.
- `backend/app/modules/money_management`, `finance`, `marts`, `manual_costs`, `data_quality`: finance and data readiness.
- `backend/app/modules/portal`: Doctor, overview, actions, products, product quality, results, cases, reputation, photo, experiments.
- `backend/app/models/operator.py`: operator signal, diagnosis, unified action, case, evidence, draft, result event, integrations.
- `backend/app/modules/stock_control`: stock control workflows.
- `backend/app/modules/exports`: Excel exports.

Frontend:

- Core routes: `/dashboard`, `/doctor`, `/action-center`, `/products`, `/results`, `/data-fix`, `/costs`, `/settings`.
- Extra visible routes: `/photo-studio`, `/ab-tests`, `/grouping`, `/stock-control`, `/purchase-plan`, `/ads`, `/analytics`, `/marts`, etc.

## Compliance Matrix

| TZ Requirement | Current Status | Evidence / Notes | What To Do |
| --- | --- | --- | --- |
| Not a dashboard, but issue/task control layer | Partial | Doctor, Action Center and Results exist, but dashboard/money/module pages still dominate navigation. | Make `/action-center` or a new `/attention` the default main screen; reduce dashboard framing. |
| MVP = Finance + Checker + Task Center | Partial | Finance and card quality exist; Action Center exists. Extra modules are exposed. | Hide or label Photo/A-B/Grouping/Stock as beta/phase-2 in MVP mode. |
| Registration/auth | Partial | Login and admin user creation exist. Public registration and password recovery are not visible. | Add self-service registration, password reset, invite acceptance flow if MVP requires no team help. |
| Companies/accounts switcher | Good | `GlobalTopBar` has account selector; backend has `wb_accounts`. | Add "all companies" aggregate mode if required by TZ. |
| Roles/invites | Partial | `AuthUserAccountAccess.role` exists. No clear invite flow found. | Add invite lifecycle and role management UI for owner/manager/viewer. |
| WB API key connection wizard with access checks | Partial | Account token storage exists; settings/data sync exist. Token management appears admin-oriented. | Build seller-facing onboarding wizard: paste WB key, validate categories, show what can be checked. |
| Excel/CSV upload | Partial | Costs upload/template exists; exports exist. General finance/docs CSV imports are limited. | Add upload flows for financial reports/documents/1C-like CSV if required for MVP demo. |
| Main screen "What needs attention" | Partial | `/action-center` groups actions and has status updates. `/doctor` diagnoses. | Merge/position as first screen with summary counters and money impact. |
| Problem feed sorted by money/criticality | Partial | Portal actions sorting/dedupe exists; Doctor sorts by impact. | Make a single issue feed with filters: company, module, severity, status, assignee. |
| Summary counters: total/new/in progress/closed/saved | Partial | Results page tracks events; Action Center has actions. | Add top KPI strip based on unified issue/task/result data. |
| Finance detectors | Good/Partial | Money, finance, data blockers, reconciliation marts, costs exist. | Ensure all TZ detectors become issues: mismatches, duplicate/unpaid docs, old balances, anomalous deductions. |
| Every finance finding = issue with amount/explanation/recommendation | Partial | Doctor/Actions output amount/reason/next step. DataQualityIssue is separate. | Normalize into an Issue API contract and persist dedupe/history. |
| Checker/card quality | Good/Partial | `/portal/card-quality/*`, product quality, card quality models/services exist. | Ensure first-run checker flow creates issues and tasks, not only quality screens. |
| Checker apply jobs | Partial/Safe | Apply/write operations are guarded/default-off. | For MVP demo, expose only safe preview/confirm apply where already proven. |
| Problem -> Task in one click | Partial | Portal actions can update status; `UnifiedAction` has task fields. | Add explicit "Create task" from issue and manual task creation. |
| Task assignment/deadline/comments/attachments | Partial | `UnifiedAction` has assignee, deadline, last_comment. No full comments/attachments subsystem found. | Add `task_comments`, `task_attachments`, richer history UI. |
| Task statuses new -> in progress -> review -> closed/dismissed | Partial | Backend maps review statuses; frontend statuses are `in_progress/done/postponed/ignored`. | Align UI labels and backend enum with TZ lifecycle. |
| False-positive dismissal | Partial | Ignored/dismissed fields exist. | Add "dismiss as false positive" with reason and detector learning/dedupe suppression. |
| History/audit log | Partial | ResultEvent and some history tables exist. | Show per-issue/per-task timeline; include who/what/when. |
| Re-check after sync | Partial | Detectors and result events exist; no universal re-check contract found. | Add module contract method: `is_issue_still_active(issue)` and automatic reopen/resolve. |
| Weekly digest in portal + email | Partial/Missing | Results page exists; no clear email digest implementation found. | Add weekly digest job and portal digest page/email adapter. |
| Excel export of problems/tasks | Partial | Finance/DQ/reconciliation/stock exports exist. | Add unified issue/task export. |
| Time-to-first-issue <= 30 min | Not proven | Sync jobs exist, but no end-to-end onboarding proof. | Add acceptance smoke: new user -> key -> sync -> first issue timer. |
| 3 pilot clients and confirmed savings | Product/process gap | Code cannot prove this. | Track pilot acceptance and confirmed result events. |

## Architecture Match

TZ wants:

- One frontend.
- FastAPI modular monolith.
- One DB/auth/company model.
- Common data layer loaded once.
- Modules as detectors producing `Issue[]`.

Current project mostly matches the technical direction:

- FastAPI modular monolith is in place.
- Frontend is a single React/TanStack app.
- Auth/accounts are centralized.
- Operator layer exists.
- Optional modules degrade safely.

But the clean module contract is not fully enforced. Today modules can expose their own route families, data models and UI pages. That is useful for development, but the MVP product should converge on a single portal loop.

## Biggest Product Gaps

1. Single Issue model is not product-final.

   There are operator diagnoses/actions and several module-specific issue-like models. Create a canonical `IssueRead`/`Issue` table or explicitly promote `OperatorDiagnosis` to the canonical issue model with required fields: `source_module`, `detector_code`, `entity_ref`, `severity`, `money_impact`, `title`, `explanation`, `recommendation`, `status`, `dedup_key`, `history`.

2. Task Center is functional but not collaboration-complete.

   `UnifiedAction` has assignee/deadline/comment/closed/dismissed fields, but TZ needs comments, attachments, manual tasks, review status, and full timeline.

3. MVP scope is too broad in UI.

   Photo Studio, A/B tests, Grouping, Stock Control, Ads and other modules are visible. TZ says these should not be in MVP as primary user modules.

4. Onboarding is not self-service enough.

   Login exists, accounts/tokens exist, but the TZ journey says a new user should register, create company, connect WB key and get first findings without help.

5. Digest and saved-money proof need product hardening.

   Result tracking exists, but weekly digest and confirmed savings counters are not yet presented as the central retention mechanic.

6. Re-check loop is not universal.

   TZ requires that after a task is closed the system verifies whether the issue disappeared and reopens if not. Current implementation has result events and detectors, but not an obvious generic re-check lifecycle.

## MVP Scope Recommendation

For a strict TZ MVP, configure the frontend into a focused mode:

Primary navigation:

- What needs attention / Action Center
- Legacy profit diagnostics
- Products / Checker
- Finance
- Data Fix / Costs
- Results
- Settings

Hide or move under "Beta / later":

- Photo Studio
- A/B tests
- Grouping
- Stock Control
- Purchase Plan
- Ads
- Analytics
- Marts/Admin-only technical pages

## Suggested Implementation Roadmap

### Sprint 1: Product Spine

- Define canonical `Issue` contract and map existing `OperatorDiagnosis`, `DataQualityIssue`, finance blockers, card-quality issues and claims candidates into it.
- Add `/portal/issues` endpoint with filters and sorting by money impact/priority/status/assignee.
- Make frontend main screen consume `/portal/issues`.
- Keep existing modules as detail pages, not main product spine.

### Sprint 2: Task Center Completion

- Add manual task creation.
- Add comments and attachments.
- Align statuses with TZ: `new`, `in_progress`, `review`, `closed`, `dismissed`.
- Add per-task timeline from result/history events.
- Add "dismiss false positive" reason.

### Sprint 3: Onboarding

- Seller-facing registration/invite acceptance.
- Company creation flow.
- WB token connection wizard with category validation.
- First sync progress UI.
- First-audit completion screen: found issues, money impact, top 3.

### Sprint 4: Closed Loop

- Add re-check contract for issue types.
- Add automatic resolve/reopen behavior after sync.
- Add saved-money counters.
- Add weekly digest generation and portal digest view.
- Add issue/task Excel export.

### Sprint 5: MVP Polish

- Hide phase-2/phase-3 modules from default navigation.
- Run an end-to-end acceptance test for the TZ DoD.
- Verify with 3 pilot accounts and record confirmed savings.

## Current Readiness Estimate

Technical backend readiness for the TZ direction: high.

Product-MVP readiness: medium.

The codebase has many of the pieces, but the MVP needs a stronger product spine:

`Issue feed -> explanation -> task -> status/history -> result/savings`

Without that spine, the app feels like a broad seller analytics/admin portal. With it, the same code can become the Control Tower described in the TZ.
