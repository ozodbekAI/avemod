# Claims Factory Reality Audit

Date: 2026-06-22

## Current State

- Finance is the source of truth for accounts, auth, tokens, money data, operator cases, drafts, evidence, and result events.
- Claims Factory is implemented as finance-owned local capability. It does not require a separate claims backend for the MVP.
- Existing `/portal/cases/*` endpoints remain the lifecycle API for cases, evidence, drafts, proof checks, manual submit recording, and result history.
- Existing `/portal/cases/detect/*` endpoints remain read-only detection previews.
- New `/portal/claims/scans` and `/portal/claims/candidates` endpoints persist detector runs and deduplicated candidates.
- Marketplace/external submit remains disabled by default. `ENABLE_CLAIMS_SUBMIT=false` records local manual confirmation only and does not call Wildberries or an external claims service.

## Reference Material

`_incoming_projects/backenddefect.zip` and downloaded local integration notes are reference material only. They informed detector naming, lifecycle concepts, compensation matching, finance traces, proof requirements, and UX states. They were not copied wholesale into Finance.

## Safety Boundaries

- No WB write, submit, appeal, or external publish action is enabled by these changes.
- Candidate scan uses finance-owned account checks and persisted local tables.
- Candidate payloads and responses pass through recursive secret-field scrubbing.
- Case creation from a candidate creates a local `OperatorCase` only.
- External ticket tracking is still gated by `ENABLE_CLAIMS_SUBMIT` and manual confirmation.

## Local Persistence

The local claims discovery layer uses:

- `claim_detection_runs`: one row per detector run, with status, counters, requested user, period, and sanitized source snapshot.
- `claim_candidates`: deduplicated claim opportunities keyed by `(account_id, fingerprint)`, with source references, severity/confidence, amount/quantity impact, evidence summary, and optional linked case.

## Degraded States

Optional detectors can return `empty`, `not_configured`, `not_enough_data`, or `unavailable` without breaking money, actions, product, case, or reputation pages.
