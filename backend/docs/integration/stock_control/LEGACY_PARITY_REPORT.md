# Local Stock Control Legacy Parity Report

Date: 2026-06-19

## Source Material

Legacy/reference material was inspected from `_incoming_projects/all.zip`, including TZostatka-style `return_excess` / `ship_from_hand` artifacts and tests.

Per `AGENTS.md`, that project remains reference-only. No legacy auth, SQLite app structure, token handling, store model, or whole project tree was copied into Finance.

## Ported Behavior

Implemented in Finance-owned modules:

- region alias normalization and excluded-region filtering;
- largest remainder allocation with exact total preservation;
- no zero-quantity movement/action rows;
- `return_excess` donor-to-recipient movement planning;
- zero-demand handling without fake demand rows;
- `ship_from_hand` exact size-safe matching;
- article+size fallback only when unambiguous;
- unsafe size mismatch and ambiguous article-only rows routed to `unmatched`;
- `redistribute`, `balance`, and `ship_all_available` behavior;
- local Excel/CSV preview, import normalization, template, and XLSX export artifact generation;
- legacy `/portal/stockops/run` and `/portal/stockops/runs` compatibility in local mode.

## Finance-Specific Changes

The Finance implementation intentionally differs from legacy behavior in these areas:

- account access is enforced by Finance auth/RBAC helpers;
- all persisted rows are account-scoped;
- `store_balance` is rejected for phase 1 and documented as phase 2;
- recommendations are read-only and cannot call WB write APIs;
- frontend-facing payloads are recursively scrubbed for token-like fields;
- optional module failures do not break money, actions, Product 360, costs, settings, or data-fix pages;
- scheduler work is local: `process-queued-stock-control-runs` only processes queued Finance DB runs.

## Parity Tests Added

Covered by `tests/unit/test_stock_control_domain.py`:

- region normalization and warehouse/exclusion aliases;
- largest remainder sum preservation;
- excluded regions;
- zero demand donor behavior with minimum keep;
- size-aware allocation;
- unmatched size safety;
- article-only ambiguity;
- `redistribute`, `balance`, and `ship_all_available`.

Covered by portal/API tests:

- Stock Control endpoints are registered in OpenAPI;
- run creation returns local queued `202`;
- `store_balance` is rejected for phase 1;
- import preview can report invalid templates;
- compatibility `/portal/stockops/*` routes remain available in local mode;
- module registry exposes `stockops` with `mode="local"`;
- Product 360 and Action Center consume local stock signals without external writes.

## Remaining Parity Gaps

- Historical demand fallback to uploaded regional-supply rows is persisted, but full legacy fixture replay against every manual artifact is still a follow-up.
- Store-balance formulas are intentionally not ported in phase 1.
- Export formatting is Finance-native XLSX and may not match every legacy workbook style cell-for-cell.
