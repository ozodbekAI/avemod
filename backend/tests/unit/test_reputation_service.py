from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.core.config import Settings
from app.models.reputation import ReputationReviewCategory
from app.services.reputation import ReputationService, manual_attention_threshold, requires_manual_review_attention


@pytest.mark.asyncio
async def test_local_reputation_publish_requires_manual_confirm_before_any_io() -> None:
    service = ReputationService(Settings(enable_reputation_publish=True))
    result = await service.publish_reply(
        SimpleNamespace(),
        SimpleNamespace(id=1),
        draft_id="review:fb1",
        request=SimpleNamespace(confirm=False, text=None, payload={}),
        user_id=7,
    )

    assert result.success is False
    assert result.event_type == "publish_blocked_confirmation_required"
    assert result.warnings == ["manual_confirm_required"]


@pytest.mark.asyncio
async def test_local_reputation_publish_disabled_by_default_even_with_confirm() -> None:
    service = ReputationService(Settings(enable_reputation_publish=False))
    result = await service.publish_reply(
        SimpleNamespace(),
        SimpleNamespace(id=1),
        draft_id="review:fb1",
        request=SimpleNamespace(confirm=True, text=None, payload={}),
        user_id=7,
    )

    assert result.success is False
    assert result.event_type == "publish_disabled_by_feature_flag"
    assert result.warnings == ["reputation_publish_disabled"]


@pytest.mark.asyncio
async def test_local_reputation_sync_without_token_reports_lifecycle(monkeypatch: pytest.MonkeyPatch) -> None:
    service = ReputationService()

    class FakeSession:
        def add(self, obj: object) -> None:
            obj.id = 123

        async def flush(self) -> None:
            return None

        async def commit(self) -> None:
            return None

    async def fake_feedbacks_questions_token(session: object, *, account_id: int):
        return None

    async def fake_upsert_integration(*args, **kwargs):
        return None

    monkeypatch.setattr(service, "_feedbacks_questions_token", fake_feedbacks_questions_token)
    monkeypatch.setattr(service, "_upsert_integration", fake_upsert_integration)

    result = await service.sync_reputation(FakeSession(), SimpleNamespace(id=1))

    assert result.status == "not_configured"
    assert result.reviews_sync_status == "not_configured"
    assert result.questions_sync_status == "not_configured"
    assert result.chats_sync_status == "not_configured"
    assert result.backlog_status == "disabled"
    assert result.automation_status == "not_configured"
    assert result.last_error == "WB feedbacks/questions token is not configured"


@pytest.mark.asyncio
async def test_local_reputation_sync_reports_answered_unanswered_and_question_cursor(monkeypatch: pytest.MonkeyPatch) -> None:
    service = ReputationService(Settings(reputation_auto_draft_enabled=True))
    settings = SimpleNamespace(
        account_id=1,
        automation_enabled=False,
        auto_draft=True,
        questions_auto_draft=True,
        auto_publish_enabled=False,
        questions_auto_publish=False,
        questions_reply_mode="semi",
        rating_mode_map_json={"5": "auto"},
        config_json={},
        chat_enabled=False,
        last_sync_at=None,
        last_questions_sync_at=None,
        last_chat_sync_at=None,
        last_feedback_created_at=None,
        last_full_sync_at=None,
        chat_next_ms=None,
    )
    fetch_calls: list[tuple[str, bool | None]] = []

    class FakeSession:
        def add(self, obj: object) -> None:
            obj.id = 456
            obj.rows_received = obj.rows_received or 0
            obj.rows_created = obj.rows_created or 0
            obj.rows_updated = obj.rows_updated or 0

        async def flush(self) -> None:
            return None

        async def commit(self) -> None:
            return None

    async def fake_feedbacks_questions_token(session: object, *, account_id: int):
        return "feedbacks-questions-token"

    async def fake_settings(session: object, *, account_id: int):
        return settings

    async def fake_fetch(
        session: object,
        *,
        account_id: int,
        token: str,
        source_type: str,
        is_answered: bool | None = False,
    ):
        assert token == "feedbacks-questions-token"
        fetch_calls.append((source_type, is_answered))
        return [{"id": f"{source_type}-{is_answered}"}]

    async def fake_upsert(session: object, *, account_id: int, item_type: str, rows: list[dict]):
        return {"status": "ok", "received": len(rows), "created": len(rows), "updated": 0}

    async def fake_upsert_integration(*args, **kwargs):
        return None

    monkeypatch.setattr(service, "_feedbacks_questions_token", fake_feedbacks_questions_token)
    monkeypatch.setattr(service, "_settings", fake_settings)
    monkeypatch.setattr(service, "_fetch_wb_items", fake_fetch)
    monkeypatch.setattr(service, "_upsert_items", fake_upsert)
    monkeypatch.setattr(service, "_upsert_integration", fake_upsert_integration)

    result = await service.sync_reputation(FakeSession(), SimpleNamespace(id=1))

    assert result.reviews_sync_status == "ok"
    assert result.questions_sync_status == "ok"
    assert settings.last_sync_at is not None
    assert settings.last_questions_sync_at is not None
    assert ("review", False) in fetch_calls
    assert ("review", True) in fetch_calls
    assert ("question", False) in fetch_calls
    assert ("question", True) in fetch_calls
    assert result.data["sources"]["review"]["unanswered"]["received"] == 1
    assert result.data["sources"]["review"]["answered"]["received"] == 1
    assert result.data["sources"]["question"]["cursor"]["last_sync_at"] is not None


def test_local_reputation_settings_keep_automation_but_force_publish_off() -> None:
    service = ReputationService(Settings(reputation_enabled=True, enable_reputation_publish=True))
    result = service._settings_out(
        SimpleNamespace(
            account_id=1,
            automation_enabled=True,
            auto_sync=True,
            auto_draft=True,
            reply_mode="semi",
            tone="polite",
            language="ru",
            signature="Support team",
            templates_json=[],
            signatures_json=[],
            rating_mode_map_json={},
            config_json={},
            blacklist_keywords_json=[],
            whitelist_keywords_json=[],
            ai_enabled=False,
            ai_provider="openai",
            ai_model=None,
        )
    )

    assert result.status == "ok"
    assert result.runtime_mode == "local"
    assert result.dangerous_actions_enabled is True
    assert result.publish_enabled is True
    assert result.auto_publish_enabled is False
    assert result.chat_send_enabled is True
    assert result.automation_enabled is True
    assert result.data["automation"]["enabled"] is True
    assert result.auto_publish_enabled is False
    assert result.chat_auto_reply_enabled is False
    assert result.rating_mode_map["1"] == "manual"
    assert result.rating_mode_map["5"] == "auto"


def test_local_reputation_lifecycle_reports_chat_read_only_and_sync_status() -> None:
    service = ReputationService(Settings(reputation_auto_draft_enabled=True))
    result = service._settings_out(
        SimpleNamespace(
            account_id=1,
            automation_enabled=True,
            auto_sync=True,
            auto_draft=True,
            auto_draft_limit_per_sync=30,
            reply_mode="semi",
            tone="polite",
            language="ru",
            signature=None,
            templates_json=[],
            signatures_json=[],
            rating_mode_map_json={"5": "auto"},
            config_json={},
            blacklist_keywords_json=[],
            whitelist_keywords_json=[],
            ai_enabled=False,
            ai_provider="openai",
            ai_model=None,
            auto_publish_enabled=False,
            chat_auto_reply_enabled=True,
            questions_reply_mode="semi",
            questions_auto_draft=True,
            questions_auto_publish=True,
            chat_enabled=True,
            analytics_enabled=False,
            analytics_ready=False,
            analytics_period=None,
            analytics_status="activation_required",
            analytics_status_reason=None,
            last_sync_at=None,
            last_questions_sync_at=None,
            last_chat_sync_at=None,
        )
    )

    assert result.chats_sync_status == "beta_read_only"
    assert result.chat_auto_reply_enabled is True
    assert result.questions_auto_publish is True
    assert result.data["automation"]["chat_mode"] == "beta_read_only"


def test_local_reputation_kill_switch_disables_backlog_automation() -> None:
    service = ReputationService(Settings(reputation_auto_draft_enabled=True))
    settings = SimpleNamespace(
        automation_enabled=True,
        auto_draft=True,
        questions_auto_draft=True,
        auto_publish_enabled=False,
        questions_auto_publish=False,
        questions_reply_mode="auto",
        rating_mode_map_json={"5": "auto"},
        config_json={"kill_switch": True},
    )

    status = service._backlog_status(settings)

    assert status["status"] == "disabled"
    assert status["reason"] == "kill_switch"


def test_local_reputation_manual_mode_blocks_auto_draft() -> None:
    service = ReputationService(Settings(reputation_auto_draft_enabled=True))
    settings = SimpleNamespace(
        automation_enabled=True,
        auto_draft=True,
        questions_auto_draft=False,
        auto_publish_enabled=False,
        reply_mode="manual",
        rating_mode_map_json={"5": "manual"},
        config_json={},
    )
    item = SimpleNamespace(item_type="review", rating=5)

    allowed, reason = service._auto_draft_allowed_for_item(settings, item)

    assert allowed is False
    assert reason == "manual_mode"


def test_local_reputation_auto_publish_flag_keeps_aveotvet_automation_flow() -> None:
    service = ReputationService(Settings(reputation_auto_draft_enabled=True))
    settings = SimpleNamespace(
        automation_enabled=True,
        auto_draft=True,
        questions_auto_draft=False,
        auto_publish_enabled=True,
        questions_auto_publish=False,
        questions_reply_mode="auto",
        rating_mode_map_json={"5": "auto"},
        config_json={},
    )
    item = SimpleNamespace(item_type="review", rating=5)

    allowed, reason = service._auto_draft_allowed_for_item(settings, item)
    backlog = service._backlog_status(settings)

    assert allowed is True
    assert reason == "allowed"
    assert backlog["status"] == "ready"


def test_local_reputation_manual_attention_high_score_is_compatibly_clamped() -> None:
    service = ReputationService()

    score = service._compatible_need_reply_score(95, requires_manual_attention=True)

    assert score is not None
    assert score < manual_attention_threshold(service.settings)
    assert requires_manual_review_attention(score, service.settings) is True


def test_local_reputation_classifies_negative_defect_review() -> None:
    service = ReputationService()
    item = SimpleNamespace(
        item_type="review",
        rating=1,
        text="Ужасное качество, пришел брак и кривой шов.",
        raw_json={"pros": "", "cons": "брак"},
    )

    result = service._classify_item(item)

    assert result["sentiment"] == "negative"
    assert result["priority"] == "P1"
    assert result["reply_bucket"] == "negative"
    assert result["primary_category"]["role"] == "product_defect"


def test_local_reputation_does_not_mark_price_words_as_manual_attention() -> None:
    service = ReputationService()
    item = SimpleNamespace(
        item_type="review",
        rating=3,
        text="За такие деньги нитки торчат, качество среднее.",
        raw_json={},
    )

    result = service._classify_item(item)

    assert result["requires_manual_attention"] is False
    assert result["reply_bucket"] in {"negative", "neutral"}


def test_local_reputation_positive_bables_do_not_become_negative_fit() -> None:
    service = ReputationService()
    item = SimpleNamespace(
        item_type="review",
        rating=5,
        text="Костюм огонь",
        raw_json={"pros": "Костюм огонь", "cons": "", "bables": ["качество", "внешний вид", "хорошо сидит"]},
    )

    result = service._classify_item(item)

    assert result["sentiment"] == "positive"
    assert result["reply_bucket"] == "positive"
    assert result["requires_manual_attention"] is False
    assert all(category["sentiment"] == "positive" for category in result["categories"])


def test_local_reputation_neplohoi_is_not_emotional_negative() -> None:
    service = ReputationService()
    item = SimpleNamespace(
        item_type="review",
        rating=3,
        text="Костюм неплохой, но не за такие деньги. Нитки на пуговицах можно было сделать лучше.",
        raw_json={},
    )

    result = service._classify_item(item)

    assert result["requires_manual_attention"] is False
    assert not any(category["code"] == "emotional_negative" for category in result["categories"])
    assert result["reply_bucket"] in {"negative", "neutral"}


def test_local_reputation_mixed_review_keeps_positive_aspects() -> None:
    service = ReputationService()
    item = SimpleNamespace(
        item_type="review",
        rating=5,
        text="Качество товара. Коробка была порвана и побита.",
        raw_json={"pros": "Качество товара", "cons": "", "bables": ["качество", "внешний вид", "хорошо сидит"]},
    )

    result = service._classify_item(item)
    sentiments = {category["code"]: category["sentiment"] for category in result["categories"]}

    assert result["sentiment"] == "mixed"
    assert result["reply_bucket"] == "negative"
    assert sentiments["brak_i_sostoyanie_tovara"] == "negative"
    assert sentiments["dostavka_i_upakovka"] == "negative"
    assert sentiments["razmer_i_posadka"] == "positive"
    assert sentiments["kachestvo_i_poshiv"] == "positive"


def test_local_reputation_question_is_not_negative_review() -> None:
    service = ReputationService()
    item = SimpleNamespace(
        item_type="question",
        rating=None,
        text="Здравствуйте! Подскажите размер на рост 164 и вес 65?",
        raw_json={},
    )

    result = service._classify_item(item)

    assert result["sentiment"] == "neutral"
    assert result["reply_bucket"] == "neutral"
    assert result["requires_manual_attention"] is False


def test_local_reputation_draft_uses_classification_strategy() -> None:
    service = ReputationService()
    item = SimpleNamespace(
        item_type="review",
        rating=2,
        text="Размер не подошел, товар маломерит.",
        raw_json={},
    )
    settings = SimpleNamespace(signature="Команда магазина", templates_json=[], signatures_json=[])

    text = service._default_reply(item, settings, classification=service._classify_item(item))

    assert "размер" in text.lower() or "посад" in text.lower()
    assert "Команда магазина" in text


def test_local_reputation_effective_mode_uses_rating_map() -> None:
    service = ReputationService()
    settings = SimpleNamespace(reply_mode="semi", rating_mode_map_json={"1": "manual", "5": "auto"})

    assert service._effective_reply_mode(settings, 1) == "manual"
    assert service._effective_reply_mode(settings, 5) == "auto"
    assert service._effective_reply_mode(settings, None) == "semi"


@pytest.mark.asyncio
async def test_local_reputation_ai_reply_is_used_for_auto_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    service = ReputationService(Settings(openai_api_key="test-key"))
    item = SimpleNamespace(
        item_type="review",
        rating=5,
        title="Футболка",
        text="Отличный товар, спасибо!",
        raw_json={},
        buyer_name_masked=None,
    )
    settings = SimpleNamespace(
        reply_mode="semi",
        rating_mode_map_json={"5": "auto"},
        ai_enabled=True,
        ai_provider="openai",
        ai_model="gpt-5-mini",
        tone="polite",
        signature="Команда магазина",
        templates_json=[],
        signatures_json=[],
        config_json={},
        blacklist_keywords_json=[],
    )

    async def fake_response(payload: dict[str, object]) -> dict[str, object]:
        assert "Rating: 5" in str(payload["input"])
        assert "End with this signature" in str(payload["instructions"])
        assert "Команда магазина" in str(payload["instructions"])
        return {"output_text": "Здравствуйте! Спасибо за высокую оценку."}

    monkeypatch.setattr(service, "_request_openai_response", fake_response)

    text, meta = await service._reply_text(item, settings, service._classify_item(item))

    assert "Спасибо за высокую оценку" in text
    assert "Команда магазина" not in text
    assert meta["source"] == "ai"


@pytest.mark.asyncio
async def test_local_reputation_operator_generate_can_force_ai_for_manual_rating(monkeypatch: pytest.MonkeyPatch) -> None:
    service = ReputationService(Settings(openai_api_key="test-key"))
    item = SimpleNamespace(
        item_type="review",
        rating=1,
        title="Кроссовки",
        text="Пришел брак, шов кривой.",
        pros="",
        cons="брак",
        raw_json={},
        buyer_name_masked=None,
    )
    settings = SimpleNamespace(
        reply_mode="semi",
        questions_reply_mode="semi",
        rating_mode_map_json={"1": "manual"},
        ai_enabled=True,
        ai_provider="openai",
        ai_model="gpt-5-mini",
        tone="polite",
        signature="Команда магазина",
        templates_json=[],
        signatures_json=[],
        config_json={},
        blacklist_keywords_json=[],
    )

    async def fake_response(payload: dict[str, object]) -> dict[str, object]:
        assert "Пришел брак" in str(payload["input"])
        assert "Language: ru" in str(payload["instructions"])
        return {"output_text": "Здравствуйте! Спасибо за обратную связь. Нам жаль, что товар пришел с недостатком, передадим замечание в проверку качества."}

    monkeypatch.setattr(service, "_request_openai_response", fake_response)

    text, meta = await service._reply_text(item, settings, service._classify_item(item), force_ai=True)

    assert "проверку качества" in text
    assert meta["source"] == "ai"
    assert meta["reply_mode"] == "manual"
    assert meta["manual_mode_overridden_by_operator"] is True


def test_local_reputation_prompt_template_renders_aveotvet_placeholders() -> None:
    service = ReputationService()
    rendered = service._render_prompt_template(
        "{addr_rule} {length_rule} {emoji_rule} {unknown_var} Language: {language}.",
        {
            "addr_rule": "Use polite address.",
            "length_rule": "Keep it short.",
            "emoji_rule": "No emoji.",
            "language": "ru",
        },
    )

    assert "Use polite address." in rendered
    assert "Keep it short." in rendered
    assert "{unknown_var}" not in rendered
    assert "Language: ru" in rendered


def test_local_reputation_sanitizer_removes_support_style_requests() -> None:
    service = ReputationService()
    settings = SimpleNamespace(blacklist_keywords_json=[])

    result = service._sanitize_reply(
        "Спасибо за отзыв. Пришлите, пожалуйста, фото или номер заказа, мы проверим. Учтём замечание в работе.",
        settings,
    )

    assert "номер заказа" not in result.lower()
    assert "пришлите" not in result.lower()
    assert "Учтём замечание" in result


def test_local_reputation_draft_output_hides_stale_support_requests() -> None:
    service = ReputationService()
    draft = SimpleNamespace(
        id=24,
        draft_type="review_reply",
        external_status="draft_ready",
        account_id=1,
        payload_json={"source_type": "review", "source_id": "fb1"},
        title="Reply draft",
        body_text="Спасибо за отзыв. Пришлите фото или номер заказа, мы проверим. Учтём замечание.",
        status="new",
        created_at=None,
        updated_at=None,
    )

    result = service._draft_out(draft)

    assert "номер заказа" not in result.text.lower()
    assert "пришлите" not in result.text.lower()
    assert "Учтём замечание" in result.text


def test_local_reputation_signature_uses_default_signature_when_no_signature_match() -> None:
    service = ReputationService()
    settings = SimpleNamespace(
        signature="Базовая подпись",
        signatures_json=[{"text": "Подпись бренда", "type": "review", "brand": "nike", "rating": 5}],
    )

    signature = service._pick_signature(
        settings,
        kind="review",
        brand="adidas",
        rating=5,
    )

    assert signature == "Базовая подпись"


def test_local_reputation_signature_prefers_signature_list_before_fallback() -> None:
    service = ReputationService()
    settings = SimpleNamespace(
        signature="Базовая подпись",
        signatures_json=[{"text": "Подпись бренда", "type": "review", "brand": "nike", "rating": 5}],
    )

    signature = service._pick_signature(
        settings,
        kind="review",
        brand="nike",
        rating=5,
    )

    assert signature == "Подпись бренда"


def test_local_reputation_signature_prefers_brand_specific_when_possible() -> None:
    service = ReputationService()
    settings = SimpleNamespace(
        signature=None,
        signatures_json=[
            {"text": "Подпись для всех", "type": "review"},
            {"text": "Подпись для nike", "type": "review", "brand": "Nike"},
            {"text": "Подпись для adidas", "type": "review", "brand": "adidas", "rating": 5},
        ],
    )

    signature = service._pick_signature(
        settings,
        kind="review",
        brand="Nike",
        rating=4,
    )

    assert signature == "Подпись для nike"


def test_local_reputation_signature_respects_kind_and_rating_filters() -> None:
    service = ReputationService()
    settings = SimpleNamespace(
        signature=None,
        signatures_json=[
            {"text": "Подпись отзыва", "type": "review", "rating": 2},
            {"text": "Подпись вопроса", "type": "question", "rating": 2},
            {"text": "Подпись чата", "type": "chat"},
        ],
    )

    assert (
        service._pick_signature(
            settings,
            kind="question",
            rating=2,
        )
        == "Подпись вопроса"
    )
    assert (
        service._pick_signature(
            settings,
            kind="review",
            rating=2,
        )
        == "Подпись отзыва"
    )


def test_local_reputation_signature_prefers_brand_score_over_rating_score() -> None:
    service = ReputationService()
    settings = SimpleNamespace(
        signature=None,
        signatures_json=[
            {"text": "Общий по рейтингу", "type": "review", "rating": 3},
            {"text": "Nike для всех рейтингов", "type": "review", "brand": "nike"},
        ],
    )

    signature = service._pick_signature(
        settings,
        kind="review",
        brand="Nike",
        rating=3,
    )

    assert signature == "Nike для всех рейтингов"


def test_local_reputation_signature_prefers_first_candidate_on_tie() -> None:
    service = ReputationService()
    settings = SimpleNamespace(
        signature=None,
        signatures_json=[
            {"text": "Первая общая подпись", "type": "review", "rating": 5},
            {"text": "Вторая общая подпись", "type": "review", "rating": 5},
            {"text": "Брендовая подпись", "type": "review", "brand": "nike", "rating": 4},
        ],
    )

    signature = service._pick_signature(
        settings,
        kind="review",
        brand="adidas",
        rating=5,
    )

    assert signature == "Первая общая подпись"


def test_local_reputation_question_prompt_matches_aveotvet_default_template() -> None:
    service = ReputationService()
    item = SimpleNamespace(
        item_type="question",
        rating=None,
        title="Костюм",
        text="Какой размер взять?",
        pros=None,
        cons=None,
        raw_json={},
        buyer_name_masked=None,
        product_details_json={},
        media_json=[],
        bables_json=[],
        answer_text=None,
    )
    settings = SimpleNamespace(
        tone="polite",
        language="ru",
        signature=None,
        config_json={},
        blacklist_keywords_json=[],
    )

    instructions, input_text = service._build_ai_prompt_parts(
        item,
        settings,
        service._classify_item(item),
        prompt_context={},
    )

    assert "You write marketplace seller replies to customer questions." in instructions
    assert "Какой размер взять?" in input_text


@pytest.mark.asyncio
async def test_local_reputation_approve_refreshes_draft_after_commit(monkeypatch: pytest.MonkeyPatch) -> None:
    service = ReputationService()
    draft = SimpleNamespace(
        id=12,
        draft_type="review_reply",
        external_status="draft_ready",
        account_id=1,
        source_module="reputation",
        external_id="review:smoke",
        title="Reply draft",
        body_text="Здравствуйте! Спасибо за отзыв.",
        status="new",
        payload_json={"source_type": "review", "source_id": "smoke", "item_id": "review:smoke"},
        created_at=None,
        updated_at=None,
    )
    calls: list[str] = []

    class FakeSession:
        async def commit(self) -> None:
            calls.append("commit")

        async def refresh(self, obj: object) -> None:
            assert obj is draft
            calls.append("refresh")

    async def fake_find_draft(session: object, *, account_id: int, draft_id: str):
        assert account_id == 1
        assert draft_id == "12"
        return draft

    monkeypatch.setattr(service, "_find_draft", fake_find_draft)

    result = await service.approve_draft(FakeSession(), SimpleNamespace(id=1), draft_id="12", approved_by=7)

    assert calls == ["commit", "refresh"]
    assert result.status == "ok"
    assert result.draft is not None
    assert result.draft.status == "done"


@pytest.mark.asyncio
async def test_local_reputation_reply_text_blocks_manual_attention_without_force() -> None:
    service = ReputationService(Settings(openai_api_key="test-key"))
    item = SimpleNamespace(
        item_type="review",
        rating=1,
        title="Костюм",
        text="Требую вернуть деньги, буду писать претензию.",
        pros="",
        cons="верните деньги",
        raw_json={},
        buyer_name_masked=None,
        product_details_json={},
        media_json=[],
        bables_json=[],
        answer_text=None,
    )
    settings = SimpleNamespace(
        reply_mode="semi",
        rating_mode_map_json={"1": "auto"},
        ai_enabled=True,
        ai_provider="openai",
        ai_model="gpt-5-mini",
        tone="polite",
        signature=None,
        config_json={},
        blacklist_keywords_json=[],
    )

    text, meta = await service._reply_text(item, settings, service._classify_item(item))

    assert text == ""
    assert meta["blocked"] is True
    assert meta["status"] == "manual_attention_required"
    assert meta["debug_trace"]["blocked_reason"] == "manual_attention_required"


def test_local_reputation_prompt_context_contains_category_instruction_plan() -> None:
    service = ReputationService()
    item = SimpleNamespace(
        item_type="review",
        rating=2,
        title="Костюм",
        text="Качество хорошее, но коробка приехала порванная.",
        pros="Качество хорошее",
        cons="Коробка порвана",
        raw_json={},
        buyer_name_masked=None,
        product_details_json={},
        media_json=[],
        bables_json=[],
        answer_text=None,
    )
    settings = SimpleNamespace(
        tone="polite",
        language="ru",
        signature=None,
        config_json={},
        blacklist_keywords_json=[],
    )
    categories = [
        ReputationReviewCategory(code="dostavka_i_upakovka", label="Доставка и упаковка", positive_prompt="", negative_prompt="Извиниться за упаковку."),
        ReputationReviewCategory(code="kachestvo_i_poshiv", label="Качество и пошив", positive_prompt="Поблагодарить за качество.", negative_prompt="Признать проблему качества."),
    ]
    classification = {
        "sentiment": "mixed",
        "reply_bucket": "negative",
        "primary_category": {"code": "dostavka_i_upakovka", "label": "Доставка и упаковка", "sentiment": "negative", "role": "delivery_packaging"},
        "categories": [
            {"code": "dostavka_i_upakovka", "label": "Доставка и упаковка", "sentiment": "negative", "role": "delivery_packaging", "score": 80},
            {"code": "kachestvo_i_poshiv", "label": "Качество и пошив", "sentiment": "positive", "role": "quality", "score": 38},
        ],
        "requires_manual_attention": False,
    }
    plan = service._category_instruction_plan(categories, classification)

    instructions, input_text = service._build_ai_prompt_parts(
        item,
        settings,
        classification,
        prompt_context={"category_rules": [plan["instructions"]], "instruction_plan": plan},
    )

    assert plan["primary_review_category"] == "dostavka_i_upakovka"
    assert "Primary issue instructions" in instructions
    assert "Извиниться за упаковку" in instructions
    assert "Качество хорошее" in input_text
    assert "routing_weighted_scores" in plan


def test_local_reputation_plan_keeps_same_category_mixed_sentiment_guidance() -> None:
    service = ReputationService()
    category = ReputationReviewCategory(
        code="razmer_i_posadka",
        label="Размер",
        positive_prompt="Похвалить посадку.",
        negative_prompt="Разобрать проблему размера.",
    )
    classification = {
        "sentiment": "mixed",
        "reply_bucket": "negative",
        "categories": [
            {"code": "razmer_i_posadka", "sentiment": "positive", "role": "fit_size", "routing_score": 42},
            {"code": "razmer_i_posadka", "sentiment": "negative", "role": "fit_size", "routing_score": 42},
        ],
        "routing_scores": {"razmer_i_posadka": 42},
        "routing_primary_candidate": "razmer_i_posadka",
        "requires_manual_attention": False,
    }

    plan = service._category_instruction_plan([category], classification)

    assert plan["primary_review_category"] == "razmer_i_posadka"
    assert plan["primary_review_bucket"] == "mixed"
    assert plan["routing_scores"] == {"razmer_i_posadka": 42}
    assert plan["routing_primary_candidate"] == "razmer_i_posadka"
    assert "Похвалить посадку" in plan["instructions"]
    assert "Разобрать проблему размера" in plan["instructions"]
    assert "focus mainly on resolving the negative issue" in plan["instructions"]


def test_local_reputation_generic_mixed_is_suppressed_when_specific_negative_issue_exists() -> None:
    service = ReputationService()
    categories = [
        ReputationReviewCategory(code="brak_i_sostoyanie_tovara", label="Брак", positive_prompt="Good.", negative_prompt="Address defect.", sort_order=1),
        ReputationReviewCategory(code="razmer_i_posadka", label="Размер", positive_prompt="Size good.", negative_prompt="Size bad.", sort_order=2),
        ReputationReviewCategory(code="mixed", label="Mixed signals", positive_prompt="General praise.", negative_prompt="General complaint.", sort_order=3),
    ]
    classification = {
        "sentiment": "mixed",
        "reply_bucket": "negative",
        "categories": [
            {"code": "brak_i_sostoyanie_tovara", "sentiment": "negative", "role": "product_defect"},
            {"code": "razmer_i_posadka", "sentiment": "positive", "role": "fit_size"},
            {"code": "razmer_i_posadka", "sentiment": "negative", "role": "fit_size"},
            {"code": "mixed", "sentiment": "negative", "role": "mixed"},
        ],
    }

    plan = service._category_instruction_plan(categories, classification)

    assert plan["primary_review_category"] == "brak_i_sostoyanie_tovara"
    assert plan["secondary_review_categories"] == ["razmer_i_posadka"]
    assert plan["suppressed_review_categories"] == ["mixed"]
    assert "Standalone suppressed categories: mixed" in plan["instructions"]


def test_local_reputation_emotional_negative_is_tone_only_with_concrete_category() -> None:
    service = ReputationService()
    categories = [
        ReputationReviewCategory(code="brak_i_sostoyanie_tovara", label="Брак", positive_prompt="Good.", negative_prompt="Fix the defect.", sort_order=1),
        ReputationReviewCategory(code="emotional_negative", label="Эмоционально негативный тон", positive_prompt="No.", negative_prompt="No.", sort_order=2),
    ]
    classification = {
        "sentiment": "negative",
        "reply_bucket": "negative",
        "categories": [
            {"code": "brak_i_sostoyanie_tovara", "sentiment": "negative", "role": "product_defect"},
            {"code": "emotional_negative", "sentiment": "negative", "role": "emotional_negative"},
        ],
    }

    plan = service._category_instruction_plan(categories, classification)

    assert plan["primary_review_category"] == "brak_i_sostoyanie_tovara"
    assert plan["tone_only_review_categories"] == ["emotional_negative"]
    assert "Standalone suppressed categories: emotional_negative" not in plan["instructions"]


def test_local_reputation_price_complaint_is_tone_only_when_product_issue_exists() -> None:
    service = ReputationService()
    categories = [
        ReputationReviewCategory(code="brak_i_sostoyanie_tovara", label="Брак", positive_prompt="Good.", negative_prompt="Fix defect.", sort_order=1),
        ReputationReviewCategory(code="tsena_i_sootnoshenie_tsena_kachestvo", label="Цена", positive_prompt="Great value.", negative_prompt="Price is too high.", sort_order=2),
    ]
    classification = {
        "sentiment": "negative",
        "reply_bucket": "negative",
        "categories": [
            {"code": "brak_i_sostoyanie_tovara", "sentiment": "negative", "role": "product_defect"},
            {"code": "tsena_i_sootnoshenie_tsena_kachestvo", "sentiment": "negative", "role": "price_complaint"},
        ],
    }

    plan = service._category_instruction_plan(categories, classification)

    assert plan["primary_review_category"] == "brak_i_sostoyanie_tovara"
    assert plan["tone_only_review_categories"] == ["tsena_i_sootnoshenie_tsena_kachestvo"]
    assert "Tone-only/context categories: tsena_i_sootnoshenie_tsena_kachestvo" in plan["instructions"]


@pytest.mark.asyncio
async def test_local_reputation_persisted_draft_contains_debug_trace() -> None:
    service = ReputationService()
    captured: list[object] = []

    class EmptyResult:
        def scalars(self) -> "EmptyResult":
            return self

        def first(self) -> None:
            return None

    class FakeSession:
        async def execute(self, query: object) -> EmptyResult:
            return EmptyResult()

        def add(self, obj: object) -> None:
            captured.append(obj)

        async def flush(self) -> None:
            return None

    row = SimpleNamespace(
        item_type="review",
        external_id="fb1",
        nm_id=123,
        text="Отличный товар",
        rating=5,
        raw_json={},
    )
    generation_meta = {
        "source": "local_rules",
        "fallback": True,
        "fallback_reason": "ai_provider_disabled",
        "debug_trace": {"instructions": "i", "input_text": "u", "raw_messages": [], "classification_context": {"sentiment": "positive"}},
    }

    await service._persist_draft(
        FakeSession(),
        account_id=1,
        row=row,
        draft_type=None,
        text="Спасибо за отзыв.",
        status="new",
        created_by=7,
        classification={"sentiment": "positive"},
        generation_meta=generation_meta,
    )

    assert captured
    payload = captured[0].payload_json
    assert payload["generation"]["debug_trace"]["instructions"] == "i"
    assert payload["generation"]["fallback_reason"] == "ai_provider_disabled"


@pytest.mark.asyncio
async def test_local_reputation_fallback_metadata_is_explicit_when_ai_disabled() -> None:
    service = ReputationService(Settings(reputation_ai_default_enabled=False, openai_api_key=None))
    item = SimpleNamespace(
        item_type="review",
        rating=3,
        title="Костюм",
        text="Нормально, но нитки торчат.",
        pros="",
        cons="нитки торчат",
        raw_json={},
        buyer_name_masked=None,
        product_details_json={},
        media_json=[],
        bables_json=[],
        answer_text=None,
    )
    settings = SimpleNamespace(
        reply_mode="semi",
        rating_mode_map_json={"3": "semi"},
        ai_enabled=False,
        ai_provider="openai",
        ai_model=None,
        tone="polite",
        signature=None,
        templates_json=[],
        signatures_json=[],
        config_json={},
        blacklist_keywords_json=[],
    )

    text, meta = await service._reply_text(item, settings, service._classify_item(item))

    assert text
    assert meta["source"] == "local_rules"
    assert meta["fallback"] is True
    assert meta["fallback_reason"] == "ai_provider_disabled"
    assert meta["debug_trace"]["fallback_reason"] == "ai_provider_disabled"
