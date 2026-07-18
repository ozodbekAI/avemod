from __future__ import annotations

from datetime import timedelta
import re

import pytest
from cryptography.fernet import Fernet
from jose import jwt

from app.core.config import Settings, get_settings
from app.core.security import (
    TokenError,
    create_access_token,
    create_refresh_token,
    decode_token,
    fingerprint,
    hash_password,
    verify_password,
)
from app.core.db import Base  # noqa: F401
from app.core.time import utcnow
from app.models.auth import AuthRefreshToken, AuthUser
from app.schemas.auth import LoginRequest
from app.services.auth import AuthService


JWT_LOOKING_RE = re.compile(
    r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"
)


class _FakeAuthSession:
    def __init__(self, user: AuthUser) -> None:
        self.user = user
        self.added: list[object] = []

    def add(self, value: object) -> None:
        self.added.append(value)

    async def flush(self) -> None:
        return None

    async def get(self, model: object, identifier: int) -> AuthUser | None:
        if model is AuthUser and int(identifier) == int(self.user.id):
            return self.user
        return None


class _FakeUserRepository:
    def __init__(self, user: AuthUser) -> None:
        self.user = user

    async def get_by_email(self, session: object, email: str) -> AuthUser | None:
        return self.user if email == self.user.email else None


class _FakeRefreshTokenRepository:
    def __init__(self, token_row: AuthRefreshToken | None = None) -> None:
        self.token_row = token_row

    async def get_by_fingerprint(self, session: object, token_fingerprint: str) -> AuthRefreshToken | None:
        if self.token_row is None or self.token_row.token_fingerprint != token_fingerprint:
            return None
        return self.token_row


def test_password_hash_roundtrip() -> None:
    raw = "super-secret-password"
    hashed = hash_password(raw)
    assert hashed != raw
    assert verify_password(raw, hashed)


def test_tokens_decode() -> None:
    access = create_access_token("1")
    refresh = create_refresh_token("1")
    assert decode_token(access)["sub"] == "1"
    assert decode_token(refresh, refresh=True)["sub"] == "1"
    assert fingerprint("abc") == fingerprint("abc")


def test_access_token_decodes_as_access() -> None:
    payload = decode_token(create_access_token("1"))

    assert payload["sub"] == "1"
    assert payload["type"] == "access"


def test_refresh_token_decodes_as_refresh() -> None:
    payload = decode_token(create_refresh_token("1"), refresh=True)

    assert payload["sub"] == "1"
    assert payload["type"] == "refresh"


def test_refresh_token_rejected_as_access() -> None:
    with pytest.raises(TokenError, match="Invalid token type|Invalid token"):
        decode_token(create_refresh_token("1"))


def test_access_token_rejected_as_refresh() -> None:
    with pytest.raises(TokenError, match="Invalid token type|Invalid token"):
        decode_token(create_access_token("1"), refresh=True)


def test_token_without_type_rejected() -> None:
    settings = get_settings()
    token = jwt.encode({"sub": "1"}, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)

    with pytest.raises(TokenError, match="Invalid token type"):
        decode_token(token)


def test_refresh_token_without_type_rejected() -> None:
    settings = get_settings()
    token = jwt.encode({"sub": "1"}, settings.jwt_refresh_secret_key, algorithm=settings.jwt_algorithm)

    with pytest.raises(TokenError, match="Invalid token type"):
        decode_token(token, refresh=True)


def test_refresh_tokens_are_unique_for_same_subject() -> None:
    first = create_refresh_token("1")
    second = create_refresh_token("1")

    assert first != second
    assert fingerprint(first) != fingerprint(second)


@pytest.mark.asyncio
async def test_auth_token_issue_login_and_refresh_do_not_print_tokens(capsys: pytest.CaptureFixture[str]) -> None:
    user = AuthUser(
        id=1,
        email="security-test@example.com",
        full_name="Security Test",
        password_hash=hash_password("fake-test-password"),
        is_active=True,
        is_superuser=False,
    )
    session = _FakeAuthSession(user)
    service = AuthService()
    service.users = _FakeUserRepository(user)  # type: ignore[assignment]

    issued = await service._issue_tokens(session, user)
    login_tokens = await service.login(
        session,
        LoginRequest(email="security-test@example.com", password="fake-test-password"),
    )

    refresh_row = AuthRefreshToken(
        user_id=user.id,
        token_fingerprint=fingerprint(issued.refresh_token),
        expires_at=utcnow() + timedelta(days=1),
        revoked_at=None,
    )
    service.refresh_tokens = _FakeRefreshTokenRepository(refresh_row)  # type: ignore[assignment]
    refresh_tokens = await service.refresh(session, issued.refresh_token)

    captured = capsys.readouterr()
    combined_output = captured.out + captured.err

    assert combined_output == ""
    assert JWT_LOOKING_RE.search(combined_output) is None
    for raw_token in (
        issued.access_token,
        issued.refresh_token,
        login_tokens.access_token,
        login_tokens.refresh_token,
        refresh_tokens.access_token,
        refresh_tokens.refresh_token,
    ):
        assert raw_token not in combined_output


def test_production_like_jwt_secrets_must_differ() -> None:
    with pytest.raises(ValueError, match="jwt_refresh_secret_key"):
        Settings(
            app_env="production",
            jwt_secret_key="production-access-secret",
            jwt_refresh_secret_key="production-access-secret",
            wb_token_encryption_key=Fernet.generate_key().decode("utf-8"),
        )
