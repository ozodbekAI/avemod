# MVP E2E Smoke Test

The frontend MVP smoke test covers the seller loop:

login -> Action Center -> evidence -> task drawer -> status/update path -> re-check or disabled reason -> Results timeline.

## Command

Run from `frontend/`:

```bash
npm run test:e2e:mvp
```

## Required Environment

Do not hardcode credentials. CI/staging must provide:

```bash
E2E_BASE_URL=https://your-staging-frontend.example
E2E_EMAIL=pilot-user@example.com
E2E_PASSWORD=...
```

`E2E_BASE_URL` points to the frontend app. When it is set, Playwright does not start the local Vite dev server. When it is not set, the default Playwright config starts `http://127.0.0.1:5173`.

The test skips locally if any required env var is missing, but fails in CI when the env contract is incomplete.

## What It Verifies

- Login succeeds with the provided env credentials.
- Action Center loads a usable state.
- If a problem row exists, evidence opens from `Как посчитано?`.
- The task drawer exposes assignment/deadline, status, re-check, history, and result sections.
- Status/update controls work when the row supports them; otherwise a clear disabled reason is visible.
- Re-check is either launched or the UI explains why it cannot be run.
- The Results link opens a timeline with the correlation disclaimer.
- Mobile smoke verifies no desktop sidebar dependency, Action Center card layout, and full-screen task drawer.

If no problem row exists, the test requires a professional no-data/not-configured state instead of a crash.
