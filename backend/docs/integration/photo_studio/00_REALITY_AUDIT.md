# Photo Studio Reality Audit

Finance already owns the account boundary, auth, product-card data, Action Center, ResultEvent tracking, and portal module registry. The useful integration path is therefore a local Finance module, not an external Photo backend.

## Existing Finance Pieces

- Product identity is `account_id` + `nm_id` from `wb_product_cards` and related finance/product services.
- Product 360 is served by `GET /api/v1/portal/products/{nm_id}` through `PortalService.product_360`.
- Card quality media issue codes are local in `app/services/card_quality.py`: `media_no_images`, `media_too_few_images`, `media_duplicate_urls`, `media_invalid_url`, and `media_no_video_info`.
- Guided fixes already route checker media/photo actions to `photo_studio`.
- Result tracking is Finance-owned through `result_events`.
- Portal module state is Finance-owned through `portal_integrations` and `ModuleRegistryService`.

## Storage Reality

No shared object-storage abstraction existed for images. The implementation adds a local `PhotoStorageService` with account-scoped random storage keys and expiring signed download URLs. Production S3-compatible storage can replace the local path behind the same service contract.

## Reused

- Finance auth and account access checks.
- Finance `wb_product_cards.photos` as WB source image references.
- Existing portal response conventions: `status`, warnings, unavailable sources, module health.
- Existing `ResultEvent` table for safe result/change events.
- Existing guided-fix route key `photo_studio`.

## Not Reused Or Not Imported

- No old auth/users/stores/billing/credits are imported.
- No external Photo backend is required for daily reads.
- No marketplace apply/update endpoint is implemented.
- No provider secret is stored in Photo Studio tables.

## Provider-Free Flow

Manual upload, WB source import, project creation, version creation, comments, preferred/approved/rejected review, signed download, history, and safe result events work without an AI provider.
