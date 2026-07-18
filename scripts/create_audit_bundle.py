from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import zipfile
from datetime import date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATE_FROM = "2026-06-03"
DEFAULT_DATE_TO = "2026-07-03"
DEFAULT_ACCOUNT_ID = 1

EXCLUDED_DIRS = {
    ".git",
    ".venv",
    "node_modules",
    "dist",
    "build",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".cache",
    "audit_bundles",
}
EXCLUDED_NAMES = {
    ".env",
    ".coverage",
}
EXCLUDED_SUFFIXES = {
    ".pyc",
    ".pyo",
    ".log",
}
SECRET_KEY_RE = re.compile(r"(SECRET|TOKEN|PASSWORD|KEY|API_KEY|DATABASE_URL|DSN|AUTH)", re.IGNORECASE)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def should_exclude(path: Path) -> bool:
    parts = set(path.parts)
    if parts & EXCLUDED_DIRS:
        return True
    if path.name in EXCLUDED_NAMES:
        return True
    if path.suffix in EXCLUDED_SUFFIXES:
        return True
    if path.name.endswith(".db") and ".mypy_cache" in parts:
        return True
    return False


def zip_tree(src: Path, dest_zip: Path) -> dict[str, Any]:
    files_count = 0
    bytes_count = 0
    dest_zip.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(dest_zip, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for path in sorted(src.rglob("*")):
            rel = path.relative_to(src)
            if should_exclude(rel) or should_exclude(path):
                continue
            if path.is_dir():
                continue
            zf.write(path, arcname=str(rel))
            files_count += 1
            bytes_count += path.stat().st_size
    return {"path": str(dest_zip), "files": files_count, "source_bytes": bytes_count, "zip_bytes": dest_zip.stat().st_size}


def redact_env_file(src: Path, dest: Path) -> None:
    if not src.exists():
        return
    lines: list[str] = []
    for line in src.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            lines.append(line)
            continue
        key, value = line.split("=", 1)
        if SECRET_KEY_RE.search(key):
            lines.append(f"{key}=<REDACTED length={len(value)} sha256={hashlib.sha256(value.encode()).hexdigest()[:12]}>")
        else:
            lines.append(line)
    write_text(dest, "\n".join(lines) + "\n")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def redacted_database_url(database_url: str) -> str:
    parsed = urlparse(database_url.replace("postgresql+asyncpg://", "postgresql://", 1))
    netloc = parsed.netloc
    if "@" in netloc:
        auth, host = netloc.rsplit("@", 1)
        if ":" in auth:
            user, password = auth.split(":", 1)
            auth = f"{user}:<REDACTED length={len(password)}>"
        netloc = f"{auth}@{host}"
    return urlunparse(parsed._replace(netloc=netloc))


def pg_url_for_cli(database_url: str) -> str:
    return database_url.replace("postgresql+asyncpg://", "postgresql://", 1)


def dump_database(bundle_dir: Path, database_url: str) -> dict[str, Any]:
    db_dir = bundle_dir / "database"
    db_dir.mkdir(parents=True, exist_ok=True)
    plain_path = db_dir / "full_database.sql"
    custom_path = db_dir / "full_database.dump"
    cli_url = pg_url_for_cli(database_url)
    result: dict[str, Any] = {
        "database_url_redacted": redacted_database_url(database_url),
        "plain_sql": str(plain_path),
        "custom_dump": str(custom_path),
        "ok": False,
    }
    commands = [
        ["pg_dump", "--no-owner", "--no-privileges", "--format=plain", "--file", str(plain_path), cli_url],
        ["pg_dump", "--no-owner", "--no-privileges", "--format=custom", "--file", str(custom_path), cli_url],
    ]
    errors: list[str] = []
    for cmd in commands:
        proc = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, timeout=600)
        if proc.returncode != 0:
            errors.append(proc.stderr.strip() or proc.stdout.strip() or f"failed: {' '.join(cmd[:2])}")
    if errors:
        result["errors"] = errors
    result["ok"] = plain_path.exists() and custom_path.exists()
    if plain_path.exists():
        result["plain_sql_bytes"] = plain_path.stat().st_size
        result["plain_sql_sha256"] = sha256_file(plain_path)
    if custom_path.exists():
        result["custom_dump_bytes"] = custom_path.stat().st_size
        result["custom_dump_sha256"] = sha256_file(custom_path)
    return result


def schema_type(param: dict[str, Any]) -> str:
    schema = param.get("schema") or {}
    if "$ref" in schema:
        return "string"
    if "type" in schema:
        return str(schema["type"])
    if "anyOf" in schema:
        for item in schema["anyOf"]:
            if item.get("type") != "null":
                return str(item.get("type") or "string")
    return "string"


def sample_value_for_param(name: str, param: dict[str, Any]) -> Any:
    lower = name.lower()
    schema = param.get("schema") or {}
    enum = schema.get("enum")
    if enum:
        return enum[0]
    if lower in {"account_id", "accountid"}:
        return DEFAULT_ACCOUNT_ID
    if lower in {"date_from", "from", "start_date"}:
        return DEFAULT_DATE_FROM
    if lower in {"date_to", "to", "end_date"}:
        return DEFAULT_DATE_TO
    if lower == "limit":
        return 5
    if lower == "offset":
        return 0
    if lower == "only_open":
        return "true"
    if lower == "financial_final_blocker":
        return "true"
    if lower in {"priority", "status", "state"}:
        return ""
    kind = schema_type(param)
    if kind == "integer":
        return 1
    if kind == "number":
        return 1
    if kind == "boolean":
        return "true"
    if kind == "array":
        return ""
    return "sample"


def build_query(parameters: list[dict[str, Any]]) -> dict[str, Any]:
    query: dict[str, Any] = {}
    for param in parameters:
        if param.get("in") != "query":
            continue
        name = str(param.get("name") or "")
        if not name:
            continue
        required = bool(param.get("required"))
        lower = name.lower()
        common = lower in {
            "account_id",
            "accountid",
            "date_from",
            "date_to",
            "from",
            "to",
            "limit",
            "offset",
            "only_open",
            "financial_final_blocker",
        }
        if required or common:
            value = sample_value_for_param(name, param)
            if value != "":
                query[name] = value
    return query


def resolve_existing_audit_user_id() -> int | None:
    sys.path.insert(0, str(ROOT / "backend"))
    from sqlalchemy import create_engine, text
    from app.core.config import get_settings

    engine = create_engine(get_settings().sync_database_url, future=True)
    try:
        with engine.connect() as conn:
            value = conn.execute(
                text(
                    "select id from auth_users "
                    "where is_active is true "
                    "order by is_superuser desc, id asc "
                    "limit 1"
                )
            ).scalar()
            return int(value) if value is not None else None
    finally:
        engine.dispose()


def collect_openapi_and_samples(bundle_dir: Path, account_id: int, date_from: str, date_to: str) -> dict[str, Any]:
    sys.path.insert(0, str(ROOT / "backend"))
    from fastapi.testclient import TestClient
    from app.main import app
    from app.models.auth import AuthUser
    from app.services import auth as auth_deps

    audit_user_id = resolve_existing_audit_user_id()

    async def fake_current_user() -> AuthUser:
        now = datetime.now()
        return AuthUser(
            id=audit_user_id or 0,
            email="audit-superuser@example.local",
            full_name="Audit Superuser",
            password_hash="",
            is_active=True,
            is_superuser=True,
            created_at=now,
            updated_at=now,
        )

    app.dependency_overrides[auth_deps.get_current_user] = fake_current_user
    app.dependency_overrides[auth_deps.get_current_superuser] = fake_current_user
    app.dependency_overrides[auth_deps.allow_bootstrap_or_superuser] = fake_current_user

    openapi = app.openapi()
    write_json(bundle_dir / "endpoint_contracts" / "openapi.json", openapi)

    routes_catalog: list[dict[str, Any]] = []
    samples: list[dict[str, Any]] = []
    sample_dir = bundle_dir / "endpoint_samples"
    try:
        with TestClient(app) as client:
            for path, methods in sorted((openapi.get("paths") or {}).items()):
                for method, spec in sorted(methods.items()):
                    method_upper = method.upper()
                    parameters = list(spec.get("parameters") or [])
                    path_params = [p for p in parameters if p.get("in") == "path"]
                    route_record = {
                        "method": method_upper,
                        "path": path,
                        "operation_id": spec.get("operationId"),
                        "summary": spec.get("summary"),
                        "parameters": parameters,
                        "request_body": spec.get("requestBody"),
                        "responses": spec.get("responses"),
                        "sampled": False,
                        "sample_file": None,
                        "sample_skip_reason": None,
                    }
                    if method_upper != "GET":
                        route_record["sample_skip_reason"] = "mutation_or_non_get_not_executed_to_keep_database_unchanged"
                        routes_catalog.append(route_record)
                        continue
                    if path_params:
                        route_record["sample_skip_reason"] = "path_parameters_require_real_ids"
                        routes_catalog.append(route_record)
                        continue
                    if path.endswith(".xlsx") or "/download" in path or "image-proxy" in path:
                        route_record["sample_skip_reason"] = "binary_or_proxy_endpoint_not_sampled"
                        routes_catalog.append(route_record)
                        continue

                    query = build_query(parameters)
                    if "account_id" in {str(p.get("name")) for p in parameters}:
                        query["account_id"] = account_id
                    for key in list(query):
                        if key in {"date_from", "from"}:
                            query[key] = date_from
                        if key in {"date_to", "to"}:
                            query[key] = date_to
                    url = path
                    request_record = {"method": method_upper, "path": path, "query": query}
                    try:
                        response = client.get(url, params=query)
                        content_type = response.headers.get("content-type", "")
                        try:
                            body: Any = response.json()
                        except Exception:
                            body = response.text[:20000]
                        sample_payload = {
                            "request": request_record,
                            "response": {
                                "status_code": response.status_code,
                                "content_type": content_type,
                                "body": body,
                            },
                        }
                    except Exception as exc:
                        sample_payload = {
                            "request": request_record,
                            "response": {
                                "error": repr(exc),
                            },
                        }

                    safe_name = re.sub(r"[^a-zA-Z0-9_.-]+", "_", f"{method_upper}_{path.strip('/') or 'root'}")
                    sample_path = sample_dir / f"{safe_name}.json"
                    write_json(sample_path, sample_payload)
                    route_record["sampled"] = True
                    route_record["sample_file"] = str(sample_path.relative_to(bundle_dir))
                    samples.append(route_record)
                    routes_catalog.append(route_record)
    finally:
        app.dependency_overrides.pop(auth_deps.get_current_user, None)
        app.dependency_overrides.pop(auth_deps.get_current_superuser, None)
        app.dependency_overrides.pop(auth_deps.allow_bootstrap_or_superuser, None)

    write_json(bundle_dir / "endpoint_contracts" / "routes_catalog.json", routes_catalog)
    write_json(bundle_dir / "endpoint_samples" / "_sample_index.json", samples)
    return {
        "routes_total": len(routes_catalog),
        "get_samples_total": len(samples),
        "openapi": "endpoint_contracts/openapi.json",
        "routes_catalog": "endpoint_contracts/routes_catalog.json",
        "sample_index": "endpoint_samples/_sample_index.json",
    }


def collect_service_snapshots(bundle_dir: Path, account_id: int, date_from: str, date_to: str) -> dict[str, Any]:
    sys.path.insert(0, str(ROOT / "backend"))
    import asyncio
    from app.core.db import SessionLocal, dispose_all_engines
    from app.services.dashboard import DashboardService
    from app.services.money_management import MoneyManagementService

    out_dir = bundle_dir / "service_snapshots"
    actual_from = date.fromisoformat(date_from)
    actual_to = date.fromisoformat(date_to)
    money = MoneyManagementService()
    dashboard = DashboardService()

    async def run() -> dict[str, str]:
        created: dict[str, str] = {}
        try:
            async with SessionLocal() as session:
                calls = {
                    "money_summary": money.summary(session, account_id=account_id, date_from=actual_from, date_to=actual_to),
                    "money_actions_today": money.today_actions(session, account_id=account_id, date_from=actual_from, date_to=actual_to, limit=20),
                    "money_articles": money.articles(session, account_id=account_id, date_from=actual_from, date_to=actual_to, limit=10, offset=0),
                    "money_data_blockers": money.data_blockers(session, account_id=account_id, date_from=actual_from, date_to=actual_to),
                    "dashboard_data_health": dashboard.data_health(session, account_id=account_id, date_from=actual_from, date_to=actual_to),
                }
                for name, coro in calls.items():
                    path = out_dir / f"{name}.json"
                    try:
                        result = await coro
                        if hasattr(result, "model_dump"):
                            payload = result.model_dump(mode="json")
                        else:
                            payload = result
                        write_json(path, {"ok": True, "payload": payload})
                    except Exception as exc:
                        write_json(path, {"ok": False, "error": repr(exc)})
                    created[name] = str(path.relative_to(bundle_dir))
            return created
        finally:
            await dispose_all_engines()

    return asyncio.run(run())


def make_checksums(bundle_dir: Path) -> dict[str, str]:
    checksums: dict[str, str] = {}
    for path in sorted(bundle_dir.rglob("*")):
        if path.is_file() and path.name != "checksums.sha256":
            checksums[str(path.relative_to(bundle_dir))] = sha256_file(path)
    lines = [f"{value}  {key}" for key, value in checksums.items()]
    write_text(bundle_dir / "checksums.sha256", "\n".join(lines) + "\n")
    return checksums


def build_readme(bundle_dir: Path, manifest: dict[str, Any]) -> None:
    text = f"""# Finance Audit Bundle

Generated at: `{manifest["generated_at"]}`

Purpose: external AI/code auditor package.

## Contents

- `code/backend_source.zip` - backend source code, excluding `.env`, caches, virtualenvs and build artifacts.
- `code/frontend_source.zip` - frontend source code, excluding `node_modules`, `dist` and caches.
- `database/full_database.sql` - full PostgreSQL plain SQL dump.
- `database/full_database.dump` - full PostgreSQL custom-format dump for `pg_restore`.
- `endpoint_contracts/openapi.json` - all API endpoints with request/response schemas.
- `endpoint_contracts/routes_catalog.json` - route catalog with sampling status.
- `endpoint_samples/*.json` - real GET request/response samples where safe IDs were not required.
- `service_snapshots/*.json` - direct service-level snapshots for dashboard/money audit.
- `config_redacted/` - redacted environment/config files.
- `checksums.sha256` - SHA256 checksums for bundle files.

## Scope Notes

- Non-GET endpoints were not executed because they can mutate the database.
- GET endpoints requiring unknown path IDs were listed in OpenAPI/routes catalog but not sampled.
- Secrets in `.env` are redacted. The database dump is full and may still contain business data, encrypted tokens, user emails, hashes, and operational records.
- Default sampled business window: account `{manifest["account_id"]}`, `{manifest["date_from"]}` to `{manifest["date_to"]}`.

## DB Restore

Plain SQL:

```bash
createdb finance_audit
psql finance_audit < database/full_database.sql
```

Custom dump:

```bash
createdb finance_audit
pg_restore --no-owner --no-privileges -d finance_audit database/full_database.dump
```
"""
    write_text(bundle_dir / "README_AUDIT.md", text)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--account-id", type=int, default=DEFAULT_ACCOUNT_ID)
    parser.add_argument("--date-from", default=DEFAULT_DATE_FROM)
    parser.add_argument("--date-to", default=DEFAULT_DATE_TO)
    parser.add_argument("--out-dir", default=str(ROOT / "audit_bundles"))
    args = parser.parse_args()

    sys.path.insert(0, str(ROOT / "backend"))
    from app.core.config import get_settings

    settings = get_settings()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    bundle_dir = Path(args.out_dir) / f"finance_audit_{timestamp}"
    bundle_dir.mkdir(parents=True, exist_ok=False)

    code_dir = bundle_dir / "code"
    code_stats = {
        "backend": zip_tree(ROOT / "backend", code_dir / "backend_source.zip"),
        "frontend": zip_tree(ROOT / "frontend", code_dir / "frontend_source.zip"),
    }

    config_dir = bundle_dir / "config_redacted"
    redact_env_file(ROOT / "backend" / ".env", config_dir / "backend.env.redacted")
    if (ROOT / ".env.example").exists():
        shutil.copy2(ROOT / ".env.example", config_dir / ".env.example")

    db_stats = dump_database(bundle_dir, settings.database_url)
    endpoint_stats = collect_openapi_and_samples(bundle_dir, args.account_id, args.date_from, args.date_to)
    service_stats = collect_service_snapshots(bundle_dir, args.account_id, args.date_from, args.date_to)

    manifest = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "bundle_dir": str(bundle_dir),
        "account_id": args.account_id,
        "date_from": args.date_from,
        "date_to": args.date_to,
        "database_url_redacted": redacted_database_url(settings.database_url),
        "code": code_stats,
        "database": db_stats,
        "endpoints": endpoint_stats,
        "service_snapshots": service_stats,
        "secrets_policy": "raw .env files excluded; redacted env copy included; full DB dump included as requested",
    }
    write_json(bundle_dir / "manifest.json", manifest)
    build_readme(bundle_dir, manifest)
    checksums = make_checksums(bundle_dir)
    manifest["checksums_total"] = len(checksums)
    write_json(bundle_dir / "manifest.json", manifest)

    bundle_zip = bundle_dir.with_suffix(".zip")
    with zipfile.ZipFile(bundle_zip, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for path in sorted(bundle_dir.rglob("*")):
            if path.is_file():
                zf.write(path, arcname=str(path.relative_to(bundle_dir.parent)))

    print(json.dumps({
        "bundle_dir": str(bundle_dir),
        "bundle_zip": str(bundle_zip),
        "bundle_zip_bytes": bundle_zip.stat().st_size,
        "manifest": str(bundle_dir / "manifest.json"),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
