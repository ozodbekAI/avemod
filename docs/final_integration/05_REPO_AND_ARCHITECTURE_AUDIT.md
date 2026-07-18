# Repo And Architecture Audit

Generated from Section 01 of the prompt package on 2026-06-25.

## Scope

This pass covered:

- frontend/backend roots;
- module and worker locations;
- legacy ZIP and deploy structure;
- single auth/account/DB/Portal API requirements;
- module registry, frontend, RBAC, and deploy checks referenced by master prompt sections 17, 18, 22, and 23.

## Architecture Baseline

| Requirement | Finding | Status |
| --- | --- | --- |
| One backend | FastAPI backend lives in `backend/app`, with one API router mounted from `backend/app/main.py`. | Pass |
| One frontend | React/TanStack frontend lives in `frontend/src`. | Pass |
| One DB authority | Backend config uses one `DATABASE_URL`; Finance models/migrations own local module persistence. | Pass, runtime DB not verified |
| One auth boundary | `app/services/auth.py` owns JWT, refresh tokens, account access, role checks. | Pass, runtime RBAC tests pending |
| One account boundary | Portal, sync, costs, stock control and several dashboard endpoints call `resolve_user_account`/`require_account_role`. | Partial, raw read endpoints need full audit |
| One Portal API | Product/operator modules are exposed mainly under `/portal/*`; raw finance endpoints still exist for advanced/admin pages. | Pass for MVP direction |
| Workers/scheduler | `app/core/scheduler.py` and `app/jobs/registry.py` are used from FastAPI lifespan when `ENABLE_SCHEDULER=true`. | Pass, runtime worker proof pending |
| Module registry | `app/services/module_registry.py` reports finance, doctor, actions, products, checker, stockops, grouping, reputation, claims, photo, experiments, results. | Pass, real DB state proof pending |
| Legacy ZIPs | `_incoming_projects` exists under backend and is excluded from lint/type/test/deploy contexts. | Pass |
| Deploy context | GitHub Actions and deploy scripts exist; deploy excludes zips/logs/reports/cache/artifacts and runs Alembic plus health check. | Fixed workflow root mismatch in this pass |

## Fixed Issue

### Deploy workflow assumed wrong repository root

Evidence:

- Workflow file is `.github/workflows/deploy-finance-backend.yml`.
- Backend code lives under `backend/app`, `backend/alembic`, `backend/pyproject.toml`.
- The workflow previously watched `app/**`, `alembic/**`, `pyproject.toml`, etc. at repository root.
- The test job ran `python -m pip install -e ".[dev]"` from root, where no `pyproject.toml` exists.
- The deploy upload used `rsync ./`, which would upload the workspace root instead of a clean backend deploy context expected by `remote_deploy_finance_backend.sh`.

Fix:

- Updated workflow path filters to `backend/...`.
- Set the test job default run directory to `backend`.
- Changed deploy upload step to `cd backend` before rsync.

Regression:

- Static workflow syntax/root check is pending via local grep/parse or GitHub Actions run.
- Full regression requires GitHub Actions or equivalent container with PostgreSQL.

## Deploy Structure

Deploy files:

- `.github/workflows/deploy-finance-backend.yml`
- `backend/deploy/README.md`
- `backend/deploy/finance-backend.service`
- `backend/deploy/finance.env.example`
- `backend/deploy/nginx.finance.ozodbek-akramov.uz.conf`
- `backend/deploy/nginx.operator.ozodbek-akramov.uz.conf`
- `backend/deploy/remote_deploy_finance_backend.sh`

Deploy behavior:

- CI test job starts PostgreSQL 16.
- Backend install uses editable package with dev dependencies.
- Compile, Alembic heads, Alembic SQL generation, and pytest run before deploy.
- Deploy rsync excludes `.git`, virtualenv/cache folders, frontend, `_incoming_projects`, source/extract folders, exports, logs, reports, zips, DB files, spreadsheets, HAR/trace/log files, audit bundles, raw audits, and coverage HTML.
- Remote activation installs dependencies, switches `current` symlink, runs Alembic upgrade, restarts systemd service, reloads nginx, and checks `/api/v1/health`.

Remaining deploy checks:

- Confirm frontend deploy/build pipeline separately; current workflow is backend-only.
- Confirm production nginx hostname choice between finance and operator configs.
- Confirm worker startup policy: current scheduler is in API process and controlled by `ENABLE_SCHEDULER`; no separate worker service found.
- Confirm backup docs/process beyond env example and deploy README.
- Confirm monitoring beyond health endpoint and request timing middleware.

## Frontend Architecture

Frontend root:

- `frontend/`

Core files:

- `frontend/src/lib/api.ts`
- `frontend/src/lib/endpoints.ts`
- `frontend/src/lib/money-endpoints.ts`
- `frontend/src/lib/portal.ts`
- `frontend/src/lib/account-context.tsx`
- `frontend/src/lib/date-range-context.tsx`
- `frontend/src/routes/_authenticated.tsx`
- `frontend/src/components/AppSidebar.tsx`

Initial findings:

- API paths are centralized in `endpoints.ts`.
- `api.ts` has guardrails against calling UI routes as backend paths.
- Portal client is isolated in `portal.ts`.
- Account and date range contexts exist.
- Settings module health UI recognizes `ok`, `warning`, `not_configured`, `disabled`, `unavailable`, `error`, `unknown`.

Frontend verification still needed:

- `npm run build`.
- Browser smoke for canonical seller navigation.
- Endpoint map diff against generated local OpenAPI.
- Stale/duplicate legacy route review: advanced pages exist and should remain hidden/admin/beta where appropriate.

## RBAC And Account Boundary

Core service:

- `backend/app/services/auth.py`

Important helpers:

- `get_current_user`
- `list_user_account_access`
- `resolve_user_account`
- `resolve_user_account_role`
- `require_account_role`

Current behavior from static review:

- Missing auth returns 401.
- Foreign account access returns 403.
- Unknown account returns 404.
- Superuser can access all active accounts.
- Account roles support viewer/operator/manager/admin style checks through module-level role sets.

High-priority RBAC audit target:

- Several raw read routers accept optional `account_id`. They may be intended for advanced/admin data browsing, but each must be reviewed for `get_current_user` and account filtering before final acceptance.
- Portal and write-like workflows should remain the primary frontend path.

## Module Registry

Required modules from master section 17:

- finance
- doctor
- actions
- products
- card_quality/checker
- stock_control/stockops
- reputation
- claims
- grouping
- photo
- experiments
- results

Local implementation:

- `ModuleRegistryService.health()` returns the required product families, with local DB state preferred over environment fallback.
- Registry statuses currently include `ok`, `disabled`, `not_configured`, `degraded`, `unavailable`; other prompt statuses such as `empty`, `running`, `partial`, `failed`, `not_implemented` appear in other module responses and should be normalized before final acceptance.

Follow-up:

- Compare DB `portal_integrations` rows with computed local health for stale registry rows.
- Verify Settings UI renders real module health for a real account.
- Treat `empty` as valid only after a completed local run/sync proves no data.

## Open Issues

| Issue | Severity | Owner Area | Recommended Next Step |
| --- | --- | --- | --- |
| Backend deploy workflow root mismatch | High | Deploy | Fixed in this pass; run workflow/test locally or in GitHub |
| Frontend deploy/build not covered by backend workflow | Medium | Deploy/frontend | Identify current frontend host pipeline or add separate workflow |
| Raw read endpoints need account-auth audit | High | RBAC | Static scan every router and add focused tests for foreign account access |
| Module registry status vocabulary differs from prompt | Medium | Settings/integrations | Normalize or document allowed aliases in schema/tests |
| Runtime DB/source-of-truth proof missing | High | Architecture/data | Start backend with real DB and update acceptance matrix |

## Regression Commands

```bash
cd backend && python -m compileall app tests scripts alembic
cd backend && python -m alembic heads
cd backend && python -m pytest -q -p no:ddtrace
cd frontend && npm run build
```

For deploy workflow regression, run the GitHub Actions workflow or mirror its test job from repository root after this fix.
