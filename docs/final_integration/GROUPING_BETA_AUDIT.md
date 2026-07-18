# Grouping Beta Audit

Section 09 check, 2026-06-25.

## Covered Surface

- Local engine lives in Finance as `GroupingBetaService`.
- Product normalization includes article core/base core, brand, subject, color, characteristics, sizes, barcodes, media summary, and source revision.
- Candidate generation supports article-family, IMT validation, variant, and duplicate-style scenarios through the local scenario resolver.
- Constraints block cross-brand, cross-subject, conflicting article-family, and missing identity evidence by default.
- Scoring and risk are stored on local candidates; high-risk/blocked operations never produce a WB merge.
- Full catalog run is supported by `POST /portal/grouping/preview` when `nm_id` is omitted; product-scoped preview is supported when `nm_id` is provided.
- Product 360 uses `/portal/products/{nm_id}/grouping` and falls back from local empty state to the legacy adapter only when external grouping is configured.
- Action Center and Doctor can consume local Grouping Beta recommendations as review-only actions.
- Review status is local-only through `/portal/grouping/candidates/{candidate_id}/status`.

## Section 09 Fixes In This Pass

- The Grouping frontend now calls the local preview endpoint and can run full-catalog or `nm_id`-scoped analysis from the page.
- The Grouping frontend now displays local recommendations and exposes accept, reject, and postpone review actions.
- Portal client endpoint constants now include grouping preview and candidate status review.
- Static regression tests guard the local UI lifecycle, no-WB-merge safety, and audit documentation.

## Safety Model

- Finance never exposes a `merge-wb` route.
- Recommendation payloads include `auto_merge_enabled=false` and preview payloads have `enabled=false`.
- Review buttons only change local candidate status and result history; they do not mutate WB cards.
- External legacy grouping remains blocked by configuration and test-account gates unless explicitly configured.

## Remaining Runtime Proof

Needs a configured runtime account/DB:

- Run full-catalog preview with `nm_id=null` and record analyzed product count.
- Run product-scoped preview for a real `nm_id` and verify Product 360 shows the same recommendation.
- Review accept/reject/postpone and verify Action Center, Doctor, and Results reflect the status.
- Confirm a real empty full-catalog run is honest: `products_processed > 0`, `candidate_groups = 0`, and no placeholder recommendations.
