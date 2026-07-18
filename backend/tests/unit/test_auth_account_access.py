from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.core.db import Base  # noqa: F401
from app.models.accounts import WBAccount
from app.services.auth import resolve_user_account


class _FakeScalarResult:
    def __init__(self, values: list[object]) -> None:
        self._values = values

    def __iter__(self):
        return iter(self._values)


class _FakeExecuteResult:
    def __init__(self, *, rows: list[tuple[int, str]], scalars: list[object]) -> None:
        self._rows = rows
        self._scalars = scalars

    def all(self) -> list[tuple[int, str]]:
        return self._rows

    def scalars(self) -> _FakeScalarResult:
        return _FakeScalarResult(self._scalars)


class _FakeAccountSession:
    def __init__(self, *, allowed_account_ids: set[int]) -> None:
        self.accounts = {
            1: SimpleNamespace(
                id=1,
                name="Own",
                seller_name=None,
                external_account_id=None,
                timezone="Europe/Moscow",
                is_active=True,
                created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            ),
            2: SimpleNamespace(
                id=2,
                name="Forbidden",
                seller_name=None,
                external_account_id=None,
                timezone="Europe/Moscow",
                is_active=True,
                created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            ),
        }
        self.allowed_account_ids = allowed_account_ids

    async def get(self, model: object, key: int):
        if model is WBAccount:
            return self.accounts.get(int(key))
        return None

    async def execute(self, stmt: object) -> _FakeExecuteResult:
        allowed_accounts = [
            account
            for account_id, account in sorted(self.accounts.items())
            if account_id in self.allowed_account_ids
        ]
        rows = [(int(account.id), "operator") for account in allowed_accounts]
        return _FakeExecuteResult(rows=rows, scalars=allowed_accounts)


@pytest.mark.asyncio
async def test_resolve_user_account_allows_normal_user_own_account() -> None:
    user = SimpleNamespace(id=10, is_superuser=False)
    account = await resolve_user_account(
        _FakeAccountSession(allowed_account_ids={1}),
        user,
        account_id=1,
        require_account=True,
    )

    assert account is not None
    assert account.id == 1


@pytest.mark.asyncio
async def test_resolve_user_account_denies_normal_user_forbidden_account() -> None:
    user = SimpleNamespace(id=10, is_superuser=False)

    with pytest.raises(HTTPException) as exc:
        await resolve_user_account(
            _FakeAccountSession(allowed_account_ids={1}),
            user,
            account_id=2,
            require_account=True,
        )

    assert exc.value.status_code == 403
    assert exc.value.detail == "Account access forbidden"


@pytest.mark.asyncio
async def test_resolve_user_account_allows_superuser_for_other_account() -> None:
    user = SimpleNamespace(id=1, is_superuser=True)
    account = await resolve_user_account(
        _FakeAccountSession(allowed_account_ids={1}),
        user,
        account_id=2,
        require_account=True,
    )

    assert account is not None
    assert account.id == 2
