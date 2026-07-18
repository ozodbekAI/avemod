# Photo Studio Implementation Plan

## Implemented In This Phase

1. Add local Photo Studio persistence tables.
2. Add local image storage service with account-scoped keys.
3. Add upload validation for MIME, size, dimensions, and unsupported formats.
4. Strip JPEG EXIF metadata before storing.
5. Add expiring signed download URLs.
6. Add project, asset, version, message, job, settings, and status API contracts.
7. Import WB source images from Finance-owned `wb_product_cards.photos` as remote references.
8. Add Product 360 `photo_studio` status block.
9. Add local module health for Photo Studio.
10. Create safe `result_events` when a version is approved.

## Intentional MVP Limits

- AI generation jobs are created as `not_configured` unless account settings have a provider. No provider call is made inside HTTP.
- WB apply/publish is not exposed.
- Remote WB source images are referenced; they are not downloaded into local storage in this phase.
- S3-compatible storage can be added behind `PhotoStorageService` without changing portal contracts.

## Next Focus

- Add a real async worker/provider adapter behind `photo_generation_jobs`.
- Add thumbnail generation once an image processing library is approved for the backend runtime.
- Add richer Action Center task creation from open card-quality media issues.
- Add frontend views for compare, preferred version, and approval history.
