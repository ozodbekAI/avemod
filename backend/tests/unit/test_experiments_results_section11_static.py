from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_experiment_result_events_include_windows_and_safe_causality() -> None:
    service = _read("app/services/experiments.py")
    result_tracking = _read("app/services/result_tracking.py")
    schemas = _read("app/schemas/portal.py")

    assert "CAUSALITY_DISCLAIMER" in service
    assert '"baseline_window": evaluation.baseline_window_json' in service
    assert '"post_window": evaluation.post_window_json' in service
    assert '"data_sufficiency": data_sufficiency' in service
    assert '"confounders": confounders' in service
    assert 'event_type="experiment_evaluated"' in service
    assert "payload=self._safe_snapshot(payload)" in result_tracking
    assert "payload: dict[str, Any]" in schemas


def test_photo_studio_has_experiment_bridge_for_approved_versions() -> None:
    endpoints = _read("../frontend/src/lib/endpoints.ts")
    client = _read("../frontend/src/lib/photo-studio.ts")
    route = _read("../frontend/src/routes/_authenticated/photo-studio.projects.$projectId.tsx")
    router = _read("app/modules/portal/router.py")

    assert "photoVersionExperiment" in endpoints
    assert "/portal/photo/projects/${id}/versions/${vid}/experiment" in endpoints
    assert "createPhotoVersionExperiment" in client
    assert "baseline_days: payload.baseline_days ?? 7" in client
    assert "post_days: payload.post_days ?? 14" in client
    assert "Отслеживать эффект 14 дней" in route
    assert '"/portal/photo/projects/{project_id}/versions/{version_id}/experiment"' in router


def test_results_page_renders_experiment_evidence_without_causality_claims() -> None:
    route = _read("../frontend/src/routes/_authenticated/results.tsx")

    assert "function ExperimentEvidence" in route
    assert "baseline_window" in route
    assert "post_window" in route
    assert "primary_result" in route
    assert "data_sufficiency" in route
    assert "confounders" in route
    assert "Корреляция, а не гарантия" in route
    assert "PROBLEM_RESULT_CORRELATION_DISCLAIMER" in route
