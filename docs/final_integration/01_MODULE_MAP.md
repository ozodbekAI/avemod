# Module Map

Generated from static discovery on 2026-06-25.

Status legend:

- `implemented`: local backend/frontend/test surfaces exist.
- `partial`: meaningful surface exists, but runtime proof or full product loop is not yet established in this pass.
- `reference`: exists as legacy ZIP/reference only.
- `needs verification`: must be checked against a running backend, DB, and real account data.

## Core Product Modules

| Module | Backend Surface | Frontend Surface | Test/Fixture Surface | Initial Status |
| --- | --- | --- | --- | --- |
| Auth / Accounts / Tokens | `app/modules/auth`, `app/modules/accounts`, `app/services/auth.py`, `app/services/accounts.py`, auth/account models | login route, account context, top bar account selector, admin account/token UI | auth schema/security/access tests | implemented, needs security/runtime verification |
| Finance / Money | `app/modules/finance`, `app/modules/money_management`, finance/money services, marts | dashboard, money, finance, expenses, cards/catalog | money service/API tests, Etap3 money acceptance | implemented, needs real-data formula audit |
| Dashboard / Overview | `app/modules/dashboard`, `app/modules/control_tower`, `app/modules/portal` overview | dashboard route | dashboard API/service tests, portal overview fixture | implemented, needs runtime proof |
| Data Readiness / DQ | `app/modules/data_quality`, data quality service/repository | data-fix route, dashboard health panels | DQ/marts tests | implemented, needs runtime proof |
| Costs / Себестоимость | `app/modules/manual_costs`, cost math helpers | costs route, unresolved/missing costs UI | manual costs route/service tests | implemented, needs formula audit |
| Legacy profit diagnostics | `/portal/doctor`, profit doctor service | doctor route and admin diagnostics references | profit doctor service tests, fixture | implemented, needs data-source proof |
| Action Center | `/portal/actions`, control tower actions | action-center route, actions route | portal route/service tests, action fixtures | implemented, needs end-to-end mutation proof |
| Products | `/portal/products`, `/products`, product card/core SKU modules | products route, cards/catalog routes | product 360 and portal fixtures | implemented, needs contract parity audit |
| Product 360 | `/portal/products/{nm_id}` | products detail route | product 360 contract fixtures | implemented, needs runtime proof |
| Card Quality / Checker | card quality models/service, checker adapter, `/portal/card-quality/*`, product quality endpoints | cards/products quality UI | card quality/checker adapter tests | partial: local read/analyze exists; WB apply remains default-off |
| Stock / TZostatka / Regional Supply | stocks module, `stock_control` module/domain, stockops adapter | stock, stock-control route/workflows | stock service/domain/adapter tests | implemented/partial, no WB mutation proof expected |
| Reputation / Reviews / Questions / Chats | reputation model/service/adapter, `/portal/reputation/*` | reputation route | reputation service/adapter tests, fixtures | partial: drafts/actions exist; publish disabled by feature flag unless configured |
| Claims Factory | claims models/service/adapter, `/portal/cases/*`, `/portal/claims/*` | claims route | claims adapter/factory tests, fixtures | partial: candidates/cases/drafts exist; submit disabled by feature flag unless configured |
| Grouping Beta | grouping model/service/adapter, `/portal/grouping/*`, product grouping | grouping route, product detail grouping | grouping tests | partial: beta recommendation flow; merge/apply must remain off |
| Photo Studio | photo studio model/service, `/portal/photo/*` | photo-studio routes | photo studio tests | partial: project/assets/jobs exist; generation/apply depend on config |
| Experiments / Result Evaluation | experiments service/model, `/portal/experiments/*`, product events, Photo Studio version experiment bridge | results/product/photo studio references | experiments/result tracking tests | implemented, needs runtime proof |
| Results | result tracking service, `/portal/results`, result event endpoints, experiment evidence payloads | results route | result tracking tests, fixtures | implemented, needs runtime proof |
| Settings / Integrations | business settings, module registry, `/portal/modules/health`, settings endpoints | settings route, modules health section, data sync section | module registry/config tests | implemented, needs config audit |
| Workers / Scheduler / Jobs | `app/core/scheduler.py`, `app/jobs/registry.py`, `app/jobs/sync_jobs.py` | admin/data sync trigger UI | sync schema tests, smoke backend tests | partial: runtime depends on `enable_scheduler` and environment |
| Frontend Runtime / UX / Contracts | OpenAPI-backed backend, central `endpoints.ts`, typed clients | full app route tree | backend fixture contract tests; frontend build not yet run in this pass | partial, needs build and browser smoke |

## Backend Route Families

Discovered route families include:

- Auth/accounts: `/auth/login`, `/auth/refresh`, `/auth/me`, `/auth/logout`, `/users`, `/accounts`, `/accounts/{account_id}/tokens`.
- Portal/operator: `/portal/doctor`, `/portal/overview`, `/portal/actions`, `/portal/products`, `/portal/results`, `/portal/modules/health`.
- Card quality: `/portal/card-quality/analyze`, `/portal/card-quality/runs`, `/portal/card-quality/issues`, `/portal/products/{nm_id}/quality`.
- Reputation: `/portal/reputation/inbox`, `/portal/reputation/summary`, drafts, approve/reject/regenerate/publish guarded operations.
- Claims: `/portal/cases`, case evidence/drafts/proof/submit, detection endpoints, claim scans/candidates.
- Photo: `/portal/photo/status`, settings, projects, assets, versions, messages, jobs.
- Experiments: `/portal/experiments`, start/cancel/evaluate/metrics/events.
- Grouping/stockops: `/portal/grouping/preview`, candidate status, `/portal/stockops/run`, runs.
- Stock control: `/portal/stock-control/status`, settings, import previews, hand-stock drafts, runs, run details/export.
- Finance/money/raw business data: `/money/*`, `/finance/*`, `/marts/*`, `/dq/*`, `/costs/*`, `/dashboard/*`, `/core-sku/*`, `/products`, `/prices`, `/orders`, `/sales`, `/stocks`, `/supplies`, `/ads/*`, `/analytics/*`, `/tariffs`, `/documents`.

## Frontend Route Families

Authenticated frontend route files exist for:

- dashboard, money, finance, expenses;
- actions and action-center;
- products, Product 360, cards/catalog;
- data-fix and costs;
- stock and stock-control;
- grouping, photo-studio, reputation, claims, results;
- settings and admin/dev workflows;
- ads, analytics, pricing, purchase-plan, operations, marts.

## Contract Notes

- Frontend central path source is `frontend/src/lib/endpoints.ts`.
- Finance/money calls are mostly in `frontend/src/lib/money-endpoints.ts`.
- Portal calls are in `frontend/src/lib/portal.ts`.
- `frontend/src/lib/api.ts` includes guardrails against outdated/nonexistent backend paths.

Known contract items to verify:

- Photo endpoints in `endpoints.ts` now map to the backend-owned contract: `/assets/import-wb`, `/assets/upload`, `/messages`, `/versions/{version_id}/review`, job retry/cancel, and signed asset download URLs. Manual WB follow-up is recorded as a project message; no auto-apply route is exposed.
- Stock control aliases intentionally point multiple frontend helpers to the same backend routes. Confirm no stale UI calls remain.
- All frontend business calls must send `account_id`, and date-scoped calls must send `date_from` and `date_to` where required.

## Safety Notes

Implemented optional modules must preserve default-off behavior for:

- reputation publish;
- claims submit;
- grouping apply/merge;
- card auto-apply;
- stock auto-apply;
- photo auto-apply;
- price/ads/WB mutation.

Any endpoint returning HTTP 200 with `disabled`, `not_configured`, `placeholder`, empty, or fixture-only data remains incomplete until it has an explicit product reason and UI state.
