from __future__ import annotations

from pathlib import Path


def test_checker_ui_separates_local_fix_from_explicit_wb_apply() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    route_text = (repo_root / "frontend/src/routes/_authenticated/checker.$nmId.tsx").read_text(encoding="utf-8")
    client_text = (repo_root / "frontend/src/lib/portal.ts").read_text(encoding="utf-8")

    assert "Применить" in route_text
    assert "Подтвердить раздел" in route_text
    assert "Проблемные" in route_text
    assert "Пустые" in route_text
    assert "Отправить в WB" in route_text
    assert "apply_to_wb: false" in route_text
    assert "confirm: true" in route_text
    assert "manual_review_required_status_only" in route_text
    assert "fixed_value" in client_text
    assert "apply_to_wb" in client_text
    assert "previewCardQualityIssueApply" in client_text


def test_checker_ui_keeps_source_issue_fix_editor_flow() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    route_text = (repo_root / "frontend/src/routes/_authenticated/checker.$nmId.tsx").read_text(encoding="utf-8")
    client_text = (repo_root / "frontend/src/lib/portal.ts").read_text(encoding="utf-8")

    assert "getSwapInfo" in route_text
    assert "getCompoundFixes" in route_text
    assert "SourceFixPreview" in route_text
    assert "SourceCharacteristicsTab" in route_text
    assert "SourceDescriptionTab" in route_text
    assert "Draft fix value" in route_text
    assert "Открыть фотостудию" in route_text
    assert "Передать" in route_text
    assert "fetchCardQualityQueueProgress" in client_text
    assert "fetchCardQualityFixedFileStatus" in client_text


def test_checker_ui_uses_source_pipeline_order_before_severity() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    route_text = (repo_root / "frontend/src/routes/_authenticated/checker.$nmId.tsx").read_text(encoding="utf-8")

    assert "function sourceOrder" in route_text
    assert "issue?.source_order" in route_text
    assert "const order = sourceOrder(a) - sourceOrder(b)" in route_text
    assert route_text.index("const order = sourceOrder(a) - sourceOrder(b)") < route_text.index("const rank = severityRank(a) - severityRank(b)")


def test_action_center_checker_flow_keeps_evidence_status_and_recheck_visible() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    route_text = (repo_root / "frontend/src/routes/_authenticated/action-center.tsx").read_text(encoding="utf-8")
    container_text = (repo_root / "frontend/src/components/action-center/ActionCenterPageContainer.tsx").read_text(encoding="utf-8")
    mutations_text = (repo_root / "frontend/src/hooks/action-center/useActionCenterMutations.ts").read_text(encoding="utf-8")

    assert "ActionCenterPageContainer" in route_text
    assert "EvidenceDrawer" in container_text
    assert "EvidenceButton" in container_text
    assert "Перепроверить" in container_text
    assert "checker-product-quality" in container_text
    assert "ActionCenterHistoryTimeline" in container_text
    assert "source_sync_state" in container_text
    assert "can_update_reason" in container_text
    assert "updateActionBySource" in container_text
    assert "updateActionBySource" in mutations_text
