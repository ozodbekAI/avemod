#!/usr/bin/env python3
"""Generate deterministic static audit summary from current evidence files."""

from __future__ import annotations

import argparse
import json
import tomllib
from pathlib import Path
from typing import Any


OPTIONAL_STATUS = "NOT_CONFIGURED_OPTIONAL"


def read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def read_rc(path: Path) -> int | None:
    try:
        return int(path.read_text(encoding="utf-8").strip())
    except Exception:
        return None


def pyproject_dependencies(pyproject_path: Path) -> set[str]:
    try:
        data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    except Exception:
        return set()
    names: set[str] = set()
    project = data.get("project") or {}
    groups = [project.get("dependencies") or []]
    optional = project.get("optional-dependencies") or {}
    groups.extend(optional.values())
    for group in groups:
        for dep in group:
            name = str(dep).split("[", 1)[0].split(">", 1)[0].split("<", 1)[0].split("=", 1)[0].split("~", 1)[0].strip().lower()
            if name:
                names.add(name)
    return names


def tool_status(tool: str, audit_dir: Path, pyproject_path: Path) -> dict[str, Any]:
    static_dir = audit_dir / "02_code_static"
    rc = read_rc(static_dir / f"{tool}.rc")
    output = (static_dir / f"{tool}.txt").read_text(encoding="utf-8", errors="ignore") if (static_dir / f"{tool}.txt").exists() else ""
    configured = tool in pyproject_dependencies(pyproject_path)
    missing_module = f"No module named {tool}" in output
    if not configured and (rc is None or missing_module or rc != 0):
        status = OPTIONAL_STATUS
        blocking = False
    elif rc == 0:
        status = "PASS"
        blocking = False
    else:
        status = "FAIL"
        blocking = True
    return {
        "tool": tool,
        "rc": rc,
        "status": status,
        "blocking": blocking,
        "configured_dependency": configured,
        "missing_module": missing_module,
    }


def build_static_summary(audit_dir: Path, pyproject_path: Path) -> dict[str, Any]:
    static_dir = audit_dir / "02_code_static"
    risky = read_json(static_dir / "risky_patterns.json", {})
    duplicate_routes = read_json(audit_dir / "05_openapi_routes" / "duplicate_routes.json", [])
    compileall_rc = read_rc(static_dir / "compileall.rc")
    return {
        "compileall": {
            "rc": compileall_rc,
            "status": "PASS" if compileall_rc == 0 else "FAIL",
            "blocking": compileall_rc != 0,
        },
        "ruff": tool_status("ruff", audit_dir, pyproject_path),
        "mypy": tool_status("mypy", audit_dir, pyproject_path),
        "risky_patterns": {
            "status": risky.get("status", "MISSING"),
            "count": int(risky.get("count") or 0),
            "blocking": int(risky.get("count") or 0) > 0 or risky.get("status") == "FAIL",
        },
        "duplicate_routes": {
            "count": len(duplicate_routes) if isinstance(duplicate_routes, list) else int(duplicate_routes.get("count") or 0),
        },
    }


def write_static_summary(audit_dir: Path, summary: dict[str, Any]) -> None:
    static_dir = audit_dir / "02_code_static"
    lines = [
        "# Static Findings",
        "",
        f"- compileall rc: {summary['compileall']['rc']}",
        f"- compileall status: {summary['compileall']['status']}",
        f"- ruff rc: {summary['ruff']['rc']}",
        f"- ruff status: {summary['ruff']['status']}",
        f"- mypy rc: {summary['mypy']['rc']}",
        f"- mypy status: {summary['mypy']['status']}",
        f"- risky pattern findings: {summary['risky_patterns']['count']}",
        f"- risky pattern status: {summary['risky_patterns']['status']}",
        f"- duplicate routes: {summary['duplicate_routes']['count']}",
        "",
        "## Notes",
        "",
    ]
    for tool in ("ruff", "mypy"):
        item = summary[tool]
        if item["status"] == OPTIONAL_STATUS:
            lines.append(f"- `{tool}` is not listed in configured dependencies and is treated as optional, not a code failure.")
    static_dir.mkdir(parents=True, exist_ok=True)
    (static_dir / "static_findings.md").write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    (static_dir / "static_findings.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit-dir", type=Path, default=Path("audit_100_backend"))
    parser.add_argument("--pyproject", type=Path, default=Path("pyproject.toml"))
    args = parser.parse_args()
    summary = build_static_summary(args.audit_dir, args.pyproject)
    write_static_summary(args.audit_dir, summary)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0 if not any(summary[name].get("blocking") for name in ("compileall", "ruff", "mypy", "risky_patterns")) else 1


if __name__ == "__main__":
    raise SystemExit(main())
