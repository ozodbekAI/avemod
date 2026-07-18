from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from app.core.db import SessionLocal
from app.services.manual_costs import ManualCostService


async def main(account_id: int, output: str) -> None:
    async with SessionLocal() as session:
        csv_text = await ManualCostService().build_template_csv(
            session,
            account_id=account_id,
        )
    path = Path(output)
    path.write_text(csv_text, encoding="utf-8")
    print(path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--account-id", type=int, required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    asyncio.run(main(args.account_id, args.output))
