# Legacy To Local Map

Generated from ZIP inventory on 2026-06-25. Archives were inspected with `unzip -l`; no wholesale extraction or copy was performed.

## Integration Rule

Per `backend/AGENTS.md`, legacy archives under `_incoming_projects/` are reference/source material only.

Allowed:

- inspect contracts, formulas, fixtures, algorithms, and UX behavior;
- extract a small focused file temporarily outside deploy context when needed;
- port only the needed logic into Finance-owned models/services/schemas/tests.

Not allowed:

- copy entire legacy projects into Finance;
- replace Finance auth/account/token/database boundaries;
- expose legacy service endpoints directly to the frontend;
- enable WB write/apply actions by default.

## Archive Inventory

| Archive | Apparent Domain | Useful Reference Areas | Local Finance Target |
| --- | --- | --- | --- |
| `backend/_incoming_projects/backendfinance.zip` | Earlier finance backend | Alembic chain, finance models/routes/services, response snapshots | Already largely represented in current `backend/app/modules/finance`, `money_management`, `marts`, migrations through API response snapshots |
| `backend/_incoming_projects/backenddefect.zip` | Defect claims/support cases | case lifecycle, evidence snapshots, support routes, templates, WB audit hardening | `app/services/claims_adapter.py`, `app/services/claims_factory.py`, `app/models/claims.py`, `/portal/cases/*`, `/portal/claims/*` |
| `backend/_incoming_projects/checker.zip` | Card checker/product quality/photo/promotion | issue explainability, product DNA, WB apply jobs, economics cache, photo chat/generator models | `app/services/checker_adapter.py`, `app/services/card_quality.py`, `app/models/card_quality.py`, `/portal/card-quality/*`, photo studio where appropriate |
| `backend/_incoming_projects/groupingbackend.zip` | Grouping/recommendation beta | product/group/recommendation/scenario/pipeline models and schemas | `app/services/grouping_adapter.py`, `app/services/grouping.py`, `app/models/grouping.py`, `/portal/grouping/*` |
| `backend/_incoming_projects/all.zip` | StockOps/regional supply/calculation utilities | `ship_distribution`, `ship_demand`, `dispatch_from_hand`, `store_balance`, `calculator`, `wb_api`, exporter/reference data | `app/domain/stock_control/*`, `app/services/stockops_adapter.py`, `/portal/stock-control/*`, `/portal/stockops/*` |
| `backend/_incoming_projects/audit-bundle.zip` | Prior backend endpoint audit snapshots | endpoint JSON payloads for accounts/actions/ads/analytics/catalog/costs/dashboard/dq/finance | Contract fixture comparison and acceptance matrix inputs |
| `backend/_incoming_projects/backend (7) .zip` | Larger legacy portal/backend | migrations for reviews/news/RBAC/shops/payments/GPT usage and API surface | Reference only; extract focused review/reputation/RBAC ideas if current modules lack a needed behavior |
| `frontend/audit_bundle/LOVABLE_FINAL_ACCEPTANCE_AUDIT_2026-06-16.zip` | Frontend acceptance evidence | screenshots and network summaries | UI regression reference |
| `frontend/audit_bundle/LOVABLE_FINAL_ACCEPTANCE_AUDIT_2026-06-17.zip` | Frontend acceptance evidence | screenshots, network summaries, run script | UI/browser smoke reference |

## Already Localized Capabilities

The current Finance backend already contains local modules corresponding to several legacy domains:

- Claims: `claims.py` model/schema/service/adapter and portal case/claim routes.
- Reputation: `reputation.py` model/schema/service/adapter and portal reputation routes.
- Grouping beta: `grouping.py` model/schema/service/adapter and portal grouping routes.
- Photo studio: `photo_studio.py` model/schema/service and portal photo routes.
- Card quality/checker: `card_quality.py` model/schema/service plus checker adapter.
- Stock control/StockOps: stock control domain, model/schema/service, stockops adapter.

This suggests the next integration pass should be gap-focused, not archive-focused.

## Focused Extraction Candidates

Only extract these if a concrete failing acceptance item points to them:

- From `all.zip`: stock allocation formulas and Excel import/export edge cases.
- From `checker.zip`: explainability fields, product DNA score details, safe WB access ping logic.
- From `backenddefect.zip`: evidence snapshot rules, support ticket lifecycle controls, proof checklist wording.
- From `groupingbackend.zip`: recommendation scoring/scenario formulas.
- From `audit-bundle.zip`: expected endpoint payload examples for contract diffing.
- From frontend audit bundles: screenshot/network baselines for Playwright or manual regression.

## Unsafe Or Non-MVP Legacy Areas

Treat these as blocked unless feature flags, preview, confirm, permissions, idempotency, and audit are implemented:

- WB card apply jobs from checker.
- Review/reply publishing.
- Defect claim submission.
- Grouping merge/apply.
- Stock mutation or shipment/return write operations.
- Price or ads changes.
- Raw token or credential logging/debug routes.

## Next Legacy Audit Steps

1. Build a targeted manifest for each ZIP with models, routes, services, formulas, tests, unsafe write paths.
2. Compare current local services against those manifests.
3. Create one small task per verified gap.
4. Add/adjust Finance-owned tests before or with each port.
5. Delete any temporary extraction directory after inspection, or keep it under an ignored non-deploy audit path with no secrets.
