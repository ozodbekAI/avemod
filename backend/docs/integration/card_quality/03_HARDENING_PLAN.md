# Card Quality Hardening Plan

Date: 2026-06-19

## Implemented In This Pass

- Make account-level analysis enqueue a `queued` run and return HTTP 202 without processing catalog rows in the request path.
- Add run progress fields for eligible total, processed, skipped unchanged, failed, cursor, heartbeat, and attempt.
- Add `GET /portal/card-quality/runs/{run_id}` and `POST /portal/card-quality/runs/{run_id}/retry`.
- Add bounded keyset worker processing through `CardQualityAnalysisService.process_run_batch`.
- Keep product quality GET read-only; unanalyzed local cards return `not_analyzed` with an explicit analyze endpoint.
- Store logical photo objects with `canonical_url` and `variants`, and count one marketplace photo object as one logical photo.
- Default `GET /portal/card-quality/issues` to actionable issues only; include informational observations only with `include_info=true`.
- Validate manual issue status transitions and return a conflict at the route layer for illegal transitions.
- Write status history for auto-resolve and auto-reopen.
- Add snapshot uniqueness for `(account_id, nm_id, source_revision)` and current lookup index.
- Clear registry error fields on success and store local metrics separately.
- Add explicit `rows_processed` and `rows_skipped` sync-run counters.
- Preserve real card-quality issue severity in Action Center actions.

## Still Required Before Phase 1 Completion

- Run the worker against account 1 until `unique_products_analyzed == eligible_products`.
- Capture Product 360 and quality endpoint latency evidence.
- Add Product list aggregate fields and filters.
- Add Data Fix Card Quality source/filter endpoint or tab contract.
- Complete Doctor consistency tests against the real local DB path.
- Build and document rule parity benchmark against legacy Checker.
- Produce the final sanitized audit bundle with runtime responses, timings, parity metrics, and SHA256.
