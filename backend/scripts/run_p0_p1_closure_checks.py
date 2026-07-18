"""Run the P0/P1 closure verification gate without printing secrets."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PYTHON = Path(sys.executable)

TARGETED_TESTS = [
    "tests/unit/test_module_registry.py",
    "tests/unit/test_runtime_correctness.py::test_register_jobs_does_not_raise_and_registers_jobs",
    "tests/unit/test_reputation_service.py",
    "tests/unit/test_claims_factory_service.py",
    "tests/unit/test_grouping_beta_service.py",
    "tests/unit/test_photo_studio_service.py",
    "tests/unit/test_experiments_service.py",
    "tests/unit/test_stock_control_domain.py",
    "tests/api/test_portal_routes.py",
]

CRITICAL_COVERAGE_TARGETS = [
    "--cov=app.services.portal",
    "--cov=app.services.module_registry",
    "--cov=app.jobs",
    "--cov=app.services.claims_factory",
    "--cov=app.services.reputation",
    "--cov=app.services.grouping",
    "--cov=app.services.photo_studio",
    "--cov=app.services.experiments",
    "--cov=app.services.stock_control",
]


def _run(label: str, command: list[str], *, env: dict[str, str] | None = None) -> None:
    print(f"\n== {label} ==")
    subprocess.run(command, cwd=ROOT, env=env, check=True)


def main() -> int:
    env = os.environ.copy()
    env.setdefault("PYTHONPATH", str(ROOT))
    coverage_fail_under = env.get("P0_P1_COVERAGE_FAIL_UNDER", "50")

    checks = [
        ("compile", [str(PYTHON), "-m", "compileall", "-f", "-q", "app", "tests", "alembic", "scripts"]),
        ("ruff", [str(PYTHON), "-m", "ruff", "check", "app", "tests", "scripts", "alembic"]),
        ("mypy", [str(PYTHON), "-m", "mypy", "app"]),
        ("bandit-high", [str(PYTHON), "-m", "bandit", "-q", "-lll", "-r", "app", "scripts"]),
        ("secret-scan", [str(PYTHON), "scripts/scan_secret_leaks.py"]),
        ("alembic-heads", [str(PYTHON), "-m", "alembic", "heads"]),
        ("deploy-context-safety", [str(PYTHON), "scripts/check_deploy_artifact_safety.py", "--root", "deploy"]),
        ("targeted-tests", [str(PYTHON), "-m", "pytest", "-q", *TARGETED_TESTS]),
        ("full-tests", [str(PYTHON), "-m", "pytest", "-q"]),
        (
            "critical-coverage-baseline",
            [
                str(PYTHON),
                "-m",
                "pytest",
                "-q",
                *CRITICAL_COVERAGE_TARGETS,
                "--cov-report=term-missing",
                f"--cov-fail-under={coverage_fail_under}",
            ],
        ),
    ]

    postgres_database_url = env.get("P0_P1_POSTGRES_DATABASE_URL")
    if postgres_database_url:
        postgres_env = env.copy()
        postgres_env["DATABASE_URL"] = postgres_database_url
        checks.insert(
            7,
            ("postgres-alembic-upgrade", [str(PYTHON), "-m", "alembic", "upgrade", "head"]),
        )
        env_by_label = {"postgres-alembic-upgrade": postgres_env}
    else:
        env_by_label = {}

    if env.get("P0_P1_STRICT_COVERAGE") == "1":
        checks.append(
            (
                "critical-coverage-strict-85",
                [
                    str(PYTHON),
                    "-m",
                    "pytest",
                    "-q",
                    *CRITICAL_COVERAGE_TARGETS,
                    "--cov-report=term-missing",
                    "--cov-fail-under=85",
                ],
            )
        )

    missing = [name for name in ("ruff", "mypy", "bandit") if shutil.which(name) is None]
    if missing:
        print(f"Tool executables not on PATH: {', '.join(missing)}. Falling back to python -m invocations.")
    if not postgres_database_url:
        print("P0_P1_POSTGRES_DATABASE_URL is not set; skipping real PostgreSQL alembic upgrade gate.")
    if env.get("P0_P1_STRICT_COVERAGE") != "1":
        print("P0_P1_STRICT_COVERAGE is not set to 1; enforcing coverage baseline only.")

    for label, command in checks:
        _run(label, command, env=env_by_label.get(label, env))
    print("\nP0/P1 closure checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
