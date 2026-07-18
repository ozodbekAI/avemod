from __future__ import annotations

from app.core.repository import SQLAlchemyRepository
from app.models.promotions import WBPromotionCalendar, WBPromotionNomenclature


class PromotionCalendarRepository(SQLAlchemyRepository[WBPromotionCalendar]):
    def __init__(self) -> None:
        super().__init__(WBPromotionCalendar)


class PromotionNomenclatureRepository(SQLAlchemyRepository[WBPromotionNomenclature]):
    def __init__(self) -> None:
        super().__init__(WBPromotionNomenclature)
