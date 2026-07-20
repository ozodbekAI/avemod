from __future__ import annotations

import os
from pathlib import Path


def pytest_configure() -> None:
    repo_root = Path(__file__).resolve().parent
    if Path.cwd().resolve() == repo_root:
        os.chdir(repo_root / "backend")
