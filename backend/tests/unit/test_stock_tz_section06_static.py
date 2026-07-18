from __future__ import annotations

from pathlib import Path


def test_store_balance_is_real_local_run_not_disabled_placeholder() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    schema_text = (repo_root / "backend/app/schemas/stock_control.py").read_text(encoding="utf-8")
    service_text = (repo_root / "backend/app/services/stock_control/service.py").read_text(encoding="utf-8")
    router_text = (repo_root / "backend/app/modules/stock_control/router.py").read_text(encoding="utf-8")
    endpoints_text = (repo_root / "frontend/src/lib/endpoints.ts").read_text(encoding="utf-8")
    store_wizard_text = (repo_root / "frontend/src/components/stock-control/StoreBalanceWizard.tsx").read_text(encoding="utf-8")

    assert 'StockControlRunTypeWithPlanned = Literal["return_excess", "ship_from_hand", "store_balance"]' in schema_text
    assert "store_balance is planned for phase 2" not in schema_text
    assert "target_account_id is required for store_balance" in schema_text
    assert "StockControlStoreBalancePreviewRequest" in schema_text

    assert "compute_store_balance" in service_text
    assert "async def preview_store_balance" in service_text
    assert 'run.run_type == "store_balance"' in service_text
    assert '"marketplace_change": False' in service_text

    assert '"/portal/stock-control/preview"' in router_text
    assert "payload.target_account_id" in router_text
    assert 'stockControlPreview:         "/portal/stock-control/preview"' in endpoints_text
    assert 'run_type: "store_balance"' in store_wizard_text
    assert 'kind: "store_balance"' in store_wizard_text


def test_stock_tz_audit_doc_covers_required_section_06_items() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    audit_text = (repo_root / "docs/final_integration/STOCK_TZ_AUDIT.md").read_text(encoding="utf-8")

    for required in (
        "return_excess",
        "ship_from_hand",
        "store_balance",
        "regional supply import",
        "hand stock template",
        "warehouse-region mapping",
        "run lifecycle",
        "movements",
        "export",
        "Product 360",
        "Actions",
        "Doctor",
        "Size safety",
        "excluded regions",
        "default IL",
        "largest remainder",
        "total quantity preservation",
        "No automatic WB operation",
    ):
        assert required in audit_text
