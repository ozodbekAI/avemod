from __future__ import annotations

from pathlib import Path


def test_products_aggregate_exposes_card_quality_contract() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    schema_text = (repo_root / "backend/app/schemas/portal.py").read_text(encoding="utf-8")
    router_text = (repo_root / "backend/app/modules/portal/router.py").read_text(encoding="utf-8")
    service_text = (repo_root / "backend/app/services/portal.py").read_text(encoding="utf-8")
    products_text = (repo_root / "frontend/src/routes/_authenticated/products.index.tsx").read_text(encoding="utf-8")

    for field in (
        "card_quality_state",
        "card_quality_score",
        "card_quality_issue_count",
        "card_quality_photo_count",
        "card_quality_analyzed_at",
    ):
        assert field in schema_text
        assert field in products_text or field in service_text

    assert "card_quality_status" in router_text
    assert '"quality_score"' in router_text
    assert '"quality_issues"' in router_text
    assert "CardQualitySnapshot" in service_text
    assert "CardQualityIssue" in service_text
    assert "async def _enrich_product_rows_with_card_quality" in service_text
    assert "def _filter_sort_product_rows_by_card_quality" in service_text

    assert "SelectItem value=\"critical\"" in products_text
    assert "SelectItem value=\"warning\"" in products_text
    assert "SelectItem value=\"not_analyzed\"" in products_text
    assert "quality_score" in products_text
    assert "qualityIssues" in products_text


def test_product_360_and_data_fix_cover_required_quality_fields() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    product_360_text = (repo_root / "frontend/src/routes/_authenticated/products.$nmId.tsx").read_text(encoding="utf-8")
    data_fix_text = (repo_root / "frontend/src/routes/_authenticated/data-fix.tsx").read_text(encoding="utf-8")
    audit_text = (repo_root / "docs/final_integration/CARD_QUALITY_AUDIT.md").read_text(encoding="utf-8")

    for required in (
        "categoryScores",
        "photosCount",
        "analyzedAt",
        "Открытых проблем",
        "Score по категориям",
    ):
        assert required in product_360_text

    for issue_code in (
        "title_missing",
        "title_too_short",
        "description_missing",
        "description_too_short",
        "characteristics_missing",
        "media_no_images",
        "media_too_few_images",
        "media_invalid_url",
    ):
        assert issue_code in data_fix_text

    for required in (
        "Eligible count",
        "Unique analyzed",
        "Coverage",
        "Actionable issues",
        "Info observations",
        "Category scores",
        "Photo count",
        "Analyzed at",
        "page-bounded",
    ):
        assert required in audit_text


def test_local_card_quality_stays_primary_with_checker_fallback() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    portal_text = (repo_root / "backend/app/services/portal.py").read_text(encoding="utf-8")
    doctor_text = (repo_root / "backend/app/services/diagnosis/profit_doctor.py").read_text(encoding="utf-8")

    assert "local_quality = await self.card_quality.product_quality" in portal_text
    assert 'not in {"unavailable", "not_configured", "empty", "not_analyzed"}' in portal_text
    assert "return local_quality" in portal_text
    assert "self.checker.product_quality" in portal_text
    assert "CardQualityAnalysisService" in doctor_text
