from __future__ import annotations

import pytest

from app.services.guided_fixes import GUIDED_FIX_METHODS, GuidedFixMapper


@pytest.mark.parametrize(
    ("source_module", "action_type", "expected_method", "expected_route"),
    [
        ("finance", "review_profit", "open_product_360", "product_360"),
        ("finance", "fix_costs", "upload_costs", "costs"),
        ("finance", "fix_data", "open_data_fix", "data_fix"),
        ("costs", "FIX_COST_TRUST", "upload_costs", "costs"),
        ("data_quality", "DATA_FIX_REQUIRED", "open_data_fix", "data_fix"),
        ("checker", "CARD_QUALITY_FIX", "open_card_quality", "card_quality"),
        ("photo", "PHOTO_IMPROVE", "photo_fix", "photo_studio"),
        ("checker", "photo_fix", "photo_fix", "photo_studio"),
        ("checker", "media_quality_fix", "media_quality_fix", "photo_studio"),
        ("reputation", "negative_review_unanswered", "open_reputation_item", "reputation"),
        ("reputation", "draft_reply", "generate_reputation_draft", "reputation"),
        ("claims", "defect_claim_candidate", "create_claim_case_from_signal", "claims"),
        ("claims", "draft_claim", "generate_claim_draft", "claims"),
        ("claims", "open_case", "open_claim_case", "claims"),
        ("stockops", "stock_recommendation", "open_stock_planner", "stock"),
        ("stockops", "REORDER", "open_stock_planner", "stock"),
        ("grouping", "grouping_review", "open_grouping_preview", "grouping_beta"),
        ("grouping_beta", "GROUPING_RECOMMENDATION", "open_grouping_preview", "grouping_beta"),
        ("finance", "AD_PAUSE_REVIEW", "open_ads_review", "ads"),
        ("finance", "PRICE_INCREASE_REVIEW", "open_pricing_review", "pricing"),
        ("experiments", "result_tracking", "open_result_tracking", "result_history"),
    ],
)
def test_guided_fix_mapper_covers_core_action_types(
    source_module: str,
    action_type: str,
    expected_method: str,
    expected_route: str,
) -> None:
    result = GuidedFixMapper().map(source_module=source_module, action_type=action_type, nm_id=1001, target_id="target")

    assert result["method"] == expected_method
    assert result["type"] == expected_method
    assert result["method"] in GUIDED_FIX_METHODS
    assert result["route_key"] == expected_route
    assert result["route_hint"] == expected_route
    assert result["target_module"] == expected_route
    assert result["enabled"] is True
    assert result["target_id"] == "1001"
    assert result["source_id"] == "target"
    assert result["source_issue_id"] == "target"
    assert result["nm_id"] == 1001
    assert result["label"]
    assert result["steps"][0]["route_key"] == expected_route
    assert result["steps"][0]["route_hint"] == expected_route
    assert result["steps"][0]["target_module"] == expected_route
    assert result["steps"][0]["source_id"] == "target"
    assert result["steps"][0]["source_issue_id"] == "target"
    assert result["marketplace_change"] is False


def test_guided_fix_mapper_marks_unavailable_module_disabled() -> None:
    result = GuidedFixMapper().map(
        source_module="checker",
        action_type="CARD_QUALITY_FIX",
        nm_id=1001,
        module_status="unavailable",
        message="checker is down",
    )

    assert result["method"] == "open_card_quality"
    assert result["enabled"] is False
    assert result["status"] == "unavailable"
    assert result["message"] == "checker is down"
    assert result["disabled_reason"] == "checker_module_unavailable"
    assert result["steps"][0]["marketplace_change"] is False


@pytest.mark.parametrize(
    ("source_module", "action_type"),
    [
        ("checker", "card_quality_fix"),
        ("checker", "photo_fix"),
        ("checker", "media_quality_fix"),
        ("photo", "photo_improve"),
        ("reputation", "draft_reply"),
        ("claims", "draft_claim"),
        ("claims", "open_case"),
        ("stockops", "stock_recommendation"),
        ("grouping", "grouping_review"),
    ],
)
def test_guided_fix_mapper_marks_future_risky_flows_as_confirm_required_without_marketplace_change(
    source_module: str,
    action_type: str,
) -> None:
    result = GuidedFixMapper().map(source_module=source_module, action_type=action_type, target_id="source-1")

    assert result["confirm_required"] is True
    assert result["requires_confirmation"] is True
    assert result["marketplace_change"] is False
    assert result["safety_note"]
    assert result["steps"][0]["confirm_required"] is True
    assert result["steps"][0]["marketplace_change"] is False


def test_guided_fix_mapper_operator_shape_contains_button_data() -> None:
    result = GuidedFixMapper().to_operator(
        source_module="claims",
        action_type="draft_claim",
        title="Generate claim",
        summary="Prepare draft",
        target_id="case-1",
    )

    assert result.confirm_required is True
    assert result.audit_required is True
    assert result.marketplace_change is False
    assert result.safety_note
    assert result.data["method"] == "generate_claim_draft"
    assert result.data["confirm_required"] is True
    assert result.steps[0].data["route_key"] == "claims"
