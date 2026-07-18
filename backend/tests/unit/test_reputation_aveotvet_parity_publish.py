from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.core.config import Settings
from app.schemas.operator import ExternalStatus
from app.schemas.reputation import ReputationNoReplyRequest, ReputationPublishRequest
from app.services.reputation import ReputationService
from app.services.reputation_adapter import ReputationAdapter


class _NoopSession:
    def __init__(self) -> None:
        self.added: list[object] = []
        self.commits = 0

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.commits += 1

    async def refresh(self, obj):
        return None


def _account() -> SimpleNamespace:
    return SimpleNamespace(id=1, external_account_id="10", name="Account 1")


def _draft(**overrides):
    data = {
        "id": 77,
        "account_id": 1,
        "source_module": "reputation",
        "external_id": "review:fb-1",
        "draft_type": "review_reply",
        "external_status": "draft_ready",
        "status": "new",
        "title": "Reply draft",
        "body_text": "Draft reply",
        "payload_json": {"item_id": "review:fb-1", "source_type": "review", "source_id": "fb-1"},
        "created_at": None,
        "updated_at": None,
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def _item(**overrides):
    data = {
        "id": 10,
        "account_id": 1,
        "item_type": "review",
        "external_id": "fb-1",
        "rating": 5,
        "status": "draft_ready",
        "needs_reply": True,
        "answer_text": None,
        "answer_state": None,
        "answer_editable": None,
        "raw_json": {},
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def _settings() -> SimpleNamespace:
    return SimpleNamespace(blacklist_keywords_json=[], signature=None)


@pytest.mark.asyncio
async def test_publish_requires_confirmation_before_any_io(monkeypatch: pytest.MonkeyPatch) -> None:
    service = ReputationService(Settings(enable_reputation_publish=True))
    publish_calls: list[str] = []

    async def fake_publish(*args, **kwargs):
        publish_calls.append("called")

    monkeypatch.setattr(service, "_publish_wb", fake_publish)

    result = await service.publish_reply(
        _NoopSession(),
        _account(),
        draft_id="77",
        request=ReputationPublishRequest(confirm=False),
        user_id=501,
    )

    assert result.success is False
    assert result.event_type == "publish_blocked_confirmation_required"
    assert result.warnings == ["manual_confirm_required"]
    assert publish_calls == []


@pytest.mark.asyncio
async def test_publish_requires_approved_draft_even_when_confirmed(monkeypatch: pytest.MonkeyPatch) -> None:
    service = ReputationService(Settings(enable_reputation_publish=True))

    async def fake_find_draft(session, *, account_id: int, draft_id: str):
        return _draft(status="new")

    monkeypatch.setattr(service, "_find_draft", fake_find_draft)

    result = await service.publish_reply(
        _NoopSession(),
        _account(),
        draft_id="77",
        request=ReputationPublishRequest(confirm=True),
        user_id=501,
    )

    assert result.success is False
    assert result.event_type == "publish_blocked_approved_draft_required"
    assert result.warnings == ["approved_draft_required"]


@pytest.mark.asyncio
async def test_publish_blocked_when_feature_flag_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    service = ReputationService(Settings(enable_reputation_publish=False))
    find_calls: list[str] = []

    async def fake_find_draft(*args, **kwargs):
        find_calls.append("called")
        return _draft(status="done")

    monkeypatch.setattr(service, "_find_draft", fake_find_draft)

    result = await service.publish_reply(
        _NoopSession(),
        _account(),
        draft_id="77",
        request=ReputationPublishRequest(confirm=True),
        user_id=501,
    )

    assert result.success is False
    assert result.event_type == "publish_disabled_by_feature_flag"
    assert result.warnings == ["reputation_publish_disabled"]
    assert find_calls == []


@pytest.mark.asyncio
async def test_publish_approved_draft_updates_review_state_after_wb_submit(monkeypatch: pytest.MonkeyPatch) -> None:
    service = ReputationService(Settings(enable_reputation_publish=True))
    draft = _draft(status="done", body_text="Approved reply")
    item = _item()
    published: list[tuple[object, object, str]] = []

    async def fake_find_draft(session, *, account_id: int, draft_id: str):
        return draft

    async def fake_find_item(session, *, account_id: int, item_id: str):
        return item

    async def fake_feedbacks_questions_token(session, *, account_id: int):
        return "wb-token"

    async def fake_settings(session, *, account_id: int):
        return _settings()

    async def fake_publish(session, *, account_id: int, token: str, row, text: str):
        assert account_id == 1
        published.append((token, row, text))

    monkeypatch.setattr(service, "_find_draft", fake_find_draft)
    monkeypatch.setattr(service, "_find_item", fake_find_item)
    monkeypatch.setattr(service, "_feedbacks_questions_token", fake_feedbacks_questions_token)
    monkeypatch.setattr(service, "_settings", fake_settings)
    monkeypatch.setattr(service, "_publish_wb", fake_publish)

    result = await service.publish_reply(
        _NoopSession(),
        _account(),
        draft_id="77",
        request=ReputationPublishRequest(confirm=True),
        user_id=501,
    )

    assert result.success is True
    assert result.external_status == ExternalStatus.SUBMITTED
    assert item.status == "answered"
    assert item.needs_reply is False
    assert item.answer_text == "Approved reply"
    assert item.answer_state == "published"
    assert draft.external_status == ExternalStatus.SUBMITTED.value
    assert draft.payload_json["external_submit_attempted"] is True
    assert published == [("wb-token", item, "Approved reply")]


@pytest.mark.asyncio
async def test_publish_blocked_without_wb_feedbacks_questions_token(monkeypatch: pytest.MonkeyPatch) -> None:
    service = ReputationService(Settings(enable_reputation_publish=True))
    draft = _draft(status="done", body_text="Approved reply")
    item = _item()
    published: list[str] = []

    async def fake_find_draft(session, *, account_id: int, draft_id: str):
        return draft

    async def fake_find_item(session, *, account_id: int, item_id: str):
        return item

    async def fake_feedbacks_questions_token(session, *, account_id: int):
        return None

    async def fake_publish(*args, **kwargs):
        published.append("called")

    monkeypatch.setattr(service, "_find_draft", fake_find_draft)
    monkeypatch.setattr(service, "_find_item", fake_find_item)
    monkeypatch.setattr(service, "_feedbacks_questions_token", fake_feedbacks_questions_token)
    monkeypatch.setattr(service, "_publish_wb", fake_publish)

    result = await service.publish_reply(
        _NoopSession(),
        _account(),
        draft_id="77",
        request=ReputationPublishRequest(confirm=True),
        user_id=501,
    )

    assert result.success is False
    assert result.event_type == "publish_not_configured"
    assert result.warnings == ["wb_feedbacks_questions_token_not_configured"]
    assert published == []


@pytest.mark.asyncio
async def test_no_reply_needed_sets_semantic_state_and_rejects_active_draft(monkeypatch: pytest.MonkeyPatch) -> None:
    service = ReputationService()
    item = _item(status="needs_reply", needs_reply=True)
    active_draft = _draft(status="new", body_text="Draft that should be rejected")

    async def fake_find_item(session, *, account_id: int, item_id: str):
        return item

    async def fake_find_draft(session, *, account_id: int, draft_id: str):
        return active_draft

    monkeypatch.setattr(service, "_find_item", fake_find_item)
    monkeypatch.setattr(service, "_find_draft", fake_find_draft)

    result = await service.mark_no_reply_needed(
        _NoopSession(),
        _account(),
        item_id="review:fb-1",
        request=ReputationNoReplyRequest(confirm=True, reason="operator_no_reply_needed"),
        user_id=700,
    )

    assert result.success is True
    assert item.status in {"ignored", "closed"}
    assert item.needs_reply is False
    assert item.answer_text == "—"
    assert item.answer_state == "no_reply_needed"
    assert item.answer_editable is False
    assert active_draft.status == "rejected"
    assert active_draft.payload_json["closed_by_no_reply_needed"] is True


@pytest.mark.asyncio
async def test_regenerate_stores_generation_metadata_and_previous_relation(monkeypatch: pytest.MonkeyPatch) -> None:
    service = ReputationService(Settings(reputation_enabled=True))
    draft = _draft(
        status="done",
        body_text="Old reply",
        payload_json={
            "item_id": "review:fb-1",
            "source_type": "review",
            "source_id": "fb-1",
            "generation": {"source": "local_rules", "debug_trace": {"instructions": "old"}},
            "approved_by": 44,
            "approved_at": "2026-01-01T00:00:00+00:00",
            "approval_scope": "local_draft_only",
        },
    )
    item = _item(text="Хороший товар", raw_json={})
    generation_meta = {
        "source": "local_rules",
        "fallback": True,
        "fallback_reason": "ai_provider_disabled",
        "category_instruction_plan": {"primary_review_category": "positive"},
        "debug_trace": {"instructions": "new", "input_text": "buyer"},
    }

    async def fake_find_draft(session, *, account_id: int, draft_id: str):
        return draft

    async def fake_find_item(session, *, account_id: int, item_id: str):
        return item

    async def fake_settings(session, *, account_id: int):
        return _settings()

    async def fake_reply_text(*args, **kwargs):
        return "New reply", generation_meta

    monkeypatch.setattr(service, "_find_draft", fake_find_draft)
    monkeypatch.setattr(service, "_find_item", fake_find_item)
    monkeypatch.setattr(service, "_settings", fake_settings)
    monkeypatch.setattr(service, "_reply_text", fake_reply_text)

    result = await service.regenerate_draft(
        _NoopSession(),
        _account(),
        draft_id="77",
        request=SimpleNamespace(reason="operator_regenerate", payload={"force_ai": False}),
    )

    assert result.status == "ok"
    assert draft.status == "new"
    assert draft.body_text == "New reply"
    assert draft.payload_json["regenerated_from_draft_id"] == "77"
    assert draft.payload_json["previous_generation"]["debug_trace"]["instructions"] == "old"
    assert draft.payload_json["generation"]["debug_trace"]["instructions"] == "new"
    assert draft.payload_json["approved_by"] is None
    assert draft.payload_json["external_submit_attempted"] is False
    assert item.raw_json["local_instruction_plan"]["primary_review_category"] == "positive"


@pytest.mark.xfail(strict=True, reason="external publish disabled by feature flag")
@pytest.mark.asyncio
async def test_external_adapter_publish_contract_is_disabled_until_feature_flag_is_enabled() -> None:
    adapter = ReputationAdapter(
        Settings(
            reputation_enabled=True,
            reputation_base_url="http://reputation.internal",
            reputation_shop_map={"1": 10},
            enable_reputation_publish=False,
        )
    )

    result = await adapter.publish_reply(
        _account(),
        draft_id="review:fb-1",
        request=ReputationPublishRequest(confirm=True, text="Approved reply"),
    )

    assert result.success is True
    assert result.event_type == "publish_confirmed"
