#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import secrets
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import create_engine, text

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from app.core.security import hash_password
from scripts.run_full_runtime_endpoint_audit import (
    AuditConfig,
    contains_unredacted_secret,
    db_url_from_settings,
    normalize_prefix,
    sanitize,
    sanitize_string,
    start_local_backend_if_needed,
    stop_local_backend,
    write_json,
    write_text,
)

OUTPUT_DIR = REPO_ROOT / "reports" / "rbac_audit"
SUMMARY_PATH = OUTPUT_DIR / "summary.json"
REQUESTS_PATH = OUTPUT_DIR / "requests.jsonl"
README_PATH = OUTPUT_DIR / "README.md"
TRUTHY = {"1", "true", "yes", "on"}


@dataclass
class AuditEnv:
    base_url: str | None
    api_prefix: str
    admin_access_token: str | None
    admin_email: str | None
    admin_password: str | None
    seller_access_token: str | None
    seller_email: str | None
    seller_password: str | None
    allowed_account_id: int | None
    forbidden_account_id: int | None
    allow_fixtures: bool
    audit_env: str


def _env_int(name: str) -> int | None:
    raw = (os.getenv(name) or "").strip()
    return int(raw) if raw else None


def _load_env() -> AuditEnv:
    return AuditEnv(
        base_url=(os.getenv("BASE_URL") or "").strip().rstrip("/") or None,
        api_prefix=normalize_prefix(os.getenv("API_PREFIX")),
        admin_access_token=(os.getenv("ADMIN_ACCESS_TOKEN") or "").strip() or None,
        admin_email=(os.getenv("ADMIN_EMAIL") or "").strip() or None,
        admin_password=(os.getenv("ADMIN_PASSWORD") or "").strip() or None,
        seller_access_token=(os.getenv("SELLER_ACCESS_TOKEN") or "").strip() or None,
        seller_email=(os.getenv("SELLER_EMAIL") or "").strip() or None,
        seller_password=(os.getenv("SELLER_PASSWORD") or "").strip() or None,
        allowed_account_id=_env_int("SELLER_OWN_ACCOUNT_ID") or _env_int("ALLOWED_ACCOUNT_ID"),
        forbidden_account_id=_env_int("FORBIDDEN_ACCOUNT_ID"),
        allow_fixtures=(os.getenv("ALLOW_RBAC_TEST_FIXTURES") or "").strip().lower() in TRUTHY,
        audit_env=(os.getenv("AUDIT_ENV") or "local").strip().lower(),
    )


def _url(env: AuditEnv, path: str) -> str:
    assert env.base_url is not None
    base = env.base_url.rstrip("/")
    if base.endswith(env.api_prefix):
        return f"{base}{path}"
    return f"{base}{env.api_prefix}{path}"


def _safe_body(response: httpx.Response) -> Any:
    try:
        return response.json()
    except Exception:
        clean, _ = sanitize_string(response.text[:500])
        return {"text": clean}


def _record(
    sink: Any,
    *,
    actor: str,
    method: str,
    path: str,
    status_code: int,
    duration_ms: int,
    request: dict[str, Any] | None = None,
    response: Any = None,
) -> dict[str, Any]:
    clean_request, request_redactions = sanitize(request or {})
    clean_response, response_redactions = sanitize(response)
    row = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "actor": actor,
        "method": method,
        "path": path,
        "status_code": status_code,
        "duration_ms": duration_ms,
        "request": clean_request,
        "response": clean_response,
        "redactions": request_redactions + response_redactions,
    }
    response_dir = OUTPUT_DIR / "responses"
    response_dir.mkdir(parents=True, exist_ok=True)
    safe_path = path.strip("/").replace("/", "_").replace("{", "").replace("}", "") or "root"
    filename = f"{len(list(response_dir.glob('*.json'))) + 1:03d}_{actor}_{method.lower()}_{safe_path}.json"
    row["evidence_file"] = str((response_dir / filename).relative_to(OUTPUT_DIR))
    sink.write(json.dumps(row, ensure_ascii=False) + "\n")
    sink.flush()
    write_json(response_dir / filename, row)
    return row


def _request(
    client: httpx.Client,
    env: AuditEnv,
    sink: Any,
    *,
    actor: str,
    method: str,
    path: str,
    token: str | None = None,
    params: dict[str, Any] | None = None,
    json_body: dict[str, Any] | None = None,
) -> tuple[httpx.Response, Any, dict[str, Any]]:
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    started = time.perf_counter()
    response = client.request(method, _url(env, path), params=params, json=json_body, headers=headers)
    duration_ms = int((time.perf_counter() - started) * 1000)
    body = _safe_body(response)
    row = _record(
        sink,
        actor=actor,
        method=method,
        path=path,
        status_code=response.status_code,
        duration_ms=duration_ms,
        request={
            "params": params or {},
            "json": json_body or {},
            "headers": {"Authorization": "Bearer <REDACTED>"} if token else {},
        },
        response=body,
    )
    return response, body, row


def _login(client: httpx.Client, env: AuditEnv, sink: Any, *, actor: str, email: str, password: str) -> tuple[str | None, Any]:
    response, body, _row = _request(
        client,
        env,
        sink,
        actor=actor,
        method="POST",
        path="/auth/login",
        json_body={"email": email, "password": password},
    )
    if response.status_code != 200:
        return None, body
    token = body.get("access_token") if isinstance(body, dict) else None
    return str(token) if token else None, body


def _ensure_fixture_env(env: AuditEnv) -> dict[str, Any]:
    if not env.allow_fixtures:
        return {"created": False, "reason": "ALLOW_RBAC_TEST_FIXTURES is not enabled"}
    if env.audit_env not in {"local", "staging", "stage", "dev", "development", "test"}:
        raise RuntimeError("Refusing RBAC fixture creation outside local/staging/dev/test AUDIT_ENV")
    database_url = db_url_from_settings()
    if not database_url:
        raise RuntimeError("DATABASE_URL/settings database URL is unavailable for fixture creation")

    seller_password = env.seller_password or secrets.token_urlsafe(24)
    admin_password = env.admin_password or secrets.token_urlsafe(24)
    seller_email = env.seller_email or "rbac-audit-seller@example.com"
    admin_email = env.admin_email or "rbac-audit-admin@example.com"
    engine = create_engine(database_url, future=True)
    try:
        with engine.begin() as conn:
            allowed_id = env.allowed_account_id or conn.execute(
                text("SELECT id FROM wb_accounts WHERE is_active IS TRUE ORDER BY id LIMIT 1")
            ).scalar_one_or_none()
            if allowed_id is None:
                allowed_id = conn.execute(
                    text(
                        """
                        INSERT INTO wb_accounts (name, seller_name, external_account_id, timezone, is_active)
                        VALUES ('rbac-audit-allowed-account', 'RBAC Audit Allowed', 'rbac-audit-allowed', 'Europe/Moscow', TRUE)
                        RETURNING id
                        """
                    )
                ).scalar_one()
            forbidden_id = env.forbidden_account_id or conn.execute(
                text("SELECT id FROM wb_accounts WHERE id != :allowed_id ORDER BY id LIMIT 1"),
                {"allowed_id": int(allowed_id)},
            ).scalar_one_or_none()
            if forbidden_id is None:
                forbidden_id = conn.execute(
                    text(
                        """
                        INSERT INTO wb_accounts (name, seller_name, external_account_id, timezone, is_active)
                        VALUES ('rbac-audit-forbidden-account', 'RBAC Audit Forbidden', 'rbac-audit-forbidden', 'Europe/Moscow', TRUE)
                        RETURNING id
                        """
                    )
                ).scalar_one()

            seller_id = conn.execute(text("SELECT id FROM auth_users WHERE email = :email"), {"email": seller_email}).scalar_one_or_none()
            if seller_id is None:
                seller_id = conn.execute(
                    text(
                        """
                        INSERT INTO auth_users (email, full_name, password_hash, is_active, is_superuser)
                        VALUES (:email, 'RBAC Audit Seller', :password_hash, TRUE, FALSE)
                        RETURNING id
                        """
                    ),
                    {"email": seller_email, "password_hash": hash_password(seller_password)},
                ).scalar_one()
            else:
                conn.execute(
                    text(
                        """
                        UPDATE auth_users
                        SET password_hash = :password_hash, is_active = TRUE, is_superuser = FALSE
                        WHERE id = :user_id
                        """
                    ),
                    {"user_id": int(seller_id), "password_hash": hash_password(seller_password)},
                )
            conn.execute(text("DELETE FROM auth_user_account_access WHERE user_id = :user_id"), {"user_id": int(seller_id)})
            conn.execute(
                text(
                    """
                    INSERT INTO auth_user_account_access (user_id, account_id, role, is_default)
                    VALUES (:user_id, :account_id, 'operator', TRUE)
                    """
                ),
                {"user_id": int(seller_id), "account_id": int(allowed_id)},
            )

            admin_id = conn.execute(text("SELECT id FROM auth_users WHERE email = :email"), {"email": admin_email}).scalar_one_or_none()
            if admin_id is None:
                admin_id = conn.execute(
                    text(
                        """
                        INSERT INTO auth_users (email, full_name, password_hash, is_active, is_superuser)
                        VALUES (:email, 'RBAC Audit Admin', :password_hash, TRUE, TRUE)
                        RETURNING id
                        """
                    ),
                    {"email": admin_email, "password_hash": hash_password(admin_password)},
                ).scalar_one()
            else:
                conn.execute(
                    text(
                        """
                        UPDATE auth_users
                        SET password_hash = :password_hash, is_active = TRUE, is_superuser = TRUE
                        WHERE id = :user_id
                        """
                    ),
                    {"user_id": int(admin_id), "password_hash": hash_password(admin_password)},
                )
    finally:
        engine.dispose()

    env.seller_email = seller_email
    env.seller_password = seller_password
    env.admin_email = admin_email
    env.admin_password = admin_password
    env.allowed_account_id = int(allowed_id)
    env.forbidden_account_id = int(forbidden_id)
    return {
        "created": True,
        "seller_user_id": int(seller_id),
        "admin_user_id": int(admin_id),
        "allowed_account_id": int(allowed_id),
        "forbidden_account_id": int(forbidden_id),
        "seller_role": "operator",
    }


def _status(ok: bool) -> str:
    return "PASS" if ok else "FAIL"


def _missing_auth_inputs(env: AuditEnv) -> list[str]:
    missing: list[str] = []
    if not env.seller_access_token and not (env.seller_email and env.seller_password):
        missing.append("SELLER_ACCESS_TOKEN or SELLER_EMAIL+SELLER_PASSWORD")
    if not env.admin_access_token and not (env.admin_email and env.admin_password):
        missing.append("ADMIN_ACCESS_TOKEN or ADMIN_EMAIL+ADMIN_PASSWORD")
    if env.allowed_account_id is None:
        missing.append("SELLER_OWN_ACCOUNT_ID")
    if env.forbidden_account_id is None:
        missing.append("FORBIDDEN_ACCOUNT_ID")
    return missing


def _extract_items(body: Any) -> list[dict[str, Any]]:
    if isinstance(body, dict) and isinstance(body.get("items"), list):
        return [item for item in body["items"] if isinstance(item, dict)]
    return []


def _response_contains_account_id(body: Any, account_id: int) -> bool:
    if isinstance(body, dict):
        for key, value in body.items():
            if str(key).lower() == "account_id" and str(value) == str(account_id):
                return True
            if _response_contains_account_id(value, account_id):
                return True
    if isinstance(body, list):
        return any(_response_contains_account_id(item, account_id) for item in body)
    return False


def _matrix_row(row: dict[str, Any], *, expected: str, accepted_codes: set[int]) -> dict[str, Any]:
    actual = int(row["status_code"])
    return {
        "actor": row["actor"],
        "method": row["method"],
        "path": row["path"],
        "status_code": actual,
        "expected": expected,
        "status": _status(actual in accepted_codes),
        "evidence_file": row.get("evidence_file"),
    }


def _secret_scan_projection(value: Any) -> Any:
    ignored_keys = {
        "base_url",
        "duration_ms",
        "evidence_file",
        "generated_at",
        "log_file",
        "token_sources",
        "ts",
    }
    if isinstance(value, dict):
        return {
            key: _secret_scan_projection(inner)
            for key, inner in value.items()
            if str(key) not in ignored_keys
        }
    if isinstance(value, list):
        return [_secret_scan_projection(item) for item in value]
    return value


def main() -> int:
    env = _load_env()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    if REQUESTS_PATH.exists():
        REQUESTS_PATH.unlink()
    config = AuditConfig(
        base_url=env.base_url,
        api_prefix=env.api_prefix,
        access_token=None,
        account_id=str(env.allowed_account_id) if env.allowed_account_id is not None else None,
        audit_env=env.audit_env,
        output_dir=OUTPUT_DIR,
        run_commands=False,
    )
    server_process, server_log, server_status = start_local_backend_if_needed(config, OUTPUT_DIR)
    env.base_url = config.base_url

    summary: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "base_url": env.base_url,
        "api_prefix": env.api_prefix,
        "fixture_mode": env.allow_fixtures,
        "server": server_status,
        "checks": {},
        "facts": {},
        "errors": [],
    }
    try:
        if not server_status.get("ready", True):
            raise RuntimeError(f"backend not ready: {server_status}")
        fixture_facts = _ensure_fixture_env(env)
        summary["facts"]["fixtures"] = fixture_facts
        missing = _missing_auth_inputs(env)
        if missing:
            summary["checks"] = {
                "seller_allowed_account": "MISSING_ENV",
                "seller_forbidden_account": "MISSING_ENV",
                "superuser_access": "MISSING_ENV",
                "secret_scan": "MISSING_ENV",
            }
            summary["facts"]["missing_env"] = missing
            summary["score_cap"] = 70
            summary["passed"] = False
            write_json(SUMMARY_PATH, summary)
            write_json(OUTPUT_DIR / "rbac_matrix.json", [])
            write_text(OUTPUT_DIR / "rbac_matrix.md", "# Seller RBAC Matrix\n\nMISSING_ENV: " + ", ".join(missing))
            write_text(README_PATH, "# Seller RBAC Audit\n\nMISSING_ENV: " + ", ".join(missing))
            print("MISSING_ENV: " + ", ".join(missing), file=sys.stderr)
            return 1

        with REQUESTS_PATH.open("a", encoding="utf-8") as sink, httpx.Client(timeout=httpx.Timeout(45.0, connect=10.0), follow_redirects=True) as client:
            seller_token = env.seller_access_token
            admin_token = env.admin_access_token
            seller_login: Any = {"token_source": "env"} if seller_token else None
            admin_login: Any = {"token_source": "env"} if admin_token else None
            if not seller_token:
                seller_token, seller_login = _login(
                    client,
                    env,
                    sink,
                    actor="seller",
                    email=str(env.seller_email),
                    password=str(env.seller_password),
                )
            if not admin_token:
                admin_token, admin_login = _login(
                    client,
                    env,
                    sink,
                    actor="admin",
                    email=str(env.admin_email),
                    password=str(env.admin_password),
                )
            if not seller_token:
                raise RuntimeError(f"seller login failed: {seller_login}")
            if not admin_token:
                raise RuntimeError(f"admin login failed: {admin_login}")

            seller_me_status, seller_me, _ = _request(client, env, sink, actor="seller", method="GET", path="/auth/me", token=seller_token)
            accounts_status, accounts_body, _ = _request(client, env, sink, actor="seller", method="GET", path="/accounts", token=seller_token)
            account_items = _extract_items(accounts_body)
            account_ids = {int(item["id"]) for item in account_items if "id" in item}
            seller_roles = {
                int(item["id"]): str(item.get("role") or "viewer")
                for item in (seller_me.get("accounts") or [])
                if isinstance(seller_me, dict) and isinstance(item, dict) and item.get("id") is not None
            }
            seller_role = seller_roles.get(int(env.allowed_account_id), "unknown")

            products_status, products_body, _ = _request(
                client,
                env,
                sink,
                actor="seller",
                method="GET",
                path="/portal/products",
                token=seller_token,
                params={"account_id": env.allowed_account_id, "limit": 1},
            )
            product_items = _extract_items(products_body)
            nm_id = product_items[0].get("nm_id") if products_status.status_code == 200 and product_items else None

            allowed_paths = ["/portal/doctor", "/portal/actions", "/portal/products", "/portal/results", "/portal/cases"]
            if nm_id is not None:
                allowed_paths.append(f"/portal/products/{nm_id}")
            allowed_rows = [
                _request(
                    client,
                    env,
                    sink,
                    actor="seller",
                    method="GET",
                    path=path,
                    token=seller_token,
                    params={"account_id": env.allowed_account_id},
                )[2]
                for path in allowed_paths
            ]
            forbidden_paths = ["/portal/doctor", "/portal/actions", "/portal/products", "/portal/results", "/portal/cases"]
            if nm_id is not None:
                forbidden_paths.append(f"/portal/products/{nm_id}")
            forbidden_rows = [
                _request(
                    client,
                    env,
                    sink,
                    actor="seller",
                    method="GET",
                    path=path,
                    token=seller_token,
                    params={"account_id": env.forbidden_account_id},
                )[2]
                for path in forbidden_paths
            ]
            forbidden_response_leaks = [
                row
                for row in forbidden_rows
                if _response_contains_account_id(row.get("response"), int(env.forbidden_account_id))
            ]
            admin_paths = ["/portal/doctor", "/portal/actions", "/portal/products", "/portal/results", "/portal/cases"]
            if nm_id is not None:
                admin_paths.append(f"/portal/products/{nm_id}")
            admin_rows = [
                _request(
                    client,
                    env,
                    sink,
                    actor="admin",
                    method="GET",
                    path=path,
                    token=admin_token,
                    params={"account_id": account_id},
                )[2]
                for account_id in (env.allowed_account_id, env.forbidden_account_id)
                for path in admin_paths
            ]

            action_patch_status = "SKIPPED_NO_MUTABLE_ACTION"
            action_patch_detail: dict[str, Any] = {"seller_role": seller_role}
            actions_status, actions_body, _ = _request(
                client,
                env,
                sink,
                actor="seller",
                method="GET",
                path="/portal/actions",
                token=seller_token,
                params={"account_id": env.allowed_account_id, "limit": 50},
            )
            if actions_status.status_code == 200:
                mutable_action = next(
                    (
                        item
                        for item in _extract_items(actions_body)
                        if item.get("source_module") and item.get("source_id") and (item.get("can_update") or item.get("can_update_status"))
                    ),
                    None,
                )
                if mutable_action:
                    patch_payload = {
                        "account_id": env.allowed_account_id,
                        "source_module": mutable_action["source_module"],
                        "source_id": mutable_action["source_id"],
                        "status": "in_progress",
                        "comment": "RBAC audit status update",
                    }
                    patch_response, patch_body, patch_row = _request(
                        client,
                        env,
                        sink,
                        actor="seller",
                        method="PATCH",
                        path="/portal/actions/by-source",
                        token=seller_token,
                        json_body=patch_payload,
                    )
                    action_patch_detail.update(
                        {
                            "source_module": mutable_action["source_module"],
                            "source_id": mutable_action["source_id"],
                            "status_code": patch_response.status_code,
                        }
                    )
                    if patch_response.status_code == 200:
                        action_patch_status = "PASS"
                    elif patch_response.status_code == 403 and seller_role == "viewer":
                        action_patch_status = "EXPECTED_FORBIDDEN"
                    else:
                        action_patch_status = "FAIL"

            safe_forbidden_codes = {403, 404}
            matrix_rows = [
                *[
                    _matrix_row(row, expected="seller own account returns 200", accepted_codes={200})
                    for row in allowed_rows
                ],
                *[
                    _matrix_row(row, expected="seller forbidden account denied with 403/404", accepted_codes=safe_forbidden_codes)
                    for row in forbidden_rows
                ],
                *[
                    _matrix_row(row, expected="superuser/admin account access returns 200", accepted_codes={200})
                    for row in admin_rows
                ],
            ]
            summary["checks"] = {
                "seller_login": _status(seller_token is not None and seller_me_status.status_code == 200),
                "seller_accounts_scoped": _status(
                    accounts_status.status_code == 200
                    and int(env.allowed_account_id) in account_ids
                    and int(env.forbidden_account_id) not in account_ids
                ),
                "seller_allowed_account": _status(all(row["status_code"] == 200 for row in allowed_rows)),
                "seller_forbidden_account": _status(all(row["status_code"] in safe_forbidden_codes for row in forbidden_rows)),
                "seller_forbidden_response_no_data": _status(not forbidden_response_leaks),
                "superuser_access": _status(all(row["status_code"] == 200 for row in admin_rows)),
                "seller_action_patch": action_patch_status,
            }
            summary["facts"].update(
                {
                    "allowed_account_id": env.allowed_account_id,
                    "forbidden_account_id": env.forbidden_account_id,
                    "seller_role": seller_role,
                    "seller_account_ids_seen": sorted(account_ids),
                    "nm_id_used": nm_id,
                    "action_patch": action_patch_detail,
                    "token_sources": {
                        "seller": "env" if env.seller_access_token else "login",
                        "admin": "env" if env.admin_access_token else "login",
                    },
                    "forbidden_response_leak_count": len(forbidden_response_leaks),
                }
            )
            write_json(OUTPUT_DIR / "rbac_matrix.json", matrix_rows)
            matrix_lines = [
                "# Seller RBAC Matrix",
                "",
                "| Actor | Endpoint | Status code | Expected | Result | Evidence |",
                "|---|---|---:|---|---|---|",
            ]
            matrix_lines.extend(
                f"| {row['actor']} | `{row['method']} {row['path']}` | {row['status_code']} | {row['expected']} | {row['status']} | `{row.get('evidence_file')}` |"
                for row in matrix_rows
            )
            write_text(OUTPUT_DIR / "rbac_matrix.md", "\n".join(matrix_lines))

        summary_for_scan = _secret_scan_projection(json.loads(json.dumps(summary, ensure_ascii=False, default=str)))
        request_rows = [json.loads(line) for line in REQUESTS_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]
        findings = contains_unredacted_secret(summary_for_scan) + contains_unredacted_secret(_secret_scan_projection(request_rows))
        summary["secret_scan_findings"] = findings
        summary["checks"]["secret_scan"] = _status(not findings)
        required_ok = {
            "seller_allowed_account": "PASS",
            "seller_forbidden_account": "PASS",
            "seller_forbidden_response_no_data": "PASS",
            "superuser_access": "PASS",
            "secret_scan": "PASS",
        }
        passed = all(summary["checks"].get(key) == value for key, value in required_ok.items()) and summary["checks"].get("seller_action_patch") in {
            "PASS",
            "EXPECTED_FORBIDDEN",
            "SKIPPED_NO_MUTABLE_ACTION",
        }
        summary["passed"] = passed
        write_json(SUMMARY_PATH, summary)
        readme_lines = [
            "# Seller RBAC Audit",
            "",
            f"- Generated at: {summary['generated_at']}",
            f"- Base URL: `{env.base_url}`",
            f"- Allowed account: `{env.allowed_account_id}`",
            f"- Forbidden account: `{env.forbidden_account_id}`",
            f"- Seller role on allowed account: `{summary['facts'].get('seller_role')}`",
            f"- Seller account ids seen: `{summary['facts'].get('seller_account_ids_seen')}`",
            f"- Product 360 nm_id used: `{summary['facts'].get('nm_id_used')}`",
            "",
            "## Acceptance Summary",
            "",
            "```json",
            json.dumps(
                {
                    "seller_allowed_account": summary["checks"].get("seller_allowed_account"),
                    "seller_forbidden_account": summary["checks"].get("seller_forbidden_account"),
                    "seller_forbidden_response_no_data": summary["checks"].get("seller_forbidden_response_no_data"),
                    "superuser_access": summary["checks"].get("superuser_access"),
                    "seller_action_patch": summary["checks"].get("seller_action_patch"),
                    "secret_scan": summary["checks"].get("secret_scan"),
                },
                ensure_ascii=False,
                indent=2,
            ),
            "```",
            "",
            "Detailed sanitized request/response evidence is in `requests.jsonl` and `responses/`.",
        ]
        write_text(README_PATH, "\n".join(readme_lines))
        print(json.dumps(summary["checks"], ensure_ascii=False, indent=2))
        return 0 if passed else 1
    except Exception as exc:
        clean, _ = sanitize_string(str(exc))
        summary["errors"].append(clean)
        summary["passed"] = False
        summary["checks"].setdefault("secret_scan", "FAIL")
        write_json(SUMMARY_PATH, summary)
        write_text(README_PATH, f"# Seller RBAC Audit\n\nAudit failed before completion: {clean}")
        print(clean, file=sys.stderr)
        return 1
    finally:
        stop_local_backend(server_process, server_log)


if __name__ == "__main__":
    raise SystemExit(main())
