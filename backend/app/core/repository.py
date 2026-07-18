from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Generic, TypeVar

from sqlalchemy import Select, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dedupe import compute_dedupe_key_from_mapping
from app.core.pagination import Page

ModelT = TypeVar("ModelT")


class SQLAlchemyRepository(Generic[ModelT]):
    def __init__(self, model: type[ModelT]) -> None:
        self.model = model

    async def get(self, session: AsyncSession, entity_id: Any) -> ModelT | None:
        return await session.get(self.model, entity_id)

    async def list(
        self,
        session: AsyncSession,
        *,
        statement: Select[Any] | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Page[ModelT]:
        query = statement if statement is not None else select(self.model)
        count_query = select(func.count()).select_from(query.subquery())
        total = (await session.execute(count_query)).scalar_one()
        items = list(
            (await session.execute(query.limit(limit).offset(offset))).scalars()
        )
        return Page(total=total, limit=limit, offset=offset, items=items)

    async def create(self, session: AsyncSession, **values: Any) -> ModelT:
        if "dedupe_key" in self.model.__table__.columns and "dedupe_key" not in values:
            fields = getattr(self.model, "__dedupe_fields__", None)
            if fields:
                values["dedupe_key"] = compute_dedupe_key_from_mapping(fields, values)
        entity = self.model(**values)
        session.add(entity)
        await session.flush()
        return entity

    async def upsert_many(
        self,
        session: AsyncSession,
        rows: Sequence[dict[str, Any]],
        *,
        conflict_fields: Sequence[str],
        skip_update_fields: Sequence[str] | None = None,
    ) -> None:
        if not rows:
            return
        if "dedupe_key" in self.model.__table__.columns:
            fields = getattr(self.model, "__dedupe_fields__", None)
            if fields:
                rows = [
                    {
                        **row,
                        "dedupe_key": row.get("dedupe_key")
                        or compute_dedupe_key_from_mapping(fields, row),
                    }
                    for row in rows
                ]
        deduplicated_rows: list[dict[str, Any]] = []
        seen_by_conflict: dict[tuple[Any, ...], int] = {}
        for row in rows:
            key = tuple(row.get(field) for field in conflict_fields)
            existing_index = seen_by_conflict.get(key)
            if existing_index is None:
                seen_by_conflict[key] = len(deduplicated_rows)
                deduplicated_rows.append(row)
                continue
            # Keep the last version for the same conflict key so backfills do not
            # fail on repeated rows returned within a single WB response.
            deduplicated_rows[existing_index] = row
        skip = set(skip_update_fields or []) | {"id", "created_at"}
        column_count = max(1, len(self.model.__table__.columns))
        chunk_size = max(1, min(500, 10000 // column_count))
        for start in range(0, len(deduplicated_rows), chunk_size):
            chunk = list(deduplicated_rows[start : start + chunk_size])
            stmt = insert(self.model).values(chunk)
            update_values = {
                column.name: getattr(stmt.excluded, column.name)
                for column in self.model.__table__.columns
                if column.name not in skip and column.name not in conflict_fields
            }
            stmt = stmt.on_conflict_do_update(
                index_elements=[
                    getattr(self.model, field) for field in conflict_fields
                ],
                set_=update_values,
            )
            await session.execute(stmt)
