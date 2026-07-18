from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.ab_tests import ABTestCompany, ABTestPhoto


class ABTestRepository:
    async def get_company(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        company_id: int,
    ) -> ABTestCompany | None:
        return (
            await session.execute(
                select(ABTestCompany)
                .options(selectinload(ABTestCompany.photos))
                .where(
                    ABTestCompany.account_id == int(account_id),
                    ABTestCompany.id == int(company_id),
                )
            )
        ).scalar_one_or_none()

    async def get_company_any_id(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        company_id: int,
    ) -> ABTestCompany | None:
        return (
            await session.execute(
                select(ABTestCompany)
                .options(selectinload(ABTestCompany.photos))
                .where(
                    ABTestCompany.account_id == int(account_id),
                    or_(
                        ABTestCompany.id == int(company_id),
                        ABTestCompany.wb_advert_id == int(company_id),
                    ),
                )
                .order_by(ABTestCompany.id.desc())
            )
        ).scalar_one_or_none()

    async def list_by_status(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        statuses: set[str],
        limit: int,
        offset: int,
    ) -> tuple[list[ABTestCompany], int]:
        stmt = (
            select(ABTestCompany)
            .options(selectinload(ABTestCompany.photos))
            .where(
                ABTestCompany.account_id == int(account_id),
                ABTestCompany.status.in_(sorted(statuses)),
            )
            .order_by(ABTestCompany.id.desc())
        )
        count_stmt = (
            select(func.count())
            .select_from(ABTestCompany)
            .where(
                ABTestCompany.account_id == int(account_id),
                ABTestCompany.status.in_(sorted(statuses)),
            )
        )
        total = int((await session.execute(count_stmt)).scalar_one() or 0)
        rows = list((await session.execute(stmt.limit(limit).offset(offset))).scalars())
        return rows, total

    async def list_active_for_scheduler(
        self, session: AsyncSession, *, limit: int = 100
    ) -> list[ABTestCompany]:
        return list(
            (
                await session.execute(
                    select(ABTestCompany)
                    .options(selectinload(ABTestCompany.photos))
                    .where(ABTestCompany.status.in_(("created", "running")))
                    .order_by(
                        ABTestCompany.last_polled_at.asc().nullsfirst(),
                        ABTestCompany.id.asc(),
                    )
                    .limit(limit)
                )
            ).scalars()
        )

    async def replace_photos(
        self, session: AsyncSession, company: ABTestCompany, photos: list[dict]
    ) -> None:
        current = {int(photo.order): photo for photo in (company.photos or [])}
        next_orders = set()
        for payload in photos:
            order = int(payload["order"])
            next_orders.add(order)
            photo = current.get(order)
            if photo is None:
                session.add(
                    ABTestPhoto(
                        company_id=int(company.id),
                        order=order,
                        file_url=str(payload["file_url"]),
                        preview_url=payload.get("preview_url")
                        or payload.get("file_url"),
                        wb_url=payload.get("wb_url"),
                    )
                )
            else:
                photo.file_url = str(payload["file_url"])
                photo.preview_url = payload.get("preview_url") or payload.get(
                    "file_url"
                )
                if payload.get("wb_url"):
                    photo.wb_url = payload.get("wb_url")
        for order, photo in current.items():
            if order not in next_orders:
                await session.delete(photo)
        company.photos_count = len(photos)
        await session.flush()
