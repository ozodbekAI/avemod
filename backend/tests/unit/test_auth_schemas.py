from __future__ import annotations

from datetime import datetime, timezone

from app.schemas.auth import UserRead


def test_user_read_allows_existing_reserved_domain_emails() -> None:
    user = UserRead(
        id=1,
        email="rbac-audit-seller@example.test",
        full_name="RBAC Audit Seller",
        is_active=True,
        is_superuser=False,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )

    assert user.email == "rbac-audit-seller@example.test"
