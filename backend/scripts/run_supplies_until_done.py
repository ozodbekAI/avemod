from __future__ import annotations

import asyncio

from sqlalchemy import select

from app.core.db import SessionLocal
from app.models.accounts import WBAccount
from app.modules.supplies.sync import SuppliesSyncService

MAX_BATCHES = 100


async def main() -> None:
    async with SessionLocal() as session:
        account = (
            await session.execute(select(WBAccount).where(WBAccount.id == 1))
        ).scalar_one()
        service = SuppliesSyncService()
        for batch in range(1, MAX_BATCHES + 1):
            result = await service.run(session, account=account)
            await session.commit()
            print({"batch": batch, **result}, flush=True)
            if result.get("enrichmentDone"):
                break


if __name__ == "__main__":
    asyncio.run(main())
