from __future__ import annotations

from datetime import datetime, timezone

from app.models.grouping import GroupingCandidate, GroupingSettings
from app.services.grouping import GroupingBetaService, NormalizedGroupingProduct


def _product(**overrides) -> NormalizedGroupingProduct:
    values = {
        "account_id": 1,
        "nm_id": 1001,
        "imt_id": None,
        "vendor_code": "AV 100 black",
        "article_core": "AV 100 BLACK",
        "article_base_core": "AV 100",
        "title": "Avemod suit black",
        "brand": "Avemod",
        "subject_name": "Костюмы",
        "color_normalized": "black",
        "characteristics": [{"name": "Цвет", "value": ["black"]}],
        "sizes": [],
        "barcodes": [],
        "media_summary": {"photo_count": 3},
        "stock_summary": {},
        "finance_summary": {},
        "source_revision": "rev-1",
    }
    values.update(overrides)
    return NormalizedGroupingProduct(**values)


def _settings(**overrides) -> GroupingSettings:
    values = {
        "account_id": 1,
        "minimum_confidence": 0.55,
        "maximum_risk": 0.65,
        "allow_cross_brand": False,
        "allow_cross_subject": False,
        "require_identity_evidence": True,
    }
    values.update(overrides)
    return GroupingSettings(**values)


def test_grouping_beta_builds_article_family_candidate_without_wb_write() -> None:
    service = GroupingBetaService()

    candidates = service._build_candidates(
        [
            _product(nm_id=1001, color_normalized="black"),
            _product(nm_id=1002, vendor_code="AV 100 red", article_core="AV 100 RED", color_normalized="red"),
        ],
        account_id=1,
        run_id=10,
        scenario="article_family",
        settings=_settings(),
    )

    assert len(candidates) == 1
    payload = service._candidate_payload(candidates[0])
    assert payload["nm_ids"] == [1001, 1002]
    assert payload["risk_level"] == "low"
    assert "same_article_base_core" in payload["reasons"]
    assert payload["auto_merge_enabled"] is False
    assert payload["preview_payload"]["enabled"] is False
    assert payload["preview_payload"]["operation"] == "merge_preview"


def test_grouping_beta_blocks_cross_brand_candidate_by_default() -> None:
    service = GroupingBetaService()

    candidates = service._build_candidates(
        [
            _product(nm_id=1001, brand="Avemod"),
            _product(nm_id=1002, brand="OtherBrand"),
        ],
        account_id=1,
        run_id=10,
        scenario="article_family",
        settings=_settings(),
    )

    assert candidates == []


def test_grouping_beta_action_is_review_only() -> None:
    service = GroupingBetaService()
    now = datetime.now(timezone.utc)
    candidate = GroupingCandidate(
        id=77,
        account_id=1,
        run_id=10,
        candidate_key="article_base:avemod:костюмы:AV 100",
        anchor_nm_id=1001,
        member_nm_ids_json=[1001, 1002],
        scenario="article_family",
        candidate_type="article_base",
        confidence=0.9,
        risk_level="low",
        risk_score=0.1,
        reasons_json=["same_article_base_core"],
        risk_reasons_json=[],
        conflicts_json=[],
        evidence_json={"source_module": "finance"},
        status="new",
        fingerprint="fp",
        first_seen_at=now,
        last_seen_at=now,
    )

    action = service._action_from_candidate(candidate)

    assert action.source_module == "grouping"
    assert action.can_execute is False
    assert action.payload["auto_merge_enabled"] is False
    assert action.payload["preview_payload"]["blocked_submit_reason"]


def test_grouping_beta_preview_payload_never_enables_wb_merge() -> None:
    service = GroupingBetaService()
    now = datetime.now(timezone.utc)
    candidate = GroupingCandidate(
        id=88,
        account_id=1,
        run_id=10,
        candidate_key="article_base:avemod:костюмы:AV 100",
        anchor_nm_id=1001,
        member_nm_ids_json=[1001, 1002],
        scenario="article_family",
        candidate_type="article_base",
        confidence=0.9,
        risk_level="low",
        risk_score=0.1,
        reasons_json=["same_article_base_core"],
        risk_reasons_json=[],
        conflicts_json=[],
        evidence_json={"source_module": "finance"},
        status="new",
        fingerprint="fp-88",
        first_seen_at=now,
        last_seen_at=now,
    )

    payload = service._candidate_payload(candidate)

    assert payload["auto_merge_enabled"] is False
    assert payload["preview_payload"]["enabled"] is False
    assert payload["preview_payload"]["auto_merge_enabled"] is False
    assert payload["preview_payload"]["operation"] == "merge_preview"
    assert "merge-wb" not in str(payload)
