from __future__ import annotations

from datetime import UTC, datetime

from app.schemas.portal import PortalDataSyncDomainStatus
from app.schemas.sync import SyncCursorRead, SyncRunRead


def test_sync_run_read_scrubs_secret_like_details_and_error_text() -> None:
    row = SyncRunRead(
        id=1,
        account_id=1,
        domain="finance",
        trigger="manual",
        status="failed",
        is_backfill=False,
        started_at=datetime(2026, 6, 19, tzinfo=UTC),
        finished_at=None,
        details={
            "token": "must-not-leak",
            "safe": True,
            "nested": {"authorization": "Bearer must-not-leak", "message": "api_key=must-not-leak"},
        },
        error_text="request failed Authorization: Bearer must-not-leak",
    )

    dumped = row.model_dump(mode="json")
    assert "must-not-leak" not in str(dumped)
    assert dumped["details"] == {"safe": True, "nested": {"message": "api_key=<redacted>"}}
    assert dumped["error_text"] == "request failed Authorization=<redacted>"


def test_sync_cursor_read_scrubs_secret_like_cursor_payload() -> None:
    row = SyncCursorRead(
        id=1,
        account_id=1,
        domain="orders",
        cursor_key="default",
        cursor_value={"lastChangeDate": "2026-06-19", "refresh_token": "must-not-leak"},
        last_synced_at=None,
        status="idle",
        last_error_text="upstream said password=must-not-leak",
    )

    dumped = row.model_dump(mode="json")
    assert "must-not-leak" not in str(dumped)
    assert dumped["cursor_value"] == {"lastChangeDate": "2026-06-19"}
    assert dumped["last_error_text"] == "upstream said password=<redacted>"


def test_portal_sync_status_redacts_bearer_values() -> None:
    row = PortalDataSyncDomainStatus(
        domain="finance",
        status="failed",
        last_error_text="WB failed with bearer must-not-leak",
        next_action="fix_token",
    )

    dumped = row.model_dump(mode="json")
    assert "must-not-leak" not in str(dumped)
    assert dumped["last_error_text"] == "WB failed with Bearer <redacted>"
