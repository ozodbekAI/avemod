# Frontend And E2E Audit

Generated during Section 12 on 2026-06-25.

## Static Status

The frontend now has a first-party Playwright harness.

- `npm run test:e2e` runs `playwright test`.
- `playwright.config.ts` starts the Vite dev server and runs desktop plus mobile Chromium projects by default.
- Set `PLAYWRIGHT_BROWSER_CHANNEL=chrome` only when a run should use system Google Chrome.
- E2E tests install a browser-level API mock for `/api/v1/*`, so navigation and UX states can be tested without a live backend.
- The mock covers auth, accounts, module health, dashboard/overview, Action Center, Products, Product 360, Results, Photo Studio, Claims, Reputation, Grouping, Stock Control, money/cost/catalog endpoints, and generic empty envelopes for safe fallback.

## Covered Flows

- Authenticated app shell and canonical sidebar navigation.
- Products list to Product 360 deep link.
- Product 360 mounted money and data-quality sections.
- Results page experiment evidence: baseline, post window, safe correlation wording.
- Photo Studio empty state and manual project `nm_id` input.
- API failure state with retry button.
- Mobile viewport smoke: desktop sidebar hidden and no horizontal overflow.

## Guardrails

- Frontend API client keeps a development-time invalid path list for UI routes that must never be called as backend endpoints.
- Section 12 static tests verify key route files, endpoint constants, Playwright config, and E2E coverage phrases.

## Remaining Runtime Proof

- Run the E2E suite against a live backend with a real sanitized account after environment setup.
- Add visual screenshots for the final audit bundle.
- Expand E2E with mutation flows once a disposable test account/database is available.
