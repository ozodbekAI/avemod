from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.control_tower import ControlTowerService
from app.services.trust import (
    COST_TRUST_POLICY_OWNER_APPROVED_FINAL,
    COST_TRUST_POLICY_OPERATOR_BASELINE,
    COST_TRUST_POLICY_SUPPLIER_ONLY,
    COST_TRUTH_OPERATOR_BASELINE,
    COST_TRUTH_PLACEHOLDER,
    COST_TRUTH_SUPPLIER_CONFIRMED,
    TRUST_STATE_DATA_BLOCKED,
    TRUST_STATE_FINANCIAL_FINAL,
    TRUST_STATE_OPERATIONAL_PROVISIONAL,
    TRUST_STATE_TEST_ONLY,
    TRUST_STATE_TRUSTED,
    build_cost_coverage_decision,
    build_global_trust_decision,
    build_public_trust_snapshot,
    core_sku_cost_trust_snapshot,
    cost_truth_level_from_cost,
    trust_state_for_row,
)


def test_cost_truth_level_detects_supplier_confirmed_manual_cost() -> None:
    cost = SimpleNamespace(
        supplier="Trusted Supplier",
        cost_source="supplier_confirmed",
        cost_price=125,
        unit_cost=125,
        is_placeholder=False,
        is_supplier_confirmed=True,
    )

    assert cost_truth_level_from_cost(cost) == COST_TRUTH_SUPPLIER_CONFIRMED


def test_cost_truth_level_does_not_treat_generic_manual_upload_as_supplier_confirmed() -> None:
    cost = SimpleNamespace(
        supplier="Trusted Supplier",
        cost_source="manual_upload",
        cost_price=125,
        unit_cost=125,
        is_placeholder=False,
        is_supplier_confirmed=False,
        is_business_trusted=False,
    )

    assert cost_truth_level_from_cost(cost) == "manual_untrusted"


def test_cost_truth_level_detects_operator_baseline_and_placeholder() -> None:
    operator_cost = SimpleNamespace(
        supplier="OPERATOR_TRUSTED_COST",
        cost_source="operator_trusted_manual",
        cost_price=90,
        unit_cost=90,
        is_placeholder=False,
    )
    placeholder_cost = SimpleNamespace(
        supplier="AUTO_TEMPLATE",
        cost_source="placeholder_auto_template",
        cost_price=90,
        unit_cost=90,
        is_placeholder=True,
    )

    assert cost_truth_level_from_cost(operator_cost) == COST_TRUTH_OPERATOR_BASELINE
    assert cost_truth_level_from_cost(placeholder_cost) == COST_TRUTH_PLACEHOLDER


def test_trust_state_for_row_keeps_supplier_baseline_as_test_only() -> None:
    assert (
        trust_state_for_row(
            has_manual_cost=True,
            has_real_manual_cost=False,
            blocked_reasons=["supplier_cost_not_confirmed"],
        )
        == TRUST_STATE_TEST_ONLY
    )


def test_trust_state_for_row_marks_real_blockers_as_data_blocked() -> None:
    assert (
        trust_state_for_row(
            has_manual_cost=True,
            has_real_manual_cost=False,
            blocked_reasons=["missing_chrt_id"],
        )
        == TRUST_STATE_DATA_BLOCKED
    )


def test_global_trust_decision_opens_only_when_all_gates_are_green() -> None:
    green = build_global_trust_decision(
        supplier_confirmed_revenue_coverage_percent=98.0,
        failed_domains=[],
        unresolved_unmatched_sku_count=0,
        latest_stocks_status="completed",
        blocking_open_issue_count=0,
        article_audit_consistent=True,
        scheduler_stable=True,
    )
    blocked = build_global_trust_decision(
        supplier_confirmed_revenue_coverage_percent=60.0,
        failed_domains=[],
        unresolved_unmatched_sku_count=0,
        latest_stocks_status="completed",
        blocking_open_issue_count=0,
        article_audit_consistent=True,
        scheduler_stable=True,
    )

    assert green.trust_state == TRUST_STATE_TRUSTED
    assert green.can_generate_business_actions is True
    assert blocked.trust_state == TRUST_STATE_TEST_ONLY
    assert blocked.can_generate_business_actions is True
    assert "supplier_cost_coverage_below_threshold" in blocked.blocked_reasons


def test_global_trust_decision_keeps_article_mismatch_as_test_only() -> None:
    decision = build_global_trust_decision(
        supplier_confirmed_revenue_coverage_percent=98.0,
        failed_domains=[],
        unresolved_unmatched_sku_count=0,
        latest_stocks_status="completed",
        blocking_open_issue_count=0,
        article_audit_consistent=False,
        scheduler_stable=True,
    )

    assert decision.trust_state == TRUST_STATE_TEST_ONLY
    assert decision.can_generate_business_actions is True
    assert "article_audit_mismatch" in decision.blocked_reasons


def test_cost_coverage_decision_counts_operator_baseline_for_operations_but_not_supplier_confirmed() -> None:
    decision = build_cost_coverage_decision(
        total_revenue=1000,
        supplier_confirmed_revenue=0,
        operator_baseline_revenue=996,
        missing_cost_revenue=4,
        cost_trust_policy=COST_TRUST_POLICY_OPERATOR_BASELINE,
    )

    assert decision.operational_cost_coverage_percent == pytest.approx(99.6)
    assert decision.supplier_confirmed_cost_coverage_percent == 0.0
    assert decision.business_accepted_cost_coverage_percent == pytest.approx(99.6)
    assert decision.can_use_for_operations is True
    assert decision.can_use_for_final_profit is False


def test_cost_coverage_decision_supplier_confirmed_revenue_increases_final_coverage() -> None:
    decision = build_cost_coverage_decision(
        total_revenue=1000,
        supplier_confirmed_revenue=820,
        operator_baseline_revenue=176,
        missing_cost_revenue=4,
        cost_trust_policy=COST_TRUST_POLICY_OPERATOR_BASELINE,
    )

    assert decision.supplier_confirmed_cost_coverage_percent == pytest.approx(82.0)
    assert decision.business_accepted_cost_coverage_percent == pytest.approx(99.6)
    assert decision.cost_truth_level == "mixed"


def test_cost_coverage_decision_supplier_only_policy_blocks_operator_baseline_for_operations() -> None:
    decision = build_cost_coverage_decision(
        total_revenue=1000,
        supplier_confirmed_revenue=0,
        operator_baseline_revenue=996,
        missing_cost_revenue=4,
        cost_trust_policy=COST_TRUST_POLICY_SUPPLIER_ONLY,
    )

    assert decision.operational_cost_coverage_percent == 0.0
    assert decision.business_accepted_cost_coverage_percent == 0.0
    assert decision.can_use_for_operations is False
    assert decision.can_use_for_final_profit is False


def test_cost_coverage_decision_owner_approved_policy_allows_temporary_final_profit() -> None:
    decision = build_cost_coverage_decision(
        total_revenue=1000,
        supplier_confirmed_revenue=0,
        operator_baseline_revenue=996,
        missing_cost_revenue=4,
        cost_trust_policy=COST_TRUST_POLICY_OWNER_APPROVED_FINAL,
    )

    assert decision.operational_cost_coverage_percent == pytest.approx(99.6)
    assert decision.business_accepted_cost_coverage_percent == pytest.approx(99.6)
    assert decision.can_use_for_operations is True
    assert decision.can_use_for_final_profit is True


def test_control_tower_classification_blocks_untrusted_rows() -> None:
    service = ControlTowerService()

    assert (
        service._classify_sku_status(
            trust_state=TRUST_STATE_DATA_BLOCKED,
            profit=None,
            days_of_stock=None,
            ad_spend=0,
            safe_price_gap=None,
            overstock_threshold_days=90,
            finance_rows=0,
            net_units=0,
        )
        == "DATA_BLOCKED"
    )


def test_core_sku_cost_trust_snapshot_marks_supplier_confirmed_rows_as_final() -> None:
    snapshot = core_sku_cost_trust_snapshot(
        SimpleNamespace(
            supplier="Real Supplier",
            cost_source="supplier_confirmed",
            is_placeholder=False,
            is_business_trusted=True,
            is_ambiguous=False,
        )
    )

    assert snapshot["cost_truth_level"] == "supplier_confirmed"
    assert snapshot["has_real_manual_cost"] is True
    assert snapshot["operational_trusted"] is True


def test_core_sku_cost_trust_snapshot_marks_operator_baseline_without_supplier_confirmation() -> None:
    snapshot = core_sku_cost_trust_snapshot(
        SimpleNamespace(
            supplier="OPERATOR_TRUSTED_COST",
            cost_source="operator_baseline",
            is_placeholder=False,
            is_business_trusted=True,
            is_ambiguous=False,
        )
    )

    assert snapshot["cost_truth_level"] == "operator_baseline"
    assert snapshot["has_real_manual_cost"] is False
    assert snapshot["business_trusted"] is True


def test_core_sku_cost_trust_snapshot_marks_placeholder_and_missing_rows() -> None:
    placeholder = core_sku_cost_trust_snapshot(
        SimpleNamespace(
            supplier="AUTO_TEMPLATE",
            cost_source="placeholder_auto_template",
            is_placeholder=True,
            is_business_trusted=False,
            is_ambiguous=False,
        )
    )
    missing = core_sku_cost_trust_snapshot(None)

    assert placeholder["cost_truth_level"] == "placeholder"
    assert placeholder["business_trusted"] is False
    assert missing["cost_truth_level"] == "missing"
    assert missing["operational_trusted"] is False


def test_public_trust_snapshot_distinguishes_operational_and_financial_final() -> None:
    provisional = build_public_trust_snapshot(
        operational_trusted=True,
        supplier_confirmed_revenue_coverage_percent=0.0,
        operator_baseline_revenue_coverage_percent=99.6,
        trusted_revenue_cost_coverage_percent=99.6,
        financial_final_blockers_total=2,
        cost_trust_policy="operator_baseline",
        finance_reconciliation_clean=False,
    )
    final = build_public_trust_snapshot(
        operational_trusted=True,
        supplier_confirmed_revenue_coverage_percent=95.0,
        operator_baseline_revenue_coverage_percent=0.0,
        trusted_revenue_cost_coverage_percent=95.0,
        financial_final_blockers_total=0,
        cost_trust_policy="supplier_only",
        finance_reconciliation_clean=True,
    )

    assert provisional.trust_state == TRUST_STATE_OPERATIONAL_PROVISIONAL
    assert provisional.financial_final is False
    assert final.trust_state == TRUST_STATE_FINANCIAL_FINAL
    assert final.financial_final is True


def test_public_trust_snapshot_owner_override_hides_temporary_blockers() -> None:
    snapshot = build_public_trust_snapshot(
        operational_trusted=True,
        supplier_confirmed_revenue_coverage_percent=0.0,
        operator_baseline_revenue_coverage_percent=99.6,
        trusted_revenue_cost_coverage_percent=99.6,
        financial_final_blockers_total=12,
        cost_trust_policy=COST_TRUST_POLICY_OWNER_APPROVED_FINAL,
        finance_reconciliation_clean=False,
        blocked_reasons=["open_blocking_dq_issues", "unmatched_sku_detected"],
        all_open_issues_total=100,
        blocking_open_issues_total=12,
    )

    assert snapshot.trust_state == TRUST_STATE_FINANCIAL_FINAL
    assert snapshot.financial_final is True
    assert snapshot.financial_final_blockers_total == 0
    assert snapshot.blocking_open_issues_total == 0


def test_global_trust_decision_owner_override_accepts_current_snapshot() -> None:
    decision = build_global_trust_decision(
        supplier_confirmed_revenue_coverage_percent=0.0,
        trusted_revenue_cost_coverage_percent=99.6,
        cost_trust_policy=COST_TRUST_POLICY_OWNER_APPROVED_FINAL,
        failed_domains=["stocks"],
        unresolved_unmatched_sku_count=5,
        latest_stocks_status="failed",
        blocking_open_issue_count=12,
        article_audit_consistent=False,
        scheduler_stable=False,
    )

    assert decision.trust_state == TRUST_STATE_TRUSTED
    assert decision.business_trusted is True
    assert decision.can_generate_business_actions is True
    assert decision.blocked_reasons == []
