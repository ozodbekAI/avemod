# Claims Factory Implementation Plan

Date: 2026-06-22

## Completed Baseline

- Added local `claim_detection_runs` and `claim_candidates` persistence.
- Added scan/candidate schemas with stable degraded-state fields.
- Added local scan orchestration over existing detector adapter methods.
- Added candidate deduplication by account-scoped fingerprint.
- Added candidate triage and candidate-to-case linking.
- Kept all external submit behavior disabled by default.

## Near-Term Next Steps

- Add richer detector fixtures for compensation underpayment and report anomaly parity.
- Add UI integration against `/portal/claims/scans` and `/portal/claims/candidates`.
- Add async/background execution if detector runtime grows beyond bounded local scans.
- Add stricter status transition policy if candidate workflow becomes multi-operator.

## Future External Submit Requirements

External marketplace-changing operations must remain disabled until all of these are implemented:

- manual preview;
- explicit confirmation;
- manager/admin account role check;
- proof check with required evidence;
- approved draft;
- idempotency key;
- audit/result event before any external call;
- adapter-level secret scrubbing and no raw credential logging.
