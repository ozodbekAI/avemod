#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import unquote, urlparse, urlunparse


ROOT = Path(__file__).resolve().parents[1]
FRONTEND_ROOT = ROOT / "frontend"
VENV_PYTHON = ROOT / ".venv" / "bin" / "python"
VENV_ALEMBIC = ROOT / ".venv" / "bin" / "alembic"


def _python_bin() -> str:
    if VENV_PYTHON.exists():
        return str(VENV_PYTHON)
    raise FileNotFoundError(
        f"Expected project virtualenv interpreter at {VENV_PYTHON}. "
        "Create it with `python3 -m venv .venv` and install dependencies before verification."
    )


def _alembic_bin() -> str:
    if VENV_ALEMBIC.exists():
        return str(VENV_ALEMBIC)
    raise FileNotFoundError(
        f"Expected Alembic executable at {VENV_ALEMBIC}. "
        "Install project dependencies into .venv before verification."
    )


def _module_cmd(module: str) -> list[str]:
    return [_python_bin(), "-m", module]
EXPECTED_VIEWS = [
    "v_core_sku_enriched",
    "v_wb_orders_current",
    "v_wb_sales_current",
]


def _trim(value: str, limit: int = 4000) -> str:
    if len(value) <= limit:
        return value
    return value[:limit] + "\n...<truncated>..."


def _run(
    cmd: list[str],
    *,
    env: dict[str, str] | None = None,
    cwd: Path = ROOT,
) -> dict:
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    started = time.time()
    process = subprocess.run(
        cmd,
        cwd=cwd,
        env=merged_env,
        text=True,
        capture_output=True,
    )
    duration = round(time.time() - started, 3)
    return {
        "ok": process.returncode == 0,
        "returncode": process.returncode,
        "duration_seconds": duration,
        "stdout": _trim(process.stdout.strip()),
        "stderr": _trim(process.stderr.strip()),
        "cmd": " ".join(cmd),
    }


def _get_database_url(cli_database_url: str | None) -> str:
    if cli_database_url:
        return cli_database_url
    if "DATABASE_URL" in os.environ:
        return os.environ["DATABASE_URL"]
    for candidate in (ROOT / ".env", ROOT / ".env.example"):
        if not candidate.exists():
            continue
        for line in candidate.read_text(encoding="utf-8").splitlines():
            if not line or line.strip().startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            if key.strip() == "DATABASE_URL":
                return value.strip()
    return "postgresql+asyncpg://postgres:postgres@localhost:5432/wb_data_core"


def _parse_database_url(database_url: str) -> dict[str, str | int | None]:
    parsed = urlparse(database_url)
    return {
        "scheme": parsed.scheme,
        "username": unquote(parsed.username) if parsed.username else None,
        "password": unquote(parsed.password) if parsed.password else None,
        "hostname": parsed.hostname or "localhost",
        "port": parsed.port,
        "database": parsed.path.lstrip("/"),
        "query": parsed.query,
    }


def _build_database_url(template_url: str, database_name: str) -> str:
    parsed = urlparse(template_url)
    rebuilt = parsed._replace(path=f"/{database_name}")
    return urlunparse(rebuilt)


def _scheduler_check() -> dict:
    python_bin = _python_bin()
    script = (
        "from apscheduler.schedulers.asyncio import AsyncIOScheduler\n"
        "from app.jobs.registry import register_jobs\n"
        "scheduler = AsyncIOScheduler()\n"
        "register_jobs(scheduler)\n"
        "print(len(scheduler.get_jobs()))\n"
        "print('\\n'.join(sorted(job.id for job in scheduler.get_jobs())))\n"
    )
    return _run([python_bin, "-c", script])


def _formula_smoke_check() -> dict:
    python_bin = _python_bin()
    return _run(
        [
            python_bin,
            "-m",
            "pytest",
            "tests/unit/test_dashboard_service.py::test_profit_formula_shape",
            "tests/unit/test_dashboard_service.py::test_article_reconciliation_uses_finance_report_total_for_match_check",
            "tests/unit/test_manual_costs_service.py::test_operator_baseline_supplier_does_not_count_as_business_trusted",
            "tests/unit/test_control_tower_service.py",
            "-q",
        ]
    )


def _frontend_checks() -> dict:
    if not FRONTEND_ROOT.exists():
        return {"ok": False, "reason": "frontend directory not found", "steps": {}}
    if shutil.which("npm") is None:
        return {"ok": False, "reason": "npm executable not found", "steps": {}}
    typecheck = _run(["npm", "run", "typecheck"], cwd=FRONTEND_ROOT)
    build = _run(["npm", "run", "build"], cwd=FRONTEND_ROOT)
    ok = typecheck["ok"] and build["ok"]
    return {
        "ok": ok,
        "reason": None if ok else "Frontend verification failed",
        "steps": {
            "typecheck": typecheck,
            "build": build,
        },
    }


def _expected_sha256(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _dedupe_parity_check(
    host: str,
    port: str | None,
    user: str | None,
    database_name: str,
    pg_env: dict[str, str],
) -> dict:
    order_payload = "1|SRID|2026-05-15T12:00:00+00:00|111|AAA|555"
    sale_payload = "1|SRID|2026-05-15T12:00:00+00:00|111|AAA|SALE-555"
    query = """
    SELECT
      encode(
        digest(
          concat_ws(
            '|',
            COALESCE(1::text, '<null>'),
            COALESCE('SRID', '<null>'),
            CASE
              WHEN to_char(timezone('UTC', '2026-05-15T12:00:00+00:00'::timestamptz), 'US') = '000000'
              THEN to_char(timezone('UTC', '2026-05-15T12:00:00+00:00'::timestamptz), 'YYYY-MM-DD"T"HH24:MI:SS') || '+00:00'
              ELSE to_char(timezone('UTC', '2026-05-15T12:00:00+00:00'::timestamptz), 'YYYY-MM-DD"T"HH24:MI:SS.US') || '+00:00'
            END,
            COALESCE(111::text, '<null>'),
            COALESCE('AAA', '<null>'),
            COALESCE(555::text, '<null>')
          ),
          'sha256'
        ),
        'hex'
      ) AS order_hash,
      encode(
        digest(
          concat_ws(
            '|',
            COALESCE(1::text, '<null>'),
            COALESCE('SRID', '<null>'),
            CASE
              WHEN to_char(timezone('UTC', '2026-05-15T12:00:00+00:00'::timestamptz), 'US') = '000000'
              THEN to_char(timezone('UTC', '2026-05-15T12:00:00+00:00'::timestamptz), 'YYYY-MM-DD"T"HH24:MI:SS') || '+00:00'
              ELSE to_char(timezone('UTC', '2026-05-15T12:00:00+00:00'::timestamptz), 'YYYY-MM-DD"T"HH24:MI:SS.US') || '+00:00'
            END,
            COALESCE(111::text, '<null>'),
            COALESCE('AAA', '<null>'),
            COALESCE('SALE-555', '<null>')
          ),
          'sha256'
        ),
        'hex'
      ) AS sale_hash
    """
    cmd = ["psql", "-h", host]
    if port:
        cmd.extend(["-p", port])
    if user:
        cmd.extend(["-U", user])
    cmd.extend(["-d", database_name, "-AtF", "|", "-c", query])
    step = _run(cmd, env=pg_env)
    if not step["ok"]:
        return {"ok": False, "reason": "psql parity query failed", "step": step}
    output = step["stdout"].strip()
    parts = output.split("|") if output else []
    if len(parts) != 2:
        return {"ok": False, "reason": "unexpected parity query output", "step": step}
    order_hash, sale_hash = parts
    expected_order = _expected_sha256(order_payload)
    expected_sale = _expected_sha256(sale_payload)
    return {
        "ok": order_hash == expected_order and sale_hash == expected_sale,
        "reason": None if order_hash == expected_order and sale_hash == expected_sale else "dedupe hash mismatch",
        "step": step,
        "expected_order": expected_order,
        "actual_order": order_hash,
        "expected_sale": expected_sale,
        "actual_sale": sale_hash,
    }


def _clean_postgres_check(database_url: str, keep_temp_db: bool) -> dict:
    parsed = _parse_database_url(database_url)
    result: dict[str, object] = {
        "ok": False,
        "reason": None,
        "views": [],
        "temp_database": None,
        "steps": {},
    }
    if not str(parsed["scheme"]).startswith("postgresql"):
        result["reason"] = "DATABASE_URL is not PostgreSQL"
        return result
    required_binaries = ["dropdb", "createdb", "psql"]
    missing = [binary for binary in required_binaries if shutil.which(binary) is None]
    if missing:
        result["reason"] = f"Missing PostgreSQL CLI tools: {', '.join(missing)}"
        return result
    base_name = str(parsed["database"] or "wb_data_core")
    temp_database = f"{base_name}_verify_{int(time.time())}"
    result["temp_database"] = temp_database
    temp_database_url = _build_database_url(database_url, temp_database)
    pg_env = {}
    if parsed["password"]:
        pg_env["PGPASSWORD"] = str(parsed["password"])
    host = str(parsed["hostname"])
    port = str(parsed["port"]) if parsed["port"] else None
    user = str(parsed["username"]) if parsed["username"] else None

    def _pg_cmd(binary: str, database_name: str | None = None, *, include_db: bool = False) -> list[str]:
        cmd = [binary, "-h", host]
        if port:
            cmd.extend(["-p", port])
        if user:
            cmd.extend(["-U", user])
        if include_db and database_name:
            cmd.extend(["-d", database_name])
        elif database_name:
            cmd.append(database_name)
        return cmd

    result["steps"]["dropdb_before"] = _run(
        _pg_cmd("dropdb", temp_database) + ["--if-exists"],
        env=pg_env,
    )
    if not result["steps"]["dropdb_before"]["ok"]:
        result["reason"] = "Initial dropdb failed"
        return result

    result["steps"]["createdb"] = _run(
        _pg_cmd("createdb", temp_database),
        env=pg_env,
    )
    if not result["steps"]["createdb"]["ok"]:
        result["reason"] = "createdb failed"
        return result

    try:
        alembic_env = {"DATABASE_URL": temp_database_url}
        result["steps"]["alembic_upgrade_1"] = _run(
            [_alembic_bin(), "upgrade", "head"],
            env=alembic_env,
        )
        result["steps"]["alembic_upgrade_2"] = _run(
            [_alembic_bin(), "upgrade", "head"],
            env=alembic_env,
        )
        if not result["steps"]["alembic_upgrade_1"]["ok"] or not result["steps"]["alembic_upgrade_2"]["ok"]:
            result["reason"] = "Alembic upgrade failed"
            return result

        view_query = (
            "select table_name from information_schema.views "
            "where table_name in ('v_core_sku_enriched','v_wb_orders_current','v_wb_sales_current') "
            "order by table_name;"
        )
        result["steps"]["view_query"] = _run(
            _pg_cmd("psql", temp_database, include_db=True) + ["-Atc", view_query],
            env=pg_env,
        )
        if not result["steps"]["view_query"]["ok"]:
            result["reason"] = "View query failed"
            return result
        views = [line.strip() for line in result["steps"]["view_query"]["stdout"].splitlines() if line.strip()]
        result["views"] = views
        result["steps"]["dedupe_parity"] = _dedupe_parity_check(
            host,
            port,
            user,
            temp_database,
            pg_env,
        )
        result["ok"] = views == EXPECTED_VIEWS and result["steps"]["dedupe_parity"]["ok"]
        if views != EXPECTED_VIEWS:
            result["reason"] = "Expected views not found"
        elif not result["steps"]["dedupe_parity"]["ok"]:
            result["reason"] = result["steps"]["dedupe_parity"]["reason"]
        return result
    finally:
        if not keep_temp_db:
            result["steps"]["dropdb_after"] = _run(
                _pg_cmd("dropdb", temp_database) + ["--if-exists"],
                env=pg_env,
            )


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify backend correctness acceptance pack.")
    parser.add_argument("--database-url", help="Override DATABASE_URL for clean PostgreSQL verification.")
    parser.add_argument("--keep-temp-db", action="store_true", help="Keep temporary verification database.")
    parser.add_argument("--skip-clean-postgres", action="store_true", help="Skip clean PostgreSQL migration smoke.")
    args = parser.parse_args()

    try:
        python_bin = _python_bin()
    except FileNotFoundError as error:
        print(
            json.dumps(
                {
                    "overall_ok": False,
                    "python_env": {
                        "ok": False,
                        "reason": str(error),
                        "current_interpreter": str(Path(sys.executable)),
                    },
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 1
    database_url = _get_database_url(args.database_url)

    results: dict[str, object] = {
        "python_env": {
            "ok": True,
            "project_python": python_bin,
            "current_interpreter": str(Path(sys.executable)),
        },
        "compileall": _run([python_bin, "-m", "compileall", "-q", "app", "tests", "scripts", "alembic"]),
        "pytest": _run([python_bin, "-m", "pytest", "tests/unit", "tests/api", "-q"]),
        "formula_smoke": _formula_smoke_check(),
        "scheduler": _scheduler_check(),
        "frontend": _frontend_checks(),
    }
    if args.skip_clean_postgres:
        results["clean_postgres"] = {"ok": False, "skipped": True, "reason": "Skipped by flag"}
    else:
        results["clean_postgres"] = _clean_postgres_check(database_url, args.keep_temp_db)
    results["overall_ok"] = all(
        section.get("ok", False)
        for key, section in results.items()
        if isinstance(section, dict) and key != "clean_postgres"
    ) and bool(results["clean_postgres"].get("ok") or results["clean_postgres"].get("skipped"))
    print(json.dumps(results, indent=2, sort_keys=True))
    return 0 if results["overall_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
