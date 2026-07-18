from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.core.config import Settings
from app.schemas.operator import DraftOut
from app.schemas.reputation import ReputationDraftRequest
from app.services.reputation import (
    ReputationService,
    manual_attention_threshold,
    parse_reputation_classification_response,
    requires_manual_review_attention,
)


def _review(**overrides):
    data = {
        "id": 1,
        "account_id": 1,
        "item_type": "review",
        "external_id": "fb-1",
        "rating": 5,
        "title": "Костюм",
        "text": "",
        "pros": "",
        "cons": "",
        "raw_json": {},
        "buyer_name_masked": None,
        "product_details_json": {},
        "media_json": [],
        "bables_json": [],
        "status": "new",
        "needs_reply": True,
        "nm_id": 1001,
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def _settings(**overrides):
    data = {
        "reply_mode": "semi",
        "questions_reply_mode": "semi",
        "rating_mode_map_json": {"1": "manual", "2": "manual", "3": "semi", "4": "auto", "5": "auto"},
        "ai_enabled": False,
        "ai_provider": "openai",
        "ai_model": None,
        "tone": "polite",
        "language": "ru",
        "signature": None,
        "templates_json": [],
        "signatures_json": [],
        "config_json": {},
        "blacklist_keywords_json": [],
    }
    data.update(overrides)
    return SimpleNamespace(**data)


class _NoopSession:
    def add(self, obj):
        return None

    async def flush(self):
        return None

    async def commit(self):
        return None

    async def refresh(self, obj):
        return None


def test_mixed_sentiment_keeps_positive_and_negative_matches_for_same_category_code() -> None:
    """Aveotvet keeps full category matches as source of truth, even for the same code."""
    service = ReputationService()
    item = _review(
        rating=5,
        text="Костюм хорошо сидит, но размер маломерит и в плечах не подошел.",
        raw_json={"pros": "хорошо сидит", "cons": "маломерит, не подошел"},
    )

    result = service._classify_item(item)
    fit_matches = [match for match in result["categories"] if match["code"] == "razmer_i_posadka"]
    fit_sentiments = {match["sentiment"] for match in fit_matches}

    assert result["sentiment"] == "mixed"
    assert fit_sentiments == {"positive", "negative"}


def test_manual_attention_semantics_match_aveotvet_review_routing() -> None:
    service = ReputationService()
    item = _review(
        rating=1,
        text="Верните деньги, буду писать претензию и обращаться в суд.",
        raw_json={},
    )

    result = service._classify_item(item)

    assert result["requires_manual_attention"] is True
    assert result["reply_bucket"] == "manual_attention"
    assert result["priority"] == "P0"
    assert result["need_reply_score"] < manual_attention_threshold(service.settings)
    assert requires_manual_review_attention(result["need_reply_score"], service.settings) is True


def test_normal_positive_review_score_is_above_manual_attention_threshold() -> None:
    service = ReputationService()
    item = _review(
        rating=5,
        text="Отличный костюм, качество хорошее, хорошо сидит.",
        raw_json={"pros": "качество хорошее, хорошо сидит", "cons": ""},
    )

    result = service._classify_item(item)

    assert result["requires_manual_attention"] is False
    assert result["reply_bucket"] == "positive"
    assert result["need_reply_score"] >= manual_attention_threshold(service.settings)
    assert requires_manual_review_attention(result["need_reply_score"], service.settings) is False


def test_fenced_json_classification_parsing_matches_aveotvet_contract() -> None:
    raw = """```json
{
  "need_reply_score": 85,
  "categories": [
    {"code": "kachestvo_i_poshiv", "sentiment": "positive"},
    {"code": "razmer_i_posadka", "sentiment": "negative"},
    {"code": "razmer_i_posadka", "sentiment": "positive"}
  ],
  "routing_hint": {
    "scores": [
      {"code": "kachestvo_i_poshiv", "score": 40},
      {"code": "razmer_i_posadka", "score": 85}
    ],
    "primary_candidate": "razmer_i_posadka",
    "secondary_candidate": "kachestvo_i_poshiv"
  }
}
```"""
    allowed_codes = {"kachestvo_i_poshiv", "razmer_i_posadka"}

    codes, matches, score, routing_scores, primary, secondary = parse_reputation_classification_response(
        raw,
        allowed_codes,
        "positive",
    )

    assert codes == ["kachestvo_i_poshiv", "razmer_i_posadka"]
    assert matches == [
        {"code": "kachestvo_i_poshiv", "sentiment": "positive"},
        {"code": "razmer_i_posadka", "sentiment": "negative"},
        {"code": "razmer_i_posadka", "sentiment": "positive"},
    ]
    assert score == 85
    assert routing_scores == {"kachestvo_i_poshiv": 40, "razmer_i_posadka": 85}
    assert primary == "razmer_i_posadka"
    assert secondary == "kachestvo_i_poshiv"


@pytest.mark.asyncio
async def test_draft_generation_blocks_manual_attention_reviews(monkeypatch: pytest.MonkeyPatch) -> None:
    """Aveotvet does not generate a normal reply draft for manual-attention reviews."""
    service = ReputationService(Settings(reputation_enabled=True))
    item = _review(
        rating=1,
        text="Верните деньги, нужна претензия и связь с поддержкой.",
        raw_json={},
    )

    async def fake_find_item(session, *, account_id: int, item_id: str):
        return item

    async def fake_settings(session, *, account_id: int):
        return _settings()

    async def fake_reply_text(*args, **kwargs):
        return "Ответ не должен создаваться", {"source": "local_rules"}

    async def fake_persist_draft(*args, **kwargs):
        return DraftOut(
            id="draft-1",
            draft_type="review_reply",
            external_status="draft_ready",
            account_id=1,
            source_type="review",
            source_id="fb-1",
            title="Reply draft",
            text="Ответ не должен создаваться",
            status="new",
            requires_confirmation=True,
        )

    monkeypatch.setattr(service, "_find_item", fake_find_item)
    monkeypatch.setattr(service, "_settings", fake_settings)
    monkeypatch.setattr(service, "_reply_text", fake_reply_text)
    monkeypatch.setattr(service, "_persist_draft", fake_persist_draft)

    result = await service.generate_draft(
        _NoopSession(),
        SimpleNamespace(id=1),
        item_id="review:fb-1",
        draft_type=ReputationDraftRequest().draft_type,
        created_by=7,
    )

    assert result.status in {"blocked", "manual_attention_required"}
    assert result.draft is None
    assert "manual_attention" in result.warnings
