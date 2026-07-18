#!/usr/bin/env python3
"""Scan production code and scripts for raw secret logging patterns."""

from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass
from pathlib import Path


DEFAULT_SCAN_ROOTS = ("app", "scripts")
SENSITIVE_NAME_TOKENS = (
    "access_token",
    "api_key",
    "authorization",
    "jwt",
    "password",
    "refresh_token",
    "secret",
    "service_token",
    "token",
    "wb_token",
)
SAFE_NAME_TOKENS = (
    "token_present",
    "token_provided",
    "token_resolved",
    "token_source",
    "token_type",
)
LOGGER_METHODS = {"critical", "debug", "error", "exception", "info", "warning", "warn"}


@dataclass(frozen=True)
class SecretLogFinding:
    path: Path
    line: int
    call: str
    reason: str

    def format(self) -> str:
        return f"{self.path}:{self.line}: {self.reason} ({self.call})"


def _is_logger_call(func: ast.AST) -> bool:
    if not isinstance(func, ast.Attribute) or func.attr not in LOGGER_METHODS:
        return False
    if isinstance(func.value, ast.Name):
        return func.value.id in {"logger", "logging"}
    if isinstance(func.value, ast.Attribute):
        return isinstance(func.value.value, ast.Name) and func.value.value.id == "logging"
    return False


def _call_name(func: ast.AST) -> str | None:
    if isinstance(func, ast.Name) and func.id == "print":
        return "print"
    if _is_logger_call(func):
        return "logger"
    return None


def _name_is_sensitive(name: str) -> bool:
    lowered = name.lower()
    if any(safe in lowered for safe in SAFE_NAME_TOKENS):
        return False
    return any(token in lowered for token in SENSITIVE_NAME_TOKENS)


def _node_has_sensitive_value(node: ast.AST) -> bool:
    if isinstance(node, ast.Name):
        return _name_is_sensitive(node.id)
    if isinstance(node, ast.Attribute):
        return _name_is_sensitive(node.attr) or _node_has_sensitive_value(node.value)
    if isinstance(node, ast.Subscript):
        return _node_has_sensitive_value(node.value) or _node_has_sensitive_value(node.slice)
    if isinstance(node, ast.Constant):
        return False
    if isinstance(node, ast.JoinedStr):
        return any(_node_has_sensitive_value(value) for value in node.values)
    if isinstance(node, ast.FormattedValue):
        return _node_has_sensitive_value(node.value)
    if isinstance(node, ast.Call):
        if isinstance(node.func, ast.Name) and node.func.id == "bool":
            return False
        return _node_has_sensitive_value(node.func) or any(
            _node_has_sensitive_value(arg) for arg in node.args
        ) or any(_node_has_sensitive_value(keyword.value) for keyword in node.keywords)
    if isinstance(node, ast.BinOp):
        return _node_has_sensitive_value(node.left) or _node_has_sensitive_value(node.right)
    if isinstance(node, ast.Tuple | ast.List | ast.Set):
        return any(_node_has_sensitive_value(item) for item in node.elts)
    if isinstance(node, ast.Dict):
        return any(
            (key is not None and _node_has_sensitive_value(key)) or _node_has_sensitive_value(value)
            for key, value in zip(node.keys, node.values, strict=False)
        )
    return False


def scan_file(path: Path, *, display_path: Path | None = None) -> list[SecretLogFinding]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError as exc:
        shown = display_path or path
        return [SecretLogFinding(shown, exc.lineno or 1, "parse", "syntax error during scan")]

    findings: list[SecretLogFinding] = []
    shown = display_path or path
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        call_name = _call_name(node.func)
        if call_name is None:
            continue
        checked_nodes = [*node.args, *(keyword.value for keyword in node.keywords)]
        if any(_node_has_sensitive_value(item) for item in checked_nodes):
            findings.append(
                SecretLogFinding(
                    shown,
                    int(getattr(node, "lineno", 1)),
                    call_name,
                    "potential raw secret/token logging",
                )
            )
    return findings


def iter_python_files(root: Path) -> list[Path]:
    if root.is_file():
        return [root] if root.suffix == ".py" else []
    return sorted(
        path
        for path in root.rglob("*.py")
        if "__pycache__" not in path.parts and ".venv" not in path.parts
    )


def scan_roots(roots: list[Path]) -> list[SecretLogFinding]:
    findings: list[SecretLogFinding] = []
    cwd = Path.cwd().resolve()
    for root in roots:
        for path in iter_python_files(root):
            try:
                display = path.resolve().relative_to(cwd)
            except ValueError:
                display = path
            findings.extend(scan_file(path, display_path=display))
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("roots", nargs="*", type=Path, default=[Path(item) for item in DEFAULT_SCAN_ROOTS])
    args = parser.parse_args()

    findings = scan_roots(args.roots)
    if findings:
        print("FAIL secret leak scan")
        for finding in findings:
            print(finding.format())
        return 1
    print("PASS secret leak scan")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
