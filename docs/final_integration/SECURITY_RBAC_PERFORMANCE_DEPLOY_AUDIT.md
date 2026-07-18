# Security RBAC Performance Deploy Audit

Generated during Section 13 on 2026-06-25.

## Static Status

- Login no longer pre-fills a real-looking admin email or password in `frontend/src/routes/login.tsx`.
- Audit helper defaults use a non-routable `example.invalid` address instead of a live-test admin identity.
- `scripts/scan_frontend_secret_literals.py` scans frontend source, E2E tests, Playwright config, and package metadata for credential-shaped literals.
- Backend deploy CI runs compile, backend secret-leak scan, deploy artifact safety scan, Alembic checks, and tests before deploy.
- Frontend CI now runs `npm ci`, `npm run build`, installs Playwright Chrome, and runs `npm run test:e2e`.
- Deploy artifact safety is checked both by the workflow gate and the existing static deploy tests.

## RBAC And Tenant Isolation

- Portal write routes continue to use account/role helpers through `_required_portal_account_for_role`.
- Auth still centralizes account resolution through `resolve_user_account` and role checks through `require_account_role`.
- Claims, reputation, experiments, Photo Studio, grouping, and stock-control writes remain account-scoped at the route/service boundary.

## Deploy Guardrails

- Backend release upload excludes local runtime material such as `_incoming_projects`, logs, reports, DB files, spreadsheets, HAR/trace files, ZIPs, and audit bundles.
- Remote activation applies Alembic migrations, restarts the systemd service, validates/reloads nginx, and checks `/api/v1/health`.
- Frontend build and mock-backed E2E are separated into their own workflow so UI regressions are caught independently of backend deploy.

## Remaining Runtime Proof

- Run GitHub Actions on a real branch to prove hosted runners have the same browser/system package behavior as local verification.
- Run tenant-spoof and role-negative smoke tests against a disposable account in the target environment.
- Capture timing samples for high-volume portal list/detail endpoints after production-like data is available.
- Confirm worker/scheduler startup and failed-job isolation in the deployment environment.
