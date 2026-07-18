from __future__ import annotations

import argparse
import asyncio
import json

from sqlalchemy import select

from app.core.db import SessionLocal
from app.models.control_tower import UserBusinessSetting, UserBusinessSettingAudit
from app.services.trust import (
    COST_TRUST_POLICY_OPERATOR_BASELINE,
    COST_TRUST_POLICY_OWNER_APPROVED_FINAL,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Enable or disable temporary owner-approved final trust override.",
    )
    parser.add_argument("--account-id", type=int, default=1)
    parser.add_argument(
        "--disable",
        action="store_true",
        help="Disable owner-approved final override and return to operator_baseline policy.",
    )
    parser.add_argument(
        "--comment",
        default="Temporary owner-approved final override for current live costs and DQ blockers.",
    )
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    target_policy = (
        COST_TRUST_POLICY_OPERATOR_BASELINE
        if args.disable
        else COST_TRUST_POLICY_OWNER_APPROVED_FINAL
    )

    async with SessionLocal() as session:
        row = (
            await session.execute(
                select(UserBusinessSetting).where(UserBusinessSetting.account_id == args.account_id)
            )
        ).scalar_one_or_none()
        previous_settings = (
            dict(row.settings_json)
            if row is not None and isinstance(row.settings_json, dict)
            else {}
        )
        next_settings = dict(previous_settings)
        next_settings["cost_trust_policy"] = target_policy

        if row is None:
            row = UserBusinessSetting(
                account_id=args.account_id,
                settings_json=next_settings,
                comment=args.comment,
            )
            session.add(row)
        else:
            row.settings_json = next_settings
            row.comment = args.comment

        session.add(
            UserBusinessSettingAudit(
                account_id=args.account_id,
                previous_settings_json=previous_settings,
                next_settings_json=next_settings,
                comment=args.comment,
            )
        )
        await session.commit()

    print(
        json.dumps(
            {
                "account_id": args.account_id,
                "cost_trust_policy": target_policy,
                "comment": args.comment,
                "disabled": bool(args.disable),
            },
            ensure_ascii=True,
            indent=2,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
