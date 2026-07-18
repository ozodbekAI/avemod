# Card Quality Hardening Baseline

Date: 2026-06-19

This baseline captures the code state before the hardening patch in this workspace. Live account metrics were not available from a running database during implementation, so runtime values must be captured from staging before declaring Phase 1 complete.

## Code Baseline

- `POST /api/v1/portal/card-quality/analyze` processed the selected catalog synchronously inside the HTTP request.
- `GET /api/v1/portal/products/{nm_id}/quality` could create snapshots and issues when a local product card existed without a snapshot.
- Account analysis selected latest rows with a limit instead of tracking full catalog progress.
- Snapshot health counted snapshot rows rather than distinct analyzed products.
- Marketplace photo variants were flattened into URLs, which could overcount one logical photo with multiple resolutions.
- Informational `media_no_video_info` issues were stored as issues and could be included in default issue lists.
- Manual issue status changes had history, but automatic resolve/reopen did not consistently write status history.
- Local checker registry success state used `last_error_message` for metrics.
- `PortalModuleSyncRun` did not expose `rows_processed` or `rows_skipped`.
- Local Action Center card-quality actions hardcoded severity to `high`.

## Runtime Metrics To Capture

Capture these from staging before final acceptance:

- eligible product count;
- unique analyzed product count;
- snapshot rows;
- actionable issue count;
- informational observation count;
- Product 360 latency;
- batch duration;
- Doctor unavailable sources;
- Products quality coverage;
- Data Fix quality coverage.
