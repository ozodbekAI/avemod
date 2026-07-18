from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.services.photo_studio import PhotoStorageService


def _settings(tmp_path):
    return SimpleNamespace(
        photo_storage_root=str(tmp_path),
        photo_signed_url_ttl_seconds=60,
        jwt_secret_key="test-photo-signing-secret",
    )


def _png(width: int = 100, height: int = 100) -> bytes:
    return b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + width.to_bytes(4, "big") + height.to_bytes(4, "big") + b"\x08\x02\x00\x00\x00" + b"\x00" * 32


def _jpeg_with_exif(width: int = 100, height: int = 100) -> bytes:
    sof0 = (
        b"\xff\xc0\x00\x11\x08"
        + height.to_bytes(2, "big")
        + width.to_bytes(2, "big")
        + b"\x03\x01\x11\x00\x02\x11\x00\x03\x11\x00"
    )
    return b"\xff\xd8" + b"\xff\xe1\x00\x08Exif\x00\x00" + sof0 + b"\xff\xda\x00\x08\x01\x01\x00\x00?\x00\x00\xff\xd9"


def test_photo_storage_accepts_png_and_creates_signed_url(tmp_path) -> None:
    storage = PhotoStorageService(_settings(tmp_path))

    stored = storage.store_bytes(
        account_id=7,
        project_id=11,
        original_file_name="product.png",
        content=_png(),
        declared_mime="image/png",
    )

    assert stored.mime_type == "image/png"
    assert stored.width == 100
    assert stored.height == 100
    assert storage.path_for_key(stored.storage_key).exists()
    signed = storage.signed_url(asset_id=123, storage_key=stored.storage_key, account_id=7)
    assert "account_id=7" in signed.url
    token = signed.url.split("token=", 1)[1]
    storage.verify_download_token(asset_id=123, storage_key=stored.storage_key, token=token)
    with pytest.raises(HTTPException):
        storage.verify_download_token(asset_id=124, storage_key=stored.storage_key, token=token)


def test_photo_storage_rejects_svg_payload(tmp_path) -> None:
    storage = PhotoStorageService(_settings(tmp_path))

    with pytest.raises(HTTPException) as exc:
        storage.store_bytes(
            account_id=7,
            project_id=11,
            original_file_name="unsafe.svg",
            content=b"<svg><script>alert(1)</script></svg>",
            declared_mime="image/svg+xml",
        )

    assert exc.value.status_code == 400


def test_photo_storage_strips_jpeg_exif(tmp_path) -> None:
    storage = PhotoStorageService(_settings(tmp_path))

    stored = storage.store_bytes(
        account_id=7,
        project_id=11,
        original_file_name="with-exif.jpg",
        content=_jpeg_with_exif(),
        declared_mime="image/jpeg",
    )
    saved = storage.path_for_key(stored.storage_key).read_bytes()

    assert stored.mime_type == "image/jpeg"
    assert stored.exif_removed is True
    assert b"Exif\x00\x00" not in saved
