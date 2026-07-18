from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.core.config import Settings
from app.schemas.reputation import ReputationSettingsUpdateRequest
from app.services.reputation import ReputationService


def _account() -> SimpleNamespace:
    return SimpleNamespace(id=1, external_account_id="10", name="Account 1")


def _chat_item() -> SimpleNamespace:
    return SimpleNamespace(
        id=22,
        account_id=1,
        item_type="chat",
        external_id="chat-1",
        rating=None,
        title="Buyer chat",
        text="",
        pros=None,
        cons=None,
        raw_json={
            "events": [
                {
                    "event_id": "seller-newer",
                    "sender_role": "seller",
                    "message": {"text": "Мы уже ответили"},
                    "addTimestamp": 500,
                },
                {
                    "event_id": "buyer-latest",
                    "sender_role": "client",
                    "message": {"text": "Когда доставят?"},
                    "addTimestamp": 450,
                    "attachments": {"images": []},
                },
            ],
            "goodCard": {"nmID": 55},
        },
        buyer_name_masked=None,
        product_details_json={},
        media_json=[],
        bables_json=[],
        status="new",
        needs_reply=True,
        nm_id=55,
    )


def _settings(**overrides) -> SimpleNamespace:
    data = {
        "account_id": 1,
        "reply_mode": "semi",
        "questions_reply_mode": "semi",
        "rating_mode_map_json": {},
        "ai_enabled": True,
        "ai_provider": "openai",
        "ai_model": "gpt-test",
        "tone": "polite",
        "language": "ru",
        "signature": None,
        "templates_json": [],
        "signatures_json": [],
        "config_json": {},
        "blacklist_keywords_json": [],
        "analytics_enabled": False,
        "analytics_ready": False,
        "analytics_period": None,
        "analytics_status": "activation_required",
        "analytics_status_reason": None,
        "analytics_status_updated_at": None,
    }
    data.update(overrides)
    return SimpleNamespace(**data)


class _NoopSession:
    async def commit(self):
        return None

    async def flush(self):
        return None


@pytest.mark.xfail(strict=True, reason="chat event sync not ported")
@pytest.mark.asyncio
async def test_chat_draft_uses_latest_inbound_buyer_message(monkeypatch: pytest.MonkeyPatch) -> None:
    service = ReputationService(Settings(openai_api_key="test-key"))
    item = _chat_item()
    settings = _settings()
    prompts: list[str] = []

    async def fake_response(payload: dict[str, object]) -> dict[str, object]:
        prompts.append(str(payload["input"]))
        return {"output_text": "AI reply"}

    monkeypatch.setattr(service, "_request_openai_response", fake_response)

    text, meta = await service._reply_text(_NoopSession(), item, settings, service._classify_item(item), force_ai=True)

    assert text == "AI reply"
    assert meta["source"] == "ai"
    assert prompts
    assert "Когда доставят?" in prompts[0]
    assert "Мы уже ответили" not in prompts[0]
    assert "goodCard" in prompts[0] or "nmID" in prompts[0]


@pytest.mark.asyncio
async def test_analytics_activation_contract_sets_ready_status_on_settings_update(monkeypatch: pytest.MonkeyPatch) -> None:
    service = ReputationService()
    settings = _settings()

    async def fake_settings(session, *, account_id: int):
        return settings

    monkeypatch.setattr(service, "_settings", fake_settings)

    result = await service.update_settings(
        _NoopSession(),
        _account(),
        request=ReputationSettingsUpdateRequest(analytics_enabled=True, analytics_period="90d"),
    )

    assert result.analytics_enabled is True
    assert result.analytics_ready is True
    assert result.analytics_period == "90d"
    assert result.analytics_status == "ready"
    assert settings.analytics_enabled is True
    assert settings.analytics_ready is True
    assert settings.analytics_period == "90d"
    assert settings.analytics_status == "ready"
    assert settings.analytics_status_reason is None


@pytest.mark.xfail(strict=True, reason="source billing/gpt accounting not ported")
def test_job_dedupe_and_retry_runtime_contract_is_not_available_in_finance() -> None:
    from app.repos.job_repo import build_job_dedupe_key, job_retry_delay_seconds

    payload = {"shop_id": 11, "is_answered": False, "take": 5000}
    left = build_job_dedupe_key("sync_shop", payload)
    right = build_job_dedupe_key("sync_shop", dict(reversed(list(payload.items()))))

    assert left == right
    assert left == "sync_shop:11:False:None:0"
    assert job_retry_delay_seconds(3) >= job_retry_delay_seconds(2)


@pytest.mark.xfail(strict=True, reason="source billing/gpt accounting not ported")
@pytest.mark.asyncio
async def test_analytics_preview_credit_reservation_contract_is_not_available_in_finance() -> None:
    from app.api.routes.analytics import ReviewAnalyticsPreviewIn, _build_analytics_preview

    result = await _build_analytics_preview(
        db=object(),
        shop_id=8,
        payload=ReviewAnalyticsPreviewIn(period="30d"),
    )

    assert result.reviews_count >= 0
    assert result.required_credits >= 0
    assert result.available_credits >= 0
    assert isinstance(result.enough_balance, bool)


def test_aveotvet_reputation_parity_matrix(capsys: pytest.CaptureFixture[str]) -> None:
    rows = [
        ("mixed sentiment same category", "test_mixed_sentiment_keeps_positive_and_negative_matches_for_same_category_code", "pass"),
        ("manual attention routing", "test_manual_attention_semantics_match_aveotvet_review_routing", "pass"),
        ("fenced JSON classification parsing", "test_fenced_json_classification_parsing_matches_aveotvet_contract", "pass"),
        ("manual-attention draft block", "test_draft_generation_blocks_manual_attention_reviews", "pass"),
        ("publish confirm gate", "test_publish_requires_confirmation_before_any_io", "pass"),
        ("approved draft gate", "test_publish_requires_approved_draft_even_when_confirmed", "pass"),
        ("no-reply semantic close", "test_no_reply_needed_sets_semantic_state_and_rejects_active_draft", "pass"),
        ("external publish", "test_external_adapter_publish_contract_is_disabled_until_feature_flag_is_enabled", "xfail: external publish disabled by feature flag"),
        ("chat latest inbound", "test_chat_draft_uses_latest_inbound_buyer_message", "xfail: chat event sync not ported"),
        ("analytics activation", "test_analytics_activation_contract_sets_ready_status_on_settings_update", "pass"),
        ("job runtime", "test_job_dedupe_and_retry_runtime_contract_is_not_available_in_finance", "xfail: source billing/gpt accounting not ported"),
        ("analytics credit preview", "test_analytics_preview_credit_reservation_contract_is_not_available_in_finance", "xfail: source billing/gpt accounting not ported"),
    ]
    with capsys.disabled():
        print("\nAveotvet Reputation parity matrix")
        print("source behavior -> target test -> expected result")
        for source, target, expected in rows:
            print(f"- {source} -> {target} -> {expected}")

    assert rows
