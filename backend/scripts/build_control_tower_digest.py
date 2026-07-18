#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

from sqlalchemy.exc import SQLAlchemyError

from app.core.db import SessionLocal
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
    parser = argparse.ArgumentParser(description="Build internal control-tower daily digest payload.")
    parser.add_argument("--account-id", type=int, required=True, help="Account id for the digest payload.")
    parser.add_argument("--date-from", help="Start date in YYYY-MM-DD format.")
    parser.add_argument("--date-to", help="End date in YYYY-MM-DD format.")
    parser.add_argument("--action-limit", type=int, default=10, help="Max actions to include.")
    parser.add_argument("--alert-limit", type=int, default=10, help="Max alerts to include.")
    parser.add_argument("--output", help="Optional JSON output file.")
    args = parser.parse_args()

    service = ControlTowerService()
    try:
        async with SessionLocal() as session:
            payload = await service.build_daily_digest_payload(
                session,
                account_id=args.account_id,
                date_from=_parse_date(args.date_from),
                date_to=_parse_date(args.date_to),
                action_limit=args.action_limit,
                alert_limit=args.alert_limit,
            )
    except SQLAlchemyError as error:
        payload = {
            "ok": False,
            "reason": "Control Tower digest requires an up-to-date database schema. Run `alembic upgrade head` first.",
            "error": str(error.__class__.__name__),
        }
        text = json.dumps(payload, indent=2, sort_keys=True, default=_json_default)
        if args.output:
            Path(args.output).write_text(text + "\n", encoding="utf-8")
        print(text)
        return 1

    text = json.dumps({"ok": True, **payload}, indent=2, sort_keys=True, default=_json_default)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


def main() -> None:
    raise SystemExit(asyncio.run(_run()))


if __name__ == "__main__":
    main()
