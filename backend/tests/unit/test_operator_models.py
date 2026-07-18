from __future__ import annotations

from app.core.db import Base
from app.core.model_registry import load_all_models
from app.models.operator import (
    ExternalTicket,
    OperatorCase,
    OperatorDiagnosis,
    OperatorDraft,
    OperatorEvidence,
    OperatorSignal,
    ResultEvent,
    UnifiedAction,
    scrub_operator_payload,
)


OPERATOR_MODELS = (
    OperatorSignal,
    OperatorDiagnosis,
    UnifiedAction,
    OperatorCase,
    OperatorEvidence,
    OperatorDraft,
    ExternalTicket,
    ResultEvent,
)


REQUIRED_COLUMNS = {
    "account_id",
    "source_module",
    "source_id",
    "external_id",
    "nm_id",
    "vendor_code",
    "status",
    "created_at",
    "updated_at",
    "payload_json",
}


def test_operator_models_are_registered_in_metadata() -> None:
    load_all_models()

    for model in OPERATOR_MODELS:
        assert model.__tablename__ in Base.metadata.tables


def test_operator_models_have_required_common_columns_and_indexes() -> None:
    for model in OPERATOR_MODELS:
        columns = model.__table__.c
        assert REQUIRED_COLUMNS.issubset(columns.keys())
        assert columns["account_id"].index is True
        assert columns["source_module"].index is True
        assert columns["nm_id"].index is True
        assert columns["status"].index is True
        assert f"ix_{model.__tablename__}_created_at" in {index.name for index in model.__table__.indexes}


def test_operator_chain_foreign_keys_are_additive_and_finance_scoped() -> None:
    assert {fk.column.table.name for fk in OperatorSignal.__table__.foreign_keys} == {"wb_accounts"}
    assert {fk.column.table.name for fk in OperatorDiagnosis.__table__.foreign_keys} == {
        "operator_signals",
        "wb_accounts",
    }
    assert {fk.column.table.name for fk in UnifiedAction.__table__.foreign_keys} == {
        "auth_users",
        "operator_diagnoses",
        "wb_accounts",
    }
    assert {fk.column.table.name for fk in OperatorCase.__table__.foreign_keys} == {
        "unified_actions",
        "wb_accounts",
    }
    assert {fk.column.table.name for fk in OperatorDraft.__table__.foreign_keys} == {
        "operator_cases",
        "unified_actions",
        "wb_accounts",
    }
    assert {fk.column.table.name for fk in ExternalTicket.__table__.foreign_keys} == {
        "operator_cases",
        "operator_drafts",
        "wb_accounts",
    }
    assert {fk.column.table.name for fk in ResultEvent.__table__.foreign_keys} == {
        "external_tickets",
        "operator_cases",
        "operator_drafts",
        "problem_instances",
        "unified_actions",
        "wb_accounts",
    }


def test_operator_payload_scrubber_removes_secret_like_keys_recursively() -> None:
    payload = {
        "safe": True,
        "token": "must-not-leak",
        "nested": {
            "api_key": "must-not-leak",
            "value": 5,
        },
        "items": [
            {"authorization": "must-not-leak", "name": "kept"},
            {"refresh_token": "must-not-leak", "count": 2},
        ],
    }

    assert scrub_operator_payload(payload) == {
        "safe": True,
        "nested": {"value": 5},
        "items": [{"name": "kept"}, {"count": 2}],
    }


def test_operator_payload_model_events_are_registered() -> None:
    for model in OPERATOR_MODELS:
        assert model.__mapper__.dispatch.before_insert
        assert model.__mapper__.dispatch.before_update
