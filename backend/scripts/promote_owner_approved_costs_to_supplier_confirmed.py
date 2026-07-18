from __future__ import annotations

import argparse
import asyncio
import json

from sqlalchemy import func, select, update

from app.core.db import SessionLocal
from app.core.time import utcnow
from app.models.manual_costs import ManualCost


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Promote operator-approved manual costs into supplier_confirmed classification.",
    )
    parser.add_argument("--account-id", type=int, default=1)
    parser.add_argument(
        "--supplier-name",
        default="OWNER_APPROVED_CURRENT_COST",
        help="Supplier label to assign so rows stop being treated as operator baseline.",
    )
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    promoted_at = utcnow()

    async with SessionLocal() as session:
        before = (
            await session.execute(
                select(
                    func.count(),
                    func.count().filter(ManualCost.is_supplier_confirmed.is_(True)),
                ).where(ManualCost.account_id == args.account_id)
            )
        ).one()

        promote_stmt = (
            update(ManualCost)
            .where(
                ManualCost.account_id == args.account_id,
                ManualCost.is_placeholder.is_not(True),
                ManualCost.is_ambiguous.is_not(True),
                ManualCost.is_supplier_confirmed.is_not(True),
                (
                    (ManualCost.cost_source == "operator_trusted_manual")
                    | (ManualCost.cost_source == "operator_baseline")
                    | (ManualCost.supplier == "OPERATOR_TRUSTED_COST")
                ),
            )
            .values(
                cost_source="supplier_confirmed",
                supplier=args.supplier_name,
                is_supplier_confirmed=True,
                supplier_confirmed_at=promoted_at,
                comment="Promoted from operator baseline into supplier_confirmed by owner approval.",
            )
        )
        result = await session.execute(promote_stmt)
        await session.commit()

        after = (
            await session.execute(
                select(
                    func.count(),
                    func.count().filter(ManualCost.is_supplier_confirmed.is_(True)),
                ).where(ManualCost.account_id == args.account_id)
            )
        ).one()

    print(
        json.dumps(
            {
                "account_id": args.account_id,
                "rows_total_before": int(before[0] or 0),
                "rows_supplier_confirmed_before": int(before[1] or 0),
                "rows_promoted": int(result.rowcount or 0),
                "rows_total_after": int(after[0] or 0),
                "rows_supplier_confirmed_after": int(after[1] or 0),
                "supplier_name": args.supplier_name,
                "promoted_at": promoted_at.isoformat(),
            },
            ensure_ascii=True,
            indent=2,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
