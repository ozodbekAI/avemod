from __future__ import annotations

from datetime import timedelta
from hashlib import sha256
from typing import Any
from uuid import uuid4

from cryptography.fernet import Fernet
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import get_settings
from app.core.time import utcnow

pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
settings = get_settings()


class TokenError(ValueError):
    """Raised when a JWT token cannot be decoded."""


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def _build_token(payload: dict[str, Any], secret: str, expires_delta: timedelta) -> str:
    to_encode = payload.copy()
    expire = utcnow() + expires_delta
    to_encode.update({"exp": expire, "iat": utcnow()})
    return jwt.encode(to_encode, secret, algorithm=settings.jwt_algorithm)


def create_access_token(subject: str) -> str:
    return _build_token(
        payload={"sub": subject, "type": "access"},
        secret=settings.jwt_secret_key,
        expires_delta=timedelta(minutes=settings.access_token_expire_minutes),
    )


def create_refresh_token(subject: str) -> str:
    return _build_token(
        payload={"sub": subject, "type": "refresh", "jti": uuid4().hex},
        secret=settings.jwt_refresh_secret_key,
        expires_delta=timedelta(days=settings.refresh_token_expire_days),
    )


def decode_token(token: str, refresh: bool = False) -> dict[str, Any]:
    secret = settings.jwt_refresh_secret_key if refresh else settings.jwt_secret_key
    expected_type = "refresh" if refresh else "access"
    try:
        payload = jwt.decode(token, secret, algorithms=[settings.jwt_algorithm])
    except JWTError as exc:
        raise TokenError("Invalid token") from exc
    if payload.get("type") != expected_type:
        raise TokenError("Invalid token type")
    return payload


def fingerprint(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def get_fernet() -> Fernet:
    return Fernet(settings.wb_token_encryption_key.encode("utf-8"))


def encrypt_wb_token(token: str) -> str:
    return get_fernet().encrypt(token.encode("utf-8")).decode("utf-8")


def decrypt_wb_token(token_encrypted: str) -> str:
    return get_fernet().decrypt(token_encrypted.encode("utf-8")).decode("utf-8")
