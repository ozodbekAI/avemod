#!/usr/bin/env python3
"""Scan frontend source/config files for hardcoded credential-looking literals."""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path


DEFAULT_FRONTEND_ROOT = Path(__file__).resolve().parents[2] / "frontend"
SCAN_SUFFIXES = {".ts", ".tsx", ".js", ".jsx", ".json", ".jsonc", ".env", ".example"}
SKIP_PARTS = {"node_modules", "dist", "playwright-report", "test-results", "audit_bundle"}

SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("jwt", re.compile(r"eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}")),
    ("bearer token", re.compile(r"Bearer\s+[A-Za-z0-9_.-]{24,}", re.IGNORECASE)),
    ("password literal", re.compile(r"(password|пароль)[\"'\s:=]+[A-Za-z0-9!@#$%^&*()_+\-=]{10,}", re.IGNORECASE)),
    ("wb token literal", re.compile(r"(wb[_-]?token|access[_-]?token|refresh[_-]?token|api[_-]?key)[\"'\s:=]+[A-Za-z0-9_.-]{20,}", re.IGNORECASE)),
)

ALLOWLIST_SUBSTRINGS = (
    "e2e-access",
    "e2e-refresh",
    "access_token",
    "refresh_token",
    "token_type",
    "VITE_API_BASE_URL",
)


@dataclass(frozen=True)
class FrontendSecretFinding:
    path: Path
    line: int
    reason: str
    excerpt: str

    def format(self) -> str:
        return f"{self.path}:{self.line}: {self.reason}: {self.excerpt}"


def _skip(path: Path) -> bool:
    return any(part in SKIP_PARTS for part in path.parts)


def iter_files(root: Path) -> list[Path]:
    if root.is_file():
        return [root]
    return sorted(
        path
        for path in root.rglob("*")
        if path.is_file()
        and not _skip(path)
        and (path.suffix in SCAN_SUFFIXES or path.name.startswith(".env"))
    )


def scan_file(path: Path, *, display_path: Path | None = None) -> list[FrontendSecretFinding]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    findings: list[FrontendSecretFinding] = []
    shown = display_path or path
    for line_no, line in enumerate(text.splitlines(), start=1):
        if any(item in line for item in ALLOWLIST_SUBSTRINGS):
            continue
        for reason, pattern in SECRET_PATTERNS:
            if pattern.search(line):
                findings.append(
                    FrontendSecretFinding(
                        shown,
                        line_no,
                        reason,
                        line.strip()[:160],
                    )
                )
    return findings


def scan_roots(roots: list[Path]) -> list[FrontendSecretFinding]:
    findings: list[FrontendSecretFinding] = []
    cwd = Path.cwd().resolve()
    for root in roots:
        for path in iter_files(root):
            try:
                shown = path.resolve().relative_to(cwd)
            except ValueError:
                shown = path
            findings.extend(scan_file(path, display_path=shown))
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("roots", nargs="*", type=Path, default=[DEFAULT_FRONTEND_ROOT])
    args = parser.parse_args()

    findings = scan_roots(args.roots)
    if findings:
        print("FAIL frontend secret literal scan")
        for finding in findings:
            print(finding.format())
        return 1
    print("PASS frontend secret literal scan")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
