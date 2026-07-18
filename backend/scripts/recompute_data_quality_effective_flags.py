from __future__ import annotations

import argparse
import asyncio
import json

from sqlalchemy import select

from app.core.db import SessionLocal
from app.models.data_quality import DataQualityIssue
from app.services.data_quality import DataQualityService


async def main(*, account_id: int | None, only_open: bool) -> None:
    service = DataQualityService()
    summary = {
        "account_id": account_id,
        "only_open": only_open,
        "scanned": 0,
        "updated": 0,
        "effective_true": 0,
        "effective_false": 0,
    }

    async with SessionLocal() as session:
        stmt = select(DataQualityIssue)
        if account_id is not None:
            stmt = stmt.where(DataQualityIssue.account_id == account_id)
        if only_open:
            stmt = stmt.where(DataQualityIssue.resolved_at.is_(None))

        issues = list((await session.execute(stmt)).scalars())
        for issue in issues:
            summary["scanned"] += 1
            before = bool(getattr(issue, "effective_financial_final_blocker", False))
            service._normalize_issue_runtime_flags(issue)
            after = bool(issue.effective_financial_final_blocker)
            if before != after:
                summary["updated"] += 1
            if after:
                summary["effective_true"] += 1
            else:
                summary["effective_false"] += 1

        await session.commit()

    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--account-id", type=int)
    parser.add_argument("--all", action="store_true", help="Recompute both open and resolved issues.")
    args = parser.parse_args()
    asyncio.run(main(account_id=args.account_id, only_open=not args.all))
