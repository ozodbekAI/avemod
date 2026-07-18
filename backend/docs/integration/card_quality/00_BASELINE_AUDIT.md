# Card Quality Baseline Audit

Phase 1 inspected the existing Finance portal flow, Finance product-card tables, and the extracted Checker reference project under `/tmp/finance_incoming_projects_audit/checker`.

## Current Finance Flow

- Public route: `GET /api/v1/portal/products/{nm_id}/quality`.
- Router: `app/modules/portal/router.py`.
- Existing orchestration: `PortalService.product_quality`.
- Product 360 assembly calls a quality source and exposes both `quality` and `card_quality` blocks.
- Action Center previously pulled card-quality actions from `CheckerAdapter.quality_actions`.
- Legacy profit diagnostics already accept card quality as an explanatory optional signal through the portal/checker quality contract.

## Finance Source Data

Local analysis uses Finance-owned tables:

- `wb_product_cards`: identity, title, description, brand, subject, vendor code, photos, video, dimensions, raw payload.
- `wb_product_card_characteristics`: normalized characteristic name/value rows.
- `wb_product_card_sizes`: size/chrt/skus rows.

The normalizer tolerates missing fields and never invents content. Missing source fields create evidence-based issues only when the absence itself is meaningful.

## Checker Logic Reused

The legacy Checker project contains useful logic around:

- card snapshot normalization;
- title and description quality checks;
- characteristic completeness checks;
- media/photo/video checks;
- issue categorization and score impact;
- issue de-duplication and action mapping.

This phase reimplemented the deterministic subset locally rather than copying Checker auth, stores, teams, billing, SQLite DB, WB apply jobs, or external service runtime.

## Implemented Local Rule Families

- `title`: missing, too short, too long, repeated words, excessive punctuation/caps, title equals vendor code.
- `description`: missing, too short, duplicates title, too little useful detail.
- `characteristics`: missing, empty values, conflicting duplicate values, missing high-value filter fields.
- `media`: no images, too few images, duplicate image URLs, invalid image URL, no video as informational only.
- `identity`: missing brand, missing subject/category.

## Contract Semantics

The new local module returns:

- `module=card_quality`
- `mode=local`
- `source=card_quality`
- `score`
- `category_scores`
- `issues`
- `analyzed_at`
- `source_revision`
- `next_recommended_action`

External Checker remains a fallback only when local quality is unavailable.
