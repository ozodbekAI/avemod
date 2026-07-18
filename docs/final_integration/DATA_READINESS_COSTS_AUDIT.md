# Data Readiness And Costs Audit

Generated from Section 04 static audit on 2026-06-25.

## Scope

This pass covered:

- DQ blocker grouping and seller-facing Data Fix page;
- missing costs;
- template download;
- upload / preview / confirm;
- manual edit and supplier confirmation;
- DQ refresh and cache invalidation after cost changes;
- frontend wizard/runtime flow surfaces.

Real-data proof still requires a configured PostgreSQL database and an active account.

## Backend Surfaces

Data readiness:

- `GET /dq/issues`
- `GET /dq/issues/summary`
- `GET /dq/issues/investigator`
- `POST /dq/run`
- DQ service: `backend/app/services/data_quality.py`
- Data Fix source: `GET /money/data-blockers`

Costs:

- `GET /costs/template`
- `GET /costs/missing`
- `POST /costs/upload`
- `GET /costs/uploads/{upload_id}/preview`
- `POST /costs/uploads/{upload_id}/confirm`
- `GET /costs/unresolved`
- `PATCH /costs/{cost_id}`
- `POST /costs/{cost_id}/mark-supplier-confirmed`
- `POST /costs/relink`

Frontend:

- `frontend/src/routes/_authenticated/data-fix.tsx`
- `frontend/src/routes/_authenticated/costs.tsx`
- `frontend/src/components/settings/DataSyncSection.tsx`

## Fixed In This Pass

### Cost mutations now refresh DQ automatically

Before this pass, cost mutations invalidated money/operator snapshots but did not automatically run DQ checks. The prompt-required flow is:

```text
download -> fill -> upload -> preview -> confirm -> DB transaction -> DQ refresh -> Doctor/Actions/Product 360 refresh
```

Updated cost mutation endpoints now call `DataQualityService.run_checks(account_id=...)` before snapshot invalidation:

- `POST /costs/upload` when `commit_rows=true`;
- `POST /costs/uploads/{upload_id}/confirm`;
- `PATCH /costs/{cost_id}`;
- `POST /costs/{cost_id}/mark-supplier-confirmed`;
- `POST /costs/relink`.

### Seller UI no longer shows raw blocker code in card header

The Data Fix card header now shows a friendly ordinal label instead of the raw blocker code. Internal deep-linking by `code` is preserved.

## Blocker Group Requirements

Prompt-required groups:

- missing cost;
- finance mismatch;
- unmatched SKU;
- order lifecycle incomplete;
- stock without sales;
- sales without fresh stock.

Each blocker must expose seller-facing:

- title;
- business explanation;
- how to fix;
- severity;
- count;
- products affected;
- money affected;
- deep link.

Static frontend evidence:

- `data-fix.tsx` renders title, business impact, first action, step-by-step fix, success check, severity/priority, affected SKU/revenue, current/required values, and next-screen links.
- Existing copy covers missing manual cost, ambiguous manual cost, unresolved SKU, sale without finance, finance mismatch, finance without sale, unmatched SKU, expense unclassified, stock task failed, and photo/card issues.

Runtime proof needed:

- `GET /money/data-blockers` returns grouped blockers with no raw issue IDs in seller main copy;
- `GET /dq/issues/summary` group counts match open DQ rows;
- all blockers deep-link to working pages.

## Costs Flow Requirements

| Step | Static Status | Runtime Proof Needed |
| --- | --- | --- |
| Download CSV/XLSX template | implemented | Download both formats for active account |
| Missing costs | implemented | Verify row count, affected revenue, date-window behavior |
| Upload | implemented | Upload safe fixture with invalid/valid rows |
| Preview | implemented | Confirm preview shows valid/invalid reasons without committing |
| Confirm | fixed with DQ refresh | Confirm fixture and verify DB rows, DQ refresh, cache invalidation |
| Manual edit | fixed with DQ refresh | Patch a safe row and verify health/data blockers refresh |
| Supplier confirmation | fixed with DQ refresh | Mark safe row supplier-confirmed and verify finality changes |
| Relink | fixed with DQ refresh | Run relink and verify unresolved count changes |
| Doctor/Actions/Product 360 refresh | snapshot invalidation exists | Browser/API smoke after mutation |

## Validation Checks

Cost upload/import must reject or flag:

- duplicate rows;
- negative cost;
- zero cost where invalid;
- invalid currency;
- invalid or missing `valid_from`;
- missing required product/SKU identifiers;
- ambiguous SKU match;
- unresolved SKU;
- seller other expense missing when policy requires it;
- old legacy fields usage.

Existing tests cover several of these areas in:

- `backend/tests/unit/test_manual_costs_service.py`
- `backend/tests/api/test_manual_costs_routes.py`
- `backend/tests/unit/test_marts_and_quality.py`

## Runtime Acceptance Checklist

For a real account:

1. Open `/data-fix` and confirm blockers are grouped and seller-readable.
2. Open `/costs` and confirm missing/unresolved/import sections use backend data.
3. Download CSV and XLSX missing-cost templates.
4. Upload a safe fixture with at least one valid row and one invalid row using preview mode.
5. Confirm the upload.
6. Verify:
   - manual cost row exists;
   - DQ checks reran;
   - `/dashboard/data-health` changed where expected;
   - `/money/data-blockers` changed where expected;
   - `/portal/doctor`, `/portal/actions`, `/portal/products/{nm_id}` are refreshed by invalidation.
7. Run manual edit, supplier confirmation, and relink smoke checks.

## Remaining Runtime-Gated Items

- Real DB blocker grouping proof.
- Real missing-cost affected revenue proof.
- Real frontend wizard proof with screenshots/network logs.
- Full duplicate/negative/zero/currency/valid_from fixture matrix against the deployed DB.
