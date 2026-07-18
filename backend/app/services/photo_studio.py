from __future__ import annotations

import base64
import hashlib
import hmac
import ipaddress
import os
import secrets
import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
from fastapi import HTTPException, UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.security import decrypt_wb_token
from app.core.time import utcnow
from app.models.accounts import WBAPICategory, WBAPIToken
from app.models.auth import AuthUser
from app.models.operator import PortalIntegration, ResultEvent, UnifiedAction
from app.models.photo_studio import (
    PhotoAsset,
    PhotoGenerationJob,
    PhotoProject,
    PhotoProjectEvent,
    PhotoProjectMessage,
    PhotoSettings,
    PhotoVersion,
)
from app.models.product_cards import WBProductCard
from app.schemas.photo import (
    PhotoAssetOut,
    PhotoDownloadUrlOut,
    PhotoJobCreate,
    PhotoJobOut,
    PhotoProjectCreate,
    PhotoProjectEventOut,
    PhotoProjectMessageCreate,
    PhotoProjectMessageOut,
    PhotoProjectOut,
    PhotoProjectUpdate,
    PhotoProjectsPage,
    PhotoSettingsOut,
    PhotoSettingsUpdate,
    PhotoStudioStatusOut,
    PhotoVersionCreate,
    PhotoVersionOut,
    PhotoVersionReview,
    PhotoWBImportOut,
)


ALLOWED_MIME_TYPES = ("image/jpeg", "image/png", "image/webp")
MAX_UPLOAD_MB = 10
MIN_IMAGE_SIDE = 64
MAX_IMAGE_SIDE = 12000
MAX_REMOTE_IMAGE_BYTES = 15 * 1024 * 1024
GEMINI_IMAGE_FALLBACK_MODEL = "gemini-2.5-flash-image"


class PhotoProviderError(RuntimeError):
    pass


def _photo_provider_message(exc: Exception | str | None = None) -> str:
    raw = str(exc or "").strip()
    lowered = raw.lower()
    if not raw:
        return "Провайдер генерации фото вернул ошибку."
    if (
        "gemini_api_key" in lowered
        or "api key" in lowered
        or "not configured" in lowered
    ):
        return "Провайдер генерации фото не настроен. Проверьте ключ Gemini в настройках сервера."
    if "no source image" in lowered:
        return "Для этой операции нужно выбрать исходное фото."
    if "no candidates" in lowered:
        return "Провайдер не вернул готовое изображение. Попробуйте уточнить задачу или выбрать другое исходное фото."
    if "private image url" in lowered:
        return "Нельзя использовать приватную ссылку на изображение."
    if "too large" in lowered:
        return "Исходное изображение слишком большое."
    if "did not return an image" in lowered or "non-image" in lowered:
        return "По ссылке не найдено изображение."
    if "unsupported image url scheme" in lowered:
        return "Поддерживаются только ссылки http/https."
    if "gemini error" in lowered or "gemini request failed" in lowered:
        return "Gemini временно не смог обработать фото. Попробуйте повторить задачу."
    return raw[:1000]


class GeminiImageProvider:
    """Small REST adapter based on the incoming checker Photo Chat generator."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.api_key = (settings.gemini_api_key or "").strip()
        self.base_url = str(
            settings.gemini_api_base_url
            or "https://generativelanguage.googleapis.com/v1beta"
        ).rstrip("/")
        if not self.api_key:
            raise PhotoProviderError("GEMINI_API_KEY is not configured")

    async def edit_or_generate(
        self,
        *,
        prompt: str,
        images: list[tuple[bytes, str]],
        model: str | None = None,
        aspect_ratio: str | None = None,
    ) -> tuple[bytes, str, str | None, str]:
        selected_model = (
            model or self.settings.gemini_image_model or ""
        ).strip() or "gemini-3.1-flash-image-preview"
        fallback_model = (
            self.settings.gemini_image_model_fallback or GEMINI_IMAGE_FALLBACK_MODEL
        ).strip()
        try:
            return await self._call_model(
                selected_model, prompt=prompt, images=images, aspect_ratio=aspect_ratio
            )
        except PhotoProviderError:
            if not fallback_model or fallback_model == selected_model:
                raise
            return await self._call_model(
                fallback_model, prompt=prompt, images=images, aspect_ratio=aspect_ratio
            )

    async def _call_model(
        self,
        model: str,
        *,
        prompt: str,
        images: list[tuple[bytes, str]],
        aspect_ratio: str | None,
    ) -> tuple[bytes, str, str | None, str]:
        parts: list[dict[str, Any]] = [
            {
                "text": prompt.strip()
                or "Создайте готовый для маркетплейса вариант фото товара."
            }
        ]
        for raw, mime_type in images[:4]:
            parts.append(
                {
                    "inline_data": {
                        "mime_type": mime_type
                        if mime_type.startswith("image/")
                        else "image/png",
                        "data": base64.b64encode(raw).decode("utf-8"),
                    }
                }
            )
        generation_config: dict[str, Any] = {"responseModalities": ["TEXT", "IMAGE"]}
        if aspect_ratio:
            generation_config["imageConfig"] = {"aspectRatio": aspect_ratio}
        payload = {
            "contents": [{"role": "user", "parts": parts}],
            "generationConfig": generation_config,
        }
        url = f"{self.base_url}/models/{model}:generateContent"
        timeout = float(self.settings.gemini_image_timeout_seconds or 240.0)
        max_retries = max(0, int(self.settings.gemini_image_max_retries or 0))
        last_error = ""
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(
                timeout, connect=10.0, read=timeout, write=timeout, pool=timeout
            )
        ) as client:
            for attempt in range(max_retries + 1):
                try:
                    response = await client.post(
                        url,
                        json=payload,
                        headers={
                            "x-goog-api-key": self.api_key,
                            "Content-Type": "application/json",
                        },
                    )
                except httpx.HTTPError as exc:
                    last_error = str(exc)
                    if attempt >= max_retries:
                        raise PhotoProviderError(
                            f"Gemini request failed: {last_error}"
                        ) from exc
                    continue
                if response.status_code < 400:
                    return self._extract_image(response.json(), model)
                last_error = response.text[:1000]
                if (
                    response.status_code not in {408, 429, 500, 502, 503, 504}
                    or attempt >= max_retries
                ):
                    raise PhotoProviderError(
                        f"Gemini error {response.status_code}: {last_error}"
                    )
        raise PhotoProviderError(f"Gemini request failed: {last_error}")

    def _extract_image(
        self, data: dict[str, Any], model: str
    ) -> tuple[bytes, str, str | None, str]:
        candidates = data.get("candidates") or []
        if not candidates:
            raise PhotoProviderError("Gemini returned no candidates")
        parts = (candidates[0].get("content") or {}).get("parts") or []
        text_chunks: list[str] = []
        for part in parts:
            if part.get("text"):
                text_chunks.append(str(part.get("text")))
            inline = part.get("inlineData") or part.get("inline_data")
            if inline and inline.get("data"):
                try:
                    return (
                        base64.b64decode(str(inline["data"])),
                        str(
                            inline.get("mimeType")
                            or inline.get("mime_type")
                            or "image/png"
                        ),
                        "\n".join(text_chunks).strip() or None,
                        model,
                    )
                except Exception as exc:
                    raise PhotoProviderError(
                        f"Gemini image decode failed: {exc}"
                    ) from exc
        raise PhotoProviderError("Gemini response did not contain an image")


@dataclass(frozen=True)
class StoredImage:
    storage_key: str
    mime_type: str
    width: int
    height: int
    file_size: int
    checksum: str
    exif_removed: bool


class PhotoStorageService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.root = Path(
            getattr(self.settings, "photo_storage_root", ".local/photo_studio")
        ).resolve()
        self.url_ttl_seconds = int(
            getattr(self.settings, "photo_signed_url_ttl_seconds", 900) or 900
        )

    async def store_upload(
        self,
        *,
        account_id: int,
        project_id: int,
        file: UploadFile,
        max_upload_mb: int = MAX_UPLOAD_MB,
        allowed_mime_types: list[str] | None = None,
    ) -> StoredImage:
        content = await file.read()
        safe_name = os.path.basename(file.filename or "upload")
        return self.store_bytes(
            account_id=account_id,
            project_id=project_id,
            original_file_name=safe_name,
            content=content,
            declared_mime=file.content_type,
            max_upload_mb=max_upload_mb,
            allowed_mime_types=allowed_mime_types,
        )

    def store_bytes(
        self,
        *,
        account_id: int,
        project_id: int,
        original_file_name: str | None,
        content: bytes,
        declared_mime: str | None,
        max_upload_mb: int = MAX_UPLOAD_MB,
        allowed_mime_types: list[str] | None = None,
    ) -> StoredImage:
        max_size = max(1, int(max_upload_mb or MAX_UPLOAD_MB)) * 1024 * 1024
        if not content:
            raise HTTPException(status_code=400, detail="Empty image upload")
        if len(content) > max_size:
            raise HTTPException(
                status_code=413, detail="Image upload exceeds configured size limit"
            )
        sniffed_mime, width, height = self._sniff_image(content)
        allowed = set(allowed_mime_types or ALLOWED_MIME_TYPES)
        if sniffed_mime not in allowed:
            raise HTTPException(status_code=400, detail="Unsupported image MIME type")
        if declared_mime and declared_mime.lower().split(";")[0].strip() not in allowed:
            raise HTTPException(
                status_code=400, detail="Declared MIME type is not allowed"
            )
        if (
            width < MIN_IMAGE_SIDE
            or height < MIN_IMAGE_SIDE
            or width > MAX_IMAGE_SIDE
            or height > MAX_IMAGE_SIDE
        ):
            raise HTTPException(
                status_code=400, detail="Image dimensions are outside allowed bounds"
            )
        sanitized, exif_removed = (
            self._strip_jpeg_exif(content)
            if sniffed_mime == "image/jpeg"
            else (content, False)
        )
        checksum = hashlib.sha256(sanitized).hexdigest()
        ext = self._extension_for_mime(sniffed_mime)
        storage_key = f"accounts/{account_id}/photo_studio/projects/{project_id}/{secrets.token_urlsafe(24)}.{ext}"
        path = self.path_for_key(storage_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(sanitized)
        return StoredImage(
            storage_key=storage_key,
            mime_type=sniffed_mime,
            width=width,
            height=height,
            file_size=len(sanitized),
            checksum=checksum,
            exif_removed=exif_removed,
        )

    def path_for_key(self, storage_key: str) -> Path:
        normalized = storage_key.strip().lstrip("/")
        if ".." in Path(normalized).parts:
            raise HTTPException(status_code=400, detail="Invalid storage key")
        return self.root / normalized

    def signed_url(
        self,
        *,
        asset_id: int,
        storage_key: str,
        account_id: int | None = None,
        now: datetime | None = None,
    ) -> PhotoDownloadUrlOut:
        issued_at = now or utcnow()
        expires_at = issued_at + timedelta(seconds=self.url_ttl_seconds)
        expires_ts = int(expires_at.timestamp())
        payload = f"{asset_id}:{storage_key}:{expires_ts}"
        signature = hmac.new(
            self._signing_secret(), payload.encode("utf-8"), hashlib.sha256
        ).hexdigest()
        token = base64.urlsafe_b64encode(
            f"{expires_ts}:{signature}".encode("utf-8")
        ).decode("ascii")
        account_query = f"account_id={account_id}&" if account_id is not None else ""
        return PhotoDownloadUrlOut(
            asset_id=asset_id,
            url=f"/api/v1/portal/photo/assets/{asset_id}/download?{account_query}token={token}",
            expires_at=expires_at,
        )

    def verify_download_token(
        self, *, asset_id: int, storage_key: str, token: str
    ) -> None:
        try:
            decoded = base64.urlsafe_b64decode(token.encode("ascii")).decode("utf-8")
            expires_raw, signature = decoded.split(":", 1)
            expires_ts = int(expires_raw)
        except Exception as exc:
            raise HTTPException(
                status_code=403, detail="Invalid download token"
            ) from exc
        if expires_ts < int(utcnow().timestamp()):
            raise HTTPException(status_code=403, detail="Expired download token")
        payload = f"{asset_id}:{storage_key}:{expires_ts}"
        expected = hmac.new(
            self._signing_secret(), payload.encode("utf-8"), hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise HTTPException(status_code=403, detail="Invalid download token")

    def _signing_secret(self) -> bytes:
        return str(
            self.settings.jwt_secret_key or Settings.DEFAULT_ACCESS_SECRET
        ).encode("utf-8")

    def _sniff_image(self, content: bytes) -> tuple[str, int, int]:
        if content.startswith(b"\x89PNG\r\n\x1a\n") and len(content) >= 24:
            return (
                "image/png",
                int.from_bytes(content[16:20], "big"),
                int.from_bytes(content[20:24], "big"),
            )
        if content.startswith(b"RIFF") and content[8:12] == b"WEBP":
            width, height = self._webp_dimensions(content)
            return "image/webp", width, height
        if content.startswith(b"\xff\xd8"):
            width, height = self._jpeg_dimensions(content)
            return "image/jpeg", width, height
        raise HTTPException(
            status_code=400, detail="Uploaded file is not a supported image"
        )

    def _jpeg_dimensions(self, content: bytes) -> tuple[int, int]:
        pos = 2
        while pos + 9 < len(content):
            if content[pos] != 0xFF:
                pos += 1
                continue
            marker = content[pos + 1]
            pos += 2
            if marker in {0xD8, 0xD9}:
                continue
            if pos + 2 > len(content):
                break
            length = int.from_bytes(content[pos : pos + 2], "big")
            if length < 2 or pos + length > len(content):
                break
            if marker in {
                0xC0,
                0xC1,
                0xC2,
                0xC3,
                0xC5,
                0xC6,
                0xC7,
                0xC9,
                0xCA,
                0xCB,
                0xCD,
                0xCE,
                0xCF,
            }:
                height = int.from_bytes(content[pos + 3 : pos + 5], "big")
                width = int.from_bytes(content[pos + 5 : pos + 7], "big")
                return width, height
            pos += length
        raise HTTPException(status_code=400, detail="Invalid JPEG image")

    def _webp_dimensions(self, content: bytes) -> tuple[int, int]:
        chunk = content[12:16]
        if chunk == b"VP8 " and len(content) >= 30:
            return int.from_bytes(content[26:28], "little") & 0x3FFF, int.from_bytes(
                content[28:30], "little"
            ) & 0x3FFF
        if chunk == b"VP8L" and len(content) >= 25:
            bits = int.from_bytes(content[21:25], "little")
            return (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
        if chunk == b"VP8X" and len(content) >= 30:
            return int.from_bytes(
                content[24:27] + b"\x00", "little"
            ) + 1, int.from_bytes(content[27:30] + b"\x00", "little") + 1
        raise HTTPException(status_code=400, detail="Invalid WEBP image")

    def _strip_jpeg_exif(self, content: bytes) -> tuple[bytes, bool]:
        output = bytearray(content[:2])
        pos = 2
        removed = False
        while pos + 4 <= len(content):
            if content[pos] != 0xFF:
                output.extend(content[pos:])
                break
            marker = content[pos + 1]
            if marker == 0xDA:
                output.extend(content[pos:])
                break
            if marker in {0xD8, 0xD9}:
                output.extend(content[pos : pos + 2])
                pos += 2
                continue
            length = int.from_bytes(content[pos + 2 : pos + 4], "big")
            segment = content[pos : pos + 2 + length]
            if marker == 0xE1 and content[pos + 4 : pos + 10] == b"Exif\x00\x00":
                removed = True
            else:
                output.extend(segment)
            pos += 2 + length
        return bytes(output), removed

    def _extension_for_mime(self, mime_type: str) -> str:
        return {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}[
            mime_type
        ]


class PhotoStudioService:
    def __init__(
        self,
        *,
        storage: PhotoStorageService | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.storage = storage or PhotoStorageService(self.settings)

    async def status(
        self, session: AsyncSession, *, account_id: int
    ) -> PhotoStudioStatusOut:
        projects_total = int(
            (
                await session.execute(
                    select(func.count())
                    .select_from(PhotoProject)
                    .where(PhotoProject.account_id == account_id)
                )
            ).scalar()
            or 0
        )
        projects_active = int(
            (
                await session.execute(
                    select(func.count())
                    .select_from(PhotoProject)
                    .where(
                        PhotoProject.account_id == account_id,
                        PhotoProject.status.in_(("draft", "in_progress", "review")),
                    )
                )
            ).scalar()
            or 0
        )
        versions_ready = int(
            (
                await session.execute(
                    select(func.count())
                    .select_from(PhotoVersion)
                    .where(
                        PhotoVersion.account_id == account_id,
                        PhotoVersion.status.in_(("ready", "preferred", "approved")),
                    )
                )
            ).scalar()
            or 0
        )
        last_activity_at = (
            await session.execute(
                select(func.max(PhotoProject.updated_at)).where(
                    PhotoProject.account_id == account_id
                )
            )
        ).scalar()
        settings = await self._settings_row(session, account_id=account_id)
        generation_status = (
            "ok" if self._generation_configured(settings) else "not_configured"
        )
        return PhotoStudioStatusOut(
            status="ok" if projects_total else "empty",
            generation={
                "status": generation_status,
                "provider": settings.default_provider,
                "message": None
                if generation_status == "ok"
                else "Провайдер генерации фото не настроен. Ручная загрузка и версии остаются доступными.",
            },
            projects_total=projects_total,
            projects_active=projects_active,
            versions_ready=versions_ready,
            last_activity_at=last_activity_at,
        )

    async def get_settings(
        self, session: AsyncSession, *, account_id: int
    ) -> PhotoSettingsOut:
        row = await self._settings_row(session, account_id=account_id)
        return self._settings_out(row)

    async def update_settings(
        self, session: AsyncSession, *, account_id: int, payload: PhotoSettingsUpdate
    ) -> PhotoSettingsOut:
        row = await self._settings_row(session, account_id=account_id)
        data = payload.model_dump(exclude_unset=True)
        for key, value in data.items():
            if key == "allowed_mime_types":
                row.allowed_mime_types_json = value
            elif (
                key in {"generation_enabled", "editing_enabled"}
                and value
                and not row.default_provider
            ):
                setattr(row, key, False)
            elif key != "external_apply_enabled":
                setattr(row, key, value)
        if not row.default_provider:
            row.generation_enabled = False
            row.editing_enabled = False
        row.external_apply_enabled = False
        await self._ensure_integration(session, account_id=account_id)
        await session.flush()
        return self._settings_out(row)

    async def list_projects(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        nm_id: int | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> PhotoProjectsPage:
        filters = [PhotoProject.account_id == account_id]
        if nm_id is not None:
            filters.append(PhotoProject.nm_id == nm_id)
        if status:
            filters.append(PhotoProject.status == status)
        total = int(
            (
                await session.execute(
                    select(func.count()).select_from(PhotoProject).where(*filters)
                )
            ).scalar()
            or 0
        )
        rows = list(
            (
                await session.execute(
                    select(PhotoProject)
                    .where(*filters)
                    .order_by(PhotoProject.updated_at.desc(), PhotoProject.id.desc())
                    .limit(limit)
                    .offset(offset)
                )
            ).scalars()
        )
        return PhotoProjectsPage(
            total=total,
            limit=limit,
            offset=offset,
            items=[
                await self._project_out(session, row, include_detail=False)
                for row in rows
            ],
        )

    async def create_project(
        self,
        session: AsyncSession,
        *,
        payload: PhotoProjectCreate,
        created_by_user_id: int | None,
    ) -> PhotoProjectOut:
        created_by_user_id = await self._existing_user_id(session, created_by_user_id)
        row = PhotoProject(
            account_id=payload.account_id,
            nm_id=payload.nm_id,
            sku_id=payload.sku_id,
            title=payload.title.strip() or "Photo Studio project",
            source_issue_id=payload.source_issue_id,
            source_action_key=payload.source_action_key,
            created_by_user_id=created_by_user_id,
        )
        session.add(row)
        await session.flush()
        await self._event(
            session,
            account_id=payload.account_id,
            project_id=row.id,
            event_type="project_created",
            actor_user_id=created_by_user_id,
            payload={"nm_id": payload.nm_id},
        )
        await self._ensure_integration(session, account_id=payload.account_id)
        return await self._project_out(session, row)

    async def get_project(
        self, session: AsyncSession, *, account_id: int, project_id: int
    ) -> PhotoProjectOut:
        row = await self._project_or_404(
            session, account_id=account_id, project_id=project_id
        )
        return await self._project_out(session, row)

    async def update_project(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        project_id: int,
        payload: PhotoProjectUpdate,
        actor_user_id: int | None,
    ) -> PhotoProjectOut:
        actor_user_id = await self._existing_user_id(session, actor_user_id)
        row = await self._project_or_404(
            session, account_id=account_id, project_id=project_id
        )
        data = payload.model_dump(exclude_unset=True)
        if payload.preferred_version_id is not None:
            await self._assert_version(
                session,
                account_id=account_id,
                project_id=project_id,
                version_id=payload.preferred_version_id,
            )
        for key, value in data.items():
            setattr(row, key, value)
        await self._event(
            session,
            account_id=account_id,
            project_id=project_id,
            event_type="project_updated",
            actor_user_id=actor_user_id,
            payload=data,
        )
        await session.flush()
        return await self._project_out(session, row)

    async def archive_project(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        project_id: int,
        actor_user_id: int | None,
    ) -> PhotoProjectOut:
        actor_user_id = await self._existing_user_id(session, actor_user_id)
        row = await self._project_or_404(
            session, account_id=account_id, project_id=project_id
        )
        row.status = "archived"
        row.archived_at = utcnow()
        await self._event(
            session,
            account_id=account_id,
            project_id=project_id,
            event_type="project_archived",
            actor_user_id=actor_user_id,
            payload={},
        )
        return await self._project_out(session, row)

    async def upload_asset(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        project_id: int,
        file: UploadFile,
        actor_user_id: int | None,
        asset_type: str = "user_upload",
    ) -> PhotoAssetOut:
        actor_user_id = await self._existing_user_id(session, actor_user_id)
        project = await self._project_or_404(
            session, account_id=account_id, project_id=project_id
        )
        settings = await self._settings_row(session, account_id=account_id)
        stored = await self.storage.store_upload(
            account_id=account_id,
            project_id=project_id,
            file=file,
            max_upload_mb=settings.max_upload_mb,
            allowed_mime_types=settings.allowed_mime_types_json
            or list(ALLOWED_MIME_TYPES),
        )
        row = PhotoAsset(
            account_id=account_id,
            nm_id=project.nm_id,
            project_id=project_id,
            asset_type=asset_type,
            source_type="manual_upload",
            storage_key=stored.storage_key,
            original_file_name=os.path.basename(file.filename or "upload"),
            mime_type=stored.mime_type,
            width=stored.width,
            height=stored.height,
            file_size=stored.file_size,
            checksum=stored.checksum,
            exif_removed=stored.exif_removed,
            created_by_user_id=actor_user_id,
            metadata_json={"storage": "local", "external_apply_enabled": False},
        )
        session.add(row)
        await session.flush()
        await self._event(
            session,
            account_id=account_id,
            project_id=project_id,
            event_type="asset_uploaded",
            actor_user_id=actor_user_id,
            payload={"asset_id": row.id},
        )
        return self._asset_out(row)

    async def import_wb_assets(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        project_id: int,
        actor_user_id: int | None,
    ) -> PhotoWBImportOut:
        actor_user_id = await self._existing_user_id(session, actor_user_id)
        project = await self._project_or_404(
            session, account_id=account_id, project_id=project_id
        )
        card = (
            await session.execute(
                select(WBProductCard).where(
                    WBProductCard.account_id == account_id,
                    WBProductCard.nm_id == project.nm_id,
                )
            )
        ).scalar_one_or_none()
        urls = self._photo_urls(card.photos if card is not None else None)
        if not urls:
            return PhotoWBImportOut(
                status="empty",
                imported=0,
                warnings=["No WB source images found for this product"],
            )
        imported: list[PhotoAsset] = []
        for url in urls:
            existing = (
                await session.execute(
                    select(PhotoAsset).where(
                        PhotoAsset.account_id == account_id,
                        PhotoAsset.project_id == project_id,
                        PhotoAsset.source_url == url,
                        PhotoAsset.deleted_at.is_(None),
                    )
                )
            ).scalar_one_or_none()
            if existing is not None:
                imported.append(existing)
                continue
            row = PhotoAsset(
                account_id=account_id,
                nm_id=project.nm_id,
                project_id=project_id,
                asset_type="wb_source",
                source_type="wb_sync",
                storage_key=None,
                original_file_name=None,
                mime_type="image/remote",
                width=None,
                height=None,
                file_size=0,
                checksum=hashlib.sha256(url.encode("utf-8")).hexdigest(),
                exif_removed=False,
                source_url=url,
                created_by_user_id=actor_user_id,
                metadata_json={"remote_only": True, "signed_download_available": False},
            )
            session.add(row)
            imported.append(row)
        await session.flush()
        await self._event(
            session,
            account_id=account_id,
            project_id=project_id,
            event_type="wb_assets_imported",
            actor_user_id=actor_user_id,
            payload={"imported": len(imported)},
        )
        return PhotoWBImportOut(
            imported=len(imported), assets=[self._asset_out(row) for row in imported]
        )

    async def list_assets(
        self, session: AsyncSession, *, account_id: int, project_id: int
    ) -> list[PhotoAssetOut]:
        await self._project_or_404(
            session, account_id=account_id, project_id=project_id
        )
        rows = list(
            (
                await session.execute(
                    select(PhotoAsset)
                    .where(
                        PhotoAsset.account_id == account_id,
                        PhotoAsset.project_id == project_id,
                        PhotoAsset.deleted_at.is_(None),
                    )
                    .order_by(PhotoAsset.created_at.desc(), PhotoAsset.id.desc())
                )
            ).scalars()
        )
        return [self._asset_out(row) for row in rows]

    async def delete_asset(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        asset_id: int,
        actor_user_id: int | None,
    ) -> PhotoAssetOut:
        actor_user_id = await self._existing_user_id(session, actor_user_id)
        row = await self._asset_or_404(
            session, account_id=account_id, asset_id=asset_id
        )
        row.deleted_at = utcnow()
        if row.project_id is not None:
            await self._event(
                session,
                account_id=account_id,
                project_id=row.project_id,
                event_type="asset_deleted",
                actor_user_id=actor_user_id,
                payload={"asset_id": row.id},
            )
        return self._asset_out(row)

    async def download_url(
        self, session: AsyncSession, *, account_id: int, asset_id: int
    ) -> PhotoDownloadUrlOut:
        row = await self._asset_or_404(
            session, account_id=account_id, asset_id=asset_id
        )
        if not row.storage_key:
            raise HTTPException(
                status_code=409,
                detail="Asset is remote-only and has no local signed download",
            )
        return self.storage.signed_url(
            asset_id=row.id, storage_key=row.storage_key, account_id=account_id
        )

    async def create_version(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        project_id: int,
        payload: PhotoVersionCreate,
        actor_user_id: int | None,
    ) -> PhotoVersionOut:
        actor_user_id = await self._existing_user_id(session, actor_user_id)
        project = await self._project_or_404(
            session, account_id=account_id, project_id=project_id
        )
        asset = await self._asset_or_404(
            session, account_id=account_id, asset_id=payload.asset_id
        )
        if asset.project_id != project_id:
            raise HTTPException(
                status_code=400, detail="Asset does not belong to this project"
            )
        if payload.parent_version_id is not None:
            await self._assert_version(
                session,
                account_id=account_id,
                project_id=project_id,
                version_id=payload.parent_version_id,
            )
        next_number = (
            int(
                (
                    await session.execute(
                        select(
                            func.coalesce(func.max(PhotoVersion.version_number), 0)
                        ).where(
                            PhotoVersion.account_id == account_id,
                            PhotoVersion.project_id == project_id,
                        )
                    )
                ).scalar()
                or 0
            )
            + 1
        )
        row = PhotoVersion(
            account_id=account_id,
            project_id=project_id,
            asset_id=payload.asset_id,
            version_number=next_number,
            parent_version_id=payload.parent_version_id,
            status="ready",
            label=payload.label,
            brief_text=payload.brief_text,
            change_summary=payload.change_summary,
            created_by_user_id=actor_user_id,
        )
        project.status = "review"
        session.add(row)
        await session.flush()
        await self._event(
            session,
            account_id=account_id,
            project_id=project_id,
            event_type="version_created",
            actor_user_id=actor_user_id,
            payload={"version_id": row.id, "asset_id": payload.asset_id},
        )
        return self._version_out(row)

    async def review_version(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        project_id: int,
        version_id: int,
        payload: PhotoVersionReview,
        actor_user_id: int | None,
    ) -> PhotoVersionOut:
        actor_user_id = await self._existing_user_id(session, actor_user_id)
        project = await self._project_or_404(
            session, account_id=account_id, project_id=project_id
        )
        version = await self._assert_version(
            session, account_id=account_id, project_id=project_id, version_id=version_id
        )
        now = utcnow()
        if payload.status == "preferred":
            version.status = "preferred"
            project.preferred_version_id = version.id
            event_type = "version_preferred"
        elif payload.status == "approved":
            version.status = "approved"
            version.approved_by_user_id = actor_user_id
            version.approved_at = now
            project.approved_version_id = version.id
            project.preferred_version_id = version.id
            project.status = "approved"
            event_type = "version_approved"
            await self._result_event(
                session,
                account_id=account_id,
                project=project,
                version=version,
                actor_user_id=actor_user_id,
            )
        else:
            version.status = "rejected"
            version.rejected_at = now
            version.rejection_reason = payload.reason
            project.status = "rejected"
            event_type = "version_rejected"
        await self._event(
            session,
            account_id=account_id,
            project_id=project_id,
            event_type=event_type,
            actor_user_id=actor_user_id,
            payload={"version_id": version.id, "reason": payload.reason},
        )
        return self._version_out(version)

    async def apply_version_to_wb(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        project_id: int,
        version_id: int,
        photo_number: int = 1,
        actor_user_id: int | None,
    ) -> dict[str, Any]:
        actor_user_id = await self._existing_user_id(session, actor_user_id)
        project = await self._project_or_404(
            session, account_id=account_id, project_id=project_id
        )
        version = await self._assert_version(
            session, account_id=account_id, project_id=project_id, version_id=version_id
        )
        asset = await self._asset_or_404(
            session, account_id=account_id, asset_id=version.asset_id
        )
        slot = max(1, min(int(photo_number or 1), 30))
        card = (
            await session.execute(
                select(WBProductCard).where(
                    WBProductCard.account_id == account_id,
                    WBProductCard.nm_id == project.nm_id,
                )
            )
        ).scalar_one_or_none()
        before = self._photo_urls(card.photos if card is not None else None)
        proposed = list(before)
        while len(proposed) < slot:
            proposed.append("")
        preview_url = self._preview_url(asset)
        if preview_url:
            proposed[slot - 1] = preview_url
        proposed = [item for item in proposed if item]
        await self._event(
            session,
            account_id=account_id,
            project_id=project_id,
            event_type="version_apply_wb_blocked_draft_only",
            actor_user_id=actor_user_id,
            payload={
                "version_id": version.id,
                "asset_id": asset.id,
                "photo_number": slot,
                "before_order": before,
                "proposed_order": proposed,
                "marketplace_write_performed": False,
                "requires_preview_diff": True,
                "requires_explicit_confirm": True,
                "requires_audit_log": True,
                "result_status": "blocked",
            },
        )
        return {
            "status": "blocked",
            "result_status": "blocked",
            "project_id": project_id,
            "version_id": version.id,
            "photo_number": slot,
            "external_apply_enabled": False,
            "marketplace_write_performed": False,
            "requires_permission_check": True,
            "requires_preview_diff": True,
            "requires_explicit_confirm": True,
            "requires_audit_log": True,
            "message": "Photo Studio is draft-only. WB media publish is disabled until preview, confirm, audit, and verification are implemented.",
            "diff": {
                "before_order": before,
                "proposed_order": proposed,
                "changed_slot": slot,
            },
            "audit": {
                "event_type": "version_apply_wb_blocked_draft_only",
                "actor_user_id": actor_user_id,
            },
        }
        token = await self._content_token(session, account_id=account_id)
        if not token:
            raise HTTPException(
                status_code=403,
                detail="Не настроен WB Content API токен. Добавьте токен с доступом к карточкам, чтобы отправлять фото в Wildberries.",
            )

        payload, content_type, filename = await self._asset_bytes_for_wb(asset)
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(
                "https://content-api.wildberries.ru/content/v3/media/file",
                headers={
                    "Authorization": token,
                    "Accept": "application/json",
                    "X-Nm-Id": str(int(project.nm_id)),
                    "X-Photo-Number": str(slot),
                },
                files={
                    "uploadfile": (
                        filename,
                        payload,
                        content_type or "application/octet-stream",
                    )
                },
            )
        if response.status_code >= 400:
            raise HTTPException(
                status_code=502,
                detail=f"Wildberries не принял фото: {response.text[:500]}",
            )
        try:
            wb_payload = response.json() if response.text else {}
        except Exception:
            wb_payload = {}
        if isinstance(wb_payload, dict) and wb_payload.get("error"):
            raise HTTPException(
                status_code=502,
                detail=wb_payload.get("errorText") or "Wildberries не принял фото",
            )

        card = (
            await session.execute(
                select(WBProductCard).where(
                    WBProductCard.account_id == account_id,
                    WBProductCard.nm_id == project.nm_id,
                )
            )
        ).scalar_one_or_none()
        photos = await self._fetch_wb_photo_urls(token=token, nm_id=int(project.nm_id))
        if not photos:
            preview_url = self._preview_url(asset)
            photos = self._photo_urls(card.photos if card is not None else None)
            while len(photos) < slot:
                photos.append("")
            if preview_url:
                photos[slot - 1] = preview_url
            photos = [item for item in photos if item]
        if card is not None:
            card.photos = photos

        version.status = "approved"
        version.approved_by_user_id = actor_user_id
        version.approved_at = version.approved_at or utcnow()
        project.status = "approved"
        project.approved_version_id = version.id
        project.preferred_version_id = version.id
        await self._event(
            session,
            account_id=account_id,
            project_id=project_id,
            event_type="version_applied_to_wb",
            actor_user_id=actor_user_id,
            payload={
                "version_id": version.id,
                "asset_id": asset.id,
                "photo_number": slot,
                "wb_response": wb_payload,
            },
        )
        return {
            "status": "ok",
            "project_id": project_id,
            "version_id": version.id,
            "photo_number": slot,
            "photos": photos,
            "wb_response": wb_payload,
        }

    async def save_project_card_photos_to_wb(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        project_id: int,
        photos: list[str],
        actor_user_id: int | None,
    ) -> dict[str, Any]:
        actor_user_id = await self._existing_user_id(session, actor_user_id)
        project = await self._project_or_404(
            session, account_id=account_id, project_id=project_id
        )
        desired: list[str] = []
        seen: set[str] = set()
        for raw in photos or []:
            url = str(raw or "").strip()
            if not url:
                continue
            normalized = self._strip_url_query(url)
            if normalized in seen:
                raise HTTPException(
                    status_code=400, detail="Duplicate photo URLs are not allowed"
                )
            seen.add(normalized)
            desired.append(url)
        if not desired:
            raise HTTPException(
                status_code=400, detail="At least one photo URL is required"
            )
        if len(desired) > 30:
            raise HTTPException(
                status_code=400, detail="WB allows up to 30 product photos"
            )
        card = (
            await session.execute(
                select(WBProductCard).where(
                    WBProductCard.account_id == account_id,
                    WBProductCard.nm_id == project.nm_id,
                )
            )
        ).scalar_one_or_none()
        before = self._photo_urls(card.photos if card is not None else None)
        verification = self._media_verification(
            requested_order=desired, actual_order=before
        )
        await self._event(
            session,
            account_id=account_id,
            project_id=project_id,
            event_type="card_photos_save_wb_blocked_draft_only",
            actor_user_id=actor_user_id,
            payload={
                "before_order": before,
                "requested_order": desired,
                "marketplace_write_performed": False,
                "requires_preview_diff": True,
                "requires_explicit_confirm": True,
                "requires_audit_log": True,
                "result_status": "blocked",
            },
        )
        return {
            "status": "blocked",
            "result_status": "blocked",
            "project_id": project_id,
            "nm_id": int(project.nm_id),
            "external_apply_enabled": False,
            "marketplace_write_performed": False,
            "requires_permission_check": True,
            "requires_preview_diff": True,
            "requires_explicit_confirm": True,
            "requires_audit_log": True,
            "message": "Photo Studio is draft-only. WB media save is disabled until preview, confirm, audit, and verification are implemented.",
            "diff": {
                "before_order": before,
                "requested_order": desired,
                "missing_urls": verification["missing_urls"],
                "unexpected_urls": verification["unexpected_urls"],
            },
            "audit": {
                "event_type": "card_photos_save_wb_blocked_draft_only",
                "actor_user_id": actor_user_id,
            },
        }
        token = await self._content_token(session, account_id=account_id)
        if not token:
            raise HTTPException(
                status_code=403,
                detail="Не настроен WB Content API токен. Добавьте токен с доступом к карточкам, чтобы сохранять порядок фото.",
            )

        desired: list[str] = []
        seen: set[str] = set()
        for raw in photos or []:
            url = str(raw or "").strip()
            if not url:
                continue
            normalized = self._strip_url_query(url)
            if normalized in seen:
                raise HTTPException(
                    status_code=400, detail="Duplicate photo URLs are not allowed"
                )
            seen.add(normalized)
            desired.append(url)
        if not desired:
            raise HTTPException(
                status_code=400, detail="At least one photo URL is required"
            )
        if len(desired) > 30:
            raise HTTPException(
                status_code=400, detail="WB allows up to 30 product photos"
            )

        before = await self._fetch_wb_photo_urls(token=token, nm_id=int(project.nm_id))
        payload = {"nmId": int(project.nm_id), "data": desired}
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                "https://content-api.wildberries.ru/content/v3/media/save",
                headers={
                    "Authorization": token,
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
        if response.status_code >= 400:
            raise HTTPException(
                status_code=502, detail=f"WB media save failed: {response.text[:500]}"
            )
        try:
            wb_payload = response.json() if response.text else {}
        except Exception:
            wb_payload = {}
        if isinstance(wb_payload, dict) and wb_payload.get("error"):
            raise HTTPException(
                status_code=502,
                detail=wb_payload.get("errorText") or "WB media save failed",
            )

        actual: list[str] = []
        stable: list[str] | None = None
        stable_hits = 0
        for _ in range(12):
            await asyncio.sleep(1.5)
            current = await self._fetch_wb_photo_urls(
                token=token, nm_id=int(project.nm_id)
            )
            if current:
                actual = current
            clean = [self._strip_url_query(url) for url in current]
            if len(clean) == len(desired):
                if clean == stable:
                    stable_hits += 1
                else:
                    stable = clean
                    stable_hits = 1
                if stable_hits >= 2:
                    actual = current
                    break

        verification = self._media_verification(
            requested_order=desired, actual_order=actual
        )
        card = (
            await session.execute(
                select(WBProductCard).where(
                    WBProductCard.account_id == account_id,
                    WBProductCard.nm_id == project.nm_id,
                )
            )
        ).scalar_one_or_none()
        final_photos = actual or desired
        if card is not None:
            card.photos = final_photos
            if hasattr(card, "photos_count"):
                card.photos_count = len(final_photos)

        await self._event(
            session,
            account_id=account_id,
            project_id=project_id,
            event_type="card_photos_saved_to_wb",
            actor_user_id=actor_user_id,
            payload={
                "before_order": before,
                "requested_order": desired,
                "actual_order": final_photos,
                "matched": verification["matched"],
                "wb_response": wb_payload,
            },
        )
        return {
            "status": "ok",
            "project_id": project_id,
            "nm_id": int(project.nm_id),
            "photos": final_photos,
            "before_order": before,
            "requested_order": desired,
            "actual_order": actual,
            "matched": verification["matched"],
            "missing_urls": verification["missing_urls"],
            "unexpected_urls": verification["unexpected_urls"],
            "verification": verification,
            "wb_response": wb_payload,
        }

    async def add_message(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        project_id: int,
        payload: PhotoProjectMessageCreate,
        actor_user_id: int | None,
    ) -> PhotoProjectMessageOut:
        actor_user_id = await self._existing_user_id(session, actor_user_id)
        await self._project_or_404(
            session, account_id=account_id, project_id=project_id
        )
        await self._assert_project_assets(
            session,
            account_id=account_id,
            project_id=project_id,
            asset_ids=payload.linked_asset_ids,
        )
        row = PhotoProjectMessage(
            account_id=account_id,
            project_id=project_id,
            author_user_id=actor_user_id,
            author_type="user" if actor_user_id is not None else "system",
            message_type=payload.message_type,
            text=payload.text,
            linked_asset_ids_json=payload.linked_asset_ids,
            created_at=utcnow(),
        )
        session.add(row)
        await session.flush()
        await self._event(
            session,
            account_id=account_id,
            project_id=project_id,
            event_type="message_added",
            actor_user_id=actor_user_id,
            payload={"message_id": row.id},
        )
        return self._message_out(row)

    async def create_job(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        project_id: int,
        payload: PhotoJobCreate,
        actor_user_id: int | None,
    ) -> PhotoJobOut:
        actor_user_id = await self._existing_user_id(session, actor_user_id)
        await self._project_or_404(
            session, account_id=account_id, project_id=project_id
        )
        await self._assert_project_assets(
            session,
            account_id=account_id,
            project_id=project_id,
            asset_ids=payload.input_asset_ids,
        )
        settings = await self._settings_row(session, account_id=account_id)
        configured = self._generation_configured(settings)
        row = PhotoGenerationJob(
            account_id=account_id,
            project_id=project_id,
            input_asset_ids_json=payload.input_asset_ids,
            job_type=payload.job_type,
            provider=payload.provider or settings.default_provider,
            model=payload.model or settings.default_model,
            status="queued" if configured else "not_configured",
            sanitized_prompt=self._sanitize_prompt(payload.prompt or ""),
            settings_snapshot_json={
                "provider_mode": settings.provider_mode,
                "generation_enabled": settings.generation_enabled,
                "editing_enabled": settings.editing_enabled,
                "external_apply_enabled": False,
            },
            requested_by_user_id=actor_user_id,
            error_code=None if configured else "provider_not_configured",
            error_message=None
            if configured
            else "Провайдер генерации фото не настроен. Можно загрузить фото вручную или проверить ключ Gemini.",
        )
        session.add(row)
        await session.flush()
        await self._event(
            session,
            account_id=account_id,
            project_id=project_id,
            event_type="generation_started"
            if configured
            else "generation_not_configured",
            actor_user_id=actor_user_id,
            payload={"job_id": row.id},
        )
        return self._job_out(row)

    async def get_job(
        self, session: AsyncSession, *, account_id: int, job_id: int
    ) -> PhotoJobOut:
        row = await self._job_or_404(session, account_id=account_id, job_id=job_id)
        return self._job_out(row)

    async def list_jobs(
        self, session: AsyncSession, *, account_id: int, limit: int, offset: int
    ) -> dict[str, Any]:
        total = int(
            (
                await session.execute(
                    select(func.count())
                    .select_from(PhotoGenerationJob)
                    .where(PhotoGenerationJob.account_id == account_id)
                )
            ).scalar()
            or 0
        )
        rows = list(
            (
                await session.execute(
                    select(PhotoGenerationJob)
                    .where(PhotoGenerationJob.account_id == account_id)
                    .order_by(
                        PhotoGenerationJob.created_at.desc(),
                        PhotoGenerationJob.id.desc(),
                    )
                    .limit(limit)
                    .offset(offset)
                )
            ).scalars()
        )
        return {
            "status": "ok",
            "total": total,
            "limit": limit,
            "offset": offset,
            "items": [self._job_out(row) for row in rows],
        }

    async def cancel_job(
        self, session: AsyncSession, *, account_id: int, job_id: int
    ) -> PhotoJobOut:
        row = await self._job_or_404(session, account_id=account_id, job_id=job_id)
        if row.status in {"completed", "failed", "cancelled", "not_configured"}:
            return self._job_out(row)
        row.status = "cancelled"
        row.finished_at = utcnow()
        return self._job_out(row)

    async def retry_job(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        job_id: int,
        actor_user_id: int | None,
    ) -> PhotoJobOut:
        actor_user_id = await self._existing_user_id(session, actor_user_id)
        row = await self._job_or_404(session, account_id=account_id, job_id=job_id)
        if row.status not in {"failed", "not_configured", "cancelled"}:
            raise HTTPException(
                status_code=409,
                detail="Повторить можно только задачу с ошибкой, отменённую задачу или задачу без настроенного провайдера",
            )
        settings = await self._settings_row(session, account_id=account_id)
        configured = self._generation_configured(settings)
        row.attempt += 1
        row.status = "queued" if configured else "not_configured"
        row.requested_by_user_id = actor_user_id
        row.error_code = None if configured else "provider_not_configured"
        row.error_message = (
            None
            if configured
            else "Провайдер генерации фото не настроен. Можно загрузить фото вручную или проверить ключ Gemini."
        )
        return self._job_out(row)

    async def process_queued_jobs(
        self, session: AsyncSession, *, max_jobs: int = 5
    ) -> int:
        jobs = list(
            (
                await session.execute(
                    select(PhotoGenerationJob)
                    .where(PhotoGenerationJob.status.in_(("queued", "running")))
                    .order_by(PhotoGenerationJob.id.asc())
                    .limit(max(1, int(max_jobs)))
                )
            ).scalars()
        )
        processed = 0
        for job in jobs:
            settings = await self._settings_row(session, account_id=job.account_id)
            configured = self._generation_configured(settings) and bool(job.provider)
            job.started_at = job.started_at or utcnow()
            job.heartbeat_at = utcnow()
            job.status = "running"
            job.progress_percent = max(int(job.progress_percent or 0), 5)
            await session.flush()
            if not configured:
                job.status = "not_configured"
                job.finished_at = utcnow()
                job.error_code = "provider_not_configured"
                job.error_message = "Провайдер генерации фото не настроен. Ручная загрузка и версии остаются доступными."
                await self._event(
                    session,
                    account_id=job.account_id,
                    project_id=job.project_id,
                    event_type="generation_not_configured",
                    actor_user_id=job.requested_by_user_id,
                    payload={"job_id": job.id, "error_code": job.error_code},
                )
            else:
                try:
                    await self._process_generation_job(
                        session, job=job, settings=settings
                    )
                except Exception as exc:
                    job.status = "failed"
                    job.finished_at = utcnow()
                    job.progress_percent = 100
                    job.error_code = "provider_failed"
                    job.error_message = _photo_provider_message(exc)
                    await self._event(
                        session,
                        account_id=job.account_id,
                        project_id=job.project_id,
                        event_type="generation_failed",
                        actor_user_id=job.requested_by_user_id,
                        payload={
                            "job_id": job.id,
                            "error_code": job.error_code,
                            "message": job.error_message,
                        },
                    )
            processed += 1
        await session.flush()
        return processed

    async def _process_generation_job(
        self, session: AsyncSession, *, job: PhotoGenerationJob, settings: PhotoSettings
    ) -> None:
        project = await self._project_or_404(
            session, account_id=job.account_id, project_id=job.project_id
        )
        requested_by_user_id = await self._existing_user_id(
            session, job.requested_by_user_id
        )
        input_assets = await self._assets_for_job(
            session,
            account_id=job.account_id,
            project_id=job.project_id,
            asset_ids=job.input_asset_ids_json or [],
        )
        images = await self._image_bytes_for_assets(input_assets)
        if job.job_type != "generate" and not images:
            raise PhotoProviderError("No source image is available for this edit job")
        prompt = self._build_generation_prompt(job=job, project=project)
        provider = GeminiImageProvider(self.settings)
        (
            image_bytes,
            mime_type,
            provider_text,
            model_used,
        ) = await provider.edit_or_generate(
            prompt=prompt,
            images=images,
            model=job.model or settings.default_model,
            aspect_ratio=settings.default_aspect_ratio or "3:4",
        )
        stored = self.storage.store_bytes(
            account_id=job.account_id,
            project_id=job.project_id,
            original_file_name=f"generated-job-{job.id}",
            content=image_bytes,
            declared_mime=mime_type,
            max_upload_mb=max(
                int(settings.max_upload_mb or MAX_UPLOAD_MB), MAX_UPLOAD_MB
            ),
            allowed_mime_types=settings.allowed_mime_types_json
            or list(ALLOWED_MIME_TYPES),
        )
        source_asset_id = input_assets[0].id if input_assets else None
        asset = PhotoAsset(
            account_id=job.account_id,
            nm_id=project.nm_id,
            project_id=job.project_id,
            asset_type="generated",
            source_type="ai",
            storage_key=stored.storage_key,
            original_file_name=f"generated-job-{job.id}.{self.storage._extension_for_mime(stored.mime_type)}",
            mime_type=stored.mime_type,
            width=stored.width,
            height=stored.height,
            file_size=stored.file_size,
            checksum=stored.checksum,
            exif_removed=stored.exif_removed,
            source_asset_id=source_asset_id,
            created_by_user_id=requested_by_user_id,
            metadata_json={
                "provider": job.provider,
                "model": model_used,
                "job_id": job.id,
                "job_type": job.job_type,
                "prompt": job.sanitized_prompt,
                "provider_text": provider_text,
                "source": "checker_gemini_adapter",
            },
        )
        session.add(asset)
        await session.flush()
        next_number = (
            int(
                (
                    await session.execute(
                        select(
                            func.coalesce(func.max(PhotoVersion.version_number), 0)
                        ).where(
                            PhotoVersion.account_id == job.account_id,
                            PhotoVersion.project_id == job.project_id,
                        )
                    )
                ).scalar()
                or 0
            )
            + 1
        )
        version = PhotoVersion(
            account_id=job.account_id,
            project_id=job.project_id,
            asset_id=asset.id,
            version_number=next_number,
            status="ready",
            label=f"AI {job.job_type}",
            brief_text=job.sanitized_prompt,
            change_summary=provider_text or f"Generated via {model_used}",
            generation_job_id=job.id,
            created_by_user_id=requested_by_user_id,
        )
        session.add(version)
        await session.flush()
        project.status = "review"
        project.preferred_version_id = version.id
        job.status = "completed"
        job.progress_percent = 100
        job.finished_at = utcnow()
        job.output_asset_ids_json = [asset.id]
        job.model = model_used
        await self._event(
            session,
            account_id=job.account_id,
            project_id=job.project_id,
            event_type="generation_completed",
            actor_user_id=requested_by_user_id,
            payload={
                "job_id": job.id,
                "asset_id": asset.id,
                "version_id": version.id,
                "model": model_used,
            },
        )

    async def _assets_for_job(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        project_id: int,
        asset_ids: list[int],
    ) -> list[PhotoAsset]:
        unique_ids = sorted({int(asset_id) for asset_id in asset_ids if asset_id})
        if not unique_ids:
            return []
        return list(
            (
                await session.execute(
                    select(PhotoAsset).where(
                        PhotoAsset.account_id == account_id,
                        PhotoAsset.project_id == project_id,
                        PhotoAsset.id.in_(unique_ids),
                        PhotoAsset.deleted_at.is_(None),
                    )
                )
            ).scalars()
        )

    async def _image_bytes_for_assets(
        self, assets: list[PhotoAsset]
    ) -> list[tuple[bytes, str]]:
        result: list[tuple[bytes, str]] = []
        for asset in assets[:4]:
            if asset.storage_key:
                path = self.storage.path_for_key(asset.storage_key)
                if path.exists() and path.is_file():
                    result.append((path.read_bytes(), asset.mime_type or "image/png"))
                    continue
            if asset.source_url:
                result.append((await self._download_image(asset.source_url)))
        return result

    async def _download_image(self, url: str) -> tuple[bytes, str]:
        parsed = urlparse(url.strip())
        if parsed.scheme not in {"http", "https"}:
            raise PhotoProviderError("Unsupported image URL scheme")
        host = parsed.hostname or ""
        if self._is_private_host(host):
            raise PhotoProviderError("Private image URL hosts are not allowed")
        timeout = min(float(self.settings.gemini_image_timeout_seconds or 60.0), 60.0)
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(
                timeout, connect=5.0, read=timeout, write=10.0, pool=10.0
            ),
            follow_redirects=True,
        ) as client:
            response = await client.get(url)
            response.raise_for_status()
            content_type = (
                (response.headers.get("content-type") or "image/png")
                .split(";", 1)[0]
                .strip()
                .lower()
            )
            if not content_type.startswith("image/"):
                raise PhotoProviderError("Source URL did not return an image")
            content = response.content
            if len(content) > MAX_REMOTE_IMAGE_BYTES:
                raise PhotoProviderError("Source image is too large")
            return content, content_type

    def _is_private_host(self, host: str) -> bool:
        lowered = (host or "").lower()
        if lowered in {"localhost", "127.0.0.1", "::1"}:
            return True
        try:
            ip = ipaddress.ip_address(lowered)
        except ValueError:
            return False
        return (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
        )

    def _build_generation_prompt(
        self, *, job: PhotoGenerationJob, project: PhotoProject
    ) -> str:
        operation_hint = {
            "background_replace": "Задача: заменить фон, сохранив сам товар, форму, цвет, фактуру, пропорции и безопасную композицию для маркетплейса.",
            "remove_background": "Задача: удалить или аккуратно очистить фон, сохранив товар без изменений.",
            "enhance": "Задача: улучшить свет, резкость, чистоту и товарную подачу без изменения самого товара.",
            "variant": "Задача: создать новый вариант фото для карточки, сохранив реальный товар без изменений.",
            "edit": "Задача: выполнить правку пользователя, сохранив реальный товар без изменений.",
            "generate": "Задача: создать готовое фото товара для карточки маркетплейса.",
        }.get(
            job.job_type,
            "Задача: создать готовое фото товара для карточки маркетплейса.",
        )
        user_prompt = (job.sanitized_prompt or "").strip()
        project_context = []
        if project.nm_id:
            project_context.append(f"nm_id товара: {project.nm_id}.")
        if project.title:
            project_context.append(f"Название товара: {project.title}.")
        vendor_code = getattr(project, "vendor_code", None)
        if vendor_code:
            project_context.append(f"Артикул продавца: {vendor_code}.")
        return "\n".join(
            part
            for part in [
                operation_hint,
                "\n".join(project_context),
                f"Запрос пользователя: {user_prompt}" if user_prompt else "",
                "Правила качества:",
                "- Делайте только то, что указано в задаче; остальное оставьте без изменений.",
                "- Сохраняйте реальный товар: форму, посадку, цвет, материал, фактуру, фурнитуру и пропорции.",
                "- Не добавляйте лишние товары, фейковые надписи, логотипы, водяные знаки, ценники и несуществующие элементы.",
                "- Если есть исходное фото, используйте его как главный источник правды по товару.",
                "- Для Wildberries нужна чистая e-commerce подача: ровный свет, реалистичные тени, аккуратный кадр, без перегруженного фона.",
                "- Если задача про объединение изображений, сохраняйте идентичность целевого товара и не меняйте фон/ракурс без явной просьбы.",
            ]
            if part
        )[:4000]

    def _generation_configured(self, settings: PhotoSettings) -> bool:
        provider = (settings.default_provider or "").strip().lower()
        if not settings.generation_enabled or not provider:
            return False
        if provider == "gemini":
            return bool((self.settings.gemini_api_key or "").strip())
        return True

    async def _settings_row(
        self, session: AsyncSession, *, account_id: int
    ) -> PhotoSettings:
        row = (
            await session.execute(
                select(PhotoSettings).where(PhotoSettings.account_id == account_id)
            )
        ).scalar_one_or_none()
        has_gemini = bool((self.settings.gemini_api_key or "").strip())
        if row is None:
            row = PhotoSettings(
                account_id=account_id,
                provider_mode="ai_optional" if has_gemini else "manual",
                default_provider="gemini" if has_gemini else None,
                default_model=self.settings.gemini_image_model if has_gemini else None,
                default_aspect_ratio="3:4",
                generation_enabled=has_gemini,
                editing_enabled=has_gemini,
                allowed_mime_types_json=list(ALLOWED_MIME_TYPES),
                external_apply_enabled=False,
            )
            session.add(row)
            await session.flush()
        elif has_gemini and not row.default_provider:
            row.provider_mode = "ai_optional"
            row.default_provider = "gemini"
            row.default_model = row.default_model or self.settings.gemini_image_model
            row.default_aspect_ratio = row.default_aspect_ratio or "3:4"
            row.generation_enabled = True
            row.editing_enabled = True
        return row

    async def _ensure_integration(
        self, session: AsyncSession, *, account_id: int
    ) -> None:
        row = (
            await session.execute(
                select(PortalIntegration).where(
                    PortalIntegration.account_id == account_id,
                    PortalIntegration.module == "photo",
                )
            )
        ).scalar_one_or_none()
        status = "ok"
        if row is None:
            row = PortalIntegration(
                account_id=account_id,
                module="photo",
                enabled=True,
                mode="local",
                status=status,
                metadata_json={"local_module": True},
            )
            session.add(row)
        else:
            row.enabled = True
            row.mode = "local"
            row.status = status
            row.metadata_json = {**(row.metadata_json or {}), "local_module": True}

    async def _project_or_404(
        self, session: AsyncSession, *, account_id: int, project_id: int
    ) -> PhotoProject:
        row = await session.get(PhotoProject, project_id)
        if row is None or row.account_id != account_id:
            raise HTTPException(status_code=404, detail="Photo project not found")
        return row

    async def _asset_or_404(
        self, session: AsyncSession, *, account_id: int, asset_id: int
    ) -> PhotoAsset:
        row = await session.get(PhotoAsset, asset_id)
        if row is None or row.account_id != account_id or row.deleted_at is not None:
            raise HTTPException(status_code=404, detail="Photo asset not found")
        return row

    async def _job_or_404(
        self, session: AsyncSession, *, account_id: int, job_id: int
    ) -> PhotoGenerationJob:
        row = await session.get(PhotoGenerationJob, job_id)
        if row is None or row.account_id != account_id:
            raise HTTPException(status_code=404, detail="Photo job not found")
        return row

    async def _assert_version(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        project_id: int,
        version_id: int,
    ) -> PhotoVersion:
        row = await session.get(PhotoVersion, version_id)
        if row is None or row.account_id != account_id or row.project_id != project_id:
            raise HTTPException(status_code=404, detail="Photo version not found")
        return row

    async def _assert_project_assets(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        project_id: int,
        asset_ids: list[int],
    ) -> None:
        unique_ids = sorted({int(asset_id) for asset_id in asset_ids if asset_id})
        if not unique_ids:
            return
        found = set(
            (
                await session.execute(
                    select(PhotoAsset.id).where(
                        PhotoAsset.account_id == account_id,
                        PhotoAsset.project_id == project_id,
                        PhotoAsset.id.in_(unique_ids),
                        PhotoAsset.deleted_at.is_(None),
                    )
                )
            ).scalars()
        )
        missing = [asset_id for asset_id in unique_ids if asset_id not in found]
        if missing:
            raise HTTPException(
                status_code=400,
                detail="One or more photo assets do not belong to this project",
            )

    async def _project_out(
        self, session: AsyncSession, row: PhotoProject, *, include_detail: bool = True
    ) -> PhotoProjectOut:
        assets: list[PhotoAssetOut] = []
        versions: list[PhotoVersionOut] = []
        jobs: list[PhotoJobOut] = []
        messages: list[PhotoProjectMessageOut] = []
        events: list[PhotoProjectEventOut] = []
        card = (
            await session.execute(
                select(WBProductCard).where(
                    WBProductCard.account_id == row.account_id,
                    WBProductCard.nm_id == row.nm_id,
                )
            )
        ).scalar_one_or_none()
        card_photos = self._photo_urls(card.photos if card is not None else None)
        if not card_photos and card is not None:
            card_photos = self._photo_urls(card.payload)
        card_title = (card.title if card is not None else None) or row.title
        card_vendor_code = card.vendor_code if card is not None else None
        if include_detail:
            asset_rows = list(
                (
                    await session.execute(
                        select(PhotoAsset)
                        .where(
                            PhotoAsset.project_id == row.id,
                            PhotoAsset.deleted_at.is_(None),
                        )
                        .order_by(PhotoAsset.created_at.desc(), PhotoAsset.id.desc())
                    )
                ).scalars()
            )
            assets = [self._asset_out(item) for item in asset_rows]
            asset_by_id = {item.id: item for item in asset_rows}
            versions = [
                self._version_out(item, asset_by_id.get(item.asset_id))
                for item in (
                    await session.execute(
                        select(PhotoVersion)
                        .where(PhotoVersion.project_id == row.id)
                        .order_by(
                            PhotoVersion.version_number.desc(), PhotoVersion.id.desc()
                        )
                    )
                ).scalars()
            ]
            jobs = [
                self._job_out(item)
                for item in (
                    await session.execute(
                        select(PhotoGenerationJob)
                        .where(PhotoGenerationJob.project_id == row.id)
                        .order_by(
                            PhotoGenerationJob.created_at.desc(),
                            PhotoGenerationJob.id.desc(),
                        )
                        .limit(20)
                    )
                ).scalars()
            ]
            messages = [
                self._message_out(item)
                for item in (
                    await session.execute(
                        select(PhotoProjectMessage)
                        .where(PhotoProjectMessage.project_id == row.id)
                        .order_by(
                            PhotoProjectMessage.created_at.desc(),
                            PhotoProjectMessage.id.desc(),
                        )
                        .limit(100)
                    )
                ).scalars()
            ]
            events = [
                self._event_out(item)
                for item in (
                    await session.execute(
                        select(PhotoProjectEvent)
                        .where(PhotoProjectEvent.project_id == row.id)
                        .order_by(
                            PhotoProjectEvent.created_at.desc(),
                            PhotoProjectEvent.id.desc(),
                        )
                        .limit(100)
                    )
                ).scalars()
            ]
        return PhotoProjectOut(
            id=row.id,
            account_id=row.account_id,
            nm_id=row.nm_id,
            sku_id=row.sku_id,
            title=row.title,
            product_name=card_title,
            vendor_code=card_vendor_code,
            thumbnail=card_photos[0] if card_photos else None,
            preferred_thumbnail=None,
            approved_thumbnail=None,
            photos=card_photos,
            status=row.status,
            source_issue_id=row.source_issue_id,
            source_action_key=row.source_action_key,
            created_by_user_id=row.created_by_user_id,
            preferred_version_id=row.preferred_version_id,
            approved_version_id=row.approved_version_id,
            created_at=row.created_at,
            updated_at=row.updated_at,
            archived_at=row.archived_at,
            assets=assets,
            versions=versions,
            jobs=jobs,
            messages=messages,
            events=events,
        )

    def _settings_out(self, row: PhotoSettings) -> PhotoSettingsOut:
        return PhotoSettingsOut(
            account_id=row.account_id,
            provider_mode=row.provider_mode,
            default_provider=row.default_provider,
            default_model=row.default_model,
            default_aspect_ratio=row.default_aspect_ratio,
            default_output_format=row.default_output_format,
            max_upload_mb=row.max_upload_mb,
            allowed_mime_types=row.allowed_mime_types_json or list(ALLOWED_MIME_TYPES),
            generation_enabled=bool(row.generation_enabled and row.default_provider),
            editing_enabled=bool(row.editing_enabled and row.default_provider),
            external_apply_enabled=False,
        )

    def _asset_out(self, row: PhotoAsset) -> PhotoAssetOut:
        preview_url = self._preview_url(row)
        return PhotoAssetOut(
            id=row.id,
            account_id=row.account_id,
            nm_id=row.nm_id,
            project_id=row.project_id,
            asset_type=row.asset_type,
            source_type=row.source_type,
            original_file_name=row.original_file_name,
            mime_type=row.mime_type,
            width=row.width,
            height=row.height,
            file_size=row.file_size,
            checksum=row.checksum,
            exif_removed=row.exif_removed,
            source_url=row.source_url,
            url=preview_url,
            thumbnail=preview_url,
            source_asset_id=row.source_asset_id,
            is_test=row.is_test,
            metadata=row.metadata_json or {},
            created_at=row.created_at,
            deleted_at=row.deleted_at,
        )

    def _version_out(
        self, row: PhotoVersion, asset: PhotoAsset | None = None
    ) -> PhotoVersionOut:
        preview_url = self._preview_url(asset) if asset is not None else None
        return PhotoVersionOut(
            id=row.id,
            account_id=row.account_id,
            project_id=row.project_id,
            asset_id=row.asset_id,
            version_number=row.version_number,
            parent_version_id=row.parent_version_id,
            status=row.status,
            label=row.label,
            brief_text=row.brief_text,
            change_summary=row.change_summary,
            generation_job_id=row.generation_job_id,
            created_by_user_id=row.created_by_user_id,
            approved_by_user_id=row.approved_by_user_id,
            approved_at=row.approved_at,
            rejected_at=row.rejected_at,
            rejection_reason=row.rejection_reason,
            url=preview_url,
            thumbnail=preview_url,
            operation=(asset.metadata_json or {}).get("job_type")
            if asset is not None and asset.metadata_json
            else None,
            source="generation"
            if asset is not None and asset.source_type == "ai"
            else None,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    def _preview_url(self, row: PhotoAsset | None) -> str | None:
        if row is None:
            return None
        if row.storage_key:
            return self.storage.signed_url(
                asset_id=row.id, storage_key=row.storage_key, account_id=row.account_id
            ).url
        return row.source_url

    async def _content_token(
        self, session: AsyncSession, *, account_id: int
    ) -> str | None:
        row = (
            await session.execute(
                select(WBAPIToken).where(
                    WBAPIToken.account_id == account_id,
                    WBAPIToken.category == WBAPICategory.CONTENT.value,
                    WBAPIToken.is_active.is_(True),
                )
            )
        ).scalar_one_or_none()
        return decrypt_wb_token(row.token_encrypted) if row is not None else None

    async def _asset_bytes_for_wb(self, asset: PhotoAsset) -> tuple[bytes, str, str]:
        if asset.storage_key:
            path = self.storage.path_for_key(asset.storage_key)
            if path.exists():
                return (
                    path.read_bytes(),
                    asset.mime_type or "image/png",
                    asset.original_file_name or f"photo_asset_{asset.id}.png",
                )
        raw = (asset.source_url or self._preview_url(asset) or "").strip()
        if not raw:
            raise HTTPException(
                status_code=400, detail="Selected image has no downloadable URL"
            )
        async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
            response = await client.get(raw)
        if response.status_code >= 400:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot download selected image: {response.status_code}",
            )
        content_type = response.headers.get(
            "content-type", asset.mime_type or "image/png"
        ).split(";")[0]
        filename = (
            os.path.basename(urlparse(raw).path)
            or asset.original_file_name
            or f"photo_asset_{asset.id}.png"
        )
        return response.content, content_type, filename

    async def _fetch_wb_photo_urls(self, *, token: str, nm_id: int) -> list[str]:
        body = {
            "settings": {
                "sort": {"ascending": False},
                "cursor": {"limit": 20},
                "filter": {"withPhoto": -1, "textSearch": str(int(nm_id))},
            }
        }
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                "https://content-api.wildberries.ru/content/v2/get/cards/list",
                headers={
                    "Authorization": token,
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
                json=body,
            )
        if response.status_code >= 400:
            return []
        try:
            payload = response.json()
        except Exception:
            return []
        for card in payload.get("cards") or []:
            if int(card.get("nmID") or card.get("nmId") or 0) == int(nm_id):
                return self._photo_urls(card.get("photos"))
        return []

    def _message_out(self, row: PhotoProjectMessage) -> PhotoProjectMessageOut:
        return PhotoProjectMessageOut(
            id=row.id,
            account_id=row.account_id,
            project_id=row.project_id,
            author_user_id=row.author_user_id,
            author_type=row.author_type,
            message_type=row.message_type,
            text=row.text,
            linked_asset_ids=row.linked_asset_ids_json or [],
            created_at=row.created_at,
        )

    def _event_out(self, row: PhotoProjectEvent) -> PhotoProjectEventOut:
        return PhotoProjectEventOut(
            id=row.id,
            account_id=row.account_id,
            project_id=row.project_id,
            event_type=row.event_type,
            actor_user_id=row.actor_user_id,
            payload=row.payload_json or {},
            created_at=row.created_at,
        )

    def _job_out(self, row: PhotoGenerationJob) -> PhotoJobOut:
        return PhotoJobOut(
            id=row.id,
            account_id=row.account_id,
            project_id=row.project_id,
            input_asset_ids=row.input_asset_ids_json or [],
            job_type=row.job_type,
            provider=row.provider,
            model=row.model,
            status=row.status,
            prompt_version=row.prompt_version,
            sanitized_prompt=row.sanitized_prompt,
            settings_snapshot=row.settings_snapshot_json or {},
            requested_by_user_id=row.requested_by_user_id,
            started_at=row.started_at,
            finished_at=row.finished_at,
            heartbeat_at=row.heartbeat_at,
            attempt=row.attempt,
            progress_percent=row.progress_percent,
            output_asset_ids=row.output_asset_ids_json or [],
            error_code=row.error_code,
            error_message=row.error_message,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    async def _existing_user_id(
        self, session: AsyncSession, user_id: int | None
    ) -> int | None:
        if user_id is None:
            return None
        existing = await session.get(AuthUser, int(user_id))
        return int(user_id) if existing is not None else None

    async def _event(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        project_id: int,
        event_type: str,
        actor_user_id: int | None,
        payload: dict[str, Any],
    ) -> None:
        actor_user_id = await self._existing_user_id(session, actor_user_id)
        session.add(
            PhotoProjectEvent(
                account_id=account_id,
                project_id=project_id,
                event_type=event_type,
                actor_user_id=actor_user_id,
                payload_json=payload,
                created_at=utcnow(),
            )
        )

    async def _result_event(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        project: PhotoProject,
        version: PhotoVersion,
        actor_user_id: int | None,
    ) -> None:
        action = None
        if project.source_action_key:
            action = (
                await session.execute(
                    select(UnifiedAction).where(
                        UnifiedAction.account_id == account_id,
                        UnifiedAction.source_module == "checker",
                        UnifiedAction.source_id == project.source_action_key,
                    )
                )
            ).scalar_one_or_none()
        event = ResultEvent(
            account_id=account_id,
            action_id=getattr(action, "id", None),
            source_module="photo",
            source_id=f"photo_project:{project.id}:version:{version.id}",
            nm_id=project.nm_id,
            event_type="photo_changed",
            status="new",
            external_status="draft_ready",
            message="Photo version approved in local Photo Studio. WB apply is not performed.",
            payload_json={
                "project_id": project.id,
                "version_id": version.id,
                "asset_id": version.asset_id,
                "created_by": actor_user_id,
                "marketplace_apply": "disabled",
                "calculation_note": "Safe change event only; no sales lift claim.",
            },
        )
        session.add(event)
        if action is not None:
            action.status = "done"
            action.closed_at = utcnow()

    def _photo_urls(self, value: Any) -> list[str]:
        result: list[str] = []

        def best_from_photo(item: Any) -> str | None:
            if isinstance(item, str) and item.startswith(("http://", "https://")):
                return item
            if isinstance(item, dict):
                for key in (
                    "big",
                    "canonical_url",
                    "url",
                    "full",
                    "photo",
                    "src",
                    "c516x688",
                    "square",
                    "c246x328",
                    "tm",
                ):
                    raw = item.get(key)
                    if isinstance(raw, str) and raw.startswith(("http://", "https://")):
                        return raw
            return None

        def collect(item: Any) -> None:
            best = best_from_photo(item)
            if best:
                result.append(best)
            elif isinstance(item, dict):
                for key in ("photos", "images", "media"):
                    nested = item.get(key)
                    if isinstance(nested, (list, dict)):
                        collect(nested)
            elif isinstance(item, list):
                for nested in item:
                    collect(nested)

        collect(value)
        seen: set[str] = set()
        unique: list[str] = []
        for url in result:
            if url not in seen:
                seen.add(url)
                unique.append(url)
        return unique

    @staticmethod
    def _strip_url_query(url: str) -> str:
        parsed = urlparse(str(url or "").strip())
        return parsed._replace(query="", fragment="").geturl()

    def _media_verification(
        self, *, requested_order: list[str], actual_order: list[str]
    ) -> dict[str, Any]:
        requested_clean = [self._strip_url_query(url) for url in requested_order]
        actual_clean = [self._strip_url_query(url) for url in actual_order]
        requested_set = set(requested_clean)
        actual_set = set(actual_clean)
        return {
            "requested_order": requested_order,
            "actual_order": actual_order,
            "matched": requested_clean == actual_clean,
            "missing_urls": [
                requested_order[idx]
                for idx, clean in enumerate(requested_clean)
                if clean not in actual_set
            ],
            "unexpected_urls": [
                actual_order[idx]
                for idx, clean in enumerate(actual_clean)
                if clean not in requested_set
            ],
        }

    def _sanitize_prompt(self, prompt: str) -> str:
        blocked = ("authorization", "api_key", "password", "token", "secret", "jwt")
        text = prompt.strip()
        for word in blocked:
            text = text.replace(word, "[redacted]")
            text = text.replace(word.upper(), "[redacted]")
        return text[:4000]
