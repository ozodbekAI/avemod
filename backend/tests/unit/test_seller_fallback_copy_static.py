from __future__ import annotations

from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[2]

SELLER_COPY_FILES = [
    "app/schemas/portal.py",
    "app/services/portal.py",
    "app/services/result_tracking.py",
    "app/services/claims_factory.py",
    "app/services/reputation_adapter.py",
    "scripts/seed_ai_operator_demo.py",
    "tests/fixtures/portal/actions_page_ok.json",
    "tests/fixtures/portal/claims_submit_blocked.json",
    "tests/fixtures/portal/product_360_contract_ok.json",
    "tests/fixtures/portal/product_360_ok.json",
    "tests/fixtures/portal/reputation_publish_blocked.json",
    "tests/fixtures/portal/result_summary_windows_ok.json",
    "tests/fixtures/portal/results_unified_ok.json",
]

FORBIDDEN_ENGLISH_FALLBACKS = [
    "Action Center item generated from a module signal.",
    "Complete the action or refresh /portal/actions after source data changes.",
    "Product row combines money, stock, card quality and action signals for this nm_id.",
    "Refresh Product 360 after source module sync or analysis.",
    "Correlation only; result events do not prove causation.",
    "correlation, not guaranteed causality",
    "Before/after results are observed correlation, not proven causality.",
    "Before/after windows show correlation only; they do not prove causation.",
    "Expected impact is not converted to saved money until post-action data is measured.",
    "Product 360 section status returned by the owning module.",
    "Product 360 joins module sections for one nm_id.",
    "Product 360 aggregates module evidence for this nm_id.",
    "Статус раздела Product 360",
    "Обновите Product 360",
    "Product 360 объединяет",
    "Refresh /portal/products after money sync, card-quality analysis, or action updates.",
    "Refresh /portal/products/{nm_id} after source data changes.",
    "Manual confirmation required",
    "Claims submission requires explicit confirm=true.",
    "Publishing requires explicit confirm=true.",
]


def _read(relative_path: str) -> str:
    return (BACKEND_ROOT / relative_path).read_text(encoding="utf-8")


def test_backend_seller_fallback_copy_is_russian() -> None:
    combined = "\n".join(_read(path) for path in SELLER_COPY_FILES)

    for phrase in FORBIDDEN_ENGLISH_FALLBACKS:
        assert phrase not in combined


def test_synthetic_evidence_detection_uses_stable_contract() -> None:
    portal_schema = _read("app/schemas/portal.py")

    assert "is_synthetic=True" in portal_schema
    assert "bool(self.evidence_ledger.is_synthetic)" in portal_schema
    assert 'formula_code.startswith("portal_action.")' in portal_schema
    assert "formula_human ==" not in portal_schema
    assert "Action Center item generated from a module signal." not in portal_schema
