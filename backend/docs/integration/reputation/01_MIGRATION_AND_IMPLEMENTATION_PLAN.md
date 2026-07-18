# Reputation Migration And Implementation Plan

Date: 2026-06-21

## Implemented In This Step

1. Add local `reputation_items` and `reputation_settings` tables.
2. Reuse `operator_drafts` for reply drafts.
3. Reuse `result_events` for manual no-reply and publish outcomes.
4. Reuse `portal_module_sync_runs` and `portal_integrations` for sync/health state.
5. Keep `/portal/reputation/*` response schemas stable.
6. Wire Product 360, Action Center, and legacy profit diagnostics to local reputation data.
7. Keep automation, chat auto-reply, and auto-publish forced off by default.

## Follow-Up

- Add WB chat support only after Finance has an explicit token/API boundary for it.
- Add richer AI draft generation once PII minimization and provider audit hooks are wired.
- Add idempotency-key enforcement for publish before enabling `ENABLE_REPUTATION_PUBLISH` in any environment.
- Run a real account sync for `account_id=1` where a WB content token is configured.
