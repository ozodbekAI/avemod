from __future__ import annotations

import argparse
import asyncio
import json
from collections.abc import Iterable

from app.core.db import SessionLocal
from app.services.data_quality import DataQualityService
from app.services.marts import MartService
from app.services.sync import SyncOrchestrator

DEFAULT_DOMAINS = [
    "product_cards",
    "prices",
    "orders",
    "sales",
    "stocks",
    "finance",
    "supplies",
    "ads",
    "analytics",
    "tariffs",
    "documents",
]


def _print_event(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False, default=str), flush=True)


def _should_repeat(domain: str, run_details: dict | None) -> bool:
    details = run_details or {}
    if domain == "finance":
        return bool(details.get("detailsPending") or details.get("acquiringPending"))
    if domain == "supplies":
        return not bool(details.get("enrichmentDone"))
    return False


def _max_iterations(domain: str, overrides: dict[str, int]) -> int:
    if domain in overrides:
        return overrides[domain]
    if domain == "finance":
        return 12
    if domain == "supplies":
        return 20
    return 1


async def _run_domain(
    *,
    account_id: int,
    domain: str,
    trigger: str,
    max_iterations: int,
) -> list[dict]:
    results: list[dict] = []
    for iteration in range(1, max_iterations + 1):
        async with SessionLocal() as session:
            run = await SyncOrchestrator(session).trigger(
                account_id=account_id,
                domain=domain,
                trigger=trigger,
            )
            await session.commit()
            result = {
                "kind": "sync_run",
                "iteration": iteration,
                "domain": domain,
                "id": run.id,
                "status": run.status,
                "error_text": run.error_text,
                "details": run.details,
            }
            results.append(result)
            _print_event(result)
        if run.status not in {"completed", "partial"}:
            break
        if not _should_repeat(domain, run.details):
            break
    return results


async def _refresh_marts_and_dq(account_id: int) -> None:
    async with SessionLocal() as session:
        marts = await MartService().refresh_account(session, account_id=account_id)
        await session.commit()
        _print_event({"kind": "marts_refresh", "account_id": account_id, "result": marts})
    async with SessionLocal() as session:
        dq = await DataQualityService().run_checks(session, account_id=account_id)
        await session.commit()
        _print_event({"kind": "dq_run", "account_id": account_id, "result": dq})


async def _main(account_id: int, domains: Iterable[str], iteration_overrides: dict[str, int]) -> None:
    for domain in domains:
        await _run_domain(
            account_id=account_id,
            domain=domain,
            trigger="manual_full_resync",
            max_iterations=_max_iterations(domain, iteration_overrides),
        )
    await _refresh_marts_and_dq(account_id)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a full WB resync for one account.")
    parser.add_argument("--account-id", type=int, required=True)
    parser.add_argument(
        "--domains",
        nargs="*",
        default=DEFAULT_DOMAINS,
        help="Optional explicit domain order",
    )
    parser.add_argument(
        "--max-iterations",
        action="append",
        default=[],
        metavar="DOMAIN=N",
        help="Override repeat count for one domain, e.g. supplies=30",
    )
    args = parser.parse_args()
    overrides: dict[str, int] = {}
    for item in args.max_iterations:
        domain, _, raw_value = item.partition("=")
        if not domain or not raw_value:
            raise SystemExit(f"Invalid --max-iterations value: {item}")
        overrides[domain] = int(raw_value)
    asyncio.run(_main(args.account_id, args.domains, overrides))


if __name__ == "__main__":
    main()
