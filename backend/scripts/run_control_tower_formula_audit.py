#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import select

from app.core.db import SessionLocal
from app.models.accounts import WBAccount
from app.services.control_tower import ControlTowerService


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    return date.fromisoformat(value)


def _json_default(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


async def _run() -> int:
    parser = argparse.ArgumentParser(description="Run and persist Stage 3 control-tower formula audits.")
    parser.add_argument("--account-id", type=int, help="Run audit for one account only.")
    parser.add_argument("--date-from", help="Start date in YYYY-MM-DD format.")
    parser.add_argument("--date-to", help="End date in YYYY-MM-DD format.")
    parser.add_argument("--sample-limit", type=int, default=5, help="Number of article-audit samples to include.")
    parser.add_argument("--dry-run", action="store_true", help="Build runs but rollback instead of committing.")
    parser.add_argument("--output", help="Optional JSON output file.")
    args = parser.parse_args()

    service = ControlTowerService()
    actual_from = _parse_date(args.date_from)
    actual_to = _parse_date(args.date_to)

    try:
        async with SessionLocal() as session:
            if args.account_id is not None:
                account_ids = [args.account_id]
            else:
                account_ids = list(
                    (
                        await session.execute(
                            select(WBAccount.id).where(WBAccount.is_active.is_(True)).order_by(WBAccount.id.asc())
                        )
                    ).scalars()
                )

            runs: list[dict[str, Any]] = []
            for account_id in account_ids:
                run = await service.run_formula_audit(
                    session,
                    account_id=int(account_id),
                    date_from=actual_from,
                    date_to=actual_to,
                    sample_limit=args.sample_limit,
                )
                runs.append(
                    {
                        "id": run.id,
                        "account_id": run.account_id,
                        "scope": run.scope,
                        "status": run.status,
                        "passed": run.passed,
                        "started_at": run.started_at,
                        "finished_at": run.finished_at,
                        "result": dict(run.result_json or {}),
                    }
                )

            if args.dry_run:
                await session.rollback()
            else:
                await session.commit()
    except SQLAlchemyError as error:
        payload = {
            "ok": False,
            "reason": "Control Tower formula audit requires an up-to-date database schema. Run `alembic upgrade head` first.",
            "error": str(error.__class__.__name__),
        }
        text = json.dumps(payload, indent=2, sort_keys=True, default=_json_default)
        if args.output:
            Path(args.output).write_text(text + "\n", encoding="utf-8")
        print(text)
        return 1

    payload = {
        "ok": True,
        "date_from": actual_from,
        "date_to": actual_to,
        "dry_run": args.dry_run,
        "runs": runs,
    }
    text = json.dumps(payload, indent=2, sort_keys=True, default=_json_default)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


def main() -> None:
    raise SystemExit(asyncio.run(_run()))


if __name__ == "__main__":
    main()
