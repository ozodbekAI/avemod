from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_photo_studio_frontend_routes_match_backend_contract() -> None:
    endpoints = _read("../frontend/src/lib/endpoints.ts")
    client = _read("../frontend/src/lib/photo-studio.ts")
    photo_block = endpoints.split("// ─── Photo Studio", 1)[1].split("},\n  sync:", 1)[0]

    for expected in (
        "/portal/photo/projects/${id}/assets/import-wb",
        "/portal/photo/projects/${id}/assets/upload",
        "/portal/photo/projects/${id}/messages",
        "/portal/photo/assets/${assetId}/download-url",
        "/portal/photo/projects/${id}/versions/${vid}/review",
        "/portal/photo/jobs/${jobId}/retry",
    ):
        assert expected in photo_block

    assert "photoProjectManualUpdate" not in photo_block
    assert "/manual-update" not in photo_block
    assert "/prefer" not in photo_block
    assert "/approve" not in photo_block
    assert "/reject" not in photo_block
    assert "query: withAcc(accountId)" in client
    assert "photoProjectMessages" in client
    assert "photoVersionReview" in client


def test_photo_studio_manual_mode_creates_versions_and_signed_downloads() -> None:
    client = _read("../frontend/src/lib/photo-studio.ts")
    route = _read("../frontend/src/routes/_authenticated/photo-studio.projects.$projectId.tsx")

    assert "export const createPhotoVersion" in client
    assert "fetchPhotoAssetDownloadUrl" in client
    assert "recordManualWbUpdate" in client
    assert "addProjectComment(" in client
    assert "manual-update" not in client
    assert "createPhotoVersion(projectId, activeId!" in route
    assert "Создать версию" in route
    assert "fetchPhotoAssetDownloadUrl(approvedVersion.asset_id" in route
    assert "allowed_mime_types" in route
    assert "external_apply_enabled" in route


def test_photo_studio_project_creation_requires_nm_id() -> None:
    client = _read("../frontend/src/lib/photo-studio.ts")
    list_route = _read("../frontend/src/routes/_authenticated/photo-studio.tsx")

    assert "nm_id: number | string;" in client
    assert "Введите nm_id товара" in list_route
    assert "source_action_key: \"manual\"" in list_route
    assert "nm_id для проекта" in list_route


def test_photo_studio_backend_preserves_storage_security_and_results() -> None:
    service = _read("app/services/photo_studio.py")
    schemas = _read("app/schemas/photo.py")
    doc = _read("../docs/final_integration/PHOTO_STUDIO_AUDIT.md")

    assert "accounts/{account_id}/photo_studio/projects/{project_id}" in service
    assert "verify_download_token" in service
    assert "external_apply_enabled=False" in service
    assert "version_apply_wb_blocked_draft_only" in service
    assert "card_photos_save_wb_blocked_draft_only" in service
    assert '"requires_explicit_confirm": True' in service
    assert '"marketplace_write_performed": False' in service
    assert 'event_type="photo_changed"' in service
    assert 'external_status="draft_ready"' in service
    assert "PhotoVersionReview" in schemas
    assert "Local manual mode works without an AI provider" in doc
    assert "Auto-apply to Wildberries is disabled" in doc
