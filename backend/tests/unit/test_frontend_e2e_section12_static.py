from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT.parent / "frontend"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_frontend_has_first_party_playwright_e2e_harness() -> None:
    package = json.loads(_read(FRONTEND / "package.json"))
    config = _read(FRONTEND / "playwright.config.ts")
    spec = _read(FRONTEND / "e2e" / "navigation.spec.ts")
    mock = _read(FRONTEND / "e2e" / "mock-api.ts")

    assert package["scripts"]["test:e2e"] == "playwright test"
    assert "@playwright/test" in package["devDependencies"]
    assert "channel: \"chrome\"" in config
    assert "webServer" in config
    assert "Desktop Chrome" in config
    assert "Pixel 5" in config
    assert "installMockApi" in spec
    assert "**/api/v1/**" in mock


def test_frontend_e2e_covers_canonical_navigation_and_states() -> None:
    spec = _read(FRONTEND / "e2e" / "navigation.spec.ts")

    for phrase in (
        "authenticated canonical navigation",
        "product 360 deep link",
        "empty beta page",
        "API failures render a page error state",
        "mobile viewport",
        "Корреляция, а не гарантия",
        "Проектов пока нет",
        "Не удалось загрузить результаты",
        "До действия",
        "После изменения",
    ):
        assert phrase in spec


def test_canonical_frontend_routes_exist_for_main_navigation() -> None:
    expected_routes = [
        "dashboard.tsx",
        "doctor.tsx",
        "action-center.tsx",
        "products.index.tsx",
        "products.$nmId.tsx",
        "results.tsx",
        "data-fix.tsx",
        "settings.tsx",
        "money.tsx",
        "finance.tsx",
        "costs.tsx",
        "photo-studio.tsx",
        "photo-studio.projects.$projectId.tsx",
        "grouping.tsx",
        "stock-control.tsx",
        "reputation.tsx",
        "claims.tsx",
    ]
    for route in expected_routes:
        assert (FRONTEND / "src" / "routes" / "_authenticated" / route).exists(), route


def test_api_endpoint_map_blocks_stale_ui_paths_and_covers_recent_modules() -> None:
    api = _read(FRONTEND / "src" / "lib" / "api.ts")
    endpoints = _read(FRONTEND / "src" / "lib" / "endpoints.ts")

    for invalid in ('"/money"', '"/cards"', '"/sku"', '"/data-fix"', '"/costs"', '"/finance"', '"/operations"'):
        assert invalid in api

    for endpoint_name in (
        "photoVersionExperiment",
        "photoProjectAssetUpload",
        "photoVersionReview",
        "groupingPreview",
        "claimCandidates",
        "reputationSync",
        "stockControlRuns",
        "results",
    ):
        assert endpoint_name in endpoints


def test_action_center_marks_reputation_as_beta_and_warns_about_publish() -> None:
    container = _read(FRONTEND / "src" / "components" / "action-center" / "ActionCenterPageContainer.tsx")
    adapter = _read(ROOT / "app" / "services" / "reputation_adapter.py")

    assert '{ value: "reputation", label: "Репутация" }' in container
    assert 'reputation: () => "/reputation"' in container
    assert "external_reputation_recommendation" in container
    assert "подготовьте черновик" in container
    assert "canUpdateReasonLabel" in container
    assert 'source_module="reputation"' in adapter
    assert 'can_update_reason="external_reputation_recommendation"' in adapter
