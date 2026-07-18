# Card Quality / Checker Audit

Section 05 scope: local Card Quality is primary; legacy Checker remains a read-only fallback. The audit covers analysis runs, coverage, snapshots, issues, status history, Products aggregate, Data Fix filters, Product 360, Action Center, and legacy profit diagnostics.

## Static Evidence

- Local analysis lives in `backend/app/services/card_quality.py`.
- Normalization reads Finance-owned WB product-card tables: title, description, brand, subject, vendor code, characteristics, photos, videos, sizes, source revision, and source updated time.
- Rule coverage includes title, description, characteristics, media, and identity. The engine returns score, status, category scores, severity counts, and issue payloads.
- Analysis writes durable `CardQualityAnalysisRun`, `CardQualitySnapshot`, `CardQualityIssue`, and `CardQualityIssueStatusHistory` rows.
- Batch account analysis is queued through `POST /portal/card-quality/analyze` with HTTP 202, then processed by card-quality jobs.
- Product analysis, run listing, run detail, retry, issue listing, and issue status updates are exposed in `backend/app/modules/portal/router.py`.
- `PortalService.product_quality()` prefers local card-quality snapshots and falls back to the legacy Checker adapter only when local quality is unavailable/not configured.
- Action Center consumes local high/critical quality issues through `quality_actions()`.
- Legacy profit diagnostics consume local card-quality signals through `ProfitDoctorService`.
- Product 360 renders card quality status, score, issue list, recommendations, photo count, analyzed time, and category scores.
- Products aggregate now exposes `card_quality_state`, `card_quality_score`, `card_quality_issue_count`, `card_quality_photo_count`, and `card_quality_analyzed_at`; the frontend can filter by quality status and sort by quality score.
- Data Fix now has non-technical fallback copy for local checker title, description, characteristics, and media issue codes.

## Required Metrics

| Metric | Source |
| --- | --- |
| Eligible count | `CardQualityAnalysisRun.eligible_total` |
| Unique analyzed | `CardQualityAnalysisRun.cards_analyzed` and distinct snapshot `nm_id` in runtime proof |
| Coverage | module health fields and runtime ratio of analyzed/eligible |
| Actionable issues | active non-info `CardQualityIssue` rows |
| Info observations | `CardQualityIssue.severity == "info"` |
| Score | `CardQualitySnapshot.score` / `PortalProductQualityRead.score` |
| Category scores | `CardQualitySnapshot.summary_json.category_scores` |
| Photo count | `CardQualitySnapshot.photos_count` |
| Analyzed at | `CardQualitySnapshot.analyzed_at` |

## Runtime Proof Still Needed

Runtime verification requires a configured PostgreSQL database with real `wb_product_cards` rows for an accessible account.

Run:

```bash
cd backend
python -m compileall -q app tests scripts alembic
pytest -q tests/unit/test_card_quality_service.py tests/unit/test_checker_adapter.py tests/unit/test_profit_doctor_service.py tests/unit/test_card_quality_section05_static.py
```

Then with a real account:

1. Call `POST /api/v1/portal/card-quality/analyze` and confirm HTTP 202 plus a queued run.
2. Process the queued run or wait for scheduler processing.
3. Call `GET /api/v1/portal/card-quality/runs/{run_id}` and record eligible, processed, analyzed, skipped, failed, created, and resolved counts.
4. Call `GET /api/v1/portal/card-quality/issues?include_info=true` and record actionable versus informational counts.
5. Call `GET /api/v1/portal/products` and verify product rows include quality score, status, issue count, photo count, and analyzed time.
6. Call `GET /api/v1/portal/products/{nm_id}` and verify Product 360 card-quality block matches the product-quality endpoint.
7. Open `/products`, `/products/:nmId`, `/actions`, `/data-fix`, and `/doctor` in the frontend and confirm local quality signals are visible without requiring legacy Checker write access.

## Known Limitation

The Products page enriches the current money-aggregate page with card-quality snapshots. Quality status filtering is therefore page-bounded in this pass. A catalog-wide quality-first pagination mode would require a shared aggregate query over product cards, money rows, latest quality snapshots, and open issue counts.
