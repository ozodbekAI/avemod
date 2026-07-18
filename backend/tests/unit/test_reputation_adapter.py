from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core.config import Settings
from app.schemas.reputation import (
    ReputationDraftDecisionRequest,
    ReputationNoReplyRequest,
    ReputationPublishRequest,
    ReputationSettingsUpdateRequest,
)
from app.services.reputation_adapter import ReputationAdapter


FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "reputation"


def _account() -> SimpleNamespace:
    return SimpleNamespace(id=1, external_account_id=None, name="main")


def _fixture(name: str) -> dict:
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


@pytest.mark.asyncio
async def test_reputation_adapter_normalizes_inbox_and_actions_without_secrets() -> None:
    adapter = ReputationAdapter(
        Settings(
            reputation_enabled=True,
            reputation_base_url="http://reputation.internal",
            reputation_shop_map={"1": 10},
            reputation_internal_token="secret-token",
        )
    )
    review_payload = {
        "items": [
            {
                "wb_id": "fb1",
                "rating": 1,
                "text": "Bad quality",
                "user_name": "Customer Name",
                "product_details": {"nmId": 1001, "productName": "Product"},
                "token": "must-not-leak",
            }
        ]
    }
    adapter._request = AsyncMock(side_effect=[review_payload, {"items": []}, {"items": []}] * 2)

    inbox = await adapter.list_inbox(_account(), limit=20, offset=0)
    actions, unavailable = await adapter.reputation_actions(_account(), limit=20)

    assert inbox.status == "ok"
    assert inbox.total == 1
    assert inbox.items[0].id == "review:fb1"
    assert inbox.items[0].item_id == "review:fb1"
    assert inbox.items[0].kind == "review"
    assert inbox.items[0].status == "needs_reply"
    assert inbox.items[0].nm_id == 1001
    assert inbox.items[0].priority == "P1"
    assert inbox.items[0].buyer_name == "C***"
    assert inbox.items[0].source_payload["product_details"]["nmId"] == 1001
    assert "token" not in inbox.items[0].source_payload
    assert unavailable is None
    assert actions[0].source_module == "reputation"
    assert actions[0].action_type == "negative_review_unanswered"
    assert "must-not-leak" not in str(inbox.model_dump(mode="json"))
    assert "secret-token" not in str(inbox.model_dump(mode="json"))


@pytest.mark.asyncio
async def test_reputation_adapter_generate_draft_uses_review_endpoint() -> None:
    adapter = ReputationAdapter(
        Settings(
            reputation_enabled=True,
            reputation_base_url="http://reputation.internal",
            reputation_shop_map={"1": 10},
            enable_reputation_publish=True,
        )
    )
    adapter._request = AsyncMock(return_value={"id": "d1", "text": "Hello, we will check this."})

    result = await adapter.generate_draft(_account(), item_id="review:fb1")

    assert result.status == "ok"
    assert result.draft is not None
    assert result.draft.id == "d1"
    assert result.draft.requires_confirmation is True
    adapter._request.assert_awaited_once()
    assert adapter._request.await_args.args[:2] == ("POST", "/feedbacks/10/fb1/draft")


@pytest.mark.asyncio
async def test_reputation_adapter_inbox_type_filters_use_backend7_paths_and_scrub_private_fields() -> None:
    adapter = ReputationAdapter(
        Settings(
            reputation_enabled=True,
            reputation_base_url="http://reputation.internal",
            reputation_shop_map={"1": 10},
            enable_reputation_publish=True,
        )
    )

    cases = [
        (
            "review",
            {"wb_id": "fb1", "rating": 2, "text": "Bad", "user_name": "Private Buyer", "product_details": {"nmId": 1001}},
            ("GET", "/feedbacks/10"),
            "Private Buyer",
        ),
        (
            "question",
            {"id": "q1", "text": "Size?", "user_name": "Question Buyer", "product_details": {"nmId": 1002}},
            ("GET", "/questions/10"),
            "Question Buyer",
        ),
        (
            "chat",
            {
                "chat_id": "c1",
                "client_name": "Chat Buyer",
                "last_message": {"text": "Hello"},
                "good_card": {"nmID": 1003, "title": "Bag"},
            },
            ("GET", "/chats/10"),
            "Chat Buyer",
        ),
    ]

    for item_type, payload, expected_call, private_value in cases:
        adapter._request = AsyncMock(return_value=[payload])

        inbox = await adapter.list_inbox(_account(), item_type=item_type, limit=7, offset=0)

        assert inbox.status == "ok"
        assert inbox.total == 1
        assert inbox.items[0].item_type == item_type
        assert adapter._request.await_args.args[:2] == expected_call
        assert adapter._request.await_args.kwargs["params"] == {"limit": 7, "offset": 0}
        assert private_value not in str(inbox.model_dump(mode="json"))


@pytest.mark.asyncio
async def test_reputation_adapter_generate_draft_uses_question_and_chat_backend7_paths() -> None:
    adapter = ReputationAdapter(
        Settings(
            reputation_enabled=True,
            reputation_base_url="http://reputation.internal",
            reputation_shop_map={"1": 10},
        )
    )
    adapter._request = AsyncMock(
        side_effect=[
            {"id": "dq1", "text": "Question answer"},
            {"id": "dc1", "text": "Chat answer"},
        ]
    )

    question = await adapter.generate_draft(_account(), item_id="question:q1")
    chat = await adapter.generate_draft(_account(), item_id="chat:c1")

    assert question.status == "ok"
    assert question.draft is not None
    assert question.draft.id == "dq1"
    assert chat.status == "ok"
    assert chat.draft is not None
    assert chat.draft.id == "dc1"
    assert [call.args[:2] for call in adapter._request.await_args_list] == [
        ("POST", "/questions/10/q1/draft"),
        ("POST", "/chats/10/c1/draft"),
    ]


@pytest.mark.asyncio
async def test_reputation_adapter_publish_requires_manual_confirm() -> None:
    adapter = ReputationAdapter(
        Settings(
            reputation_enabled=True,
            reputation_base_url="http://reputation.internal",
            reputation_shop_map={"1": 10},
        )
    )
    adapter._request = AsyncMock()

    result = await adapter.publish_reply(
        _account(),
        draft_id="review:fb1",
        request=ReputationPublishRequest(confirm=False),
    )

    assert result.success is False
    assert result.event_type == "publish_blocked_confirmation_required"
    assert result.data["external_submit_attempted"] is False
    assert result.data["external_write_enabled"] is False
    assert result.data["local_only"] is False
    adapter._request.assert_not_called()


@pytest.mark.asyncio
async def test_reputation_adapter_publish_disabled_by_default_even_with_confirm() -> None:
    adapter = ReputationAdapter(
        Settings(
            reputation_enabled=True,
            reputation_base_url="http://reputation.internal",
            reputation_shop_map={"1": 10},
        )
    )
    adapter._request = AsyncMock()

    result = await adapter.publish_reply(
        _account(),
        draft_id="review:fb1",
        request=ReputationPublishRequest(confirm=True),
    )

    assert result.success is False
    assert result.event_type == "publish_disabled_by_feature_flag"
    assert result.warnings == ["reputation_publish_disabled"]
    assert result.data["external_submit_attempted"] is False
    assert result.data["external_write_enabled"] is False
    assert result.data["local_only"] is True
    adapter._request.assert_not_called()


@pytest.mark.asyncio
async def test_reputation_adapter_reports_not_configured_without_mapping() -> None:
    adapter = ReputationAdapter(Settings(reputation_enabled=True, reputation_base_url="http://reputation.internal"))

    inbox = await adapter.list_inbox(_account(), limit=10, offset=0)

    assert inbox.status == "not_configured"
    assert "reputation" in inbox.unavailable_sources


@pytest.mark.asyncio
async def test_reputation_adapter_filters_inbox_and_builds_summary() -> None:
    adapter = ReputationAdapter(
        Settings(
            reputation_enabled=True,
            reputation_base_url="http://reputation.internal",
            reputation_shop_map={"1": 10},
        )
    )
    adapter._request = AsyncMock(
        side_effect=[
            {
                "items": [
                    {
                        "wb_id": "fb1",
                        "rating": 1,
                        "text": "Bad",
                        "created_date": "2026-06-10T10:00:00+00:00",
                        "product_details": {"nmId": 1001},
                    },
                    {
                        "wb_id": "fb2",
                        "rating": 5,
                        "text": "Good",
                        "created_date": "2026-06-10T11:00:00+00:00",
                        "product_details": {"nmId": 1002},
                    },
                ]
            },
            {"items": []},
            {"items": []},
            {
                "items": [
                    {
                        "wb_id": "fb1",
                        "rating": 1,
                        "text": "Bad",
                        "created_date": "2026-06-10T10:00:00+00:00",
                        "product_details": {"nmId": 1001},
                    }
                ]
            },
            {"items": []},
            {"items": []},
        ]
    )

    inbox = await adapter.list_inbox(
        _account(),
        item_type="all",
        rating=1,
        sentiment="negative",
        priority="P1",
        nm_id=1001,
        limit=20,
        offset=0,
    )
    summary = await adapter.summary(_account())

    assert inbox.total == 1
    assert inbox.items[0].id == "review:fb1"
    assert summary.status == "ok"
    assert summary.negative_unanswered_count == 1
    assert summary.average_rating == 1


@pytest.mark.asyncio
async def test_reputation_adapter_product_360_returns_frontend_ready_counts_and_last_items() -> None:
    adapter = ReputationAdapter(
        Settings(
            reputation_enabled=True,
            reputation_base_url="http://reputation.internal",
            reputation_shop_map={"1": 10},
        )
    )
    adapter._request = AsyncMock(
        side_effect=[
            {
                "items": [
                    {
                        "wb_id": "fb1",
                        "rating": 1,
                        "text": "Bad",
                        "user_name": "Private Buyer",
                        "created_date": "2026-06-10T10:00:00+00:00",
                        "product_details": {"nmId": 1001, "productName": "Product"},
                        "token": "must-not-leak",
                    },
                    {
                        "wb_id": "fb2",
                        "rating": 5,
                        "text": "Good",
                        "created_date": "2026-06-10T11:00:00+00:00",
                        "product_details": {"nmId": 2002, "productName": "Other"},
                    },
                ]
            },
            {
                "items": [
                    {
                        "id": "q1",
                        "text": "What size?",
                        "created_at": "2026-06-10T12:00:00+00:00",
                        "product_details": {"nmId": 1001, "productName": "Product"},
                    }
                ]
            },
            {
                "items": [
                    {
                        "chat_id": "c1",
                        "unread_count": 2,
                        "last_message": {"text": "Hello"},
                        "created_at": "2026-06-10T13:00:00+00:00",
                        "good_card": {"nmID": 1001, "title": "Product"},
                        "draft": {"id": "draft-c1", "text": "Hello!"},
                    }
                ]
            },
        ]
    )

    block = await adapter.product_360(account_id=1, nm_id=1001)

    assert block.status == "ok"
    assert block.data["unanswered_reviews_count"] == 1
    assert block.data["unanswered_questions_count"] == 1
    assert block.data["negative_unanswered_count"] == 1
    assert block.data["unread_chats_count"] == 1
    assert block.data["draft_ready_count"] == 1
    assert len(block.data["last_items"]) == 3
    assert block.data["next_reputation_action"]["source_module"] == "reputation"
    assert block.data["next_reputation_action"]["action_type"] == "negative_review_unanswered"
    assert "must-not-leak" not in str(block.data)
    assert "Private Buyer" not in str(block.data)


@pytest.mark.asyncio
async def test_reputation_adapter_normalizes_incoming_project_payload_shapes_without_private_leakage() -> None:
    adapter = ReputationAdapter(
        Settings(
            reputation_enabled=True,
            reputation_base_url="http://reputation.internal",
            reputation_shop_map={"1": 10},
        )
    )
    adapter._request = AsyncMock(
        side_effect=[
            [_fixture("incoming_review_item.json")],
            [_fixture("incoming_question_item.json")],
            [_fixture("incoming_chat_item.json")],
        ]
    )

    inbox = await adapter.list_inbox(_account(), item_type="all", limit=20, offset=0)

    assert inbox.status == "ok"
    assert {item.item_type for item in inbox.items} == {"review", "question", "chat"}
    review = next(item for item in inbox.items if item.item_type == "review")
    question = next(item for item in inbox.items if item.item_type == "question")
    chat = next(item for item in inbox.items if item.item_type == "chat")
    assert review.rating == 2
    assert review.sentiment == "negative"
    assert review.draft is not None
    assert review.nm_id == 1001
    assert review.item_id == "review:fb-real"
    assert review.kind == "review"
    assert review.created_at is not None
    assert review.source_payload["product_details"]["nmId"] == 1001
    assert question.needs_reply is True
    assert question.nm_id == 1002
    assert question.item_id == "question:q-real"
    assert question.kind == "question"
    assert chat.needs_reply is True
    assert chat.nm_id == 1003
    assert chat.item_id == "chat:chat-real"
    assert chat.kind == "chat"
    assert chat.title == "Bag"
    assert "client_id" not in chat.source_payload
    dumped = str(inbox.model_dump(mode="json"))
    assert "must-not-leak" not in dumped
    assert "Private Buyer" not in dumped
    assert "Question Buyer" not in dumped
    assert "Chat Buyer" not in dumped
    assert "client-1" not in dumped


@pytest.mark.asyncio
async def test_reputation_adapter_summary_counts_real_like_mixed_payloads() -> None:
    adapter = ReputationAdapter(
        Settings(
            reputation_enabled=True,
            reputation_base_url="http://reputation.internal",
            reputation_shop_map={"1": 10},
        )
    )
    adapter._request = AsyncMock(
        side_effect=[
            [_fixture("incoming_review_item.json")],
            [_fixture("incoming_question_item.json")],
            [_fixture("incoming_chat_item.json")],
        ]
    )

    summary = await adapter.summary(_account())

    assert summary.status == "ok"
    assert summary.unanswered_reviews_count == 0
    assert summary.unanswered_questions_count == 1
    assert summary.unread_chats_count == 1
    assert summary.negative_unanswered_count == 0
    assert summary.draft_ready_count == 1
    assert summary.priority["P1"] == 1
    assert summary.priority["P2"] == 2


def test_reputation_adapter_chat_title_does_not_fall_back_to_private_client_name() -> None:
    adapter = ReputationAdapter(Settings())

    item = adapter._item_from_payload(
        account_id=1,
        kind="chat",
        payload={
            "chat_id": "chat-private",
            "client_name": "Private Client",
            "last_message": {"text": "Hello"},
            "unread_count": 1,
            "updated_at": "2026-06-10T12:00:00+00:00",
        },
    )

    assert item.title == "Chat"
    assert item.buyer_name == "P***"
    dumped = str(item.model_dump(mode="json"))
    assert "Private Client" not in dumped


@pytest.mark.asyncio
async def test_reputation_adapter_chat_publish_uses_reference_form_shape_after_confirm_and_flag() -> None:
    adapter = ReputationAdapter(
        Settings(
            reputation_enabled=True,
            reputation_base_url="http://reputation.internal",
            reputation_shop_map={"1": 10},
            enable_reputation_publish=True,
        )
    )
    adapter._request = AsyncMock(return_value={"sent": True})

    result = await adapter.publish_reply(
        _account(),
        draft_id="chat:chat-real",
        request=ReputationPublishRequest(confirm=True, text="Hello"),
    )

    assert result.success is True
    adapter._request.assert_awaited_once()
    assert adapter._request.await_args.args[:2] == ("POST", "/chats/10/chat-real/send")
    assert adapter._request.await_args.kwargs["form_data"] == {"message": "Hello", "use_latest_draft": "false"}


@pytest.mark.asyncio
async def test_reputation_adapter_approve_draft_is_local_only() -> None:
    adapter = ReputationAdapter(
        Settings(
            reputation_enabled=True,
            reputation_base_url="http://reputation.internal",
            reputation_shop_map={"1": 10},
        )
    )
    adapter._request = AsyncMock()

    result = await adapter.approve_draft(_account(), draft_id="review:fb1")

    assert result.status == "ok"
    assert result.draft is not None
    assert result.draft.status == "in_progress"
    assert "publishing remains behind manual confirm" in (result.message or "")
    adapter._request.assert_not_called()


@pytest.mark.asyncio
async def test_reputation_adapter_regenerate_and_reject_are_safe() -> None:
    adapter = ReputationAdapter(
        Settings(
            reputation_enabled=True,
            reputation_base_url="http://reputation.internal",
            reputation_shop_map={"1": 10},
        )
    )
    adapter._request = AsyncMock(
        side_effect=[
            {"id": "d2", "text": "Regenerated", "source_type": "review", "source_id": "fb1"},
            {"id": "d2", "text": "Rejected", "source_type": "review", "source_id": "fb1"},
        ]
    )

    regenerated = await adapter.regenerate_draft(_account(), draft_id="review:fb1", request=ReputationDraftDecisionRequest())
    rejected = await adapter.reject_draft(_account(), draft_id="review:fb1", request=ReputationDraftDecisionRequest(reason="bad tone"))

    assert regenerated.status == "ok"
    assert regenerated.draft is not None
    assert regenerated.draft.text == "Regenerated"
    assert rejected.draft is not None
    assert rejected.draft.status == "ignored"
    assert [call.args[:2] for call in adapter._request.await_args_list] == [
        ("POST", "/drafts/10/drafts/review:fb1/regenerate"),
        ("POST", "/drafts/10/drafts/review:fb1/reject"),
    ]


@pytest.mark.asyncio
async def test_reputation_adapter_no_reply_confirm_false_blocks_without_external_call() -> None:
    adapter = ReputationAdapter(
        Settings(
            reputation_enabled=True,
            reputation_base_url="http://reputation.internal",
            reputation_shop_map={"1": 10},
        )
    )
    adapter._request = AsyncMock()

    result = await adapter.mark_no_reply_needed(
        _account(),
        item_id="review:fb1",
        request=ReputationNoReplyRequest(confirm=False),
    )

    assert result.success is False
    assert result.event_type == "no_reply_blocked_confirmation_required"
    assert result.data["external_submit_attempted"] is False
    adapter._request.assert_not_called()


@pytest.mark.asyncio
async def test_reputation_adapter_no_reply_confirm_true_flag_false_records_local_only() -> None:
    adapter = ReputationAdapter(
        Settings(
            reputation_enabled=True,
            reputation_base_url="http://reputation.internal",
            reputation_shop_map={"1": 10},
        )
    )
    adapter._request = AsyncMock()

    result = await adapter.mark_no_reply_needed(
        _account(),
        item_id="review:fb1",
        request=ReputationNoReplyRequest(confirm=True, reason="duplicate"),
    )

    assert result.success is True
    assert result.event_type == "no_reply_recorded_local"
    assert result.external_status is None
    assert result.warnings == ["external_reputation_write_disabled"]
    assert result.data["external_submit_attempted"] is False
    assert result.data["external_write_enabled"] is False
    assert result.data["local_only"] is True
    adapter._request.assert_not_called()


@pytest.mark.asyncio
async def test_reputation_adapter_no_reply_confirm_true_flag_true_calls_external() -> None:
    adapter = ReputationAdapter(
        Settings(
            reputation_enabled=True,
            reputation_base_url="http://reputation.internal",
            reputation_shop_map={"1": 10},
            enable_reputation_write_actions=True,
        )
    )
    adapter._request = AsyncMock(return_value={"status": "ok"})

    result = await adapter.mark_no_reply_needed(
        _account(),
        item_id="review:fb1",
        request=ReputationNoReplyRequest(confirm=True, reason="duplicate"),
    )

    assert result.success is True
    assert result.event_type == "no_reply_marked"
    assert result.external_status == "closed"
    assert result.data["external_submit_attempted"] is True
    assert result.data["external_write_enabled"] is True
    assert result.data["local_only"] is False
    adapter._request.assert_awaited_once()
    assert adapter._request.await_args.args[:2] == ("POST", "/feedbacks/10/fb1/no-reply-needed")


@pytest.mark.asyncio
async def test_reputation_adapter_no_reply_non_review_remains_local_only() -> None:
    adapter = ReputationAdapter(
        Settings(
            reputation_enabled=True,
            reputation_base_url="http://reputation.internal",
            reputation_shop_map={"1": 10},
            enable_reputation_write_actions=True,
        )
    )
    adapter._request = AsyncMock()

    result = await adapter.mark_no_reply_needed(
        _account(),
        item_id="question:q1",
        request=ReputationNoReplyRequest(confirm=True, reason="answered elsewhere"),
    )

    assert result.success is True
    assert result.event_type == "no_reply_marked_local"
    assert result.external_status is None
    assert result.data["external_submit_attempted"] is False
    assert result.data["external_write_enabled"] is True
    assert result.data["local_only"] is True
    adapter._request.assert_not_called()


@pytest.mark.asyncio
async def test_reputation_adapter_settings_force_auto_publish_off() -> None:
    adapter = ReputationAdapter(
        Settings(
            reputation_enabled=True,
            reputation_base_url="http://reputation.internal",
            reputation_shop_map={"1": 10},
            enable_reputation_publish=True,
        )
    )
    adapter._request = AsyncMock(
        side_effect=[
            {
                "reply_mode": "manual",
                "tone": "friendly",
                "language": "ru",
                "auto_publish": True,
                "automation_enabled": True,
                "chat_auto_reply": True,
                "token": "must-not-leak",
            },
            {
                "reply_mode": "manual",
                "tone": "formal",
                "language": "ru",
                "auto_publish": True,
            },
        ]
    )

    current = await adapter.get_settings(_account())
    updated = await adapter.update_settings(
        _account(),
        request=ReputationSettingsUpdateRequest(tone="formal", payload={"auto_publish": True}),
    )

    assert current.status == "ok"
    assert current.runtime_mode == "external_adapter"
    assert current.dangerous_actions_enabled is True
    assert current.publish_enabled is True
    assert current.chat_send_enabled is True
    assert current.auto_publish_enabled is False
    assert current.automation_enabled is False
    assert "must-not-leak" not in str(current.model_dump(mode="json"))
    assert updated.tone == "formal"
    assert updated.runtime_mode == current.runtime_mode
    assert updated.publish_enabled is current.publish_enabled
    assert updated.auto_publish_enabled is False
    assert adapter._request.await_args_list[-1].kwargs["json_body"]["auto_publish"] is False


def test_reputation_adapter_backend7_reference_endpoint_inventory_marks_dangerous_publish_routes() -> None:
    safe = set(ReputationAdapter.SAFE_REFERENCE_ENDPOINTS)
    dangerous = set(ReputationAdapter.DANGEROUS_REFERENCE_ENDPOINTS)

    assert "GET /feedbacks/{shop_id}" in safe
    assert "GET /questions/{shop_id}" in safe
    assert "GET /chats/{shop_id}" in safe
    assert "POST /drafts/{shop_id}/drafts/{draft_id}/regenerate" in safe
    assert "POST /drafts/{shop_id}/drafts/{draft_id}/reject" in safe
    assert "POST /drafts/{shop_id}/drafts/{draft_id}/approve" in dangerous
    assert "POST /drafts/{shop_id}/drafts/approve-all" in dangerous
    assert dangerous.isdisjoint(safe)
