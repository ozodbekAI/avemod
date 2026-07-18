# Repo Map

Generated from local discovery on 2026-06-25.

## Product Shape

This workspace contains a modular-monolith Seller Portal / Finance product with:

- `backend/`: FastAPI backend, PostgreSQL/Alembic persistence, WB sync clients, portal aggregation, scheduler jobs, tests.
- `frontend/`: TanStack Router + React frontend, typed API clients, portal pages, money pages, settings, stock control, photo studio.
- `backend/_incoming_projects/`: legacy/reference ZIP archives only. Per `backend/AGENTS.md`, these must not replace Finance architecture.
- `frontend/audit_bundle/`: prior acceptance audit ZIPs with screenshots/network summaries.

The root directory is not a Git repository in this workspace. No git status baseline is available.

## Agent And Product Rules

Primary local rules are in `backend/AGENTS.md`.

Key constraints:

- Finance is the auth, account, token, database, and money authority.
- Frontend must call Finance/Portal endpoints only.
- Optional modules must degrade with explicit states such as `disabled`, `not_configured`, `unavailable`, `empty`, or `beta`.
- WB write/apply/publish/submit operations stay default-off and require explicit preview, confirmation, role checks, idempotency, and audit events.
- Incoming ZIP projects are reference material. Extract only focused logic/contracts/fixtures when needed.

## Backend

Backend root: `backend/`

Runtime entrypoint:

- `backend/app/main.py`
- FastAPI app includes `app.api.router:api_router` under `settings.api_v1_prefix`.
- Scheduler starts only when `settings.enable_scheduler` is true.

Router registry:

- `backend/app/api/router.py`
- Includes health, auth, accounts, meta, money management, portal, stock control, sync, costs, marts, data quality, SKU, product cards, prices, orders, sales, stocks, finance, supplies, ads, analytics, tariffs, documents, exports, dashboard.

Important backend folders:

- `backend/app/models/`: SQLAlchemy models for accounts, auth, finance, marts, operator, card quality, claims, grouping, reputation, photo studio, stock control, etc.
- `backend/app/modules/`: FastAPI route modules and WB sync clients.
- `backend/app/services/`: business services and optional-module adapters.
- `backend/app/repositories/`: persistence access layer.
- `backend/app/schemas/`: Pydantic contracts.
- `backend/app/core/`: config, DB, security, scheduler, redaction, observability, math helpers, sync helpers.
- `backend/app/jobs/`: scheduler job registry and sync jobs.
- `backend/domain/stock_control/`: stock control algorithms and IO helpers.
- `backend/alembic/versions/`: forward Alembic migrations.
- `backend/tests/`: unit, API, integration tests and contract fixtures.

Deploy structure:

- `backend/deploy/README.md`
- `backend/deploy/finance-backend.service`
- `backend/deploy/finance.env.example`
- `backend/deploy/nginx.finance.ozodbek-akramov.uz.conf`
- `backend/deploy/nginx.operator.ozodbek-akramov.uz.conf`
- `backend/deploy/remote_deploy_finance_backend.sh`
- `.github/workflows/deploy-finance-backend.yml`

## Frontend

Frontend root: `frontend/`

Runtime/tooling:

- `frontend/package.json`
- Vite dev/build scripts.
- React 19, TanStack Router/Start, TanStack Query, Radix UI, Tailwind, lucide-react, Recharts.

Important frontend folders:

- `frontend/src/routes/`: app routes. Authenticated routes include dashboard, money, actions/action-center, products, product 360, data-fix, costs, settings, grouping, stock control, photo studio, reputation, claims, results, finance, ads, pricing, purchase plan.
- `frontend/src/lib/api.ts`: API base URL, auth refresh, path guardrails, shared types.
- `frontend/src/lib/endpoints.ts`: central backend endpoint map.
- `frontend/src/lib/money-endpoints.ts`: finance/money client functions.
- `frontend/src/lib/portal.ts`: typed client for `/portal/*`.
- `frontend/src/components/`: shared UI, portal helpers, money UI, settings health, stock-control workflows.

## Migrations

Migration chain is in `backend/alembic/versions/` and currently spans:

- initial finance schema through WB data normalization and finance correctness repairs;
- control tower and trust/performance additions;
- normalized expense accounting and manual cost fixes;
- API response snapshots;
- experiment events;
- auth user account access;
- operator foundation;
- portal performance indexes and module registry;
- card quality, stock control, reputation, claims, grouping beta, photo studio, experiment result evaluation.

Latest discovered migration file:

- `backend/alembic/versions/20260623_000041_experiments_result_evaluation.py`

Potential anomaly to verify before new migrations:

- both `20260622_000039_claims_local_candidates.py` and `20260623_000039_grouping_beta_local_module.py` include `000039` in the filename. Confirm Alembic revision IDs and down-revisions are linear before adding another migration.

## Tests

Backend tests:

- `backend/tests/unit/`: service, adapter, schema, security, audit, runtime, contract fixture tests.
- `backend/tests/api/`: health, control tower, dashboard, manual costs, money detail, portal route tests.
- `backend/tests/fixtures/portal/`: contract fixture snapshots for overview, actions, product 360, results, reputation, claims, modules health.

Frontend tests were not discovered in the initial scan. Frontend verification currently appears to rely on build/lint/manual or external acceptance audit bundles.

## Legacy And Audit Inputs

Incoming reference archives:

- `backend/_incoming_projects/all.zip`
- `backend/_incoming_projects/audit-bundle.zip`
- `backend/_incoming_projects/backend (7) .zip`
- `backend/_incoming_projects/backenddefect.zip`
- `backend/_incoming_projects/backendfinance.zip`
- `backend/_incoming_projects/checker.zip`
- `backend/_incoming_projects/groupingbackend.zip`

Frontend audit bundles:

- `frontend/audit_bundle/LOVABLE_FINAL_ACCEPTANCE_AUDIT_2026-06-16.zip`
- `frontend/audit_bundle/LOVABLE_FINAL_ACCEPTANCE_AUDIT_2026-06-17.zip`

## Initial Risk Notes

- The master prompt asks for real WB data runtime proof and final audit ZIP generation. That requires DB credentials, configured tokens, running backend/frontend, and explicit test commands.
- Existing code already has many optional module states. Each module still needs endpoint-level runtime proof to distinguish real implementation from a clean degraded response.
- Frontend endpoint map contains comments about live OpenAPI as source of truth. Contract parity should be checked against local `app.openapi()` and/or running `/openapi.json`.
- Backend deploy workflow root mismatch was found and fixed in `.github/workflows/deploy-finance-backend.yml`; full proof requires a GitHub Actions run or equivalent local CI mirror.
