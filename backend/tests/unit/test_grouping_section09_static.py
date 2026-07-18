from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_grouping_frontend_wires_preview_and_local_review() -> None:
    endpoints = _read("../frontend/src/lib/endpoints.ts")
    portal = _read("../frontend/src/lib/portal.ts")
    route = _read("../frontend/src/routes/_authenticated/grouping.tsx")

    assert "groupingPreview" in endpoints
    assert '"/portal/grouping/preview"' in endpoints
    assert "groupingCandidateStatus" in endpoints
    assert "previewGrouping" in portal
    assert "updateGroupingCandidateStatus" in portal
    assert "previewGrouping(activeId" in route
    assert "updateGroupingCandidateStatus" in route
    assert "merge WB: off" in route


def test_grouping_finance_portal_has_no_wb_merge_route() -> None:
    router = _read("app/modules/portal/router.py")
    service = _read("app/services/grouping.py")

    assert '"/portal/grouping/preview"' in router
    assert '"/portal/grouping/candidates/{candidate_id}/status"' in router
    assert "merge-wb" not in router
    assert "blocked_operations" in service
    assert "auto_merge_enabled" in service
    assert '"enabled": False' in service


def test_grouping_section09_audit_doc_exists() -> None:
    doc = _read("../docs/final_integration/GROUPING_BETA_AUDIT.md")

    for phrase in (
        "Local engine lives in Finance",
        "Full catalog run is supported",
        "Finance never exposes a `merge-wb` route",
        "Product 360 uses `/portal/products/{nm_id}/grouping`",
    ):
        assert phrase in doc
