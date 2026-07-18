from __future__ import annotations

import argparse
import asyncio
import json
import sys

from app.core.db import SessionLocal
from app.services.sync import SyncOrchestrator


async def _run(account_id: int, domain: str, trigger: str) -> int:
    async with SessionLocal() as session:
        run = await SyncOrchestrator(session).trigger(
            account_id=account_id,
            domain=domain,
            trigger=trigger,
        )
        await session.commit()
        print(
            json.dumps(
                {
                    "id": run.id,
                    "account_id": account_id,
                    "domain": run.domain,
                    "status": run.status,
                    "error_text": run.error_text,
                    "details": run.details,
                },
                ensure_ascii=False,
                default=str,
            )
        )
        return 0 if run.status == "completed" else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one WB sync domain and print JSON result.")
    parser.add_argument("--account-id", type=int, required=True)
    parser.add_argument("--domain", required=True)
    parser.add_argument("--trigger", default="manual")
    args = parser.parse_args()
    return asyncio.run(_run(account_id=args.account_id, domain=args.domain, trigger=args.trigger))


if __name__ == "__main__":
    sys.exit(main())
