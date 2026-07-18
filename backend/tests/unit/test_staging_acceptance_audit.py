from __future__ import annotations

from pathlib import Path

import scripts.run_staging_acceptance_audit as staging_audit
from scripts.run_staging_acceptance_audit import (
    REQUIRED_ENV,
    missing_required_env,
    path_url,
)


def test_missing_required_env_lists_exact_missing_names() -> None:
    env = {name: "set" for name in REQUIRED_ENV}
    env["SELLER_ACCESS_TOKEN"] = ""
    env.pop("FORBIDDEN_ACCOUNT_ID")

    assert missing_required_env(env) == ["SELLER_ACCESS_TOKEN", "FORBIDDEN_ACCOUNT_ID"]


def test_path_url_accepts_base_url_with_or_without_api_prefix() -> None:
    assert path_url("https://stage.example.com", "/api/v1/health") == "https://stage.example.com/api/v1/health"
    assert path_url("https://stage.example.com/api/v1", "/api/v1/health") == "https://stage.example.com/api/v1/health"
    assert (
        path_url("https://stage.example.com/api/v1", "/api/v1/portal/actions", {"account_id": "42"})
        == "https://stage.example.com/api/v1/portal/actions?account_id=42"
    )


def test_scorecard_missing_env_never_allows_public_launch_or_pilot(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(staging_audit, "OUTPUT_DIR", tmp_path)
    report = staging_audit.scorecard(
        missing=["BASE_URL"],
        runtime=[],
        rbac_pass=False,
        nm_id=None,
        action_patch={"passed": False},
        slow=[],
        security_findings=[],
    )

    assert report["final_verdict"] == "NO_GO_MISSING_ENV"
    assert report["scores"]["Public launch readiness"] <= 70
    assert report["controlled_pilot_allowed"] is False


def test_scorecard_caps_controlled_pilot_when_action_patch_missing(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(staging_audit, "OUTPUT_DIR", tmp_path)
    runtime = [
        {"path": "/api/v1/auth/me", "status_code": 200},
        {"path": "/api/v1/portal/products/123", "status_code": 200},
    ]

    report = staging_audit.scorecard(
        missing=[],
        runtime=runtime,
        rbac_pass=True,
        nm_id="123",
        action_patch={"passed": False},
        slow=[],
        security_findings=[],
    )

    assert report["scores"]["Action PATCH"] == 70
    assert report["scores"]["Controlled pilot readiness"] <= 85
    assert report["controlled_pilot_allowed"] is False
