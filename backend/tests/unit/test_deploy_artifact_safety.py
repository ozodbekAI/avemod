from pathlib import Path

from scripts.check_deploy_artifact_safety import (
    deploy_safety_reason,
    find_suspicious_paths,
)


def test_deploy_safety_reason_blocks_required_artifacts() -> None:
    unsafe_paths = [
        Path("_incoming_projects/backend.zip"),
        Path("backend.zip"),
        Path("data/local.sqlite"),
        Path("data/local.sqlite-wal"),
        Path("data/local.sqlite3-shm"),
        Path("data/local.sqlite3"),
        Path("finance.db"),
        Path("finance.db-journal"),
        Path("finance.xlsx"),
        Path("finance.xls"),
        Path("finance_export.csv"),
        Path("backend_audit.csv"),
        Path("logs/uvicorn.log"),
        Path("secrets/wb-token.txt"),
        Path("deploy/private.pem"),
        Path("deploy/service-account.key"),
        Path("output/current.json"),
        Path("artifacts/report.json"),
        Path("run_output.txt"),
        Path("scratch.tmp"),
        Path("exports/audit.json"),
        Path("audit-bundle-final/report.json"),
        Path("audit_100_backend/FINAL_BACKEND_100_SCORE_REPORT.md"),
        Path("audit-20260617/report.json"),
        Path("checker_extracted/app/main.py"),
        Path("reports/checker_mvp/source/tests/test_health.py"),
        Path("app/__pycache__/router.cpython-312.pyc"),
        Path("scripts/nested/audit_bad.py"),
        Path("audit_seller_rbac.py"),
    ]

    for path in unsafe_paths:
        assert deploy_safety_reason(path), path


def test_deploy_safety_reason_allows_normal_source_files() -> None:
    safe_paths = [
        Path("app/services/portal.py"),
        Path("app/modules/exports/router.py"),
        Path("app/modules/exports/schemas.py"),
        Path("app/modules/exports/output.py"),
        Path("app/services/exporter.py"),
        Path("docs/manual_cost_template.csv"),
        Path("alembic/versions/20260612_000031_operator_foundation.py"),
        Path("deploy/finance.env.example"),
        Path("docs/deploy_ai_operator_safety.md"),
        Path("scripts/audit_seller_rbac.py"),
        Path("scripts/audit_reputation_disabled_mode.py"),
    ]

    for path in safe_paths:
        assert deploy_safety_reason(path) is None, path


def test_find_suspicious_paths_reports_directory_once(tmp_path: Path) -> None:
    (tmp_path / "exports" / "nested").mkdir(parents=True)
    (tmp_path / "exports" / "nested" / "raw.json").write_text("{}", encoding="utf-8")
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "main.py").write_text("print('ok')\n", encoding="utf-8")
    (tmp_path / "finance.sqlite3").write_text("", encoding="utf-8")

    findings = find_suspicious_paths(tmp_path)

    assert (Path("exports"), "blocked data directory: exports") in findings
    assert (Path("finance.sqlite3"), "blocked file suffix: .sqlite3") in findings
    assert not any(path == Path("exports/nested/raw.json") for path, _ in findings)


def test_find_suspicious_paths_allows_source_exports_module(tmp_path: Path) -> None:
    (tmp_path / "app" / "modules" / "exports").mkdir(parents=True)
    (tmp_path / "app" / "modules" / "exports" / "router.py").write_text("router = None\n", encoding="utf-8")
    (tmp_path / "generated" / "app" / "modules" / "exports").mkdir(parents=True)
    (tmp_path / "generated" / "app" / "modules" / "exports" / "data.json").write_text("{}", encoding="utf-8")
    (tmp_path / "generated" / "exports").mkdir(parents=True)
    (tmp_path / "generated" / "exports" / "data.json").write_text("{}", encoding="utf-8")

    findings = find_suspicious_paths(tmp_path)

    assert not any(path == Path("app/modules/exports") for path, _ in findings)
    assert not any(path == Path("app/modules/exports/router.py") for path, _ in findings)
    assert (Path("generated/app/modules/exports"), "blocked data directory: exports") in findings
    assert (Path("generated/exports"), "blocked data directory: exports") in findings


def test_find_suspicious_paths_is_path_aware_for_output_named_source(tmp_path: Path) -> None:
    (tmp_path / "app" / "services").mkdir(parents=True)
    (tmp_path / "app" / "services" / "output.py").write_text("VALUE = 1\n", encoding="utf-8")
    (tmp_path / "output").mkdir()
    (tmp_path / "output" / "local.json").write_text("{}", encoding="utf-8")

    findings = find_suspicious_paths(tmp_path)

    assert not any(path == Path("app/services/output.py") for path, _ in findings)
    assert (Path("output"), "blocked directory: output") in findings


def test_find_suspicious_paths_source_tree_ignores_deploy_excluded_local_dirs(tmp_path: Path) -> None:
    for directory in ("__pycache__", "_incoming_projects", "logs", "reports", "exports"):
        (tmp_path / directory).mkdir(parents=True)
        (tmp_path / directory / "local.db").write_text("", encoding="utf-8")
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "main.py").write_text("print('ok')\n", encoding="utf-8")
    (tmp_path / "deploy").mkdir()
    (tmp_path / "deploy" / "private.pem").write_text("", encoding="utf-8")

    findings = find_suspicious_paths(tmp_path, source_tree=True)

    assert (Path("deploy/private.pem"), "blocked file suffix: .pem") in findings
    assert not any(path.parts[0] in {"__pycache__", "_incoming_projects", "logs", "reports", "exports"} for path, _ in findings)
