#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import create_engine, text

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from app.core.security import create_access_token, hash_password
from scripts.run_full_runtime_endpoint_audit import (
    AuditConfig,
    db_url_from_settings,
    normalize_prefix,
    sanitize,
    start_local_backend_if_needed,
    stop_local_backend,
    write_json,
    write_text,
)


REPORT_PATH = REPO_ROOT / "reports" / "rbac_account_scope_proof.md"
JSON_PATH = REPO_ROOT / "reports" / "rbac_account_scope_proof.json"


def _config() -> AuditConfig:
    return AuditConfig(
        base_url=(os.getenv("BASE_URL") or "").strip().rstrip("/") or None,
        api_prefix=normalize_prefix(os.getenv("API_PREFIX")),
        access_token=None,
        account_id=None,
        audit_env=(os.getenv("AUDIT_ENV") or "local").strip().lower(),
        output_dir=REPO_ROOT / "reports" / "rbac_account_scope_runtime",
        run_commands=False,
    )


def _ensure_accounts_and_user() -> dict[str, Any]:
    database_url = db_url_from_settings()
    if not database_url:
        raise RuntimeError("database URL is unavailable")
    engine = create_engine(database_url, future=True)
    try:
        with engine.begin() as conn:
            allowed_id = conn.execute(text("SELECT id FROM wb_accounts WHERE is_active IS TRUE ORDER BY id LIMIT 1")).scalar_one_or_none()
            if allowed_id is None:
                raise RuntimeError("no active wb_accounts row found")
            forbidden_id = conn.execute(
                text("SELECT id FROM wb_accounts WHERE id != :allowed_id ORDER BY id LIMIT 1"),
                {"allowed_id": int(allowed_id)},
            ).scalar_one_or_none()
            if forbidden_id is None:
                forbidden_id = conn.execute(
                    text(
                        """
                        INSERT INTO wb_accounts (name, seller_name, external_account_id, timezone, is_active)
                        VALUES ('runtime-audit-forbidden-account', 'Runtime Audit Forbidden', 'runtime-audit-forbidden', 'Europe/Moscow', TRUE)
                        ON CONFLICT (name) DO UPDATE SET is_active = TRUE
                        RETURNING id
                        """
                    )
                ).scalar_one()
            email = "runtime-audit-seller@example.com"
            conn.execute(
                text("UPDATE auth_users SET email = :new_email WHERE email = 'runtime-audit-seller@example.invalid'"),
                {"new_email": email},
            )
            user_id = conn.execute(text("SELECT id FROM auth_users WHERE email = :email"), {"email": email}).scalar_one_or_none()
            if user_id is None:
                user_id = conn.execute(
                    text(
                        """
                        INSERT INTO auth_users (email, full_name, password_hash, is_active, is_superuser)
                        VALUES (:email, 'Runtime Audit Seller', :password_hash, TRUE, FALSE)
                        RETURNING id
                        """
                    ),
                    {"email": email, "password_hash": hash_password("runtime-audit-local-password")},
                ).scalar_one()
            else:
                conn.execute(
                    text("UPDATE auth_users SET is_active = TRUE, is_superuser = FALSE WHERE id = :user_id"),
                    {"user_id": int(user_id)},
                )
            conn.execute(text("DELETE FROM auth_user_account_access WHERE user_id = :user_id"), {"user_id": int(user_id)})
            conn.execute(
                text(
                    """
                    INSERT INTO auth_user_account_access (user_id, account_id, role, is_default)
                    VALUES (:user_id, :account_id, 'operator', TRUE)
                    """
                ),
                {"user_id": int(user_id), "account_id": int(allowed_id)},
            )
            superuser_id = conn.execute(
                text("SELECT id FROM auth_users WHERE is_active IS TRUE AND is_superuser IS TRUE ORDER BY id LIMIT 1")
            ).scalar_one_or_none()
            if superuser_id is None:
                superuser_id = int(user_id)
                conn.execute(text("UPDATE auth_users SET is_superuser = TRUE WHERE id = :user_id"), {"user_id": superuser_id})
        return {
            "allowed_account_id": int(allowed_id),
            "forbidden_account_id": int(forbidden_id),
            "seller_user_id": int(user_id),
            "superuser_id": int(superuser_id),
        }
    finally:
        engine.dispose()


def _url(config: AuditConfig, path: str) -> str:
    base = str(config.base_url).rstrip("/")
    if base.endswith(config.api_prefix):
        return f"{base}{path}"
    return f"{base}{config.api_prefix}{path}"


def _call(client: httpx.Client, config: AuditConfig, token: str, path: str, account_id: int, nm_id: int | None = None) -> dict[str, Any]:
    concrete = path.replace("{nm_id}", str(nm_id or 0))
    started = time.perf_counter()
    response = client.get(
        _url(config, concrete),
        params={"account_id": account_id},
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
    )
    body: Any
    try:
        body = response.json()
    except Exception:
        body = {"text": response.text[:500]}
    clean_body, redactions = sanitize(body)
    return {
        "endpoint": path,
        "account_id": account_id,
        "status_code": response.status_code,
        "duration_ms": int((time.perf_counter() - started) * 1000),
        "body_keys": list(clean_body.keys()) if isinstance(clean_body, dict) else [],
        "redactions": redactions,
    }


def main() -> int:
    config = _config()
    facts = _ensure_accounts_and_user()
    config.account_id = str(facts["allowed_account_id"])
    server_process, server_log, server_status = start_local_backend_if_needed(config, config.output_dir)
    try:
        if not server_status.get("ready", True):
            raise RuntimeError(f"backend not ready: {server_status}")
        seller_token = create_access_token(str(facts["seller_user_id"]))
        superuser_token = create_access_token(str(facts["superuser_id"]))
        nm_id = None
        with httpx.Client(timeout=httpx.Timeout(30.0, connect=5.0), follow_redirects=True) as client:
            products = client.get(
                _url(config, "/portal/products"),
                params={"account_id": facts["allowed_account_id"], "limit": 1},
                headers={"Authorization": f"Bearer {seller_token}", "Accept": "application/json"},
            )
            if products.status_code == 200:
                items = (products.json().get("items") or [])
                if items:
                    nm_id = items[0].get("nm_id")
            endpoints = ["/portal/doctor", "/portal/actions", "/portal/products"]
            if nm_id:
                endpoints.append("/portal/products/{nm_id}")
            allowed = [_call(client, config, seller_token, path, facts["allowed_account_id"], nm_id) for path in endpoints]
            forbidden = [_call(client, config, seller_token, path, facts["forbidden_account_id"], nm_id) for path in endpoints]
            superuser = [_call(client, config, superuser_token, path, facts["forbidden_account_id"], nm_id) for path in endpoints]
        report = {
            "server": server_status,
            "facts": facts,
            "nm_id_used": nm_id,
            "allowed": allowed,
            "forbidden": forbidden,
            "superuser": superuser,
            "passed": all(item["status_code"] == 200 for item in allowed)
            and all(item["status_code"] == 403 for item in forbidden)
            and all(item["status_code"] in {200, 404} for item in superuser),
        }
        write_json(JSON_PATH, report)
        lines = [
            "# RBAC Account Scope Proof",
            "",
            f"- Allowed account: {facts['allowed_account_id']}",
            f"- Forbidden account: {facts['forbidden_account_id']}",
            f"- Seller user id: {facts['seller_user_id']}",
            f"- Superuser id: {facts['superuser_id']}",
            f"- Product nm_id used: {nm_id}",
            f"- Passed: {report['passed']}",
            "",
            "| Scenario | Endpoint | Account | Status | Duration ms |",
            "|---|---|---:|---:|---:|",
        ]
        for label, rows in (("allowed", allowed), ("forbidden", forbidden), ("superuser", superuser)):
            lines.extend(
                f"| {label} | `{row['endpoint']}` | {row['account_id']} | {row['status_code']} | {row['duration_ms']} |"
                for row in rows
            )
        write_text(REPORT_PATH, "\n".join(lines))
        return 0 if report["passed"] else 1
    finally:
        stop_local_backend(server_process, server_log)


if __name__ == "__main__":
    raise SystemExit(main())
