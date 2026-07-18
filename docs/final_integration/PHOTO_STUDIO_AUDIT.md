# Photo Studio Audit

Generated during Section 10 on 2026-06-25.

## Static Status

Photo Studio is Finance-owned and local-first.

- Backend routes cover status, settings, projects, WB source image import, secure uploads, asset listing/deletion, signed downloads, versions, reviews, comments/messages, jobs, retry/cancel, and experiment creation.
- Local manual mode works without an AI provider: operators can upload an image, create a version from that asset, mark it preferred, approve it, reject it, comment, and download the approved asset through a signed URL.
- Provider mode is guarded. Job creation records `not_configured` when generation is not configured and leaves manual upload/version flow available.
- Auto-apply to Wildberries is disabled. Settings output forces `external_apply_enabled=false`; approval records a `photo_changed` ResultEvent with marketplace apply disabled.
- Manual WB follow-up is tracked as a project message. There is no frontend dependency on a `/manual-update` route.

## Contract

Frontend endpoint constants now match the backend contract:

- `POST /portal/photo/projects/{project_id}/assets/import-wb`
- `POST /portal/photo/projects/{project_id}/assets/upload`
- `GET /portal/photo/projects/{project_id}/assets`
- `POST /portal/photo/projects/{project_id}/versions`
- `POST /portal/photo/projects/{project_id}/versions/{version_id}/review`
- `POST /portal/photo/projects/{project_id}/messages`
- `GET /portal/photo/assets/{asset_id}/download-url`
- `POST /portal/photo/jobs/{job_id}/cancel`
- `POST /portal/photo/jobs/{job_id}/retry`

## Remaining Runtime Proof

- Create a project from Product 360/Data Fix/Actions deep links and verify the `nm_id` is preserved.
- Import real WB source images for a product with card photos.
- Upload JPEG/PNG/WEBP and verify MIME, size, dimensions, EXIF stripping, account-scoped storage key, and signed download.
- Create a version from a local upload without an AI provider, approve it, and verify Results shows the `photo_changed` event.
- Create an AI job with no provider and verify it returns `not_configured` rather than pretending success.
