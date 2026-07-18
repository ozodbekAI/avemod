from __future__ import annotations

import json
from pathlib import Path


REPO = Path(__file__).resolve().parents[3]
FRONTEND = REPO / "frontend"
BACKEND = REPO / "backend"
DOCS = REPO / "docs"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_frontend_problem_loop_acceptance_script_is_wired() -> None:
    package = json.loads((FRONTEND / "package.json").read_text(encoding="utf-8"))
    script = _read(FRONTEND / "scripts" / "check-problem-loop-acceptance.mjs")
    fixture_manifest = _read(
        FRONTEND
        / "src"
        / "product-acceptance"
        / "problem-loop.acceptance.fixtures.ts"
    )

    assert package["scripts"]["test:problem-loop"] == (
        "node scripts/check-problem-loop-acceptance.mjs"
    )
    for scenario in (
        "actionCenterDynamicProblemDrawer",
        "productDoctorGroupedIssue",
        "dataFixLinkedIssue",
        "evidenceDrawerSellerMode",
        "estimatedVsConfirmedMoneyStyling",
        "adminRuleBuilderNoCode",
    ):
        assert scenario in script
        assert scenario in fixture_manifest

    for loop_step in (
        "Проблема",
        "доказательства",
        "действие",
        "статус",
        "повторная проверка",
        "результат",
    ):
        assert loop_step in fixture_manifest


def test_backend_problem_loop_contracts_back_the_acceptance_surfaces() -> None:
    result_tracking = _read(BACKEND / "app" / "services" / "result_tracking.py")
    checker_bridge = _read(BACKEND / "app" / "services" / "checker_problem_bridge.py")
    portal = _read(BACKEND / "app" / "services" / "portal.py")

    for token in (
        "ensure_problem_before_snapshot",
        "create_problem_status_event",
        "create_problem_completed_event",
        "create_problem_recheck_event",
        "problem_instance_id",
        "problem_code",
        'source_module="problem_engine"',
        "saved_money_claimed",
        "correlation only",
    ):
        assert token in result_tracking

    for token in (
        "checker_problem_bridge",
        "problem_ux_contract",
        "content_quality_signal",
        '"trust_state": semantics["trust_state"]',
        '"impact_type": semantics["impact_type"]',
        "не подтверждённый финансовый убыток",
        "recheck_rule_human",
    ):
        assert token in checker_bridge

    for token in (
        "build_checker_problem_bridge",
        "source_module",
        "problem_engine",
        "checker",
        "evidence_ledger",
    ):
        assert token in portal


def test_final_product_problem_loop_qa_is_documented_and_covered() -> None:
    qa_doc = _read(DOCS / "final_product_problem_loop_qa.md")
    e2e = _read(FRONTEND / "e2e" / "action-center-professional.spec.ts")
    mock_api = _read(FRONTEND / "e2e" / "mock-api.ts")

    for step in (
        "Evaluate a dynamic problem",
        "Open Action Center",
        "Open evidence",
        "Open the task drawer",
        "Assign an owner",
        "Set a deadline",
        "Change status to `В работе`",
        "Click `Перепроверить`",
        "Mark the task `Выполнено`",
        "Open Product360",
        "Open Results from Action Center",
        "Open Data Fix",
    ):
        assert step in qa_doc

    for screenshot in (
        "action-center-task-drawer",
        "results-problem-timeline",
        "product360-problem-preview",
    ):
        assert screenshot in qa_doc
        assert screenshot in e2e

    for token in (
        "same dynamic problem is traceable through Action Center, Product360 and Results",
        "problem_instance_id=42",
        "Открыть в результатах",
        "Открыть задачу",
        "Открыть исправление данных",
    ):
        assert token in e2e

    for token in (
        "business_issues",
        "result_history",
        "before_snapshot",
        "action_completed",
        "recheck_result",
        "saved_money_claimed: false",
    ):
        assert token in mock_api
