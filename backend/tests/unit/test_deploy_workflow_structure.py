from __future__ import annotations

from pathlib import Path


def test_finance_backend_workflow_uses_backend_root() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    workflow = repo_root / ".github" / "workflows" / "deploy-finance-backend.yml"
    text = workflow.read_text(encoding="utf-8")

    assert '"backend/app/**"' in text
    assert '"backend/alembic/**"' in text
    assert '"backend/pyproject.toml"' in text
    assert "working-directory: backend" in text
    assert "cd backend" in text
    assert "python -m pip install -e \".[dev]\"" in text
