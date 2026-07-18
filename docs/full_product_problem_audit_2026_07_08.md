# Full Product Problem Audit

Date: 2026-07-08

Scope: audit of the recent professional problem-loop prompts across frontend,
backend, tests and build output.

## Result

Product-loop, backend, e2e and production-build audit passed after fixes.
Frontend global lint still has a broad pre-existing formatting/type cleanup
backlog; see Residual Notes.

Confirmed areas:

- frontend install is reproducible with `npm ci`;
- Action Center route remains small and delegates to extracted components/hooks;
- dynamic problem contracts/adapters are covered by frontend contract tests;
- Product360, Action Center, Results and Data Fix share the same problem identity
  in the cross-surface e2e fixture;
- result events keep `saved_money_claimed=false` unless measured after-data is
  explicitly available;
- checker/content issues are guarded from becoming confirmed financial loss;
- legacy diagnostics are hidden from seller navigation and available as legacy
  diagnostics only;
- price/promo safety, missing cost blockers and money trust copy are covered by
  backend/frontend tests;
- production build completes without SSR hang or Vite chunk-size warning.

## Fixes Made During Audit

1. Frontend backend-contract test expected an older Action Center deep link
   without `source_id`. The product link now carries both `source_id` and
   `problem_instance_id` for exact task focus, so the test was updated.

2. Checker static UI test expected old English-adjacent copy
   `Открыть Photo Studio`. The current seller copy is Russian:
   `Открыть фотостудию`; the test was updated.

3. Checker static UI test still inspected the slim route file for Action Center
   internals after the component extraction. It now checks
   `ActionCenterPageContainer` and the mutation hook.

4. Action Center adapter carried `source_sync_state`, but the UI did not expose
   it directly. Added a Russian source-sync label helper plus:
   - row badge for non-unknown sync states;
   - drawer `Синхронизация` field for every task.

5. Bundle analysis report was regenerated from the current `dist` output, and
   the build-performance doc was updated with the latest build times and chunk
   sizes.

6. Backend full pytest initially collected `_incoming_projects`, which are
   documented as reference-only material. Added `backend/pytest.ini` so normal
   backend pytest runs only the current backend tests and skips reference
   archives.

7. Backend static tests and portal contract fixtures were aligned with the
   extracted frontend architecture and current Russian seller copy:
   - Results static test now checks the shared correlation disclaimer contract;
   - navigation static test expects `Проектов пока нет` and `До действия`;
   - reputation Action Center test inspects the container/adapter contract after
     route extraction;
   - Photo Studio beta navigation test expects `Фотостудия`;
   - `action_update_ok.json` now includes SLA/status/evidence fields emitted by
     `PortalActionRead`.

8. Action Center no longer renders raw backend `can_update_reason` keys to
   sellers. Added a Russian label mapper for readonly/update reasons such as
   `external_reputation_recommendation`, source shadow updates, checker, costs,
   finance and problem-engine workflow reasons.

9. Manual costs service test fixture was corrected for the current three-query
   flow: missing-cost revenue rows, total revenue rows and SKU rows. This keeps
   missing-cost/data-blocker coverage aligned with the negative-profit guardrail.

10. `ActionCenterPageContainer.tsx` was formatted with Prettier after the UI
    reason-label fix. Targeted ESLint for this file has no errors.

## Verification Commands

Frontend:

```bash
cd frontend
npm ci
npm run test:problem-copy
npm run test:problem-loop
npm run test:action-center-contract
npm run test:action-center-backend-contract
npm run test:action-center-filters
npm run test:legacy-diagnostics
npx playwright test e2e/navigation.spec.ts --project=desktop
npx playwright test e2e/action-center-professional.spec.ts --project=desktop
npx playwright test e2e/navigation.spec.ts --project=mobile -g "mobile Action Center"
npx eslint src/components/action-center/ActionCenterPageContainer.tsx
npm run build
npm run analyze:bundle:write
```

Backend:

```bash
cd backend
../.venv/bin/python -m compileall app tests
../.venv/bin/python -m pytest -q tests/unit/test_result_tracking_service.py tests/unit/test_portal_service.py
../.venv/bin/python -m pytest -q tests/unit/test_problem_engine_runner.py tests/api/test_problem_rule_admin_routes.py
../.venv/bin/python -m pytest -q tests/api/test_action_center_result_ledger_integration.py tests/unit/test_problem_engine_portal_integration.py tests/unit/test_problem_engine_price_safety.py
../.venv/bin/python -m pytest -q tests/unit/test_card_quality_service.py tests/unit/test_portal_action_source_sync.py tests/api/test_portal_action_center_contract.py
../.venv/bin/python -m pytest -q tests/unit/test_data_fix_dynamic_problem_bridge.py tests/unit/test_product_problem_loop_acceptance_static.py tests/unit/test_problem_rules_admin_ui_static.py tests/unit/test_checker_status_only_ui_static.py
../.venv/bin/python -m pytest -q
```

## Verification Results

- `npm ci`: passed, 0 vulnerabilities.
- Frontend static/contract scripts: passed.
- `navigation.spec.ts --project=desktop`: 5 passed, 1 mobile-only skipped.
- `action-center-professional.spec.ts --project=desktop`: 8 passed.
- `navigation.spec.ts --project=mobile -g "mobile Action Center"`: 1 passed.
- `npm run build`: passed.
  - client build: 10.96s;
  - SSR build: 10.03s;
  - no SSR hang;
  - no Vite chunk-size warning.
- `npx eslint src/components/action-center/ActionCenterPageContainer.tsx`:
  passed with 0 errors and 4 existing React hook dependency warnings.
- Backend `compileall`: passed.
- Backend selected unit/API coverage: passed.
  - `result_tracking_service` + `portal_service`: 80 passed, 1 warning;
  - `problem_engine_runner` + admin rule routes: 5 passed, 1 warning;
  - result ledger + portal integration + price safety: 21 passed, 1 warning;
  - card quality/source sync/action-center contract: 50 passed, 1 warning;
  - Data Fix/product-loop/admin UI/checker static: 13 passed.
- Backend full pytest after adding `backend/pytest.ini`: 1114 passed,
  4 expected xfailed, 1 warning.

One false failure occurred when two Playwright suites were run concurrently and
competed for the dev server. Re-running Action Center e2e by itself passed.

## Residual Notes

- This is a local automated and static audit. Live marketplace/WB data flows were
  not exercised.
- Existing Python warning remains from `passlib` importing deprecated `crypt`
  under Python 3.12; it does not fail tests.
- Repo-wide `npm run lint` is not yet a green gate. It reports a large
  pre-existing frontend formatting/type backlog across many files, mostly
  Prettier and `no-explicit-any` issues. This audit did not apply a whole-repo
  formatting rewrite because that would create broad unrelated churn; the
  Action Center container touched in this pass was cleaned to 0 lint errors.
