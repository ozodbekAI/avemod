from __future__ import annotations

from datetime import date

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import Page
from app.core.repository import SQLAlchemyRepository
from app.core.sorting import apply_sort_direction
from app.models.marts import (
    MartAccountExpenseDaily,
    MartExpenseDaily,
    MartFinanceReconciliation,
    MartReconciliationDaily,
    MartSKUDaily,
    MartStockDaily,
)


class MartSKUDailyRepository(SQLAlchemyRepository[MartSKUDaily]):
    def __init__(self) -> None:
        super().__init__(MartSKUDaily)

    async def list_filtered(
        self,
        session: AsyncSession,
        *,
        account_id: int | None = None,
        nm_id: int | None = None,
        sku_id: int | None = None,
        vendor_code: str | None = None,
        barcode: str | None = None,
        brand: str | None = None,
        subject_name: str | None = None,
        search: str | None = None,
        has_manual_cost: bool | None = None,
        has_open_issues: bool | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        sort_by: str | None = None,
        sort_dir: str = "desc",
        limit: int = 50,
        offset: int = 0,
    ) -> Page[MartSKUDaily]:
        sort_map = {
            "stat_date": MartSKUDaily.stat_date,
            "sku_id": MartSKUDaily.sku_id,
            "nm_id": MartSKUDaily.nm_id,
            "vendor_code": MartSKUDaily.vendor_code,
            "brand": MartSKUDaily.brand,
            "subject_name": MartSKUDaily.subject_name,
            "final_revenue": MartSKUDaily.final_revenue,
            "final_for_pay": MartSKUDaily.final_for_pay,
            "estimated_profit_after_ads": MartSKUDaily.estimated_profit_after_ads,
            "margin_percent": MartSKUDaily.margin_percent,
        }
        sort_column = sort_map.get(sort_by or "", MartSKUDaily.stat_date)
        stmt = select(MartSKUDaily).order_by(
            apply_sort_direction(sort_column, sort_dir),
            MartSKUDaily.id.desc(),
        )
        if account_id is not None:
            stmt = stmt.where(MartSKUDaily.account_id == account_id)
        if nm_id is not None:
            stmt = stmt.where(MartSKUDaily.nm_id == nm_id)
        if sku_id is not None:
            stmt = stmt.where(MartSKUDaily.sku_id == sku_id)
        if vendor_code is not None:
            stmt = stmt.where(MartSKUDaily.vendor_code.ilike(f"%{vendor_code}%"))
        if barcode is not None:
            stmt = stmt.where(MartSKUDaily.barcode.ilike(f"%{barcode}%"))
        if brand is not None:
            stmt = stmt.where(MartSKUDaily.brand.ilike(f"%{brand}%"))
        if subject_name is not None:
            stmt = stmt.where(MartSKUDaily.subject_name.ilike(f"%{subject_name}%"))
        if search is not None:
            pattern = f"%{search}%"
            stmt = stmt.where(
                or_(
                    MartSKUDaily.vendor_code.ilike(pattern),
                    MartSKUDaily.barcode.ilike(pattern),
                    MartSKUDaily.title.ilike(pattern),
                    MartSKUDaily.brand.ilike(pattern),
                    MartSKUDaily.subject_name.ilike(pattern),
                )
            )
        if has_manual_cost is not None:
            stmt = stmt.where(MartSKUDaily.has_manual_cost == has_manual_cost)
        if has_open_issues is not None:
            stmt = stmt.where(MartSKUDaily.has_open_issues == has_open_issues)
        if date_from is not None:
            stmt = stmt.where(MartSKUDaily.stat_date >= date_from)
        if date_to is not None:
            stmt = stmt.where(MartSKUDaily.stat_date <= date_to)
        return await self.list(session, statement=stmt, limit=limit, offset=offset)


class MartStockDailyRepository(SQLAlchemyRepository[MartStockDaily]):
    def __init__(self) -> None:
        super().__init__(MartStockDaily)

    async def list_filtered(
        self,
        session: AsyncSession,
        *,
        account_id: int | None = None,
        nm_id: int | None = None,
        sku_id: int | None = None,
        barcode: str | None = None,
        warehouse_name: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        sort_by: str | None = None,
        sort_dir: str = "desc",
        limit: int = 50,
        offset: int = 0,
    ) -> Page[MartStockDaily]:
        sort_map = {
            "stat_date": MartStockDaily.stat_date,
            "sku_id": MartStockDaily.sku_id,
            "nm_id": MartStockDaily.nm_id,
            "barcode": MartStockDaily.barcode,
            "warehouse_name": MartStockDaily.warehouse_name,
            "quantity": MartStockDaily.quantity,
            "days_of_stock": MartStockDaily.days_of_stock,
            "turnover_rate": MartStockDaily.turnover_rate,
        }
        sort_column = sort_map.get(sort_by or "", MartStockDaily.stat_date)
        stmt = select(MartStockDaily).order_by(
            apply_sort_direction(sort_column, sort_dir),
            MartStockDaily.id.desc(),
        )
        if account_id is not None:
            stmt = stmt.where(MartStockDaily.account_id == account_id)
        if nm_id is not None:
            stmt = stmt.where(MartStockDaily.nm_id == nm_id)
        if sku_id is not None:
            stmt = stmt.where(MartStockDaily.sku_id == sku_id)
        if barcode is not None:
            stmt = stmt.where(MartStockDaily.barcode.ilike(f"%{barcode}%"))
        if warehouse_name is not None:
            stmt = stmt.where(
                MartStockDaily.warehouse_name.ilike(f"%{warehouse_name}%")
            )
        if date_from is not None:
            stmt = stmt.where(MartStockDaily.stat_date >= date_from)
        if date_to is not None:
            stmt = stmt.where(MartStockDaily.stat_date <= date_to)
        return await self.list(session, statement=stmt, limit=limit, offset=offset)


class MartFinanceReconciliationRepository(
    SQLAlchemyRepository[MartFinanceReconciliation]
):
    def __init__(self) -> None:
        super().__init__(MartFinanceReconciliation)

    async def list_filtered(
        self,
        session: AsyncSession,
        *,
        account_id: int | None = None,
        nm_id: int | None = None,
        srid: str | None = None,
        barcode: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        status: str | None = None,
        only_diff: bool | None = None,
        sort_by: str | None = None,
        sort_dir: str = "desc",
        limit: int = 50,
        offset: int = 0,
    ) -> Page[MartFinanceReconciliation]:
        sort_map = {
            "stat_date": MartFinanceReconciliation.stat_date,
            "nm_id": MartFinanceReconciliation.nm_id,
            "srid": MartFinanceReconciliation.srid,
            "barcode": MartFinanceReconciliation.barcode,
            "status": MartFinanceReconciliation.status,
            "revenue_delta": MartFinanceReconciliation.revenue_delta,
            "for_pay_delta": MartFinanceReconciliation.for_pay_delta,
        }
        sort_column = sort_map.get(sort_by or "", MartFinanceReconciliation.stat_date)
        stmt = select(MartFinanceReconciliation).order_by(
            apply_sort_direction(sort_column, sort_dir),
            MartFinanceReconciliation.id.desc(),
        )
        if account_id is not None:
            stmt = stmt.where(MartFinanceReconciliation.account_id == account_id)
        if nm_id is not None:
            stmt = stmt.where(MartFinanceReconciliation.nm_id == nm_id)
        if srid is not None:
            stmt = stmt.where(MartFinanceReconciliation.srid == srid)
        if barcode is not None:
            stmt = stmt.where(MartFinanceReconciliation.barcode.ilike(f"%{barcode}%"))
        if date_from is not None:
            stmt = stmt.where(MartFinanceReconciliation.stat_date >= date_from)
        if date_to is not None:
            stmt = stmt.where(MartFinanceReconciliation.stat_date <= date_to)
        if status is not None:
            stmt = stmt.where(MartFinanceReconciliation.status == status)
        if only_diff:
            stmt = stmt.where(
                or_(
                    (MartFinanceReconciliation.revenue_delta.is_not(None))
                    & (MartFinanceReconciliation.revenue_delta != 0),
                    (MartFinanceReconciliation.for_pay_delta.is_not(None))
                    & (MartFinanceReconciliation.for_pay_delta != 0),
                )
            )
        return await self.list(session, statement=stmt, limit=limit, offset=offset)


class MartAccountExpenseDailyRepository(SQLAlchemyRepository[MartAccountExpenseDaily]):
    def __init__(self) -> None:
        super().__init__(MartAccountExpenseDaily)

    async def list_filtered(
        self,
        session: AsyncSession,
        *,
        account_id: int | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        sort_by: str | None = None,
        sort_dir: str = "desc",
        limit: int = 50,
        offset: int = 0,
    ) -> Page[MartAccountExpenseDaily]:
        sort_map = {
            "stat_date": MartAccountExpenseDaily.stat_date,
            "source_rows": MartAccountExpenseDaily.source_rows,
            "total_expense": MartAccountExpenseDaily.total_expense,
            "commission": MartAccountExpenseDaily.commission,
            "logistics": MartAccountExpenseDaily.logistics,
            "storage": MartAccountExpenseDaily.storage,
        }
        sort_column = sort_map.get(sort_by or "", MartAccountExpenseDaily.stat_date)
        stmt = select(MartAccountExpenseDaily).order_by(
            apply_sort_direction(sort_column, sort_dir),
            MartAccountExpenseDaily.id.desc(),
        )
        if account_id is not None:
            stmt = stmt.where(MartAccountExpenseDaily.account_id == account_id)
        if date_from is not None:
            stmt = stmt.where(MartAccountExpenseDaily.stat_date >= date_from)
        if date_to is not None:
            stmt = stmt.where(MartAccountExpenseDaily.stat_date <= date_to)
        return await self.list(session, statement=stmt, limit=limit, offset=offset)


class MartExpenseDailyRepository(SQLAlchemyRepository[MartExpenseDaily]):
    def __init__(self) -> None:
        super().__init__(MartExpenseDaily)


class MartReconciliationDailyRepository(SQLAlchemyRepository[MartReconciliationDaily]):
    def __init__(self) -> None:
        super().__init__(MartReconciliationDaily)

    async def list_filtered(
        self,
        session: AsyncSession,
        *,
        account_id: int | None = None,
        sku_id: int | None = None,
        nm_id: int | None = None,
        vendor_code: str | None = None,
        barcode: str | None = None,
        search: str | None = None,
        flag: str | None = None,
        status_bucket: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        sort_by: str | None = None,
        sort_dir: str = "desc",
        limit: int = 50,
        offset: int = 0,
    ) -> Page[MartReconciliationDaily]:
        sort_map = {
            "stat_date": MartReconciliationDaily.stat_date,
            "sku_id": MartReconciliationDaily.sku_id,
            "nm_id": MartReconciliationDaily.nm_id,
            "vendor_code": MartReconciliationDaily.vendor_code,
            "status_bucket": MartReconciliationDaily.status_bucket,
            "revenue_delta": MartReconciliationDaily.revenue_delta,
            "for_pay_delta": MartReconciliationDaily.for_pay_delta,
            "ad_spend": MartReconciliationDaily.ad_spend,
        }
        sort_column = sort_map.get(sort_by or "", MartReconciliationDaily.stat_date)
        stmt = select(MartReconciliationDaily).order_by(
            apply_sort_direction(sort_column, sort_dir),
            MartReconciliationDaily.id.desc(),
        )
        if account_id is not None:
            stmt = stmt.where(MartReconciliationDaily.account_id == account_id)
        if sku_id is not None:
            stmt = stmt.where(MartReconciliationDaily.sku_id == sku_id)
        if nm_id is not None:
            stmt = stmt.where(MartReconciliationDaily.nm_id == nm_id)
        if vendor_code is not None:
            stmt = stmt.where(
                MartReconciliationDaily.vendor_code.ilike(f"%{vendor_code}%")
            )
        if barcode is not None:
            stmt = stmt.where(MartReconciliationDaily.barcode.ilike(f"%{barcode}%"))
        if search is not None:
            pattern = f"%{search}%"
            stmt = stmt.where(
                or_(
                    MartReconciliationDaily.vendor_code.ilike(pattern),
                    MartReconciliationDaily.barcode.ilike(pattern),
                    MartReconciliationDaily.title.ilike(pattern),
                )
            )
        if flag is not None:
            flag_map = {
                "order_without_sale": MartReconciliationDaily.has_order_without_sale,
                "sale_without_finance": MartReconciliationDaily.has_sale_without_finance,
                "finance_without_sale": MartReconciliationDaily.has_finance_without_sale,
                "stock_without_sales": MartReconciliationDaily.has_stock_without_sales,
                "ad_spend_without_sales": MartReconciliationDaily.has_ad_spend_without_sales,
                "price_anomaly": MartReconciliationDaily.has_price_anomaly,
            }
            if flag == "any":
                stmt = stmt.where(
                    or_(
                        MartReconciliationDaily.has_order_without_sale.is_(True),
                        MartReconciliationDaily.has_sale_without_finance.is_(True),
                        MartReconciliationDaily.has_finance_without_sale.is_(True),
                        MartReconciliationDaily.has_stock_without_sales.is_(True),
                        MartReconciliationDaily.has_ad_spend_without_sales.is_(True),
                        MartReconciliationDaily.has_price_anomaly.is_(True),
                    )
                )
            elif flag in flag_map:
                stmt = stmt.where(flag_map[flag].is_(True))
        if status_bucket is not None:
            stmt = stmt.where(MartReconciliationDaily.status_bucket == status_bucket)
        if date_from is not None:
            stmt = stmt.where(MartReconciliationDaily.stat_date >= date_from)
        if date_to is not None:
            stmt = stmt.where(MartReconciliationDaily.stat_date <= date_to)
        return await self.list(session, statement=stmt, limit=limit, offset=offset)
