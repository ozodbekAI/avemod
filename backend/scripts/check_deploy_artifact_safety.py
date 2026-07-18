"""Check a deploy artifact/context for files that must not ship.

Run this against an unpacked release directory, Docker build context, or any
candidate deploy artifact staging directory. It intentionally does not read file
contents, so it cannot print secrets.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path


BLOCKED_DIR_NAMES = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "_incoming_projects",
    "logs",
    "node_modules",
    "output",
    "reports",
    "secrets",
}

BLOCKED_DATA_DIR_NAMES = {
    "artifacts",
    "exports",
}

SOURCE_TREE_IGNORED_DIR_NAMES = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "_incoming_projects",
    "logs",
    "node_modules",
    "reports",
}

ALLOWED_SOURCE_DIR_PATHS = {
    ("app", "modules", "exports"),
}

BLOCKED_NAME_PREFIXES = (
    "audit-",
    "audit_",
    "audit-bundle",
    "audit_bundle",
    "backend_final_audit",
    "backend_full_audit",
    "final_backend_audit",
    "full_backend_db_audit",
    "full_endpoint_anomaly_audit",
    "live_backend_full_audit",
    "raw-audit",
    "raw_audit",
    "run_output",
)

BLOCKED_SUFFIXES = (
    ".db",
    ".db-journal",
    ".db-shm",
    ".db-wal",
    ".har",
    ".key",
    ".log",
    ".out",
    ".pem",
    ".p12",
    ".pfx",
    ".sqlite",
    ".sqlite-journal",
    ".sqlite-shm",
    ".sqlite-wal",
    ".sqlite3",
    ".sqlite3-journal",
    ".sqlite3-shm",
    ".sqlite3-wal",
    ".tmp",
    ".trace",
    ".xls",
    ".xlsx",
    ".zip",
)

CSV_EXPORT_NAME_TOKENS = (
    "audit",
    "bundle",
    "export",
    "exports",
    "live_backend",
    "manual_costs_account",
)


def deploy_safety_reason(path: Path) -> str | None:
    """Return a reason when a relative artifact path is unsafe to deploy."""

    parts = [part for part in path.parts if part not in {"", "."}]
    source_export_path = _is_allowed_source_path(parts)
    for index, part in enumerate(parts):
        if part in BLOCKED_DIR_NAMES:
            return f"blocked directory: {part}"
        if part in BLOCKED_DATA_DIR_NAMES and not source_export_path:
            return f"blocked data directory: {part}"
        if part.endswith("_extracted"):
            return f"extracted source/archive path: {part}"
        if part == "source" and any(_looks_like_audit_or_report_part(parent) for parent in parts[:index]):
            return "raw audit source snapshot"
        if part.startswith(BLOCKED_NAME_PREFIXES) and not _is_allowed_audit_tool_source(parts, index):
            return f"raw audit bundle/path: {part}"

    name = path.name.lower()
    for suffix in BLOCKED_SUFFIXES:
        if name.endswith(suffix):
            return f"blocked file suffix: {suffix}"
    if name.endswith(".csv") and _csv_looks_like_export(name):
        return "blocked export/audit csv"
    return None


def _is_allowed_source_path(parts: list[str]) -> bool:
    for allowed in ALLOWED_SOURCE_DIR_PATHS:
        if tuple(parts[: len(allowed)]) == allowed:
            return True
    return False


def _is_allowed_audit_tool_source(parts: list[str], index: int) -> bool:
    """Allow source audit scripts while still blocking generated audit outputs."""

    if index != len(parts) - 1:
        return False
    return len(parts) == 2 and parts[0] == "scripts" and parts[-1].endswith(".py")


def _looks_like_audit_or_report_part(part: str) -> bool:
    return part == "reports" or part.startswith(BLOCKED_NAME_PREFIXES)


def _csv_looks_like_export(name: str) -> bool:
    if "template" in name:
        return False
    return any(token in name for token in CSV_EXPORT_NAME_TOKENS)


def find_suspicious_paths(root: Path, *, source_tree: bool = False) -> list[tuple[Path, str]]:
    """List suspicious paths below root without reading file contents."""

    root = root.resolve()
    findings: list[tuple[Path, str]] = []
    for dirpath, dirnames, filenames in os.walk(root):
        current = Path(dirpath)
        rel_current = current.relative_to(root)
        kept_dirs: list[str] = []
        for dirname in sorted(dirnames):
            rel_dir = rel_current / dirname
            if source_tree and _is_source_tree_ignored_dir(rel_dir):
                continue
            reason = deploy_safety_reason(rel_dir)
            if reason:
                findings.append((rel_dir, reason))
            else:
                kept_dirs.append(dirname)
        dirnames[:] = kept_dirs

        for filename in sorted(filenames):
            rel_file = rel_current / filename
            reason = deploy_safety_reason(rel_file)
            if reason:
                findings.append((rel_file, reason))
    return findings


def _is_source_tree_ignored_dir(path: Path) -> bool:
    parts = [part for part in path.parts if part not in {"", "."}]
    if not parts:
        return False
    if parts[-1] in SOURCE_TREE_IGNORED_DIR_NAMES:
        return True
    return len(parts) == 1 and parts[0] == "exports"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "root_path",
        nargs="?",
        type=Path,
        help="Unpacked deploy artifact or build context to scan.",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path("."),
        help="Unpacked deploy artifact or build context to scan.",
    )
    parser.add_argument(
        "--max-results",
        type=int,
        default=200,
        help="Maximum findings to print before truncating output.",
    )
    parser.add_argument(
        "--source-tree",
        action="store_true",
        help="Ignore local/cache directories that are explicitly excluded from deploy rsync.",
    )
    args = parser.parse_args()

    root = args.root_path or args.root
    findings = find_suspicious_paths(root, source_tree=args.source_tree)
    if not findings:
        print(f"PASS deploy artifact safety scan: {root}")
        return 0

    print(f"FAIL deploy artifact safety scan: {root}")
    for rel_path, reason in findings[: args.max_results]:
        print(f"{rel_path}: {reason}")
    if len(findings) > args.max_results:
        print(f"... truncated {len(findings) - args.max_results} additional findings")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
