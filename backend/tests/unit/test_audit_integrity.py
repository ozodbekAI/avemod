from __future__ import annotations

from scripts.improve_backend_audit_integrity import (
    apply_integrity_caps,
    normalize_reasons,
    readiness_summary,
)


GENERIC_REASON = "Evidence did not prove every production/live dependency and RBAC negative path at 100%."


def test_normalize_reasons_replaces_generic_scorecard_text() -> None:
    scores = [
        {
            "area": "Backend runtime",
            "score": 92,
            "why_not_100": [GENERIC_REASON],
        },
        {
            "area": "Tests",
            "score": 100,
            "why_not_100": ["old"],
        },
    ]

    normalize_reasons(scores)

    assert scores[0]["why_not_100"] == [
        "Runtime evidence is local, not staging; staging BASE_URL audit is required for 100."
    ]
    assert scores[1]["why_not_100"] == []


def test_integrity_caps_tests_when_full_pytest_failed() -> None:
    scores = [
        {"area": "Tests", "score": 95, "why_not_100": [], "evidence": [], "required_to_100": [], "priority": "P2"},
        {
            "area": "Public MVP readiness",
            "score": 90,
            "why_not_100": [],
            "evidence": [],
            "required_to_100": [],
            "priority": "P2",
        },
    ]

    blockers = apply_integrity_caps(
        scores,
        {
            "pytest_full_rc": 1,
            "raw_token_logging": False,
            "rbac_passed": True,
            "staging_runtime_status": "PASS",
        },
    )

    tests = next(item for item in scores if item["area"] == "Tests")
    assert tests["score"] == 60
    assert tests["priority"] == "P0"
    assert "Full pytest failed" in blockers[0]


def test_integrity_caps_public_readiness_when_rbac_or_staging_missing() -> None:
    scores = [
        {
            "area": "RBAC/account access",
            "score": 95,
            "why_not_100": [],
            "evidence": [],
            "required_to_100": [],
            "priority": "P2",
        },
        {
            "area": "Deploy readiness",
            "score": 80,
            "why_not_100": [],
            "evidence": [],
            "required_to_100": [],
            "priority": "P1",
        },
        {
            "area": "Public MVP readiness",
            "score": 92,
            "why_not_100": [],
            "evidence": [],
            "required_to_100": [],
            "priority": "P2",
        },
    ]

    blockers = apply_integrity_caps(
        scores,
        {
            "pytest_full_rc": 0,
            "raw_token_logging": False,
            "rbac_passed": False,
            "staging_runtime_status": "SKIPPED_MISSING_ENV",
        },
    )

    rbac = next(item for item in scores if item["area"] == "RBAC/account access")
    public = next(item for item in scores if item["area"] == "Public MVP readiness")
    assert rbac["score"] == 70
    assert public["score"] == 75
    assert any("Seller RBAC negative proof" in blocker for blocker in blockers)
    assert any("Staging runtime evidence is missing" in blocker for blocker in blockers)


def test_readiness_summary_blocks_public_launch_without_staging() -> None:
    readiness = readiness_summary(
        [{"area": "Deploy readiness", "score": 80}],
        {
            "pytest_full_rc": 0,
            "raw_token_logging": False,
            "rbac_passed": True,
            "deploy_safety_pass": True,
            "staging_runtime_status": "SKIPPED_MISSING_ENV",
        },
        ["Staging runtime evidence is missing; public launch readiness is capped."],
    )

    assert readiness["demo_readiness"]["status"] == "READY"
    assert readiness["controlled_pilot_readiness"]["status"] == "CONDITIONAL_READY"
    assert readiness["public_launch_readiness"]["status"] == "BLOCKED"
