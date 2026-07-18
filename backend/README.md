# Finance Backend

Finance is the authoritative backend for Seller Portal AI Operator. It owns auth, accounts, marketplace tokens, money data, portal/operator aggregation, and the main database.

## Local Setup

Use Python 3.12.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

Configure environment variables from `deploy/finance.env.example` when running against real services. Never put WB tokens, JWT secrets, API keys, passwords, or internal credentials into committed files, fixtures, logs, screenshots, docs, or smoke output.

If your system exposes Python 3.12 as `python` instead of `python3.12`, use
`python -m venv .venv` for the first command. After activation, use
`python -m ...` so the project venv is always selected.

## Unit Test Verification

For a fresh checkout or CI job, install dependencies first and then run the
same compile and targeted unit checks used for portal/result-tracking changes:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
python -m compileall -q app tests
python -m pytest -q tests/unit/test_result_tracking_service.py tests/unit/test_portal_service.py
```

## Safety Defaults

The MVP is read/preview/review first. Checker apply, Grouping `merge-wb`, StockOps WB modifications, Reputation publish, and Claims submit must remain disabled unless a flow has manual preview, explicit confirmation, account-scoped permission checks, and audit/result events.

Optional modules must degrade safely with explicit statuses such as `ok`, `empty`, `disabled`, `unavailable`, and `not_configured`. Frontend callers should use Finance/Portal endpoints only.

## Verification

Run the P0/P1 closure gate:

```bash
.venv/bin/python scripts/run_p0_p1_closure_checks.py
```

The script runs compile checks, Ruff, Mypy, Bandit, secret scan, Alembic head checks, targeted portal/module tests, full tests, and coverage for critical modules. Real PostgreSQL Alembic upgrade must also be proven in the deployment environment with:

```bash
P0_P1_POSTGRES_DATABASE_URL=postgresql://user:pass@host:5432/db \
  .venv/bin/python scripts/run_p0_p1_closure_checks.py
```

By default the coverage gate enforces the current proven critical-module baseline. To enforce the pilot hardening target, run with `P0_P1_STRICT_COVERAGE=1`; this keeps the 85% target explicit while the remaining legacy monolith coverage is raised.

## Deploy Context

Deploy/build contexts must exclude local databases, logs, reports, audit bundles, zips, caches, `_incoming_projects/`, generated artifacts, and secret-bearing files. Check a context with:

```bash
.venv/bin/python scripts/check_deploy_artifact_safety.py --root .
```
