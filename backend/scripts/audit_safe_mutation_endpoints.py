#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import create_engine, text

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from app.core.security import create_access_token
from scripts.run_full_runtime_endpoint_audit import (
    AuditConfig,
    db_url_from_settings,
    hydrate_runtime_config_from_db,
    normalize_prefix,
    sanitize,
    start_local_backend_if_needed,
    stop_local_backend,
    write_json,
    write_text,
)


REPORT_PATH = REPO_ROOT / "reports" / "safe_mutation_endpoint_proof.md"
JSON_PATH = REPO_ROOT / "reports" / "safe_mutation_endpoint_proof.json"


def _config() -> AuditConfig:
    return AuditConfig(
        base_url=(os.getenv("BASE_URL") or "").strip().rstrip("/") or None,
        api_prefix=normalize_prefix(os.getenv("API_PREFIX")),
        access_token=(os.getenv("ACCESS_TOKEN") or "").strip() or None,
        account_id=(os.getenv("ACCOUNT_ID") or "").strip() or None,
        audit_env=(os.getenv("AUDIT_ENV") or "local").strip().lower(),
        output_dir=REPO_ROOT / "reports" / "safe_mutation_runtime",
        run_commands=False,
    )


def _url(config: AuditConfig, path: str) -> str:
    base = str(config.base_url).rstrip("/")
    if base.endswith(config.api_prefix):
        return f"{base}{path}"
    return f"{base}{config.api_prefix}{path}"


def _discover_nm_id(account_id: int) -> int | None:
    database_url = db_url_from_settings()
    if not database_url:
        return None
    engine = create_engine(database_url, future=True)
    try:
        with engine.connect() as conn:
            value = conn.execute(
                text(
                    """
                    SELECT nm_id FROM core_sku
                    WHERE account_id = :account_id AND nm_id IS NOT NULL
                    ORDER BY id LIMIT 1
                    """
                ),
                {"account_id": account_id},
            ).scalar_one_or_none()
            return int(value) if value is not None else None
    finally:
        engine.dispose()


def _call(client: httpx.Client, config: AuditConfig, method: str, path: str, body: dict[str, Any]) -> dict[str, Any]:
    started = time.perf_counter()
    response = client.request(method, _url(config, path), json=body)
    try:
        raw_body: Any = response.json()
    except Exception:
        raw_body = {"text": response.text[:500]}
    clean_body, redactions = sanitize(raw_body)
    expected_safe = response.status_code < 300 or response.status_code in {400, 403, 404, 409, 422}
    return {
        "method": method,
        "path": path,
        "status_code": response.status_code,
        "duration_ms": int((time.perf_counter() - started) * 1000),
        "expected_safe": expected_safe,
        "body_keys": list(clean_body.keys()) if isinstance(clean_body, dict) else [],
        "redactions": redactions,
        "note": "No external marketplace write was requested; dangerous flags remain disabled.",
    }


def main() -> int:
    for name in (
        "ENABLE_REPUTATION_PUBLISH",
        "ENABLE_REPUTATION_WRITE_ACTIONS",
        "ENABLE_CLAIMS_SUBMIT",
        "ENABLE_GROUPING_MERGE",
        "ENABLE_CARD_AUTO_APPLY",
    ):
        os.environ[name] = "false"
    config = _config()
    setup = hydrate_runtime_config_from_db(config)
    server_process, server_log, server_status = start_local_backend_if_needed(config, config.output_dir)
    try:
        if not config.access_token or not config.account_id:
            raise RuntimeError(f"missing token/account after hydrate: {setup}")
        account_id = int(config.account_id)
        nm_id = _discover_nm_id(account_id)
        headers = {"Authorization": f"Bearer {config.access_token}", "Accept": "application/json"}
        source_id = f"runtime-audit-safe-{int(time.time())}"
        with httpx.Client(headers=headers, timeout=httpx.Timeout(30.0, connect=5.0), follow_redirects=True) as client:
            results = []
            results.append(
                _call(
                    client,
                    config,
                    "PATCH",
                    "/portal/actions/by-source",
                    {
                        "account_id": account_id,
                        "source_module": "runtime_audit",
                        "source_id": source_id,
                        "status": "in_progress",
                        "comment": "safe local audit mutation; no external write",
                    },
                )
            )
            case_create = _call(
                client,
                config,
                "POST",
                "/portal/cases/from-signal",
                {
                    "account_id": account_id,
                    "source_module": "runtime_audit",
                    "source_id": source_id,
                    "nm_id": nm_id,
                    "title": "Runtime audit safe synthetic case",
                    "summary": "Local-only proof object.",
                    "payload": {"audit": True, "safe_mode": True, "external_operation": False},
                },
            )
            results.append(case_create)
            case_id = None
            body = client.post(
                _url(config, "/portal/cases/from-signal"),
                json={
                    "account_id": account_id,
                    "source_module": "runtime_audit",
                    "source_id": source_id,
                    "nm_id": nm_id,
                    "title": "Runtime audit safe synthetic case",
                    "summary": "Local-only proof object.",
                    "payload": {"audit": True, "safe_mode": True, "external_operation": False},
                },
            ).json()
            if isinstance(body, dict) and body.get("id"):
                case_id = int(body["id"])
            if case_id is not None:
                results.append(
                    _call(
                        client,
                        config,
                        "PATCH",
                        f"/portal/cases/{case_id}",
                        {"status": "evidence_needed", "payload": {"audit": True, "safe_mode": True}},
                    )
                )
                results.append(
                    _call(
                        client,
                        config,
                        "POST",
                        f"/portal/cases/{case_id}/evidence",
                        {
                            "evidence_type": "manual",
                            "title": "Runtime audit safe evidence",
                            "description": "Synthetic local evidence only.",
                            "payload": {"audit": True, "safe_mode": True},
                        },
                    )
                )
                results.append(
                    _call(
                        client,
                        config,
                        "POST",
                        f"/portal/cases/{case_id}/generate-draft",
                        {"draft_type": "support_appeal", "tone": "neutral", "payload": {"audit": True, "safe_mode": True}},
                    )
                )
            results.append(
                _call(
                    client,
                    config,
                    "POST",
                    "/portal/experiments/events",
                    {
                        "account_id": account_id,
                        "nm_id": nm_id or 0,
                        "event_type": "manual_note",
                        "before_json": {"audit": True},
                        "after_json": {"audit": True, "safe_mode": True},
                    },
                )
            )
        report = {
            "setup": setup,
            "server": server_status,
            "account_id": account_id,
            "nm_id": nm_id,
            "case_id": case_id,
            "results": results,
            "passed": all(item["expected_safe"] for item in results),
        }
        write_json(JSON_PATH, report)
        lines = [
            "# Safe Mutation Endpoint Proof",
            "",
            f"- Account id: {account_id}",
            f"- nm_id: {nm_id}",
            f"- Synthetic case id: {case_id}",
            f"- Passed: {report['passed']}",
            "- External marketplace writes: disabled/not requested",
            "",
            "| Endpoint | Status | Expected safe | Duration ms |",
            "|---|---:|---|---:|",
        ]
        lines.extend(
            f"| `{item['method']} {item['path']}` | {item['status_code']} | {item['expected_safe']} | {item['duration_ms']} |"
            for item in results
        )
        write_text(REPORT_PATH, "\n".join(lines))
        return 0 if report["passed"] else 1
    finally:
        stop_local_backend(server_process, server_log)


if __name__ == "__main__":
    raise SystemExit(main())
