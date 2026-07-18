# Claims Factory Audit

Section 08 check, 2026-06-25.

## Covered Surface

- Detection types are local and account-scoped: `defect`, `supply_discrepancy`, `missing_goods`, `report_anomaly`, `compensation_underpayment`, `repeat_claim`, and `pretrial`.
- Detection scans persist `claim_detection_runs` and `claim_candidates`, with retry/detail/list endpoints under `/portal/claims/*`.
- Seller-facing case workflow supports case creation, case-from-signal, candidate-to-case, evidence, draft generation, proof-check, result events, and guarded manual submit under `/portal/cases/*`.
- External submit remains safe: `confirm=true` is required, `ENABLE_CLAIMS_SUBMIT=false` records a local manual submission without calling an external claims service, and manager/admin role is required for submit.
- Product 360, Action Center, legacy profit diagnostics, and Results have claims adapters/blocks that use Finance-owned local data where available.

## Section 08 Fixes In This Pass

- Synthetic/audit/test cases are hidden in `ClaimsFactoryService.list_cases()` and direct case detail reads now reject synthetic rows, so seller UI and Product 360 consume the same filtered service surface.
- The Claims frontend now uses real local candidate and scan endpoints instead of an empty placeholder tab.
- The Claims frontend can create a case from a candidate, generate a draft, run proof-check, and submit with the backend-required `confirm=true` payload.
- The submit success copy distinguishes local manual submission from external submission instead of implying WB was called.

## Local Health

Claims module health is local-first:

- `ModuleRegistryService` checks database-backed local claims health before external adapter configuration.
- Local health reports `mode=local`, Finance DB detection state, open candidates, latest successful run, and active/failed run state.
- External submit being disabled does not disable local Claims Factory; it only affects the guarded submit branch.

## Remaining Runtime Proof

Needs a configured runtime account/DB:

- Run `/portal/claims/scans` and verify each detector with real source rows.
- Create a candidate-derived case, attach evidence, generate draft, run proof-check, and record manual submission with `ENABLE_CLAIMS_SUBMIT=false`.
- Verify Product 360 claims block, Action Center claims actions, legacy profit diagnostics claims opportunities, and Results events against the same case.
- Confirm manager/operator RBAC around create/update/proof/submit in a live session.
