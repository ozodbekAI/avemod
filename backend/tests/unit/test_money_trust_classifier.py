from app.schemas.card_quality import CardQualityIssueRead
from app.schemas.money_management import DataBlockerRead, NextActionRead, TopCardPreview
from app.schemas.money_trust import classify_money_trust
from app.schemas.portal import PortalActionRead


def test_finance_confirmed_loss_is_the_only_confirmed_loss_label() -> None:
    trust = classify_money_trust(
        value=-1250,
        value_type="money",
        confidence="confirmed",
        impact_type="confirmed_loss",
        financial_final=True,
        source_module="finance",
        source_table="realization_report_rows",
        source_endpoint="GET /api/v1/money/summary",
    )

    assert trust.state == "confirmed"
    assert trust.impact_kind == "confirmed_loss"
    assert trust.amount_label == "Подтверждённый убыток"
    assert trust.show_as_confirmed_money is True
    assert trust.evidence_trust_state == "confirmed"
    assert trust.impact_trust_state == "confirmed"
    assert trust.saved_money_claimed is False


def test_low_stock_risk_keeps_confirmed_evidence_separate_from_impact_trust() -> None:
    trust = classify_money_trust(
        value=12500,
        value_type="money",
        confidence="confirmed",
        impact_type="lost_sales_risk",
        trust_state="confirmed",
        source_module="problem_engine",
        source_table="mart_stock_daily",
        source_endpoint="GET /api/v1/marts/stock-daily",
        action_type="low_stock_risk",
    )

    assert trust.state in {"provisional", "estimated"}
    assert trust.impact_kind == "lost_sales_risk"
    assert trust.display_label == "Риск потери продаж"
    assert trust.amount_label == "Риск потери продаж"
    assert trust.evidence_trust_state == "confirmed"
    assert trust.impact_trust_state in {"provisional", "estimated"}
    assert trust.show_as_confirmed_money is False
    assert trust.saved_money_claimed is False


def test_portal_action_freshness_downgrades_stale_low_stock_evidence_and_impact() -> None:
    action = PortalActionRead(
        id="problem_engine:42",
        source="dynamic_problem_instances",
        source_module="problem_engine",
        source_id="42",
        account_id=1,
        action_type="low_stock_risk",
        detector_code="low_stock_risk",
        title="Риск потери продаж по товару",
        priority="P1",
        severity="high",
        status="new",
        expected_impact_amount=12500,
        impact_type="confirmed_loss",
        trust_state="confirmed",
        evidence_state="full_evidence",
        data_freshness={
            "required_sources": ["stocks", "sales"],
            "source_status": "stale",
            "last_synced_at": "2026-06-20T08:00:00Z",
            "blocking_sources": ["stocks"],
            "freshness_notes": ["Остатки требуют синхронизации."],
        },
        evidence_ledger={
            "formula_human": "stock_days_left < 3",
            "confidence": "confirmed",
            "impact_type": "confirmed_loss",
            "input_facts": [
                {
                    "label": "Остаток",
                    "metric_code": "stock_qty",
                    "value": 4,
                    "trust_state": "confirmed",
                    "source_table": "mart_stock_daily",
                    "source_endpoint": "GET /api/v1/marts/stock-daily",
                    "row_count": 7,
                }
            ],
            "source_references": [
                {
                    "source_table": "mart_stock_daily",
                    "source_endpoint": "GET /api/v1/marts/stock-daily",
                    "row_count": 7,
                }
            ],
            "money_trust": {
                "state": "confirmed",
                "impact_kind": "confirmed_loss",
                "display_label": "Подтверждённый убыток",
                "amount_label": "Подтверждённый убыток",
                "show_as_confirmed_money": True,
                "evidence_trust_state": "confirmed",
                "impact_trust_state": "confirmed",
                "saved_money_claimed": False,
            },
        },
        can_update=True,
    )

    assert action.data_freshness is not None
    assert action.data_freshness.source_status == "stale"
    assert action.evidence_state == "partial_evidence"
    assert action.impact_type == "lost_sales_risk"
    assert action.trust_state in {"provisional", "estimated"}
    assert action.money_trust is not None
    assert action.money_trust.impact_kind == "lost_sales_risk"
    assert action.money_trust.impact_trust_state != "confirmed"
    assert action.money_trust.show_as_confirmed_money is False
    assert action.money_trust.saved_money_claimed is False
    assert action.payload["evidence_state"] == "partial_evidence"
    assert action.payload["data_freshness"]["source_status"] == "stale"


def test_portal_action_calculation_warnings_do_not_create_sync_blockers() -> None:
    action = PortalActionRead(
        id="problem_engine:24",
        source="dynamic_problem_instances",
        source_module="problem_engine",
        source_id="24",
        account_id=1,
        nm_id=205560671,
        action_type="negative_unit_profit",
        detector_code="negative_unit_profit",
        title="Товар 205560671 продаётся в минус",
        priority="P1",
        severity="high",
        status="new",
        expected_impact_amount=-1515,
        impact_type="probable_risk",
        trust_state="estimated",
        payload={
            "price_safety": {
                "status": "price_ok",
                "missing_required_metrics": [],
                "current_price": 7900,
                "price_after_discount": 4740,
            },
        },
        evidence_ledger={
            "calculation_warnings": ["price_safety_checked"],
            "missing_data": [],
        },
        source_references=[
            {
                "source_table": "wb_price_sizes",
                "source_endpoint": "GET /api/v1/prices",
                "row_count": 8,
            }
        ],
        can_update=True,
    )

    assert action.data_freshness is not None
    assert "prices" in action.data_freshness.required_sources
    assert action.data_freshness.source_status == "fresh"
    assert action.data_freshness.blocking_sources == []


def test_card_quality_finance_word_in_warning_does_not_create_sync_blocker() -> None:
    action = PortalActionRead(
        id="card_quality:173",
        source="card_quality_issues",
        source_module="checker",
        source_id="173",
        account_id=1,
        nm_id=12476203,
        action_type="CARD_QUALITY_FIX",
        detector_code="title_missing",
        title="Название карточки отсутствует",
        priority="P2",
        severity="medium",
        status="new",
        impact_type="opportunity",
        trust_state="opportunity",
        evidence_ledger={
            "calculation_warnings": [
                "Это возможность улучшения контента, а не подтверждённая финансовая потеря."
            ],
            "missing_data": [],
            "source_references": [
                {
                    "source": "card_quality_issues",
                    "source_module": "checker",
                    "row_count": 1,
                }
            ],
        },
        can_update=True,
    )

    assert action.data_freshness is not None
    assert action.data_freshness.source_status == "fresh"
    assert action.data_freshness.blocking_sources == []


def test_overstock_defaults_to_blocked_cash_not_confirmed_loss() -> None:
    trust = classify_money_trust(
        value=5600,
        value_type="money",
        confidence="confirmed",
        impact_type="blocked_cash",
        trust_state="confirmed",
        source_module="problem_engine",
        source_table="mart_stock_daily",
        source_endpoint="GET /api/v1/marts/stock-daily",
        action_type="overstock_slow_moving",
    )

    assert trust.state == "estimated"
    assert trust.impact_kind == "blocked_cash"
    assert trust.display_label == "Замороженные деньги"
    assert trust.show_as_confirmed_money is False
    assert trust.saved_money_claimed is False


def test_data_fix_revenue_only_blocker_is_blocked_revenue_not_loss() -> None:
    blocker = DataBlockerRead(
        code="missing_manual_cost",
        priority="critical",
        title="Нет себестоимости",
        affected_sku_count=7,
        affected_amount=0,
        affected_revenue=28_606,
        business_impact="Финальная прибыль заблокирована без себестоимости.",
    )

    assert blocker.money_trust is not None
    assert blocker.money_trust.state == "blocked"
    assert blocker.money_trust.impact_kind == "blocked_revenue"
    assert "выручка" in blocker.money_trust.amount_label.lower()
    assert blocker.money_trust.show_as_confirmed_money is False
    assert blocker.evidence_ledger is not None
    assert blocker.evidence_ledger.money_trust == blocker.money_trust


def test_checker_issue_is_estimated_opportunity_never_confirmed_loss() -> None:
    issue = CardQualityIssueRead(
        id=1,
        account_id=10,
        nm_id=123456,
        issue_code="title_too_short",
        category="content",
        severity="medium",
        title="Название можно усилить",
        score_impact=12,
        status="new",
        fingerprint="title_too_short:123456",
    )

    assert issue.money_trust is not None
    assert issue.money_trust.state == "opportunity"
    assert issue.money_trust.impact_kind == "estimated_opportunity"
    assert issue.money_trust.show_as_confirmed_money is False
    assert issue.evidence_ledger is not None
    assert issue.evidence_ledger.money_trust == issue.money_trust


def test_checker_financial_evidence_must_be_explicit_before_confirmed_loss() -> None:
    trust = classify_money_trust(
        value=1500,
        value_type="money",
        confidence="confirmed",
        trust_state="confirmed",
        impact_type="confirmed_loss",
        financial_final=True,
        source_module="checker",
        source_table="card_quality_issues",
        source_endpoint="GET /api/v1/portal/card-quality/issues",
        action_type="description_with_confirmed_finance_evidence",
    )

    assert trust.state == "confirmed"
    assert trust.impact_kind == "confirmed_loss"
    assert trust.show_as_confirmed_money is True


def test_test_only_portal_action_is_hidden_from_default_seller_view() -> None:
    action = PortalActionRead(
        id="beta-1",
        source="action_recommendations",
        source_module="grouping_beta",
        source_id="1",
        action_type="MERGE_CANDIDATE",
        title="Тестовая рекомендация",
        expected_effect_amount=5000,
        payload={"trust_state": "test_only", "runtime_mode": "test"},
    )

    assert action.money_trust is not None
    assert action.money_trust.state == "test_only"
    assert action.money_trust.seller_visible_by_default is False
    assert action.money_trust.show_as_confirmed_money is False
    assert action.evidence_ledger is not None
    assert action.evidence_ledger.money_trust == action.money_trust


def test_money_actions_and_top_cards_carry_trust_metadata() -> None:
    action = NextActionRead(
        action_type="PAUSE_AD_CAMPAIGN",
        priority="high",
        title="Проверьте рекламу",
        what_to_do="Остановите кампанию до сверки.",
        why="Риск рассчитан до финальной сверки финансов.",
        expected_effect_amount=2400,
        confidence="medium",
        financial_final=False,
    )
    card = TopCardPreview(
        sku_id=11,
        nm_id=22,
        vendor_code="SKU-22",
        title="Товар",
        revenue=10_000,
        net_profit=-1200,
        stock_value=0,
        priority_score=99,
        status="loss_making",
    )

    assert action.money_trust is not None
    assert action.money_trust.state in {"provisional", "opportunity"}
    assert action.money_trust.show_as_confirmed_money is False
    assert card.money_trust is not None
    assert card.money_trust.impact_kind == "probable_loss"
    assert card.money_trust.show_as_confirmed_money is False
    assert card.evidence_ledger is not None
    assert card.evidence_ledger.money_trust == card.money_trust
