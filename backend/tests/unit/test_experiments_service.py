from __future__ import annotations

from decimal import Decimal

from app.core.time import utcnow
from app.models.experiments import Experiment, ExperimentEvaluation, ExperimentEvent, ExperimentSettings
from app.services.experiments import ExperimentEvaluationService, ExperimentEventService, METRIC_CATALOG


def test_experiment_event_service_serializes_minimal_change_event() -> None:
    now = utcnow()
    event = ExperimentEvent(
        id=1,
        account_id=1,
        nm_id=1001,
        sku_id=None,
        action_id=10,
        event_type="price_changed",
        before_json={"price": 1000},
        after_json={"price": 900},
        changed_at=now,
        created_by=7,
        created_at=now,
    )

    read = ExperimentEventService()._event_read(event)

    assert read.id == 1
    assert read.account_id == 1
    assert read.nm_id == 1001
    assert read.action_id == 10
    assert read.event_type == "price_changed"
    assert read.before_json == {"price": 1000}
    assert read.after_json == {"price": 900}
    assert read.created_by == 7


def test_experiments_status_exposes_safe_supported_modes() -> None:
    status = ExperimentEventService().status()

    assert status.enabled is True
    assert "before_after" in status.supported_experiment_types
    assert "controlled_split" in status.unsupported_experiment_types
    assert "photo" in status.supported_intervention_types
    assert "causality" in status.disclaimer.lower()


def test_experiment_read_serializes_latest_evaluation() -> None:
    now = utcnow()
    evaluation = ExperimentEvaluation(
        id=7,
        account_id=1,
        experiment_id=3,
        status="ok",
        evaluation_version="before_after_v1",
        evaluated_at=now,
        baseline_window_json={"day_count": 7},
        post_window_json={"day_count": 7},
        primary_result_json={"metric": "revenue", "relative_change_percent": 8.0},
        secondary_results_json=[],
        guardrail_results_json=[],
        data_sufficiency_json={"post_orders": 12},
        confounders_json=[],
        confidence="medium",
        outcome="improved",
        seller_summary="Наблюдаемое улучшение. Это наблюдаемая связь, а не доказанная причинность.",
        technical_summary_json={"causality": "before_after_observational"},
    )

    read = ExperimentEventService()._evaluation_read(evaluation)

    assert read.outcome == "improved"
    assert read.confidence == "medium"
    assert read.primary_result["relative_change_percent"] == 8.0
    assert "наблюдаемая связь" in read.seller_summary.lower()


def test_before_after_outcome_respects_negative_metrics() -> None:
    service = ExperimentEvaluationService()
    primary = {
        "metric": "ads_spend",
        "baseline": 100.0,
        "post": 80.0,
        "relative_change_percent": -20.0,
        "positive_is_good": METRIC_CATALOG["ads_spend"].positive_is_good,
    }
    settings = ExperimentSettings(account_id=1, minimum_orders=1, minimum_revenue=Decimal("0"), maximum_stockout_days=1)

    outcome = service._outcome(
        primary,
        {"post_orders": 5, "post_revenue": 1000.0, "missing_post_days": 0},
        [],
        settings=settings,
    )

    assert outcome == "improved"


def test_controlled_split_without_assignment_is_not_supported_summary() -> None:
    experiment = Experiment(
        id=1,
        account_id=1,
        experiment_type="controlled_split",
        intervention_type="photo",
        status="ready_for_evaluation",
        name="Photo split",
        hypothesis="Photo A beats photo B",
        primary_metric="revenue",
        baseline_days=7,
        post_days=7,
        evaluation_delay_days=0,
    )

    assert experiment.experiment_type == "controlled_split"


def test_experiment_action_candidate_maps_ready_state_to_action_center_task() -> None:
    experiment = Experiment(
        id=42,
        account_id=1,
        nm_id=123456,
        sku_id=None,
        experiment_type="before_after",
        intervention_type="photo",
        status="ready_for_change",
        name="Photo test",
        hypothesis="Better main photo may improve conversion",
        primary_metric="conversion_rate",
        baseline_days=7,
        post_days=14,
        evaluation_delay_days=0,
    )

    action = ExperimentEventService()._action_candidate(experiment)

    assert action.source_module == "experiments"
    assert action.action_type == "record_experiment_intervention"
    assert action.can_execute is True
    assert action.nm_id == 123456
    assert action.payload["causality_note"]
