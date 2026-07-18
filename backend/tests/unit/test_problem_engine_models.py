from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from app.core.db import Base
from app.core.model_registry import load_all_models
from app.models.problem_engine import (
    AdminRuleTestRun,
    MetricCatalog,
    ProblemDefinition,
    ProblemInstance,
    ProblemInstanceHistory,
    ProblemRuleAdminAudit,
    ProblemRuleVersion,
)
from app.schemas.problem_engine import (
    AdminRuleTestRunRead,
    MetricCatalogRead,
    ProblemDefinitionRead,
    ProblemInstanceHistoryRead,
    ProblemInstanceRead,
    ProblemRuleAdminAuditRead,
    ProblemRuleVersionRead,
)


PROBLEM_ENGINE_MODELS = (
    MetricCatalog,
    ProblemDefinition,
    ProblemRuleVersion,
    ProblemInstance,
    ProblemInstanceHistory,
    AdminRuleTestRun,
    ProblemRuleAdminAudit,
)


def test_problem_engine_models_are_registered_in_metadata() -> None:
    load_all_models()

    for model in PROBLEM_ENGINE_MODELS:
        assert model.__tablename__ in Base.metadata.tables


def test_problem_engine_models_have_required_columns() -> None:
    expected_columns = {
        MetricCatalog: {
            "metric_code",
            "title",
            "description",
            "value_type",
            "unit",
            "grain",
            "entity_type",
            "source_module",
            "formula_json",
            "source_tables_json",
            "source_endpoints_json",
            "required_metrics_json",
            "trust_state",
            "is_admin_visible",
            "is_deprecated",
            "created_at",
            "updated_at",
        },
        ProblemDefinition: {
            "problem_code",
            "source_module",
            "category",
            "entity_type",
            "title_template",
            "description_template",
            "recommendation_template",
            "impact_type_default",
            "trust_state_default",
            "severity_default",
            "allowed_actions_json",
            "test_only",
            "seller_visible",
            "visibility_mode",
            "status",
            "is_system_seeded",
            "created_by_user_id",
            "created_at",
            "updated_at",
        },
        ProblemRuleVersion: {
            "problem_definition_id",
            "version",
            "status",
            "evaluation_grain",
            "lookback_days",
            "condition_json",
            "impact_formula_json",
            "severity_formula_json",
            "confidence_formula_json",
            "dedup_key_template",
            "recheck_rule_json",
            "evidence_template_json",
            "test_only",
            "seller_visible",
            "visibility_mode",
            "is_system_seeded",
            "created_by_user_id",
            "published_by_user_id",
            "published_at",
            "created_at",
            "updated_at",
        },
        ProblemInstance: {
            "account_id",
            "problem_code",
            "problem_definition_id",
            "rule_version_id",
            "source_module",
            "entity_type",
            "entity_id",
            "nm_id",
            "vendor_code",
            "dedup_key",
            "title",
            "explanation",
            "recommendation",
            "severity",
            "status",
            "impact_type",
            "money_impact_amount",
            "money_impact_currency",
            "trust_state",
            "confidence",
            "evidence_ledger_json",
            "calculation_snapshot_json",
            "first_seen_at",
            "last_seen_at",
            "resolved_at",
            "dismissed_at",
            "dismiss_reason",
            "created_at",
            "updated_at",
        },
        ProblemInstanceHistory: {
            "problem_instance_id",
            "event_type",
            "old_value_json",
            "new_value_json",
            "comment",
            "actor_user_id",
            "created_at",
        },
        AdminRuleTestRun: {
            "rule_version_id",
            "account_id",
            "date_from",
            "date_to",
            "matched_count",
            "sample_issues_json",
            "total_impact_amount",
            "warnings_json",
            "created_by_user_id",
            "created_at",
        },
        ProblemRuleAdminAudit: {
            "object_type",
            "object_id",
            "event_type",
            "old_value_json",
            "new_value_json",
            "comment",
            "actor_user_id",
            "created_at",
        },
    }

    for model, columns in expected_columns.items():
        assert columns.issubset(model.__table__.c.keys())


def test_problem_engine_indexes_and_uniqueness_match_contract() -> None:
    assert "ix_metric_catalog_metric_code" in {index.name for index in MetricCatalog.__table__.indexes}
    assert "ix_problem_instances_account_status" in {index.name for index in ProblemInstance.__table__.indexes}
    assert "ix_problem_instances_account_problem_code" in {index.name for index in ProblemInstance.__table__.indexes}
    assert "ix_problem_instances_account_status_last_seen_id" in {index.name for index in ProblemInstance.__table__.indexes}
    assert "ix_problem_instances_dedup_key" in {index.name for index in ProblemInstance.__table__.indexes}
    assert "ix_problem_instance_history_problem_created_id" in {index.name for index in ProblemInstanceHistory.__table__.indexes}
    assert "ix_problem_rule_versions_definition_version" in {index.name for index in ProblemRuleVersion.__table__.indexes}
    assert "ix_problem_definitions_system_seeded" in {index.name for index in ProblemDefinition.__table__.indexes}
    assert "ix_problem_rule_versions_system_seeded" in {index.name for index in ProblemRuleVersion.__table__.indexes}
    assert "ix_problem_definitions_visibility_mode" in {index.name for index in ProblemDefinition.__table__.indexes}
    assert "ix_problem_rule_versions_visibility_mode" in {index.name for index in ProblemRuleVersion.__table__.indexes}
    assert "ix_problem_rule_admin_audit_object" in {index.name for index in ProblemRuleAdminAudit.__table__.indexes}

    unique_constraints = {constraint.name for constraint in ProblemInstance.__table__.constraints}
    assert "uq_problem_instances_account_problem_entity_dedup" in unique_constraints

    dedup_constraint = next(
        constraint
        for constraint in ProblemInstance.__table__.constraints
        if constraint.name == "uq_problem_instances_account_problem_entity_dedup"
    )
    assert [column.name for column in dedup_constraint.columns] == [
        "account_id",
        "problem_code",
        "entity_type",
        "entity_id",
        "dedup_key",
    ]


def test_problem_engine_foreign_keys_are_additive() -> None:
    assert {fk.column.table.name for fk in ProblemDefinition.__table__.foreign_keys} == {"auth_users"}
    assert {fk.column.table.name for fk in ProblemRuleVersion.__table__.foreign_keys} == {
        "auth_users",
        "problem_definitions",
    }
    assert {fk.column.table.name for fk in ProblemInstance.__table__.foreign_keys} == {
        "problem_definitions",
        "problem_rule_versions",
        "wb_accounts",
    }
    assert {fk.column.table.name for fk in ProblemInstanceHistory.__table__.foreign_keys} == {
        "auth_users",
        "problem_instances",
    }
    assert {fk.column.table.name for fk in AdminRuleTestRun.__table__.foreign_keys} == {
        "auth_users",
        "problem_rule_versions",
        "wb_accounts",
    }
    assert {fk.column.table.name for fk in ProblemRuleAdminAudit.__table__.foreign_keys} == {"auth_users"}


def test_problem_engine_read_schemas_validate_from_orm_attributes() -> None:
    now = datetime(2026, 7, 6, tzinfo=timezone.utc)

    metric = MetricCatalogRead.model_validate(
        MetricCatalog(
            id=1,
            metric_code="net_profit_per_unit",
            title="Net profit per unit",
            description="Profit divided by net units.",
            value_type="money",
            unit="RUB",
            grain="product_period",
            entity_type="product",
            source_module="money",
            formula_json={"op": "div"},
            source_tables_json=["mart_sku_daily"],
            source_endpoints_json=["/money/articles/{nm_id}"],
            required_metrics_json=["net_profit_after_ads", "net_units"],
            trust_state="confirmed",
            is_admin_visible=True,
            is_deprecated=False,
            created_at=now,
            updated_at=now,
        )
    )
    assert metric.metric_code == "net_profit_per_unit"

    definition = ProblemDefinitionRead.model_validate(
        ProblemDefinition(
            id=2,
            problem_code="negative_unit_profit",
            source_module="money",
            category="profitability",
            entity_type="product",
            title_template="Negative unit profit",
            description_template="Unit economics are below zero.",
            recommendation_template="Review price, ads, or costs.",
            impact_type_default="confirmed_loss",
            trust_state_default="confirmed",
            severity_default="high",
            allowed_actions_json=["PRICE_INCREASE_REVIEW"],
            status="draft",
            is_system_seeded=False,
            created_by_user_id=None,
            created_at=now,
            updated_at=now,
        )
    )
    assert definition.problem_code == "negative_unit_profit"

    rule = ProblemRuleVersionRead.model_validate(
        ProblemRuleVersion(
            id=3,
            problem_definition_id=2,
            version=1,
            status="testing",
            evaluation_grain="product_period",
            lookback_days=30,
            condition_json={"type": "compare"},
            impact_formula_json={"type": "metric_ref", "key": "net_profit_after_ads"},
            severity_formula_json={},
            confidence_formula_json={},
            dedup_key_template="{account_id}:{problem_code}:{nm_id}",
            recheck_rule_json={"mode": "manual"},
            evidence_template_json={"required": ["net_profit_per_unit"]},
            is_system_seeded=False,
            created_by_user_id=None,
            published_by_user_id=None,
            published_at=None,
            created_at=now,
            updated_at=now,
        )
    )
    assert rule.version == 1

    instance = ProblemInstanceRead.model_validate(
        ProblemInstance(
            id=4,
            account_id=10,
            problem_code="negative_unit_profit",
            problem_definition_id=2,
            rule_version_id=3,
            source_module="problem_engine",
            entity_type="product",
            entity_id="123456",
            nm_id=123456,
            vendor_code="VC-1",
            dedup_key="dedup-1",
            title="Negative unit profit",
            explanation="Profit per unit is negative.",
            recommendation="Review price.",
            severity="high",
            status="new",
            impact_type="confirmed_loss",
            money_impact_amount=Decimal("123.45"),
            money_impact_currency="RUB",
            trust_state="confirmed",
            confidence="high",
            evidence_ledger_json={"formula_code": "negative_unit_profit.v1"},
            calculation_snapshot_json={"net_profit_per_unit": -10},
            first_seen_at=now,
            last_seen_at=now,
            resolved_at=None,
            dismissed_at=None,
            dismiss_reason=None,
            created_at=now,
            updated_at=now,
        )
    )
    assert instance.dedup_key == "dedup-1"

    history = ProblemInstanceHistoryRead.model_validate(
        ProblemInstanceHistory(
            id=5,
            problem_instance_id=4,
            event_type="status_changed",
            old_value_json={"status": "new"},
            new_value_json={"status": "in_progress"},
            comment="Started work",
            actor_user_id=None,
            created_at=now,
        )
    )
    assert history.event_type == "status_changed"

    test_run = AdminRuleTestRunRead.model_validate(
        AdminRuleTestRun(
            id=6,
            rule_version_id=3,
            account_id=None,
            date_from=date(2026, 6, 1),
            date_to=date(2026, 6, 30),
            matched_count=2,
            sample_issues_json=[{"nm_id": 123456}],
            total_impact_amount=Decimal("200.00"),
            warnings_json=["sample"],
            created_by_user_id=None,
            created_at=now,
        )
    )
    assert test_run.matched_count == 2

    audit = ProblemRuleAdminAuditRead.model_validate(
        ProblemRuleAdminAudit(
            id=7,
            object_type="rule_version",
            object_id=3,
            event_type="published",
            old_value_json={"status": "testing"},
            new_value_json={"status": "active"},
            comment="approved after backtest",
            actor_user_id=None,
            created_at=now,
        )
    )
    assert audit.event_type == "published"
