# Implementation Plan

This plan converts the master prompt into a safe Finance-owned execution sequence.

## Phase 0: Guardrails And Baseline

Status: started with static discovery.

Tasks:

- Keep Finance as the single auth/account/token/DB boundary.
- Keep frontend calls routed through Finance/Portal APIs.
- Preserve default-off external writes.
- Do not copy legacy projects wholesale.
- Establish current OpenAPI, migrations, tests, and frontend build status.

Commands:

```bash
cd backend && python -m compileall app
cd backend && pytest
cd frontend && npm run build
```

Expected output:

- compile passes;
- backend tests pass or failures are documented;
- frontend build passes or contract/type failures are documented.

## Phase 1: Contract Audit

Goal: prove frontend/backend route parity.

Tasks:

- Generate backend OpenAPI from local app.
- Compare OpenAPI paths against `frontend/src/lib/endpoints.ts`, `frontend/src/lib/money-endpoints.ts`, and `frontend/src/lib/portal.ts`.
- Mark every frontend endpoint as `matched`, `alias`, `stale`, or `missing backend`.
- Mark every product-required backend endpoint as `used`, `admin-only`, `legacy/raw`, or `missing frontend`.
- Fix stale frontend endpoint constants before UI work.

Deliverables:

- Update `04_ACCEPTANCE_MATRIX.md`.
- Add or update contract tests where feasible.

## Phase 2: Runtime Data Proof

Goal: distinguish real data from placeholder/degraded responses.

Tasks:

- Start backend against configured PostgreSQL.
- Confirm at least one accessible `account_id`.
- Run sync/data readiness endpoints only in read-safe mode.
- For each core module, call endpoint with real `account_id`, `date_from`, and `date_to`.
- Record whether response is real-data-backed, empty, disabled, not configured, unavailable, or fixture-like.
- Fill `WB_DATA_SOURCE_CATALOG.md`, `DATA_FRESHNESS_REPORT.md`, and `DB_DATA_QUALITY_REPORT.md` with real row counts, latest source dates, account/token coverage, stale cursors, duplicate/orphan/unmatched summaries, and last successful sync evidence.
- Fill `DATA_READINESS_COSTS_AUDIT.md` with real blocker grouping and costs flow proof.
- Fill `CARD_QUALITY_AUDIT.md` with runtime analyze/run/coverage/products/Data Fix/Product 360/action/doctor proof.
- Fill `STOCK_TZ_AUDIT.md` with runtime return_excess, ship_from_hand, store_balance, regional supply, hand stock, movement, export, Product 360, Actions, and Doctor proof.
- Fill `REPUTATION_AUDIT.md` with runtime reviews/questions/chats sync, inbox, draft lifecycle, safe publish, Product 360, Actions, Doctor, and Results proof.

Required proof:

- money summary and cascade;
- dashboard and data health;
- products and Product 360;
- action center;
- costs/missing costs;
- data readiness;
- modules health;
- results;
- optional modules with explicit degraded states where expected.

## Phase 3: Formula And Finance Audit

Goal: verify money calculations against formulas and source rows.

Tasks:

- Keep `FINANCE_METRIC_DICTIONARY.md` and `FINANCE_FORMULA_AUDIT.md` current with the canonical formulas and runtime proof.
- Trace money summary fields to services/marts/source tables.
- Verify revenue, commission, logistics, storage, penalties, deductions, manual costs, seller other expenses, taxes if present.
- Verify zero/null behavior: unknown values must be `null`, not fake zero.
- Check cost placeholder handling and supplier-confirmed flags.
- Add unit tests for any formula bug found.
- Recompute product `nm_id=245405620` and at least 20 additional products from real DB source rows, then compare to `/money/*` and `/portal/products/{nm_id}` outputs.

High-risk files to inspect first:

- `backend/app/services/money_management.py`
- `backend/app/services/money_snapshots.py`
- `backend/app/services/manual_costs.py`
- `backend/app/core/manual_cost_math.py`
- `backend/app/services/marts.py`
- `backend/app/services/trust.py`

## Phase 4: Optional Module Closure

Goal: ensure optional modules are useful, safely degraded, and frontend-visible.

Tasks by module:

- Card Quality: verify product quality analysis, issues, run retry, status updates; keep WB apply off.
- Card Quality: Products aggregate now carries local quality metrics and the frontend can filter/sort by card quality; runtime proof still needed for full catalog coverage and legacy Checker parity.
- Reputation: verify inbox, summary, draft generation, no-reply, approve/reject/regenerate; publish remains blocked unless fully configured and explicitly confirmed.
- Reputation: frontend now wires sync, inbox filters, draft lifecycle, no-reply, and safe publish calls to Finance local endpoints; runtime source proof still needed.
- Claims: verify candidate detection, case creation, evidence, draft, proof check; submit remains blocked unless fully configured and explicitly confirmed.
- Claims: frontend now wires local scan, candidates, candidate-to-case, draft, proof-check, and `confirm=true` manual submit; seller reads hide synthetic/audit/test cases in the service layer; runtime proof still needed for real detector data and Product 360/Actions/Doctor/Results closure.
- Grouping Beta: verify preview and candidate status; apply/merge remains off.
- Grouping Beta: frontend now wires local full-catalog/product preview and local accept/reject/postpone review actions; Finance still exposes no WB merge route; runtime proof still needed for real full-catalog empty/non-empty runs and Product 360/Actions/Doctor/Results closure.
- Photo Studio: verify project CRUD, assets, versions, jobs, settings, experiment links; auto-apply remains off.
- Photo Studio: frontend now uses backend-owned routes for WB import, secure upload, messages, review, retry/cancel, and signed downloads; local manual mode can create reviewable versions from uploaded assets without a provider. Runtime proof still needed for real WB source images, Product 360/Data Fix/Actions entry points, and Results visibility after approval.
- Experiments/Results: verify before/after baseline, intervention record, 7/14-day post collection, evaluation, confounders, Product 360 event block, Photo Studio experiment bridge, and safe causality wording.
- Experiments/Results: result events now preserve sanitized experiment evidence and the Results page renders baseline/post windows, primary metric movement, data sufficiency, and confounders; Photo Studio approved versions can start a 14-day tracking experiment. Runtime proof still needed with real sales/funnel/stock data.
- Stock Control: verify status/settings, imports preview, drafts, runs, overview/export; no WB mutation.
- Stock Control: local store_balance planning is now available through preview and run lifecycle; still needs runtime proof with two accessible accounts.

## Phase 5: Frontend Runtime UX

Goal: prove the app works as a product, not just isolated endpoints.

Tasks:

- Run `cd frontend && npm run test:e2e` for the mock-backed canonical navigation suite before live-browser proof.
- Start frontend dev server.
- Login and select account.
- Walk main navigation: dashboard, money, actions, products, Product 360, data-fix, costs, settings.
- Walk beta navigation where modules are present: stock control, grouping, photo studio, reputation, claims, results.
- Capture errors, console logs, failed network requests, layout breaks.
- Fix contract/UI bugs with focused diffs.
- Frontend/E2E: first-party Playwright harness now covers authenticated shell, canonical navigation, Product 360, Results experiment evidence, Photo Studio empty state, API error state, and mobile overflow/sidebar smoke with browser-level `/api/v1/*` mocks. Live backend/browser proof still needed for final evidence.

## Phase 6: Security, RBAC, And Secrets

Goal: prevent unsafe data exposure and writes.

Tasks:

- Confirm account-scoped server-side checks on portal endpoints.
- Verify normal users cannot spoof `account_id`.
- Verify token fields are redacted in responses/logs.
- Run existing security/secret leak tests.
- Verify write endpoints require explicit feature flag and confirmation.
- Ensure audit events exist for confirmed actions.
- Section 13: frontend login defaults no longer contain real-looking credentials; a frontend secret-literal scanner now covers source/config/E2E files; backend deploy CI runs backend secret and deploy artifact safety scans.

## Phase 7: Performance And Deploy Readiness

Goal: catch slow endpoints and deploy blockers.

Tasks:

- Review portal indexes and query shapes for list/detail endpoints.
- Check scheduler behavior and job failure isolation.
- Verify migrations apply linearly.
- Check deploy artifacts exclude `_incoming_projects`, audit bundles, logs, raw env, raw DB dumps, and secrets.
- Verify CORS/settings are environment-driven.
- Verify `.github/workflows/deploy-finance-backend.yml` from repository root, including backend path filters, backend working directory, clean backend-only rsync context, Alembic startup, systemd restart, nginx reload, and health check.
- Identify or add a separate frontend build/deploy gate; the current workflow is backend-only.
- Verify heavy WB sync requests follow `POST -> 202 queued run -> worker/background processor -> GET /sync/runs`; manual sync was changed to this lifecycle in the Section 02 pass.
- Section 13: `.github/workflows/frontend-ci.yml` now runs frontend install, build, Chrome install, and mock-backed Playwright E2E.

## Phase 8: Final Audit ZIP

Goal: produce a final evidence bundle without secrets.

Include:

- repo/module/legacy maps;
- acceptance matrix;
- OpenAPI/frontend contract diff;
- test command outputs;
- runtime endpoint smoke summaries with sanitized payload excerpts;
- frontend screenshots/network summary;
- known risks and follow-up tasks.

Exclude:

- raw `.env`;
- raw DB dumps;
- tokens, passwords, cookies, JWTs;
- buyer PII;
- raw WB API responses containing sensitive fields;
- incoming ZIPs unless explicitly sanitized and necessary.
