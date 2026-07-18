# Local Stock Control Formula Catalog

Date: 2026-06-19

## Scope

Phase 1 is Finance-owned and local-only:

- `return_excess`
- `ship_from_hand`

`store_balance` is documented as planned phase 2 and is rejected by `/api/v1/portal/stock-control/runs`.

No WB write, auto shipment, auto return, auto submit, or external mutation is performed by this module.

## Region Normalization

Russian federal district aliases are normalized to stable region keys before allocation. Examples:

- `Центральный федеральный округ` -> `Центральный`
- `Северо западный федеральный округ` -> `Северо-Западный`
- `Южный федеральный округ` -> `Южный`

Excluded regions are normalized through the same function before filtering demand and stock rows.

## Integer Allocation

All regional integer splits use largest remainder allocation:

1. Compute each raw regional share from `total_qty * weight / weight_sum`.
2. Floor every raw value.
3. Distribute the remaining units to the highest fractional remainders.
4. Preserve exact `sum(allocated_qty) == total_qty`.

When all weights are zero, the first stable key receives the full quantity. Action/movement rows with `quantity <= 0` are not created.

## `return_excess`

Inputs:

- regional demand rows from Finance orders, regional sales fallback, regional supply import fallback, or default IL profile fallback;
- latest stock snapshot rows mapped through `warehouse_region_mappings`;
- optional excluded regions and minimum keep per size settings.

For each product/size key:

1. Aggregate demand by normalized region.
2. Aggregate stock by normalized warehouse region.
3. Allocate total stock to regions by demand share.
4. If total demand is zero, use equal regional weights for visible stock regions.
5. Calculate `delta_qty = target_stock_qty - current_stock_qty`.
6. Mark rows as `shortage`, `excess`, or `balanced`.
7. Pair donor excess rows to recipient shortage rows, creating local-only movement recommendations.

The output is persisted as `stock_control_region_rows`, `stock_control_movements`, run summary, provenance, and an Excel export artifact.

## `ship_from_hand`

Inputs:

- same regional demand/stock basis as `return_excess`;
- a local hand-stock draft uploaded/created in Finance;
- allocation mode: `redistribute` or `balance`;
- optional `ship_all_available`.

Matching order:

1. Exact size-safe match by product plus reliable barcode/size identity.
2. Article+size fallback only when the size is unambiguous.
3. Default IL profile fallback when no demand history exists.
4. Unsafe size mismatch and ambiguous article-only rows become `unmatched`.

`redistribute` allocates by uncovered demand. `balance` allocates by target-minus-current regional need. `ship_all_available=true` ships the full hand-stock quantity across available weights; otherwise leftover quantity beyond measured need becomes unmatched.

## Public Safety Flags

All generated actions and movement candidates are read-only:

- `marketplace_change=false`
- `can_execute=false`
- `can_update=true`
- `source_module="stockops"` or `source_module="stock_control"`

The UI must treat them as operator recommendations, not as WB mutations.
