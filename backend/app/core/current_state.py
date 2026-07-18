from __future__ import annotations

from sqlalchemy import Select, func, select

from app.models.orders import WBOrder
from app.models.sales import WBSale


def orders_current_subquery(name: str = "v_wb_orders_current") -> Select:
    ranked = select(
        *WBOrder.__table__.c,
        func.row_number()
        .over(
            partition_by=(
                WBOrder.account_id,
                WBOrder.srid,
                WBOrder.nm_id,
                WBOrder.barcode,
                WBOrder.order_id,
            ),
            order_by=(WBOrder.last_change_date.desc(), WBOrder.id.desc()),
        )
        .label("rn"),
    ).subquery(f"{name}_ranked")
    return (
        select(*[column for column in ranked.c if column.key != "rn"])
        .where(ranked.c.rn == 1)
        .subquery(name)
    )


def sales_current_subquery(name: str = "v_wb_sales_current") -> Select:
    ranked = select(
        *WBSale.__table__.c,
        func.row_number()
        .over(
            partition_by=(
                WBSale.account_id,
                WBSale.srid,
                WBSale.nm_id,
                WBSale.barcode,
                WBSale.sale_id,
            ),
            order_by=(WBSale.last_change_date.desc(), WBSale.id.desc()),
        )
        .label("rn"),
    ).subquery(f"{name}_ranked")
    return (
        select(*[column for column in ranked.c if column.key != "rn"])
        .where(ranked.c.rn == 1)
        .subquery(name)
    )
