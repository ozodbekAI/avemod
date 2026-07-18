#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


DEFAULT_BASE_URL = "http://127.0.0.1:8000/api/v1"
TOKEN_ENV = "FINANCE_BACKEND_TOKEN"
BASE_URL_ENV = "FINANCE_BACKEND_BASE_URL"


@dataclass
class SmokeResult:
    name: str
    status: str
    detail: str
    http_status: int | None = None
    duration_ms: float | None = None


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _join_url(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}"


def _request_json(
    base_url: str,
    path: str,
    *,
    token: str | None,
    query: dict[str, Any] | None = None,
    timeout_seconds: float,
) -> tuple[int, Any, float]:
    url = _join_url(base_url, path)
    if query:
        url = f"{url}?{urlencode({key: value for key, value in query.items() if value is not None}, doseq=True)}"
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    request = Request(url, headers=headers, method="GET")
    started = time.perf_counter()
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            body = response.read().decode("utf-8")
            return int(response.status), json.loads(body) if body else None, (time.perf_counter() - started) * 1000
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(body) if body else None
        except json.JSONDecodeError:
            payload = {"body": body[:500]}
        return int(exc.code), payload, (time.perf_counter() - started) * 1000
    except URLError as exc:
        raise RuntimeError(str(exc.reason)) from exc


def _ok(name: str, detail: str, http_status: int | None = None, duration_ms: float | None = None) -> SmokeResult:
    return SmokeResult(name=name, status="ok", detail=detail, http_status=http_status, duration_ms=duration_ms)


def _fail(name: str, detail: str, http_status: int | None = None, duration_ms: float | None = None) -> SmokeResult:
    return SmokeResult(name=name, status="fail", detail=detail, http_status=http_status, duration_ms=duration_ms)


def _skip(name: str, detail: str) -> SmokeResult:
    return SmokeResult(name=name, status="skipped", detail=detail)


def _check_health(base_url: str, timeout_seconds: float) -> SmokeResult:
    name = "health"
    try:
        status, payload, duration_ms = _request_json(base_url, "/health", token=None, timeout_seconds=timeout_seconds)
    except RuntimeError as exc:
        return _fail(name, f"request failed: {exc}")
    if status == 200 and isinstance(payload, dict) and payload.get("status") == "ok":
        return _ok(name, "GET /health returned status=ok", status, duration_ms)
    return _fail(name, f"unexpected response: {_json_dumps(payload)}", status, duration_ms)


def _check_auth_me(base_url: str, token: str | None, timeout_seconds: float) -> SmokeResult:
    name = "auth_me"
    if not token:
        return _skip(name, f"{TOKEN_ENV} not set and --token not provided")
    try:
        status, payload, duration_ms = _request_json(base_url, "/auth/me", token=token, timeout_seconds=timeout_seconds)
    except RuntimeError as exc:
        return _fail(name, f"request failed: {exc}")
    if status == 200 and isinstance(payload, dict) and "id" in payload:
        return _ok(name, "GET /auth/me returned current user payload", status, duration_ms)
    return _fail(name, f"unexpected response: {_json_dumps(payload)}", status, duration_ms)


def _check_accounts(base_url: str, token: str | None, timeout_seconds: float) -> SmokeResult:
    name = "accounts"
    if not token:
        return _skip(name, f"{TOKEN_ENV} not set and --token not provided")
    try:
        status, payload, duration_ms = _request_json(
            base_url,
            "/accounts",
            token=token,
            query={"limit": 1, "offset": 0},
            timeout_seconds=timeout_seconds,
        )
    except RuntimeError as exc:
        return _fail(name, f"request failed: {exc}")
    if status == 200 and isinstance(payload, dict) and {"total", "items"}.issubset(payload):
        return _ok(name, "GET /accounts returned a paginated account payload", status, duration_ms)
    if status == 403:
        return _ok(name, "GET /accounts returned 403 for non-superuser token, permission boundary is enforced", status, duration_ms)
    return _fail(name, f"unexpected response: {_json_dumps(payload)}", status, duration_ms)


def _check_portal_endpoint(
    base_url: str,
    token: str | None,
    *,
    name: str,
    path: str,
    query: dict[str, Any] | None,
    expected_keys: set[str],
    timeout_seconds: float,
) -> SmokeResult:
    if not token:
        return _skip(name, f"{TOKEN_ENV} not set and --token not provided")
    try:
        status, payload, duration_ms = _request_json(base_url, path, token=token, query=query, timeout_seconds=timeout_seconds)
    except RuntimeError as exc:
        return _fail(name, f"request failed: {exc}")
    if status == 200 and isinstance(payload, dict) and expected_keys.issubset(payload):
        return _ok(name, f"GET {path} returned expected portal shape", status, duration_ms)
    return _fail(name, f"unexpected response: {_json_dumps(payload)}", status, duration_ms)


def _print_timing_table(results: list[SmokeResult]) -> None:
    timed = [result for result in results if result.duration_ms is not None]
    if not timed:
        return
    print("")
    print("Response time table")
    print(f"{'check':<28} {'http':>5} {'status':>8} {'ms':>10}")
    print(f"{'-' * 28} {'-' * 5:>5} {'-' * 8:>8} {'-' * 10:>10}")
    for result in timed:
        http = str(result.http_status) if result.http_status is not None else "-"
        print(f"{result.name:<28} {http:>5} {result.status:>8} {result.duration_ms:>10.1f}")


def run_smoke(
    *,
    base_url: str,
    token: str | None,
    account_id: int | None,
    nm_id: int | None,
    timeout_seconds: float,
) -> list[SmokeResult]:
    results = [_check_health(base_url, timeout_seconds)]
    results.append(_check_auth_me(base_url, token, timeout_seconds))
    results.append(_check_accounts(base_url, token, timeout_seconds))
    portal_query = {"account_id": account_id} if account_id is not None else {}
    results.append(
        _check_portal_endpoint(
            base_url,
            token,
            name="portal_modules_health",
            path="/portal/modules/health",
            query=portal_query,
            expected_keys={"finance", "checker", "stockops", "grouping"},
            timeout_seconds=timeout_seconds,
        )
    )
    results.append(
        _check_portal_endpoint(
            base_url,
            token,
            name="portal_overview",
            path="/portal/overview",
            query={**portal_query, "limit": 5},
            expected_keys={"module_health", "unavailable_sources"},
            timeout_seconds=timeout_seconds,
        )
    )
    results.append(
        _check_portal_endpoint(
            base_url,
            token,
            name="portal_doctor",
            path="/portal/doctor",
            query={**portal_query, "period": "7d"},
            expected_keys={"summary", "unavailable_sources", "trust_state"},
            timeout_seconds=timeout_seconds,
        )
    )
    results.append(
        _check_portal_endpoint(
            base_url,
            token,
            name="portal_actions",
            path="/portal/actions",
            query={**portal_query, "limit": 5, "offset": 0},
            expected_keys={"total", "items", "unavailable_sources"},
            timeout_seconds=timeout_seconds,
        )
    )
    results.append(
        _check_portal_endpoint(
            base_url,
            token,
            name="portal_products",
            path="/portal/products",
            query={**portal_query, "limit": 5, "offset": 0},
            expected_keys={"total", "items", "unavailable_sources"},
            timeout_seconds=timeout_seconds,
        )
    )
    if nm_id is not None:
        results.append(
            _check_portal_endpoint(
                base_url,
                token,
                name="portal_product_360",
                path=f"/portal/products/{nm_id}",
                query=portal_query,
                expected_keys={"nm_id", "identity", "money", "actions", "unavailable_sources"},
                timeout_seconds=timeout_seconds,
            )
        )
    else:
        results.append(_skip("portal_product_360", "--nm-id not provided"))
    results.append(
        _check_portal_endpoint(
            base_url,
            token,
            name="portal_reputation_inbox",
            path="/portal/reputation/inbox",
            query={**portal_query, "limit": 5, "offset": 0},
            expected_keys={"status", "items", "unavailable_sources"},
            timeout_seconds=timeout_seconds,
        )
    )
    results.append(
        _check_portal_endpoint(
            base_url,
            token,
            name="portal_cases",
            path="/portal/cases",
            query={**portal_query, "limit": 5, "offset": 0},
            expected_keys={"status", "items", "unavailable_sources"},
            timeout_seconds=timeout_seconds,
        )
    )
    results.append(
        _check_portal_endpoint(
            base_url,
            token,
            name="portal_results",
            path="/portal/results",
            query={**portal_query, "limit": 5, "offset": 0},
            expected_keys={"status", "items", "unavailable_sources"},
            timeout_seconds=timeout_seconds,
        )
    )
    return results


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Smoke-test the current finance backend HTTP surface without requiring "
            "real marketplace tokens. Start the backend separately before running."
        )
    )
    parser.add_argument("--base-url", default=os.getenv(BASE_URL_ENV, DEFAULT_BASE_URL))
    parser.add_argument("--token", default=os.getenv(TOKEN_ENV), help=f"Optional bearer token. Prefer {TOKEN_ENV}.")
    parser.add_argument("--account-id", type=int, default=None, help="Optional finance account_id for portal checks.")
    parser.add_argument("--nm-id", type=int, default=None, help="Optional nm_id for Product 360 smoke check.")
    parser.add_argument("--timeout-seconds", type=float, default=5.0)
    args = parser.parse_args()

    started = time.time()
    results = run_smoke(
        base_url=args.base_url,
        token=args.token,
        account_id=args.account_id,
        nm_id=args.nm_id,
        timeout_seconds=args.timeout_seconds,
    )
    failed = [result for result in results if result.status == "fail"]

    print("Finance backend smoke")
    print(f"base_url={args.base_url.rstrip('/')}")
    print(f"token_provided={bool(args.token)}")
    if args.account_id is not None:
        print(f"account_id={args.account_id}")
    print(f"duration_seconds={time.time() - started:.2f}")
    for result in results:
        status = result.status.upper()
        http = f" http={result.http_status}" if result.http_status is not None else ""
        timing = f" {result.duration_ms:.1f}ms" if result.duration_ms is not None else ""
        print(f"- {status} {result.name}{http}{timing}: {result.detail}")
    _print_timing_table(results)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
