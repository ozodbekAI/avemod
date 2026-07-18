from __future__ import annotations

import json
from pathlib import Path

from scripts.generate_static_audit_summary import (
    OPTIONAL_STATUS,
    build_static_summary,
    write_static_summary,
)


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_static_findings_uses_current_risky_pattern_count(tmp_path: Path) -> None:
    audit_dir = tmp_path / "audit"
    pyproject = tmp_path / "pyproject.toml"
    write(pyproject, '[project]\ndependencies = []\n[project.optional-dependencies]\ndev = ["pytest>=8"]\n')
    write(audit_dir / "02_code_static" / "compileall.rc", "0\n")
    write(audit_dir / "02_code_static" / "ruff.rc", "1\n")
    write(audit_dir / "02_code_static" / "ruff.txt", "No module named ruff\n")
    write(audit_dir / "02_code_static" / "mypy.rc", "1\n")
    write(audit_dir / "02_code_static" / "mypy.txt", "No module named mypy\n")
    write(audit_dir / "02_code_static" / "risky_patterns.json", json.dumps({"status": "PASS", "count": 0}))
    write(audit_dir / "05_openapi_routes" / "duplicate_routes.json", "[]\n")

    summary = build_static_summary(audit_dir, pyproject)
    write_static_summary(audit_dir, summary)

    markdown = (audit_dir / "02_code_static" / "static_findings.md").read_text(encoding="utf-8")
    assert "risky pattern findings: 0" in markdown
    assert "risky pattern findings: 16" not in markdown


def test_missing_ruff_and_mypy_are_optional_when_not_dependencies(tmp_path: Path) -> None:
    audit_dir = tmp_path / "audit"
    pyproject = tmp_path / "pyproject.toml"
    write(pyproject, '[project]\ndependencies = ["fastapi>=0.115"]\n[project.optional-dependencies]\ndev = ["pytest>=8"]\n')
    write(audit_dir / "02_code_static" / "compileall.rc", "0\n")
    write(audit_dir / "02_code_static" / "ruff.rc", "1\n")
    write(audit_dir / "02_code_static" / "ruff.txt", "/bin/python: No module named ruff\n")
    write(audit_dir / "02_code_static" / "mypy.rc", "1\n")
    write(audit_dir / "02_code_static" / "mypy.txt", "/bin/python: No module named mypy\n")
    write(audit_dir / "02_code_static" / "risky_patterns.json", json.dumps({"status": "PASS", "count": 0}))
    write(audit_dir / "05_openapi_routes" / "duplicate_routes.json", "[]\n")

    summary = build_static_summary(audit_dir, pyproject)

    assert summary["ruff"]["status"] == OPTIONAL_STATUS
    assert summary["ruff"]["blocking"] is False
    assert summary["mypy"]["status"] == OPTIONAL_STATUS
    assert summary["mypy"]["blocking"] is False
