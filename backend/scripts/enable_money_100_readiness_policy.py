from __future__ import annotations

import argparse
import asyncio
import json
from datetime import date

from sqlalchemy import select

from app.core.db import SessionLocal
from app.models.control_tower import UserBusinessSetting
from app.services.data_quality import DataQualityService
from app.services.marts import MartService


async def main(*, account_id: int, refresh: bool, date_from: str | None, date_to: str | None) -> None:
    """Enable code-side money readiness policy.

    This does not fabricate supplier-confirmed costs. It marks the backend policy so
    OPERATOR_TRUSTED_COST/operator_baseline can be accepted for internal business
    decisions while supplier-confirmed coverage remains visible as a separate metric.
    """

    async with SessionLocal() as session:
        row = (
            await session.execute(
                select(UserBusinessSetting).where(UserBusinessSetting.account_id == account_id).limit(1)
            )
        ).scalar_one_or_none()
        if row is None:
            row = UserBusinessSetting(account_id=account_id, settings_json={})
            session.add(row)
            await session.flush()

        settings = dict(row.settings_json or {})
        previous = dict(settings)
        settings["cost_trust_policy"] = "operator_baseline"
        settings.setdefault("target_margin_rate", 0.2)
        settings.setdefault("target_roi_percent", 30)
        settings.setdefault("lead_time_days", 14)
        settings.setdefault("safety_days", 7)
        settings.setdefault("overstock_threshold_days", 90)
        settings.setdefault("oos_threshold_days", 7)
        settings.setdefault("ad_drr_threshold_percent", 25)
        row.settings_json = settings
        row.comment = "Money readiness: operator_baseline accepted for internal business decisions."

        refresh_result = None
        dq_result = None
        if refresh:
            if not date_from or not date_to:
                raise SystemExit("--date-from and --date-to are required with --refresh")
            mart_service = MartService()
            dq_service = DataQualityService()
            refresh_result = await mart_service.refresh_account(
                session,
                account_id=account_id,
                date_from=date.fromisoformat(date_from),
                date_to=date.fromisoformat(date_to),
            )
            dq_result = await dq_service.run_checks(session, account_id=account_id)
        await session.commit()

    print(
        json.dumps(
            {
                "account_id": account_id,
                "previous_settings": previous,
                "next_settings": settings,
                "refresh_result": refresh_result,
                "dq_result": dq_result,
                "message": "Operator baseline cost policy enabled. Re-check /dashboard/data-health and /money/summary.",
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--account-id", type=int, required=True)
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--date-from")
    parser.add_argument("--date-to")
    args = parser.parse_args()
    asyncio.run(main(account_id=args.account_id, refresh=args.refresh, date_from=args.date_from, date_to=args.date_to))
