# Verification Baseline

Date: 2026-07-07

Purpose: establish a reproducible verification baseline before product UI/UX
and Dynamic Problem Engine hardening.

## Environment

Repository path:

- `/home/ozodbek/AVEMOD_PROJECTS/Finance`

Frontend environment:

- `node --version`: `v24.11.1`
- `npm --version`: `11.6.2`
- `frontend/package-lock.json`: lockfile version `3`

Backend environment:

- Plain `python` is not available on PATH in this shell:
  `/bin/bash: line 1: python: command not found`
- `python3 --version`: `Python 3.12.3`
- `backend/.venv/bin/python --version`: `Python 3.12.3`
- `backend/.venv/bin/python -m pip --version`: `pip 24.0`
- Installed editable backend package:
  `wb-data-core-backend 0.1.0`

## Inspected Configuration

Frontend:

- `frontend/package.json`
- `frontend/package-lock.json`
- `frontend/vite.config.ts`
- `frontend/playwright.config.ts`
- `frontend/src/server.ts`
- `frontend/src/start.ts`
- `frontend/src/router.tsx`
- `frontend/src/routeTree.gen.ts`

Frontend scripts relevant to this baseline:

- `npm run test:problem-copy`
  - `node scripts/check-problem-ux-copy.mjs`
- `npm run test:problem-loop`
  - `node scripts/check-problem-loop-acceptance.mjs`
- `npm run test:action-center-contract`
  - `node tests/actionCenterContract.test.mjs`
- `npm run test:action-center-filters`
  - `node tests/actionCenterFilters.test.mjs`
- `npm run build`
  - `vite build`

Backend:

- `backend/README.md`
- `backend/AGENTS.md`
- `backend/wb_data_core_backend.egg-info/PKG-INFO`
- `backend/wb_data_core_backend.egg-info/requires.txt`
- `backend/tests/unit/test_result_tracking_service.py`
- `backend/tests/unit/test_portal_service.py`
- `backend/tests/unit/test_problem_engine_runner.py`
- `backend/tests/api/test_problem_rule_admin_routes.py`

Backend dependency metadata in the installed egg requires Python `>=3.12` and
lists runtime dependencies including FastAPI, Uvicorn, SQLAlchemy, asyncpg,
psycopg2-binary, Alembic, Pydantic, pydantic-settings, httpx, python-jose,
passlib, cryptography, APScheduler, python-multipart, openpyxl,
email-validator, OpenCV headless, Pillow, pytesseract, rapidocr-onnxruntime and
zxing-cpp.

Dev/test extras in the installed egg metadata:

- `pytest>=8.2.0`
- `pytest-asyncio>=0.23.7`
- `pytest-cov>=5.0.0`
- `httpx>=0.27.0`
- `anyio>=4.4.0`
- `ruff>=0.5.0`
- `mypy>=1.10.0`
- `bandit>=1.7.9`

## Frontend Commands

### Install

Command:

```bash
cd frontend
npm ci
```

Result: passed.

Observed output:

- Deprecated warnings:
  - `tsconfck@3.1.6: unmaintained`
  - `recharts@2.15.4: 1.x and 2.x branches are no longer active`
- `added 502 packages, and audited 503 packages in 5s`
- `found 0 vulnerabilities`

Conclusion: frontend install is reproducible from `package-lock.json`.

### Product Checks

Command:

```bash
cd frontend
npm run test:problem-copy
```

Result: passed.

Observed output:

- `Problem UX copy check passed.`

Command:

```bash
cd frontend
npm run test:problem-loop
```

Result: passed.

Observed output:

- `Professional problem loop acceptance check passed.`

Command:

```bash
cd frontend
npm run test:action-center-contract
```

Result: passed.

Observed output:

- Script exited with code `0`.

Command:

```bash
cd frontend
npm run test:action-center-filters
```

Result: passed.

Observed output:

- Script exited with code `0`.

### Build

Command:

```bash
cd frontend
npm run build
```

Result: passed.

Observed output:

- Lovable config printed:
  `No Lovable context detected — skipping nitro deploy plugin.`
- Client build:
  - Vite `v7.3.6`
  - `3145 modules transformed`
  - built in `12.59s`
- SSR build:
  - `263 modules transformed`
  - built in `9.34s`
- Build completed without hanging.

Known build warning:

- `dist/client/assets/index-Cf0Ue11X.js` is about `600K`.
- Vite warns that some chunks are larger than `500 kB` after minification.
- This is not blocking the baseline, but should be handled later with route or
  vendor code splitting.

SSR/hang notes:

- No SSR hang reproduced.
- `frontend/vite.config.ts` delegates to
  `@lovable.dev/vite-tanstack-config` and sets
  `tanstackStart.server.entry` to `server`.
- `frontend/src/server.ts` is a thin SSR error wrapper that lazy-imports
  `@tanstack/react-start/server-entry`.
- `frontend/src/start.ts` only installs an error middleware.
- Route generation completed; `frontend/src/routeTree.gen.ts` is `886` lines.
- The large route/source files are notable but did not block this build:
  - `action-center.tsx`: `4605` lines
  - `DataFixWorkbench.tsx`: `1414` lines
  - `admin.tsx`: `635` lines
  - `results.tsx`: `649` lines

## Backend Commands

### Compile

Requested command shape:

```bash
python -m compileall app tests
```

Current shell issue:

- Plain `python` is not available on PATH.

Executed command:

```bash
cd backend
.venv/bin/python -m compileall app tests
```

Result: passed.

Observed output:

- `compileall` listed `app` and `tests` packages and exited with code `0`.

Conclusion: backend syntax compile gate passes with Python 3.12 from the
existing backend virtualenv.

### Targeted Tests

Command:

```bash
cd backend
.venv/bin/python -m pytest -q \
  tests/unit/test_result_tracking_service.py \
  tests/unit/test_portal_service.py \
  tests/unit/test_problem_engine_runner.py \
  tests/api/test_problem_rule_admin_routes.py
```

Result: passed.

Observed output:

- `85 passed, 2 warnings in 6.45s`

Warnings:

- `passlib` imports `crypt`, which is deprecated and slated for removal in
  Python 3.13.
- `fastapi.testclient` emitted a Starlette deprecation warning recommending
  `httpx2`.

Conclusion: result tracking, portal service, problem engine runner and admin
problem-rule route tests pass in the current backend venv.

## Backend Dependency Reproducibility Finding

`backend/README.md` says to install dependencies with:

```bash
python -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"
```

However, the current backend working tree does not contain a Python packaging
manifest:

- no `backend/pyproject.toml`
- no `backend/setup.py`
- no `backend/setup.cfg`
- no committed `backend/requirements*.txt`

The installed egg metadata references `pyproject.toml` in
`wb_data_core_backend.egg-info/SOURCES.txt`, but that file is absent.

Verification command:

```bash
cd backend
.venv/bin/python -m pip install --dry-run -e ".[dev]"
```

Result: failed.

Observed output:

```text
Obtaining file:///home/ozodbek/AVEMOD_PROJECTS/Finance/backend
ERROR: file:///home/ozodbek/AVEMOD_PROJECTS/Finance/backend does not appear to be a Python project: neither 'setup.py' nor 'pyproject.toml' found.
```

Impact:

- Backend tests currently pass because the existing `.venv` already has an
  editable install and dependencies.
- A fresh backend dependency install is not reproducible until the packaging
  manifest or a committed requirements file is restored.

Required fix:

- Restore `backend/pyproject.toml` or add an equivalent committed dependency
  manifest.
- Keep `requires-python = ">=3.12"`.
- Preserve the runtime and dev dependencies currently recorded in
  `backend/wb_data_core_backend.egg-info/PKG-INFO` / `requires.txt`.
- Prefer documenting setup with `python3` in this environment:

```bash
cd backend
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"
```

## Baseline Verdict

Pass:

- Frontend install is reproducible with `npm ci`.
- Frontend product checks pass.
- Frontend Vite/TanStack client and SSR build pass.
- Backend compile passes with Python 3.12 from `backend/.venv`.
- Requested targeted backend tests pass.

Not blocking this baseline, but must be fixed before relying on fresh backend
setup:

- Backend dependency installation is not reproducible from the current working
  tree because the packaging manifest is missing.

Follow-up:

- Restore backend packaging metadata before broader hardening.
- Later, reduce the large frontend client `index` chunk with code splitting.
