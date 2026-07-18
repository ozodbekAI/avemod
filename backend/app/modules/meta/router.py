from __future__ import annotations

from fastapi import APIRouter

from app.core.enums_meta import get_enum_labels
from app.schemas.meta import EnumMetaResponse

router = APIRouter(tags=["meta"])


@router.get("/meta/enums", response_model=EnumMetaResponse)
async def get_meta_enums() -> EnumMetaResponse:
    return EnumMetaResponse(enums=get_enum_labels())
