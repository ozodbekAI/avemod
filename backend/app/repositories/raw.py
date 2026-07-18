from __future__ import annotations

from app.core.repository import SQLAlchemyRepository
from app.models.raw import RawWBAPIResponse


class RawResponseRepository(SQLAlchemyRepository[RawWBAPIResponse]):
    def __init__(self) -> None:
        super().__init__(RawWBAPIResponse)
