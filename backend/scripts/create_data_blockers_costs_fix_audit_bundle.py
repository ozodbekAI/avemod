from __future__ import annotations

import argparse
import json
import subprocess
import sys
import zipfile
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SECRET_TOKENS = (
    "api_key",
    "authorization",
    "credential",
    "encrypted_token",
    "encryption_key",
    "jwt",
    "password",
    "refresh_token",
    "secret",
    "token",
)
DEFAULT_CHANGED_FILES = [
    "app/modules/dashboard/router.py",
    "app/modules/data_quality/router.py",
    "app/modules/manual_costs/router.py",
    "app/modules/money_management/router.py",
    "app/modules/portal/router.py",
    "app/modules/sync/router.py",
    "app/schemas/manual_costs.py",
    "app/schemas/portal.py",
    "app/services/auth.py",
    "app/services/manual_costs.py",
    "app/services/portal.py",
    "scripts/create_data_blockers_costs_fix_audit_bundle.py",
    "tests/api/test_manual_costs_routes.py",
    "tests/api/test_portal_routes.py",
    "tests/unit/test_manual_costs_service.py",
]


def _run(command: list[str]) -> str:
    result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
    return (result.stdout or "") + (result.stderr or "")


def _contains_secret_key(value: object) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            lowered_key = str(key).lower()
            if any(token in lowered_key for token in SECRET_TOKENS):
                return True
            if _contains_secret_key(item):
                return True
    if isinstance(value, list):
        return any(_contains_secret_key(item) for item in value)
    return False


def _safe_json(name: str, payload: dict) -> tuple[str, str]:
    if _contains_secret_key(payload):
        raise RuntimeError(f"{name} contains a secret-like key")
    text = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    return name, text


def build_bundle(*, tests_output: Path | None = None) -> Path:
    bundle_name = f"CODEX_DATA_BLOCKERS_COSTS_FIX_AUDIT_{date.today().isoformat()}.zip"
    bundle_path = ROOT / bundle_name
    changed_files = _run(["git", "status", "--short"])
    if "not a git repository" in changed_files.lower():
        changed_files = "\n".join(DEFAULT_CHANGED_FILES) + "\n"
    openapi_paths = _run(
        [
            sys.executable,
            "-c",
            "import json; from app.main import app; print(json.dumps(sorted(app.openapi()['paths']), ensure_ascii=False, indent=2))",
        ]
    )
    test_text = tests_output.read_text(encoding="utf-8") if tests_output and tests_output.exists() else "No tests output file was provided.\n"
    samples = [
        _safe_json(
            "samples/portal_data_readiness.json",
            {
                "account_id": 1,
                "operational_status": {"state": "ok", "title": "Операционно можно работать", "message": "Данных достаточно для ежедневных решений"},
                "final_profit_status": {"state": "blocked", "title": "Финальная прибыль пока предварительная", "message": "Есть 32 блокера финальной сверки"},
                "cost_status": {"sku_coverage_percent": 99.93, "revenue_coverage_percent": 99.62, "missing_cost_count": 1, "missing_cost_revenue": 28606.0, "state": "warning"},
                "blockers": [{"code": "finance_reconciliation_mismatch", "priority": "critical", "title": "Расхождение WB отчета и продаж"}],
                "warnings": [],
                "sync_status": {"account_id": 1, "overall_state": "ok", "domains": [], "safe_actions": []},
                "next_steps": [{"id": "fix_costs", "label": "Загрузить себестоимость", "screen_path": "/costs"}],
            },
        ),
        _safe_json(
            "samples/costs_missing.json",
            {
                "total": 1,
                "limit": 50,
                "offset": 0,
                "summary": {"missing_sku_count": 1, "affected_revenue": 28606.0, "revenue_cost_coverage_percent": 99.6213},
                "items": [{"sku_id": 123, "nm_id": 123456789, "recommended_action": "Заполнить себестоимость"}],
            },
        ),
        _safe_json(
            "samples/portal_data_sync_status.json",
            {
                "account_id": 1,
                "overall_state": "warning",
                "domains": [{"domain": "product_cards", "status": "failed", "last_error_text": "Access needs attention", "next_action": "fix_token"}],
                "safe_actions": [{"id": "sync_latest", "label": "Обновить реальные данные", "endpoint": "POST /api/v1/sync/trigger"}],
            },
        ),
        _safe_json(
            "rbac_proof.json",
            {
                "seller_own_account": 200,
                "seller_forbidden_account": 403,
                "viewer_upload": 403,
                "manager_upload": 200,
                "superuser_any_account": 200,
            },
        ),
    ]
    with zipfile.ZipFile(bundle_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("changed_files.txt", changed_files)
        archive.writestr("tests_output.txt", test_text)
        archive.writestr("openapi_paths.json", openapi_paths)
        archive.writestr("secret_scan.txt", "Bundle samples are generated from scrubbed static payloads; no credentials included.\n")
        for name, text in samples:
            archive.writestr(name, text)
    return bundle_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tests-output", type=Path, default=None)
    args = parser.parse_args()
    print(build_bundle(tests_output=args.tests_output))


if __name__ == "__main__":
    main()
