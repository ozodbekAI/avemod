# Acceptance Matrix

Generated as an initial static matrix on 2026-06-25. Runtime cells must be updated after backend/frontend/test runs.

Legend:

- `PASS`: verified in this audit pass.
- `STATIC`: code surface exists, runtime proof pending.
- `PARTIAL`: useful implementation exists, but gap or default-off state remains.
- `BLOCKED`: cannot verify without environment/config/credentials.
- `FAIL`: verified broken.

| Area | Acceptance Requirement | Current Evidence | Status | Next Proof |
| --- | --- | --- | --- | --- |
| Repo discovery | Find frontend/backend/scheduler/migrations/tests/incoming ZIPs | backend, frontend, scheduler, migrations, tests, ZIPs discovered | PASS | Keep docs updated |
| Local rules | Read `AGENTS.md` | Rules incorporated into docs | PASS | None |
| Auth/accounts | Single login/account boundary, server-side account access | auth/accounts modules and tests exist | STATIC | Run auth/security tests; attempt account spoof smoke |
| Tokens | WB tokens never exposed | token model/service present; redaction rules in AGENTS/core | STATIC | Run secret leak tests and response scan |
| Finance source of truth | PostgreSQL finance data backs money/product decisions | finance/money/marts modules exist | BLOCKED | Run against configured DB and real account |
| Money calculations | Formulas verified from source rows to UI | money services/tests exist | PARTIAL | Formula trace and targeted tests |
| Finance formula dictionary | Required Section 03 metric dictionary and audit docs exist | Dictionary/audit docs added in Section 03 pass | PARTIAL | Fill with real DB recomputation results |
| Dashboard overview | Seller sees overview from real backend | dashboard and portal overview exist | STATIC | Runtime endpoint and browser proof |
| Data readiness | DQ issues/summary/investigator work | data_quality module and UI route exist | STATIC | Run `/dq/*` and `/portal/data-readiness` |
| Costs | Manual costs, missing/unresolved, supplier confirmation | manual_costs module and tests exist | STATIC | Runtime upload/preview/confirm smoke with safe fixture |
| Data readiness/costs flow | Cost mutations refresh DQ and seller Data Fix hides raw codes | DQ refresh wired into cost mutations; audit doc added | PARTIAL | Real DB/frontend wizard smoke |
| Legacy profit diagnostics | Admin/operator diagnosis based on available data | `/portal/doctor` and tests exist | STATIC | Real account response with source evidence |
| Action Center | Actions can be viewed/updated and result events recorded | `/portal/actions`, `/portal/results`, UI exist | STATIC | Runtime mutate/result event smoke |
| Products | Product list backed by portal/finance | `/portal/products` now exposes card quality status, score, issue count, photo count, analyzed time; UI filter/sort added | PARTIAL | Runtime product list proof with real quality snapshots |
| Product 360 | Product detail aggregates money/quality/grouping/events | Product 360 renders local quality score, issues, recommendations, photos, analyzed time, and category scores | PARTIAL | Runtime detail proof for real `nm_id` |
| Card Quality | Read/analyze/issues available; no unsafe apply | local service/adapter/routes/tests exist; `CARD_QUALITY_AUDIT.md` added; Data Fix copy covers title/description/characteristics/media issues | PARTIAL | Runtime analyze/status proof; confirm apply is unavailable/default-off |
| Stock control | Regional supply/hand stock/run/export flows available | stock_control module/domain/UI/tests exist; local store_balance preview/run added; audit doc added | PARTIAL | Runtime return/ship/store/import/export proof with safe fixture and two accounts |
| Reputation | Inbox/summary/drafts work; publish guarded | local reputation service/routes exist; frontend lifecycle actions wired; audit doc added | PARTIAL | Runtime reviews/questions/chats sync proof; inbox/draft/no-reply/publish-blocked proof |
| Claims | Detection/cases/drafts/proof work; submit guarded | claims service/adapter/routes/tests exist; frontend scan/candidate/case/draft/proof/manual-submit flow wired; synthetic seller rows hidden; `CLAIMS_FACTORY_AUDIT.md` added | PARTIAL | Runtime candidate/case/evidence/draft/proof/manual-submit proof with real DB/account |
| Grouping beta | Preview/recommendations available; apply guarded | local engine/routes/tests exist; frontend preview/review flow wired; no WB merge route; `GROUPING_BETA_AUDIT.md` added | PARTIAL | Runtime full-catalog/product preview proof; review status proof; Product 360/Actions/Doctor/Results closure |
| Photo Studio | Projects/assets/versions/jobs/settings available; manual provider-free flow works; auto-apply off | frontend route contract aligned to backend assets/messages/review/signed-download endpoints; uploaded/WB assets can create local versions; approval records Results while marketplace apply stays disabled | PARTIAL | Runtime project/upload/WB import/version/review/job proof; Product 360/Data Fix/Actions/Results smoke |
| Experiments | Create/start/cancel/evaluate/events available; baseline/intervention/post/evaluation tracked safely | before/after service collects metric snapshots, evaluates confounders, emits experiment ResultEvents with safe causality note; Photo Studio bridge creates 7/14-day photo experiments | PARTIAL | Runtime baseline/intervention/post/evaluate lifecycle with real product data |
| Results | Unified result events visible with safe wording and experiment evidence | Results UI renders experiment baseline/post windows, primary result, data sufficiency, confounders; result schema preserves sanitized payload | PARTIAL | Runtime result listing proof after a real experiment evaluation |
| Settings/modules health | Module health reports explicit states | module registry and UI exist | STATIC | Runtime `/portal/modules/health` proof |
| Workers/scheduler | Jobs registered and optional scheduler works | scheduler and job registry exist | BLOCKED | Run with `enable_scheduler` in safe env |
| WB sync lifecycle | Heavy manual sync should not finish inside HTTP request | `/sync/trigger` and `/sync/backfill` now enqueue and return 202 | PARTIAL | Runtime queued-run smoke with real DB/token |
| WB data freshness | Row counts/latest dates/cursors prove DB source of truth | Static source catalog added | BLOCKED | Query real PostgreSQL and update reports |
| Frontend routes | Main and beta pages exist, canonical navigation has E2E smoke | route files discovered; Playwright suite covers core navigation, Product 360, Results, Photo Studio empty, API error, and mobile smoke; frontend CI now runs build and mock E2E | PARTIAL | Run live browser smoke against real backend |
| Frontend/backend contracts | Endpoint constants match backend OpenAPI and stale UI paths are guarded | central endpoint map exists; API client warns on known UI-route-as-API mistakes; Section 12 static tests cover recent module endpoint constants | PARTIAL | Generate OpenAPI diff; expand live network assertions |
| Repo/deploy architecture | Backend deploy workflow uses correct backend root and clean deploy context | Backend deploy workflow runs compile, secret scan, deploy artifact safety scan, Alembic checks, tests, backend-only rsync, remote migration/restart/nginx/health; frontend CI added | PARTIAL | Run GitHub Actions workflow on hosted runners |
| Optional degraded states | No false OK for disabled/not_configured/unavailable modules | frontend health normalization and backend adapters show explicit statuses | STATIC | Endpoint audit for every optional module |
| Security writes | External writes require flag + confirm + role + audit | adapters include disabled paths; AGENTS requires default-off | PARTIAL | Direct publish/submit/apply endpoint smoke |
| Secret hygiene | No secrets in logs/docs/responses/audit ZIP | backend and frontend secret scanners exist; login hardcoded credential defaults removed; docs exclude raw env/dumps | PARTIAL | Run scanners in CI and audit bundle scan |
| Migrations | Alembic chain linear and deployable | migrations discovered | STATIC | `alembic heads`, `alembic upgrade head` in test DB |
| Performance | Portal endpoints indexed and tolerable | portal perf migration exists | STATIC | Query timing/runtime profiling smoke |
| Final audit ZIP | Sanitized evidence bundle generated | not generated in this pass | BLOCKED | Complete runtime/test phases first |

## Immediate Findings

- The product has far more local implementation than the master prompt assumes; many optional modules are already represented as Finance-owned services/routes/models/tests.
- The next highest-value work is contract/runtime proof, not bulk legacy import.
- Runtime verification is blocked until the backend can connect to the intended PostgreSQL DB and the frontend/backend can be started with the right environment.
- Frontend endpoint parity should be checked before fixing UI bugs, because stale endpoint constants can mimic broken modules.

## First Commands To Run

```bash
cd backend && python -m compileall app
cd backend && pytest
cd frontend && npm run build
```

After these, run a sanitized endpoint smoke suite against a real account and update this matrix from `STATIC/PARTIAL/BLOCKED` to `PASS/FAIL`.
