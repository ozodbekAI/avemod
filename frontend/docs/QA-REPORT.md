# Frontend QA — Final Pass

Date: 2026-05-25
Scope: invalid API path audit + per-page business answer check.

## API path audit

Searched `src/**` for any string referencing UI routes used as API calls.

| Suspect path | Found as API call? | Where it appears | Verdict |
|---|---|---|---|
| `/money` (bare) | No | only as `<Link to="/money">` | OK — UI route |
| `/cards`, `/cards/{nmId}` | No | only as router `<Link>` and `navigate()` | OK — UI route |
| `/sku/{id}` | No | only as router `<Link>` and `navigate()` | OK — UI route |
| `/data-fix` | No | UI route only | OK |
| `/costs` (bare) | No | API calls use `/costs/rows`, `/costs/imports`, etc. | OK |
| `/finance` (bare) | No | API calls use `/finance/report-rows`, `/finance/reports` | OK |
| `/operations` | No | removed; only sub-endpoints `/sync/*`, `/orders`, `/sales`, `/supplies`, `/dashboard/data-health` | OK |
| `/pricing` (bare) | No | API uses `/pricing/safety`, `/pricing/simulate` | OK |
| `/purchase-plan` (bare) | No | API uses `/inventory/purchase-plan` | OK |

Runtime guard: `assertValidApiPath()` in `src/lib/api.ts` warns in dev if any of
the above slip back in. Whitelist source of truth: `INVALID_API_PATHS` (api.ts)
and `FORBIDDEN_API_PATHS` (endpoints.ts).

## Per-page checklist

| Page | Endpoint(s) | Status | Business question answered | Remaining issue |
|---|---|---|---|---|
| `/money` | `/money/summary`, `/money/actions/today`, `/money/data-blockers` | OK | Yes — store money status, waterfall, top risks/opps | none |
| `/cards` | `/money/articles`, `/money/filters` | OK | Yes — article list grouped by `nm_id`, sortable by profit/loss | `/money/filters` not in user's allow list but is a real backend route used for brand/subject options |
| `/cards/:nmId` | `/money/articles/{nm_id}` | OK | Yes — per-article detail with SKU breakdown | none |
| `/sku/:id` | `/money/cards/{sku_id}` (+ fallback `/core-sku/{sku_id}`) | OK | Yes — SKU economics | none |
| `/actions` (inside `/money` tab + dashboard) | `/money/actions/today`, `/money/actions` | OK | Yes — top owner actions first, sorted by priority | none |
| `/data-fix` | `/money/data-blockers`, `/dashboard/data-health`, `/dq/issues`, `/dq/issues/summary` | OK | Yes — blockers + open issues with links to source | none |
| `/costs` | `/costs/rows`, `/costs/imports`, `/dashboard/data-health` | OK | Yes — cost coverage and supplier-confirmed coverage separated | none |
| `/finance` | `/finance/report-rows`, `/marts/finance-reconciliation`, `/marts/account-expense-daily`, `/finance/reports` | OK | Yes — reconciliation + unallocated expenses visible | none |
| `/ads` | `/ads/efficiency`, `/ads/stats`, `/ads/campaigns` | OK | Yes — ДРР and profit-after-ads per card | none |
| `/pricing` | `/pricing/safety`, `/pricing/simulate` | OK | Yes — unsafe price reasons + simulator modal | none |
| `/purchase-plan` | `/inventory/purchase-plan` | OK | Yes — REORDER / DO_NOT_BUY / LIQUIDATE / WATCH / WAIT_DATA with explanation | none |
| `/settings` | `/settings/business` (PATCH), `/settings/business/policies` (GET) | OK | Yes — saves with PATCH, cost policy impact warning shown | none |
| `/dashboard` | `/money/summary`, `/money/actions/today`, `/money/articles`, `/money/data-blockers` | OK | Yes — main cockpit, matches `/money` truth | legacy `/dashboard/owner` kept only as secondary link |
| `/operations` | `/sync/runs`, `/sync/cursors`, `/orders`, `/sales`, `/supplies`, `/dashboard/data-health` | OK | Operational/debug only, lazy tabs | none |

## Cross-cutting

- **Trust state**: components use `BusinessStatusBanner` / `trust_state` badge.
  No page renders "final / trusted" wording when `business_status === "provisional"`
  or `trust_state` ∈ {`test_only`, `provisional`}. Cautionary copy is shown instead.
- **0 vs null**: `formatMoney`, `formatNumber`, and table cells render `—` for `null` / `undefined`
  and `0` / `0,00 ₽` for real zero. Verified in `src/lib/format.ts` and table renderers.
- **Loading UX**: React Query with `staleTime` 2–5 min, debounced search (350 ms),
  `keepPreviousData` on browsers, lazy tab mounting on `/operations`, `/money`, `/finance`.
- **Error UX**: `EndpointError` handles 401 (login), 404 ("Frontend endpoint mapping xato" + path),
  422 (validation details), 500 (retry).

## Audit result

- 0 invalid API routes called from the frontend.
- 0 forbidden UI routes hit as API.
- All pages answer their primary business question; no page contradicts
  `/money/summary` as the source of truth.
