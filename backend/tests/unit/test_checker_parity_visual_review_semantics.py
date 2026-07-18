from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.models.card_quality import CardQualityIssue
from app.services.card_quality import CardQualityAnalysisService, CardQualityRuleEngine, NormalizedCard, RuleIssue


def _card(**overrides) -> NormalizedCard:
    values = {
        "account_id": 1,
        "nm_id": 245405620,
        "source_card_id": 10,
        "title": "Костюм для офиса классический с юбкой миди",
        "description": "Удобный женский костюм для повседневной носки. Подходит для прогулок, поездок и дома.",
        "brand": "Avemod",
        "subject_id": 123,
        "subject_name": "Костюмы",
        "vendor_code": "AV-1",
        "characteristics": [{"name": "Цвет", "value": ["черный"]}, {"name": "Состав", "value": ["хлопок"]}],
        "photos": [{"canonical_url": "https://example.test/1.jpg", "variants": {}}],
        "videos": [],
        "sizes": [],
        "source_revision": "rev",
        "source_updated_at": None,
    }
    values.update(overrides)
    return NormalizedCard(**values)


def _target_issue(**overrides) -> CardQualityIssue:
    values = {
        "id": 1,
        "account_id": 1,
        "nm_id": 245405620,
        "issue_code": "wb_allowed_values",
        "category": "characteristics",
        "severity": "medium",
        "title": "Проверить характеристику",
        "field_name": "characteristics.Фактура материала",
        "suggested_value": None,
        "ai_suggested_value": "габардин",
        "requires_human_check": True,
        "status": "new",
        "fingerprint": "fp",
        "first_seen_at": datetime.now(UTC),
        "last_seen_at": datetime.now(UTC),
    }
    values.update(overrides)
    return CardQualityIssue(**values)


@pytest.mark.parametrize("field_name", ["Комплектация", "Вид застежки", "Фактура материала"])
def test_visual_risky_fields_are_review_only(field_name: str) -> None:
    rules = CardQualityRuleEngine()

    assert rules._requires_human_check(name=field_name, errors=[], suggested="кандидат") is True
    assert "Проверить" in rules._wb_recommended_fix(
        name=field_name,
        suggested="кандидат",
        requires_human_check=True,
    )


@pytest.mark.asyncio
async def test_review_ready_ai_candidate_does_not_leak_into_confirmed_suggested_value() -> None:
    service = CardQualityAnalysisService()
    service.ai_fixer = SimpleNamespace(
        is_enabled=True,
        generate_fixes=AsyncMock(
            return_value={
                "0": {
                    "recommended_value": "габардин",
                    "reason": "needs visual confirmation",
                    "confidence": 0.7,
                    "requires_human_check": True,
                    "suggestion_kind": "candidate",
                    "candidate_values": ["габардин"],
                    "used_sources": ["card_characteristics"],
                    "evidence": {"observed": ["candidate only"]},
                    "photo_evidence": [],
                }
            }
        ),
    )
    issue = RuleIssue(
        issue_code="wb_allowed_values",
        category="characteristics",
        severity="medium",
        title="Проверить фактуру",
        business_explanation="candidate",
        recommended_fix="Проверить вручную",
        field_name="characteristics.Фактура материала",
        ai_suggested_value="габардин",
        allowed_values=["габардин", "твид"],
        requires_human_check=True,
    )

    [updated] = await service._apply_ai_fixes(_card(), [issue])

    assert updated.requires_human_check is True
    assert updated.suggested_value is None
    assert updated.ai_suggested_value is None
    assert updated.ai_alternatives == ["габардин"]
    assert updated.ai_evidence["observed"] == ["candidate only"]
    assert updated.ai_evidence["why_human_check_required"] == "visual_field_requires_manual_check"
    assert updated.ai_evidence["visual_trust"]["grounded"] is False


@pytest.mark.asyncio
async def test_weak_product_dna_is_removed_from_ai_used_sources() -> None:
    service = CardQualityAnalysisService()
    service.ai_fixer = SimpleNamespace(
        is_enabled=True,
        generate_fixes=AsyncMock(
            return_value={
                "0": {
                    "recommended_value": "костюм",
                    "reason": "source truth provenance guard",
                    "confidence": 0.8,
                    "requires_human_check": True,
                    "suggestion_kind": "candidate",
                    "candidate_values": ["костюм"],
                    "used_sources": ["product_dna", "photos", "card_characteristics"],
                    "evidence": {"observed": ["candidate from weak visual context"]},
                    "photo_evidence": [],
                }
            }
        ),
    )
    issue = RuleIssue(
        issue_code="wb_allowed_values",
        category="characteristics",
        severity="medium",
        title="Проверить комплектацию",
        business_explanation="candidate",
        recommended_fix="Проверить вручную",
        field_name="characteristics.Комплектация",
        current_value_json="",
        allowed_values=["костюм", "пиджак"],
        requires_human_check=True,
    )
    card = _card(
        product_dna_text="",
        product_dna_audit={"trust_state": "weak", "grounded": False, "reasons": ["confidence<0.45"]},
    )

    [updated] = await service._apply_ai_fixes(card, [issue])

    assert "product_dna" not in updated.ai_used_sources
    assert "photos" not in updated.ai_used_sources
    assert updated.ai_used_sources == ["card_characteristics"]
    assert updated.ai_evidence["visual_trust"] == {
        "trust_state": "weak",
        "grounded": False,
        "reasons": ["confidence<0.45"],
    }


def test_safety_gate_strips_untrusted_visual_sources() -> None:
    service = CardQualityAnalysisService()
    issue = RuleIssue(
        issue_code="wb_allowed_values",
        category="characteristics",
        severity="medium",
        title="Проверить комплектацию",
        business_explanation="candidate",
        recommended_fix="Проверить вручную",
        field_name="characteristics.Комплектация",
        suggested_value="костюм",
        ai_suggested_value="костюм",
        ai_used_sources=["product_dna", "photos", "card_characteristics"],
        ai_evidence={"observed": ["weak visual claim"]},
        source="ai",
    )
    card = _card(product_dna_audit={"trust_state": "weak", "grounded": False, "reasons": ["confidence<0.45"]})

    updated = service._apply_safety_gates(card, issue)

    assert updated.requires_human_check is True
    assert updated.suggested_value is None
    assert updated.ai_used_sources == ["card_characteristics"]
    assert updated.ai_evidence["visual_trust"]["grounded"] is False


def test_confirmed_suggestion_requires_real_non_media_non_review_value() -> None:
    service = CardQualityAnalysisService()
    no_value = _target_issue(suggested_value=None, ai_suggested_value=None, requires_human_check=False, category="title", field_name="title")
    review_value = _target_issue(ai_suggested_value="Черновик", requires_human_check=True, category="description", field_name="description")
    media_value = _target_issue(issue_code="media_no_video_info", category="media", field_name="video", suggested_value="Добавьте видео", requires_human_check=False)
    exact_value = _target_issue(category="characteristics", field_name="characteristics.Ткань", suggested_value="габардин", ai_suggested_value=None, requires_human_check=False)

    assert service._has_confirmed_suggestion(no_value) is False
    assert service._has_confirmed_suggestion(review_value) is False
    assert service._has_confirmed_suggestion(media_value) is False
    assert service._has_confirmed_suggestion(exact_value) is True


def test_issue_payload_keeps_review_ready_fields_separate() -> None:
    service = CardQualityAnalysisService()
    payload = service._issue_payload(_target_issue())

    assert payload["suggested_value"] is None
    assert payload["ai_suggested_value"] == "габардин"
    assert payload["requires_human_check"] is True
    assert payload["suggestion_kind"] == "candidate"
    assert payload["has_confirmed_suggestion"] is False


@pytest.mark.asyncio
async def test_ai_fix_retries_then_uses_valid_allowed_value() -> None:
    service = CardQualityAnalysisService()
    service.ai_fixer = SimpleNamespace(
        is_enabled=True,
        generate_fixes=AsyncMock(
            side_effect=[
                {
                    "0": {
                        "recommended_value": "атлас",
                        "reason": "first try",
                        "confidence": 0.9,
                        "requires_human_check": False,
                    }
                },
                {
                    "0": {
                        "recommended_value": "твид",
                        "reason": "retry fixed",
                        "confidence": 0.9,
                        "requires_human_check": False,
                    }
                },
            ]
        ),
    )
    issue = RuleIssue(
        issue_code="wb_allowed_values",
        category="characteristics",
        severity="medium",
        title="Проверить материал",
        business_explanation="allowed value mismatch",
        recommended_fix="Исправить",
        field_name="characteristics.Материал",
        current_value_json="атлас",
        allowed_values=["габардин", "твид"],
    )

    [updated] = await service._apply_ai_fixes(_card(), [issue])

    assert service.ai_fixer.generate_fixes.await_count == 2
    assert updated.requires_human_check is False
    assert updated.suggested_value == "твид"
    assert updated.ai_suggested_value == "твид"


def test_fixed_file_priority_excludes_ai_and_wins_with_exact_fix() -> None:
    service = CardQualityAnalysisService()
    card = _card(characteristics=[{"name": "Материал", "value": "атлас"}])
    issues = [
        RuleIssue(
            issue_code="wb_allowed_values",
            category="characteristics",
            severity="medium",
            title="AI material",
            business_explanation="ai",
            recommended_fix="ai",
            field_name="characteristics.Материал",
            current_value_json="атлас",
            suggested_value="габардин",
            source="ai",
        )
    ]

    [fixed_issue] = service._apply_fixed_file_priority(card, issues, {"Материал": "твид"})

    assert fixed_issue.source == "fixed_file"
    assert fixed_issue.suggested_value == "твид"
    assert fixed_issue.requires_human_check is False


def test_fingerprint_keeps_distinct_charc_ids_apart() -> None:
    rules = CardQualityRuleEngine()
    card = _card()
    base = {
        "issue_code": "wb_allowed_values",
        "category": "characteristics",
        "severity": "medium",
        "title": "Проверить характеристику",
        "business_explanation": "allowed value mismatch",
        "recommended_fix": "Исправить",
        "field_name": "characteristics.Материал",
        "current_value_json": "атлас",
    }

    first = RuleIssue(**base, charc_id=100)
    second = RuleIssue(**base, charc_id=200)

    assert rules.fingerprint(card, first) != rules.fingerprint(card, second)


def test_actionable_bucket_includes_human_check_non_media_issues() -> None:
    service = CardQualityAnalysisService()
    issue = _target_issue()

    assert service.issue_belongs_to_bucket(issue, "actionable") is True
    assert service.issue_belongs_to_bucket(issue, "human_check") is True
    assert service.issue_belongs_to_bucket(issue, "media") is False


def test_issue_fix_request_defaults_to_local_fix_only() -> None:
    from app.schemas.card_quality import CardQualityIssueFixRequest

    payload = CardQualityIssueFixRequest(fixed_value="Новое значение")

    assert payload.apply_to_wb is False
    assert payload.confirm is False
