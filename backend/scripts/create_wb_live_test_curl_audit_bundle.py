#!/usr/bin/env python3
"""Create a curl-based sanitized audit bundle for the wb-live-test account."""

from __future__ import annotations

import json
import os
import re
import secrets
import socket
import subprocess
import sys
import time
import zipfile
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from sqlalchemy import create_engine, inspect, text


REPO_ROOT = Path(__file__).resolve().parents[1]
ACCOUNT_NAME = "wb-live-test"
API_PREFIX = "/api/v1"
REDACTED = "<REDACTED>"
MAX_ROWS_PER_TABLE = int(os.getenv("WB_LIVE_AUDIT_MAX_ROWS_PER_TABLE", "0"))
CURL_TIMEOUT_SECONDS = int(os.getenv("WB_LIVE_AUDIT_CURL_TIMEOUT_SECONDS", "240"))
SENSITIVE_TOKENS = {
    "access_token",
    "api_key",
    "authorization",
    "buyer",
    "client",
    "contact",
    "cookie",
    "credential",
    "customer",
    "email",
    "encrypted_token",
    "encryption_key",
    "fio",
    "full_name",
    "headers",
    "jwt",
    "passport",
    "password",
    "phone",
    "refresh",
    "refresh_token",
    "secret",
    "set-cookie",
    "token",
}
DANGEROUS_FLAGS = (
    "ENABLE_REPUTATION_PUBLISH",
    "ENABLE_REPUTATION_WRITE_ACTIONS",
    "ENABLE_CLAIMS_SUBMIT",
    "ENABLE_GROUPING_MERGE",
    "ENABLE_CARD_AUTO_APPLY",
)
TRUTHY = {"1", "true", "yes", "on", "enabled"}
JWT_RE = re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b")
EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
PHONE_RE = re.compile(r"(?<!\d)(?:\+?\d[\d\s().-]{8,}\d)(?!\d)")
LONG_SECRET_RE = re.compile(r"\b[A-Za-z0-9_+/=-]{56,}\b")


def json_default(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return str(value)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=json_default) + "\n", encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", encoding="utf-8")


def is_sensitive_key(key: Any) -> bool:
    lowered = str(key).lower()
    return any(token in lowered for token in SENSITIVE_TOKENS)


def sanitize_string(value: str) -> str:
    value = JWT_RE.sub(REDACTED, value)
    value = EMAIL_RE.sub(REDACTED, value)
    value = PHONE_RE.sub(REDACTED, value)
    value = LONG_SECRET_RE.sub(REDACTED, value)
    return value


def sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, inner in value.items():
            if is_sensitive_key(key):
                result[str(key)] = REDACTED
            else:
                result[str(key)] = sanitize(inner)
        return result
    if isinstance(value, list):
        return [sanitize(item) for item in value]
    if isinstance(value, str):
        return sanitize_string(value)
    return value


def contains_secret(value: Any) -> list[str]:
    findings: list[str] = []

    def visit(node: Any, path: str) -> None:
        if isinstance(node, dict):
            for key, inner in node.items():
                if is_sensitive_key(key) and inner != REDACTED:
                    findings.append(f"{path}.{key}: sensitive key not redacted")
                visit(inner, f"{path}.{key}")
        elif isinstance(node, list):
            for index, inner in enumerate(node):
                visit(inner, f"{path}[{index}]")
        elif isinstance(node, str):
            if JWT_RE.search(node):
                findings.append(f"{path}: jwt-like token")
            if any(marker in node.lower() for marker in ("authorization: bearer", "encrypted_token", "refresh_token")):
                findings.append(f"{path}: secret-like text")

    visit(value, "$")
    return findings


def safe_name(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "_", value).strip("_").lower() or "endpoint"


def db_url_from_settings() -> str:
    if os.getenv("DATABASE_URL"):
        return os.environ["DATABASE_URL"]
    from app.core.config import get_settings

    return get_settings().sync_database_url


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_for_backend(base_url: str) -> dict[str, Any]:
    start = time.perf_counter()
    last = ""
    while time.perf_counter() - start < 45:
        proc = subprocess.run(
            ["curl", "-sS", "--max-time", "5", "-o", "/dev/null", "-w", "%{http_code}", f"{base_url}/openapi.json"],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
        )
        if proc.returncode == 0 and proc.stdout.strip() == "200":
            return {"ready": True, "duration_ms": int((time.perf_counter() - start) * 1000)}
        last = (proc.stderr or proc.stdout or "").strip()
        time.sleep(1)
    return {"ready": False, "last_error": sanitize_string(last)}


def start_backend(output_dir: Path) -> tuple[subprocess.Popen[str] | None, Any | None, str, dict[str, Any]]:
    base_url = (os.getenv("BASE_URL") or os.getenv("BACKEND_AUDIT_BASE_URL") or "").strip().rstrip("/")
    if base_url:
        return None, None, base_url, {"started": False, "reason": "BASE_URL provided", "base_url": base_url}
    port = int(os.getenv("AUDIT_LOCAL_PORT") or free_port())
    base_url = f"http://127.0.0.1:{port}"
    log_path = output_dir / "server" / "uvicorn.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_handle = log_path.open("w", encoding="utf-8")
    env = os.environ.copy()
    env["ENABLE_SCHEDULER"] = "false"
    for flag in DANGEROUS_FLAGS:
        env[flag] = "false"
    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port)],
        cwd=REPO_ROOT,
        env=env,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        text=True,
    )
    status = wait_for_backend(base_url)
    status.update({"started": True, "pid": process.pid, "base_url": base_url, "log_file": str(log_path.relative_to(output_dir))})
    if not status.get("ready"):
        process.terminate()
        log_handle.close()
        return None, None, base_url, status
    return process, log_handle, base_url, status


def stop_backend(process: subprocess.Popen[str] | None, log_handle: Any | None) -> None:
    if process is not None:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)
    if log_handle is not None:
        log_handle.close()


def ensure_audit_admin(engine: Any) -> dict[str, Any]:
    from app.core.security import hash_password

    email = f"wb-live-curl-audit-{datetime.now().strftime('%Y%m%d%H%M%S')}@example.com"
    password = secrets.token_urlsafe(32)
    with engine.begin() as conn:
        row = conn.execute(
            text(
                """
                INSERT INTO auth_users (email, full_name, password_hash, is_active, is_superuser, created_at, updated_at)
                VALUES (:email, 'WB live curl audit admin', :password_hash, TRUE, TRUE, now(), now())
                RETURNING id
                """
            ),
            {"email": email, "password_hash": hash_password(password)},
        ).first()
    return {"id": int(row[0]), "email": email, "password": password, "created_temporary_user": True}


def resolve_account(engine: Any) -> dict[str, Any]:
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT id, name, seller_name, is_active FROM wb_accounts WHERE name = :name"),
            {"name": ACCOUNT_NAME},
        ).mappings().first()
        if row is None:
            raise RuntimeError(f"account {ACCOUNT_NAME!r} not found")
        return dict(row)


def discover_ids(engine: Any, account_id: int) -> dict[str, Any]:
    ids: dict[str, Any] = {"account_id": account_id}
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    with engine.connect() as conn:
        sku = conn.execute(
            text(
                """
                SELECT sku_id, nm_id
                FROM mart_sku_daily
                WHERE account_id = :account_id AND nm_id IS NOT NULL
                GROUP BY sku_id, nm_id
                ORDER BY sum(realized_revenue) DESC NULLS LAST, max(stat_date) DESC
                LIMIT 1
                """
            ),
            {"account_id": account_id},
        ).mappings().first()
        if sku:
            ids["sku_id"] = int(sku["sku_id"]) if sku["sku_id"] is not None else None
            ids["nm_id"] = int(sku["nm_id"]) if sku["nm_id"] is not None else None
        issue = conn.execute(text("SELECT id FROM data_quality_issues WHERE account_id=:account_id ORDER BY detected_at DESC NULLS LAST, id DESC LIMIT 1"), {"account_id": account_id}).first()
        if issue:
            ids["issue_id"] = int(issue[0])
        if "unified_actions" in tables:
            action = conn.execute(text("SELECT id FROM unified_actions WHERE account_id=:account_id ORDER BY id DESC LIMIT 1"), {"account_id": account_id}).first()
            if action:
                ids["action_id"] = int(action[0])
        elif "operator_actions" in tables:
            action = conn.execute(text("SELECT id FROM operator_actions WHERE account_id=:account_id ORDER BY id DESC LIMIT 1"), {"account_id": account_id}).first()
            if action:
                ids["action_id"] = int(action[0])
    return ids


def table_columns(inspector: Any, table: str) -> list[str]:
    return [str(col["name"]) for col in inspector.get_columns(table)]


def export_db(engine: Any, account: dict[str, Any], ids: dict[str, Any], output_dir: Path) -> dict[str, Any]:
    db_dir = output_dir / "db"
    db_dir.mkdir(parents=True, exist_ok=True)
    inspector = inspect(engine)
    tables = sorted(inspector.get_table_names())
    account_id = int(account["id"])
    nm_id = ids.get("nm_id")
    sku_id = ids.get("sku_id")
    summary: dict[str, Any] = {"account": sanitize(account), "tables": {}, "max_rows_per_table": MAX_ROWS_PER_TABLE}
    with engine.connect() as conn:
        for table in tables:
            cols = table_columns(inspector, table)
            where: str | None = None
            params: dict[str, Any] = {"account_id": account_id, "nm_id": nm_id, "sku_id": sku_id}
            if "account_id" in cols:
                where = "account_id = :account_id"
            elif table == "wb_accounts":
                where = "id = :account_id"
            elif "sku_id" in cols and sku_id is not None:
                where = "sku_id = :sku_id"
            elif "nm_id" in cols and nm_id is not None:
                where = "nm_id = :nm_id"
            else:
                continue
            order_col = "id" if "id" in cols else cols[0]
            selected_cols = [f'"{col}"' for col in cols]
            limit_sql = "" if MAX_ROWS_PER_TABLE <= 0 else " LIMIT :limit"
            sql = f'SELECT {", ".join(selected_cols)} FROM "{table}" WHERE {where} ORDER BY "{order_col}"{limit_sql}'
            count_sql = f'SELECT count(*) FROM "{table}" WHERE {where}'
            total = int(conn.execute(text(count_sql), params).scalar_one())
            query_params = dict(params)
            if MAX_ROWS_PER_TABLE > 0:
                query_params["limit"] = MAX_ROWS_PER_TABLE
            rows_exported = 0
            file_path = db_dir / f"{table}.json"
            with file_path.open("w", encoding="utf-8") as handle:
                handle.write("{\n")
                handle.write(f'  "table": {json.dumps(table, ensure_ascii=False)},\n')
                handle.write(f'  "total": {total},\n')
                handle.write(f'  "filter": {json.dumps(where, ensure_ascii=False)},\n')
                handle.write('  "rows": [')
                first = True
                result = conn.execution_options(stream_results=True).execute(text(sql), query_params).mappings()
                for row in result:
                    if not first:
                        handle.write(",")
                    first = False
                    handle.write("\n    ")
                    handle.write(json.dumps(sanitize(dict(row)), ensure_ascii=False, default=json_default))
                    rows_exported += 1
                handle.write("\n  ],\n")
                handle.write(f'  "rows_exported": {rows_exported}\n')
                handle.write("}\n")
            summary["tables"][table] = {"total": total, "rows_exported": rows_exported, "filter": where}
    write_json(db_dir / "db_export_summary.json", summary)
    return summary


def curl_json(
    method: str,
    url: str,
    *,
    token: str | None = None,
    body: dict[str, Any] | None = None,
    sanitize_body: bool = True,
) -> dict[str, Any]:
    cmd = ["curl", "-sS", "--connect-timeout", "15", "--max-time", str(CURL_TIMEOUT_SECONDS), "-X", method.upper()]
    if token:
        cmd += ["-H", f"Authorization: Bearer {token}"]
    if body is not None:
        cmd += ["-H", "Content-Type: application/json", "--data-binary", json.dumps(body, ensure_ascii=False)]
    cmd += ["-w", "\n__CURL_META__%{http_code} %{time_total}", url]
    start = time.perf_counter()
    proc = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True)
    elapsed = time.perf_counter() - start
    stdout = (proc.stdout or b"").decode("utf-8", errors="replace")
    body_text = stdout
    status_code: int | None = None
    curl_time: float | None = None
    marker = "\n__CURL_META__"
    if marker in stdout:
        body_text, meta = stdout.rsplit(marker, 1)
        parts = meta.strip().split()
        if parts:
            try:
                status_code = int(parts[0])
            except ValueError:
                status_code = None
        if len(parts) > 1:
            try:
                curl_time = float(parts[1])
            except ValueError:
                curl_time = None
    try:
        parsed: Any = json.loads(body_text) if body_text.strip() else None
    except json.JSONDecodeError:
        parsed = {"raw_text": body_text[:20000]}
    return {
        "returncode": proc.returncode,
        "status_code": status_code,
        "duration_seconds": round(curl_time or elapsed, 3),
        "stderr": sanitize_string((proc.stderr or b"").decode("utf-8", errors="replace")),
        "body": sanitize(parsed) if sanitize_body else parsed,
    }


def login_with_curl(base_url: str, admin: dict[str, Any], output_dir: Path) -> str:
    url = f"{base_url}{API_PREFIX}/auth/login"
    result = curl_json("POST", url, body={"email": admin["email"], "password": admin["password"]}, sanitize_body=False)
    body = result.get("body") if isinstance(result.get("body"), dict) else {}
    token = body.get("access_token") if isinstance(body, dict) else None
    safe_result = sanitize(result)
    if isinstance(safe_result.get("body"), dict):
        safe_result["body"] = {
            "token_type": safe_result["body"].get("token_type"),
            "has_access_token": bool(token),
            "has_refresh_token": bool(body.get("refresh_token")),
        }
    write_json(output_dir / "auth" / "login.json", safe_result)
    if not token:
        raise RuntimeError("curl login did not return access_token")
    return str(token)


def fetch_openapi(base_url: str, output_dir: Path) -> dict[str, Any]:
    result = curl_json("GET", f"{base_url}/openapi.json")
    write_json(output_dir / "openapi" / "openapi_fetch.json", result)
    doc = result.get("body")
    if not isinstance(doc, dict):
        raise RuntimeError("OpenAPI fetch failed")
    write_json(output_dir / "openapi" / "openapi.json", doc)
    return doc


def substitute_path(path: str, ids: dict[str, Any]) -> tuple[str, str | None]:
    replacements = {
        "account_id": ids.get("account_id"),
        "nm_id": ids.get("nm_id"),
        "sku_id": ids.get("sku_id"),
        "issue_id": ids.get("issue_id"),
        "action_id": ids.get("action_id"),
        "cursor_id": None,
        "upload_id": None,
        "item_id": None,
        "draft_id": None,
        "case_id": None,
        "run_id": None,
    }
    missing: list[str] = []

    def repl(match: re.Match[str]) -> str:
        name = match.group(1)
        value = replacements.get(name)
        if value is None:
            missing.append(name)
            return match.group(0)
        return str(value)

    rendered = re.sub(r"\{([^}]+)\}", repl, path)
    return rendered, f"missing path params: {', '.join(missing)}" if missing else None


def query_for_operation(path: str, operation: dict[str, Any], ids: dict[str, Any]) -> dict[str, Any]:
    query: dict[str, Any] = {}
    for param in operation.get("parameters") or []:
        if param.get("in") != "query":
            continue
        name = str(param.get("name") or "")
        if name == "account_id":
            query[name] = ids.get("account_id")
        elif name in {"limit", "page_size"}:
            query[name] = 20
        elif name == "offset":
            query[name] = 0
        elif name == "date_from":
            query[name] = os.getenv("WB_LIVE_AUDIT_DATE_FROM", "2026-05-19")
        elif name == "date_to":
            query[name] = os.getenv("WB_LIVE_AUDIT_DATE_TO", "2026-06-17")
        elif name == "nm_id" and ids.get("nm_id") is not None:
            query[name] = ids.get("nm_id")
        elif name == "sku_id" and ids.get("sku_id") is not None:
            query[name] = ids.get("sku_id")
        elif name == "only_open":
            query[name] = "true"
        elif name == "format":
            query[name] = "csv"
        elif name == "mode":
            query[name] = "all"
    if path in {"/portal/data-readiness", "/portal/data-sync/status"}:
        query.setdefault("account_id", ids.get("account_id"))
    return {k: v for k, v in query.items() if v is not None}


def should_execute(method: str, path: str) -> tuple[bool, str | None]:
    if method == "GET":
        return True, None
    if method == "POST" and path in {"/auth/login"}:
        return False, "captured separately in auth/login.json with sanitized token shape"
    return False, "skipped: non-GET endpoint not executed by audit to avoid state changes or marketplace writes"


def execute_endpoints(base_url: str, token: str, openapi: dict[str, Any], ids: dict[str, Any], output_dir: Path) -> dict[str, Any]:
    endpoint_dir = output_dir / "endpoints"
    index: list[dict[str, Any]] = []
    paths = openapi.get("paths") or {}
    for path, methods in sorted(paths.items()):
        if not isinstance(methods, dict):
            continue
        for method, operation in sorted(methods.items()):
            method_upper = method.upper()
            if method_upper not in {"GET", "POST", "PATCH", "PUT", "DELETE"}:
                continue
            api_path = path
            if api_path.startswith(API_PREFIX):
                api_path = api_path[len(API_PREFIX):] or "/"
            execute, skip_reason = should_execute(method_upper, api_path)
            rendered_path, missing_reason = substitute_path(api_path, ids)
            skip_reason = skip_reason or missing_reason
            query = query_for_operation(api_path, operation if isinstance(operation, dict) else {}, ids)
            url = f"{base_url}{API_PREFIX}{rendered_path}"
            if query:
                url = f"{url}?{urlencode(query)}"
            file_name = f"{safe_name(method_upper + '_' + api_path)}.json"
            record = {
                "method": method_upper,
                "path": api_path,
                "url_path": f"{API_PREFIX}{rendered_path}",
                "query": query,
                "executed": False,
                "skip_reason": skip_reason,
                "request": {
                    "curl_template": f"curl -sS -X {method_upper} -H 'Authorization: Bearer {REDACTED}' '{url}'",
                },
            }
            if execute and not skip_reason:
                result = curl_json(method_upper, url, token=token)
                record.update({"executed": True, "response": result})
            write_json(endpoint_dir / file_name, record)
            index.append(
                {
                    "method": method_upper,
                    "path": api_path,
                    "file": f"endpoints/{file_name}",
                    "executed": record["executed"],
                    "status_code": (record.get("response") or {}).get("status_code") if record.get("response") else None,
                    "duration_seconds": (record.get("response") or {}).get("duration_seconds") if record.get("response") else None,
                    "skip_reason": record.get("skip_reason"),
                }
            )
    write_json(output_dir / "endpoints_index.json", index)
    return {
        "total": len(index),
        "executed": sum(1 for item in index if item["executed"]),
        "skipped": sum(1 for item in index if not item["executed"]),
        "non_2xx": [item for item in index if item["executed"] and not (200 <= int(item["status_code"] or 0) < 300)],
    }


def final_secret_scan(output_dir: Path) -> list[str]:
    findings: list[str] = []
    for path in output_dir.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in {".json", ".md", ".txt", ".log"}:
            continue
        try:
            with path.open("r", encoding="utf-8", errors="ignore") as handle:
                for line_no, line in enumerate(handle, start=1):
                    if JWT_RE.search(line):
                        findings.append(f"{path.relative_to(output_dir)}:{line_no}: jwt-like token")
                    if re.search(r"(?i)(authorization|access_token|refresh_token|encrypted_token|api_key|password)\":\\s*\"(?!<REDACTED>|true|false)", line):
                        findings.append(f"{path.relative_to(output_dir)}:{line_no}: secret-like key/value")
                    if len(findings) >= 20:
                        return findings
        except OSError as exc:
            findings.append(f"{path.relative_to(output_dir)}: scan failed: {sanitize_string(str(exc))}")
    return findings


def zip_dir(source_dir: Path, zip_path: Path) -> None:
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(source_dir.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(source_dir))


def main() -> None:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    configured_output = (os.getenv("AUDIT_OUTPUT_DIR") or "").strip()
    output_dir = Path(configured_output) if configured_output else REPO_ROOT / "reports" / f"wb_live_test_curl_audit_{timestamp}"
    if not output_dir.is_absolute():
        output_dir = REPO_ROOT / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    engine = create_engine(db_url_from_settings(), future=True)
    process = None
    log_handle = None
    try:
        account = resolve_account(engine)
        ids = discover_ids(engine, int(account["id"]))
        admin = ensure_audit_admin(engine)
        process, log_handle, base_url, server_status = start_backend(output_dir)
        write_json(output_dir / "meta" / "server.json", server_status)
        if not server_status.get("ready") and server_status.get("started"):
            raise RuntimeError(f"backend did not become ready: {server_status}")
        token = login_with_curl(base_url, admin, output_dir)
        openapi = fetch_openapi(base_url, output_dir)
        db_summary_path = output_dir / "db" / "db_export_summary.json"
        if db_summary_path.exists():
            db_summary = json.loads(db_summary_path.read_text(encoding="utf-8"))
        else:
            db_summary = export_db(engine, account, ids, output_dir)
        endpoint_summary = execute_endpoints(base_url, token, openapi, ids, output_dir)
        secrets_found = final_secret_scan(output_dir)
        meta = {
            "generated_at": datetime.now().isoformat(),
            "account": sanitize(account),
            "discovered_ids": ids,
            "admin_login": {
                "created_temporary_user": True,
                "user_id": admin["id"],
                "email": REDACTED,
                "curl_login_performed": True,
                "password_stored_in_bundle": False,
                "token_stored_in_bundle": False,
            },
            "db_summary": db_summary,
            "endpoint_summary": endpoint_summary,
            "secret_scan": {"status": "PASS" if not secrets_found else "FAIL", "findings": secrets_found},
            "safety": {
                "dangerous_flags_forced_false_for_local_server": list(DANGEROUS_FLAGS),
                "non_get_endpoints": "skipped except auth login to avoid state changes and marketplace writes",
            },
        }
        write_json(output_dir / "meta" / "summary.json", meta)
        write_text(
            output_dir / "README.md",
            "\n".join(
                [
                    "# wb-live-test curl audit bundle",
                    "",
                    f"Generated at: `{meta['generated_at']}`",
                    f"Account: `{ACCOUNT_NAME}` / id `{account['id']}`",
                    f"Endpoint captures: `{endpoint_summary['executed']}` executed, `{endpoint_summary['skipped']}` skipped.",
                    f"DB tables exported: `{len(db_summary.get('tables', {}))}`.",
                    f"Secret scan: `{meta['secret_scan']['status']}`.",
                    "",
                    "Raw auth credentials and bearer tokens are not stored in this bundle.",
                    "Unsafe non-GET endpoints are listed with skip reasons instead of being executed.",
                ]
            ),
        )
        if secrets_found:
            raise RuntimeError(f"refusing to zip because secret scan failed: {secrets_found[:5]}")
        zip_path = REPO_ROOT / f"WB_LIVE_TEST_CURL_AUDIT_{timestamp}.zip"
        zip_dir(output_dir, zip_path)
        print(json.dumps({"bundle_dir": str(output_dir), "zip_path": str(zip_path), "summary": meta}, ensure_ascii=False, indent=2, default=json_default))
    finally:
        stop_backend(process, log_handle)
        engine.dispose()


if __name__ == "__main__":
    main()
