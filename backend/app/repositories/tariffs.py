from __future__ import annotations


from app.core.repository import SQLAlchemyRepository
from app.models.tariffs import (
    WBTariffAcceptance,
    WBTariffBox,
    WBTariffCommission,
    WBTariffPallet,
    WBTariffReturn,
)


class TariffCommissionRepository(SQLAlchemyRepository[WBTariffCommission]):
    def __init__(self) -> None:
        super().__init__(WBTariffCommission)


class TariffBoxRepository(SQLAlchemyRepository[WBTariffBox]):
    def __init__(self) -> None:
        super().__init__(WBTariffBox)


class TariffPalletRepository(SQLAlchemyRepository[WBTariffPallet]):
    def __init__(self) -> None:
        super().__init__(WBTariffPallet)


class TariffReturnRepository(SQLAlchemyRepository[WBTariffReturn]):
    def __init__(self) -> None:
        super().__init__(WBTariffReturn)


class TariffAcceptanceRepository(SQLAlchemyRepository[WBTariffAcceptance]):
    def __init__(self) -> None:
        super().__init__(WBTariffAcceptance)
