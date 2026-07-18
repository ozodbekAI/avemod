from __future__ import annotations

from pathlib import Path


def test_cost_mutations_refresh_dq_and_snapshots() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    router_text = (repo_root / "backend/app/modules/manual_costs/router.py").read_text(encoding="utf-8")
    audit_text = (repo_root / "docs/final_integration/DATA_READINESS_COSTS_AUDIT.md").read_text(encoding="utf-8")

    assert "DataQualityService" in router_text
    assert "async def _refresh_dq_and_snapshots" in router_text
    assert "data_quality_service.run_checks" in router_text
    assert router_text.count("_refresh_dq_and_snapshots") >= 6

    for required in (
        "missing cost",
        "finance mismatch",
        "unmatched SKU",
        "order lifecycle incomplete",
        "stock without sales",
        "sales without fresh stock",
        "template",
        "upload",
        "preview",
        "confirm",
        "DQ refresh",
    ):
        assert required in audit_text


def test_data_fix_does_not_show_raw_blocker_code_in_card_header() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    data_fix_text = (repo_root / "frontend/src/routes/_authenticated/data-fix.tsx").read_text(encoding="utf-8")

    assert "Блокер #{index + 1}" in data_fix_text
    assert '<span className="text-[11px] text-muted-foreground font-mono">{blocker.code}</span>' not in data_fix_text
