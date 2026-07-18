from __future__ import annotations

from pathlib import Path

from scripts.scan_frontend_secret_literals import scan_file, scan_roots


ROOT = Path(__file__).resolve().parents[3]
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_frontend_secret_literal_scanner_flags_password_literals(tmp_path: Path) -> None:
    unsafe = tmp_path / "login.tsx"
    unsafe.write_text('const password = "HardcodedPassword2026!";\n', encoding="utf-8")

    findings = scan_file(unsafe)

    assert len(findings) == 1
    assert findings[0].reason == "password literal"


def test_frontend_source_contains_no_hardcoded_credentials() -> None:
    findings = scan_roots([FRONTEND / "src", FRONTEND / "e2e", FRONTEND / "playwright.config.ts", FRONTEND / "package.json"])

    assert findings == []
    login = _read(FRONTEND / "src" / "routes" / "login.tsx")
    assert 'useState("")' in login
    assert "FinanceAdmin2026" not in login
    assert "live-test-admin@example.com" not in login

    scripts_with_audit_login_defaults = [
        BACKEND / "scripts" / "audit_dashboard_finance_vs_wb.py",
        BACKEND / "scripts" / "audit_frontend_placeholder_consistency.py",
        BACKEND / "scripts" / "export_ai_formula_handoff.py",
        BACKEND / "scripts" / "export_live_backend_full_audit.py",
        BACKEND / "scripts" / "manual_correctness_audit.py",
    ]
    for script in scripts_with_audit_login_defaults:
        assert "live-test-admin@example.com" not in _read(script)
        assert "audit-user@example.invalid" in _read(script)


def test_deploy_and_ci_gates_include_backend_frontend_and_secret_checks() -> None:
    backend_workflow = _read(ROOT / ".github" / "workflows" / "deploy-finance-backend.yml")
    frontend_workflow = _read(ROOT / ".github" / "workflows" / "frontend-ci.yml")

    assert "python -m compileall -q app tests scripts alembic" in backend_workflow
    assert "python -m pytest -q -p no:ddtrace" in backend_workflow
    assert "python scripts/scan_secret_leaks.py app scripts" in backend_workflow
    assert "python scripts/check_deploy_artifact_safety.py --source-tree ." in backend_workflow
    assert "npm run build" in frontend_workflow
    assert "npm run test:e2e" in frontend_workflow


def test_deploy_artifact_excludes_runtime_and_secret_material() -> None:
    workflow = _read(ROOT / ".github" / "workflows" / "deploy-finance-backend.yml")
    remote = _read(BACKEND / "deploy" / "remote_deploy_finance_backend.sh")

    for blocked in (
        "--exclude '/_incoming_projects'",
        "--exclude '/reports'",
        "--exclude '/logs'",
        "--exclude '*.zip'",
        "--exclude '*.db'",
        "--exclude '*.xlsx'",
        "--exclude 'audit-bundle*'",
        "--exclude '*.har'",
        "--exclude '*.trace'",
    ):
        assert blocked in workflow

    assert "alembic upgrade head" in remote
    assert "systemctl restart" in remote
    assert "nginx -t" in remote
    assert "curl -fsS http://127.0.0.1:8016/api/v1/health" in remote


def test_account_scope_and_role_guards_are_used_by_portal_writes() -> None:
    router = _read(BACKEND / "app" / "modules" / "portal" / "router.py")
    auth = _read(BACKEND / "app" / "services" / "auth.py")

    assert "resolve_user_account" in auth
    assert "require_account_role" in auth
    assert "_required_portal_account_for_role" in router
    for route_name in (
        "portal_photo_asset_upload",
        "portal_photo_version_review",
        "portal_create_experiment",
        "portal_record_experiment_intervention",
        "portal_submit_case",
    ):
        assert route_name in router
    assert router.count("_required_portal_account_for_role") >= 20
