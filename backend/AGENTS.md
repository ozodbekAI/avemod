# AGENTS.md

Persistent instructions for Codex and other coding agents working in this finance backend for Seller Portal AI Operator.

## Product Direction

- Finance is the core backend, main database, auth boundary, account boundary, token boundary, and money source.
- The MVP is not a full rewrite.
- Portal is an aggregation layer over existing finance capabilities, not a rewrite of the backend.
- The MVP is: Finance + current frontend/portal UI + Action Center + Product 360 + Checker issues in read-only mode.
- Checker, grouping, StockOps, Photo Studio, reviews/reputation, and defect claims are modules, not separate products in the MVP.
- Checker is read-only in the MVP.
- Grouping is beta recommendation only in the MVP.
- StockOps is optional in the MVP.
- Reviews/reputation and defect claims must be integrated gradually through finance-owned portal/operator endpoints.
- Frontend must call finance/portal endpoints only, never checker/grouping/StockOps/reviews/claims services directly.
- Incoming external projects under `_incoming_projects/` are reference/source material only. They should inform adapters, contracts, and UX decisions without replacing the finance architecture.

## Safety Rules

- Never expose WB/marketplace tokens, encrypted WB tokens, JWTs, encryption keys, API keys, passwords, internal service credentials, or other secrets in frontend responses, logs, errors, tests, fixtures, screenshots, generated docs, or smoke output.
- Never log raw tokens, JWTs, encryption keys, API keys, passwords, marketplace credentials, internal service credentials, request headers, or authorization values.
- Never enable WB write/apply actions in the MVP.
- Never enable auto-apply to Wildberries by default.
- Never enable auto-publish replies by default.
- Never enable auto-submit defect claims or appeals by default.
- Never enable checker apply-all.
- Never enable card auto-apply by default.
- Never enable grouping auto-merge or `merge-wb`.
- Never make StockOps launch WB-modifying operations from the portal.
- Never copy entire external projects into finance.
- Treat external zip projects as reference/source only.
- Extract only the specific logic, contracts, or fixtures needed for a focused implementation.
- Keep finance auth, account, token, and permission boundaries authoritative.
- Marketplace-changing operations require manual preview, explicit user confirmation, account-scoped permission checks, and an audit event before any submit/apply/publish call is allowed.
- If a marketplace-changing operation is not fully wired with preview, confirm, permissions, and audit, return `disabled` or `not_configured` instead of performing the operation.

## Implementation Rules

- Prefer small incremental changes.
- Before writing new backend code, search existing finance modules, services, schemas, migrations, tests, and docs for matching behavior.
- Reuse existing patterns from auth, accounts, money_management, data_quality, manual_costs, dashboard, marts, and control_tower.
- Reuse existing finance auth, account, money, data-quality, costs, marts, and dashboard logic.
- Do not duplicate business math if finance already has a function, service, mart, or schema for it.
- Do not rewrite or replace existing working finance code unless the task explicitly requires fixing that code and tests cover the behavior.
- Do not replace the existing auth/account/token system.
- Do not replace working code with new abstractions unless absolutely needed.
- Add adapters for external modules instead of merging their whole codebases.
- Frontend must call finance/portal endpoints, not checker/grouping/StockOps/reviews/claims directly.
- If optional modules are unavailable, core finance pages must still work.
- Keep optional module failures isolated from money, actions, products, data-fix, costs, and settings.
- Checker, grouping, StockOps, reviews/reputation, and defect-claims failures must not break money, actions, products, Product 360, data-fix, costs, or settings.
- Optional module responses should use explicit statuses such as `ok`, `not_configured`, `unavailable`, `empty`, `beta`, and `disabled`.
- Record `unavailable_sources` where it helps the frontend show a clear degraded state.
- Keep frontend contracts stable and documented. When response shapes change, update schemas, docs, and tests together.
- Every implementation must add or update unit tests, API tests, smoke checks, or a documented smoke script for the touched behavior.
- Do not introduce unrelated large refactors while implementing portal features.

## Preferred Folder Structure

- Finance-owned API routes live under `app/modules/<domain>/router.py`.
- Portal/operator aggregation routes live under `app/modules/portal/router.py` until they become large enough to split into a focused finance-owned module.
- Portal/operator orchestration lives in `app/services/portal.py` or a focused `app/services/operator_*.py` service.
- External module adapters live in `app/services/*_adapter.py`, for example:
  - `app/services/checker_adapter.py`
  - `app/services/grouping_adapter.py`
  - `app/services/stockops_adapter.py`
  - `app/services/reputation_adapter.py`
  - `app/services/defect_claims_adapter.py`
- Finance-owned persistence models live in `app/models/*.py`; do not import external project model trees wholesale.
- Finance-owned repositories live in `app/repositories/*.py` when persistence logic is non-trivial.
- API response/request schemas live in `app/schemas/*.py`; shared portal contracts may remain in `app/schemas/portal.py`.
- Migrations are forward-only Alembic revisions in `alembic/versions/` and must follow the existing linear chain.
- Tests belong near the touched behavior:
  - API route tests in `tests/api/`.
  - Service/adapter/model tests in `tests/unit/`.
  - Smoke scripts in `scripts/` only when tests cannot cover the workflow cleanly.
- Documentation for frontend/backend contracts belongs in `docs/`.

## Naming Conventions

- Use `signal` for observed facts or metrics from finance or optional modules. Examples: `stockout_signal`, `review_risk_signal`, `quality_score_signal`.
- Use `diagnosis` for interpreted causes. Examples: `margin_drop_diagnosis`, `claim_compensation_gap_diagnosis`.
- Use `action` for recommended operator work. Examples: `card_quality_action`, `reply_draft_action`, `claim_appeal_action`.
- Use `case` for defect/claim/support lifecycle records. Examples: `defect_case`, `support_case`.
- Use `evidence` for files, snapshots, screenshots, finance traces, WB responses, and other proof attached to a case. Examples: `case_evidence`, `finance_trace_evidence`.
- Use `draft` for AI-generated or operator-prepared content that has not been published/submitted. Examples: `reply_draft`, `claim_appeal_draft`.
- Use `result_event` for audited outcomes of confirmed operations. Examples: `reply_publish_result_event`, `claim_submit_result_event`, `grouping_preview_result_event`.
- Prefer stable source keys:
  - `source_module`
  - `source_type`
  - `source_id`
  - `external_id`
  - `account_id`
  - `nm_id`
  - `sku_id`
- Status fields should use lowercase snake/string values already present in finance where possible: `new`, `in_progress`, `done`, `postponed`, `ignored`, `ok`, `empty`, `disabled`, `unavailable`, `not_configured`.

## Response Shape Conventions

Portal/operator responses should be predictable and degraded-state friendly.

- Include `status` for module/block state when a response can be partial.
- Put primary payload in `data` for new generic module responses, or in existing typed fields when extending established schemas.
- Include `warnings` as a list for non-fatal issues the frontend may show.
- Include `unavailable_sources` as a list when any optional source fails or is not configured.
- Include `module_health` on overview/summary endpoints that aggregate multiple modules.
- Include `trust_state` where money, data quality, or operator confidence affects decisions.
- Use `null` for unknown values, not fake zeroes.
- Use `[]` for empty lists and `{}` for empty objects.
- Scrub token-like fields recursively from response payloads before returning data to the frontend.
- Prefer explicit module block states over HTTP 5xx for optional module failures.

## Permission Model

- Superusers can access all accounts.
- Normal users can access only accounts they own or are explicitly allowed to access.
- Portal endpoints must not be superuser-only unless they are clearly admin-only.
- Do not weaken security by allowing `account_id` spoofing.
- Account-scoped access checks must happen server-side, not only in the frontend.
- Marketplace-changing confirms must record who confirmed the operation and which account/entity was affected.

## MVP Navigation

Main navigation:

- Dashboard / Overview
- Money
- Actions
- Products / Cards
- Product 360
- Data Fix
- Costs
- Settings

Advanced/Beta navigation:

- Finance raw reports
- Ads
- Pricing
- Purchase plan
- Stock
- StockOps
- Grouping Beta
- Photo Studio
- Reviews / Reputation
- Defect Claims
- Experiments
- Admin/dev pages

## Done Criteria

- Existing tests pass, or documented failures are explained clearly.
- After backend changes, run a compile check and the relevant tests for the touched area.
- If tests cannot run because of an environment dependency, document the exact blocker and the command that failed.
- New portal endpoints have tests or at least smoke checks.
- Add smoke scripts or tests for new portal behavior.
- No secrets appear in logs, frontend responses, screenshots, fixtures, or generated documents.
- No unrelated large refactors are included.
- Keep diffs small and focused.
- Do not include unrelated refactors, formatting churn, or dependency additions.
- Every task must end with a concise report that includes:
  - Changed files.
  - Verification commands and results.
  - Known risks, skipped tests, or follow-up items.
