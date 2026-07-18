# Card Quality Implementation Plan

## Completed In This Slice

1. Add local persistence:
   - `card_quality_analysis_runs`
   - `card_quality_snapshots`
   - `card_quality_issues`
   - `card_quality_issue_status_history`
2. Add deterministic normalizer/rule engine/analysis service in `app/services/card_quality.py`.
3. Preserve `/portal/products/{nm_id}/quality` compatibility while returning local module fields.
4. Add account-scoped routes:
   - `POST /portal/card-quality/analyze`
   - `POST /portal/card-quality/products/{nm_id}/analyze`
   - `GET /portal/card-quality/runs`
   - `GET /portal/card-quality/issues`
   - `PATCH /portal/card-quality/issues/{issue_id}/status`
5. Update Product 360 and Action Center to use local quality data first.
6. Update module health to report local `checker` health from snapshots/issues before env fallback.

## Remaining Work

1. Move full-account analysis to a true background queue instead of bounded synchronous batches.
2. Add richer subject-specific required characteristic rules.
3. Add product-list card quality state aggregation.
4. Add Data Fix UI contract tabs/filters for `photo`, `title`, `description`, `characteristics`.
5. Add richer Doctor narrative tests for local quality + finance context.
6. Add optional LLM suggestions behind a disabled-by-default feature flag.

## Safety

- No WB card write is performed.
- No auto-apply or apply-all exists.
- No Checker auth/store/user/team/billing is imported.
- No raw marketplace credentials are logged or returned.
