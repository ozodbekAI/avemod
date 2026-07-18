from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_claims_frontend_wires_local_lifecycle_endpoints() -> None:
    endpoints = _read("../frontend/src/lib/endpoints.ts")
    portal = _read("../frontend/src/lib/portal.ts")
    route = _read("../frontend/src/routes/_authenticated/claims.tsx")

    assert 'claimsScans:          "/portal/claims/scans"' in endpoints
    assert 'claimCandidates:      "/portal/claims/candidates"' in endpoints
    assert "claimCandidateCreateCase" in endpoints
    assert "caseGenerateDraft" in endpoints

    assert "fetchClaimCandidates" in portal
    assert "startClaimScan" in portal
    assert "createCaseFromCandidate" in portal
    assert "generateClaimDraft" in portal
    assert "submitCase(id, { confirm: true })" in route
    assert "manual: true" not in route


def test_claims_service_hides_synthetic_cases_and_health_is_local_first() -> None:
    factory = _read("app/services/claims_factory.py")
    registry = _read("app/services/module_registry.py")

    assert "def _is_synthetic_case" in factory
    assert "shadow_synthetic" in factory
    assert "runtime audit" in factory
    assert "or self._is_synthetic_case(row)" in factory
    assert "if not self._is_synthetic_case(row)" in factory

    local_first = (
        'db_states.get("claims") or await self._local_claims_health(session=session, account=account) '
        "or self._external_config_health"
    )
    assert local_first in registry
    assert 'message="local claims detection uses finance database"' in registry


def test_claims_section08_audit_doc_exists() -> None:
    doc = _read("../docs/final_integration/CLAIMS_FACTORY_AUDIT.md")

    for phrase in (
        "Detection types are local and account-scoped",
        "Synthetic/audit/test cases are hidden",
        "External submit being disabled does not disable local Claims Factory",
        "Product 360, Action Center, legacy profit diagnostics, and Results",
    ):
        assert phrase in doc
