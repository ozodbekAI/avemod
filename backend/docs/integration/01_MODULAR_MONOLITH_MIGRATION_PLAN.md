# Modular Monolith Migration Plan

This plan converts the current Finance Portal facade into a finance-owned modular monolith without a big-bang rewrite.

## Phase 0: Baseline And Registry

Status: started.

1. Keep Finance as the only public backend and account/auth boundary.
2. Extract legacy archives only into temporary analysis folders outside deploy context.
3. Document legacy models, routes, services, jobs, auth, data ownership, and reusable algorithms.
4. Add DB-backed module registry:
   - `portal_integrations`
   - `portal_module_sync_runs`
5. Keep env configuration as global fallback while DB rows become account-level source of truth.
6. Never expose `configuration_encrypted_json` or other secret values in API payloads.

Acceptance:

- `/portal/modules/health` can reflect account-level DB state.
- Existing env-only behavior still works when there is no DB row.
- Tenant isolation tests prove one account's integration state does not affect another.

## Phase 1: Card Quality Local Module

Goal: replace Checker URL dependency with Finance-owned card quality persistence.

Tables:

- `card_quality_analysis_runs`
- `card_quality_snapshots`
- `card_quality_issues`
- `card_quality_issue_status_history`

Implementation steps:

1. Build `app/services/card_quality.py` using Finance `wb_product_cards`, characteristics, sizes, and media fields.
2. Port only deterministic rule/score helpers from Checker.
3. Add run states: `queued`, `running`, `completed`, `partial`, `failed`.
4. Keep `/portal/products/{nm_id}/quality` response shape stable.
5. Add internal/account-scoped routes for sync/analyze/runs.
6. Emit unified actions for unresolved real issues.
7. Update Product 360 and Doctor to use local quality block.

Safety:

- No checker auth/users/stores.
- No WB apply job.
- No card auto-apply.

## Phase 2: Reputation Reviews Lite

Goal: local Reviews/Questions/Chats with draft workflow.

Tables:

- `reputation_items`
- `reputation_sync_runs`
- `reputation_drafts`
- `reputation_settings`
- `reputation_action_history`

Implementation steps:

1. Adapt WB sync clients into Finance account token boundary.
2. Normalize `review`, `question`, and `chat` items by `account_id`, `nm_id`, `external_item_id`.
3. Implement classify -> action -> draft -> approve/reject/regenerate.
4. Keep publish disabled by default and confirm/audit-gated.
5. Create Action Center tasks for negative unanswered items.
6. Surface product-specific reputation blocks in Product 360 and Doctor.

## Phase 3: Grouping Beta Local Engine

Goal: local recommendation runs fed by Finance product snapshots.

Tables:

- `grouping_runs`
- `grouping_candidates`
- `grouping_recommendations`
- `grouping_review_history`

Implementation steps:

1. Port article normalization, constraints, scoring, and scenario preview helpers.
2. Use `wb_product_cards`, characteristics, sizes, brand, subject, color, vendor code, and `imt_id`.
3. Add run/recommendation APIs while preserving `/portal/products/{nm_id}/grouping` and `/portal/grouping/preview`.
4. Return `beta` or `empty` with `run_id`, `analyzed_product_count`, and `analyzed_at` even with no recommendations.
5. Keep `merge-wb` impossible from Finance Portal.

## Phase 4: Claims Real Data Hardening

Goal: claims/cases come from real finance and supply signals, not seller-visible synthetic audit data.

Implementation steps:

1. Hide or exclude `payload.audit=true` cases from seller views.
2. Connect real defect/return data and supply discrepancy detectors.
3. Implement local compensation matching.
4. Generate case/evidence/draft/proof-check records.
5. Keep external submit disabled until confirm/permission/audit is complete.

## Phase 5: Stock Control Local Signals

Goal: finance stock is source of truth for stock control signals.

Implementation steps:

1. Port calculators for frozen stock, deficit, overstock, region imbalance, return excess, ship from hand, and store balance.
2. Persist local runs and action candidates.
3. Surface Product 360 stock signal and Action Center stock actions.
4. No WB-modifying operations from portal.

## Phase 6: Unified Portal Read Model

Update:

- `/portal/modules/health`
- `/portal/doctor`
- `/portal/actions`
- `/portal/products`
- `/portal/products/{nm_id}`
- `/portal/results`

Rules:

- `disabled` means intentionally off.
- `not_configured` means missing required setup.
- `empty` means module works but no data/issues.
- `ok` means module works and data exists.
- `unavailable` means runtime error.
- `beta` means enabled beta surface.

## Verification Per Phase

Run after each implementation step:

```bash
.venv/bin/python -m compileall -f -q app tests alembic scripts
.venv/bin/python -m alembic upgrade head
.venv/bin/python -m pytest -q
```

Also run live contract audits before deploying public portal changes.

## Final Audit Bundle

The final integration audit must include:

- before/after module statuses;
- real row counts per module;
- sanitized Card Quality issue sample;
- sanitized Reputation item/draft sample;
- Grouping run evidence;
- Claims case evidence;
- Action Center source distribution;
- Product 360 response for `nm_id=245405620`;
- remaining P0/P1/P2 risks.
