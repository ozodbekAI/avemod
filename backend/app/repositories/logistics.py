from __future__ import annotations

from app.core.repository import SQLAlchemyRepository
from app.models.logistics import (
    WBLogisticsAcceptanceReportRow,
    WBLogisticsPaidStorageRow,
    WBLogisticsTransitTariff,
    WBSellerWarehouse,
    WBSellerWarehouseStock,
)


class LogisticsPaidStorageRepository(SQLAlchemyRepository[WBLogisticsPaidStorageRow]):
    def __init__(self) -> None:
        super().__init__(WBLogisticsPaidStorageRow)


class LogisticsAcceptanceReportRepository(
    SQLAlchemyRepository[WBLogisticsAcceptanceReportRow]
):
    def __init__(self) -> None:
        super().__init__(WBLogisticsAcceptanceReportRow)


class LogisticsTransitTariffRepository(SQLAlchemyRepository[WBLogisticsTransitTariff]):
    def __init__(self) -> None:
        super().__init__(WBLogisticsTransitTariff)


class SellerWarehouseRepository(SQLAlchemyRepository[WBSellerWarehouse]):
    def __init__(self) -> None:
        super().__init__(WBSellerWarehouse)


class SellerWarehouseStockRepository(SQLAlchemyRepository[WBSellerWarehouseStock]):
    def __init__(self) -> None:
        super().__init__(WBSellerWarehouseStock)
