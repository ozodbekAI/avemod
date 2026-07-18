# Stock / TZ / Regional Supply Audit

Section 06 scope: Stock Control must be a local Finance module for return excess, ship from hand, store balance, regional supply import, hand stock template, warehouse-region mapping, run lifecycle, movements, export, Product 360, Actions, and Doctor. Legacy StockOps/TZostatka is a read-only compatibility reference only.

## Static Evidence

- Local backend routes live in `backend/app/modules/stock_control/router.py`.
- Local orchestration lives in `backend/app/services/stock_control/service.py`.
- Allocation formulas live in `backend/app/domain/stock_control/algorithms.py` and `allocation.py`.
- Durable rows live in `stock_control_runs`, `stock_control_region_rows`, `stock_control_movements`, `stock_control_imports`, `stock_control_hand_stock_drafts`, `warehouse_region_mappings`, and `stock_control_export_artifacts`.
- Frontend route is `/stock-control`, with tabs for overview, return excess, regional supply, store balance, history, and settings.
- Legacy adapter `backend/app/services/stockops_adapter.py` maps return_excess, ship_from_hand, and store_balance to safe read-only endpoints and keeps write status disabled.

## Flow Coverage

| Flow | Local Status | Evidence |
| --- | --- | --- |
| return_excess | Implemented | `compute_return_excess`, `StockControlRunCreate.run_type`, run output rows, movements, export |
| ship_from_hand | Implemented | hand-stock draft CRUD/template, size-safe matching, `compute_ship_from_hand`, unmatched rows |
| store_balance | Implemented in this pass as local non-mutating plan | `compute_store_balance`, `POST /portal/stock-control/preview`, `run_type=store_balance`, target-account access check |
| regional supply import | Implemented | `/imports/regional-supply/preview`, `/imports/regional-supply`, parser aliases, import rows |
| hand stock template | Implemented | `/templates/hand-stock`, CSV template, hand-stock draft CRUD |
| warehouse-region mapping | Implemented | `WarehouseRegionMapping`, mapping coverage in status, `unmapped_warehouses` warning |
| run lifecycle | Implemented | queued/running/completed/partial/failed/cancelled, retry, cancel, heartbeat |
| movements | Implemented | `/runs/{run_id}/movements`, movement rows, Action Center candidates |
| export | Implemented | `/runs/{run_id}/export`, xlsx summary/region_rows/movements/unmatched sheets |
| Product 360 | Implemented | `PortalService.product_360` includes local stock insights |
| Actions | Implemented | `StockControlService.action_candidates` emits read-only stockops actions |
| Legacy profit diagnostics | Implemented | Legacy profit diagnostics consume stock control / stockops signals through local services |

## Formula / Safety Checks

- Size safety: `ship_from_hand` rejects ambiguous article-only hand stock when multiple sizes exist and reports `size_mismatch` or `article_size_ambiguous`.
- size safety is also applied to `store_balance` by default through barcode/chrt/size-aware keys.
- Store balance uses size-aware keys by default and can fall back to product-level keys when `size_aware=false`.
- Excluded regions are normalized through `normalize_excluded_regions` and omitted from return/ship allocation.
- excluded regions are stored in Stock Control settings and copied into each run snapshot.
- Default IL is used for ship-from-hand when history is below `minimum_history_orders`.
- default IL is configured in settings as `default_il_profile_json`.
- Largest remainder allocation preserves total quantity exactly.
- largest remainder is the only supported extra allocation method in the local settings contract.
- Return excess uses regional demand weights, with equal distribution only when demand is zero.
- Store balance preserves planned movement quantity and creates donor-to-recipient movements only; it does not mutate WB.
- total quantity preservation is asserted in unit tests for largest remainder and store-balance planned units.
- No automatic WB operation: all local runs and exports set `marketplace_change=false` and `can_execute=false`.

## Runtime Proof Still Needed

Runtime verification requires real source rows for stock snapshots, orders or regional demand, and at least two accessible accounts for store balance.

Run:

```bash
cd backend
python -m compileall -q app tests scripts alembic
pytest -q tests/unit/test_stock_control_domain.py tests/unit/test_stockops_adapter.py tests/unit/test_stock_tz_section06_static.py
```

Then with a real account:

1. Call `GET /api/v1/portal/stock-control/status` and record latest stock snapshot, regional demand date, mapping coverage, and unmapped warehouses.
2. Preview and import a regional supply file through `/imports/regional-supply/preview` and `/imports/regional-supply`.
3. Download `/templates/hand-stock`, create a hand-stock draft, and run `ship_from_hand`.
4. Run `return_excess` and verify region rows, movements, and export.
5. With two accessible accounts, call `POST /portal/stock-control/preview` for `store_balance`, then queue `run_type=store_balance`.
6. Verify `/runs/{run_id}`, `/overview`, `/region-rows`, `/movements`, `/unmatched`, and `/export`.
7. Open `/stock-control`, Product 360, Action Center, and Doctor in the frontend and confirm the same stock signals appear as local read-only recommendations.

## Legacy Parity Notes

Legacy StockOps/TZostatka parity is covered at the flow level: return excess, ship from hand, store balance, safe run reads, overview, sheets, and export are mapped in `StockOpsAdapter.FLOW_MATRIX`. Exact numeric parity against `old all.zip` still needs a sanitized fixture pair or runtime legacy output export; no legacy write/apply behavior should be copied into Finance.
