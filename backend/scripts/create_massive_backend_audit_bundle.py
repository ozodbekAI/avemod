#!/usr/bin/env python3
"""Create a comprehensive backend audit bundle with source and endpoint evidence."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import httpx


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.run_full_runtime_endpoint_audit import AuditConfig, db_url_from_settings, hydrate_runtime_config_from_db  # noqa: E402

REDACTED = "<REDACTED>"
SOURCE_INCLUDE = (
    "app",
    "alembic",
    "tests",
    "scripts",
    "docs",
    "deploy",
    ".github",
    "pyproject.toml",
    "alembic.ini",
    "README.md",
    ".env.example",
    "AGENTS.md",
)
EXCLUDE_DIRS = {
    ".git",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "node_modules",
    "reports",
    "audit_100_backend",
    "audit_staging_final",
    "_incoming_projects",
}
EXCLUDE_SUFFIXES = {
    ".pyc",
    ".pyo",
    ".db",
    ".sqlite",
    ".sqlite3",
    ".log",
    ".zip",
    ".tar",
    ".gz",
    ".xlsx",
    ".xls",
    ".csv",
}
WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
SAFE_EXECUTED_METHODS = {"GET", "HEAD", "OPTIONS"}
DANGEROUS_FLAGS = (
    "ENABLE_REPUTATION_PUBLISH",
    "ENABLE_REPUTATION_WRITE_ACTIONS",
    "ENABLE_CLAIMS_SUBMIT",
    "ENABLE_GROUPING_MERGE",
    "ENABLE_CARD_AUTO_APPLY",
)
JWT_RE = re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b")
LONG_SECRET_RE = re.compile(r"\b[A-Za-z0-9_+/=-]{48,}\b")
EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
PHONE_RE = re.compile(r"(?<!\d)(?:\+?\d[\d\s().-]{8,}\d)(?!\d)")
SENSITIVE_KEY_RE = re.compile(
    r'(?i)(access_token|refresh_token|encrypted_token|api_key|password|secret|jwt|authorization)\s*[:=]\s*["\']?[A-Za-z0-9_./+=-]{12,}'
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", encoding="utf-8")


def sanitize_string(value: str) -> str:
    value = JWT_RE.sub(REDACTED, value)
    value = EMAIL_RE.sub(REDACTED, value)
    value = PHONE_RE.sub(REDACTED, value)
    value = LONG_SECRET_RE.sub(REDACTED, value)
    return value


def sanitize_json(value: Any) -> Any:
    if isinstance(value, dict):
        clean: dict[str, Any] = {}
        for key, inner in value.items():
            lowered = str(key).lower()
            if any(token in lowered for token in ("token", "authorization", "password", "secret", "api_key", "jwt", "cookie", "phone", "email", "address", "buyer")):
                clean[str(key)] = REDACTED
            else:
                clean[str(key)] = sanitize_json(inner)
        return clean
    if isinstance(value, list):
        return [sanitize_json(item) for item in value]
    if isinstance(value, str):
        return sanitize_string(value)
    return value


def safe_filename(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "_", value).strip("_").lower()[:180] or "item"


def should_exclude(path: Path) -> bool:
    if any(part in EXCLUDE_DIRS for part in path.parts):
        return True
    if path.suffix.lower() in EXCLUDE_SUFFIXES:
        return True
    if path.name.startswith(".env") and path.name != ".env.example":
        return True
    return False


def copy_source_tree(output_dir: Path) -> dict[str, Any]:
    source_root = output_dir / "source_code"
    copied: list[dict[str, Any]] = []
    skipped: list[str] = []
    for include in SOURCE_INCLUDE:
        src = REPO_ROOT / include
        if not src.exists():
            skipped.append(include)
            continue
        if src.is_file():
            rel = Path(include)
            dst = source_root / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            text = src.read_text(encoding="utf-8", errors="ignore")
            if src.name == ".env.example":
                text = re.sub(r"(?im)^([A-Z0-9_]*(TOKEN|SECRET|PASSWORD|KEY)[A-Z0-9_]*=).*$", r"\1", text)
            dst.write_text(text, encoding="utf-8")
            copied.append({"path": str(rel), "bytes": dst.stat().st_size})
            continue
        for path in src.rglob("*"):
            rel = path.relative_to(REPO_ROOT)
            if should_exclude(rel):
                if path.is_file():
                    skipped.append(str(rel))
                continue
            if path.is_dir():
                continue
            dst = source_root / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                skipped.append(str(rel))
                continue
            dst.write_text(text, encoding="utf-8")
            copied.append({"path": str(rel), "bytes": dst.stat().st_size})
    copied.sort(key=lambda item: item["path"])
    write_json(output_dir / "source_code" / "SOURCE_CODE_INDEX.json", {"copied_files": copied, "skipped": sorted(set(skipped))})
    lines = ["# Source Code Index", "", f"Copied source files: `{len(copied)}`", "", "## Files", ""]
    lines.extend(f"- `{item['path']}` ({item['bytes']} bytes)" for item in copied)
    if skipped:
        lines.extend(["", "## Skipped For Safety/Noise", ""])
        lines.extend(f"- `{item}`" for item in sorted(set(skipped))[:500])
    write_text(output_dir / "source_code" / "SOURCE_CODE_INDEX.md", "\n".join(lines))
    return {"copied_count": len(copied), "skipped_count": len(set(skipped)), "bytes": sum(item["bytes"] for item in copied)}


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def start_backend(output_dir: Path) -> tuple[subprocess.Popen[str] | None, Any | None, str, dict[str, Any]]:
    base_url = (os.getenv("BASE_URL") or "").strip().rstrip("/")
    if base_url:
        return None, None, base_url, {"started": False, "reason": "BASE_URL provided"}
    port = int(os.getenv("AUDIT_LOCAL_PORT") or free_port())
    base_url = f"http://127.0.0.1:{port}"
    log_path = output_dir / "runtime" / "local_backend_server.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_handle = log_path.open("w", encoding="utf-8")
    env = os.environ.copy()
    for name in DANGEROUS_FLAGS:
        env[name] = "false"
    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port)],
        cwd=REPO_ROOT,
        env=env,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        text=True,
    )
    status = wait_for_backend(base_url)
    status.update({"started": True, "base_url": base_url, "pid": process.pid, "log_file": str(log_path.relative_to(output_dir))})
    return process, log_handle, base_url, status


def wait_for_backend(base_url: str) -> dict[str, Any]:
    started = time.perf_counter()
    last_error = ""
    with httpx.Client(timeout=httpx.Timeout(3.0, connect=1.0), follow_redirects=True) as client:
        while time.perf_counter() - started < 30:
            try:
                response = client.get(f"{base_url}/openapi.json")
                if response.status_code == 200:
                    return {"ready": True, "duration_ms": int((time.perf_counter() - started) * 1000)}
                last_error = f"status {response.status_code}"
            except Exception as exc:
                last_error = exc.__class__.__name__
            time.sleep(0.5)
    return {"ready": False, "duration_ms": int((time.perf_counter() - started) * 1000), "last_error": sanitize_string(last_error)}


def stop_backend(process: subprocess.Popen[str] | None, log_handle: Any | None) -> None:
    log_path = Path(log_handle.name) if log_handle is not None and getattr(log_handle, "name", None) else None
    if process is not None and process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
    if log_handle is not None:
        log_handle.close()
    if log_path and log_path.exists():
        log_path.write_text(sanitize_string(log_path.read_text(encoding="utf-8", errors="ignore")), encoding="utf-8")


def fetch_openapi(base_url: str) -> dict[str, Any]:
    with httpx.Client(timeout=httpx.Timeout(30.0, connect=5.0), follow_redirects=True) as client:
        response = client.get(f"{base_url}/openapi.json")
        response.raise_for_status()
        return response.json()


def sample_value(name: str, schema: dict[str, Any] | None = None) -> Any:
    lowered = name.lower()
    if lowered in {"account_id", "accountid"}:
        return int(os.getenv("ACCOUNT_ID") or os.getenv("SELLER_OWN_ACCOUNT_ID") or "1")
    if lowered in {"limit", "page_size"}:
        return 20
    if lowered == "offset":
        return 0
    if "date_from" in lowered or lowered in {"from_date", "start_date"}:
        return os.getenv("AUDIT_DATE_FROM") or "2026-01-01"
    if "date_to" in lowered or lowered in {"to_date", "end_date"}:
        return os.getenv("AUDIT_DATE_TO") or "2026-01-31"
    if lowered in {"nm_id", "nmid"}:
        return int(os.getenv("NM_ID") or os.getenv("SELLER_TEST_NM_ID") or "1")
    if lowered == "sku_id":
        return int(os.getenv("SKU_ID") or "1")
    if lowered == "action_id":
        return int(os.getenv("ACTION_ID") or "1")
    if lowered.endswith("_id") or lowered == "id":
        return 1
    if schema:
        typ = schema.get("type")
        if typ == "integer":
            return 1
        if typ == "number":
            return 1
        if typ == "boolean":
            return False
        if typ == "array":
            return []
    return "sample"


def hydrate_sample_ids(output_dir: Path) -> dict[str, Any]:
    from sqlalchemy import create_engine, text

    result: dict[str, Any] = {"resolved": False, "values": {}}
    database_url = db_url_from_settings()
    if not database_url:
        result["warning"] = "database URL unavailable"
        write_json(output_dir / "runtime" / "sample_ids.json", result)
        return result
    engine = create_engine(database_url, future=True)
    try:
        with engine.connect() as conn:
            sku = conn.execute(text("SELECT id, nm_id FROM core_sku ORDER BY id ASC LIMIT 1")).mappings().first()
            action = conn.execute(text("SELECT id FROM action_recommendations ORDER BY id ASC LIMIT 1")).mappings().first()
            portal_action = conn.execute(text("SELECT id FROM unified_actions ORDER BY id ASC LIMIT 1")).mappings().first()
            if sku is not None:
                os.environ.setdefault("SKU_ID", str(int(sku["id"])))
                if sku["nm_id"] is not None:
                    os.environ.setdefault("NM_ID", str(int(sku["nm_id"])))
            if action is not None:
                os.environ.setdefault("ACTION_ID", str(int(action["id"])))
            elif portal_action is not None:
                os.environ.setdefault("ACTION_ID", str(int(portal_action["id"])))
            result = {
                "resolved": True,
                "values": {
                    "SKU_ID": os.environ.get("SKU_ID"),
                    "NM_ID": os.environ.get("NM_ID"),
                    "ACTION_ID": os.environ.get("ACTION_ID"),
                },
            }
    except Exception as exc:
        result["warning"] = exc.__class__.__name__
    finally:
        engine.dispose()
    write_json(output_dir / "runtime" / "sample_ids.json", result)
    return result


def build_request(route_path: str, method: str, operation: dict[str, Any]) -> dict[str, Any]:
    path = route_path
    query: dict[str, Any] = {}
    for param in operation.get("parameters") or []:
        name = param.get("name")
        if not name:
            continue
        value = sample_value(str(name), param.get("schema") or {})
        if param.get("in") == "path":
            path = path.replace("{" + str(name) + "}", str(value))
        elif param.get("in") == "query" and (param.get("required") or str(name).lower() in {"account_id", "limit", "offset"}):
            query[str(name)] = value
    body = None
    if "requestBody" in operation:
        body = sample_body(operation.get("requestBody") or {})
    return {"path": path, "query": query, "body": body, "method": method.upper()}


def sample_body(request_body: dict[str, Any]) -> dict[str, Any]:
    content = request_body.get("content") or {}
    schema = None
    for meta in content.values():
        if isinstance(meta, dict) and meta.get("schema"):
            schema = meta["schema"]
            break
    if not schema:
        return {"sample": True}
    props = schema.get("properties") or {}
    required = schema.get("required") or []
    body: dict[str, Any] = {}
    for name in required:
        body[str(name)] = sample_value(str(name), props.get(name) or {})
    if not body:
        body["sample"] = True
    return body


def endpoint_url(base_url: str, path: str, query: dict[str, Any]) -> str:
    url = f"{base_url.rstrip('/')}{path}"
    if query:
        url += "?" + urlencode(query)
    return url


def resolve_runtime_auth(output_dir: Path, base_url: str) -> dict[str, Any]:
    config = AuditConfig(
        base_url=base_url,
        api_prefix="/api/v1",
        access_token=(os.getenv("ACCESS_TOKEN") or os.getenv("SELLER_ACCESS_TOKEN") or "").strip() or None,
        account_id=(os.getenv("ACCOUNT_ID") or os.getenv("SELLER_OWN_ACCOUNT_ID") or "").strip() or None,
        audit_env="local_full_bundle",
        output_dir=output_dir,
        run_commands=False,
    )
    setup = hydrate_runtime_config_from_db(config)
    if config.account_id:
        os.environ["ACCOUNT_ID"] = str(config.account_id)
    safe_setup = {
        "access_token_resolved": setup.get("access_token_resolved"),
        "account_id_resolved": setup.get("account_id_resolved"),
        "token_source": setup.get("token_source"),
        "account_source": setup.get("account_source"),
        "account_id": REDACTED if config.account_id else None,
        "token_values_saved": False,
        "warnings": setup.get("warnings") or [],
    }
    write_json(output_dir / "runtime" / "runtime_auth_setup.json", safe_setup)
    return {"access_token": config.access_token, "account_id": config.account_id, "safe_setup": safe_setup}


def execute_endpoint_evidence(output_dir: Path, base_url: str, openapi: dict[str, Any], server_ready: bool, access_token: str | None) -> dict[str, Any]:
    evidence_dir = output_dir / "endpoint_evidence"
    records: list[dict[str, Any]] = []
    auth_token = (access_token or os.getenv("ACCESS_TOKEN") or os.getenv("SELLER_ACCESS_TOKEN") or "").strip()
    headers = {"Accept": "application/json"}
    if auth_token:
        headers["Authorization"] = f"Bearer {auth_token}"
    sequence = 0
    with httpx.Client(timeout=httpx.Timeout(45.0, connect=10.0), follow_redirects=True) as client:
        for route_path, methods in sorted((openapi.get("paths") or {}).items()):
            for method, operation in sorted(methods.items()):
                if method.lower() not in {"get", "post", "put", "patch", "delete", "head", "options"}:
                    continue
                sequence += 1
                request = build_request(route_path, method, operation)
                operation_id = operation.get("operationId") or f"{method}_{route_path}"
                record: dict[str, Any] = {
                    "sequence": sequence,
                    "operation_id": operation_id,
                    "method": request["method"],
                    "openapi_path": route_path,
                    "executed_path": request["path"],
                    "query": request["query"],
                    "request_body": sanitize_json(request["body"]),
                    "tags": operation.get("tags") or [],
                    "summary": operation.get("summary"),
                    "executed": False,
                    "skip_reason": None,
                    "status_code": None,
                    "duration_ms": None,
                    "response": None,
                }
                if not server_ready:
                    record["skip_reason"] = "LOCAL_BACKEND_NOT_READY"
                    record["response"] = {"status": "SKIPPED_BACKEND_NOT_READY"}
                elif request["method"] in WRITE_METHODS:
                    record["skip_reason"] = "SKIPPED_UNSAFE_WRITE_OR_MUTATION"
                    record["response"] = {
                        "status": "SKIPPED_UNSAFE_WRITE",
                        "reason": "Mutation endpoints are documented with request templates but not executed in the full audit bundle to avoid marketplace/DB writes.",
                    }
                elif request["method"] not in SAFE_EXECUTED_METHODS:
                    record["skip_reason"] = "SKIPPED_UNSUPPORTED_METHOD"
                    record["response"] = {"status": "SKIPPED_UNSUPPORTED_METHOD"}
                else:
                    started = time.perf_counter()
                    try:
                        response = client.request(request["method"], endpoint_url(base_url, request["path"], request["query"]), headers=headers)
                        duration_ms = int((time.perf_counter() - started) * 1000)
                        try:
                            body = response.json()
                        except Exception:
                            body = {"text": response.text[:4000]}
                        record.update(
                            {
                                "executed": True,
                                "status_code": response.status_code,
                                "duration_ms": duration_ms,
                                "response": sanitize_json(body),
                            }
                        )
                    except Exception as exc:
                        record.update(
                            {
                                "executed": True,
                                "status_code": 0,
                                "duration_ms": int((time.perf_counter() - started) * 1000),
                                "response": {"error": exc.__class__.__name__},
                            }
                        )
                filename = f"{sequence:04d}_{safe_filename(request['method'] + '_' + route_path)}.json"
                record["evidence_file"] = f"endpoint_evidence/responses/{filename}"
                write_json(evidence_dir / "responses" / filename, record)
                records.append(record)
    executed = [item for item in records if item["executed"]]
    skipped = [item for item in records if not item["executed"]]
    summary = {
        "total_openapi_operations": len(records),
        "executed_read_only_operations": len(executed),
        "skipped_mutation_or_unavailable_operations": len(skipped),
        "status_codes": status_counts(executed),
        "records": [
            {
                "operation_id": item["operation_id"],
                "method": item["method"],
                "path": item["openapi_path"],
                "executed": item["executed"],
                "status_code": item["status_code"],
                "skip_reason": item["skip_reason"],
                "evidence_file": item["evidence_file"],
            }
            for item in records
        ],
    }
    write_json(evidence_dir / "ALL_ENDPOINTS_REQUEST_RESPONSE_INDEX.json", summary)
    write_endpoint_markdown(evidence_dir / "ALL_ENDPOINTS_REQUEST_RESPONSE_INDEX.md", summary)
    return summary


def status_counts(records: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in records:
        key = str(item.get("status_code"))
        counts[key] = counts.get(key, 0) + 1
    return counts


def write_endpoint_markdown(path: Path, summary: dict[str, Any]) -> None:
    lines = [
        "# All Endpoints Request/Response Index",
        "",
        f"- Total OpenAPI operations: `{summary['total_openapi_operations']}`",
        f"- Executed read-only operations: `{summary['executed_read_only_operations']}`",
        f"- Skipped mutation/unavailable operations: `{summary['skipped_mutation_or_unavailable_operations']}`",
        "",
        "## Endpoint Evidence",
        "",
        "| Method | Path | Executed | Status | Skip reason | Evidence |",
        "|---|---|---:|---:|---|---|",
    ]
    for item in summary["records"]:
        lines.append(
            f"| `{item['method']}` | `{item['path']}` | `{item['executed']}` | `{item['status_code']}` | `{item['skip_reason'] or ''}` | `{item['evidence_file']}` |"
        )
    write_text(path, "\n".join(lines))


def copy_existing_audits(output_dir: Path) -> None:
    for name in ("audit_100_backend", "audit_staging_final"):
        src = REPO_ROOT / name
        if src.exists():
            shutil.copytree(src, output_dir / "existing_audits" / name, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache"))


def write_architecture_docs(output_dir: Path, source_summary: dict[str, Any], endpoint_summary: dict[str, Any], openapi: dict[str, Any]) -> None:
    paths = openapi.get("paths") or {}
    tags: dict[str, int] = {}
    for methods in paths.values():
        for operation in methods.values():
            if not isinstance(operation, dict):
                continue
            for tag in operation.get("tags") or ["untagged"]:
                tags[tag] = tags.get(tag, 0) + 1
    docs = output_dir / "docs"
    write_text(
        docs / "FULL_BACKEND_AUDIT_README.md",
        "\n".join(
            [
                "# Full Backend Code And Endpoint Audit",
                "",
                "This bundle contains a safety-filtered full backend source snapshot, OpenAPI endpoint catalog, request/response evidence for every documented endpoint, existing audit evidence, and architecture notes.",
                "",
                "## Main Folders",
                "",
                "- `source_code/` - backend source snapshot excluding caches, local env files, databases, logs, zips, and generated noise.",
                "- `endpoint_evidence/` - one JSON evidence file per OpenAPI operation plus a global index.",
                "- `existing_audits/` - previously generated backend/staging audit evidence when available.",
                "- `docs/` - architecture and module connection explanations.",
                "- `security/` - bundle secret scan result.",
                "",
                "## Safety",
                "",
                "Mutation/write endpoints are not executed automatically. They are included with request templates and `SKIPPED_UNSAFE_WRITE` evidence so the endpoint list is complete without performing marketplace or DB-changing operations.",
            ]
        ),
    )
    write_text(
        docs / "BACKEND_ARCHITECTURE_FULL.md",
        "\n".join(
            [
                "# Backend Architecture Full Map",
                "",
                "## Runtime Entry",
                "",
                "- `app/main.py` builds the FastAPI app, attaches request timing middleware, configures CORS, starts the optional scheduler in lifespan, and mounts `app.api.router.api_router` under `API_V1_PREFIX`.",
                "- `app/api/router.py` is the central module wiring layer. It includes health, auth, accounts, portal, money, marts, costs, WB domain modules, exports, dashboard, and optional operator surfaces.",
                "",
                "## Layering",
                "",
                "- `app/modules/*/router.py` exposes HTTP endpoints.",
                "- `app/services/*.py` owns orchestration, aggregation, optional adapter isolation, and business workflows.",
                "- `app/repositories/*.py` owns non-trivial persistence queries.",
                "- `app/models/*.py` defines finance-owned SQLAlchemy persistence models.",
                "- `app/schemas/*.py` defines API contracts and response/request shapes.",
                "- `app/core/*.py` owns shared config, DB session, security, pagination, parsing, cache, observability, and common math helpers.",
                "- `app/jobs/*.py` wires scheduled refresh jobs.",
                "",
                "## Product Boundary",
                "",
                "Finance remains the authoritative auth/account/token/money backend. Portal endpoints aggregate finance-owned data and optional modules. Optional modules return `disabled`, `not_configured`, `unavailable`, `empty`, or `beta` rather than breaking core finance pages.",
                "",
                "## Source Snapshot",
                "",
                f"- Copied files: `{source_summary['copied_count']}`",
                f"- Copied bytes: `{source_summary['bytes']}`",
                "",
                "## Endpoint Snapshot",
                "",
                f"- Total OpenAPI operations: `{endpoint_summary['total_openapi_operations']}`",
                f"- Executed read-only operations: `{endpoint_summary['executed_read_only_operations']}`",
                f"- Skipped mutation/unavailable operations: `{endpoint_summary['skipped_mutation_or_unavailable_operations']}`",
            ]
        ),
    )
    lines = ["# Module Connections", "", "## OpenAPI Tags", ""]
    lines.extend(f"- `{tag}`: {count} operations" for tag, count in sorted(tags.items()))
    lines.extend(
        [
            "",
            "## Core Connections",
            "",
            "- Auth routes depend on `AuthService`, JWT helpers in `app/core/security.py`, and `AuthUser` persistence.",
            "- Account routes and portal routes enforce server-side account access through finance-owned auth/account boundaries.",
            "- Portal routes call `PortalService` and focused adapters for checker, grouping, StockOps, reputation, and claims; adapter failures are isolated from money/actions/products.",
            "- Money, costs, marts, data quality, and dashboard routes reuse finance repositories/models instead of duplicating business math.",
            "- Sync routers schedule or trigger WB data ingestion, while write/apply actions remain disabled or confirmation-gated for MVP safety.",
        ]
    )
    write_text(docs / "MODULE_CONNECTIONS.md", "\n".join(lines))


def run_verification(output_dir: Path) -> None:
    commands = [
        ("compileall", [sys.executable, "-m", "compileall", "-f", "-q", "app", "tests", "alembic", "scripts"]),
        ("pytest_full", [sys.executable, "-m", "pytest", "-q"]),
    ]
    results = []
    for name, command in commands:
        started = time.perf_counter()
        result = subprocess.run(command, cwd=REPO_ROOT, text=True, capture_output=True, timeout=1800)
        payload = {
            "name": name,
            "command": command,
            "returncode": result.returncode,
            "duration_ms": int((time.perf_counter() - started) * 1000),
            "stdout_tail": sanitize_string(result.stdout[-8000:]),
            "stderr_tail": sanitize_string(result.stderr[-8000:]),
        }
        write_json(output_dir / "verification" / f"{name}.json", payload)
        results.append(payload)
    write_json(output_dir / "verification" / "verification_summary.json", results)


def secret_scan(output_dir: Path) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    classified_source_literals: list[dict[str, str]] = []
    for path in output_dir.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in {".py", ".md", ".json", ".txt", ".toml", ".yml", ".yaml", ".ini", ".example"}:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        rel = str(path.relative_to(output_dir))
        target = classified_source_literals if rel.startswith("source_code/") else findings
        if JWT_RE.search(text):
            target.append({"path": rel, "pattern": "jwt_like_token"})
        if re.search(r"Bearer\s+(?!<REDACTED>)[A-Za-z0-9._-]+", text):
            target.append({"path": rel, "pattern": "raw_bearer"})
        for line in text.splitlines():
            if REDACTED in line or "replace-with" in line or "example" in line.lower():
                continue
            if SENSITIVE_KEY_RE.search(line):
                target.append({"path": rel, "pattern": "sensitive_key_value"})
                break
    write_json(
        output_dir / "security" / "bundle_secret_scan.json",
        {
            "passed": not findings,
            "findings": findings[:200],
            "classified_source_literal_findings": classified_source_literals[:300],
            "note": "Source-code regex/test literals are classified separately; runtime evidence and docs still fail on raw token-like values.",
        },
    )
    return findings


def create_zip(output_dir: Path, zip_path: Path) -> Path:
    write_text(output_dir / "ZIP_PATH.txt", str(zip_path))
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in output_dir.rglob("*"):
            if path.is_file():
                archive.write(path, path.relative_to(REPO_ROOT))
    return zip_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--skip-tests", action="store_true")
    args = parser.parse_args()
    output_dir = args.output_dir or REPO_ROOT / f"audit_full_backend_code_endpoint_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    if not output_dir.is_absolute():
        output_dir = REPO_ROOT / output_dir
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)
    write_json(output_dir / "manifest.json", {"generated_at": utc_now(), "repo_root": str(REPO_ROOT), "token_values_saved": False})
    source_summary = copy_source_tree(output_dir)
    process = None
    log_handle = None
    try:
        process, log_handle, base_url, server_status = start_backend(output_dir)
        write_json(output_dir / "runtime" / "runtime_setup.json", {"base_url": base_url, "server": server_status})
        auth_context = resolve_runtime_auth(output_dir, base_url) if server_status.get("ready") else {"access_token": None, "safe_setup": {}}
        hydrate_sample_ids(output_dir)
        openapi = fetch_openapi(base_url) if server_status.get("ready") else {"paths": {}}
        write_json(output_dir / "endpoint_evidence" / "openapi.json", sanitize_json(openapi))
        endpoint_summary = execute_endpoint_evidence(output_dir, base_url, openapi, bool(server_status.get("ready")), auth_context.get("access_token"))
    finally:
        stop_backend(process, log_handle)
    copy_existing_audits(output_dir)
    write_architecture_docs(output_dir, source_summary, endpoint_summary, openapi)
    if not args.skip_tests:
        run_verification(output_dir)
    findings = secret_scan(output_dir)
    zip_path = REPO_ROOT / f"FULL_BACKEND_CODE_ENDPOINT_AUDIT_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
    summary = {
        "output_dir": str(output_dir),
        "zip_path": str(zip_path),
        "source": source_summary,
        "endpoints": endpoint_summary | {"records": f"{len(endpoint_summary.get('records', []))} records, see endpoint_evidence/ALL_ENDPOINTS_REQUEST_RESPONSE_INDEX.json"},
        "secret_scan_passed": not findings,
    }
    write_json(output_dir / "FINAL_FULL_BACKEND_AUDIT_SUMMARY.json", summary)
    write_text(
        output_dir / "FINAL_FULL_BACKEND_AUDIT_SUMMARY.md",
        "\n".join(
            [
                "# Final Full Backend Audit Summary",
                "",
                f"- Output dir: `{output_dir}`",
                f"- Zip path: `{zip_path}`",
                f"- Source files copied: `{source_summary['copied_count']}`",
                f"- Endpoint operations indexed: `{endpoint_summary['total_openapi_operations']}`",
                f"- Read-only endpoint operations executed: `{endpoint_summary['executed_read_only_operations']}`",
                f"- Mutation/unavailable operations documented but skipped: `{endpoint_summary['skipped_mutation_or_unavailable_operations']}`",
                f"- Secret scan passed: `{not findings}`",
                "",
                "Mutation endpoints are present in the endpoint evidence with request templates and explicit skip reasons; they were not executed to avoid unsafe writes.",
            ]
        ),
    )
    create_zip(output_dir, zip_path)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0 if not findings else 2


if __name__ == "__main__":
    raise SystemExit(main())
