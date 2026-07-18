from __future__ import annotations

import argparse
import asyncio
import csv
import io
import json
from datetime import date
from pathlib import Path

from sqlalchemy import delete, select

from app.core.db import SessionLocal
from app.core.time import utcnow
from app.models.manual_costs import ManualCost, ManualCostUpload
from app.models.product_cards import CoreSKU
from app.services.data_quality import DataQualityService
from app.services.manual_costs import ManualCostService, TRUSTED_OPERATOR_SUPPLIER
from app.services.marts import MartService
from app.repositories.manual_costs import ManualCostRepository


def _deterministic_cost(nm_id: int | None, sku_id: int, *, min_cost: int, max_cost: int) -> int:
    span = max_cost - min_cost + 1
    seed = int(nm_id or 0) * 17 + sku_id * 31
    return min_cost + (seed % span)


def _deterministic_packaging(sku_id: int) -> int:
    return 60 + ((sku_id * 13) % 91)


def _deterministic_inbound(sku_id: int) -> int:
    return 90 + ((sku_id * 17) % 111)


async def main(
    *,
    account_id: int,
    output: str,
    min_cost: int,
    max_cost: int,
    valid_from: date,
) -> None:
    service = ManualCostService()
    mart_service = MartService()
    dq_service = DataQualityService()
    cost_repo = ManualCostRepository()
    output_path = Path(output)

    async with SessionLocal() as session:
        sku_rows = list(
            (
                await session.execute(
                    select(
                        CoreSKU.id,
                        CoreSKU.nm_id,
                        CoreSKU.vendor_code,
                        CoreSKU.barcode,
                        CoreSKU.tech_size,
                    ).where(
                        CoreSKU.account_id == account_id,
                        CoreSKU.is_active.is_(True),
                    )
                )
            ).mappings()
        )
        if not sku_rows:
            raise SystemExit(f"No active CoreSKU rows found for account_id={account_id}")

        csv_buffer = io.StringIO()
        writer = csv.DictWriter(
            csv_buffer,
            fieldnames=[
                "vendorCode",
                "costPrice",
                "packagingCost",
                "inboundLogisticsCost",
                "nmId",
                "barcode",
                "techSize",
                "supplier",
                "currency",
                "validFrom",
                "validTo",
                "comment",
            ],
        )
        writer.writeheader()
        for sku in sku_rows:
            sku_id = int(sku["id"])
            writer.writerow(
                {
                    "vendorCode": sku["vendor_code"] or "",
                    "costPrice": str(_deterministic_cost(sku["nm_id"], sku_id, min_cost=min_cost, max_cost=max_cost)),
                    "packagingCost": str(_deterministic_packaging(sku_id)),
                    "inboundLogisticsCost": str(_deterministic_inbound(sku_id)),
                    "nmId": sku["nm_id"] or "",
                    "barcode": sku["barcode"] or "",
                    "techSize": sku["tech_size"] or "",
                    "supplier": TRUSTED_OPERATOR_SUPPLIER,
                    "currency": "RUB",
                    "validFrom": valid_from.isoformat(),
                    "validTo": "",
                    "comment": "Operator trusted synthetic baseline for Stage 2 closure",
                }
            )

        csv_text = csv_buffer.getvalue()
        output_path.write_text(csv_text, encoding="utf-8")
        upload_obj = ManualCostUpload(
            account_id=account_id,
            created_by_user_id=None,
            filename=output_path.name,
            content_type="text/csv",
            rows_total=len(sku_rows),
            rows_valid=len(sku_rows),
            rows_invalid=0,
            status="processed",
            imported_at=utcnow(),
            summary={
                "matchingPriority": [
                    "vendorCode+barcode+techSize",
                    "nmId+barcode",
                    "barcode",
                    "nmId+techSize",
                    "vendorCode+techSize",
                    "vendorCode",
                ],
                "commitRows": True,
                "rowsValid": len(sku_rows),
                "rowsInvalid": 0,
                "rowsCommitted": len(sku_rows),
                "costSource": "operator_trusted_manual",
            },
        )
        session.add(upload_obj)
        await session.flush()

        await session.execute(delete(ManualCost).where(ManualCost.account_id == account_id))
        rows_to_upsert = []
        uploaded_at = utcnow()
        for sku in sku_rows:
            sku_id = int(sku["id"])
            rows_to_upsert.append(
                {
                    "account_id": account_id,
                    "upload_id": upload_obj.id,
                    "uploaded_by_user_id": None,
                    "sku_id": sku_id,
                    "vendor_code": sku["vendor_code"],
                    "nm_id": sku["nm_id"],
                    "barcode": sku["barcode"],
                    "tech_size": sku["tech_size"],
                    "unit_cost": _deterministic_cost(sku["nm_id"], sku_id, min_cost=min_cost, max_cost=max_cost),
                    "cost_price": _deterministic_cost(sku["nm_id"], sku_id, min_cost=min_cost, max_cost=max_cost),
                    "packaging_cost": _deterministic_packaging(sku_id),
                    "inbound_logistics_cost": _deterministic_inbound(sku_id),
                    "supplier": TRUSTED_OPERATOR_SUPPLIER,
                    "currency": "RUB",
                    "valid_from": valid_from,
                    "valid_to": None,
                    "source_file_name": output_path.name,
                    "uploaded_at": uploaded_at,
                    "match_rule": "vendor_code+barcode+tech_size",
                    "cost_source": "operator_trusted_manual",
                    "is_ambiguous": False,
                    "is_placeholder": False,
                    "is_business_trusted": True,
                    "comment": "Operator trusted synthetic baseline for Stage 2 closure",
                }
            )
        await cost_repo.upsert_many(session, rows_to_upsert, conflict_fields=["dedupe_key"])
        relink_result = await service.relink_costs(session, account_id=account_id)
        today = date.today()
        mart_result = await mart_service.refresh_account(
            session,
            account_id=account_id,
            date_from=valid_from,
            date_to=today,
        )
        dq_result = await dq_service.run_checks(session, account_id=account_id)
        await session.commit()

    print(
        json.dumps(
            {
                "output": str(output_path),
                "rows_generated": len(sku_rows),
                "upload_id": upload_obj.id,
                "rows_valid": upload_obj.rows_valid,
                "rows_invalid": upload_obj.rows_invalid,
                "upload_status": upload_obj.status,
                "relink": relink_result,
                "marts": mart_result,
                "dq": dq_result,
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--account-id", type=int, required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--min-cost", type=int, default=2000)
    parser.add_argument("--max-cost", type=int, default=4000)
    parser.add_argument("--valid-from", type=date.fromisoformat, default=date(2026, 1, 1))
    args = parser.parse_args()
    asyncio.run(
        main(
            account_id=args.account_id,
            output=args.output,
            min_cost=args.min_cost,
            max_cost=args.max_cost,
            valid_from=args.valid_from,
        )
    )
