#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import Any

import httpx

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from scripts.run_full_runtime_endpoint_audit import (
    AuditConfig,
    hydrate_runtime_config_from_db,
    normalize_prefix,
    sanitize,
    start_local_backend_if_needed,
    stop_local_backend,
    write_json,
    write_text,
)


REPORT_PATH = REPO_ROOT / "reports" / "reputation_disabled_mode_contract.md"
JSON_PATH = REPO_ROOT / "reports" / "reputation_disabled_mode_contract.json"
SAFE_DISABLED = {"disabled", "not_configured", "unavailable", "empty", "degraded"}


def _config() -> AuditConfig:
    return AuditConfig(
        base_url=(os.getenv("BASE_URL") or "").strip().rstrip("/") or None,
        api_prefix=normalize_prefix(os.getenv("API_PREFIX")),
        access_token=(os.getenv("ACCESS_TOKEN") or "").strip() or None,
        account_id=(os.getenv("ACCOUNT_ID") or "").strip() or None,
        audit_env=(os.getenv("AUDIT_ENV") or "local").strip().lower(),
        output_dir=REPO_ROOT / "reports" / "reputation_disabled_runtime",
        run_commands=False,
    )


def _url(config: AuditConfig, path: str) -> str:
    base = str(config.base_url).rstrip("/")
    if base.endswith(config.api_prefix):
        return f"{base}{path}"
    return f"{base}{config.api_prefix}{path}"


def _request(client: httpx.Client, config: AuditConfig, method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
    started = time.perf_counter()
    response = client.request(method, _url(config, path), params={"account_id": config.account_id} if method == "GET" else None, json=body)
    try:
        raw_body: Any = response.json()
    except Exception:
        raw_body = {"text": response.text[:500]}
    clean_body, redactions = sanitize(raw_body)
    status = clean_body.get("status") if isinstance(clean_body, dict) else None
    expected = response.status_code < 300 and (status in SAFE_DISABLED or path.endswith("/settings"))
    if method != "GET":
        expected = response.status_code in {400, 403, 404, 409, 422} or status in SAFE_DISABLED
    return {
        "method": method,
        "path": path,
        "status_code": response.status_code,
        "duration_ms": int((time.perf_counter() - started) * 1000),
        "body_status": status,
        "expected_safe_disabled": expected,
        "body_keys": list(clean_body.keys()) if isinstance(clean_body, dict) else [],
        "redactions": redactions,
    }


def main() -> int:
    os.environ["REPUTATION_ENABLED"] = "false"
    os.environ["ENABLE_REPUTATION_PUBLISH"] = "false"
    os.environ["ENABLE_REPUTATION_WRITE_ACTIONS"] = "false"
    config = _config()
    setup = hydrate_runtime_config_from_db(config)
    server_process, server_log, server_status = start_local_backend_if_needed(config, config.output_dir)
    try:
        if not config.access_token or not config.account_id:
            raise RuntimeError(f"missing token/account after hydrate: {setup}")
        headers = {"Authorization": f"Bearer {config.access_token}", "Accept": "application/json"}
        with httpx.Client(headers=headers, timeout=httpx.Timeout(30.0, connect=5.0), follow_redirects=True) as client:
            results = [
                _request(client, config, "GET", "/portal/reputation/summary"),
                _request(client, config, "GET", "/portal/reputation/inbox"),
                _request(client, config, "GET", "/portal/reputation/settings"),
                _request(client, config, "POST", "/portal/reputation/items/runtime-audit-missing/draft", {"dry_run": True}),
                _request(client, config, "POST", "/portal/reputation/drafts/runtime-audit-missing/publish", {"confirm": False}),
            ]
        report = {
            "setup": setup,
            "server": server_status,
            "account_id": config.account_id,
            "results": results,
            "passed": all(item["expected_safe_disabled"] for item in results),
        }
        write_json(JSON_PATH, report)
        lines = [
            "# Reputation Disabled Mode Contract",
            "",
            f"- Account id: {config.account_id}",
            f"- Passed: {report['passed']}",
            "- Lovable UX: show disabled/not connected state; do not crash.",
            "- External publish/write flags: disabled.",
            "",
            "| Endpoint | Status code | Body status | Expected safe | Duration ms |",
            "|---|---:|---|---|---:|",
        ]
        lines.extend(
            f"| `{item['method']} {item['path']}` | {item['status_code']} | {item['body_status']} | {item['expected_safe_disabled']} | {item['duration_ms']} |"
            for item in results
        )
        write_text(REPORT_PATH, "\n".join(lines))
        return 0 if report["passed"] else 1
    finally:
        stop_local_backend(server_process, server_log)


if __name__ == "__main__":
    raise SystemExit(main())
