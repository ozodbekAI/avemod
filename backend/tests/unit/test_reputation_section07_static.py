from __future__ import annotations

from pathlib import Path


def test_reputation_frontend_wires_draft_lifecycle_and_safe_publish() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    page_text = (repo_root / "frontend/src/routes/_authenticated/reputation.tsx").read_text(encoding="utf-8")
    portal_client_text = (repo_root / "frontend/src/lib/portal.ts").read_text(encoding="utf-8")
    endpoints_text = (repo_root / "frontend/src/lib/endpoints.ts").read_text(encoding="utf-8")

    for helper in (
        "syncReputation",
        "createReputationDraft",
        "approveReputationDraft",
        "regenerateReputationDraft",
        "rejectReputationDraft",
        "publishReputationDraft",
        "markReputationNoReply",
    ):
        assert helper in portal_client_text
        assert helper in page_text

    for endpoint in (
        "reputationSync",
        "reputationDraftApprove",
        "reputationDraftRegenerate",
        "reputationDraftReject",
        "reputationDraftPublish",
        "reputationNoReply",
    ):
        assert endpoint in endpoints_text

    assert "confirm: true" in page_text
    assert "publishEnabled && !!draftId" in page_text
    assert "itemType" in page_text


def test_reputation_backend_keeps_local_primary_and_per_source_status() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    service_text = (repo_root / "backend/app/services/reputation.py").read_text(encoding="utf-8")
    portal_text = (repo_root / "backend/app/services/portal.py").read_text(encoding="utf-8")
    router_text = (repo_root / "backend/app/modules/portal/router.py").read_text(encoding="utf-8")

    assert "per_source_status" in service_text
    assert "chats_not_configured" in service_text
    assert "self.reputation.list_inbox" in portal_text
    assert "self.reputation.summary" in portal_text
    assert "self.reputation.sync_reputation" in portal_text
    assert "self.reputation.product_360" in portal_text
    assert "self.reputation.reputation_actions" in portal_text

    for route in (
        '"/portal/reputation/inbox"',
        '"/portal/reputation/summary"',
        '"/portal/reputation/sync"',
        '"/portal/reputation/items/{item_id}/draft"',
        '"/portal/reputation/items/{item_id}/no-reply-needed"',
        '"/portal/reputation/drafts/{draft_id}/approve"',
        '"/portal/reputation/drafts/{draft_id}/regenerate"',
        '"/portal/reputation/drafts/{draft_id}/reject"',
        '"/portal/reputation/drafts/{draft_id}/publish"',
        '"/portal/reputation/settings"',
    ):
        assert route in router_text


def test_reputation_audit_doc_covers_section_07_contract() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    audit_text = (repo_root / "docs/final_integration/REPUTATION_AUDIT.md").read_text(encoding="utf-8")

    for required in (
        "reviews",
        "questions",
        "chats",
        "sync runs",
        "inbox",
        "summary",
        "classification",
        "draft",
        "edit",
        "regenerate",
        "approve",
        "reject",
        "no-reply",
        "safe publish",
        "settings",
        "Product 360",
        "Actions",
        "Doctor",
        "Results",
        "per-source",
        "does not disable reviews/questions",
    ):
        assert required in audit_text
