from __future__ import annotations

from pathlib import Path


def test_section03_finance_formula_docs_cover_required_metrics() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    dictionary = (repo_root / "docs/final_integration/FINANCE_METRIC_DICTIONARY.md").read_text(encoding="utf-8")
    audit = (repo_root / "docs/final_integration/FINANCE_FORMULA_AUDIT.md").read_text(encoding="utf-8")
    money_tests = (repo_root / "backend/tests/unit/test_money_management_service.py").read_text(encoding="utf-8")
    marts_tests = (repo_root / "backend/tests/unit/test_marts_and_quality.py").read_text(encoding="utf-8")

    required_terms = [
        "revenue",
        "for_pay",
        "WB expenses",
        "COGS",
        "ads spend",
        "estimated profit",
        "owner profit",
        "margin",
        "ROI",
        "average order value",
        "return rate",
        "stock value",
        "days of stock",
        "money at risk",
        "nm_id=245405620",
    ]
    combined_docs = f"{dictionary}\n{audit}"
    for term in required_terms:
        assert term in combined_docs

    assert "profit_formula_valid is True" in money_tests
    assert "total_seller_expenses" in marts_tests
    assert "seller_other_expense" in marts_tests
