from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
import httpx
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db_session
from app.core.time import utcnow
from app.models.accounts import WBAccount
from app.models.auth import AuthUser
from app.models.photo_studio import PhotoAsset, PhotoProject, PhotoProjectMessage
from app.models.product_cards import WBProductCard
from app.schemas.photo_chat import PhotoChatStreamRequest
from app.schemas.photo import PhotoJobCreate, PhotoProjectCreate
from app.services.auth import get_current_user, resolve_user_account
from app.services.photo_error_mapper import map_photo_error
from app.services.photo_studio import PhotoStudioService

router = APIRouter(tags=["photo-chat"])
photo_service = PhotoStudioService()


def _sse(payload: dict[str, Any]) -> str:
    return f"event: message\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _photo_urls(value: Any) -> list[str]:
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
            return
        if isinstance(item, dict):
            for key in ("photos", "images", "media"):
                nested = item.get(key)
                if isinstance(nested, (list, dict)):
                    collect(nested)
            return
        if isinstance(item, list):
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


async def _required_account(
    session: AsyncSession,
    user: AuthUser,
    account_id: int | None = None,
) -> WBAccount:
    return await resolve_user_account(
        session, user, account_id=account_id, require_account=True
    )  # type: ignore[return-value]


@router.get("/photo/image-proxy")
async def photo_image_proxy(
    url: str = Query(..., min_length=10, max_length=2000),
) -> StreamingResponse:
    parsed = urlparse(url.strip())
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in {"http", "https"} or not (
        host == "wbbasket.ru" or host.endswith(".wbbasket.ru")
    ):
        raise HTTPException(
            status_code=400, detail="Only WB basket images can be proxied"
        )
    if "/images/" not in parsed.path:
        raise HTTPException(status_code=400, detail="Only image URLs can be proxied")

    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        response = await client.get(
            url,
            headers={
                "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
                "Referer": "https://www.wildberries.ru/",
                "User-Agent": "Mozilla/5.0",
            },
        )
    if response.status_code >= 400:
        raise HTTPException(
            status_code=response.status_code, detail="WB image is unavailable"
        )
    content_type = response.headers.get("content-type", "image/webp").split(";")[0]
    if not content_type.startswith("image/"):
        raise HTTPException(status_code=502, detail="WB returned non-image content")
    return StreamingResponse(
        iter([response.content]),
        media_type=content_type,
        headers={"Cache-Control": "public, max-age=86400"},
    )


async def _card_by_nm(
    session: AsyncSession, *, account_id: int, nm_id: int | None
) -> WBProductCard | None:
    if not nm_id:
        return None
    return (
        await session.execute(
            select(WBProductCard).where(
                WBProductCard.account_id == account_id,
                WBProductCard.nm_id == int(nm_id),
            )
        )
    ).scalar_one_or_none()


async def _ensure_thread(
    session: AsyncSession,
    *,
    account_id: int,
    user_id: int | None,
    thread_id: int | None = None,
    nm_id: int | None = None,
) -> PhotoProject:
    if thread_id:
        row = await session.get(PhotoProject, int(thread_id))
        if row is None or row.account_id != account_id:
            raise HTTPException(status_code=404, detail="photo_thread_not_found")
        return row

    effective_nm_id = int(nm_id or 0)
    if effective_nm_id:
        existing = (
            await session.execute(
                select(PhotoProject)
                .where(
                    PhotoProject.account_id == account_id,
                    PhotoProject.nm_id == effective_nm_id,
                    PhotoProject.status != "archived",
                )
                .order_by(PhotoProject.updated_at.desc(), PhotoProject.id.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if existing is not None:
            return existing

    card = await _card_by_nm(session, account_id=account_id, nm_id=effective_nm_id)
    title = card.title or card.vendor_code if card is not None else None
    project = await photo_service.create_project(
        session,
        payload=PhotoProjectCreate(
            account_id=account_id,
            nm_id=effective_nm_id,
            title=title
            or (
                f"Photo Studio {effective_nm_id}"
                if effective_nm_id
                else "Photo Studio Chat"
            ),
            source_action_key="photo_chat",
        ),
        created_by_user_id=user_id,
    )
    return await session.get(PhotoProject, project.id)  # type: ignore[return-value]


async def _move_assets_to_thread(
    session: AsyncSession,
    *,
    account_id: int,
    project: PhotoProject,
    asset_ids: list[int],
) -> list[int]:
    unique = [int(item) for item in dict.fromkeys(asset_ids) if item]
    if not unique:
        return []
    rows = list(
        (
            await session.execute(
                select(PhotoAsset).where(
                    PhotoAsset.account_id == account_id,
                    PhotoAsset.id.in_(unique),
                    PhotoAsset.deleted_at.is_(None),
                )
            )
        ).scalars()
    )
    for row in rows:
        row.project_id = project.id
        row.nm_id = project.nm_id or row.nm_id
    await session.flush()
    return [int(row.id) for row in rows]


def _thread_meta(project: PhotoProject, message_count: int = 0) -> dict[str, Any]:
    preview = project.title or (
        f"Артикул {project.nm_id}" if project.nm_id else "Новый чат"
    )
    return {
        "id": int(project.id),
        "preview": preview,
        "created_at": project.created_at,
        "updated_at": project.updated_at,
        "message_count": message_count,
        "is_active": False,
    }


def _asset_payload(asset: PhotoAsset) -> dict[str, Any]:
    out = photo_service._asset_out(asset)
    metadata = out.metadata or {}
    label = metadata.get("name") or out.original_file_name or f"Asset {out.id}"
    return {
        "asset_id": out.id,
        "id": out.id,
        "owner_type": "user",
        "asset_type": out.asset_type,
        "name": label,
        "label": label,
        "file_url": out.url or out.source_url,
        "image_url": out.url or out.source_url,
        "url": out.url or out.source_url,
        "file_name": out.original_file_name,
        "prompt": metadata.get("prompt") or "",
        "category": metadata.get("category"),
    }


async def _history_payload(
    session: AsyncSession, *, account_id: int, project: PhotoProject
) -> dict[str, Any]:
    messages = list(
        (
            await session.execute(
                select(PhotoProjectMessage)
                .where(
                    PhotoProjectMessage.account_id == account_id,
                    PhotoProjectMessage.project_id == project.id,
                )
                .order_by(
                    PhotoProjectMessage.created_at.asc(), PhotoProjectMessage.id.asc()
                )
            )
        ).scalars()
    )
    assets = list(
        (
            await session.execute(
                select(PhotoAsset)
                .where(
                    PhotoAsset.account_id == account_id,
                    PhotoAsset.project_id == project.id,
                    PhotoAsset.deleted_at.is_(None),
                )
                .order_by(PhotoAsset.created_at.asc(), PhotoAsset.id.asc())
            )
        ).scalars()
    )
    asset_payload = []
    for asset in assets:
        out = photo_service._asset_out(asset)
        asset_payload.append(
            {
                "asset_id": out.id,
                "file_url": out.url or out.source_url,
                "file_name": out.original_file_name,
                "prompt": (out.metadata or {}).get("prompt")
                or (out.metadata or {}).get("job_type")
                or "",
                "caption": (out.metadata or {}).get("provider_text") or "",
            }
        )

    return {
        "thread_id": int(project.id),
        "active_thread_id": int(project.id),
        "context_state": {
            "last_generated_asset_id": asset_payload[-1]["asset_id"]
            if asset_payload
            else None,
            "working_asset_ids": [item["asset_id"] for item in asset_payload[-4:]],
            "pending_question": None,
            "last_action": None,
            "locale": "ru",
        },
        "assets": asset_payload,
        "messages": [
            {
                "id": int(msg.id),
                "role": "assistant"
                if msg.author_type in {"assistant", "system"}
                else "user",
                "msg_type": "image" if msg.message_type == "image" else "text",
                "content": msg.text,
                "created_at": msg.created_at,
                "thread_id": int(project.id),
                "request_id": None,
                "meta": {"asset_ids": msg.linked_asset_ids_json or []},
            }
            for msg in messages
        ],
        "message_count": len(messages),
    }


@router.get("/stores")
async def photo_stores_alias(
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> list[dict[str, Any]]:
    account = await _required_account(session, current_user)
    return [
        {"id": int(account.id), "name": account.name, "is_active": account.is_active}
    ]


@router.get("/stores/{account_id}/cards/wb/live")
async def photo_cards_live(
    account_id: int,
    limit: int = Query(default=80, ge=1, le=200),
    with_photo: int = Query(default=1, ge=-1, le=1),
    q: str | None = Query(default=None),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    account = await _required_account(session, current_user, account_id=account_id)
    stmt = select(WBProductCard).where(WBProductCard.account_id == account.id)
    if q:
        like = f"%{q.strip()}%"
        clauses = [
            WBProductCard.vendor_code.ilike(like),
            WBProductCard.title.ilike(like),
        ]
        if q.strip().isdigit():
            clauses.append(WBProductCard.nm_id == int(q.strip()))
        stmt = stmt.where(or_(*clauses))
    rows = list(
        (
            await session.execute(
                stmt.order_by(WBProductCard.updated_at.desc()).limit(limit)
            )
        ).scalars()
    )
    cards: list[dict[str, Any]] = []
    for row in rows:
        photos = _photo_urls(row.photos)
        if not photos:
            photos = _photo_urls(row.payload)
        if with_photo == 1 and not photos:
            continue
        if with_photo == 0 and photos:
            continue
        cards.append(
            {
                "id": int(row.id),
                "nm_id": int(row.nm_id),
                "vendor_code": row.vendor_code,
                "title": row.title,
                "main_photo_url": photos[0] if photos else None,
                "photos": photos,
            }
        )
    return {"cards": cards, "total": len(cards)}


@router.get("/stores/{account_id}/cards")
async def photo_cards_local(
    account_id: int,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=200),
    search: str | None = Query(default=None),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    offset = (page - 1) * limit
    account = await _required_account(session, current_user, account_id=account_id)
    stmt = select(WBProductCard).where(WBProductCard.account_id == account.id)
    count_stmt = (
        select(func.count())
        .select_from(WBProductCard)
        .where(WBProductCard.account_id == account.id)
    )
    if search:
        like = f"%{search.strip()}%"
        clauses = [
            WBProductCard.vendor_code.ilike(like),
            WBProductCard.title.ilike(like),
        ]
        if search.strip().isdigit():
            clauses.append(WBProductCard.nm_id == int(search.strip()))
        stmt = stmt.where(or_(*clauses))
        count_stmt = count_stmt.where(or_(*clauses))
    total = int((await session.execute(count_stmt)).scalar() or 0)
    rows = list(
        (
            await session.execute(
                stmt.order_by(WBProductCard.updated_at.desc())
                .limit(limit)
                .offset(offset)
            )
        ).scalars()
    )
    return {
        "total": total,
        "items": [
            {
                "id": int(row.id),
                "nm_id": int(row.nm_id),
                "vendor_code": row.vendor_code,
                "title": row.title,
                "photos": _photo_urls(row.photos),
            }
            for row in rows
        ],
    }


@router.get("/stores/{account_id}/cards/{card_id}")
async def photo_card_detail(
    account_id: int,
    card_id: int,
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    account = await _required_account(session, current_user, account_id=account_id)
    row = await session.get(WBProductCard, card_id)
    if row is None or row.account_id != account.id:
        raise HTTPException(status_code=404, detail="card_not_found")
    return {
        "id": int(row.id),
        "nm_id": int(row.nm_id),
        "vendor_code": row.vendor_code,
        "title": row.title,
        "photos": _photo_urls(row.photos),
    }


@router.post("/stores/{account_id}/cards/{card_id}/photos/sync")
async def photo_card_photos_sync(
    account_id: int,
    card_id: int,
    payload: dict[str, Any],
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    account = await _required_account(session, current_user, account_id=account_id)
    row = await session.get(WBProductCard, card_id)
    if row is None or row.account_id != account.id:
        raise HTTPException(status_code=404, detail="card_not_found")
    photos = [str(item) for item in payload.get("photos") or [] if str(item).strip()]
    row.photos = photos
    await session.commit()
    return {"id": int(row.id), "nm_id": int(row.nm_id), "photos": photos}


@router.get("/photo/catalog/all")
async def photo_catalog_all() -> dict[str, Any]:
    return {"scenes": [], "poses": [], "models": [], "videos": []}


@router.get("/photo-assets/catalog")
async def photo_assets_catalog(
    asset_type: str = Query(default="scene"),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    account = await _required_account(session, current_user)
    rows = list(
        (
            await session.execute(
                select(PhotoAsset)
                .where(
                    PhotoAsset.account_id == account.id,
                    PhotoAsset.asset_type == asset_type,
                    PhotoAsset.deleted_at.is_(None),
                )
                .order_by(PhotoAsset.created_at.desc(), PhotoAsset.id.desc())
                .limit(100)
            )
        ).scalars()
    )
    return {"assets": [_asset_payload(row) for row in rows]}


@router.post("/photo-assets/user/upload")
async def photo_assets_user_upload(
    file: UploadFile = File(...),
    asset_type: str = Form(default="scene"),
    name: str | None = Form(default=None),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    account = await _required_account(session, current_user)
    project = await _ensure_thread(
        session, account_id=account.id, user_id=current_user.id
    )
    out = await photo_service.upload_asset(
        session,
        account_id=account.id,
        project_id=project.id,
        file=file,
        actor_user_id=current_user.id,
        asset_type=asset_type,
    )
    row = await session.get(PhotoAsset, out.id)
    if row is not None:
        row.metadata_json = {
            **(row.metadata_json or {}),
            "name": name or out.original_file_name,
            "gallery": True,
        }
    await session.commit()
    return (
        _asset_payload(row)
        if row is not None
        else {"asset_id": out.id, "id": out.id, "url": out.url}
    )


@router.post("/photo-assets/user/import")
async def photo_assets_user_import(
    payload: dict[str, Any],
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    account = await _required_account(
        session, current_user, account_id=payload.get("account_id")
    )
    project = await _ensure_thread(
        session,
        account_id=account.id,
        user_id=current_user.id,
        nm_id=payload.get("nm_id"),
    )
    source_url = str(payload.get("source_url") or payload.get("url") or "").strip()
    if not source_url:
        raise HTTPException(status_code=400, detail="source_url_required")
    row = PhotoAsset(
        account_id=account.id,
        nm_id=project.nm_id,
        project_id=project.id,
        asset_type=str(payload.get("asset_type") or "scene"),
        source_type="remote_url",
        storage_key=None,
        original_file_name=(
            str(payload.get("name") or "") or source_url.rsplit("/", 1)[-1]
        )[:255]
        or None,
        mime_type="image/remote",
        width=None,
        height=None,
        file_size=0,
        checksum=None,
        exif_removed=False,
        source_url=source_url,
        created_by_user_id=current_user.id,
        metadata_json={
            "name": payload.get("name"),
            "prompt": payload.get("prompt"),
            "category": payload.get("category"),
            "gallery": True,
            "source": "photo_gallery_import",
        },
    )
    session.add(row)
    await session.commit()
    return _asset_payload(row)


@router.get("/photo/chat/models")
async def photo_chat_models() -> dict[str, Any]:
    return {
        "generation_models": [
            {
                "id": "gemini-3.1-flash-image-preview",
                "label": "Gemini 3.1 Flash Image",
                "description": "Локальная генерация через Finance backend.",
            },
            {
                "id": "gemini-2.5-flash-image",
                "label": "Gemini 2.5 Flash Image",
                "description": "Fallback-модель.",
            },
        ],
        "default_generation_model": "gemini-3.1-flash-image-preview",
    }


@router.get("/photo/threads")
async def photo_threads(
    account_id: int | None = Query(default=None),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    account = await _required_account(session, current_user, account_id=account_id)
    rows = list(
        (
            await session.execute(
                select(PhotoProject)
                .where(
                    PhotoProject.account_id == account.id,
                    PhotoProject.status != "archived",
                )
                .order_by(PhotoProject.updated_at.desc(), PhotoProject.id.desc())
                .limit(50)
            )
        ).scalars()
    )
    counts = dict(
        (
            await session.execute(
                select(PhotoProjectMessage.project_id, func.count())
                .where(PhotoProjectMessage.account_id == account.id)
                .group_by(PhotoProjectMessage.project_id)
            )
        ).all()
    )
    return {
        "threads": [_thread_meta(row, int(counts.get(row.id, 0))) for row in rows],
        "active_thread_id": int(rows[0].id) if rows else None,
    }


@router.post("/photo/threads/new")
async def photo_thread_new(
    payload: dict[str, Any] | None = None,
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    account = await _required_account(
        session, current_user, account_id=(payload or {}).get("account_id")
    )
    project = await _ensure_thread(
        session,
        account_id=account.id,
        user_id=current_user.id,
        nm_id=(payload or {}).get("nm_id"),
    )
    await session.commit()
    return await _history_payload(session, account_id=account.id, project=project)


@router.delete("/photo/threads/{thread_id}")
async def photo_thread_delete(
    thread_id: int,
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    project = await session.get(PhotoProject, thread_id)
    if project is None:
        raise HTTPException(status_code=404, detail="thread_not_found")
    account = await _required_account(
        session, current_user, account_id=project.account_id
    )
    project.status = "archived"
    project.archived_at = utcnow()
    await session.commit()
    return await photo_threads(
        account_id=account.id, current_user=current_user, session=session
    )


@router.get("/photo/chat/history")
async def photo_chat_history(
    thread_id: int | None = Query(default=None),
    account_id: int | None = Query(default=None),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    account = await _required_account(session, current_user, account_id=account_id)
    project = await _ensure_thread(
        session, account_id=account.id, user_id=current_user.id, thread_id=thread_id
    )
    await session.commit()
    return await _history_payload(session, account_id=account.id, project=project)


@router.post("/photo/assets/upload")
async def photo_asset_upload(
    thread_id: int | None = Query(default=None),
    account_id: int | None = Query(default=None),
    file: UploadFile = File(...),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    account = await _required_account(session, current_user, account_id=account_id)
    project = await _ensure_thread(
        session, account_id=account.id, user_id=current_user.id, thread_id=thread_id
    )
    asset = await photo_service.upload_asset(
        session,
        account_id=account.id,
        project_id=project.id,
        file=file,
        actor_user_id=current_user.id,
    )
    await session.commit()
    return {
        "asset_id": asset.id,
        "id": asset.id,
        "file_url": asset.url,
        "url": asset.url,
        "file_name": asset.original_file_name,
    }


@router.post("/photo/assets/import")
async def photo_asset_import(
    payload: dict[str, Any],
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    account = await _required_account(
        session, current_user, account_id=payload.get("account_id")
    )
    project = await _ensure_thread(
        session,
        account_id=account.id,
        user_id=current_user.id,
        thread_id=payload.get("thread_id"),
        nm_id=payload.get("nm_id"),
    )
    source_url = str(payload.get("source_url") or "").strip()
    if not source_url:
        raise HTTPException(status_code=400, detail="source_url_required")
    row = PhotoAsset(
        account_id=account.id,
        nm_id=project.nm_id,
        project_id=project.id,
        asset_type="chat_source",
        source_type="remote_url",
        storage_key=None,
        original_file_name=source_url.rsplit("/", 1)[-1][:255] or None,
        mime_type="image/remote",
        width=None,
        height=None,
        file_size=0,
        checksum=None,
        exif_removed=False,
        source_url=source_url,
        created_by_user_id=current_user.id,
        metadata_json={"source": "photo_chat_import"},
    )
    session.add(row)
    await session.commit()
    out = photo_service._asset_out(row)
    return {
        "asset_id": out.id,
        "id": out.id,
        "file_url": out.url or out.source_url,
        "url": out.url or out.source_url,
        "file_name": out.original_file_name,
    }


@router.post("/photo/chat/stream")
async def photo_chat_stream(
    payload: PhotoChatStreamRequest,
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> StreamingResponse:
    raw_payload = payload.model_dump()
    account = await _required_account(
        session, current_user, account_id=raw_payload.get("account_id")
    )
    project = await _ensure_thread(
        session,
        account_id=account.id,
        user_id=current_user.id,
        thread_id=payload.thread_id,
        nm_id=raw_payload.get("nm_id"),
    )
    request_id = str(payload.request_id or f"req_{int(utcnow().timestamp())}")
    message = payload.message
    asset_ids = [int(item) for item in payload.asset_ids if item]
    asset_ids = await _move_assets_to_thread(
        session, account_id=account.id, project=project, asset_ids=asset_ids
    )

    if message or asset_ids:
        session.add(
            PhotoProjectMessage(
                account_id=account.id,
                project_id=project.id,
                author_user_id=current_user.id,
                author_type="user",
                message_type="image" if asset_ids and not message else "comment",
                text=message,
                linked_asset_ids_json=asset_ids,
                created_at=utcnow(),
            )
        )
        await session.flush()

    wants_generation = bool(asset_ids or payload.quick_action) and message
    assistant_text = (
        "Принял. Выберите фото товара и напишите, что нужно сгенерировать."
        if not wants_generation
        else "Запускаю генерацию изображения."
    )
    generated_asset = None
    mapped_error: dict[str, Any] | None = None
    if wants_generation:
        try:
            job = await photo_service.create_job(
                session,
                account_id=account.id,
                project_id=project.id,
                payload=PhotoJobCreate(
                    job_type="edit",
                    input_asset_ids=asset_ids,
                    prompt=message,
                    model=payload.generation_model,
                ),
                actor_user_id=current_user.id,
            )
            await photo_service.process_queued_jobs(session, max_jobs=1)
            job_row = await photo_service._job_or_404(
                session, account_id=account.id, job_id=job.id
            )
            if job_row.output_asset_ids_json:
                generated_asset = await photo_service._asset_or_404(
                    session,
                    account_id=account.id,
                    asset_id=int(job_row.output_asset_ids_json[-1]),
                )
                assistant_text = "Готово!"
            elif job_row.error_message:
                mapped_error = map_photo_error(
                    job_row.error_message, context="chat_stream:generation"
                )
                assistant_text = str(
                    mapped_error.get("message") or job_row.error_message
                )
        except Exception as exc:
            mapped_error = map_photo_error(str(exc), context="chat_stream:generation")
            assistant_text = str(
                mapped_error.get("message")
                or "Операция не завершилась. Повторите попытку."
            )

    linked = [int(generated_asset.id)] if generated_asset is not None else []
    session.add(
        PhotoProjectMessage(
            account_id=account.id,
            project_id=project.id,
            author_user_id=None,
            author_type="assistant",
            message_type="image" if linked else "comment",
            text=assistant_text,
            linked_asset_ids_json=linked,
            created_at=utcnow(),
        )
    )
    await session.commit()

    async def events():
        yield _sse(
            {"type": "ack", "thread_id": int(project.id), "request_id": request_id}
        )
        if wants_generation:
            yield _sse(
                {
                    "type": "generation_start",
                    "thread_id": int(project.id),
                    "request_id": request_id,
                }
            )
        if generated_asset is not None:
            out = photo_service._asset_out(generated_asset)
            yield _sse(
                {
                    "type": "generation_complete",
                    "thread_id": int(project.id),
                    "request_id": request_id,
                    "asset_id": out.id,
                    "image_url": out.url or out.source_url,
                    "file_url": out.url or out.source_url,
                    "file_name": out.original_file_name,
                    "prompt": message,
                    "index": 1,
                    "total": 1,
                }
            )
        elif mapped_error is not None:
            yield _sse(
                {
                    "type": "error",
                    "thread_id": int(project.id),
                    "request_id": request_id,
                    "error": mapped_error,
                    "content": assistant_text,
                }
            )
        else:
            yield _sse(
                {
                    "type": "chat",
                    "thread_id": int(project.id),
                    "request_id": request_id,
                    "content": assistant_text,
                }
            )
        yield _sse(
            {
                "type": "context_state",
                "thread_id": int(project.id),
                "request_id": request_id,
                "context_state": {
                    "last_generated_asset_id": int(generated_asset.id)
                    if generated_asset is not None
                    else None,
                    "working_asset_ids": [int(generated_asset.id)]
                    if generated_asset is not None
                    else asset_ids[-4:],
                    "pending_question": None,
                    "last_action": None,
                    "locale": payload.locale or "ru",
                },
            }
        )

    return StreamingResponse(events(), media_type="text/event-stream")


@router.post("/photo/generator/run")
async def photo_generator_run(
    payload: dict[str, Any],
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    account = await _required_account(
        session, current_user, account_id=payload.get("account_id")
    )
    project = await _ensure_thread(
        session,
        account_id=account.id,
        user_id=current_user.id,
        thread_id=payload.get("thread_id"),
        nm_id=payload.get("nm_id"),
    )
    asset_ids = await _move_assets_to_thread(
        session,
        account_id=account.id,
        project=project,
        asset_ids=[int(item) for item in payload.get("asset_ids") or [] if item],
    )
    prompt = str(
        payload.get("prompt")
        or payload.get("custom_prompt")
        or "Создай маркетплейс-фото товара"
    ).strip()
    job = await photo_service.create_job(
        session,
        account_id=account.id,
        project_id=project.id,
        payload=PhotoJobCreate(
            job_type="edit" if asset_ids else "generate",
            input_asset_ids=asset_ids,
            prompt=prompt,
            model=payload.get("generation_model"),
        ),
        actor_user_id=current_user.id,
    )
    await photo_service.process_queued_jobs(session, max_jobs=1)
    job_row = await photo_service._job_or_404(
        session, account_id=account.id, job_id=job.id
    )
    if not job_row.output_asset_ids_json:
        raise HTTPException(
            status_code=400, detail=job_row.error_message or "generation_failed"
        )
    asset = await photo_service._asset_or_404(
        session, account_id=account.id, asset_id=int(job_row.output_asset_ids_json[-1])
    )
    out = photo_service._asset_out(asset)
    await session.commit()
    return {
        "thread_id": int(project.id),
        "active_thread_id": int(project.id),
        "context_state": {
            "last_generated_asset_id": out.id,
            "working_asset_ids": [out.id],
            "pending_question": None,
            "last_action": None,
            "locale": "ru",
        },
        "asset": {
            "asset_id": out.id,
            "id": out.id,
            "file_url": out.url or out.source_url,
            "url": out.url or out.source_url,
            "file_name": out.original_file_name,
            "prompt": prompt,
        },
    }


@router.post("/photo/chat/clear")
async def photo_chat_clear(
    payload: dict[str, Any],
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    thread_id = int(payload.get("thread_id") or 0)
    project = await session.get(PhotoProject, thread_id)
    if project is None:
        return {"ok": True}
    account = await _required_account(
        session, current_user, account_id=project.account_id
    )
    rows = list(
        (
            await session.execute(
                select(PhotoProjectMessage).where(
                    PhotoProjectMessage.account_id == account.id,
                    PhotoProjectMessage.project_id == project.id,
                )
            )
        ).scalars()
    )
    for row in rows:
        await session.delete(row)
    await session.commit()
    return {"ok": True, "thread_id": thread_id}


@router.post("/photo/chat/messages/delete")
async def photo_chat_messages_delete(payload: dict[str, Any]) -> dict[str, Any]:
    return {"ok": True, "deleted_message_ids": payload.get("message_ids") or []}


@router.post("/photo/chat/assets/delete")
async def photo_chat_assets_delete(
    payload: dict[str, Any],
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    asset_ids = [int(item) for item in payload.get("asset_ids") or [] if item]
    rows = list(
        (
            await session.execute(
                select(PhotoAsset).where(PhotoAsset.id.in_(asset_ids))
            )
        ).scalars()
    )
    for row in rows:
        await _required_account(session, current_user, account_id=row.account_id)
        row.deleted_at = utcnow()
    await session.commit()
    return {"ok": True, "deleted_asset_ids": asset_ids, "deleted_message_ids": []}
