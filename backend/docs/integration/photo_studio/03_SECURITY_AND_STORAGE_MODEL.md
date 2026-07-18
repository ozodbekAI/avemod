# Photo Studio Security And Storage Model

## Boundaries

- `account_id` is checked server-side for all Photo Studio endpoints.
- Write operations require at least `operator` role, except settings updates which require `manager`.
- Superuser and account access behavior stays in the existing Finance auth layer.

## Storage

- Binary image bytes are not stored in PostgreSQL.
- Local development storage root defaults to `.local/photo_studio`.
- Storage keys include `accounts/{account_id}/photo_studio/projects/{project_id}/` and a random non-guessable filename.
- Download is via expiring signed internal URLs, not permanent public object URLs.

## Upload Validation

- Allowed MIME types: `image/jpeg`, `image/png`, `image/webp`.
- SVG and executable-like arbitrary files are rejected.
- Size and dimensions are bounded.
- Image type is sniffed from bytes, not trusted solely from request headers.
- JPEG EXIF APP1 metadata is stripped before persistence.

## Secrets And Providers

- Provider secrets are not stored in Photo Studio tables and are never returned in responses.
- AI generation is optional and account-configured.
- If a provider is unavailable or not configured, generation returns `not_configured`; manual upload/version/review remains usable.

## Marketplace Safety

- Photo Studio approval creates only a local safe change/result event.
- No image is applied to Wildberries automatically.
- Future marketplace-changing operations must add preview, explicit confirmation, account-scoped permission checks, and audit before submit/apply.
