# Photo Studio Component Map

| Legacy/External Concept | Finance Local Component |
| --- | --- |
| photo asset / user asset / product asset | `photo_assets` |
| product-linked photo workspace | `photo_projects` |
| generated or edited output | `photo_versions` linked to `photo_assets` |
| generation run | `photo_generation_jobs` |
| photo thread/chat/comment | `photo_project_messages` |
| audit/event stream | `photo_project_events` plus `result_events` for approved safe changes |
| provider settings | `photo_settings` plus future encrypted `portal_integrations.configuration_encrypted_json` |
| apply job / WB media publish | Not migrated; marketplace apply is disabled |

## API Surface

- `GET /api/v1/portal/photo/status`
- `GET|PUT /api/v1/portal/photo/settings`
- `GET|POST /api/v1/portal/photo/projects`
- `GET|PATCH /api/v1/portal/photo/projects/{project_id}`
- `POST /api/v1/portal/photo/projects/{project_id}/archive`
- `POST /api/v1/portal/photo/projects/{project_id}/assets/upload`
- `POST /api/v1/portal/photo/projects/{project_id}/assets/import-wb`
- `GET /api/v1/portal/photo/projects/{project_id}/assets`
- `DELETE /api/v1/portal/photo/assets/{asset_id}`
- `GET /api/v1/portal/photo/assets/{asset_id}/download-url`
- `GET /api/v1/portal/photo/assets/{asset_id}/download`
- `POST /api/v1/portal/photo/projects/{project_id}/versions`
- `POST /api/v1/portal/photo/projects/{project_id}/versions/{version_id}/review`
- `POST /api/v1/portal/photo/projects/{project_id}/messages`
- `POST /api/v1/portal/photo/projects/{project_id}/jobs`
- `GET /api/v1/portal/photo/jobs`
- `GET /api/v1/portal/photo/jobs/{job_id}`
- `POST /api/v1/portal/photo/jobs/{job_id}/retry`
- `POST /api/v1/portal/photo/jobs/{job_id}/cancel`

## Product 360

`PortalProduct360Read` now includes `photo_studio`, a `PortalDataBlock` containing Photo Studio status. Optional Photo Studio failures are isolated and reported through `unavailable_sources`.
