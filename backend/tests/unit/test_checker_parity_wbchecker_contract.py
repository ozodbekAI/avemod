from __future__ import annotations

import pytest

from app.core.config import Settings
from app.services.checker_core.ai_fixer import CheckerAIFixer
from app.services.card_quality import CardQualityNormalizationService


def test_wb_video_extractor_counts_single_video_field_and_dedupes() -> None:
    raw = {
        "video": "https://videonme-basket-07.wbbasket.ru/vol78/part83278/832780014/hls/1440p/index.m3u8",
        "videoUrl": "https://videonme-basket-07.wbbasket.ru/vol78/part83278/832780014/hls/1440p/index.m3u8",
        "videos": [
            {"url": "https://cdn.example.com/extra.mp4"},
            {"fileUrl": "https://cdn.example.com/extra.mp4"},
        ],
    }
    normalizer = CardQualityNormalizationService()

    assert normalizer._extract_videos(raw["video"], raw) == [
        "https://videonme-basket-07.wbbasket.ru/vol78/part83278/832780014/hls/1440p/index.m3u8",
        "https://cdn.example.com/extra.mp4",
    ]


def _ai_fixer() -> CheckerAIFixer:
    return CheckerAIFixer(Settings(checker_ai_enabled=True, openai_api_key="test-key"))


@pytest.mark.asyncio
async def test_text_title_generation_uses_consistent_multi_photo_grounding(monkeypatch) -> None:
    service = _ai_fixer()
    captured: dict[str, object] = {}

    async def fake_call_json(prompt: str, **kwargs):
        captured["prompt"] = prompt
        captured["image_urls"] = kwargs.get("image_urls")
        return {"recommended_value": "Костюм офисный классический с юбкой миди", "reason": "ok"}

    monkeypatch.setattr(service, "_call_json", fake_call_json)

    await service.generate_title(
        card={
            "subjectName": "Костюмы",
            "brand": "Avemod",
            "description": "OLD DESCRIPTION MUST NOT LEAK INTO TITLE PROMPT",
            "characteristics": [],
            "photos": [
                {"big": "https://example.test/1.jpg"},
                {"big": "https://example.test/2.jpg"},
                {"big": "https://example.test/3.jpg"},
            ],
        },
        product_dna="",
    )

    assert "OLD DESCRIPTION MUST NOT LEAK INTO TITLE PROMPT" not in str(captured["prompt"])
    assert isinstance(captured["image_urls"], list)
    assert len(captured["image_urls"]) >= 2


@pytest.mark.asyncio
async def test_text_description_generation_uses_consistent_multi_photo_grounding(monkeypatch) -> None:
    service = _ai_fixer()
    captured: dict[str, object] = {}

    async def fake_call_json(prompt: str, **kwargs):
        captured["prompt"] = prompt
        captured["image_urls"] = kwargs.get("image_urls")
        return {"recommended_value": "Описание " * 180, "reason": "ok"}

    monkeypatch.setattr(service, "_call_json", fake_call_json)

    await service.generate_description(
        card={
            "subjectName": "Костюмы",
            "title": "Костюм",
            "characteristics": [],
            "photos": [
                {"big": "https://example.test/1.jpg"},
                {"big": "https://example.test/2.jpg"},
                {"big": "https://example.test/3.jpg"},
            ],
        },
        product_dna="",
    )

    assert isinstance(captured["image_urls"], list)
    assert len(captured["image_urls"]) >= 2


@pytest.mark.asyncio
async def test_generate_fixes_preserves_incoming_issue_ids(monkeypatch) -> None:
    service = _ai_fixer()
    captured: dict[str, object] = {}

    async def fake_call_json(prompt: str, **kwargs):
        captured["prompt"] = prompt
        captured["image_urls"] = kwargs.get("image_urls")
        return {
            "fixes": {
                "17": {
                    "recommended_value": "габардин",
                    "reason": "allowed value confirmed",
                    "confidence": 0.9,
                    "requires_human_check": False,
                }
            }
        }

    monkeypatch.setattr(service, "_call_json", fake_call_json)

    fixes = await service.generate_fixes(
        card={
            "subjectName": "Костюмы",
            "characteristics": [],
            "photos": [{"big": "https://example.test/1.jpg"}, {"big": "https://example.test/2.jpg"}],
        },
        issues=[
            {
                "id": "17",
                "error_type": "wb_allowed_values",
                "name": "characteristics.Фактура материала",
                "current_value": "костюмная",
                "allowed_values": ["габардин", "твид"],
            }
        ],
        product_dna="На фото плотная ткань костюма.",
    )

    assert '"id": "17"' in str(captured["prompt"])
    assert isinstance(captured["image_urls"], list)
    assert "17" in fixes


@pytest.mark.asyncio
async def test_generate_fixes_skips_no_touch_characteristics(monkeypatch) -> None:
    service = _ai_fixer()

    async def fake_call_json(prompt: str, **kwargs):
        raise AssertionError("AI must not be called for no-touch characteristics")

    monkeypatch.setattr(service, "_call_json", fake_call_json)

    fixes = await service.generate_fixes(
        card={"subjectName": "Костюмы", "characteristics": [{"name": "ИКПУ", "value": ""}]},
        issues=[
            {
                "id": "1",
                "name": "characteristics.ИКПУ",
                "current_value": "",
                "allowed_values": ["123"],
            }
        ],
    )

    assert fixes == {}
