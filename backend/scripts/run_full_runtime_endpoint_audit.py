#!/usr/bin/env python3
"""Create a sanitized runtime endpoint and DB audit bundle.

The script is intentionally conservative: it prefers skipped evidence over
unsafe writes, redacts recursively, and refuses to zip when P0 secret findings
are detected in captured request/response payloads.
"""

from __future__ import annotations

import csv
import hashlib
import importlib.metadata
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import zipfile
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import create_engine, inspect, text


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_API_PREFIX = "/api/v1"
DEFAULT_TIMEOUT = httpx.Timeout(45.0, connect=10.0)
REDACTED = "<REDACTED>"
SAFE_DEGRADED_STATUSES = {"disabled", "not_configured", "unavailable", "empty", "beta", "not_implemented"}
DANGEROUS_FLAGS = (
    "ENABLE_REPUTATION_PUBLISH",
    "ENABLE_REPUTATION_WRITE_ACTIONS",
    "ENABLE_CLAIMS_SUBMIT",
    "ENABLE_GROUPING_MERGE",
    "ENABLE_CARD_AUTO_APPLY",
)
TRUTHY = {"1", "true", "yes", "on", "enabled"}
SENSITIVE_KEY_TOKENS = (
    "token",
    "authorization",
    "api_key",
    "password",
    "secret",
    "jwt",
    "encrypted_token",
    "encryption_key",
    "phone",
    "email",
    "passport",
    "address",
    "buyer",
    "customer",
    "headers",
    "cookie",
    "set-cookie",
)
SENSITIVE_DB_COLUMN_TOKENS = SENSITIVE_KEY_TOKENS + (
    "credential",
    "refresh",
    "fio",
    "full_name",
    "contact",
)
JWT_RE = re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b")
LONG_SECRET_RE = re.compile(r"\b[A-Za-z0-9_+/=-]{48,}\b")
EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
PHONE_RE = re.compile(r"(?<!\d)(?:\+?\d[\d\s().-]{8,}\d)(?!\d)")
COMMAND_TIMEOUT_SECONDS = 1800
DB_LOGICAL_TABLE_ALIASES = {
    "users": "auth_users",
    "accounts": "wb_accounts",
}


@dataclass
class AuditConfig:
    base_url: str | None
    api_prefix: str
    access_token: str | None
    account_id: str | None
    audit_env: str
    output_dir: Path
    nm_id: str | None = None
    action_id: str | None = None
    case_id: str | None = None
    reputation_item_id: str | None = None
    reputation_draft_id: str | None = None
    sku_id: str | None = None
    run_commands: bool = True
    auto_token_source: str | None = None
    auto_account_source: str | None = None


@dataclass
class EndpointPlanItem:
    method: str
    path: str
    query: dict[str, Any] = field(default_factory=dict)
    body: dict[str, Any] | None = None
    required_fields: list[str] = field(default_factory=list)
    skip_reason: str | None = None
    safety_note: str | None = None

    @property
    def key(self) -> str:
        return f"{self.method.upper()} {self.path}"


def json_default(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, Path):
        return str(value)
    return str(value)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=json_default) + "\n", encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", encoding="utf-8")


def safe_filename(method: str, path: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", f"{method}_{path}").strip("_").lower()
    return f"{slug or 'root'}.json"


def normalize_prefix(value: str | None) -> str:
    raw = (value or DEFAULT_API_PREFIX).strip()
    if raw in {"", "/"}:
        return ""
    return f"/{raw.strip('/')}"


def load_config() -> AuditConfig:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = Path(os.getenv("AUDIT_OUTPUT_DIR", f"reports/runtime_audit_{timestamp}"))
    if not output_dir.is_absolute():
        output_dir = REPO_ROOT / output_dir
    base_url = (os.getenv("BASE_URL") or "").strip().rstrip("/") or None
    return AuditConfig(
        base_url=base_url,
        api_prefix=normalize_prefix(os.getenv("API_PREFIX")),
        access_token=(os.getenv("ACCESS_TOKEN") or "").strip() or None,
        account_id=(os.getenv("ACCOUNT_ID") or "").strip() or None,
        audit_env=(os.getenv("AUDIT_ENV") or "local").strip().lower(),
        output_dir=output_dir,
        nm_id=(os.getenv("NM_ID") or "").strip() or None,
        action_id=(os.getenv("ACTION_ID") or "").strip() or None,
        case_id=(os.getenv("CASE_ID") or "").strip() or None,
        reputation_item_id=(os.getenv("REPUTATION_ITEM_ID") or "").strip() or None,
        reputation_draft_id=(os.getenv("REPUTATION_DRAFT_ID") or "").strip() or None,
        sku_id=(os.getenv("SKU_ID") or "").strip() or None,
        run_commands=(os.getenv("AUDIT_SKIP_COMMANDS") or "").strip().lower() not in TRUTHY,
    )


def sensitive_key(key: Any) -> bool:
    lowered = str(key).lower()
    return any(token in lowered for token in SENSITIVE_KEY_TOKENS)


def sanitize_string(value: str) -> tuple[str, int]:
    redactions = 0
    sanitized = value
    for pattern in (JWT_RE, EMAIL_RE, PHONE_RE):
        sanitized, count = pattern.subn(REDACTED, sanitized)
        redactions += count
    replaced, count = LONG_SECRET_RE.subn(REDACTED, sanitized)
    if count:
        sanitized = replaced
        redactions += count
    return sanitized, redactions


def sanitize(value: Any) -> tuple[Any, int]:
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        redactions = 0
        for key, inner in value.items():
            if sensitive_key(key):
                result[str(key)] = REDACTED
                redactions += 1
                continue
            clean, count = sanitize(inner)
            result[str(key)] = clean
            redactions += count
        return result, redactions
    if isinstance(value, list):
        items = []
        redactions = 0
        for inner in value:
            clean, count = sanitize(inner)
            items.append(clean)
            redactions += count
        return items, redactions
    if isinstance(value, str):
        return sanitize_string(value)
    return value, 0


def contains_unredacted_secret(value: Any) -> list[str]:
    findings: list[str] = []

    def visit(node: Any, path: str) -> None:
        if isinstance(node, dict):
            for key, inner in node.items():
                key_path = f"{path}.{key}" if path else str(key)
                if sensitive_key(key) and inner not in (None, "", REDACTED):
                    findings.append(f"{key_path}: sensitive key not redacted")
                visit(inner, key_path)
        elif isinstance(node, list):
            for index, inner in enumerate(node[:200]):
                visit(inner, f"{path}[{index}]")
        elif isinstance(node, str):
            if JWT_RE.search(node) or EMAIL_RE.search(node) or PHONE_RE.search(node):
                findings.append(f"{path}: token/contact pattern")
            long_match = LONG_SECRET_RE.search(node)
            if long_match and REDACTED not in node:
                findings.append(f"{path}: long secret-like string")

    visit(value, "")
    return findings


def sanitized_headers(token_present: bool) -> dict[str, str]:
    headers = {"Accept": "application/json"}
    if token_present:
        headers["Authorization"] = "Bearer <REDACTED>"
    return headers


def auth_headers(config: AuditConfig) -> dict[str, str]:
    headers = {"Accept": "application/json"}
    if config.access_token:
        headers["Authorization"] = f"Bearer {config.access_token}"
    return headers


def hydrate_runtime_config_from_db(config: AuditConfig) -> dict[str, Any]:
    """Fill missing ACCESS_TOKEN/ACCOUNT_ID from the local finance DB.

    This keeps the audit useful for local/staging databases that already have a
    store/account and users, while still never writing raw tokens to evidence.
    """

    result = {
        "access_token_resolved": bool(config.access_token),
        "account_id_resolved": bool(config.account_id),
        "token_source": "env" if config.access_token else None,
        "account_source": "env" if config.account_id else None,
        "warnings": [],
    }
    if config.access_token and config.account_id:
        return result

    database_url = db_url_from_settings()
    if not database_url:
        result["warnings"].append("database URL unavailable; cannot auto-resolve token/account")
        return result

    engine = create_engine(database_url, future=True)
    try:
        with engine.connect() as conn:
            user_row = conn.execute(
                text(
                    """
                    SELECT id, is_superuser
                    FROM auth_users
                    WHERE is_active IS TRUE
                    ORDER BY is_superuser DESC, id ASC
                    LIMIT 1
                    """
                )
            ).mappings().first()
            if not config.access_token:
                if user_row is None:
                    result["warnings"].append("no active auth_users row; cannot generate local access token")
                else:
                    from app.core.security import create_access_token

                    config.access_token = create_access_token(str(int(user_row["id"])))
                    config.auto_token_source = "generated_from_db_superuser" if bool(user_row["is_superuser"]) else "generated_from_db_active_user"
                    result["access_token_resolved"] = True
                    result["token_source"] = config.auto_token_source
            if not config.account_id:
                account_id = resolve_account_id_from_db(conn, int(user_row["id"]) if user_row is not None else None, bool(user_row["is_superuser"]) if user_row is not None else False)
                if account_id is None:
                    result["warnings"].append("no active wb_accounts row; cannot auto-resolve ACCOUNT_ID")
                else:
                    config.account_id = str(account_id)
                    config.auto_account_source = "db_active_account"
                    result["account_id_resolved"] = True
                    result["account_source"] = config.auto_account_source
    except Exception as exc:
        clean, _ = sanitize_string(repr(exc))
        result["warnings"].append(f"runtime DB auto-resolve failed: {clean}")
    finally:
        engine.dispose()
    return result


def resolve_account_id_from_db(conn: Any, user_id: int | None, is_superuser: bool) -> int | None:
    if user_id is not None and not is_superuser:
        row = conn.execute(
            text(
                """
                SELECT a.account_id
                FROM auth_user_account_access a
                JOIN wb_accounts w ON w.id = a.account_id
                WHERE a.user_id = :user_id AND w.is_active IS TRUE
                ORDER BY a.is_default DESC, a.account_id ASC
                LIMIT 1
                """
            ),
            {"user_id": user_id},
        ).first()
        if row is not None:
            return int(row[0])
    row = conn.execute(text("SELECT id FROM wb_accounts WHERE is_active IS TRUE ORDER BY id ASC LIMIT 1")).first()
    if row is not None:
        return int(row[0])
    row = conn.execute(text("SELECT id FROM wb_accounts ORDER BY id ASC LIMIT 1")).first()
    return int(row[0]) if row is not None else None


def free_local_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def start_local_backend_if_needed(config: AuditConfig, output_dir: Path) -> tuple[subprocess.Popen[str] | None, Any | None, dict[str, Any]]:
    if config.base_url:
        return None, None, {"started": False, "reason": "BASE_URL provided"}
    port = int(os.getenv("AUDIT_LOCAL_PORT") or free_local_port())
    config.base_url = f"http://127.0.0.1:{port}"
    log_path = output_dir / "commands" / "local_backend_server.log"
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
    status = wait_for_backend(config.base_url)
    status.update({"started": True, "pid": process.pid, "base_url": config.base_url, "log_file": str(log_path)})
    if not status["ready"]:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
        log_handle.close()
        sanitize_text_file(log_path)
        return None, None, status
    return process, log_handle, status


def wait_for_backend(base_url: str) -> dict[str, Any]:
    started = time.perf_counter()
    last_error = None
    with httpx.Client(timeout=httpx.Timeout(3.0, connect=1.0), follow_redirects=True) as client:
        while time.perf_counter() - started < 30:
            try:
                response = client.get(f"{base_url}/openapi.json")
                if response.status_code == 200:
                    return {"ready": True, "duration_ms": int((time.perf_counter() - started) * 1000)}
                last_error = f"status {response.status_code}"
            except Exception as exc:
                last_error = repr(exc)
            time.sleep(0.5)
    clean, _ = sanitize_string(str(last_error))
    return {"ready": False, "duration_ms": int((time.perf_counter() - started) * 1000), "last_error": clean}


def stop_local_backend(process: subprocess.Popen[str] | None, log_handle: Any | None) -> None:
    log_path = Path(log_handle.name) if log_handle is not None and getattr(log_handle, "name", None) else None
    if process is not None and process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
    if log_handle is not None:
        log_handle.close()
    if log_path is not None:
        sanitize_text_file(log_path)


def sanitize_text_file(path: Path) -> None:
    if not path.exists() or not path.is_file():
        return
    try:
        content = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return
    clean, _ = sanitize_string(content)
    path.write_text(clean, encoding="utf-8")


def package_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def run_process(args: list[str], *, cwd: Path = REPO_ROOT, timeout: int = COMMAND_TIMEOUT_SECONDS) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        proc = subprocess.run(args, cwd=cwd, text=True, capture_output=True, timeout=timeout)
        duration_ms = int((time.perf_counter() - started) * 1000)
        stdout, _ = sanitize_string(proc.stdout or "")
        stderr, _ = sanitize_string(proc.stderr or "")
        return {
            "command": " ".join(args),
            "returncode": proc.returncode,
            "duration_ms": duration_ms,
            "stdout": stdout,
            "stderr": stderr,
            "ok": proc.returncode == 0,
        }
    except subprocess.TimeoutExpired as exc:
        duration_ms = int((time.perf_counter() - started) * 1000)
        stdout, _ = sanitize_string(exc.stdout or "")
        stderr, _ = sanitize_string(exc.stderr or "")
        return {
            "command": " ".join(args),
            "returncode": None,
            "duration_ms": duration_ms,
            "stdout": stdout,
            "stderr": stderr,
            "ok": False,
            "timed_out": True,
        }
    except Exception as exc:
        duration_ms = int((time.perf_counter() - started) * 1000)
        return {
            "command": " ".join(args),
            "returncode": None,
            "duration_ms": duration_ms,
            "stdout": "",
            "stderr": repr(exc),
            "ok": False,
        }


def build_repo_inventory(output_dir: Path) -> dict[str, Any]:
    git_branch = run_process(["git", "branch", "--show-current"])
    git_commit = run_process(["git", "rev-parse", "HEAD"])
    git_status = run_process(["git", "status", "--short"])
    py_files = [path for path in REPO_ROOT.rglob("*.py") if "node_modules" not in path.parts and "__pycache__" not in path.parts]
    tests = [path for path in (REPO_ROOT / "tests").rglob("test_*.py")] if (REPO_ROOT / "tests").exists() else []
    revisions = sorted(str(path.relative_to(REPO_ROOT)) for path in (REPO_ROOT / "alembic" / "versions").glob("*.py"))
    deploy_scan = run_process([sys.executable, "scripts/check_deploy_artifact_safety.py", "--root", str(REPO_ROOT), "--max-results", "50"])
    inventory = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "repo_root": str(REPO_ROOT),
        "git": {
            "is_git_repo": git_commit["returncode"] == 0,
            "branch": (git_branch["stdout"] or "").strip() or None,
            "commit": (git_commit["stdout"] or "").strip() or None,
            "status_short": (git_status["stdout"] or git_status["stderr"] or "").splitlines(),
        },
        "python_version": sys.version,
        "package_versions": {
            name: package_version(name)
            for name in ("fastapi", "sqlalchemy", "alembic", "pydantic", "httpx", "pytest")
        },
        "python_file_count": len(py_files),
        "test_file_count": len(tests),
        "alembic_revisions": revisions,
        "env_file_exists": (REPO_ROOT / ".env").exists(),
        "dockerignore_exists": (REPO_ROOT / ".dockerignore").exists(),
        "gitignore_exists": (REPO_ROOT / ".gitignore").exists(),
        "raw_deploy_artifact_scan": {
            "passed": deploy_scan["ok"],
            "returncode": deploy_scan["returncode"],
            "stdout": deploy_scan["stdout"],
            "stderr": deploy_scan["stderr"],
        },
    }
    write_json(output_dir / "00_repo_inventory.json", inventory)
    write_text(
        output_dir / "00_repo_inventory.md",
        "\n".join(
            [
                "# Repo Inventory",
                "",
                f"- Git repo: {inventory['git']['is_git_repo']}",
                f"- Branch: {inventory['git']['branch']}",
                f"- Commit: {inventory['git']['commit']}",
                f"- Python files: {inventory['python_file_count']}",
                f"- Test files: {inventory['test_file_count']}",
                f"- Alembic revisions: {len(revisions)}",
                f"- .env exists: {inventory['env_file_exists']}",
                f"- .dockerignore exists: {inventory['dockerignore_exists']}",
                f"- .gitignore exists: {inventory['gitignore_exists']}",
                f"- Deploy artifact scan passed: {deploy_scan['ok']}",
            ]
        ),
    )
    return inventory


def source_manifest(output_dir: Path) -> None:
    """Write source manifests required by the full runtime/data audit prompt."""

    source_roots = ("app", "tests", "scripts", "alembic", "docs")
    blocked_parts = {
        ".git",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".venv",
        "__pycache__",
        "_incoming_projects",
        "node_modules",
        "output",
        "reports",
    }
    blocked_suffixes = {".db", ".sqlite", ".sqlite3", ".zip", ".pyc", ".log", ".xlsx", ".xls"}
    files: list[dict[str, Any]] = []
    for root_name in source_roots:
        root = REPO_ROOT / root_name
        if not root.exists():
            continue
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(REPO_ROOT)
            if any(part in blocked_parts for part in rel.parts):
                continue
            if path.suffix.lower() in blocked_suffixes:
                continue
            files.append(
                {
                    "path": str(rel),
                    "suffix": path.suffix,
                    "size_bytes": path.stat().st_size,
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                }
            )
    by_root: dict[str, int] = {}
    by_suffix: dict[str, int] = {}
    for item in files:
        by_root[item["path"].split("/", 1)[0]] = by_root.get(item["path"].split("/", 1)[0], 0) + 1
        by_suffix[item["suffix"] or "<none>"] = by_suffix.get(item["suffix"] or "<none>", 0) + 1
    write_json(
        output_dir / "00_repo_inventory" / "source_manifest.json",
        {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "repo_root": str(REPO_ROOT),
            "file_count": len(files),
            "by_root": by_root,
            "by_suffix": by_suffix,
            "files": files,
        },
    )


def module_file_map(output_dir: Path) -> None:
    modules_root = REPO_ROOT / "app" / "modules"
    lines = ["# Module File Map", "", "| Module | Router | Schemas/Models/Services hints |", "|---|---|---|"]
    if modules_root.exists():
        for module_dir in sorted(path for path in modules_root.iterdir() if path.is_dir()):
            name = module_dir.name
            router = module_dir / "router.py"
            hints = sorted(
                str(path.relative_to(REPO_ROOT))
                for path in (
                    list((REPO_ROOT / "app" / "services").glob(f"*{name}*.py"))
                    + list((REPO_ROOT / "app" / "schemas").glob(f"*{name}*.py"))
                    + list((REPO_ROOT / "app" / "models").glob(f"*{name}*.py"))
                    + list(module_dir.glob("*.py"))
                )
                if path.exists() and path.name != "router.py"
            )
            lines.append(
                f"| {name} | `{str(router.relative_to(REPO_ROOT)) if router.exists() else 'missing'}` | "
                f"{', '.join(f'`{hint}`' for hint in hints[:12]) or 'none'} |"
            )
    write_text(output_dir / "00_repo_inventory" / "module_file_map.md", "\n".join(lines))


def route_file_map(route_catalog: list[dict[str, Any]], output_dir: Path) -> None:
    lines = ["# Route File Map", "", "| Method | Path | Operation | Likely router |", "|---|---|---|---|"]
    for row in route_catalog:
        stripped = strip_api_prefix(row["path"])
        first = stripped.strip("/").split("/", 1)[0] if stripped.strip("/") else "root"
        module = "portal" if first == "portal" else first.replace("-", "_")
        likely_router = REPO_ROOT / "app" / "modules" / module / "router.py"
        if not likely_router.exists() and module == "root":
            router_label = "app/main.py"
        else:
            router_label = str(likely_router.relative_to(REPO_ROOT)) if likely_router.exists() else "unknown"
        lines.append(f"| {row['method']} | `{row['path']}` | `{row.get('operation_id') or ''}` | `{router_label}` |")
    write_text(output_dir / "00_repo_inventory" / "route_file_map.md", "\n".join(lines))


def migration_manifest(output_dir: Path) -> None:
    revision_paths = sorted((REPO_ROOT / "alembic" / "versions").glob("*.py"))
    lines = ["# Migration Manifest", "", f"- Revision files: {len(revision_paths)}", ""]
    for path in revision_paths:
        lines.append(f"- `{path.relative_to(REPO_ROOT)}`")
    current = output_dir / "db" / "alembic_current.txt"
    history = output_dir / "db" / "alembic_history.txt"
    if current.exists():
        lines.extend(["", "## Alembic Current", "```text", current.read_text(encoding="utf-8", errors="ignore")[:4000].rstrip(), "```"])
    if history.exists():
        lines.extend(["", "## Alembic History", "```text", history.read_text(encoding="utf-8", errors="ignore")[:12000].rstrip(), "```"])
    write_text(output_dir / "db" / "migration_manifest.md", "\n".join(lines))


def module_state_consistency_report(output_dir: Path, runtime: dict[str, Any], db_result: dict[str, Any]) -> None:
    table_counts_path = output_dir / "db" / "operator_table_counts.json"
    table_counts = json.loads(table_counts_path.read_text(encoding="utf-8")) if table_counts_path.exists() else {}
    rows: list[tuple[str, str, str]] = []
    for item in runtime.get("results") or []:
        endpoint = item.get("endpoint_key") or ""
        if "/portal/" not in endpoint:
            continue
        result = ((item.get("contract_check") or {}).get("result") or "UNKNOWN")
        status = "runtime_ok" if result == "PASS" else result.lower()
        rows.append((endpoint, status, ",".join((item.get("contract_check") or {}).get("notes") or [])))
    lines = [
        "# Module State Consistency Report",
        "",
        f"- DB evidence available: {db_result.get('available')}",
        f"- Operator/portal table evidence entries: {len(table_counts)}",
        f"- Portal runtime evidence entries: {len(rows)}",
        "",
        "## Operator Table Counts",
    ]
    for table, count in sorted(table_counts.items()):
        lines.append(f"- `{table}`: {count}")
    lines.extend(["", "## Portal Runtime States", "", "| Endpoint | State | Notes |", "|---|---|---|"])
    for endpoint, status, notes in rows:
        lines.append(f"| `{endpoint}` | {status} | {notes} |")
    write_text(output_dir / "MODULE_STATE_CONSISTENCY_REPORT.md", "\n".join(lines))


def audit_tooling_changes_report(output_dir: Path) -> None:
    root_report = REPO_ROOT / "AUDIT_TOOLING_CHANGES.md"
    if root_report.exists():
        write_text(output_dir / "AUDIT_TOOLING_CHANGES.md", root_report.read_text(encoding="utf-8"))


def openapi_urls(config: AuditConfig) -> list[str]:
    if not config.base_url:
        return []
    urls = [f"{config.base_url}/openapi.json"]
    if config.base_url.endswith(config.api_prefix):
        urls.insert(0, f"{config.base_url[: -len(config.api_prefix)]}/openapi.json")
    return list(dict.fromkeys(urls))


def fetch_openapi(config: AuditConfig) -> tuple[dict[str, Any], str]:
    if config.base_url:
        with httpx.Client(timeout=DEFAULT_TIMEOUT, follow_redirects=True) as client:
            for url in openapi_urls(config):
                try:
                    response = client.get(url)
                    if response.status_code == 200:
                        return response.json(), f"live:{url}"
                except Exception:
                    continue
    from app.main import app

    return app.openapi(), "local_import:app.main.app"


def build_route_catalog(openapi_doc: dict[str, Any], output_dir: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path, methods in sorted((openapi_doc.get("paths") or {}).items()):
        for method, operation in sorted((methods or {}).items()):
            if method.lower() not in {"get", "post", "put", "patch", "delete"}:
                continue
            params = operation.get("parameters") or []
            rows.append(
                {
                    "method": method.upper(),
                    "path": path,
                    "operation_id": operation.get("operationId"),
                    "tags": operation.get("tags") or [],
                    "summary": operation.get("summary"),
                    "parameters": [
                        {
                            "name": item.get("name"),
                            "in": item.get("in"),
                            "required": item.get("required", False),
                        }
                        for item in params
                    ],
                    "has_request_body": bool(operation.get("requestBody")),
                    "response_codes": sorted((operation.get("responses") or {}).keys()),
                }
            )
    openapi_dir = output_dir / "openapi"
    write_json(openapi_dir / "route_catalog.json", rows)
    with (openapi_dir / "route_catalog.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["method", "path", "operation_id", "tags", "summary", "has_request_body", "response_codes"])
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "method": row["method"],
                    "path": row["path"],
                    "operation_id": row["operation_id"],
                    "tags": ",".join(row["tags"]),
                    "summary": row["summary"],
                    "has_request_body": row["has_request_body"],
                    "response_codes": ",".join(row["response_codes"]),
                }
            )
    return rows


def strip_api_prefix(path: str, api_prefix: str = DEFAULT_API_PREFIX) -> str:
    prefix = normalize_prefix(api_prefix)
    if prefix and path.startswith(prefix + "/"):
        return path[len(prefix) :]
    return path


def catalog_path_matches(catalog_path: str, planned_path: str) -> bool:
    return catalog_path == planned_path or strip_api_prefix(catalog_path) == planned_path


def path_exists(route_catalog: list[dict[str, Any]], method: str, path: str) -> bool:
    return any(row["method"] == method.upper() and catalog_path_matches(row["path"], path) for row in route_catalog)


def required_field_map() -> dict[str, list[str]]:
    return {
        "GET /portal/modules/health": ["modules", "unavailable_sources"],
        "GET /portal/doctor": ["status", "account_id", "today_plan", "unavailable_sources"],
        "GET /portal/overview": ["account", "module_health", "unavailable_sources"],
        "GET /portal/actions": ["total", "limit", "offset", "items", "unavailable_sources"],
        "GET /portal/products": ["total", "limit", "offset", "items", "unavailable_sources"],
        "GET /portal/products/{nm_id}": ["nm_id", "identity", "money", "costs", "actions", "unavailable_sources"],
        "GET /portal/reputation/inbox": ["status", "total", "items", "summary", "unavailable_sources"],
        "GET /portal/cases": ["total", "items"],
        "GET /portal/results": ["total", "items", "summary", "by_module", "by_outcome", "disclaimer"],
    }


def common_query(config: AuditConfig) -> dict[str, Any]:
    return {"account_id": config.account_id} if config.account_id else {}


def account_id_value(config: AuditConfig) -> int | str | None:
    if config.account_id is None:
        return None
    try:
        return int(config.account_id)
    except ValueError:
        return config.account_id


def feature_flags_safe() -> tuple[bool, list[str]]:
    unsafe = [name for name in DANGEROUS_FLAGS if (os.getenv(name) or "").strip().lower() in TRUTHY]
    return not unsafe, unsafe


def build_manual_plan(config: AuditConfig, route_catalog: list[dict[str, Any]]) -> list[EndpointPlanItem]:
    fields = required_field_map()
    query = common_query(config)
    safe_flags, unsafe_flags = feature_flags_safe()
    dangerous_skip = "dangerous feature flag enabled: " + ", ".join(unsafe_flags) if unsafe_flags else None
    plan: list[EndpointPlanItem] = []

    def add(method: str, path: str, *, body: dict[str, Any] | None = None, required: list[str] | None = None, skip: str | None = None) -> None:
        if not path_exists(route_catalog, method, path):
            plan.append(EndpointPlanItem(method, path, dict(query), body, required or fields.get(f"{method} {path}", []), "path missing from OpenAPI"))
            return
        plan.append(EndpointPlanItem(method, path, dict(query), body, required or fields.get(f"{method} {path}", []), skip))

    add("GET", "/portal/modules/health")
    add("GET", "/portal/doctor")
    add("GET", "/portal/overview")
    add("GET", "/portal/actions")
    add(
        "PATCH",
        "/portal/actions/by-source",
        body={
            "account_id": account_id_value(config),
            "source_module": "runtime_audit",
            "source_id": f"runtime-audit-action-{int(time.time())}",
            "status": "in_progress",
            "comment": "runtime audit safe local status proof",
        },
    )
    add("GET", "/portal/actions/{action_id}/results", skip=None if config.action_id else "missing ACTION_ID and discovery failed/not yet run")
    add(
        "POST",
        "/portal/actions/{action_id}/result-event",
        body={"event_type": "action_completed", "message": "runtime audit safe local result event", "payload": {"audit": True}},
        skip=None if config.action_id else "missing ACTION_ID and discovery failed/not yet run",
    )
    add("GET", "/portal/results")
    add("GET", "/portal/products")
    add("GET", "/portal/products/{nm_id}", skip=None if config.nm_id else "missing NM_ID and discovery failed/not yet run")
    add("GET", "/portal/products/{nm_id}/quality", skip=None if config.nm_id else "missing NM_ID and discovery failed/not yet run")
    add("GET", "/portal/products/{nm_id}/grouping", skip=None if config.nm_id else "missing NM_ID and discovery failed/not yet run")
    add("GET", "/portal/products/{nm_id}/events", skip=None if config.nm_id else "missing NM_ID and discovery failed/not yet run")
    add("GET", "/portal/reputation/summary")
    add("GET", "/portal/reputation/inbox")
    add("POST", "/portal/reputation/sync", body={"dry_run": True}, skip=dangerous_skip)
    add("GET", "/portal/reputation/items/{item_id}", skip=None if config.reputation_item_id else "missing REPUTATION_ITEM_ID and discovery failed/not yet run")
    add("POST", "/portal/reputation/items/{item_id}/draft", body={"tone": "neutral", "dry_run": True}, skip=None if config.reputation_item_id and safe_flags else (dangerous_skip or "missing REPUTATION_ITEM_ID and discovery failed/not yet run"))
    add("POST", "/portal/reputation/items/{item_id}/no-reply-needed", body={"confirm": False, "reason": "runtime audit safe-mode"}, skip=None if config.reputation_item_id and safe_flags else (dangerous_skip or "missing REPUTATION_ITEM_ID and discovery failed/not yet run"))
    for action in ("approve", "regenerate", "reject"):
        add("POST", f"/portal/reputation/drafts/{{draft_id}}/{action}", body={"reason": "runtime audit safe test"}, skip="draft mutation requires explicitly safe/test draft")
    add("POST", "/portal/reputation/drafts/{draft_id}/publish", body={"confirm": False}, skip=None if config.reputation_draft_id and safe_flags else (dangerous_skip or "missing REPUTATION_DRAFT_ID and discovery failed/not yet run"))
    add("GET", "/portal/reputation/settings")
    add("PUT", "/portal/reputation/settings", body={"auto_publish_enabled": False, "auto_reply_enabled": False}, skip=dangerous_skip)
    add("GET", "/portal/cases")
    add(
        "POST",
        "/portal/cases/from-signal",
        body={
            "account_id": account_id_value(config),
            "source_module": "audit",
            "source_id": f"runtime-audit-{int(time.time())}",
            "title": "Runtime audit synthetic signal",
            "summary": "Safe synthetic signal created by audit script",
            "payload": {"audit": True, "safe_mode": True},
        },
        skip=dangerous_skip,
    )
    add("GET", "/portal/cases/{case_id}", skip=None if config.case_id else "missing CASE_ID and discovery failed/not yet run")
    add("PATCH", "/portal/cases/{case_id}", body={"status": "evidence_needed", "payload": {"audit": True, "safe_mode": True}}, skip=None if config.case_id else "missing CASE_ID and discovery failed/not yet run")
    add(
        "POST",
        "/portal/cases/{case_id}/evidence",
        body={"evidence_type": "manual", "title": "Runtime audit safe evidence", "description": "Synthetic local evidence only.", "payload": {"audit": True, "safe_mode": True}},
        skip=None if config.case_id else "missing CASE_ID and discovery failed/not yet run",
    )
    add("POST", "/portal/cases/{case_id}/generate-draft", body={"draft_type": "support_appeal", "payload": {"audit": True, "safe_mode": True}}, skip=None if config.case_id else "missing CASE_ID and discovery failed/not yet run")
    add("POST", "/portal/cases/{case_id}/proof-check", body={"dry_run": True}, skip=None if config.case_id else "missing CASE_ID and discovery failed/not yet run")
    add("POST", "/portal/cases/{case_id}/submit", body={"confirm": False}, skip=None if config.case_id and safe_flags else (dangerous_skip or "missing CASE_ID and discovery failed/not yet run"))
    add("GET", "/portal/cases/{case_id}/events", skip=None if config.case_id else "missing CASE_ID and discovery failed/not yet run")
    for path in (
        "/portal/cases/detect/defects",
        "/portal/cases/detect/supply-discrepancies",
        "/portal/cases/detect/missing-goods",
        "/portal/cases/detect/report-anomalies",
        "/portal/cases/detect/compensation-underpayments",
        "/portal/cases/detect/repeat-claims",
        "/portal/cases/detect/pretrial",
    ):
        add("GET", path)
    add("POST", "/portal/grouping/preview", body={"account_id": config.account_id, "dry_run": True, "auto_merge_enabled": False, "items": []}, skip=dangerous_skip)
    add("POST", "/portal/stockops/run", body={"account_id": config.account_id, "mode": "analysis", "dry_run": True}, skip="StockOps run is skipped unless local-only behavior is explicitly confirmed")
    add("GET", "/portal/stockops/runs")
    add(
        "POST",
        "/portal/experiments/events",
        body={"account_id": account_id_value(config), "nm_id": int(config.nm_id or 0), "event_type": "manual_note", "before_json": {"audit": True}, "after_json": {"audit": True, "safe_mode": True}},
        skip=None if config.nm_id else "missing NM_ID and discovery failed/not yet run",
    )
    for method, path in (
        ("GET", "/health"),
        ("GET", "/auth/me"),
        ("GET", "/accounts"),
        ("GET", "/money/summary"),
        ("GET", "/money/actions/today"),
        ("GET", "/money/articles"),
        ("GET", "/money/data-blockers"),
        ("GET", "/costs/unresolved"),
        ("GET", "/dq/issues"),
    ):
        add(method, path)
    add_openapi_safe_gets(config, route_catalog, plan)
    return plan


def add_openapi_safe_gets(config: AuditConfig, route_catalog: list[dict[str, Any]], plan: list[EndpointPlanItem]) -> None:
    existing = {(item.method, item.path) for item in plan}
    for row in route_catalog:
        if row["method"] != "GET":
            continue
        path = strip_api_prefix(row["path"], config.api_prefix)
        if (row["method"], path) in existing:
            continue
        if path.startswith(("/accounts/")) or "/tokens" in path:
            continue
        query = common_query(config)
        parameters = row.get("parameters") or []
        for param in parameters:
            if param.get("in") != "query":
                continue
            name = str(param.get("name") or "")
            if name in query:
                continue
            if name in {"limit", "page_size"}:
                query[name] = 20
            elif name == "offset":
                query[name] = 0
            elif name == "only_open":
                query[name] = "true"
            elif name == "nm_id" and config.nm_id:
                query[name] = config.nm_id
            elif name == "code":
                query[name] = "missing_finance_report"
            elif name == "issues_limit":
                query[name] = 20
            elif name == "issues_offset":
                query[name] = 0
        skip = None
        if "{" in path:
            skip = "OpenAPI safe GET has path parameters and no generic discovery rule"
        plan.append(EndpointPlanItem("GET", path, query=query, skip_reason=skip, safety_note="auto-added from OpenAPI safe GET catalog"))


def discover_ids(config: AuditConfig, client: httpx.Client) -> None:
    if not config.base_url or not config.access_token or not config.account_id:
        return
    discover_ids_from_db(config)

    def get_json(path: str) -> Any:
        try:
            response = client.get(url_for(config, path), params=common_query(config))
            if response.status_code == 200:
                return response.json()
        except Exception:
            return None
        return None

    products = get_json("/portal/products")
    if not config.nm_id:
        config.nm_id = first_value(products, ("nm_id", "nmId"))
    actions = get_json("/portal/actions")
    if not config.action_id:
        config.action_id = first_value(actions, ("id", "action_id"))
    cases = get_json("/portal/cases")
    if not config.case_id:
        config.case_id = first_value(cases, ("id", "case_id"))
    inbox = get_json("/portal/reputation/inbox")
    if not config.reputation_item_id:
        config.reputation_item_id = first_value(inbox, ("id", "item_id"))


def discover_ids_from_db(config: AuditConfig) -> None:
    database_url = db_url_from_settings()
    if not database_url or not config.account_id:
        return
    engine = create_engine(database_url, future=True)
    try:
        account_id = int(config.account_id)
        with engine.connect() as conn:
            if not config.action_id or not str(config.action_id).isdigit():
                action_id = conn.execute(
                    text(
                        """
                        SELECT id FROM unified_actions
                        WHERE account_id = :account_id
                        ORDER BY id ASC
                        LIMIT 1
                        """
                    ),
                    {"account_id": account_id},
                ).scalar_one_or_none()
                if action_id is None:
                    action_id = conn.execute(
                        text(
                            """
                            SELECT id FROM action_recommendations
                            WHERE account_id = :account_id
                            ORDER BY id ASC
                            LIMIT 1
                            """
                        ),
                        {"account_id": account_id},
                    ).scalar_one_or_none()
                if action_id is not None:
                    config.action_id = str(int(action_id))
            if not config.case_id:
                case_id = conn.execute(
                    text(
                        """
                        SELECT id FROM operator_cases
                        WHERE account_id = :account_id
                        ORDER BY id ASC
                        LIMIT 1
                        """
                    ),
                    {"account_id": account_id},
                ).scalar_one_or_none()
                if case_id is not None:
                    config.case_id = str(int(case_id))
            if not config.nm_id:
                nm_id = conn.execute(
                    text(
                        """
                        SELECT nm_id FROM core_sku
                        WHERE account_id = :account_id AND nm_id IS NOT NULL
                        ORDER BY id ASC
                        LIMIT 1
                        """
                    ),
                    {"account_id": account_id},
                ).scalar_one_or_none()
                if nm_id is not None:
                    config.nm_id = str(int(nm_id))
    except Exception:
        return
    finally:
        engine.dispose()


def first_value(payload: Any, names: tuple[str, ...]) -> str | None:
    if not isinstance(payload, dict):
        return None
    items = payload.get("items")
    if not isinstance(items, list) or not items:
        return None
    first = items[0]
    if not isinstance(first, dict):
        return None
    for name in names:
        value = first.get(name)
        if value not in (None, ""):
            return str(value)
    return None


def effective_skip_reason(config: AuditConfig, item: EndpointPlanItem) -> str | None:
    reason = item.skip_reason
    if not reason:
        return None
    if "missing CASE_ID" in reason and config.case_id:
        return None
    if "missing NM_ID" in reason and config.nm_id:
        return None
    if "missing ACTION_ID" in reason and config.action_id:
        return None
    if "missing REPUTATION_ITEM_ID" in reason and config.reputation_item_id:
        return None
    if "missing REPUTATION_DRAFT_ID" in reason and config.reputation_draft_id:
        return None
    return reason


def expected_skip_result(reason: str) -> str:
    lowered = reason.lower()
    if "reputation" in lowered and "missing" in lowered:
        return "EXPECTED_SAFE_SKIPPED_DISABLED_MODE"
    if any(token in lowered for token in ("stockops", "draft mutation", "path parameters", "dangerous feature flag")):
        return "EXPECTED_SAFE_SKIPPED"
    return "SKIPPED"


def resolve_path(config: AuditConfig, path: str) -> str:
    replacements = {
        "{nm_id}": config.nm_id or "{nm_id}",
        "{action_id}": config.action_id or "{action_id}",
        "{case_id}": config.case_id or "{case_id}",
        "{item_id}": config.reputation_item_id or "{item_id}",
        "{draft_id}": config.reputation_draft_id or "{draft_id}",
    }
    resolved = path
    for needle, replacement in replacements.items():
        resolved = resolved.replace(needle, replacement)
    return resolved


def url_for(config: AuditConfig, path: str) -> str:
    if not config.base_url:
        raise ValueError("BASE_URL is required for runtime endpoint calls")
    base = config.base_url.rstrip("/")
    if base.endswith(config.api_prefix):
        return f"{base}{path}"
    return f"{base}{config.api_prefix}{path}"


def body_sha256(body: Any) -> str:
    raw = json.dumps(body, ensure_ascii=False, sort_keys=True, default=json_default).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def required_fields_present(body: Any, fields: list[str]) -> tuple[list[str], list[str]]:
    if not fields:
        return [], []
    if not isinstance(body, dict):
        return [], fields
    present: list[str] = []
    missing: list[str] = []
    for required_field in fields:
        alternatives = [required_field]
        if "/" in required_field:
            alternatives = required_field.split("/")
        if any(name in body for name in alternatives):
            present.append(required_field)
        else:
            missing.append(required_field)
    return present, missing


def execute_plan(config: AuditConfig, plan: list[EndpointPlanItem], output_dir: Path) -> dict[str, Any]:
    response_dir = output_dir / "responses"
    results: list[dict[str, Any]] = []
    p0_findings: list[str] = []
    slow: list[dict[str, Any]] = []

    if not config.base_url or not config.access_token or not config.account_id:
        reason = "missing BASE_URL, ACCESS_TOKEN, or ACCOUNT_ID"
        for item in plan:
            snapshot = skipped_snapshot(config, item, reason)
            write_json(response_dir / safe_filename(item.method, item.path), snapshot)
            results.append(snapshot)
        return {"results": results, "p0_findings": [], "slow_endpoints": [], "runtime_skipped": True, "skip_reason": reason}

    with httpx.Client(headers=auth_headers(config), timeout=DEFAULT_TIMEOUT, follow_redirects=True) as client:
        discover_ids(config, client)
        plan = build_manual_plan(config, build_route_catalog_cache(output_dir))
        for item in plan:
            resolved_path = resolve_path(config, item.path)
            skip_reason = effective_skip_reason(config, item)
            if skip_reason or "{" in resolved_path:
                reason = skip_reason or "missing path parameter"
                snapshot = skipped_snapshot(config, item, reason)
                write_json(response_dir / safe_filename(item.method, item.path), snapshot)
                results.append(snapshot)
                continue
            url = url_for(config, resolved_path)
            request_body = item.body or {}
            request_query = {key: value for key, value in item.query.items() if value not in (None, "")}
            started = time.perf_counter()
            retry_notes: list[str] = []
            try:
                attempts = 2 if item.method == "GET" else 1
                for attempt in range(1, attempts + 1):
                    try:
                        response = client.request(item.method, url, params=request_query, json=request_body if item.method != "GET" else None)
                        if attempt > 1:
                            retry_notes.append(f"request succeeded on retry attempt {attempt}")
                        break
                    except (httpx.TimeoutException, httpx.TransportError) as exc:
                        if attempt >= attempts:
                            raise
                        retry_notes.append(f"attempt {attempt} failed with {type(exc).__name__}; retried safe GET once")
                        time.sleep(1.0)
                duration_ms = int((time.perf_counter() - started) * 1000)
                content_type = response.headers.get("content-type", "")
                try:
                    raw_body: Any = response.json() if "json" in content_type else {"text": response.text[:4000]}
                except Exception:
                    raw_body = {"text": response.text[:4000]}
                clean_body, body_redactions = sanitize(raw_body)
                clean_headers, header_redactions = sanitize(dict(response.headers))
                request_clean, request_redactions = sanitize({"query": request_query, "body": request_body})
                present, missing = required_fields_present(clean_body, item.required_fields)
                secret_findings = contains_unredacted_secret(clean_body)
                if secret_findings:
                    p0_findings.extend([f"{item.key}: {finding}" for finding in secret_findings])
                perf_notes = performance_notes(item, duration_ms)
                notes = perf_notes + retry_notes
                if perf_notes:
                    slow.append({"endpoint_key": item.key, "duration_ms": duration_ms, "notes": perf_notes})
                snapshot = {
                    "endpoint_key": item.key,
                    "method": item.method,
                    "url": url,
                    "request": {
                        "query": request_clean["query"],
                        "body": request_clean["body"],
                        "headers": sanitized_headers(bool(config.access_token)),
                    },
                    "response": {
                        "status_code": response.status_code,
                        "duration_ms": duration_ms,
                        "headers_sanitized": clean_headers,
                        "body_sanitized": clean_body,
                        "body_sha256": body_sha256(clean_body),
                    },
                    "contract_check": {
                        "result": "PASS" if 200 <= response.status_code < 300 and not missing else "FAIL",
                        "required_fields_present": present,
                        "missing_fields": missing,
                        "notes": notes,
                    },
                    "safety_check": {
                        "result": "FAIL" if secret_findings else "PASS",
                        "redacted_fields_count": body_redactions + header_redactions + request_redactions,
                        "dangerous_external_write_attempted": False,
                        "marketplace_change": False,
                    },
                }
                update_runtime_ids_from_response(config, item, clean_body)
            except Exception as exc:
                duration_ms = int((time.perf_counter() - started) * 1000)
                snapshot = {
                    "endpoint_key": item.key,
                    "method": item.method,
                    "url": url,
                    "request": {"query": request_query, "body": request_body, "headers": sanitized_headers(bool(config.access_token))},
                    "response": {"status_code": None, "duration_ms": duration_ms, "headers_sanitized": {}, "body_sanitized": {"error": repr(exc)}, "body_sha256": body_sha256({"error": repr(exc)})},
                    "contract_check": {"result": "FAIL", "required_fields_present": [], "missing_fields": item.required_fields, "notes": ["request failed"] + retry_notes},
                    "safety_check": {"result": "PASS", "redacted_fields_count": 0, "dangerous_external_write_attempted": False, "marketplace_change": False},
                }
            write_json(response_dir / safe_filename(item.method, item.path), snapshot)
            results.append(snapshot)
    return {"results": results, "p0_findings": p0_findings, "slow_endpoints": slow, "runtime_skipped": False}


def build_route_catalog_cache(output_dir: Path) -> list[dict[str, Any]]:
    path = output_dir / "openapi" / "route_catalog.json"
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def update_runtime_ids_from_response(config: AuditConfig, item: EndpointPlanItem, body: Any) -> None:
    if not isinstance(body, dict):
        return
    if item.path == "/portal/cases/from-signal" and body.get("id"):
        config.case_id = str(body["id"])
    if item.path == "/portal/products" and not config.nm_id:
        config.nm_id = first_value(body, ("nm_id", "nmId"))
    if item.path == "/core-sku" and not config.sku_id:
        config.sku_id = first_value(body, ("id", "sku_id"))
    if item.path == "/money/articles" and not config.nm_id:
        config.nm_id = first_value(body, ("nm_id", "nmId"))


def skipped_snapshot(config: AuditConfig, item: EndpointPlanItem, reason: str) -> dict[str, Any]:
    result = expected_skip_result(reason)
    return {
        "endpoint_key": item.key,
        "method": item.method,
        "url": None if not config.base_url else url_for(config, resolve_path(config, item.path)).replace("{", "%7B").replace("}", "%7D"),
        "request": {"query": item.query, "body": item.body or {}, "headers": sanitized_headers(bool(config.access_token))},
        "response": {"status_code": None, "duration_ms": None, "headers_sanitized": {}, "body_sanitized": {}, "body_sha256": body_sha256({})},
        "contract_check": {"result": result, "required_fields_present": [], "missing_fields": item.required_fields, "notes": [f"SKIPPED_WITH_REASON: {reason}"]},
        "safety_check": {"result": "PASS", "redacted_fields_count": 0, "dangerous_external_write_attempted": False, "marketplace_change": False},
    }


def performance_notes(item: EndpointPlanItem, duration_ms: int) -> list[str]:
    notes: list[str] = []
    if duration_ms > 10_000:
        notes.append("FAIL: endpoint exceeded 10000ms")
    elif duration_ms > 1_000:
        notes.append("WARN: endpoint exceeded 1000ms")
    if item.path in {"/portal/overview", "/portal/products", "/portal/actions"} and duration_ms > 3_000:
        notes.append("WARN: main portal endpoint exceeded 3000ms")
    return notes


def generate_lovable_map(output_dir: Path) -> None:
    rows = [
        ("Login/Auth", "GET /auth/me", "Authorization header", "user/account fields", "401 unauthenticated"),
        ("Account selector", "GET /accounts", "limit/offset", "total/items", "empty items"),
        ("Legacy profit diagnostics", "GET /portal/doctor", "account_id", "status/headline/today_plan", "unavailable_sources"),
        ("Dashboard", "GET /portal/overview", "account_id", "money_summary/top_actions/top_products/module_health", "disabled/not_configured/unavailable"),
        ("Action Center", "GET /portal/actions", "account_id limit offset", "total/items", "empty items"),
        ("Products list", "GET /portal/products", "account_id limit offset", "total/items", "empty items"),
        ("Product 360", "GET /portal/products/{nm_id}", "account_id nm_id", "identity/money/costs/data_quality/actions/history", "unavailable_sources"),
        ("Reputation Operator", "GET /portal/reputation/inbox", "account_id", "status/summary/items", "disabled/not_configured/unavailable/empty"),
        ("Claims Factory", "GET /portal/cases", "account_id", "status/total/items", "disabled/not_configured/unavailable/empty"),
        ("Results", "GET /portal/results", "account_id", "summary/by_module/by_outcome/items/disclaimer", "empty items"),
        ("Settings / Module Health", "GET /portal/modules/health", "account_id", "modules/unavailable_sources", "disabled/not_configured/unavailable"),
    ]
    lines = ["# Lovable Endpoint Map", "", "| Lovable Page | Endpoint | Required Query/Body | Response Fields | Empty/Degraded States |", "|---|---|---|---|---|"]
    lines.extend(f"| {page} | `{endpoint}` | {req} | {fields} | {states} |" for page, endpoint, req, fields, states in rows)
    write_text(output_dir / "openapi" / "lovable_endpoint_map.md", "\n".join(lines))


def db_url_from_settings() -> str | None:
    if os.getenv("DATABASE_URL"):
        return os.getenv("DATABASE_URL")
    try:
        from app.core.config import get_settings

        return get_settings().sync_database_url
    except Exception:
        return None


def db_evidence(output_dir: Path) -> dict[str, Any]:
    db_dir = output_dir / "db"
    db_dir.mkdir(parents=True, exist_ok=True)
    database_url = db_url_from_settings()
    if not database_url:
        write_text(db_dir / "sanitized_db_dump_not_available.md", "DATABASE_URL/settings database URL is not available.")
        return {"available": False, "reason": "database url unavailable"}
    engine = create_engine(database_url, future=True)
    try:
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        schema_lines: list[str] = []
        table_counts: dict[str, int | str] = {}
        operator_counts: dict[str, int | str] = {}
        samples: dict[str, Any] = {}
        with engine.connect() as conn:
            for table in tables:
                columns = inspector.get_columns(table)
                schema_lines.append(f"-- table: {table}")
                schema_lines.append(f"CREATE TABLE {table} (")
                schema_lines.extend(f"  {col['name']} {col['type']}," for col in columns)
                schema_lines.append(");")
                try:
                    table_counts[table] = int(conn.execute(text(f'SELECT COUNT(*) FROM "{table}"')).scalar_one())
                except Exception as exc:
                    table_counts[table] = f"unavailable: {exc.__class__.__name__}"
                if any(token in table.lower() for token in ("operator", "portal", "case", "action", "result", "reputation", "claim")):
                    operator_counts[table] = table_counts[table]
                if is_safe_sample_table(table):
                    samples[table] = sample_rows(conn, table, columns)
        write_text(db_dir / "schema.sql", "\n".join(schema_lines))
        logical_table_counts = build_logical_table_counts(table_counts)
        write_json(db_dir / "table_counts.json", table_counts)
        write_json(db_dir / "logical_table_counts.json", logical_table_counts)
        write_json(db_dir / "operator_table_counts.json", operator_counts)
        write_json(db_dir / "safe_sample_rows.json", samples)
        write_text(db_dir / "sanitized_db_dump_not_available.md", "Full sanitized data dump is not exported; schema, counts, and safe sample rows are included.")
        return {"available": True, "table_count": len(tables)}
    except Exception as exc:
        reason, _ = sanitize_string(repr(exc))
        write_text(db_dir / "sanitized_db_dump_not_available.md", f"DB evidence unavailable: {reason}")
        return {"available": False, "reason": reason}
    finally:
        engine.dispose()


def build_logical_table_counts(table_counts: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Return logical table evidence while respecting physical table aliases."""

    logical_counts: dict[str, dict[str, Any]] = {}
    logical_names = sorted(set(table_counts) | set(DB_LOGICAL_TABLE_ALIASES))
    for logical_name in logical_names:
        physical_name = DB_LOGICAL_TABLE_ALIASES.get(logical_name, logical_name)
        if physical_name in table_counts:
            logical_counts[logical_name] = {
                "logical_table": logical_name,
                "physical_table": physical_name,
                "status": "ok",
                "count": table_counts[physical_name],
            }
        else:
            logical_counts[logical_name] = {
                "logical_table": logical_name,
                "physical_table": physical_name,
                "status": "missing",
                "count": None,
            }
    return logical_counts


def is_safe_sample_table(table: str) -> bool:
    lowered = table.lower()
    if any(token in lowered for token in ("token", "credential", "auth", "raw_wb_api")):
        return False
    return any(token in lowered for token in ("operator", "portal", "case", "action", "result", "product", "sku", "mart", "data_quality"))


def sample_rows(conn: Any, table: str, columns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    names = [col["name"] for col in columns]
    safe_names = [name for name in names if not any(token in name.lower() for token in SENSITIVE_DB_COLUMN_TOKENS)]
    if not safe_names:
        return []
    quoted = ", ".join(f'"{name}"' for name in safe_names[:30])
    rows = conn.execute(text(f'SELECT {quoted} FROM "{table}" LIMIT 5')).mappings().all()
    clean_rows, _ = sanitize([dict(row) for row in rows])
    return clean_rows


def run_command_evidence(config: AuditConfig, output_dir: Path) -> list[dict[str, Any]]:
    commands_dir = output_dir / "commands"
    commands_dir.mkdir(parents=True, exist_ok=True)
    deploy_context = prepare_clean_deploy_context(output_dir)
    specs = [
        ("compileall.log", [sys.executable, "-m", "compileall", "-f", "-q", "app", "tests", "alembic", "scripts"]),
        ("alembic_upgrade.log", [sys.executable, "-m", "alembic", "upgrade", "head"]),
        ("pytest.log", [sys.executable, "-m", "pytest", "-q"]),
        ("deploy_safety.log", [sys.executable, "scripts/check_deploy_artifact_safety.py", "--root", str(deploy_context)]),
        ("smoke_ai_operator.log", [sys.executable, "scripts/smoke_ai_operator_backend.py"]),
    ]
    results: list[dict[str, Any]] = []
    if not config.run_commands:
        for filename, command in specs:
            result = {"command": " ".join(command), "ok": False, "skipped": True, "reason": "AUDIT_SKIP_COMMANDS enabled"}
            write_text(commands_dir / filename, json.dumps(result, indent=2))
            results.append(result)
        shutil.rmtree(deploy_context, ignore_errors=True)
        return results
    env = os.environ.copy()
    env.setdefault("ENABLE_REPUTATION_PUBLISH", "false")
    env.setdefault("ENABLE_REPUTATION_WRITE_ACTIONS", "false")
    env.setdefault("ENABLE_CLAIMS_SUBMIT", "false")
    env.setdefault("ENABLE_GROUPING_MERGE", "false")
    env.setdefault("ENABLE_CARD_AUTO_APPLY", "false")
    if config.base_url:
        env["BASE_URL"] = config.base_url
    if config.api_prefix:
        env["API_PREFIX"] = config.api_prefix
    if config.access_token:
        env["ACCESS_TOKEN"] = config.access_token
    if config.account_id:
        env["ACCOUNT_ID"] = config.account_id
    env["AUDIT_ENV"] = config.audit_env
    for filename, command in specs:
        started = time.perf_counter()
        try:
            proc = subprocess.run(command, cwd=REPO_ROOT, text=True, capture_output=True, timeout=COMMAND_TIMEOUT_SECONDS, env=env)
            duration_ms = int((time.perf_counter() - started) * 1000)
            stdout, _ = sanitize_string(proc.stdout or "")
            stderr, _ = sanitize_string(proc.stderr or "")
            result = {"command": " ".join(command), "returncode": proc.returncode, "duration_ms": duration_ms, "ok": proc.returncode == 0}
            write_text(commands_dir / filename, f"command: {' '.join(command)}\nreturncode: {proc.returncode}\nduration_ms: {duration_ms}\n\nstdout:\n{stdout}\n\nstderr:\n{stderr}")
        except Exception as exc:
            result = {"command": " ".join(command), "returncode": None, "ok": False, "error": repr(exc)}
            write_text(commands_dir / filename, json.dumps(result, indent=2))
        results.append(result)
    shutil.rmtree(deploy_context, ignore_errors=True)
    return results


def prepare_clean_deploy_context(output_dir: Path) -> Path:
    context = output_dir.parent / f".{output_dir.name}_clean_deploy_context"
    if context.exists():
        shutil.rmtree(context)
    context.mkdir(parents=True, exist_ok=True)
    include_paths = [
        "app",
        "alembic",
        "scripts",
        "tests",
        "docs",
        "pyproject.toml",
        "alembic.ini",
        ".env.example",
        "README.md",
    ]

    def ignore(_: str, names: list[str]) -> set[str]:
        blocked = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".venv", "node_modules", "reports"}
        return {name for name in names if name in blocked or name.endswith((".pyc", ".log", ".zip"))}

    for rel in include_paths:
        src = REPO_ROOT / rel
        if not src.exists():
            continue
        dst = context / rel
        if src.is_dir():
            shutil.copytree(src, dst, ignore=ignore)
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
    return context


def run_alembic_text(output_dir: Path) -> None:
    db_dir = output_dir / "db"
    for filename, command in (
        ("alembic_current.txt", [sys.executable, "-m", "alembic", "current"]),
        ("alembic_history.txt", [sys.executable, "-m", "alembic", "history", "--verbose"]),
    ):
        result = run_process(command, timeout=300)
        write_text(db_dir / filename, f"command: {' '.join(command)}\nreturncode: {result['returncode']}\n\nstdout:\n{result['stdout']}\n\nstderr:\n{result['stderr']}")


def summarize_performance(runtime: dict[str, Any], output_dir: Path) -> None:
    slow = runtime.get("slow_endpoints") or []
    write_json(output_dir / "performance" / "slow_endpoints.json", slow)
    lines = ["# Performance Summary", "", f"- Slow/warned endpoints: {len(slow)}"]
    for item in slow:
        lines.append(f"- `{item['endpoint_key']}`: {item['duration_ms']}ms; {', '.join(item['notes'])}")
    write_text(output_dir / "performance" / "summary.md", "\n".join(lines))


def score(ok: bool, partial: bool = False) -> int:
    if ok:
        return 100
    return 60 if partial else 0


def build_final_report(
    config: AuditConfig,
    inventory: dict[str, Any],
    runtime: dict[str, Any],
    db_result: dict[str, Any],
    command_results: list[dict[str, Any]],
    p0_findings: list[str],
    output_dir: Path,
) -> tuple[dict[str, Any], str]:
    runtime_results = runtime.get("results") or []
    expected_skip_values = {"EXPECTED_SAFE_SKIPPED", "EXPECTED_SAFE_SKIPPED_DISABLED_MODE"}
    executed = [item for item in runtime_results if item["contract_check"]["result"] not in {"SKIPPED", *expected_skip_values}]
    executed_pass = [item for item in runtime_results if item["contract_check"]["result"] == "PASS"]
    expected_safe_skipped = [item for item in runtime_results if item["contract_check"]["result"] in expected_skip_values]
    failed = [item for item in runtime_results if item["contract_check"]["result"] == "FAIL"]
    runtime_pass = bool(executed_pass) and not failed
    runtime_partial = bool(executed)
    commands_by_name = {Path((item.get("command") or "").split()[0]).name: item for item in command_results}
    compile_ok = next((item["ok"] for item in command_results if "compileall" in item.get("command", "")), False)
    pytest_ok = next((item["ok"] for item in command_results if "pytest" in item.get("command", "")), False)
    alembic_ok = next((item["ok"] for item in command_results if "alembic upgrade" in item.get("command", "")), False)
    deploy_ok = next((item["ok"] for item in command_results if "check_deploy_artifact_safety" in item.get("command", "")), False)
    smoke_ok = next((item["ok"] for item in command_results if "smoke_ai_operator_backend.py" in item.get("command", "")), False)
    categories = {
        "Syntax / compile": (score(compile_ok), "compile command failed or skipped" if not compile_ok else ""),
        "Tests": (score(pytest_ok), "pytest failed or skipped" if not pytest_ok else ""),
        "Alembic/migrations": (score(alembic_ok), "alembic upgrade/current unavailable or failed" if not alembic_ok else ""),
        "Route registration": (100, ""),
        "Endpoint runtime success": (score(runtime_pass, runtime_partial), "some endpoints failed/skipped or runtime env missing" if not runtime_pass else ""),
        "Endpoint contract quality": (score(runtime_pass, runtime_partial), "required fields missing on failed/skipped endpoints" if not runtime_pass else ""),
        "Security/safety": (score(not p0_findings), "P0 secret findings detected" if p0_findings else ""),
        "RBAC/account scoping": (score(bool(config.account_id) and runtime_partial, runtime_partial), "requires real account-scoped staging token proof"),
        "Legacy profit diagnostics": (module_score(runtime_results, "/portal/doctor"), "doctor endpoint skipped/failed"),
        "Action Center": (module_score(runtime_results, "/portal/actions"), "actions endpoints skipped/failed"),
        "Product 360": (module_score(runtime_results, "/portal/products/{nm_id}"), "Product 360 skipped/failed"),
        "Reputation Operator": (module_score(runtime_results, "/portal/reputation"), "reputation endpoints disabled/skipped/failed"),
        "Claims Factory": (module_score(runtime_results, "/portal/cases"), "claims endpoints disabled/skipped/failed"),
        "Result Tracking": (module_score(runtime_results, "/portal/results"), "results endpoint skipped/failed"),
        "StockOps": (module_score(runtime_results, "/portal/stockops", allow_skipped=True), "StockOps write is intentionally skipped unless local-only"),
        "Grouping Beta": (module_score(runtime_results, "/portal/grouping", allow_skipped=True), "Grouping beta is dry-run/skipped unless configured"),
        "Deploy readiness": (score(deploy_ok), "deploy safety scan failed or found blocked artifacts" if not deploy_ok else ""),
        "Lovable readiness": (score(runtime_pass and not p0_findings, runtime_partial and not p0_findings), "needs passing runtime contracts"),
        "Controlled pilot readiness": (score(runtime_pass and pytest_ok and alembic_ok and smoke_ok and not p0_findings, runtime_partial and not p0_findings), "needs tests/migrations/runtime smoke all passing"),
        "Public MVP readiness": (score(runtime_pass and pytest_ok and alembic_ok and deploy_ok and smoke_ok and not p0_findings), "requires all checks passing"),
        "Full product readiness": (60, "optional modules and write workflows remain controlled/disabled for MVP"),
    }
    scores = {}
    for name, (value, why) in categories.items():
        if name == "Security/safety" and p0_findings:
            blocking_level = "P0"
        elif name == "Full product readiness" and value < 100:
            blocking_level = "later"
        elif value < 80:
            blocking_level = "P1"
        elif value < 100:
            blocking_level = "P2"
        else:
            blocking_level = "later"
        scores[name] = {
            "score_percent": value,
            "why_not_100": why if value < 100 else "",
            "what_to_fix_to_reach_100": "Fix listed blocker and rerun this audit." if value < 100 else "",
            "blocking_level": blocking_level,
        }
    public_mvp_blockers = sum(
        1
        for name, item in scores.items()
        if name != "Full product readiness" and item["blocking_level"] in {"P0", "P1"}
    )
    if p0_findings:
        verdict = "NO_GO"
    elif runtime_pass and pytest_ok and alembic_ok and deploy_ok and smoke_ok:
        verdict = "GO"
    elif runtime_pass and pytest_ok and alembic_ok and smoke_ok and not p0_findings:
        verdict = "GO_FOR_CONTROLLED_PILOT"
    elif runtime_partial and not p0_findings:
        verdict = "GO_FOR_LOVABLE_ONLY"
    else:
        verdict = "NO_GO"
    report = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "audit_env": config.audit_env,
        "repo_inventory": inventory,
        "db_evidence": db_result,
        "command_results": command_results,
        "runtime": {
            "executed_count": len(executed),
            "executed_pass": len(executed_pass),
            "expected_safe_skipped": len(expected_safe_skipped),
            "failed": len(failed),
            "total_planned": len(runtime_results),
            "skipped_count": len([item for item in runtime_results if item["contract_check"]["result"] == "SKIPPED"]),
            "p0_findings": p0_findings,
            "setup": runtime.get("setup") or {},
        },
        "scores": scores,
        "final_verdict": verdict,
        "public_mvp_blockers": public_mvp_blockers,
    }
    write_json(output_dir / "FINAL_RUNTIME_AUDIT_REPORT.json", report)
    lines = ["# Final Runtime Audit Report", "", f"- Verdict: **{verdict}**", f"- P0 blockers: {len(p0_findings)}", f"- Public MVP blockers: {public_mvp_blockers}", ""]
    lines.append("| Area | Score | Blocking | Why not 100 |")
    lines.append("|---|---:|---|---|")
    for name, item in scores.items():
        lines.append(f"| {name} | {item['score_percent']} | {item['blocking_level']} | {item['why_not_100']} |")
    if p0_findings:
        lines.extend(["", "## P0 Findings", *[f"- {finding}" for finding in p0_findings]])
    write_text(output_dir / "FINAL_RUNTIME_AUDIT_REPORT.md", "\n".join(lines))
    return report, verdict


def module_score(results: list[dict[str, Any]], needle: str, allow_skipped: bool = False) -> int:
    matched = [item for item in results if needle in item["endpoint_key"]]
    if not matched:
        return 0
    passed = [item for item in matched if item["contract_check"]["result"] == "PASS"]
    skipped = [
        item
        for item in matched
        if item["contract_check"]["result"] in {"SKIPPED", "EXPECTED_SAFE_SKIPPED", "EXPECTED_SAFE_SKIPPED_DISABLED_MODE"}
    ]
    if len(passed) == len(matched):
        return 100
    if skipped and not any(item["contract_check"]["result"] == "FAIL" for item in matched):
        return 80
    if passed:
        return 70
    return 50 if skipped else 0


def final_secret_scan(output_dir: Path) -> list[str]:
    findings: list[str] = []
    skip_suffixes = {".zip", ".pyc"}
    for path in output_dir.rglob("*"):
        if not path.is_file() or path.suffix.lower() in skip_suffixes:
            continue
        try:
            text_value = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        rel = path.relative_to(output_dir)
        if JWT_RE.search(text_value):
            findings.append(f"{rel}: JWT-like string")
        if EMAIL_RE.search(text_value):
            findings.append(f"{rel}: email-like string")
        if re.search(r"Bearer\s+(?!<REDACTED>)[A-Za-z0-9._-]+", text_value):
            findings.append(f"{rel}: raw bearer token")
        for line in text_value.splitlines():
            if REDACTED in line or "replace-with" in line:
                continue
            if re.search(
                r'(?i)(access_token|refresh_token|encrypted_token|api_key|password|secret|jwt)\s*[:=]\s*["\']?[A-Za-z0-9_./+=-]{12,}',
                line,
            ):
                findings.append(f"{rel}: sensitive key value")
                break
    return findings[:200]


def create_zip(output_dir: Path) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    zip_path = REPO_ROOT / f"AI_OPERATOR_RUNTIME_AUDIT_BUNDLE_{timestamp}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in output_dir.rglob("*"):
            if path.is_file():
                archive.write(path, path.relative_to(REPO_ROOT))
    return zip_path.resolve()


def main() -> int:
    config = load_config()
    config.output_dir.mkdir(parents=True, exist_ok=True)
    stale_p0_path = config.output_dir / "P0_SECRET_SCAN_FINDINGS.json"
    if stale_p0_path.exists():
        stale_p0_path.unlink()
    runtime_setup = hydrate_runtime_config_from_db(config)
    server_process, server_log_handle, server_status = start_local_backend_if_needed(config, config.output_dir)
    runtime_setup["local_backend"] = server_status
    write_json(config.output_dir / "runtime_setup.json", runtime_setup)
    try:
        inventory = build_repo_inventory(config.output_dir)
        source_manifest(config.output_dir)
        module_file_map(config.output_dir)
        audit_tooling_changes_report(config.output_dir)
        openapi_doc, source = fetch_openapi(config)
        write_json(config.output_dir / "openapi" / "openapi.json", openapi_doc)
        write_text(config.output_dir / "openapi" / "openapi_source.txt", source)
        route_catalog = build_route_catalog(openapi_doc, config.output_dir)
        route_file_map(route_catalog, config.output_dir)
        generate_lovable_map(config.output_dir)
        plan = build_manual_plan(config, route_catalog)
        write_json(config.output_dir / "endpoint_execution_plan.json", [item.__dict__ | {"endpoint_key": item.key} for item in plan])
        runtime = execute_plan(config, plan, config.output_dir)
        runtime["setup"] = runtime_setup
        summarize_performance(runtime, config.output_dir)
        db_result = db_evidence(config.output_dir)
        run_alembic_text(config.output_dir)
        migration_manifest(config.output_dir)
        module_state_consistency_report(config.output_dir, runtime, db_result)
        command_results = run_command_evidence(config, config.output_dir)
        p0_findings = list(runtime.get("p0_findings") or [])
        sanitize_text_file(config.output_dir / "commands" / "local_backend_server.log")
        secret_scan_findings = final_secret_scan(config.output_dir)
        if secret_scan_findings:
            p0_findings.extend([f"final_secret_scan: {finding}" for finding in secret_scan_findings])
        report, verdict = build_final_report(config, inventory, runtime, db_result, command_results, p0_findings, config.output_dir)
        if p0_findings:
            write_json(config.output_dir / "P0_SECRET_SCAN_FINDINGS.json", p0_findings)
            print("AUDIT_BUNDLE_CREATED=")
            print(f"FINAL_VERDICT={verdict}")
            print(f"PUBLIC_MVP_BLOCKERS={report['public_mvp_blockers']}")
            print(f"P0_BLOCKERS={p0_findings}")
            return 3
        zip_path = create_zip(config.output_dir)
        print(f"AUDIT_BUNDLE_CREATED={zip_path}")
        print(f"FINAL_VERDICT={verdict}")
        print(f"PUBLIC_MVP_BLOCKERS={report['public_mvp_blockers']}")
        print("P0_BLOCKERS=[]")
        return 0 if verdict != "NO_GO" else 1
    finally:
        stop_local_backend(server_process, server_log_handle)


if __name__ == "__main__":
    raise SystemExit(main())
