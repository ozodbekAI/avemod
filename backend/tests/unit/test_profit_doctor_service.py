from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.schemas.operator import DiagnosisType, OperatorModule, TrustState
from app.schemas.portal import PortalModuleHealth, PortalModuleHealthItem, PortalProductQualityRead
from app.services.diagnosis.profit_doctor import ProfitDoctorService


class _FakeSession:
    async def get(self, model, key):
        return SimpleNamespace(id=key, name="Account", external_account_id=None)


class _FakeRegistry:
    async def health(self, *, account=None):
        return PortalModuleHealth(
            finance=PortalModuleHealthItem(module="finance", status="ok", enabled=True, configured=True),
            checker=PortalModuleHealthItem(module="checker", status="not_configured", enabled=True, configured=False),
            stockops=PortalModuleHealthItem(module="stockops", status="not_configured", enabled=True, configured=False),
            grouping=PortalModuleHealthItem(module="grouping", status="disabled", enabled=False, configured=False),
        )


def _money(products, blockers=None, summary=None):
    async def _article_detail(session, *, account_id, nm_id, date_from=None, date_to=None):
        for product in products:
            if product.get("nm_id") == nm_id:
                return product
        raise LookupError("product not found")

    return SimpleNamespace(
        summary=AsyncMock(return_value=summary or {"trust": {"trust_state": "operational"}}),
        articles=AsyncMock(return_value=SimpleNamespace(items=products, total=len(products))),
        article_detail=AsyncMock(side_effect=_article_detail),
        data_blockers=AsyncMock(return_value=blockers or {"overall_state": "ok", "blockers": [], "warnings": []}),
    )


def test_missing_cost_ignores_non_missing_cost_finality_reasons() -> None:
    service = ProfitDoctorService()

    assert service._missing_cost(
        {
            "cost_coverage": {"can_use_for_final_profit": True, "status": "ok"},
            "finality": {
                "profit_final": False,
                "reasons": ["finance_not_confirmed", "supplier_cost_not_confirmed", "missing_cost"],
            },
        }
    ) is False
    assert service._missing_cost(
        {
            "cost_coverage": {
                "can_use_for_final_profit": False,
                "status": "missing",
                "missing_cost_revenue": 0,
            },
            "finality": {"profit_final": False, "reasons": ["missing_cost"]},
        }
    ) is False
    assert service._missing_cost({"finality": {"profit_final": False, "reasons": ["missing_manual_cost"]}}) is True
    assert service._missing_cost(
        {
            "cost_coverage": {
                "can_use_for_final_profit": False,
                "status": "missing",
                "missing_cost_revenue": 100,
            },
            "finality": {"profit_final": False, "reasons": ["missing_cost"]},
        }
    ) is True


@pytest.mark.asyncio
async def test_profit_doctor_builds_finance_only_diagnoses_and_prioritizes_impact() -> None:
    service = ProfitDoctorService(
        money=_money(
            [
                {
                    "nm_id": 101,
                    "sku_id": 1001,
                    "vendor_code": "A-1",
                    "title": "Missing cost top product",
                    "revenue": 150000.0,
                    "estimated_profit": 5000.0,
                    "ads_spend": 1000.0,
                    "stock": {"quantity": 10},
                    "missing_cost": True,
                },
                {
                    "nm_id": 102,
                    "sku_id": 1002,
                    "vendor_code": "B-1",
                    "title": "Loss product",
                    "revenue": 20000.0,
                    "estimated_profit": -2500.0,
                    "ads_spend": 9000.0,
                    "stock": {"quantity": 12},
                },
            ],
            blockers={
                "overall_state": "blocked",
                "blockers": [
                    {
                        "code": "missing_manual_cost",
                        "affectedRevenue": 150000.0,
                        "title": "Missing manual cost",
                    }
                ],
                "warnings": [],
            },
        ),
        checker=SimpleNamespace(product_quality=AsyncMock(return_value=PortalProductQualityRead(status="not_configured", nm_id=101))),
        module_registry=_FakeRegistry(),
    )

    result = await service.diagnose(_FakeSession(), account_id=1)

    assert result.status == "ok"
    assert result.trust_state == TrustState.BLOCKED
    assert result.business_status == "blocked"
    assert result.headline == "Сначала разблокируйте данные по прибыли"
    assert result.critical_count >= 3
    assert result.money_at_risk_amount is not None
    assert result.top_sections["profit_leaks"]["count"] >= 3
    assert result.top_sections["data_blockers"]["count"] >= 1
    assert result.today_plan_summary.startswith("Сегодня:")
    assert result.data["money_at_risk"]["is_estimated"] is True
    assert "Оценка" in result.data["money_at_risk"]["label"]
    assert "Legacy-диагностика прибыли нашла" in result.summary
    assert result.total_signals >= 3
    assert result.total_diagnoses >= 3
    assert result.estimated_impact_amount is not None
    assert result.today_plan[0].priority == "P0"
    assert any(item.diagnosis_type == DiagnosisType.COST_MISSING for item in result.diagnoses)
    assert any(item.diagnosis_type == DiagnosisType.PROFIT_LEAK for item in result.diagnoses)
    assert any(item.diagnosis_type == DiagnosisType.ADS_EATING_PROFIT for item in result.diagnoses)
    assert result.unavailable_sources == ["checker", "reputation", "claims"]


@pytest.mark.asyncio
async def test_profit_doctor_recommends_tracking_high_revenue_changes_as_experiment() -> None:
    service = ProfitDoctorService(
        money=_money(
            [
                {
                    "nm_id": 777,
                    "sku_id": 7001,
                    "vendor_code": "EXP-1",
                    "title": "High revenue product",
                    "revenue": 150000.0,
                    "estimated_profit": 20000.0,
                    "ads_spend": 1000.0,
                    "stock": {"quantity": 30},
                }
            ]
        ),
        checker=SimpleNamespace(product_quality=AsyncMock(return_value=PortalProductQualityRead(status="not_configured", nm_id=777))),
        module_registry=_FakeRegistry(),
        reputation_adapter=SimpleNamespace(profit_doctor_signals=AsyncMock(return_value=[])),
        claims_adapter=SimpleNamespace(profit_doctor_signals=AsyncMock(return_value=[])),
    )

    result = await service.diagnose(_FakeSession(), account_id=1, limit=10)

    experiment_actions = [item for item in result.actions if item.source_module == OperatorModule.EXPERIMENTS]
    assert experiment_actions
    assert experiment_actions[0].action_type.value == "experiment_review"
    assert experiment_actions[0].nm_id == 777


@pytest.mark.asyncio
async def test_profit_doctor_merges_checker_quality_for_high_revenue_product() -> None:
    checker = SimpleNamespace(
        product_quality=AsyncMock(
            return_value=PortalProductQualityRead(
                status="ok",
                nm_id=201,
                score=55,
                recommendations=["Fix title"],
            )
        )
    )
    service = ProfitDoctorService(
        money=_money(
            [
                {
                    "nm_id": 201,
                    "sku_id": 2001,
                    "title": "Top card",
                    "revenue": 120000.0,
                    "estimated_profit": 20000.0,
                    "ads_spend": 5000.0,
                    "stock": {"quantity": 20},
                }
            ]
        ),
        checker=checker,
        module_registry=_FakeRegistry(),
    )

    result = await service.diagnose(_FakeSession(), account_id=1)

    assert any(item.diagnosis_type == DiagnosisType.CARD_QUALITY_RISK for item in result.diagnoses)
    assert any(item.module == OperatorModule.CHECKER for item in result.actions)
    checker.product_quality.assert_awaited_once()


@pytest.mark.asyncio
async def test_profit_doctor_prefers_local_card_quality_signal() -> None:
    checker = SimpleNamespace(product_quality=AsyncMock(return_value=PortalProductQualityRead(status="unavailable", nm_id=202)))
    card_quality = SimpleNamespace(
        product_quality=AsyncMock(
            return_value=PortalProductQualityRead(
                status="ok",
                module="card_quality",
                source="card_quality",
                mode="local",
                nm_id=202,
                score=40,
            )
        )
    )
    service = ProfitDoctorService(
        money=_money(
            [
                {
                    "nm_id": 202,
                    "sku_id": 2002,
                    "title": "Local card quality",
                    "revenue": 120000.0,
                    "estimated_profit": 20000.0,
                    "stock": {"quantity": 20},
                }
            ]
        ),
        checker=checker,
        card_quality=card_quality,
        module_registry=_FakeRegistry(),
    )

    result = await service.diagnose(_FakeSession(), account_id=1)

    assert any(item.diagnosis_type == DiagnosisType.CARD_QUALITY_RISK for item in result.diagnoses)
    card_quality.product_quality.assert_awaited_once()
    checker.product_quality.assert_not_awaited()


@pytest.mark.asyncio
async def test_profit_doctor_stockout_and_frozen_stock_rules() -> None:
    service = ProfitDoctorService(
        money=_money(
            [
                {
                    "nm_id": 301,
                    "title": "Low stock winner",
                    "revenue": 80000.0,
                    "estimated_profit": 18000.0,
                    "stock": {"quantity": 1, "days_of_stock": 2},
                },
                {
                    "nm_id": 302,
                    "title": "Frozen stock",
                    "revenue": 5000.0,
                    "estimated_profit": -100.0,
                    "stock": {"quantity": 180, "days_of_stock": 90, "sales_velocity_daily": 0.2, "stock_value": 40000.0},
                },
            ]
        ),
        checker=SimpleNamespace(product_quality=AsyncMock(return_value=PortalProductQualityRead(status="not_configured", nm_id=301))),
        module_registry=_FakeRegistry(),
    )

    result = await service.diagnose(_FakeSession(), account_id=1)

    assert any(item.diagnosis_type == DiagnosisType.STOCK_RISK for item in result.diagnoses)
    assert any(item.diagnosis_type == DiagnosisType.FROZEN_STOCK for item in result.diagnoses)


@pytest.mark.asyncio
async def test_profit_doctor_nm_id_uses_exact_product_detail_only() -> None:
    money = _money(
        [
            {
                "nm_id": 501,
                "title": "Requested product",
                "revenue": 60000.0,
                "estimated_profit": -4000.0,
                "ads_spend": 2000.0,
            },
            {
                "nm_id": 502,
                "title": "Other product",
                "revenue": 250000.0,
                "estimated_profit": -90000.0,
                "ads_spend": 120000.0,
                "missing_cost": True,
            },
        ]
    )
    service = ProfitDoctorService(
        money=money,
        checker=SimpleNamespace(product_quality=AsyncMock(return_value=PortalProductQualityRead(status="not_configured", nm_id=501))),
        module_registry=_FakeRegistry(),
        reputation_adapter=SimpleNamespace(profit_doctor_signals=AsyncMock(return_value=[])),
        claims_adapter=SimpleNamespace(profit_doctor_signals=AsyncMock(return_value=[])),
    )

    result = await service.diagnose(_FakeSession(), account_id=1, nm_id=501)

    assert result.status == "ok"
    assert result.data["requested_nm_id"] == 501
    assert result.data["product_found"] is True
    assert {item.nm_id for item in result.diagnoses} == {501}
    assert {item.nm_id for item in result.actions} == {501}
    assert "Other product" not in str(result.model_dump(mode="json"))
    assert "502" not in {str(item.nm_id) for item in result.diagnoses + result.actions}
    money.article_detail.assert_awaited_once()
    money.articles.assert_not_awaited()


@pytest.mark.asyncio
async def test_profit_doctor_nm_id_not_found_returns_safe_empty_diagnosis() -> None:
    money = _money(
        [
            {
                "nm_id": 601,
                "title": "Different product",
                "revenue": 60000.0,
                "estimated_profit": -4000.0,
            }
        ]
    )
    service = ProfitDoctorService(
        money=money,
        checker=SimpleNamespace(product_quality=AsyncMock()),
        module_registry=_FakeRegistry(),
        reputation_adapter=SimpleNamespace(profit_doctor_signals=AsyncMock(return_value=[])),
        claims_adapter=SimpleNamespace(profit_doctor_signals=AsyncMock(return_value=[])),
    )

    result = await service.diagnose(_FakeSession(), account_id=1, nm_id=999999)

    assert result.status == "empty"
    assert result.business_status == "empty"
    assert result.headline == "Товар не найден в финансовых данных"
    assert result.data["requested_nm_id"] == 999999
    assert result.data["product_found"] is False
    assert result.total_diagnoses == 0
    assert result.today_plan == []
    assert result.money_at_risk_amount is None
    assert "nm_id=999999" in result.summary
    money.articles.assert_not_awaited()


@pytest.mark.asyncio
async def test_profit_doctor_top_actions_have_russian_business_copy_and_trust_metadata() -> None:
    service = ProfitDoctorService(
        money=_money(
            [
                {
                    "nm_id": 701,
                    "title": "Loss product",
                    "revenue": 100000.0,
                    "estimated_profit": -3000.0,
                    "ads_spend": 45000.0,
                    "stock": {"quantity": 1, "days_of_stock": 2},
                    "missing_cost": True,
                }
            ]
        ),
        checker=SimpleNamespace(
            product_quality=AsyncMock(return_value=PortalProductQualityRead(status="ok", nm_id=701, score=45))
        ),
        module_registry=_FakeRegistry(),
        reputation_adapter=SimpleNamespace(profit_doctor_signals=AsyncMock(return_value=[])),
        claims_adapter=SimpleNamespace(profit_doctor_signals=AsyncMock(return_value=[])),
    )

    result = await service.diagnose(_FakeSession(), account_id=1, nm_id=701)
    action_text = " ".join(f"{item.title} {item.reason} {item.next_step}" for item in result.today_plan)

    assert "себестоимость" in action_text
    assert "продается в минус" in action_text
    assert "Реклама съедает прибыль" in action_text
    assert "низкого остатка" in action_text
    assert "слабая карточка" in action_text
    for action in result.today_plan:
        assert action.confidence or action.trust_state
        assert action.data["calculation_note"]
        assert action.data["raw_code"]
    assert result.data["money_at_risk"]["confidence"] in {"low", "medium"}
    assert "эврист" in result.data["money_at_risk"]["calculation_note"].lower() or "оценка" in result.data["money_at_risk"]["calculation_note"].lower()
    assert result.money_at_risk_confidence == result.data["money_at_risk"]["confidence"]
    assert result.money_at_risk_calculation_note == result.data["money_at_risk"]["calculation_note"]


@pytest.mark.asyncio
async def test_profit_doctor_merges_reputation_and_claims_adapter_signals() -> None:
    reputation = SimpleNamespace(
        profit_doctor_signals=AsyncMock(
            return_value=[
                {
                    "nm_id": 401,
                    "priority": "P2",
                    "title": "Negative unanswered review",
                    "reason": "Top product has a negative unanswered review.",
                    "impact": 3000.0,
                }
            ]
        )
    )
    claims = SimpleNamespace(
        profit_doctor_signals=AsyncMock(
            return_value=[
                {
                    "nm_id": 402,
                    "priority": "P1",
                    "title": "Defect compensation candidate",
                    "reason": "Return compensation may be underpaid.",
                    "impact": 7000.0,
                }
            ]
        )
    )
    service = ProfitDoctorService(
        money=_money([]),
        checker=SimpleNamespace(product_quality=AsyncMock()),
        module_registry=_FakeRegistry(),
        reputation_adapter=reputation,
        claims_adapter=claims,
    )

    result = await service.diagnose(_FakeSession(), account_id=1)

    assert any(item.diagnosis_type == DiagnosisType.REPUTATION_RISK for item in result.diagnoses)
    assert any(item.diagnosis_type == DiagnosisType.CLAIM_OPPORTUNITY for item in result.diagnoses)
    assert result.business_status == "risk"
    assert result.top_sections["reputation_risks"]["count"] == 1
    assert result.top_sections["claims_opportunities"]["count"] == 1
    assert result.money_at_risk_amount == 10000.0
    assert "reputation" not in result.unavailable_sources
    assert "claims" not in result.unavailable_sources


@pytest.mark.asyncio
async def test_profit_doctor_merges_report_anomaly_claim_signal() -> None:
    claims = SimpleNamespace(
        profit_doctor_signals=AsyncMock(
            return_value=[
                {
                    "nm_id": 403,
                    "priority": "P2",
                    "case_type": "report_anomaly",
                    "diagnosis_type": "report_anomaly",
                    "action_type": "report_anomaly_candidate",
                    "title": "Report anomaly candidate requires review",
                    "reason": "Finance report mismatch candidate requires review and proof-check required.",
                    "impact": 2500.0,
                }
            ]
        )
    )
    service = ProfitDoctorService(
        money=_money([]),
        checker=SimpleNamespace(product_quality=AsyncMock()),
        module_registry=_FakeRegistry(),
        reputation_adapter=SimpleNamespace(profit_doctor_signals=AsyncMock(return_value=[])),
        claims_adapter=claims,
    )

    result = await service.diagnose(_FakeSession(), account_id=1)

    assert any(item.diagnosis_type == DiagnosisType.REPORT_ANOMALY for item in result.diagnoses)
    assert any(item.module == OperatorModule.CLAIMS for item in result.actions)
    claims.profit_doctor_signals.assert_awaited_once()


@pytest.mark.asyncio
async def test_profit_doctor_optional_source_failures_do_not_crash() -> None:
    service = ProfitDoctorService(
        money=SimpleNamespace(
            summary=AsyncMock(side_effect=RuntimeError("db down")),
            articles=AsyncMock(return_value=SimpleNamespace(items=[])),
            data_blockers=AsyncMock(return_value={"overall_state": "ok", "blockers": [], "warnings": []}),
        ),
        checker=SimpleNamespace(product_quality=AsyncMock()),
        module_registry=_FakeRegistry(),
    )

    result = await service.diagnose(_FakeSession(), account_id=1)

    assert result.status == "unavailable"
    assert result.trust_state == TrustState.UNAVAILABLE
    assert result.business_status == "unavailable"
    assert result.headline == "Недостаточно данных для диагностики прибыли"
    assert result.money_at_risk_amount is None
    assert result.top_sections["profit_leaks"]["count"] == 0
    assert "money_summary" in result.unavailable_sources
    assert result.total_diagnoses == 0
