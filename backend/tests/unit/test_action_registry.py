from __future__ import annotations

from app.core.action_registry import ACTION_REGISTRY, get_action, normalize_action_codes, unknown_action_codes


def test_send_to_wb_is_dangerous_and_requires_confirm_audit() -> None:
    action = ACTION_REGISTRY["send_to_wb"]

    assert action.is_external_write is True
    assert action.is_dangerous is True
    assert action.requires_preview is True
    assert action.requires_confirm is True
    assert action.requires_permission is True
    assert action.requires_audit is True
    assert action.allowed_in_rule_builder is False


def test_update_price_is_dangerous_and_not_directly_allowed_in_rule_builder() -> None:
    action = ACTION_REGISTRY["update_price"]

    assert action.category == "price"
    assert action.is_external_write is True
    assert action.is_dangerous is True
    assert action.allowed_in_rule_builder is False


def test_safe_navigation_actions_are_allowed_for_rule_builder() -> None:
    price = ACTION_REGISTRY["open_price_review"]
    data_fix = ACTION_REGISTRY["open_data_fix"]

    assert price.is_navigation_only is True
    assert price.is_external_write is False
    assert price.allowed_in_rule_builder is True
    assert data_fix.is_navigation_only is True
    assert data_fix.allowed_in_rule_builder is True


def test_classify_expense_is_only_local_data_fix_action() -> None:
    action = ACTION_REGISTRY["classify_expense"]

    assert action.module == "data_fix"
    assert action.category == "data_fix"
    assert action.is_local_only is True
    assert action.is_external_write is False
    assert action.is_dangerous is False
    assert action.allowed_in_rule_builder is True


def test_unknown_action_is_blocked_by_registry_lookup() -> None:
    assert get_action("not_a_real_action") is None
    assert unknown_action_codes(["open_data_fix", "not_a_real_action"]) == ["not_a_real_action"]


def test_legacy_aliases_normalize_to_safe_navigation() -> None:
    assert normalize_action_codes(["review_price", "safe_promo", "pause_ads"], allowed_for_seller=True) == [
        "open_price_review",
        "open_promo_planner",
    ]


def test_finance_reconciliation_has_no_manual_wb_finance_fact_edit_action() -> None:
    forbidden = [
        action
        for action in ACTION_REGISTRY.values()
        if action.module == "finance" and action.is_external_write
    ]

    assert forbidden == []
