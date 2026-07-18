# Full TZ Code Audit - Finance / Seller Portal AI Operator

Date: 2026-06-19
Workspace: `/home/ozodbek/AVEMOD_PROJECTS/Finance`
TZ source: `/home/ozodbek/Downloads/Telegram Desktop/Control_Tower_Product_Vision_MVP_and_Roadmap.docx`
Post-fix status: backend critical audit fixes applied, re-audited, and verified.

## Verdict

The Finance backend is now in a much stronger MVP acceptance state. The critical backend issues found during the full audit were fixed: the full test suite is green, portal contract fixture drift is fixed, sync and module-health responses scrub secret-like data, queued Checker account-batch processing is registered in the scheduler, duplicate card snapshot handling uses a transaction savepoint, `UnifiedAction` has basic task-center fields, claims detectors no longer return fake `not_implemented` stubs for missing goods/repeat/pretrial flows, and reputation reply drafts can be persisted locally through Finance.

This still does not make the repository a complete end-to-end TZ product by itself. The frontend repository is not present here, so portal-only frontend call-site compliance and MVP navigation cannot be proven from this workspace. Grouping remains safe beta/recommendation-only without finance-owned run/candidate persistence. StockOps remains optional/read-only for marketplace-changing operations. Reputation now has local draft persistence, but not a full finance-owned inbox sync store. Claims detection is improved, but some advanced anomaly sources still need stronger finance-owned data.

## Audit Scope

- Source/test/doc/script files checked: 377 files.
- Approximate source/test/doc/script LOC checked: 111,748 lines.
- API route decorators scanned in the original audit: 158 route definitions.
- Frontend code: not present in this repository (`package.json`, `tsx/jsx`, Vite/Next files not found), so UI/navigation/call-site audit remains out of scope for this workspace.
- External projects under `_incoming_projects/` and generated audit artifacts remain reference/evidence only, not product source.

## Verification Run

- PASS: `.venv/bin/python -m compileall -f -q app tests alembic scripts`
- PASS: `.venv/bin/python scripts/scan_secret_leaks.py`
- PASS: targeted portal/module regression suite:
  - `.venv/bin/python -m pytest -q tests/unit/test_card_quality_service.py tests/unit/test_grouping_adapter.py tests/unit/test_reputation_adapter.py tests/unit/test_claims_adapter.py tests/unit/test_stockops_adapter.py tests/unit/test_module_registry.py tests/unit/test_portal_service.py tests/api/test_portal_routes.py tests/unit/test_sync_schemas.py tests/unit/test_portal_contract_fixtures.py tests/unit/test_runtime_correctness.py::test_register_jobs_does_not_raise_and_registers_jobs`
  - Result: 208 passed, 1 warning.
- PASS: full test suite:
  - `.venv/bin/python -m pytest -q`
  - Result: 638 passed, 1 warning.

## Second Review Pass

The second full pass rechecked route/account scoping, dangerous marketplace-write gates, remaining `not_implemented` references, schema contract guards, migration chain, sync redaction, module-health redaction, and token surfaces.

One additional leak path was found and fixed: `PortalIntegration.last_error_message` could be shown in module health after only replacing known env var names. `ModuleRegistryService._safe_message` now also uses the shared `redact_sensitive_text` helper, so bearer/password/token-like values in DB-backed integration errors are redacted before frontend responses.

Covered by: `tests/unit/test_module_registry.py::test_module_registry_db_error_message_redacts_secret_like_values`.

## Fixed High-Priority Findings

### Fixed - Portal contract drift

`PortalActionRead` and the Lovable/frontend contract fixture are synchronized again. `tests/fixtures/portal/action_update_ok.json` now includes `can_execute` and the new task-center fields. The contract guard test passes.

### Fixed - Sync response secret scrub risk

A shared redaction helper was added at `app/core/redaction.py`. `SyncRunRead`, `SyncCursorRead`, and portal data sync domain status now scrub secret-like payload keys and redact token/password/bearer-like text before responses leave Finance.

Covered by: `tests/unit/test_sync_schemas.py`.

### Fixed - Module health integration error secret scrub risk

DB-backed portal integration health messages now pass through the same redaction helper. This prevents `PortalIntegration.last_error_message` from leaking bearer/password/token-like values in `/portal/modules/health` or overview module-health blocks.

Covered by: `tests/unit/test_module_registry.py::test_module_registry_db_error_message_redacts_secret_like_values`.

### Fixed - Checker queued account batch not scheduled

Queued account-wide card-quality analysis is now processed by a registered scheduler job:

- Processor: `app/jobs/sync_jobs.py`
- Scheduler registration: `app/jobs/registry.py`
- Job id: `process-card-quality-runs`

Duplicate card snapshot insert handling now uses `session.begin_nested()` in `app/services/card_quality.py`, so duplicate recovery does not roll back the outer batch transaction.

Covered by: `tests/unit/test_card_quality_service.py` and `tests/unit/test_runtime_correctness.py::test_register_jobs_does_not_raise_and_registers_jobs`.

### Fixed - Minimal unified Task Center fields

`UnifiedAction` now has finance-owned task fields:

- `assigned_to_user_id`
- `deadline_at`
- `review_status`
- `last_comment`
- `closed_at`
- `dismissed_at`

Migration added: `alembic/versions/20260619_000036_unified_action_task_fields.py`.

Portal action update flows now map action status into review lifecycle states:

- `new`
- `in_progress`
- `review`
- `closed`
- `dismissed`

Covered by: `tests/unit/test_portal_service.py`, `tests/unit/test_operator_models.py`, and contract fixture tests.

### Fixed - Claims detectors for missing goods, repeat claims, and pretrial

Claims detection no longer relies on `not_implemented` stubs for the audited endpoints:

- Missing goods detection reads finance-owned `WBSupply` / `WBSupplyGood` acceptance data when a DB session is available.
- Repeat-claim detection derives candidates from defect signals.
- Pretrial detection derives candidates from defect/legal escalation signals.
- Portal routes call these adapter detectors directly and still return degraded states such as `not_configured`, `not_enough_data`, or `empty` instead of fake cases.

Covered by: `tests/unit/test_claims_adapter.py` and `tests/api/test_portal_routes.py::test_portal_future_claim_detections_are_transparent_and_do_not_create_fake_claims`.

### Fixed - Reputation manual draft persistence

`PortalService.reputation_generate_draft` can now persist manual reply draft text locally as an `OperatorDraft` without calling the external reputation adapter. External generated draft text is also persisted locally when available. Marketplace publish remains gated and disabled by default.

Covered by: `tests/unit/test_portal_service.py::test_reputation_generate_draft_persists_manual_text_locally`.

## TZ Compliance Matrix After Fixes

| TZ / AGENTS requirement | Status | Current evidence |
| --- | --- | --- |
| Finance is core auth/account/token/money boundary | OK | Existing auth/account/token services remain authoritative; no rewrite or bypass was introduced. |
| Frontend must call finance/portal endpoints only | Cannot verify here | Frontend code is not in this repository. |
| Portal aggregation layer, not rewrite | OK | Fixes were added inside finance-owned services/adapters/routes, not by importing whole external projects. |
| Optional modules degrade safely | OK | Responses use explicit states such as `ok`, `empty`, `not_configured`, `unavailable`, `disabled`, and `not_enough_data`. |
| No marketplace write/apply by default | OK | Checker apply, grouping merge, StockOps WB writes, reputation publish, and claims submit remain gated/disabled by default. |
| Unified Action Center | Improved / partial | Basic task ownership/deadline/review/close/dismiss fields are now present. Full comments/attachments/SLA/history remain future work. |
| Checker read-only MVP | OK | Scheduler processing is wired; no WB apply path was enabled. |
| Grouping beta recommendation only | OK for MVP, partial for full product | Dry-run/beta safety remains. Local grouping run/candidate/review persistence is still not implemented. |
| Reviews / reputation through Finance | Improved / partial | Local reply draft persistence exists. Full local inbox sync and reputation item tables are still pending. |
| Defect claims through Finance | Improved / partial | Case/draft/result flow exists; missing goods/repeat/pretrial detectors are implemented safely. Advanced report anomaly detection still needs stronger finance data. |
| StockOps optional/read-only | OK for safety, partial for full product | Read and degraded states remain safe; local stock planning/handoff records are still pending. |
| Secrets not exposed in responses | Improved / OK in tested paths | Sync schemas, portal sync status, and module-health DB error messages now redact secret-like values; secret scanner passes. |

## Remaining Product-Scope Risks

### Frontend audit still required

The backend cannot prove that the actual UI calls only Finance/Portal endpoints because no frontend code is present in this workspace. The real frontend repository must be audited for:

- no direct checker/grouping/StockOps/reputation/claims calls,
- MVP navigation shape,
- Product 360 and Action Center contract compatibility,
- no token/secret display or logging.

### Grouping is safe beta, not full finance-owned persistence

Grouping still satisfies the MVP safety rule because `merge-wb` and destructive endpoints remain blocked. It does not yet satisfy a full product expectation for local run history, candidate storage, recommendation review, and result events.

### Reputation is not yet a full local inbox

Manual/generated reply drafts can now be saved locally, but Finance still lacks a full local `reputation_items`/inbox sync table. Publish remains correctly gated and disabled by default.

### StockOps / Stock Control is now local phase 1

Finance now has a local, account-scoped `stock_control` phase-1 implementation for `return_excess` and `ship_from_hand`. Existing `/portal/stockops/*` compatibility routes point at the local service with `raw.mode="local"`, and Product 360 / Action Center can consume read-only movement recommendations. `store_balance` remains planned phase 2, and WB write/auto-return/auto-shipment behavior remains disabled.

### Task Center collaboration is still minimal

The universal task fields are now present, but comments, attachments, SLA rules, full history views, and every-module task normalization are not yet complete. Existing `ResultEvent` history helps, but it is not a complete collaboration subsystem.

### Claims advanced anomaly sources need more data

Missing goods, repeat claims, and pretrial detectors were implemented safely. Some advanced report anomaly cases remain degraded unless finance-owned source data exists.

## Acceptance State

Backend acceptance is now green for the audited critical fixes:

- full tests pass,
- compile passes,
- secret scan passes,
- Checker account batch processing is scheduled,
- local Stock Control queued-run processing is scheduled,
- sync response scrubbers are in place,
- minimal Task Center fields are added,
- key claims detectors are implemented,
- reputation draft persistence is finance-owned.

The remaining work is product expansion, not immediate backend breakage: frontend call-site audit, full Grouping persistence, full Reputation inbox sync, Stock Control phase-2 `store_balance`, richer legacy fixture replay, and richer task collaboration.
