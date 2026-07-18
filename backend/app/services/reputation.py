from __future__ import annotations

import json
import re
from datetime import date, datetime, time, timedelta, timezone
from time import perf_counter
from typing import Any

import httpx
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.security import decrypt_wb_token
from app.core.time import utcnow
from app.models.accounts import WBAPICategory, WBAPIToken, WBAccount
from app.models.operator import (
    OperatorDraft,
    PortalIntegration,
    PortalModuleSyncRun,
    ResultEvent,
)
from app.models.product_cards import CoreSKU, WBProductCard
from app.models.reputation import (
    ReputationItem,
    ReputationLearningEntry,
    ReputationPromptRecord,
    ReputationReviewCategory,
    ReputationSettings,
)
from app.schemas.operator import (
    DraftOut,
    DraftType,
    ExternalStatus,
    OperatorModule,
    TrustState,
)
from app.schemas.portal import PortalActionRead, PortalDataBlock, PortalModuleHealthItem
from app.schemas.reputation import (
    ReputationDraftDecisionRequest,
    ReputationDraftMutationOut,
    ReputationDraftsOut,
    ReputationBulkDraftDecisionOut,
    ReputationAnalyticsOut,
    ReputationBrandsOut,
    ReputationChatEventOut,
    ReputationChatEventsOut,
    ReputationChatsOut,
    ReputationInboxOut,
    ReputationItemOut,
    ReputationLearningApplyRequest,
    ReputationLearningEntryOut,
    ReputationLearningOut,
    ReputationLearningToggleRequest,
    ReputationNoReplyRequest,
    ReputationProductInsightOut,
    ReputationPromptCategoryOut,
    ReputationPromptUpdateRequest,
    ReputationPublishRequest,
    ReputationSettingsOut,
    ReputationSettingsUpdateRequest,
    ReputationSummaryOut,
    ReputationSyncOut,
)
from app.services.reputation_adapter import ReputationAdapter
from app.services.raw import RawResponseService


REVIEW_SENTIMENT_POSITIVE = "positive"
REVIEW_SENTIMENT_NEGATIVE = "negative"
REVIEW_SENTIMENTS = {REVIEW_SENTIMENT_POSITIVE, REVIEW_SENTIMENT_NEGATIVE}


def normalize_need_reply_score(value: Any, fallback: int | None = None) -> int | None:
    if value is None:
        return fallback
    try:
        score = int(float(str(value).strip().replace("%", "")))
    except Exception:
        return fallback
    return max(0, min(100, score))


def manual_attention_threshold(settings: Settings | None = None) -> int:
    source = settings or get_settings()
    raw = int(
        getattr(
            source,
            "review_need_reply_manual_threshold",
            getattr(source, "REVIEW_NEED_REPLY_MANUAL_THRESHOLD", 60),
        )
        or 60
    )
    return max(0, min(100, raw))


def requires_manual_review_attention(
    score: int | None, settings: Settings | None = None
) -> bool:
    if score is None:
        return False
    return int(score) < manual_attention_threshold(settings)


def _iter_classification_payloads(raw: str) -> list[str]:
    text = (raw or "").strip()
    if not text:
        return []
    payloads = [text]
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        snippet = text[start : end + 1]
        if snippet != text:
            payloads.append(snippet)
    return payloads


def _normalize_classification_sentiment(
    value: Any, fallback: str | None = None
) -> str | None:
    raw = str(value or "").strip().lower()
    if raw in REVIEW_SENTIMENTS:
        return raw
    aliases = {
        "pos": REVIEW_SENTIMENT_POSITIVE,
        "good": REVIEW_SENTIMENT_POSITIVE,
        "negative_review": REVIEW_SENTIMENT_NEGATIVE,
        "neg": REVIEW_SENTIMENT_NEGATIVE,
        "bad": REVIEW_SENTIMENT_NEGATIVE,
    }
    if raw in aliases:
        return aliases[raw]
    if raw in {"mixed", "neutral"}:
        return fallback
    return fallback


def _normalize_classification_code(code: str, allowed_codes: set[str]) -> str | None:
    normalized = str(code or "").strip().lower()
    if not normalized or normalized not in allowed_codes:
        return None
    return normalized


def _extract_classification_entries(data: Any) -> list[tuple[str, str | None]] | None:
    if isinstance(data, list):
        entries: list[tuple[str, str | None]] = []
        for item in data:
            if isinstance(item, str):
                entries.append((item, None))
            elif isinstance(item, dict):
                raw_code = (
                    item.get("code")
                    or item.get("category")
                    or item.get("category_code")
                )
                if isinstance(raw_code, str):
                    entries.append((raw_code, item.get("sentiment")))
        return entries
    if not isinstance(data, dict):
        return None
    for key in ("categories", "codes", "category_codes", "matched_categories"):
        value = data.get(key)
        if isinstance(value, list):
            return _extract_classification_entries(value)
    return None


def _normalize_classification_matches(
    entries: list[tuple[str, str | None]],
    allowed_codes: set[str],
    fallback_sentiment: str,
) -> tuple[list[str], list[dict[str, Any]]]:
    seen_codes: set[str] = set()
    seen_pairs: set[tuple[str, str]] = set()
    codes: list[str] = []
    matches: list[dict[str, Any]] = []
    for raw_code, raw_sentiment in entries:
        code = _normalize_classification_code(raw_code, allowed_codes)
        if not code:
            continue
        sentiment = _normalize_classification_sentiment(
            raw_sentiment, fallback=fallback_sentiment
        )
        if sentiment is None:
            continue
        pair = (code, sentiment)
        if pair in seen_pairs:
            continue
        seen_pairs.add(pair)
        matches.append({"code": code, "sentiment": sentiment})
        if code not in seen_codes:
            seen_codes.add(code)
            codes.append(code)
    return codes, matches


def parse_reputation_classification_response(
    raw: str,
    allowed_codes: set[str],
    fallback_sentiment: str,
) -> tuple[
    list[str], list[dict[str, Any]], int | None, dict[str, int], str | None, str | None
]:
    for payload in _iter_classification_payloads(raw):
        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError:
            continue
        parsed_score = None
        if isinstance(parsed, dict):
            for key in ("need_reply_score", "needReplyScore", "reply_need_score"):
                if key in parsed:
                    parsed_score = normalize_need_reply_score(parsed.get(key))
                    break
        routing_scores: dict[str, int] = {}
        primary_candidate: str | None = None
        secondary_candidate: str | None = None
        if isinstance(parsed, dict) and isinstance(parsed.get("routing_hint"), dict):
            hint = parsed["routing_hint"]
            if isinstance(hint.get("scores"), list):
                for item in hint["scores"]:
                    if not isinstance(item, dict):
                        continue
                    code = _normalize_classification_code(
                        str(item.get("code") or item.get("category") or ""),
                        allowed_codes,
                    )
                    score = normalize_need_reply_score(item.get("score"), fallback=None)
                    if code and score is not None and code not in routing_scores:
                        routing_scores[code] = score
            primary_candidate = _normalize_classification_code(
                str(hint.get("primary_candidate") or hint.get("primary") or ""),
                allowed_codes,
            )
            secondary_candidate = _normalize_classification_code(
                str(hint.get("secondary_candidate") or hint.get("secondary") or ""),
                allowed_codes,
            )
        extracted = _extract_classification_entries(parsed)
        if extracted is not None:
            codes, matches = _normalize_classification_matches(
                extracted or [], allowed_codes, fallback_sentiment
            )
            code_set = set(codes)
            return (
                codes,
                matches,
                parsed_score,
                {
                    code: score
                    for code, score in routing_scores.items()
                    if code in code_set
                },
                primary_candidate if primary_candidate in code_set else None,
                secondary_candidate if secondary_candidate in code_set else None,
            )
        if parsed_score is not None:
            return ([], [], parsed_score, {}, None, None)
    return ([], [], 100, {}, None, None)


class ReputationService:
    WB_BASE_URL = "https://feedbacks-api.wildberries.ru"
    OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
    DEFAULT_RATING_MODE_MAP = {
        "1": "manual",
        "2": "manual",
        "3": "semi",
        "4": "auto",
        "5": "auto",
    }
    ALLOWED_REPLY_MODES = {"manual", "semi", "auto"}
    ROUTING_CLEAR_MARGIN = 15
    ROUTING_CLEAR_PRIMARY_SCORE = 60
    ROUTING_MIN_PRIMARY_SCORE = 45
    ROUTING_MIN_SECONDARY_SCORE = 30
    ROUTING_SOFT_MARGIN = 6
    ROUTING_ROLE_ALIASES = {
        "brak_i_sostoyanie_tovara": "product_defect",
        "razmer_i_posadka": "fit_size",
        "tsena_i_sootnoshenie_tsena_kachestvo": "price_complaint",
        "emotional_negative": "emotional_negative",
        "mixed": "mixed",
        "dostavka_i_upakovka": "delivery_packaging",
        "ozhidanie_i_realnost": "expectation_mismatch",
        "kachestvo_i_poshiv": "quality",
    }
    ROUTING_ROLE_BONUS = {
        "product_defect": 20,
        "delivery_packaging": 15,
        "fit_size": 10,
        "quality": 8,
        "price_complaint": 5,
        "expectation_mismatch": 4,
        "emotional_negative": -15,
        "mixed": -20,
        "rating_bucket": -20,
    }
    ROUTING_BUCKET_BONUS = {"negative": 5, "mixed": 3, "positive": -8}
    DEFAULT_REVIEW_PROMPT = (
        "You write marketplace seller replies to customer reviews. "
        "Output plain text only. No markdown. No links. No phone numbers. No emails. "
        "Do not mention that you are an AI. "
        "{addr_rule} {length_rule} {emoji_rule} "
        "Language: {language}. Base tone: {tone}. "
        "Hard max length: {hard_max_len} characters. "
        "{stop_words_rule} {signature_rule}"
    )
    DEFAULT_QUESTION_PROMPT = (
        "You write marketplace seller replies to customer questions. "
        "Output plain text only. No markdown. No links. No phone numbers. No emails. "
        "Do not mention that you are an AI. "
        "{addr_rule} {length_rule} {emoji_rule} "
        "Language: {language}. Base tone: {tone}. "
        "Hard max length: {hard_max_len} characters. "
        "{stop_words_rule} {signature_rule}"
    )
    DEFAULT_CHAT_PROMPT = (
        "You write short, helpful seller replies in a marketplace buyer chat. "
        "Output plain text only. No markdown. No links. No phone numbers. No emails. "
        "Be concise and clear. Ask clarifying questions only if required. "
        "{addr_rule} {emoji_rule} {stop_words_rule} "
        "Language: {language}. Tone: {tone}. Max length: {hard_max_len} characters."
    )
    DEFAULT_REVIEW_CATEGORIES: tuple[dict[str, Any], ...] = (
        {
            "code": "razmer_i_posadka",
            "label": "Размер и посадка",
            "positive_prompt": "Если отзыв положительный о размере или посадке, поблагодари за высокую оценку и подчеркни, что вещь хорошо села и подошла по размеру. Ответ должен усиливать ощущение удачной покупки без лишней воды.",
            "negative_prompt": "Если отзыв негативный о размере или посадке, спокойно признай, что модель могла сесть не так, как ожидалось, или не совпасть по размеру. Покажи внимание к проблеме и мягко отметь, что обратная связь поможет точнее описывать посадку и размерность.",
            "sort_order": 10,
        },
        {
            "code": "vneshnii_vid_i_fason",
            "label": "Внешний вид и фасон",
            "positive_prompt": "Если отзыв положительный о внешнем виде или фасоне, отметь, что рады, что модель, силуэт или фасон понравились покупателю. Сделай ответ теплым и поддерживающим стильный выбор.",
            "negative_prompt": "Если отзыв негативный о внешнем виде или фасоне, признай, что фасон, крой или общий вид могли не оправдать ожидания. Ответ должен быть деликатным, без спора, с акцентом на ценность честной обратной связи.",
            "sort_order": 20,
        },
        {
            "code": "tkan_i_material",
            "label": "Ткань и материал",
            "positive_prompt": "Если отзыв положительный о ткани или материале, подчеркни, что приятно знать, что материал оказался удачным по ощущениям и качеству. Поблагодари за внимание к фактуре, плотности или составу.",
            "negative_prompt": "Если отзыв негативный о ткани или материале, признай замечание о составе, плотности, фактуре или ощущениях от материала. Ответ должен показывать уважение к такому замечанию и готовность учитывать его в описании товара.",
            "sort_order": 30,
        },
        {
            "code": "tsvet_i_sootvetstvie_foto",
            "label": "Цвет и соответствие фото",
            "positive_prompt": "Если отзыв положительный о цвете или соответствии фото, отметь, что рады точному совпадению оттенка и визуального впечатления с ожиданиями покупателя. Ответ должен быть коротким и уверенным.",
            "negative_prompt": "Если отзыв негативный о цвете или несоответствии фото, признай, что восприятие оттенка или внешний вид могли отличаться от ожиданий. Аккуратно подчеркни важность замечания для корректной передачи товара в карточке.",
            "sort_order": 40,
        },
        {
            "code": "kachestvo_i_poshiv",
            "label": "Качество и пошив",
            "positive_prompt": "Если отзыв положительный о качестве или пошиве, поблагодари за оценку аккуратности исполнения, швов и общего качества изделия. Усиль ощущение надежности и хорошего уровня вещи.",
            "negative_prompt": "Если отзыв негативный о качестве или пошиве, признай проблему со швами, обработкой деталей или общим качеством. Ответ должен быть собранным, уважительным и без попытки оправдать недостаток.",
            "sort_order": 50,
        },
        {
            "code": "komplektnost_i_sostav",
            "label": "Комплектность и состав",
            "positive_prompt": "Если отзыв положительный о комплектности или составе, отметь, что приятно знать, что покупатель получил именно то, что ожидал по наполнению, составу или комплекту. Сделай ответ спокойным и благодарным.",
            "negative_prompt": "Если отзыв негативный о комплектности или составе, признай замечание о недостающих элементах, наполнении или несоответствии состава ожиданиям. Ответ должен фиксировать важность такого сигнала для команды.",
            "sort_order": 60,
        },
        {
            "code": "komfort_i_udobstvo",
            "label": "Комфорт и удобство",
            "positive_prompt": "Если отзыв положительный о комфорте или удобстве, подчеркни, что особенно приятно знать, что товар оказался удобным в использовании или носке. Ответ должен поддерживать эмоцию довольства и легкости.",
            "negative_prompt": "Если отзыв негативный о комфорте или удобстве, признай, что товар мог оказаться менее удобным, чем ожидалось. Ответ должен быть спокойным и внимательным к ощущениям покупателя.",
            "sort_order": 70,
        },
        {
            "code": "posle_stirki_i_v_noske",
            "label": "После стирки и в носке",
            "positive_prompt": "Если отзыв положительный о поведении вещи после стирки или в носке, поблагодари за ценную обратную связь о долговременном опыте. Подчеркни, что особенно рады хорошему сохранению формы, цвета или внешнего вида.",
            "negative_prompt": "Если отзыв негативный о вещи после стирки или в носке, признай проблему с изменением формы, состояния, цвета или поведения материала со временем. Ответ должен быть аккуратным и уважительным, без спора с опытом покупателя.",
            "sort_order": 80,
        },
        {
            "code": "dostavka_i_upakovka",
            "label": "Доставка и упаковка",
            "positive_prompt": "Если отзыв положительный о доставке или упаковке, отметь, что рады быстрой доставке и аккуратной упаковке. Ответ должен закреплять ощущение хорошего сервиса вокруг покупки.",
            "negative_prompt": "Если отзыв негативный о доставке или упаковке, признай неприятный опыт с упаковкой, сроком или состоянием заказа при получении. Ответ должен показать понимание, что такие детали влияют на общее впечатление.",
            "sort_order": 90,
        },
        {
            "code": "tsena_i_sootnoshenie_tsena_kachestvo",
            "label": "Цена и соотношение цена/качество",
            "positive_prompt": "Если отзыв положительный о цене или соотношении цена/качество, подчеркни, что особенно приятно, когда покупатель видит в покупке выгодность и оправданную стоимость. Ответ должен усиливать ощущение удачной сделки.",
            "negative_prompt": "Если отзыв негативный о цене или соотношении цена/качество, признай, что ожидания от стоимости и ценности могли не совпасть. Ответ должен быть корректным, без спора о цене, с уважением к восприятию покупателя.",
            "sort_order": 100,
        },
        {
            "code": "brak_i_sostoyanie_tovara",
            "label": "Брак и состояние товара",
            "positive_prompt": "Если отзыв положительный о состоянии товара при получении, отметь, что рады, что изделие пришло в хорошем состоянии и оправдало ожидания по сохранности. Ответ должен быть спокойным и уверенным.",
            "negative_prompt": "Если отзыв негативный о браке или состоянии товара, прямо признай проблему с дефектом, повреждением или ненадлежащим состоянием. Ответ должен быть максимально тактичным и серьезным, с акцентом на важность такого сигнала.",
            "sort_order": 110,
        },
        {
            "code": "ozhidanie_i_realnost",
            "label": "Ожидание и реальность",
            "positive_prompt": "Если отзыв положительный о совпадении ожиданий с реальностью, подчеркни, что рады полному попаданию в ожидания покупателя. Ответ должен усиливать доверие к товару и карточке.",
            "negative_prompt": "Если отзыв негативный о расхождении ожиданий и реальности, признай, что впечатление от товара могло отличаться от ожидаемого. Ответ должен быть бережным и показывать, что замечание важно для улучшения описания и подачи.",
            "sort_order": 120,
        },
        {
            "code": "emotional_negative",
            "label": "Эмоционально негативный отзыв",
            "positive_prompt": "Сохраняй спокойный и уважительный тон, без лишней радости.",
            "negative_prompt": "Ответь спокойно и с эмпатией, не защищайся, не спорь и не усиливай конфликт.",
            "sort_order": 130,
        },
    )
    DEFAULT_PROMPT_CONFIG: dict[str, Any] = {
        "advanced": {
            "address_format": "vy_lower",
            "use_buyer_name": False,
            "mention_product_name": True,
            "answer_length": "default",
            "emoji_enabled": False,
            "photo_reaction_enabled": False,
            "delivery_method": None,
            "tone_of_voice": {
                "positive": "none",
                "neutral": "none",
                "negative": "none",
                "question": "none",
            },
            "stop_words": [],
        },
        "chat": {"confirm_send": True, "confirm_ai_insert": True},
        "recommendations": {"enabled": False},
        "onboarding": {},
    }
    MANUAL_ATTENTION_RE = re.compile(
        r"\b("
        r"верн(ите|уть|ул[аи]?)\s+(деньг[иам]?|средств[ао]?)|"
        r"деньги\s+назад|возврат\s+(денег|средств|товар[а]?|покупк[иу])|"
        r"оформ(ил[аи]?|ить|ляю)\s+возврат|"
        r"связаться|свяжитесь|номер\s+заказа|"
        r"юрист|суд|претензи[яию]|жалоб[ауы]|поддержк[аи]"
        r")\b",
        re.IGNORECASE,
    )
    REVIEW_CATEGORY_RULES: tuple[dict[str, Any], ...] = (
        {
            "code": "brak_i_sostoyanie_tovara",
            "label": "Брак и состояние товара",
            "role": "product_defect",
            "keywords": (
                "брак",
                "дефект",
                "дыр",
                "порва",
                "слом",
                "пятн",
                "затяж",
                "оторва",
                "крив",
                "шов",
                "царап",
            ),
        },
        {
            "code": "razmer_i_posadka",
            "label": "Размер и посадка",
            "role": "fit_size",
            "keywords": (
                "размер",
                "маломер",
                "большемер",
                "мал",
                "велик",
                "не подош",
                "посадк",
                "сидит",
                "тесн",
                "широк",
            ),
        },
        {
            "code": "vneshnii_vid_i_fason",
            "label": "Внешний вид и фасон",
            "role": "appearance_style",
            "keywords": (
                "фасон",
                "крой",
                "силуэт",
                "модель",
                "внешн",
                "вид",
                "красив",
                "стиль",
                "смотрится",
            ),
        },
        {
            "code": "tkan_i_material",
            "label": "Ткань и материал",
            "role": "material",
            "keywords": (
                "ткан",
                "материал",
                "состав",
                "плотн",
                "тонк",
                "фактур",
                "синтет",
                "ощущен",
            ),
        },
        {
            "code": "tsvet_i_sootvetstvie_foto",
            "label": "Цвет и соответствие фото",
            "role": "color_photo",
            "keywords": (
                "цвет",
                "оттен",
                "фото",
                "картин",
                "изображ",
                "не такой",
                "отличается",
            ),
        },
        {
            "code": "tsena_i_sootnoshenie_tsena_kachestvo",
            "label": "Цена и соотношение цена/качество",
            "role": "price_complaint",
            "keywords": ("цен", "дорог", "деньг", "сто", "переплат", "не стоит"),
        },
        {
            "code": "dostavka_i_upakovka",
            "label": "Доставка и упаковка",
            "role": "delivery_packaging",
            "keywords": (
                "упаков",
                "достав",
                "короб",
                "пакет",
                "помят",
                "мятая",
                "грязн",
            ),
        },
        {
            "code": "ozhidanie_i_realnost",
            "label": "Ожидание и реальность",
            "role": "expectation_mismatch",
            "keywords": (
                "ожид",
                "реальн",
                "не соответствует",
                "другой",
                "не совпал",
                "не совпада",
            ),
        },
        {
            "code": "kachestvo_i_poshiv",
            "label": "Качество и пошив",
            "role": "quality",
            "keywords": (
                "качеств",
                "пошив",
                "шов",
                "нитк",
                "строч",
                "обработк",
                "пуговиц",
            ),
        },
        {
            "code": "komplektnost_i_sostav",
            "label": "Комплектность и состав",
            "role": "composition_set",
            "keywords": (
                "комплект",
                "комплектац",
                "недоста",
                "элемент",
                "пояс",
                "состав",
                "наполнен",
            ),
        },
        {
            "code": "komfort_i_udobstvo",
            "label": "Комфорт и удобство",
            "role": "comfort",
            "keywords": (
                "комфорт",
                "удоб",
                "неудоб",
                "мягк",
                "колет",
                "носить",
                "ощущен",
            ),
        },
        {
            "code": "posle_stirki_i_v_noske",
            "label": "После стирки и в носке",
            "role": "wash_wear",
            "keywords": (
                "стирк",
                "после стир",
                "носке",
                "катыш",
                "сел",
                "села",
                "линя",
                "выцвел",
                "форма",
            ),
        },
        {
            "code": "emotional_negative",
            "label": "Эмоционально негативный отзыв",
            "role": "emotional_negative",
            "keywords": (
                "ужас",
                "кошмар",
                "разочар",
                "отврат",
                "плохо",
                "не рекоменд",
                "никогда",
                "жаль",
            ),
        },
    )
    POSITIVE_RE = re.compile(
        r"(?<![0-9a-zа-яё])(отличн|хорош|супер|понрав|спасибо|классн|рекомендую|идеальн|подош[её]л|огонь)",
        re.IGNORECASE,
    )
    NEGATIVE_RE = re.compile(
        r"(?<![0-9a-zа-яё])(плох|ужас|брак|дефект|не\s+подош|разочар|не\s+рекоменд|дорог|грязн|порва|слом|не\s+соответствует)",
        re.IGNORECASE,
    )
    VALUE_GAP_RE = re.compile(
        r"\b(не\s+за\s+такие\s+деньг|не\s+стоит|переплат|можно\s+было|за\s+\S+\s+тысяч)",
        re.IGNORECASE,
    )

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.adapter = ReputationAdapter(self.settings)
        self.raw_service = RawResponseService()

    def _runtime_status(self) -> dict[str, Any]:
        return {
            "runtime_mode": "local" if self.settings.reputation_enabled else "disabled",
            "dangerous_actions_enabled": bool(
                self.settings.enable_reputation_publish
                or self.settings.enable_reputation_write_actions
            ),
            "publish_enabled": bool(self.settings.enable_reputation_publish),
            "auto_publish_enabled": False,
            "chat_send_enabled": bool(self.settings.enable_reputation_publish),
        }

    async def get_module_status(
        self, account: WBAccount | None = None, session: AsyncSession | None = None
    ) -> PortalModuleHealthItem:
        if account is None or session is None:
            return PortalModuleHealthItem(
                module="reputation",
                status="not_configured",
                enabled=True,
                configured=False,
                message="account is required",
                **self._runtime_status(),
            )
        counts = await self._source_counts(session, account_id=int(account.id))
        has_token = await self._has_feedbacks_questions_token(
            session, account_id=int(account.id)
        )
        status = (
            "ok"
            if sum(counts.values())
            else ("not_configured" if not has_token else "empty")
        )
        item = PortalModuleHealthItem(
            module="reputation",
            status=status,
            enabled=True,
            configured=has_token or bool(sum(counts.values())),
            message="local reputation operator uses finance database",
            warnings=["local"],
            **self._runtime_status(),
        )
        item.mode = "local"
        item.actionable_open_issues = int(
            (
                await session.execute(
                    select(func.count())
                    .select_from(ReputationItem)
                    .where(
                        ReputationItem.account_id == int(account.id),
                        ReputationItem.needs_reply.is_(True),
                        ReputationItem.status.in_(
                            ("new", "needs_reply", "draft_ready", "in_progress")
                        ),
                    )
                )
            ).scalar()
            or 0
        )
        return item

    async def sync_reputation(
        self, session: AsyncSession, account: WBAccount
    ) -> ReputationSyncOut:
        run = PortalModuleSyncRun(
            account_id=int(account.id),
            module="reputation",
            run_type="sync",
            status="running",
            started_at=utcnow(),
        )
        session.add(run)
        await session.flush()
        unavailable: list[str] = []
        warnings: list[str] = []
        source_stats: dict[str, dict[str, int | str]] = {}
        token = await self._feedbacks_questions_token(
            session, account_id=int(account.id)
        )
        if token is None:
            unavailable.extend(["reviews", "questions", "chats"])
            warnings.append("wb_feedbacks_questions_token_not_configured")
            lifecycle = self._sync_lifecycle_status(
                None,
                token_configured=False,
                last_error="WB feedbacks/questions token is not configured",
            )
            per_source_status = {
                "reviews": {
                    "status": "not_configured",
                    "received": 0,
                    "created": 0,
                    "updated": 0,
                },
                "questions": {
                    "status": "not_configured",
                    "received": 0,
                    "created": 0,
                    "updated": 0,
                },
                "chats": {
                    "status": "not_configured",
                    "mode": "read_only",
                    "received": 0,
                    "created": 0,
                    "updated": 0,
                },
            }
            run.status = "failed"
            run.finished_at = utcnow()
            run.error_summary = (
                "WB feedbacks/questions token is not configured for reputation sync"
            )
            await self._upsert_integration(
                session,
                account_id=int(account.id),
                status="not_configured",
                warnings=warnings,
            )
            await session.commit()
            return ReputationSyncOut(
                status="not_configured",
                account_id=int(account.id),
                job_id=str(run.id),
                message="WB feedbacks/questions token is not configured",
                **lifecycle,
                unavailable_sources=unavailable,
                warnings=warnings,
                trust_state=TrustState.UNAVAILABLE,
                data={
                    "sources": per_source_status,
                    "per_source_status": per_source_status,
                    **lifecycle,
                },
            )
        settings_row = await self._settings(session, account_id=int(account.id))
        last_error: str | None = None
        for source_type in ("review", "question"):
            try:
                unanswered_rows = await self._fetch_wb_items(
                    session,
                    account_id=int(account.id),
                    token=token,
                    source_type=source_type,
                    is_answered=False,
                )
                answered_rows = await self._fetch_wb_items(
                    session,
                    account_id=int(account.id),
                    token=token,
                    source_type=source_type,
                    is_answered=True,
                )
                unanswered_stats = await self._upsert_items(
                    session,
                    account_id=int(account.id),
                    item_type=source_type,
                    rows=unanswered_rows,
                )
                answered_stats = await self._upsert_items(
                    session,
                    account_id=int(account.id),
                    item_type=source_type,
                    rows=answered_rows,
                )
                synced_at = utcnow()
                if source_type == "question":
                    settings_row.last_questions_sync_at = synced_at
                else:
                    settings_row.last_sync_at = synced_at
                received = int(unanswered_stats.get("received") or 0) + int(
                    answered_stats.get("received") or 0
                )
                created_count = int(unanswered_stats.get("created") or 0) + int(
                    answered_stats.get("created") or 0
                )
                updated_count = int(unanswered_stats.get("updated") or 0) + int(
                    answered_stats.get("updated") or 0
                )
                stats = {
                    "status": "ok",
                    "received": received,
                    "created": created_count,
                    "updated": updated_count,
                    "unanswered": unanswered_stats,
                    "answered": answered_stats,
                    "cursor": self._sync_cursor_payload(
                        settings_row, source_type=source_type
                    ),
                    "backfill": {
                        "last_full_sync_at": self._iso(
                            getattr(settings_row, "last_full_sync_at", None)
                        ),
                        "full_history_complete": bool(
                            getattr(settings_row, "last_full_sync_at", None)
                        ),
                    },
                }
                source_stats[source_type] = stats
                source_stats[f"{source_type}s"] = stats
                run.rows_received += received
                run.rows_created += created_count
                run.rows_updated += updated_count
            except Exception:
                last_error = f"{source_type}_sync_failed"
                unavailable.append(f"{source_type}s")
                warnings.append(f"{source_type}_sync_failed")
        backlog_result = self._backlog_status(settings_row)
        if backlog_result["status"] == "ready":
            queue_result = await self.process_auto_draft_queue(
                session,
                max_items=int(
                    getattr(settings_row, "auto_draft_limit_per_sync", 30) or 30
                ),
            )
            backlog_result = {**backlog_result, "queue": queue_result}
        if bool(getattr(settings_row, "chat_enabled", False)):
            unavailable.append("chats")
            source_stats["chat"] = {
                "status": "beta_read_only",
                "mode": "read_only",
                "send_enabled": False,
                "events_sync_enabled": False,
                "received": 0,
                "created": 0,
                "updated": 0,
            }
        else:
            unavailable.append("chats")
            source_stats["chat"] = {
                "status": "not_configured",
                "mode": "read_only",
                "send_enabled": False,
                "events_sync_enabled": False,
                "received": 0,
                "created": 0,
                "updated": 0,
            }
        source_stats["chats"] = source_stats["chat"]
        status = (
            "completed"
            if not [item for item in unavailable if item != "chats"]
            else "partial"
        )
        lifecycle = self._sync_lifecycle_status(
            settings_row, token_configured=True, last_error=last_error
        )
        lifecycle["backlog_status"] = str(
            backlog_result.get("status") or lifecycle["backlog_status"]
        )
        lifecycle["chats_sync_status"] = str(source_stats["chat"]["status"])
        run.status = status
        run.finished_at = utcnow()
        run.rows_processed = run.rows_created + run.rows_updated
        run.rows_failed = len([item for item in unavailable if item != "chats"])
        run.error_summary = last_error
        self._set_reputation_lifecycle_config(settings_row, lifecycle)
        await self._upsert_integration(
            session,
            account_id=int(account.id),
            status="ok" if status == "completed" else "degraded",
            warnings=["local", *warnings, "chats_not_configured"],
        )
        await session.commit()
        return ReputationSyncOut(
            status="ok" if status == "completed" else "degraded",
            account_id=int(account.id),
            job_id=str(run.id),
            message="reputation sync completed from WB sources",
            **lifecycle,
            unavailable_sources=unavailable,
            warnings=["chats_not_configured", *warnings],
            trust_state=TrustState.OPERATIONAL
            if status == "completed"
            else TrustState.PROVISIONAL,
            data={
                "sources": source_stats,
                "per_source_status": source_stats,
                "backlog": backlog_result,
                **lifecycle,
            },
        )

    async def list_drafts(
        self,
        session: AsyncSession,
        account: WBAccount,
        *,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> ReputationDraftsOut:
        conditions = [
            OperatorDraft.account_id == int(account.id),
            OperatorDraft.source_module == "reputation",
        ]
        if status:
            conditions.append(OperatorDraft.status == status)
        total = int(
            (
                await session.execute(
                    select(func.count()).select_from(OperatorDraft).where(*conditions)
                )
            ).scalar()
            or 0
        )
        rows = list(
            (
                await session.execute(
                    select(OperatorDraft)
                    .where(*conditions)
                    .order_by(OperatorDraft.updated_at.desc(), OperatorDraft.id.desc())
                    .limit(limit)
                    .offset(offset)
                )
            ).scalars()
        )
        items = [self._draft_out(row) for row in rows]
        return ReputationDraftsOut(
            account_id=int(account.id),
            total=total,
            limit=limit,
            offset=offset,
            items=items,
            summary=self._draft_summary(items),
        )

    async def approve_all_drafts(
        self, session: AsyncSession, account: WBAccount, *, limit: int = 200
    ) -> ReputationBulkDraftDecisionOut:
        rows = list(
            (
                await session.execute(
                    select(OperatorDraft)
                    .where(
                        OperatorDraft.account_id == int(account.id),
                        OperatorDraft.source_module == "reputation",
                        OperatorDraft.status == "new",
                    )
                    .order_by(OperatorDraft.updated_at.asc(), OperatorDraft.id.asc())
                    .limit(max(1, min(int(limit), 500)))
                )
            ).scalars()
        )
        now = utcnow().isoformat()
        published_count = 0
        warnings: list[str] = []
        for draft in rows:
            draft.status = "done"
            draft.payload_json = {
                **(draft.payload_json or {}),
                "approved_at": now,
                "bulk_approved": True,
                "approval_scope": "approve_all_publish",
                "publish_attempted": bool(self.settings.enable_reputation_publish),
            }
            if self.settings.enable_reputation_publish:
                published, publish_warnings = await self._publish_draft_to_wb(
                    session,
                    account,
                    draft=draft,
                    user_id=None,
                    event_type="draft_approved_published",
                    event_message="Draft approved by bulk action and published to WB.",
                )
                if published:
                    published_count += 1
                elif publish_warnings:
                    draft.payload_json = {
                        **(draft.payload_json or {}),
                        "approval_scope": "approved_pending_publish",
                        "external_submit_attempted": True,
                        "publish_warnings": publish_warnings,
                    }
                warnings = self._merge_unique([*warnings, *publish_warnings])
        if rows:
            session.add(
                ResultEvent(
                    account_id=int(account.id),
                    source_module="reputation",
                    source_id="bulk",
                    event_type="drafts_bulk_approved_published"
                    if published_count
                    else "drafts_bulk_approved",
                    status="done",
                    message=f"{len(rows)} reputation drafts approved; {published_count} published to WB.",
                    payload_json={
                        "approved_count": len(rows),
                        "published_count": published_count,
                        "publish_attempted": bool(
                            self.settings.enable_reputation_publish
                        ),
                    },
                )
            )
        await session.commit()
        return ReputationBulkDraftDecisionOut(
            account_id=int(account.id),
            approved_count=len(rows),
            published_count=published_count,
            total=len(rows),
            warnings=warnings,
            data={"published_count": published_count},
        )

    async def _publish_draft_to_wb(
        self,
        session: AsyncSession,
        account: WBAccount,
        *,
        draft: OperatorDraft,
        user_id: int | None,
        text_override: str | None = None,
        event_type: str = "publish_confirmed",
        event_message: str = "Reply published to WB.",
    ) -> tuple[bool, list[str]]:
        if not self.settings.enable_reputation_publish:
            return False, ["reputation_publish_disabled"]
        item_id = str(
            draft.external_id or (draft.payload_json or {}).get("item_id") or ""
        )
        row = await self._find_item(
            session, account_id=int(account.id), item_id=item_id
        )
        if row is None:
            return False, ["source_item_missing"]
        token = await self._feedbacks_questions_token(
            session, account_id=int(account.id)
        )
        if token is None:
            return False, ["wb_feedbacks_questions_token_not_configured"]
        settings_row = await self._settings(session, account_id=int(account.id))
        text = self._sanitize_reply(
            text_override or draft.body_text or "", settings_row
        )
        if not text:
            return False, ["empty_reply"]
        try:
            await self._publish_wb(
                session, account_id=int(account.id), token=token, row=row, text=text
            )
        except Exception:
            return False, ["wb_publish_failed"]

        now = utcnow()
        row.status = "answered"
        row.needs_reply = False
        row.replied_at = now
        row.answer_text = text
        row.answer_state = "published"
        row.answer_editable = True
        draft.status = "published"
        draft.external_status = ExternalStatus.SUBMITTED.value
        draft.payload_json = {
            **(draft.payload_json or {}),
            "approval_scope": "published_to_wb",
            "publish_attempted": True,
            "external_submit_attempted": True,
            "published_by": user_id,
            "published_at": now.isoformat(),
            "published_text": text,
        }
        session.add(
            ResultEvent(
                account_id=int(account.id),
                draft_id=draft.id,
                source_module="reputation",
                source_id=item_id,
                external_id=row.external_id,
                event_type=event_type,
                status="done",
                external_status="submitted",
                message=event_message,
                payload_json={
                    "created_by": user_id,
                    "confirm": True,
                    "feature_flag": "enable_reputation_publish",
                    "text_source": "request" if text_override else "approved_draft",
                },
            )
        )
        return True, []

    async def list_chats(
        self,
        session: AsyncSession,
        account: WBAccount,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> ReputationChatsOut:
        settings_row = await self._settings(session, account_id=int(account.id))
        if not bool(getattr(settings_row, "chat_enabled", False)):
            return ReputationChatsOut(
                status="disabled",
                account_id=int(account.id),
                limit=limit,
                offset=offset,
                unavailable_sources=["chats"],
                warnings=["chat_enabled_false"],
                trust_state=TrustState.UNAVAILABLE,
            )
        inbox = await self.list_inbox(
            session, account, item_type="chat", limit=limit, offset=offset
        )
        return ReputationChatsOut(
            status=inbox.status,
            account_id=int(account.id),
            total=inbox.total,
            limit=limit,
            offset=offset,
            items=inbox.items,
            warnings=["chat_sync_source_not_configured"] if not inbox.items else [],
            trust_state=TrustState.PROVISIONAL,
        )

    async def chat_events(
        self, session: AsyncSession, account: WBAccount, *, chat_id: str
    ) -> ReputationChatEventsOut:
        row = await self._find_item(
            session,
            account_id=int(account.id),
            item_id=f"chat:{chat_id}" if ":" not in chat_id else chat_id,
        )
        events: list[ReputationChatEventOut] = []
        raw_events = []
        if row is not None:
            raw_events = (
                (row.raw_json or {}).get("events")
                or (row.raw_json or {}).get("chat_events")
                or []
            )
        if isinstance(raw_events, list):
            for idx, event in enumerate(raw_events):
                if not isinstance(event, dict):
                    continue
                message = (
                    event.get("message")
                    if isinstance(event.get("message"), dict)
                    else event
                )
                text = str(
                    message.get("text")
                    or message.get("message")
                    or event.get("text")
                    or ""
                )
                sender = str(
                    event.get("sender_role")
                    or message.get("sender")
                    or message.get("role")
                    or "buyer"
                )
                events.append(
                    ReputationChatEventOut(
                        id=str(event.get("event_id") or event.get("id") or idx),
                        chat_id=str(row.external_id if row is not None else chat_id),
                        account_id=int(account.id),
                        event_type=str(event.get("event_type") or "message"),
                        sender_role=sender,
                        text=text,
                        data=event,
                    )
                )
        elif row is not None:
            events.append(
                ReputationChatEventOut(
                    id=f"{row.external_id}:last",
                    chat_id=row.external_id,
                    account_id=int(account.id),
                    text=row.text or "",
                    created_at=row.received_at,
                    data=row.raw_json or {},
                )
            )
        return ReputationChatEventsOut(
            account_id=int(account.id), chat_id=chat_id, items=events
        )

    async def analytics(
        self,
        session: AsyncSession,
        account: WBAccount,
        *,
        date_from: date | None = None,
        date_to: date | None = None,
        granularity: str = "day",
    ) -> ReputationAnalyticsOut:
        settings_row = await self._settings(session, account_id=int(account.id))
        start_dt, end_dt = self._analytics_window(date_from=date_from, date_to=date_to)
        prev_start, prev_end = self._previous_window(start_dt, end_dt)
        base_conditions = [
            ReputationItem.account_id == int(account.id),
            ReputationItem.item_type == "review",
        ]
        conditions = [
            *base_conditions,
            ReputationItem.received_at >= start_dt,
            ReputationItem.received_at <= end_dt,
        ]
        prev_conditions = [
            *base_conditions,
            ReputationItem.received_at >= prev_start,
            ReputationItem.received_at <= prev_end,
        ]
        total = int(
            (
                await session.execute(
                    select(func.count()).select_from(ReputationItem).where(*conditions)
                )
            ).scalar()
            or 0
        )
        prev_total = int(
            (
                await session.execute(
                    select(func.count())
                    .select_from(ReputationItem)
                    .where(*prev_conditions)
                )
            ).scalar()
            or 0
        )
        avg_raw = (
            await session.execute(
                select(func.avg(ReputationItem.rating)).where(
                    *conditions, ReputationItem.rating.is_not(None)
                )
            )
        ).scalar()
        avg_rating = round(float(avg_raw), 1) if avg_raw is not None else None
        rated_total = int(
            (
                await session.execute(
                    select(func.count())
                    .select_from(ReputationItem)
                    .where(*conditions, ReputationItem.rating.is_not(None))
                )
            ).scalar()
            or 0
        )
        positive_count = int(
            (
                await session.execute(
                    select(func.count())
                    .select_from(ReputationItem)
                    .where(*conditions, ReputationItem.rating.in_([4, 5]))
                )
            ).scalar()
            or 0
        )
        by_rating = {value: 0 for value in range(1, 6)}
        for rating, count in (
            await session.execute(
                select(ReputationItem.rating, func.count())
                .where(*conditions, ReputationItem.rating.is_not(None))
                .group_by(ReputationItem.rating)
            )
        ).all():
            if rating is not None and 1 <= int(rating) <= 5:
                by_rating[int(rating)] = int(count or 0)
        category_counts: dict[str, int] = {}
        category_sentiment: dict[str, dict[str, Any]] = {}
        category_labels: dict[str, str] = {}
        rows = list(
            (
                await session.execute(
                    select(
                        ReputationItem.review_categories_json,
                        ReputationItem.review_category_matches_json,
                        ReputationItem.sentiment,
                        ReputationItem.rating,
                    ).where(*conditions)
                )
            ).all()
        )
        for categories, matches, sentiment, rating in rows:
            seen: set[str] = set()
            if isinstance(matches, list) and matches:
                for match in matches:
                    if not isinstance(match, dict):
                        continue
                    code = (
                        str(match.get("code") or match.get("category") or "").strip()
                        or "unknown"
                    )
                    label = str(match.get("label") or code)
                    bucket = str(
                        match.get("sentiment")
                        or sentiment
                        or self._rating_sentiment(rating)
                    )
                    category_labels.setdefault(code, label)
                    if code not in seen:
                        category_counts[code] = category_counts.get(code, 0) + 1
                        seen.add(code)
                    key = f"{code}:{bucket}"
                    current = category_sentiment.setdefault(
                        key, {"key": key, "code": code, "sentiment": bucket, "count": 0}
                    )
                    current["count"] += 1
            elif isinstance(categories, list) and categories:
                for code_raw in categories:
                    code = str(code_raw or "").strip() or "unknown"
                    if code in seen:
                        continue
                    seen.add(code)
                    category_labels.setdefault(code, code)
                    category_counts[code] = category_counts.get(code, 0) + 1
                    bucket = str(sentiment or self._rating_sentiment(rating))
                    key = f"{code}:{bucket}"
                    current = category_sentiment.setdefault(
                        key, {"key": key, "code": code, "sentiment": bucket, "count": 0}
                    )
                    current["count"] += 1
            else:
                category_labels.setdefault("unknown", "Без категории")
                category_counts["unknown"] = category_counts.get("unknown", 0) + 1
                key = "unknown:unknown"
                current = category_sentiment.setdefault(
                    key,
                    {"key": key, "code": "unknown", "sentiment": "unknown", "count": 0},
                )
                current["count"] += 1
        timeline = await self._analytics_timeline(
            session,
            account_id=int(account.id),
            start_dt=start_dt,
            end_dt=end_dt,
            granularity=granularity,
        )
        period_growth = total - prev_total
        growth_pct = (
            round((period_growth / prev_total * 100), 1)
            if prev_total
            else (100.0 if total else 0.0)
        )
        return ReputationAnalyticsOut(
            account_id=int(account.id),
            analytics_status=self._public_analytics_status(settings_row),
            analytics_status_reason=getattr(
                settings_row, "analytics_status_reason", None
            ),
            analytics_enabled=bool(getattr(settings_row, "analytics_enabled", False)),
            analytics_ready=bool(getattr(settings_row, "analytics_ready", False)),
            selected_period=getattr(settings_row, "analytics_period", None),
            total=total,
            prev_total=prev_total,
            period_growth=period_growth,
            growth_pct=growth_pct,
            avg_rating=avg_rating,
            positive_share=int(round(positive_count / rated_total * 100))
            if rated_total
            else 0,
            by_type=category_counts,
            by_category_sentiment=sorted(
                category_sentiment.values(),
                key=lambda item: (-int(item["count"]), str(item["code"])),
            ),
            category_labels=category_labels,
            by_rating=by_rating,
            timeline=timeline,
        )

    async def list_inbox(
        self,
        session: AsyncSession,
        account: WBAccount,
        *,
        item_type: str | None = None,
        status: str | None = None,
        rating: int | None = None,
        sentiment: str | None = None,
        priority: str | None = None,
        nm_id: int | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> ReputationInboxOut:
        conditions = [ReputationItem.account_id == int(account.id)]
        types = self.adapter._item_types(item_type)
        if item_type and "all" not in str(item_type).lower():
            conditions.append(ReputationItem.item_type.in_(types))
        if status:
            conditions.append(ReputationItem.status == status)
        if rating is not None:
            conditions.append(ReputationItem.rating == rating)
        if sentiment:
            conditions.append(ReputationItem.sentiment == sentiment)
        if priority:
            conditions.append(ReputationItem.priority == priority)
        if nm_id is not None:
            conditions.append(ReputationItem.nm_id == int(nm_id))
        if date_from is not None:
            conditions.append(
                ReputationItem.received_at
                >= datetime.combine(date_from, time.min, tzinfo=timezone.utc)
            )
        if date_to is not None:
            conditions.append(
                ReputationItem.received_at
                <= datetime.combine(date_to, time.max, tzinfo=timezone.utc)
            )
        total = int(
            (
                await session.execute(
                    select(func.count()).select_from(ReputationItem).where(*conditions)
                )
            ).scalar()
            or 0
        )
        rows = list(
            (
                await session.execute(
                    select(ReputationItem)
                    .where(*conditions)
                    .order_by(
                        ReputationItem.priority.asc(),
                        ReputationItem.received_at.desc().nullslast(),
                        ReputationItem.id.desc(),
                    )
                    .limit(limit)
                    .offset(offset)
                )
            ).scalars()
        )
        items = [await self._item_out(session, row) for row in rows]
        summary = self._summary(items)
        status_value = "ok" if items else "empty"
        return ReputationInboxOut(
            status=status_value,
            account_id=int(account.id),
            total=total,
            limit=limit,
            offset=offset,
            items=items,
            summary=summary,
            trust_state=TrustState.OPERATIONAL,
            unavailable_sources=[],
        )

    async def summary(
        self,
        session: AsyncSession,
        account: WBAccount,
        *,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> ReputationSummaryOut:
        inbox = await self.list_inbox(
            session, account, date_from=date_from, date_to=date_to, limit=200, offset=0
        )
        settings_row = await self._settings(session, account_id=int(account.id))
        lifecycle = self._sync_lifecycle_status(settings_row, token_configured=True)
        ratings = [item.rating for item in inbox.items if item.rating is not None]
        return ReputationSummaryOut(
            status=inbox.status,
            account_id=int(account.id),
            unanswered_reviews_count=int(
                inbox.summary.get("unanswered_reviews_count") or 0
            ),
            unanswered_questions_count=int(
                inbox.summary.get("unanswered_questions_count") or 0
            ),
            unread_chats_count=int(inbox.summary.get("unread_chats_count") or 0),
            negative_unanswered_count=int(
                inbox.summary.get("negative_unanswered_count") or 0
            ),
            draft_ready_count=sum(
                1
                for item in inbox.items
                if item.draft is not None or item.status in {"draft_ready", "approved"}
            ),
            average_rating=sum(ratings) / len(ratings) if ratings else None,
            sentiment=self._counts(inbox.items, "sentiment"),
            priority=self._counts(inbox.items, "priority"),
            data={"total": inbox.total, "sync_lifecycle": lifecycle},
            trust_state=TrustState.OPERATIONAL,
            **lifecycle,
            **self._runtime_status(),
        )

    async def get_item(
        self, session: AsyncSession, account: WBAccount, *, item_id: str
    ) -> ReputationItemOut:
        row = await self._find_item(
            session, account_id=int(account.id), item_id=item_id
        )
        if row is None:
            return ReputationItemOut(
                id=item_id,
                item_type=self.adapter._split_item_id(item_id)[0],
                account_id=int(account.id),
                status="not_found",
            )
        return await self._item_out(session, row)

    async def generate_draft(
        self,
        session: AsyncSession,
        account: WBAccount,
        *,
        item_id: str,
        draft_type: DraftType | str | None = None,
        text: str | None = None,
        created_by: int | None = None,
        force_ai: bool = False,
    ) -> ReputationDraftMutationOut:
        row = await self._find_item(
            session, account_id=int(account.id), item_id=item_id
        )
        if row is None:
            return ReputationDraftMutationOut(
                status="not_found",
                account_id=int(account.id),
                message="reputation item is not found",
            )
        classification = self._classify_item(row)
        if self._classification_failed(classification):
            generation_meta = self._blocked_generation_meta(
                "classification_failed",
                classification=classification,
                message="classification failed before draft generation",
            )
            row.raw_json = {
                **(row.raw_json or {}),
                "local_classification": classification,
                "draft_generation": generation_meta,
            }
            await session.commit()
            return ReputationDraftMutationOut(
                status="classification_failed",
                account_id=int(account.id),
                draft=None,
                message="Classification failed before draft generation.",
                warnings=["classification_failed"],
                trust_state=TrustState.PROVISIONAL,
            )
        if row.item_type == "review" and not isinstance(
            classification.get("instruction_plan"), dict
        ):
            instruction_plan = await self._classification_instruction_plan(
                session, account_id=int(account.id), classification=classification
            )
            if instruction_plan:
                classification = {
                    **classification,
                    "instruction_plan": instruction_plan,
                }
        if (
            classification.get("requires_manual_attention")
            and not force_ai
            and not text
        ):
            generation_meta = self._blocked_generation_meta(
                "manual_attention_required",
                classification=classification,
                message="manual attention blocks automatic draft generation",
            )
            row.raw_json = {
                **(row.raw_json or {}),
                "local_classification": classification,
            }
            if classification.get("instruction_plan"):
                row.raw_json["local_instruction_plan"] = classification[
                    "instruction_plan"
                ]
            row.raw_json["draft_generation"] = generation_meta
            await session.commit()
            return ReputationDraftMutationOut(
                status="manual_attention_required",
                account_id=int(account.id),
                draft=None,
                message="Manual attention is required before a reputation reply draft can be generated.",
                warnings=["manual_attention", "manual_attention_required"],
                trust_state=TrustState.PROVISIONAL,
            )
        settings_row = await self._settings(session, account_id=int(account.id))
        body, generation_meta = (
            (text, {"source": "manual_text"})
            if text
            else await self._reply_text(
                session, row, settings_row, classification, force_ai=force_ai
            )
        )
        if generation_meta.get("blocked") or not (body or "").strip():
            status = str(generation_meta.get("status") or "generation_failed")
            row.raw_json = {
                **(row.raw_json or {}),
                "local_classification": classification,
                "draft_generation": generation_meta,
            }
            if generation_meta.get("category_instruction_plan"):
                row.raw_json["local_instruction_plan"] = generation_meta[
                    "category_instruction_plan"
                ]
            await session.commit()
            return ReputationDraftMutationOut(
                status=status,
                account_id=int(account.id),
                draft=None,
                message=str(
                    generation_meta.get("message") or "Draft generation was blocked."
                ),
                warnings=[status],
                trust_state=TrustState.PROVISIONAL,
            )
        draft = await self._persist_draft(
            session,
            account_id=int(account.id),
            row=row,
            draft_type=draft_type,
            text=body or "",
            status="new",
            created_by=created_by,
            classification=classification,
            generation_meta=generation_meta,
        )
        row.status = "draft_ready"
        row.needs_reply = True
        row.raw_json = {**(row.raw_json or {}), "local_classification": classification}
        if generation_meta.get("category_instruction_plan"):
            row.raw_json["local_instruction_plan"] = generation_meta[
                "category_instruction_plan"
            ]
        await session.commit()
        warnings = []
        if classification.get("requires_manual_attention"):
            warnings.append(
                "manual_attention_overridden_by_operator"
                if force_ai
                else "manual_attention_recommended"
            )
        if generation_meta.get("reply_mode") == "manual":
            warnings.append("rating_mode_manual")
        if generation_meta.get("ai_error"):
            warnings.append("ai_generation_failed")
        return ReputationDraftMutationOut(
            status="ok",
            account_id=int(account.id),
            draft=draft,
            message="Reply draft saved locally in finance.",
            warnings=warnings,
            trust_state=TrustState.PROVISIONAL,
        )

    async def approve_draft(
        self,
        session: AsyncSession,
        account: WBAccount,
        *,
        draft_id: str,
        approved_by: int | None = None,
    ) -> ReputationDraftMutationOut:
        draft = await self._find_draft(
            session, account_id=int(account.id), draft_id=draft_id
        )
        if draft is None:
            return ReputationDraftMutationOut(
                status="not_found",
                account_id=int(account.id),
                message="draft is not found",
            )
        draft.status = "done"
        draft.payload_json = {
            **(draft.payload_json or {}),
            "approved_by": approved_by,
            "approved_at": utcnow().isoformat(),
            "approval_scope": "approve_publish",
            "publish_attempted": bool(self.settings.enable_reputation_publish),
            "external_submit_attempted": False,
        }
        warnings: list[str] = []
        message = "Draft approved."
        if self.settings.enable_reputation_publish:
            published, warnings = await self._publish_draft_to_wb(
                session,
                account,
                draft=draft,
                user_id=approved_by,
                event_type="draft_approved_published",
                event_message="Draft approved and published to WB.",
            )
            if published:
                message = "Draft approved and published to WB."
            else:
                draft.payload_json = {
                    **(draft.payload_json or {}),
                    "approval_scope": "approved_pending_publish",
                    "external_submit_attempted": True,
                }
                message = "Draft approved; WB publish is pending or blocked."
        await session.commit()
        await session.refresh(draft)
        return ReputationDraftMutationOut(
            status="ok",
            account_id=int(account.id),
            draft=self._draft_out(draft),
            message=message,
            warnings=warnings,
            trust_state=TrustState.PROVISIONAL,
        )

    async def regenerate_draft(
        self,
        session: AsyncSession,
        account: WBAccount,
        *,
        draft_id: str,
        request: ReputationDraftDecisionRequest | None = None,
    ) -> ReputationDraftMutationOut:
        draft = await self._find_draft(
            session, account_id=int(account.id), draft_id=draft_id
        )
        if draft is None:
            return ReputationDraftMutationOut(
                status="not_found",
                account_id=int(account.id),
                message="draft is not found",
            )
        row = await self._find_item(
            session,
            account_id=int(account.id),
            item_id=str(draft.external_id or draft.payload_json.get("item_id") or ""),
        )
        if row is None:
            return ReputationDraftMutationOut(
                status="not_found",
                account_id=int(account.id),
                message="source item is not found",
            )
        classification = self._classify_item(row)
        if row.item_type == "review" and not isinstance(
            classification.get("instruction_plan"), dict
        ):
            instruction_plan = await self._classification_instruction_plan(
                session, account_id=int(account.id), classification=classification
            )
            if instruction_plan:
                classification = {
                    **classification,
                    "instruction_plan": instruction_plan,
                }
        settings_row = await self._settings(session, account_id=int(account.id))
        body, generation_meta = await self._reply_text(
            session,
            row,
            settings_row,
            classification,
            suffix="Updated draft",
            force_ai=bool(
                (getattr(request, "payload", None) or {}).get("force_ai", True)
            ),
        )
        if generation_meta.get("blocked") or not (body or "").strip():
            row.raw_json = {
                **(row.raw_json or {}),
                "local_classification": classification,
                "draft_generation": generation_meta,
            }
            if generation_meta.get("category_instruction_plan"):
                row.raw_json["local_instruction_plan"] = generation_meta[
                    "category_instruction_plan"
                ]
            await session.commit()
            status = str(generation_meta.get("status") or "generation_failed")
            return ReputationDraftMutationOut(
                status=status,
                account_id=int(account.id),
                draft=self._draft_out(draft),
                message=str(
                    generation_meta.get("message") or "Draft regeneration was blocked."
                ),
                warnings=[status],
                trust_state=TrustState.PROVISIONAL,
            )
        previous_payload = dict(draft.payload_json or {})
        previous_generation = (
            previous_payload.get("generation")
            if isinstance(previous_payload.get("generation"), dict)
            else None
        )
        draft.body_text = body
        draft.status = "new"
        draft.payload_json = {
            **previous_payload,
            "regenerate_reason": getattr(request, "reason", None),
            "regenerated_from_draft_id": str(draft.id),
            "previous_generation": previous_generation,
            "classification": classification,
            "generation": generation_meta,
            "approval_scope": None,
            "approved_by": None,
            "approved_at": None,
            "publish_attempted": False,
            "external_submit_attempted": False,
        }
        row.raw_json = {**(row.raw_json or {}), "local_classification": classification}
        if generation_meta.get("category_instruction_plan"):
            row.raw_json["local_instruction_plan"] = generation_meta[
                "category_instruction_plan"
            ]
        await session.commit()
        await session.refresh(draft)
        warnings = ["ai_generation_failed"] if generation_meta.get("ai_error") else []
        return ReputationDraftMutationOut(
            status="ok",
            account_id=int(account.id),
            draft=self._draft_out(draft),
            warnings=warnings,
            trust_state=TrustState.PROVISIONAL,
        )

    async def reject_draft(
        self,
        session: AsyncSession,
        account: WBAccount,
        *,
        draft_id: str,
        request: ReputationDraftDecisionRequest | None = None,
    ) -> ReputationDraftMutationOut:
        draft = await self._find_draft(
            session, account_id=int(account.id), draft_id=draft_id
        )
        if draft is None:
            return ReputationDraftMutationOut(
                status="not_found",
                account_id=int(account.id),
                message="draft is not found",
            )
        draft.status = "ignored"
        draft.payload_json = {
            **(draft.payload_json or {}),
            "reject_reason": getattr(request, "reason", None),
            "rejected_at": utcnow().isoformat(),
            "approval_scope": None,
            "publish_attempted": False,
            "external_submit_attempted": False,
        }
        await session.commit()
        await session.refresh(draft)
        return ReputationDraftMutationOut(
            status="ok",
            account_id=int(account.id),
            draft=self._draft_out(draft),
            trust_state=TrustState.PROVISIONAL,
        )

    async def publish_reply(
        self,
        session: AsyncSession,
        account: WBAccount,
        *,
        draft_id: str,
        request: ReputationPublishRequest,
        user_id: int | None,
    ) -> Any:
        if not request.confirm:
            return self._result(
                account.id,
                "publish_blocked_confirmation_required",
                draft_id=draft_id,
                success=False,
                warnings=["manual_confirm_required"],
            )
        if not self.settings.enable_reputation_publish:
            return self._result(
                account.id,
                "publish_disabled_by_feature_flag",
                draft_id=draft_id,
                success=False,
                warnings=["reputation_publish_disabled"],
            )
        draft = await self._find_draft(
            session, account_id=int(account.id), draft_id=draft_id
        )
        if draft is None or str(draft.status or "") not in {"done", "approved"}:
            return self._result(
                account.id,
                "publish_blocked_approved_draft_required",
                draft_id=draft_id,
                success=False,
                warnings=["approved_draft_required"],
            )
        published, warnings = await self._publish_draft_to_wb(
            session,
            account,
            draft=draft,
            user_id=user_id,
            text_override=request.text,
            event_type="publish_confirmed",
            event_message="Reply published to WB after manual confirmation.",
        )
        if published:
            await session.commit()
            return self._result(
                account.id,
                "publish_confirmed",
                draft_id=draft_id,
                success=True,
                external_status=ExternalStatus.SUBMITTED,
            )
        event_type = "publish_failed"
        if "source_item_missing" in warnings:
            event_type = "publish_blocked_item_missing"
        elif "wb_feedbacks_questions_token_not_configured" in warnings:
            event_type = "publish_not_configured"
        elif "empty_reply" in warnings:
            event_type = "publish_blocked_empty_reply"
        return self._result(
            account.id, event_type, draft_id=draft_id, success=False, warnings=warnings
        )

    async def mark_no_reply_needed(
        self,
        session: AsyncSession,
        account: WBAccount,
        *,
        item_id: str,
        request: ReputationNoReplyRequest,
        user_id: int | None,
    ) -> Any:
        if not request.confirm:
            return self._result(
                account.id,
                "no_reply_blocked_confirmation_required",
                success=False,
                warnings=["manual_confirm_required"],
            )
        row = await self._find_item(
            session, account_id=int(account.id), item_id=item_id
        )
        if row is not None:
            row.status = "ignored"
            row.needs_reply = False
            row.answer_text = "—"
            row.answer_state = "no_reply_needed"
            row.answer_editable = False
        draft = await self._find_draft(
            session, account_id=int(account.id), draft_id=item_id
        )
        if draft is not None and str(getattr(draft, "status", "") or "") in {
            "new",
            "in_progress",
            "draft_ready",
        }:
            draft.status = "rejected"
            draft.external_status = ExternalStatus.CLOSED.value
            draft.payload_json = {
                **(draft.payload_json or {}),
                "reject_reason": "no_reply_needed",
                "rejected_at": utcnow().isoformat(),
                "closed_by_no_reply_needed": True,
                "publish_attempted": False,
                "external_submit_attempted": False,
            }
        event = ResultEvent(
            account_id=int(account.id),
            draft_id=getattr(draft, "id", None),
            source_module="reputation",
            source_id=item_id,
            external_id=item_id,
            event_type="no_reply_needed",
            status="done",
            message="Manual no-reply-needed decision recorded without WB answer.",
            payload_json={
                "created_by": user_id,
                "reason": request.reason,
                "external_submit_attempted": False,
            },
        )
        session.add(event)
        await session.commit()
        return self._result(account.id, "no_reply_needed", success=True)

    async def learning(
        self, session: AsyncSession, account: WBAccount
    ) -> ReputationLearningOut:
        settings_row = await self._settings(session, account_id=int(account.id))
        categories = await self._effective_categories(
            session, account_id=int(account.id)
        )
        entries = await self._learning_entries(session, account_id=int(account.id))
        return ReputationLearningOut(
            account_id=int(account.id),
            enabled=self._learning_enabled(settings_row),
            review_prompt_template=await self._prompt_text(
                session,
                "review_instructions_template",
                self.DEFAULT_REVIEW_PROMPT,
                account_id=int(account.id),
            ),
            question_prompt_template=await self._prompt_text(
                session,
                "question_instructions_template",
                self.DEFAULT_QUESTION_PROMPT,
                account_id=int(account.id),
            ),
            chat_prompt_template=await self._prompt_text(
                session,
                "chat_instructions_template",
                self.DEFAULT_CHAT_PROMPT,
                account_id=int(account.id),
            ),
            stop_words=await self._effective_stop_words(
                session, account_id=int(account.id), settings=settings_row
            ),
            categories=[self._category_out(category) for category in categories],
            entries=[self._learning_entry_out(entry, categories) for entry in entries],
        )

    async def toggle_learning(
        self,
        session: AsyncSession,
        account: WBAccount,
        request: ReputationLearningToggleRequest,
    ) -> ReputationLearningOut:
        settings_row = await self._settings(session, account_id=int(account.id))
        config = dict(getattr(settings_row, "config_json", None) or {})
        learning_cfg = dict(config.get("review_learning") or {})
        learning_cfg["enabled"] = bool(request.enabled)
        config["review_learning"] = learning_cfg
        settings_row.config_json = config
        if request.enabled:
            await self._ensure_account_categories(session, account_id=int(account.id))
        await session.commit()
        return await self.learning(session, account)

    async def update_prompts(
        self,
        session: AsyncSession,
        account: WBAccount,
        request: ReputationPromptUpdateRequest,
    ) -> ReputationLearningOut:
        account_id = int(account.id)
        if request.review_prompt_template is not None:
            await self._set_prompt_text(
                session,
                "review_instructions_template",
                request.review_prompt_template,
                account_id=account_id,
            )
        if request.question_prompt_template is not None:
            await self._set_prompt_text(
                session,
                "question_instructions_template",
                request.question_prompt_template,
                account_id=account_id,
            )
        if request.chat_prompt_template is not None:
            await self._set_prompt_text(
                session,
                "chat_instructions_template",
                request.chat_prompt_template,
                account_id=account_id,
            )
        if request.stop_words is not None:
            await self._set_prompt_json(
                session,
                "review_stop_words",
                self._normalize_string_list(request.stop_words),
                account_id=account_id,
            )
        if request.categories is not None:
            await self._upsert_categories(
                session, account_id=account_id, rows=request.categories
            )
        await session.commit()
        return await self.learning(session, account)

    async def apply_learning(
        self,
        session: AsyncSession,
        account: WBAccount,
        request: ReputationLearningApplyRequest,
    ) -> ReputationLearningOut:
        settings_row = await self._settings(session, account_id=int(account.id))
        if not self._learning_enabled(settings_row):
            return ReputationLearningOut(
                status="disabled",
                account_id=int(account.id),
                enabled=False,
                warnings=["review_learning_disabled"],
            )
        instruction = " ".join(str(request.instruction or "").split())
        if not instruction:
            return ReputationLearningOut(
                status="invalid",
                account_id=int(account.id),
                enabled=True,
                warnings=["empty_instruction"],
            )
        item = (
            await self._find_item(
                session, account_id=int(account.id), item_id=request.item_id
            )
            if request.item_id
            else None
        )
        nm_id = (
            request.nm_id
            if request.nm_id is not None
            else (item.nm_id if item is not None else None)
        )
        target_type = (request.target_type or "").strip().lower()
        if not target_type:
            target_type = (
                "stop_word"
                if request.stop_word
                else ("category_prompt" if request.category_code else "base_prompt")
            )
        applied_text = self._normalize_learning_text(
            instruction,
            target_type=target_type,
            category_code=request.category_code,
            sentiment_scope=request.sentiment_scope,
            stop_word=request.stop_word,
        )
        entry = ReputationLearningEntry(
            account_id=int(account.id),
            reputation_item_id=item.id if item is not None else None,
            nm_id=nm_id,
            target_type=target_type,
            category_code=(request.category_code or "").strip() or None,
            sentiment_scope=(request.sentiment_scope or "").strip() or None,
            user_instruction=instruction,
            applied_text=applied_text,
            stop_word=(request.stop_word or "").strip() or None,
            source_answer_text=(request.answer_text or "").strip() or None,
        )
        session.add(entry)
        if target_type == "category_prompt" and request.category_code:
            await self._append_category_learning(
                session,
                account_id=int(account.id),
                category_code=request.category_code,
                sentiment=request.sentiment_scope,
                text=instruction,
            )
        elif target_type == "stop_word":
            words = await self._effective_stop_words(
                session, account_id=int(account.id), settings=settings_row
            )
            word = (request.stop_word or applied_text).strip()
            if word:
                await self._set_prompt_json(
                    session,
                    "review_stop_words",
                    self._merge_unique([*words, word]),
                    account_id=int(account.id),
                )
        await session.commit()
        return await self.learning(session, account)

    async def delete_learning_entry(
        self, session: AsyncSession, account: WBAccount, entry_id: int
    ) -> ReputationLearningOut:
        entry = await session.get(ReputationLearningEntry, int(entry_id))
        if entry is not None and entry.account_id == int(account.id):
            entry.is_active = False
            await session.commit()
        return await self.learning(session, account)

    async def reset_learning(
        self, session: AsyncSession, account: WBAccount
    ) -> ReputationLearningOut:
        account_id = int(account.id)
        for entry in await self._learning_entries(session, account_id=account_id):
            entry.is_active = False
        scope = self._account_scope(account_id)
        for record in (
            await session.execute(
                select(ReputationPromptRecord).where(
                    ReputationPromptRecord.scope == scope
                )
            )
        ).scalars():
            await session.delete(record)
        for category in (
            await session.execute(
                select(ReputationReviewCategory).where(
                    ReputationReviewCategory.scope == scope
                )
            )
        ).scalars():
            await session.delete(category)
        settings_row = await self._settings(session, account_id=account_id)
        config = dict(getattr(settings_row, "config_json", None) or {})
        learning_cfg = dict(config.get("review_learning") or {})
        learning_cfg["enabled"] = True
        config["review_learning"] = learning_cfg
        settings_row.config_json = config
        await session.commit()
        return await self.learning(session, account)

    async def product_insights(
        self, session: AsyncSession, account: WBAccount, *, nm_id: int, limit: int = 20
    ) -> ReputationProductInsightOut:
        conditions = [
            ReputationItem.account_id == int(account.id),
            ReputationItem.nm_id == int(nm_id),
        ]
        rows = list(
            (
                await session.execute(
                    select(ReputationItem)
                    .where(*conditions)
                    .order_by(
                        ReputationItem.received_at.desc().nullslast(),
                        ReputationItem.id.desc(),
                    )
                    .limit(max(1, min(limit, 100)))
                )
            ).scalars()
        )
        total = int(
            (
                await session.execute(
                    select(func.count()).select_from(ReputationItem).where(*conditions)
                )
            ).scalar()
            or 0
        )
        avg_raw = (
            await session.execute(
                select(func.avg(ReputationItem.rating)).where(
                    *conditions, ReputationItem.rating.is_not(None)
                )
            )
        ).scalar()
        rating_distribution = {str(value): 0 for value in range(1, 6)}
        for rating, count in (
            await session.execute(
                select(ReputationItem.rating, func.count())
                .where(*conditions, ReputationItem.rating.is_not(None))
                .group_by(ReputationItem.rating)
            )
        ).all():
            rating_distribution[str(int(rating))] = int(count or 0)
        category_counts: dict[str, dict[str, Any]] = {}
        pain_points: dict[str, dict[str, Any]] = {}
        wants: dict[str, dict[str, Any]] = {}
        for row in rows:
            classification = self._classify_item(row)
            categories = (
                classification.get("categories")
                if isinstance(classification.get("categories"), list)
                else []
            )
            for category in categories:
                if not isinstance(category, dict):
                    continue
                code = str(category.get("code") or "unknown")
                label = str(category.get("label") or code)
                target = category_counts.setdefault(
                    code, {"code": code, "label": label, "count": 0}
                )
                target["count"] += 1
                if (row.rating or 0) <= 3 or classification.get(
                    "sentiment"
                ) == "negative":
                    pain = pain_points.setdefault(
                        code, {"code": code, "label": label, "count": 0, "examples": []}
                    )
                    pain["count"] += 1
                    if len(pain["examples"]) < 3:
                        pain["examples"].append(
                            (row.text or row.cons or "").strip()[:240]
                        )
            for keyword in self._customer_want_keywords(row):
                target = wants.setdefault(
                    keyword, {"keyword": keyword, "count": 0, "examples": []}
                )
                target["count"] += 1
                if len(target["examples"]) < 3:
                    target["examples"].append((row.text or "").strip()[:240])
        categories = await self._effective_categories(
            session, account_id=int(account.id)
        )
        learning_entries = await self._learning_entries(
            session, account_id=int(account.id), nm_id=int(nm_id)
        )
        prompt_rules = self._prompt_rules_for_categories(
            categories, category_counts.keys()
        )
        return ReputationProductInsightOut(
            account_id=int(account.id),
            nm_id=int(nm_id),
            total=total,
            avg_rating=round(float(avg_raw), 2) if avg_raw is not None else None,
            rating_distribution=rating_distribution,
            top_categories=sorted(
                category_counts.values(), key=lambda item: -int(item["count"])
            ),
            pain_points=sorted(
                pain_points.values(), key=lambda item: -int(item["count"])
            ),
            customer_wants=sorted(wants.values(), key=lambda item: -int(item["count"])),
            prompt_rules=prompt_rules,
            learning_entries=[
                self._learning_entry_out(entry, categories)
                for entry in learning_entries
            ],
            recent_items=[await self._item_out(session, row) for row in rows[:10]],
        )

    async def get_settings(
        self, session: AsyncSession, account: WBAccount
    ) -> ReputationSettingsOut:
        return self._settings_out(
            await self._settings(session, account_id=int(account.id))
        )

    async def brands(
        self, session: AsyncSession, account: WBAccount
    ) -> ReputationBrandsOut:
        account_id = int(account.id)
        core_sku_brands = (
            await session.execute(
                select(CoreSKU.brand)
                .where(
                    CoreSKU.account_id == account_id,
                    CoreSKU.is_active.is_(True),
                    CoreSKU.brand.is_not(None),
                )
                .distinct()
            )
        ).scalars()
        product_card_brands = (
            await session.execute(
                select(WBProductCard.brand)
                .where(
                    WBProductCard.account_id == account_id,
                    WBProductCard.brand.is_not(None),
                )
                .distinct()
            )
        ).scalars()
        reputation_item_brands = (
            await session.execute(
                select(
                    func.coalesce(
                        func.jsonb_extract_path_text(
                            ReputationItem.product_details_json, "brand_name"
                        ),
                        func.jsonb_extract_path_text(
                            ReputationItem.product_details_json, "brandName"
                        ),
                        func.jsonb_extract_path_text(
                            ReputationItem.product_details_json, "brand"
                        ),
                    )
                )
                .where(ReputationItem.account_id == account_id)
                .distinct()
            )
        ).scalars()

        seen: set[str] = set()
        brands: list[str] = []
        for value in [*core_sku_brands, *product_card_brands, *reputation_item_brands]:
            brand = str(value or "").strip()
            if not brand:
                continue
            key = brand.lower()
            if key in seen:
                continue
            seen.add(key)
            brands.append(brand)

        return ReputationBrandsOut(
            account_id=account_id,
            brands=sorted(brands, key=lambda item: item.lower()),
            total=len(brands),
        )

    async def admin_prompt_debug_context(
        self, session: AsyncSession, account: WBAccount, *, item_id: str
    ) -> dict[str, Any]:
        row = await self._find_item(
            session, account_id=int(account.id), item_id=item_id
        )
        if row is None:
            return {
                "status": "not_found",
                "account_id": int(account.id),
                "item_id": item_id,
            }
        settings_row = await self._settings(session, account_id=int(account.id))
        classification = self._classify_item(row)
        if row.item_type == "review" and not isinstance(
            classification.get("instruction_plan"), dict
        ):
            instruction_plan = await self._classification_instruction_plan(
                session, account_id=int(account.id), classification=classification
            )
            if instruction_plan:
                classification = {
                    **classification,
                    "instruction_plan": instruction_plan,
                }
        prompt_context = await self._prompt_context(
            session, item=row, settings=settings_row, classification=classification
        )
        instructions, input_text = self._build_ai_prompt_parts(
            row, settings_row, classification, prompt_context=prompt_context
        )
        debug_trace = self._generation_debug_trace(
            item=row,
            settings=settings_row,
            classification=classification,
            prompt_context=prompt_context,
            instructions=instructions,
            input_text=input_text,
        )
        draft = await self._active_draft_for_item(
            session,
            account_id=int(account.id),
            item_id=f"{row.item_type}:{row.external_id}",
        )
        return self._scrub_reputation_admin_payload(
            {
                "status": "ok",
                "account_id": int(account.id),
                "item": self._admin_item_context(row),
                "classification": classification,
                "prompt_context": prompt_context,
                "instructions": instructions,
                "input_text": input_text,
                "raw_messages": debug_trace.get("raw_messages") or [],
                "debug_trace": debug_trace,
                "latest_draft": self._generation_log_from_draft(draft)
                if draft is not None
                else None,
            }
        )

    async def admin_prompt_probe(
        self,
        session: AsyncSession,
        account: WBAccount,
        *,
        item_id: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = payload if isinstance(payload, dict) else {}
        dry_run = bool(payload.get("dry_run", True))
        context = await self.admin_prompt_debug_context(
            session, account, item_id=item_id
        )
        if context.get("status") != "ok":
            return context
        if not dry_run:
            return {
                **context,
                "status": "blocked",
                "probe": {
                    "dry_run": False,
                    "network_attempted": False,
                    "message": "Live prompt probe is disabled in Finance admin until provider write/debug policy is explicitly enabled.",
                },
            }
        return {
            **context,
            "probe": {
                "dry_run": True,
                "network_attempted": False,
                "message": "Prompt probe dry-run built instructions/input without contacting an AI provider.",
            },
        }

    async def admin_provider_status(
        self, session: AsyncSession, account: WBAccount
    ) -> dict[str, Any]:
        row = await self._settings(session, account_id=int(account.id))
        provider = str(getattr(row, "ai_provider", None) or "openai").strip().lower()
        model = str(getattr(row, "ai_model", None) or self.settings.openai_model)
        return {
            "status": "ok",
            "account_id": int(account.id),
            "runtime_mode": self._runtime_status()["runtime_mode"],
            "provider": provider,
            "model": model,
            "ai_enabled": bool(getattr(row, "ai_enabled", False)),
            "provider_configured": provider == "openai"
            and bool(self.settings.openai_api_key),
            "dry_run_supported": True,
            "live_probe_enabled": False,
            "network_checked": False,
        }

    async def admin_generation_logs(
        self,
        session: AsyncSession,
        account: WBAccount,
        *,
        limit: int = 50,
        offset: int = 0,
        status: str | None = None,
        provider: str | None = None,
        q: str | None = None,
    ) -> dict[str, Any]:
        conditions = [
            OperatorDraft.account_id == int(account.id),
            OperatorDraft.source_module == "reputation",
        ]
        if status:
            conditions.append(OperatorDraft.status == status)
        if q:
            term = f"%{q.strip()}%"
            conditions.append(
                OperatorDraft.external_id.ilike(term)
                | OperatorDraft.source_id.ilike(term)
                | OperatorDraft.title.ilike(term)
            )
        rows = list(
            (
                await session.execute(
                    select(OperatorDraft)
                    .where(*conditions)
                    .order_by(OperatorDraft.updated_at.desc(), OperatorDraft.id.desc())
                    .limit(max(1, min(int(limit), 200)))
                    .offset(max(0, int(offset)))
                )
            ).scalars()
        )
        items = [self._generation_log_from_draft(row) for row in rows]
        if provider:
            items = [
                item
                for item in items
                if str(item.get("provider") or "").lower() == provider.lower()
            ]
        total = int(
            (
                await session.execute(
                    select(func.count()).select_from(OperatorDraft).where(*conditions)
                )
            ).scalar()
            or 0
        )
        return self._scrub_reputation_admin_payload(
            {
                "status": "ok",
                "total": total,
                "limit": limit,
                "offset": offset,
                "items": items,
            }
        )

    async def admin_generation_log_detail(
        self, session: AsyncSession, account: WBAccount, *, log_id: int
    ) -> dict[str, Any]:
        row = await session.get(OperatorDraft, int(log_id))
        if (
            row is None
            or int(row.account_id) != int(account.id)
            or row.source_module != "reputation"
        ):
            return {
                "status": "not_found",
                "account_id": int(account.id),
                "id": int(log_id),
            }
        item = None
        if row.external_id:
            item = await self._find_item(
                session, account_id=int(account.id), item_id=str(row.external_id)
            )
        result = self._generation_log_from_draft(row, detail=True)
        if item is not None:
            result["item"] = self._admin_item_context(item)
        return self._scrub_reputation_admin_payload({"status": "ok", **result})

    async def update_settings(
        self,
        session: AsyncSession,
        account: WBAccount,
        *,
        request: ReputationSettingsUpdateRequest,
    ) -> ReputationSettingsOut:
        row = await self._settings(session, account_id=int(account.id))
        payload = request.payload or {}
        for field in (
            "reply_mode",
            "tone",
            "language",
            "signature",
            "questions_reply_mode",
            "analytics_period",
        ):
            value = getattr(request, field, None)
            if value is not None:
                setattr(row, field, value)
        for field in (
            "automation_enabled",
            "auto_sync",
            "auto_draft",
            "questions_auto_draft",
            "chat_enabled",
            "analytics_enabled",
        ):
            value = getattr(request, field, None)
            if value is not None:
                setattr(row, field, bool(value))
        auto_publish = request.auto_publish_enabled
        if auto_publish is None:
            auto_publish = request.auto_publish
        if auto_publish is None:
            auto_publish = payload.get(
                "auto_publish_enabled", payload.get("auto_publish")
            )
        if auto_publish is not None:
            row.auto_publish_enabled = bool(auto_publish)
        chat_auto_reply = request.chat_auto_reply_enabled
        if chat_auto_reply is None:
            chat_auto_reply = request.chat_auto_reply
        if chat_auto_reply is None:
            chat_auto_reply = payload.get(
                "chat_auto_reply_enabled", payload.get("chat_auto_reply")
            )
        if chat_auto_reply is not None:
            row.chat_auto_reply_enabled = bool(chat_auto_reply)
        questions_auto_publish = request.questions_auto_publish
        if questions_auto_publish is None:
            questions_auto_publish = payload.get("questions_auto_publish")
        if questions_auto_publish is not None:
            row.questions_auto_publish = bool(questions_auto_publish)
        if request.auto_draft_limit_per_sync is not None:
            row.auto_draft_limit_per_sync = max(
                0, min(int(request.auto_draft_limit_per_sync), 500)
            )
        if request.templates is not None:
            row.templates_json = request.templates
        if request.signatures is not None:
            row.signatures_json = self._normalize_signature_items(request.signatures)
        rating_mode_map = request.rating_mode_map or payload.get("rating_mode_map")
        if rating_mode_map is not None:
            row.rating_mode_map_json = self._normalize_rating_mode_map(rating_mode_map)
        config = request.config or payload.get("config")
        if isinstance(config, dict):
            row.config_json = self._merge_prompt_config(config)
        blacklist_keywords = request.blacklist_keywords or payload.get(
            "blacklist_keywords"
        )
        if blacklist_keywords is not None:
            row.blacklist_keywords_json = self._normalize_string_list(
                blacklist_keywords
            )
        whitelist_keywords = request.whitelist_keywords or payload.get(
            "whitelist_keywords"
        )
        if whitelist_keywords is not None:
            row.whitelist_keywords_json = self._normalize_string_list(
                whitelist_keywords
            )
        ai_payload = payload.get("ai") if isinstance(payload.get("ai"), dict) else {}
        ai_enabled = (
            request.ai_enabled
            if request.ai_enabled is not None
            else ai_payload.get("enabled")
        )
        if ai_enabled is not None:
            row.ai_enabled = bool(ai_enabled)
        ai_provider = request.ai_provider or ai_payload.get("provider")
        if ai_provider:
            row.ai_provider = str(ai_provider).strip().lower()[:32] or "openai"
        ai_model = (
            request.ai_model
            if request.ai_model is not None
            else ai_payload.get("model")
        )
        if ai_model is not None:
            row.ai_model = str(ai_model).strip()[:120] or None
        if getattr(row, "analytics_enabled", False):
            row.analytics_status = "ready"
            row.analytics_ready = True
            row.analytics_status_reason = None
            row.analytics_status_updated_at = utcnow()
        else:
            row.analytics_status = "activation_required"
            row.analytics_ready = False
        await session.commit()
        return self._settings_out(row)

    async def reputation_actions(
        self, session: AsyncSession, account: WBAccount, *, limit: int = 50
    ) -> tuple[list[PortalActionRead], str | None]:
        inbox = await self.list_inbox(session, account, limit=limit, offset=0)
        return [
            self._action_from_item(item) for item in inbox.items if item.needs_reply
        ], None

    async def action_center_enabled(
        self, session: AsyncSession, account: WBAccount
    ) -> bool:
        row = await self._settings(session, account_id=int(account.id))
        config = row.config_json if isinstance(row.config_json, dict) else {}
        return bool(
            config.get("action_center_enabled") is True
            or config.get("action_center_beta_enabled") is True
            or config.get("include_reputation_actions") is True
        )

    async def update_action_center_shadow_status(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        source_id: str,
        status: str,
        comment: str | None = None,
        user_id: int | None = None,
    ) -> dict[str, Any]:
        item = await self._find_item(session, account_id=account_id, item_id=source_id)
        draft = await self._find_draft(
            session, account_id=account_id, draft_id=source_id
        )
        changed: dict[str, Any] = {
            "reputation_item_updated": False,
            "reputation_draft_updated": False,
            "external_operation": False,
            "marketplace_change": False,
        }
        now = utcnow()
        if item is not None:
            if status == "ignored":
                item.status = "ignored"
                item.needs_reply = False
                changed["reputation_item_status"] = item.status
                changed["reputation_item_updated"] = True
            elif status == "in_progress":
                item.status = "in_progress"
                changed["reputation_item_status"] = item.status
                changed["reputation_item_updated"] = True
            elif status == "postponed":
                item.status = "in_progress"
                raw = item.raw_json if isinstance(item.raw_json, dict) else {}
                raw["action_center_status"] = "postponed"
                raw["action_center_comment"] = comment
                item.raw_json = raw
                changed["reputation_item_status"] = item.status
                changed["reputation_item_updated"] = True
            elif status == "blocked":
                item.status = "manual_attention"
                item.review_requires_manual_attention = True
                changed["reputation_item_status"] = item.status
                changed["reputation_item_updated"] = True
            elif status == "done":
                raw = item.raw_json if isinstance(item.raw_json, dict) else {}
                raw["action_center_status"] = "done"
                raw["action_center_closed_at"] = now.isoformat()
                raw["action_center_comment"] = comment
                raw["action_center_user_id"] = user_id
                item.raw_json = raw
                if item.status in {"new", "needs_reply", "in_progress", "draft_ready"}:
                    item.status = "draft_ready" if draft is not None else item.status
                changed["reputation_item_status"] = item.status
                changed["reputation_item_updated"] = True
        if draft is not None:
            if status == "ignored":
                draft.status = "rejected"
                draft.external_status = ExternalStatus.NOT_CREATED.value
            elif status == "in_progress":
                draft.status = ActionStatus.IN_PROGRESS.value
            elif status == "done":
                draft.status = ActionStatus.DONE.value
                draft.external_status = ExternalStatus.DRAFT_READY.value
            elif status in {"blocked", "postponed"}:
                draft.status = ActionStatus.IN_PROGRESS.value
            payload = draft.payload_json if isinstance(draft.payload_json, dict) else {}
            payload.update(
                {
                    "action_center_status": status,
                    "action_center_comment": comment,
                    "action_center_user_id": user_id,
                    "external_operation": False,
                    "marketplace_change": False,
                }
            )
            draft.payload_json = payload
            changed["reputation_draft_status"] = draft.status
            changed["reputation_draft_id"] = draft.id
            changed["reputation_draft_updated"] = True
        return changed

    async def process_auto_draft_queue(
        self, session: AsyncSession, *, max_items: int = 50
    ) -> dict[str, int | str]:
        if not self.settings.reputation_auto_draft_enabled:
            return {"status": "disabled", "processed": 0, "created": 0}
        rows = list(
            (
                await session.execute(
                    select(ReputationItem)
                    .join(
                        ReputationSettings,
                        ReputationSettings.account_id == ReputationItem.account_id,
                    )
                    .where(
                        ReputationSettings.auto_draft.is_(True),
                        ReputationSettings.automation_enabled.is_(True),
                        ReputationItem.needs_reply.is_(True),
                        ReputationItem.status.in_(
                            ("new", "needs_reply", "in_progress")
                        ),
                        ReputationItem.item_type.in_(("review", "question")),
                    )
                    .order_by(
                        ReputationItem.priority.asc(),
                        ReputationItem.received_at.asc().nullslast(),
                        ReputationItem.id.asc(),
                    )
                    .limit(max(1, min(int(max_items), 200)))
                )
            ).scalars()
        )
        processed = created = 0
        for row in rows:
            existing = (
                await session.execute(
                    select(OperatorDraft.id)
                    .where(
                        OperatorDraft.account_id == row.account_id,
                        OperatorDraft.source_module == "reputation",
                        OperatorDraft.external_id
                        == f"{row.item_type}:{row.external_id}",
                        OperatorDraft.status.in_(("new", "done")),
                    )
                    .limit(1)
                )
            ).scalar_one_or_none()
            if existing is not None:
                continue
            account = await session.get(WBAccount, row.account_id)
            if account is None:
                continue
            settings_row = await self._settings(session, account_id=row.account_id)
            allowed, _reason = self._auto_draft_allowed_for_item(settings_row, row)
            if not allowed:
                continue
            await self.generate_draft(
                session,
                account,
                item_id=f"{row.item_type}:{row.external_id}",
                created_by=None,
            )
            processed += 1
            created += 1
        return {"status": "ok", "processed": processed, "created": created}

    async def profit_doctor_signals(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        date_from: Any = None,
        date_to: Any = None,
        nm_id: int | None = None,
    ) -> list[dict[str, Any]]:
        account = await session.get(WBAccount, account_id)
        if account is None:
            return []
        inbox = await self.list_inbox(
            session,
            account,
            nm_id=nm_id,
            date_from=date_from,
            date_to=date_to,
            limit=100,
            offset=0,
        )
        return [
            {
                "nm_id": item.nm_id,
                "priority": item.priority,
                "title": self.adapter._action_title(item),
                "reason": item.text,
                "next_step": "Откройте репутацию и подготовьте черновик ответа.",
                "impact": self.adapter._impact(item),
                "source_id": item.id,
            }
            for item in inbox.items
            if item.needs_reply
        ]

    async def product_360(
        self, session: AsyncSession, *, account_id: int, nm_id: int, **_: Any
    ) -> PortalDataBlock:
        account = await session.get(WBAccount, account_id)
        if account is None:
            return PortalDataBlock(
                status="unavailable",
                data={"last_items": []},
                message="account is unavailable",
            )
        inbox = await self.list_inbox(session, account, nm_id=nm_id, limit=50, offset=0)
        actions = [
            self._action_from_item(item).model_dump(mode="json")
            for item in inbox.items
            if item.needs_reply
        ]
        ratings = [int(item.rating) for item in inbox.items if item.rating is not None]
        rating_breakdown = {
            str(value): sum(1 for rating in ratings if rating == value)
            for value in range(1, 6)
        }
        reviews_count = sum(1 for item in inbox.items if item.item_type == "review")
        questions_count = sum(1 for item in inbox.items if item.item_type == "question")
        unanswered_count = sum(1 for item in inbox.items if item.needs_reply)
        sentiment_counts: dict[str, int] = {}
        category_counts: dict[str, int] = {}
        for item in inbox.items:
            if item.sentiment:
                sentiment_counts[str(item.sentiment)] = (
                    sentiment_counts.get(str(item.sentiment), 0) + 1
                )
            classification = (
                (item.data or {}).get("local_classification")
                if isinstance(item.data, dict)
                else None
            )
            categories = (
                classification.get("categories")
                if isinstance(classification, dict)
                else []
            )
            for category in categories if isinstance(categories, list) else []:
                if not isinstance(category, dict):
                    continue
                label = str(category.get("label") or category.get("code") or "").strip()
                if label:
                    category_counts[label] = category_counts.get(label, 0) + 1
        summary = {
            **inbox.summary,
            "total": inbox.total,
            "reviews_count": reviews_count,
            "questions_count": questions_count,
            "answered_count": max(0, len(inbox.items) - unanswered_count),
            "unanswered_count": unanswered_count,
            "rating_breakdown": rating_breakdown,
            "average_rating": (sum(ratings) / len(ratings)) if ratings else None,
            "sentiment_counts": sentiment_counts,
            "category_counts": category_counts,
        }
        return PortalDataBlock(
            status=inbox.status,
            data={
                **summary,
                "summary": summary,
                "last_items": [
                    item.model_dump(mode="json") for item in inbox.items[:10]
                ],
                "items": [item.model_dump(mode="json") for item in inbox.items],
                "actions": actions,
                "next_reputation_action": actions[0] if actions else None,
            },
        )

    async def _store_wb_raw_response(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        endpoint: str,
        http_method: str,
        request_params: dict[str, Any] | None = None,
        request_body: Any | None = None,
        response: httpx.Response,
        response_json: Any,
        requested_at: datetime,
        loaded_at: datetime,
        error_text: str | None = None,
    ) -> None:
        await self.raw_service.store(
            session,
            account_id=account_id,
            api_category=WBAPICategory.FEEDBACKS_QUESTIONS.value,
            endpoint=endpoint,
            http_method=http_method,
            request_params=request_params or {},
            request_body=request_body,
            response_json=response_json,
            response_text=response.text,
            response_headers={
                str(key).lower(): str(value) for key, value in response.headers.items()
            },
            status_code=response.status_code,
            is_success=response.status_code < 400,
            retry_count=0,
            requested_at=requested_at,
            loaded_at=loaded_at,
            error_text=error_text,
        )

    async def _fetch_wb_items(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        token: str,
        source_type: str,
        is_answered: bool,
    ) -> list[dict[str, Any]]:
        take = 100
        skip = 0
        max_pages = 20
        rows: list[dict[str, Any]] = []
        seen_pages: set[tuple[str, ...]] = set()
        path = "/api/v1/feedbacks" if source_type == "review" else "/api/v1/questions"
        async with httpx.AsyncClient(
            base_url=self.WB_BASE_URL,
            timeout=self.settings.wb_http_timeout,
            headers={"Authorization": token},
        ) as client:
            for _ in range(max_pages):
                params = {
                    "isAnswered": str(is_answered).lower(),
                    "take": take,
                    "skip": skip,
                    "order": "dateDesc",
                }
                requested_at = utcnow()
                response = await client.get(path, params=params)
                loaded_at = utcnow()
                payload: Any = {}
                if response.text:
                    try:
                        payload = response.json()
                    except ValueError:
                        payload = {"rawText": response.text}
                await self._store_wb_raw_response(
                    session,
                    account_id=account_id,
                    endpoint=path,
                    http_method="GET",
                    request_params=params,
                    response=response,
                    response_json=payload,
                    requested_at=requested_at,
                    loaded_at=loaded_at,
                    error_text=None
                    if response.status_code < 400
                    else response.text[:500],
                )
                response.raise_for_status()
                page_rows = self.adapter._rows(payload)
                page_signature = tuple(
                    str(
                        row.get("id")
                        or row.get("feedback_id")
                        or row.get("question_id")
                        or ""
                    )
                    for row in page_rows
                )
                if page_signature and page_signature in seen_pages:
                    break
                seen_pages.add(page_signature)
                rows.extend(page_rows)
                if len(page_rows) < take:
                    break
                skip += take
        return rows

    def _dedupe_wb_rows(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        deduped: dict[str, dict[str, Any]] = {}
        fallback_index = 0
        for row in rows:
            row_id = (
                row.get("id")
                or row.get("feedback_id")
                or row.get("question_id")
                or row.get("external_id")
            )
            key = str(row_id) if row_id else f"row:{fallback_index}"
            fallback_index += 1
            deduped[key] = row
        return list(deduped.values())

    async def _publish_wb(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        token: str,
        row: ReputationItem,
        text: str,
    ) -> None:
        if row.item_type == "chat":
            raise RuntimeError("chat publish is not configured")
        async with httpx.AsyncClient(
            base_url=self.WB_BASE_URL,
            timeout=self.settings.wb_http_timeout,
            headers={"Authorization": token, "Content-Type": "application/json"},
        ) as client:
            if row.item_type == "review":
                path = "/api/v1/feedbacks/answer"
                body = {"id": row.external_id, "text": text}
                requested_at = utcnow()
                response = await client.post(path, json=body)
            else:
                path = "/api/v1/questions"
                body = {"id": row.external_id, "text": text}
                requested_at = utcnow()
                response = await client.patch(path, json=body)
            loaded_at = utcnow()
            payload: Any = (
                {"noData": True}
                if response.status_code == 204 and not response.text
                else {}
            )
            if response.text:
                try:
                    payload = response.json()
                except ValueError:
                    payload = {"rawText": response.text}
            await self._store_wb_raw_response(
                session,
                account_id=account_id,
                endpoint=path,
                http_method="POST" if row.item_type == "review" else "PATCH",
                request_body=body,
                response=response,
                response_json=payload,
                requested_at=requested_at,
                loaded_at=loaded_at,
                error_text=None if response.status_code < 400 else response.text[:500],
            )
            response.raise_for_status()

    async def _upsert_items(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        item_type: str,
        rows: list[dict[str, Any]],
    ) -> dict[str, int | str]:
        created = updated = 0
        effective_categories = (
            await self._effective_categories(session, account_id=account_id)
            if rows
            else []
        )
        for payload in rows:
            item = self.adapter._item_from_payload(
                account_id=account_id, kind=item_type, payload=payload
            )
            classification = self._classify_payload(
                item_type=item_type,
                rating=item.rating,
                text=item.text,
                payload=item.source_payload or payload,
            )
            instruction_plan = (
                self._category_instruction_plan(effective_categories, classification)
                if item_type == "review"
                else {}
            )
            if instruction_plan:
                classification = {
                    **classification,
                    "instruction_plan": instruction_plan,
                }
            priority = classification.get("priority") or (
                item.priority.value
                if hasattr(item.priority, "value")
                else str(item.priority)
            )
            sentiment = classification.get("sentiment") or item.sentiment
            needs_reply = bool(item.needs_reply)
            if classification.get("requires_manual_attention"):
                needs_reply = True
            primary = (
                classification.get("primary_category")
                if isinstance(classification.get("primary_category"), dict)
                else {}
            )
            category_matches = (
                classification.get("categories")
                if isinstance(classification.get("categories"), list)
                else []
            )
            category_codes = self._unique_category_codes(category_matches)
            values = {
                "account_id": account_id,
                "item_type": item_type,
                "external_id": item.external_id or item.id,
                "external_thread_id": item.data.get("thread_id"),
                "nm_id": item.nm_id,
                "sku_id": item.sku_id,
                "rating": item.rating,
                "title": item.title,
                "text": item.text,
                "pros": self._payload_text(payload, "pros"),
                "cons": self._payload_text(payload, "cons"),
                "answer_text": self._payload_text(
                    payload, "answer_text", "answerText", "answer", "answer_text"
                ),
                "answer_state": self._payload_text(
                    payload, "answer_state", "answerState"
                ),
                "answer_editable": self._payload_bool(
                    payload, "answer_editable", "answerEditable"
                ),
                "buyer_name_masked": item.buyer_name,
                "status": item.status,
                "external_status": item.external_status.value
                if hasattr(item.external_status, "value")
                else str(item.external_status),
                "sentiment": sentiment,
                "priority": priority,
                "review_type": str((primary or {}).get("code") or "") or None,
                "review_categories_json": category_codes,
                "review_category_matches_json": category_matches,
                "review_need_reply_score": int(
                    classification.get("need_reply_score") or 0
                ),
                "review_requires_manual_attention": bool(
                    classification.get("requires_manual_attention")
                ),
                "needs_reply": needs_reply,
                "received_at": item.received_at,
                "replied_at": item.replied_at,
                "product_details_json": self._product_details(
                    payload, item.source_payload
                ),
                "media_json": self._media(payload, item.source_payload),
                "bables_json": self._bables(payload, item.source_payload),
                "raw_json": {
                    **(item.source_payload or payload or {}),
                    "local_classification": classification,
                    "local_instruction_plan": instruction_plan,
                },
            }
            existing_id = (
                await session.execute(
                    select(ReputationItem.id).where(
                        ReputationItem.account_id == account_id,
                        ReputationItem.item_type == item_type,
                        ReputationItem.external_id == values["external_id"],
                    )
                )
            ).scalar_one_or_none()
            stmt = (
                pg_insert(ReputationItem)
                .values(**values)
                .on_conflict_do_update(
                    constraint="uq_reputation_items_account_type_external",
                    set_={
                        key: values[key]
                        for key in values
                        if key not in {"account_id", "item_type", "external_id"}
                    },
                )
                .returning(ReputationItem.id)
            )
            result = await session.execute(stmt)
            if result.scalar_one_or_none():
                if existing_id is None:
                    created += 1
                else:
                    updated += 1
        return {
            "status": "ok",
            "received": len(rows),
            "created": created,
            "updated": updated,
        }

    async def _feedbacks_questions_token(
        self, session: AsyncSession, *, account_id: int
    ) -> str | None:
        row = (
            (
                await session.execute(
                    select(WBAPIToken).where(
                        WBAPIToken.account_id == account_id,
                        WBAPIToken.category == WBAPICategory.FEEDBACKS_QUESTIONS.value,
                        WBAPIToken.is_active.is_(True),
                    )
                )
            )
            .scalars()
            .first()
        )
        return decrypt_wb_token(row.token_encrypted) if row is not None else None

    async def _has_feedbacks_questions_token(
        self, session: AsyncSession, *, account_id: int
    ) -> bool:
        return (
            await self._feedbacks_questions_token(session, account_id=account_id)
        ) is not None

    async def _find_item(
        self, session: AsyncSession, *, account_id: int, item_id: str
    ) -> ReputationItem | None:
        kind, external_id = self.adapter._split_item_id(item_id)
        return (
            (
                await session.execute(
                    select(ReputationItem).where(
                        ReputationItem.account_id == account_id,
                        ReputationItem.item_type == kind,
                        ReputationItem.external_id == external_id,
                    )
                )
            )
            .scalars()
            .first()
        )

    async def _find_draft(
        self, session: AsyncSession, *, account_id: int, draft_id: str
    ) -> OperatorDraft | None:
        if str(draft_id).isdigit():
            row = await session.get(OperatorDraft, int(draft_id))
            if (
                row is not None
                and row.account_id == account_id
                and row.source_module == "reputation"
            ):
                return row
        return (
            (
                await session.execute(
                    select(OperatorDraft).where(
                        OperatorDraft.account_id == account_id,
                        OperatorDraft.source_module == "reputation",
                        OperatorDraft.external_id == draft_id,
                    )
                )
            )
            .scalars()
            .first()
        )

    async def _item_out(
        self, session: AsyncSession, row: ReputationItem
    ) -> ReputationItemOut:
        draft = (
            (
                await session.execute(
                    select(OperatorDraft)
                    .where(
                        OperatorDraft.account_id == row.account_id,
                        OperatorDraft.source_module == "reputation",
                        OperatorDraft.external_id
                        == f"{row.item_type}:{row.external_id}",
                    )
                    .order_by(OperatorDraft.updated_at.desc(), OperatorDraft.id.desc())
                    .limit(1)
                )
            )
            .scalars()
            .first()
        )
        raw_json = row.raw_json if isinstance(row.raw_json, dict) else {}
        return ReputationItemOut(
            id=f"{row.item_type}:{row.external_id}",
            item_type=row.item_type,
            item_id=f"{row.item_type}:{row.external_id}",
            kind=row.item_type,
            external_id=row.external_id,
            external_status=row.external_status,
            account_id=row.account_id,
            nm_id=row.nm_id,
            sku_id=row.sku_id,
            rating=row.rating,
            buyer_name=row.buyer_name_masked,
            title=row.title or "",
            text=row.text or "",
            pros=row.pros,
            cons=row.cons,
            answer_text=row.answer_text,
            answer_state=row.answer_state,
            answer_editable=row.answer_editable,
            sentiment=row.sentiment,
            priority=row.priority,
            review_type=row.review_type,
            review_categories=row.review_categories_json or [],
            review_category_matches=row.review_category_matches_json or [],
            review_instruction_plan=self._stored_instruction_plan(raw_json),
            review_need_reply_score=self._compatible_need_reply_score(
                row.review_need_reply_score,
                bool(row.review_requires_manual_attention),
            ),
            review_requires_manual_attention=bool(row.review_requires_manual_attention),
            status=row.status,
            trust_state=TrustState.OPERATIONAL,
            received_at=row.received_at,
            created_at=row.received_at,
            replied_at=row.replied_at,
            needs_reply=row.needs_reply,
            draft=self._draft_out(draft) if draft else None,
            product_details=row.product_details_json or {},
            media=row.media_json or [],
            bables=row.bables_json or [],
            data=raw_json,
            source_payload=raw_json,
        )

    def _stored_instruction_plan(
        self, raw_json: dict[str, Any]
    ) -> dict[str, Any] | None:
        plan = raw_json.get("local_instruction_plan")
        if not isinstance(plan, dict):
            classification = raw_json.get("local_classification")
            if isinstance(classification, dict):
                plan = classification.get("instruction_plan")
        if not isinstance(plan, dict) or not plan:
            return None
        return plan

    async def _classification_instruction_plan(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        classification: dict[str, Any],
    ) -> dict[str, Any]:
        if not hasattr(session, "execute"):
            categories = [
                ReputationReviewCategory(
                    scope="global",
                    code=str(row["code"]),
                    label=str(row["label"]),
                    positive_prompt=str(row["positive_prompt"]),
                    negative_prompt=str(row["negative_prompt"]),
                    sort_order=int(row.get("sort_order") or index * 10),
                    is_active=True,
                )
                for index, row in enumerate(self.DEFAULT_REVIEW_CATEGORIES, start=1)
            ]
        else:
            categories = await self._effective_categories(
                session, account_id=account_id
            )
        return self._category_instruction_plan(categories, classification)

    async def _persist_draft(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        row: ReputationItem,
        draft_type: DraftType | str | None,
        text: str,
        status: str,
        created_by: int | None,
        classification: dict[str, Any] | None = None,
        generation_meta: dict[str, Any] | None = None,
    ) -> DraftOut:
        kind = row.item_type
        item_id = f"{kind}:{row.external_id}"
        effective_type = self.adapter._draft_type(kind, draft_type)
        draft = (
            (
                await session.execute(
                    select(OperatorDraft).where(
                        OperatorDraft.account_id == account_id,
                        OperatorDraft.source_module == "reputation",
                        OperatorDraft.external_id == item_id,
                    )
                )
            )
            .scalars()
            .first()
        )
        if draft is None:
            draft = OperatorDraft(
                account_id=account_id,
                source_module="reputation",
                source_id=f"reputation:{item_id}:draft",
                external_id=item_id,
                draft_type=effective_type.value,
            )
            session.add(draft)
        draft.status = status
        draft.external_status = ExternalStatus.DRAFT_READY.value
        draft.title = "Reply draft"
        draft.body_text = text
        draft.nm_id = row.nm_id
        draft.payload_json = {
            "source_type": kind,
            "source_id": row.external_id,
            "item_id": item_id,
            "created_by": created_by,
            "marketplace_change": False,
            "classification": classification or self._classify_item(row),
            "generation": generation_meta or {"source": "local_rules"},
        }
        await session.flush()
        return self._draft_out(draft)

    def _draft_out(self, draft: OperatorDraft) -> DraftOut:
        return DraftOut(
            id=str(draft.id),
            draft_type=draft.draft_type,
            external_status=draft.external_status,
            account_id=draft.account_id,
            source_type=(draft.payload_json or {}).get("source_type"),
            source_id=(draft.payload_json or {}).get("source_id"),
            title=draft.title or "Reply draft",
            text=self._strip_reply_artifacts(draft.body_text or ""),
            status=draft.status,
            trust_state=TrustState.PROVISIONAL,
            requires_confirmation=True,
            created_by=(draft.payload_json or {}).get("created_by"),
            approved_by=(draft.payload_json or {}).get("approved_by"),
            created_at=draft.created_at,
            updated_at=draft.updated_at,
            data=draft.payload_json or {},
        )

    async def _active_draft_for_item(
        self, session: AsyncSession, *, account_id: int, item_id: str
    ) -> OperatorDraft | None:
        return (
            (
                await session.execute(
                    select(OperatorDraft)
                    .where(
                        OperatorDraft.account_id == account_id,
                        OperatorDraft.source_module == "reputation",
                        OperatorDraft.external_id == item_id,
                    )
                    .order_by(OperatorDraft.updated_at.desc(), OperatorDraft.id.desc())
                    .limit(1)
                )
            )
            .scalars()
            .first()
        )

    def _admin_item_context(self, row: ReputationItem) -> dict[str, Any]:
        return {
            "id": f"{row.item_type}:{row.external_id}",
            "item_type": row.item_type,
            "external_id": row.external_id,
            "nm_id": row.nm_id,
            "sku_id": row.sku_id,
            "rating": row.rating,
            "title": row.title,
            "text": row.text,
            "pros": row.pros,
            "cons": row.cons,
            "buyer_name_masked": row.buyer_name_masked,
            "status": row.status,
            "sentiment": row.sentiment,
            "priority": row.priority,
            "received_at": self._iso(row.received_at),
            "review_need_reply_score": row.review_need_reply_score,
            "review_requires_manual_attention": row.review_requires_manual_attention,
            "review_category_matches": row.review_category_matches_json or [],
            "product_details": row.product_details_json or {},
        }

    def _generation_log_from_draft(
        self, draft: OperatorDraft, *, detail: bool = False
    ) -> dict[str, Any]:
        payload = draft.payload_json if isinstance(draft.payload_json, dict) else {}
        generation = (
            payload.get("generation")
            if isinstance(payload.get("generation"), dict)
            else {}
        )
        trace = (
            generation.get("debug_trace")
            if isinstance(generation.get("debug_trace"), dict)
            else {}
        )
        provider = trace.get("provider") or generation.get("provider")
        model = (
            trace.get("model") or generation.get("ai_model") or generation.get("model")
        )
        item = {
            "id": int(draft.id),
            "created_at": self._iso(draft.created_at),
            "updated_at": self._iso(draft.updated_at),
            "account_id": int(draft.account_id),
            "operation_type": "reputation_draft",
            "source": generation.get("source") or "unknown",
            "status": generation.get("status") or draft.status,
            "provider": provider,
            "model": model,
            "entity_type": payload.get("source_type"),
            "entity_id": payload.get("source_id"),
            "entity_wb_id": draft.external_id,
            "draft_id": int(draft.id),
            "rating": (trace.get("classification_context") or {}).get("rating")
            if isinstance(trace.get("classification_context"), dict)
            else None,
            "prompt_tokens": trace.get("prompt_tokens"),
            "completion_tokens": trace.get("completion_tokens"),
            "latency_ms": trace.get("latency_ms"),
            "output_text": self._strip_reply_artifacts(draft.body_text or ""),
            "error_message": trace.get("error") or generation.get("ai_error"),
            "blocked_reason": trace.get("blocked_reason"),
            "fallback_reason": trace.get("fallback_reason")
            or generation.get("fallback_reason"),
        }
        if detail:
            item.update(
                {
                    "instructions": trace.get("instructions"),
                    "input_text": trace.get("input_text"),
                    "raw_messages": trace.get("raw_messages") or [],
                    "settings_snapshot": trace.get("settings_snapshot") or {},
                    "context": trace.get("classification_context")
                    or payload.get("classification")
                    or {},
                    "build_params": {
                        "reply_mode": generation.get("reply_mode"),
                        "ai_attempted": generation.get("ai_attempted"),
                        "prompt_mode": generation.get("prompt_mode"),
                        "learning_enabled": generation.get("learning_enabled"),
                        "prompt_rules_count": generation.get("prompt_rules_count"),
                        "category_rules_count": generation.get("category_rules_count"),
                    },
                    "debug_report": trace,
                    "payload": payload,
                }
            )
        return item

    def _scrub_reputation_admin_payload(self, value: Any) -> Any:
        private_tokens = {
            "address",
            "api_key",
            "authorization",
            "credential",
            "email",
            "encrypted_token",
            "encryption_key",
            "fio",
            "full_name",
            "headers",
            "jwt",
            "passport",
            "password",
            "phone",
            "refresh_token",
            "secret",
            "token",
        }
        if isinstance(value, dict):
            result: dict[str, Any] = {}
            for key, item in value.items():
                key_text = str(key).lower()
                if key_text == "buyer_name_masked":
                    result[key] = item
                    continue
                if any(token in key_text for token in private_tokens):
                    continue
                result[key] = self._scrub_reputation_admin_payload(item)
            return result
        if isinstance(value, list):
            return [self._scrub_reputation_admin_payload(item) for item in value]
        return value

    async def _settings(
        self, session: AsyncSession, *, account_id: int
    ) -> ReputationSettings:
        row = (
            (
                await session.execute(
                    select(ReputationSettings).where(
                        ReputationSettings.account_id == account_id
                    )
                )
            )
            .scalars()
            .first()
        )
        if row is None:
            row = ReputationSettings(account_id=account_id)
            session.add(row)
            await session.flush()
        return row

    def _iso(self, value: Any) -> str | None:
        return value.isoformat() if isinstance(value, datetime) else None

    def _settings_lifecycle_config(
        self, row: ReputationSettings | None
    ) -> dict[str, Any]:
        if row is None:
            return {}
        config = getattr(row, "config_json", None)
        if not isinstance(config, dict):
            return {}
        lifecycle = config.get("reputation_lifecycle")
        return lifecycle if isinstance(lifecycle, dict) else {}

    def _set_reputation_lifecycle_config(
        self, row: ReputationSettings, lifecycle: dict[str, Any]
    ) -> None:
        config = dict(getattr(row, "config_json", None) or {})
        config["reputation_lifecycle"] = {
            **self._settings_lifecycle_config(row),
            **lifecycle,
            "updated_at": utcnow().isoformat(),
        }
        row.config_json = config

    def _sync_cursor_payload(
        self, row: ReputationSettings | None, *, source_type: str
    ) -> dict[str, Any]:
        if source_type == "review":
            return {
                "answered_supported": True,
                "unanswered_supported": True,
                "cursor_at": self._iso(getattr(row, "last_feedback_created_at", None)),
                "last_sync_at": self._iso(getattr(row, "last_sync_at", None)),
            }
        if source_type == "question":
            return {
                "answered_supported": True,
                "unanswered_supported": True,
                "cursor_at": self._iso(getattr(row, "last_questions_sync_at", None)),
                "last_sync_at": self._iso(getattr(row, "last_questions_sync_at", None)),
            }
        return {
            "answered_supported": False,
            "unanswered_supported": False,
            "cursor_at": self._iso(getattr(row, "last_chat_sync_at", None)),
            "next_ms": getattr(row, "chat_next_ms", None),
        }

    def _automation_block_reason(self, row: ReputationSettings | None) -> str | None:
        if row is None:
            return "not_configured"
        config = getattr(row, "config_json", None) or {}
        if not isinstance(config, dict):
            config = {}
        if bool(config.get("kill_switch") or config.get("automation_kill_switch")):
            return "kill_switch"
        if bool(config.get("generation_disabled")):
            return "generation_disabled"
        if not bool(getattr(row, "automation_enabled", False)):
            return "automation_disabled"
        return None

    def _has_safe_auto_rating_mode(self, row: ReputationSettings | None) -> bool:
        if row is None:
            return False
        rating_map = self._normalize_rating_mode_map(
            getattr(row, "rating_mode_map_json", None)
        )
        return any(mode == "auto" for mode in rating_map.values())

    def _auto_draft_allowed_for_item(
        self, row: ReputationSettings, item: ReputationItem
    ) -> tuple[bool, str]:
        reason = self._automation_block_reason(row)
        if reason:
            return False, reason
        if not self.settings.reputation_auto_draft_enabled:
            return False, "global_auto_draft_disabled"
        if item.item_type == "chat":
            return False, "chat_automation_not_configured"
        if item.item_type == "question":
            if not bool(getattr(row, "questions_auto_draft", False)):
                return False, "questions_auto_draft_disabled"
            mode = str(
                getattr(row, "questions_reply_mode", None)
                or getattr(row, "reply_mode", None)
                or "semi"
            )
        else:
            if not bool(getattr(row, "auto_draft", False)):
                return False, "auto_draft_disabled"
            mode = self._effective_reply_mode(
                row, item.rating, item_type=item.item_type
            )
        if mode == "manual":
            return False, "manual_mode"
        return True, "allowed"

    def _backlog_status(self, row: ReputationSettings | None) -> dict[str, Any]:
        reason = self._automation_block_reason(row)
        if reason:
            return {"status": "disabled", "reason": reason, "draft_jobs": 0}
        if not self.settings.reputation_auto_draft_enabled:
            return {
                "status": "disabled",
                "reason": "global_auto_draft_disabled",
                "draft_jobs": 0,
            }
        if not bool(
            getattr(row, "auto_draft", False)
            or getattr(row, "questions_auto_draft", False)
        ):
            return {"status": "idle", "reason": "auto_draft_disabled", "draft_jobs": 0}
        if (
            not self._has_safe_auto_rating_mode(row)
            and str(getattr(row, "questions_reply_mode", "semi")) == "manual"
        ):
            return {"status": "blocked", "reason": "manual_mode", "draft_jobs": 0}
        return {"status": "ready", "reason": "safe_auto_draft_enabled", "draft_jobs": 0}

    def _sync_lifecycle_status(
        self,
        row: ReputationSettings | None,
        *,
        token_configured: bool,
        last_error: str | None = None,
    ) -> dict[str, Any]:
        stored = self._settings_lifecycle_config(row)
        if not token_configured:
            return {
                "reviews_sync_status": "not_configured",
                "questions_sync_status": "not_configured",
                "chats_sync_status": "not_configured",
                "backlog_status": "disabled",
                "automation_status": "not_configured",
                "last_error": last_error or stored.get("last_error"),
            }
        automation_reason = self._automation_block_reason(row)
        backlog = self._backlog_status(row)
        chat_enabled = (
            bool(getattr(row, "chat_enabled", False)) if row is not None else False
        )
        return {
            "reviews_sync_status": "ok"
            if getattr(row, "last_sync_at", None)
            else str(stored.get("reviews_sync_status") or "not_started"),
            "questions_sync_status": "ok"
            if getattr(row, "last_questions_sync_at", None)
            else str(stored.get("questions_sync_status") or "not_started"),
            "chats_sync_status": "beta_read_only" if chat_enabled else "not_configured",
            "backlog_status": str(backlog.get("status") or "disabled"),
            "automation_status": "disabled"
            if automation_reason
            else (
                "draft_ready"
                if backlog.get("status") == "ready"
                else str(backlog.get("status") or "idle")
            ),
            "last_error": last_error or stored.get("last_error"),
        }

    def _settings_out(
        self, row: ReputationSettings, warnings: list[str] | None = None
    ) -> ReputationSettingsOut:
        output_warnings = list(warnings or [])
        ai_enabled = bool(
            getattr(row, "ai_enabled", False)
            or self.settings.reputation_ai_default_enabled
        )
        if ai_enabled and not self.settings.openai_api_key:
            output_warnings.append("openai_api_key_not_configured")
        rating_mode_map = self._normalize_rating_mode_map(
            getattr(row, "rating_mode_map_json", None)
        )
        config = self._merge_prompt_config(getattr(row, "config_json", None) or {})
        automation_enabled = bool(getattr(row, "automation_enabled", False))
        auto_sync = bool(getattr(row, "auto_sync", True))
        auto_draft = bool(getattr(row, "auto_draft", False))
        auto_draft_limit = int(getattr(row, "auto_draft_limit_per_sync", None) or 30)
        auto_publish_enabled = bool(getattr(row, "auto_publish_enabled", False))
        questions_auto_draft = bool(getattr(row, "questions_auto_draft", False))
        questions_auto_publish = bool(getattr(row, "questions_auto_publish", False))
        questions_reply_mode = str(getattr(row, "questions_reply_mode", None) or "semi")
        chat_enabled = bool(getattr(row, "chat_enabled", False))
        chat_auto_reply_enabled = bool(getattr(row, "chat_auto_reply_enabled", False))
        runtime_status = self._runtime_status()
        lifecycle = self._sync_lifecycle_status(row, token_configured=True)
        return ReputationSettingsOut(
            status="ok",
            account_id=row.account_id,
            auto_sync=auto_sync,
            auto_draft=auto_draft,
            auto_draft_limit_per_sync=auto_draft_limit,
            reply_mode=row.reply_mode,
            tone=row.tone,
            language=row.language,
            signature=row.signature,
            templates=row.templates_json or [],
            signatures=[
                item
                for item in self._normalize_signature_items(row.signatures_json or [])
                if item.get("is_active") is not False
            ],
            rating_mode_map=rating_mode_map,
            config=config,
            blacklist_keywords=self._normalize_string_list(
                getattr(row, "blacklist_keywords_json", None) or []
            ),
            whitelist_keywords=self._normalize_string_list(
                getattr(row, "whitelist_keywords_json", None) or []
            ),
            ai_enabled=ai_enabled,
            ai_provider=str(getattr(row, "ai_provider", None) or "openai"),
            ai_model=getattr(row, "ai_model", None) or self.settings.openai_model,
            auto_publish_enabled=auto_publish_enabled,
            auto_publish=auto_publish_enabled,
            automation_enabled=automation_enabled,
            chat_auto_reply_enabled=chat_auto_reply_enabled,
            chat_auto_reply=chat_auto_reply_enabled,
            questions_reply_mode=questions_reply_mode,
            questions_auto_draft=questions_auto_draft,
            questions_auto_publish=questions_auto_publish,
            chat_enabled=chat_enabled,
            analytics_enabled=bool(getattr(row, "analytics_enabled", False)),
            analytics_ready=bool(getattr(row, "analytics_ready", False)),
            analytics_period=getattr(row, "analytics_period", None),
            analytics_status=self._public_analytics_status(row),
            analytics_status_reason=getattr(row, "analytics_status_reason", None),
            **lifecycle,
            trust_state=TrustState.OPERATIONAL,
            warnings=output_warnings,
            runtime_mode=runtime_status["runtime_mode"],
            dangerous_actions_enabled=runtime_status["dangerous_actions_enabled"],
            publish_enabled=runtime_status["publish_enabled"],
            chat_send_enabled=runtime_status["chat_send_enabled"],
            data={
                "rating_mode_map": rating_mode_map,
                "config": config,
                "ai": {
                    "enabled": ai_enabled,
                    "provider": str(getattr(row, "ai_provider", None) or "openai"),
                    "model": getattr(row, "ai_model", None)
                    or self.settings.openai_model,
                    "configured": bool(self.settings.openai_api_key),
                },
                "automation": {
                    "enabled": automation_enabled,
                    "status": lifecycle["automation_status"],
                    "backlog_status": lifecycle["backlog_status"],
                    "auto_sync": auto_sync,
                    "auto_draft": auto_draft,
                    "auto_draft_limit_per_sync": auto_draft_limit,
                    "auto_publish_enabled": auto_publish_enabled,
                    "auto_publish": auto_publish_enabled,
                    "chat_auto_reply_enabled": chat_auto_reply_enabled,
                    "chat_auto_reply": chat_auto_reply_enabled,
                    "questions_reply_mode": questions_reply_mode,
                    "questions_auto_draft": questions_auto_draft,
                    "questions_auto_publish": questions_auto_publish,
                    "chat_enabled": chat_enabled,
                    "chat_mode": "beta_read_only" if chat_enabled else "not_configured",
                },
                "sync_lifecycle": lifecycle,
                "analytics": {
                    "enabled": bool(getattr(row, "analytics_enabled", False)),
                    "ready": bool(getattr(row, "analytics_ready", False)),
                    "period": getattr(row, "analytics_period", None),
                    "status": self._public_analytics_status(row),
                    "status_reason": getattr(row, "analytics_status_reason", None),
                },
            },
        )

    def _account_scope(self, account_id: int) -> str:
        return f"account:{int(account_id)}"

    def _learning_enabled(self, settings: ReputationSettings) -> bool:
        config = getattr(settings, "config_json", None) or {}
        if not isinstance(config, dict):
            return False
        learning_cfg = config.get("review_learning")
        if not isinstance(learning_cfg, dict):
            return False
        return bool(learning_cfg.get("enabled"))

    async def _prompt_record(
        self, session: AsyncSession, key: str, *, account_id: int | None = None
    ) -> ReputationPromptRecord | None:
        scopes = (
            [self._account_scope(account_id), "global"]
            if account_id is not None
            else ["global"]
        )
        for scope in scopes:
            row = (
                (
                    await session.execute(
                        select(ReputationPromptRecord).where(
                            ReputationPromptRecord.scope == scope,
                            ReputationPromptRecord.key == key,
                        )
                    )
                )
                .scalars()
                .first()
            )
            if row is not None:
                return row
        return None

    async def _prompt_text(
        self,
        session: AsyncSession,
        key: str,
        default: str,
        *,
        account_id: int | None = None,
    ) -> str:
        row = await self._prompt_record(session, key, account_id=account_id)
        text = (
            str(getattr(row, "value_text", None) or "").strip()
            if row is not None
            else ""
        )
        return text or default

    async def _prompt_json(
        self,
        session: AsyncSession,
        key: str,
        default: Any,
        *,
        account_id: int | None = None,
    ) -> Any:
        row = await self._prompt_record(session, key, account_id=account_id)
        value = getattr(row, "value_json", None) if row is not None else None
        return value if value is not None else default

    async def _set_prompt_text(
        self, session: AsyncSession, key: str, value: str, *, account_id: int
    ) -> None:
        scope = self._account_scope(account_id)
        row = (
            (
                await session.execute(
                    select(ReputationPromptRecord).where(
                        ReputationPromptRecord.scope == scope,
                        ReputationPromptRecord.key == key,
                    )
                )
            )
            .scalars()
            .first()
        )
        if row is None:
            row = ReputationPromptRecord(scope=scope, key=key)
            session.add(row)
        row.value_text = str(value or "").strip()
        row.value_json = None

    async def _set_prompt_json(
        self, session: AsyncSession, key: str, value: Any, *, account_id: int
    ) -> None:
        scope = self._account_scope(account_id)
        row = (
            (
                await session.execute(
                    select(ReputationPromptRecord).where(
                        ReputationPromptRecord.scope == scope,
                        ReputationPromptRecord.key == key,
                    )
                )
            )
            .scalars()
            .first()
        )
        if row is None:
            row = ReputationPromptRecord(scope=scope, key=key)
            session.add(row)
        row.value_text = None
        row.value_json = value

    async def _effective_categories(
        self, session: AsyncSession, *, account_id: int
    ) -> list[ReputationReviewCategory]:
        account_scope = self._account_scope(account_id)
        account_rows = list(
            (
                await session.execute(
                    select(ReputationReviewCategory)
                    .where(
                        ReputationReviewCategory.scope == account_scope,
                        ReputationReviewCategory.is_active.is_(True),
                    )
                    .order_by(
                        ReputationReviewCategory.sort_order.asc(),
                        ReputationReviewCategory.code.asc(),
                    )
                )
            ).scalars()
        )
        if account_rows:
            return account_rows
        global_rows = list(
            (
                await session.execute(
                    select(ReputationReviewCategory)
                    .where(
                        ReputationReviewCategory.scope == "global",
                        ReputationReviewCategory.is_active.is_(True),
                    )
                    .order_by(
                        ReputationReviewCategory.sort_order.asc(),
                        ReputationReviewCategory.code.asc(),
                    )
                )
            ).scalars()
        )
        if global_rows:
            return global_rows
        return [
            ReputationReviewCategory(
                scope="global",
                code=str(row["code"]),
                label=str(row["label"]),
                positive_prompt=str(row["positive_prompt"]),
                negative_prompt=str(row["negative_prompt"]),
                sort_order=int(row.get("sort_order") or index * 10),
                is_active=True,
            )
            for index, row in enumerate(self.DEFAULT_REVIEW_CATEGORIES, start=1)
        ]

    async def _ensure_account_categories(
        self, session: AsyncSession, *, account_id: int
    ) -> list[ReputationReviewCategory]:
        scope = self._account_scope(account_id)
        existing = list(
            (
                await session.execute(
                    select(ReputationReviewCategory).where(
                        ReputationReviewCategory.scope == scope
                    )
                )
            ).scalars()
        )
        if existing:
            return existing
        for category in await self._effective_categories(
            session, account_id=account_id
        ):
            session.add(
                ReputationReviewCategory(
                    scope=scope,
                    account_id=account_id,
                    code=category.code,
                    label=category.label,
                    positive_prompt=category.positive_prompt,
                    negative_prompt=category.negative_prompt,
                    sort_order=int(category.sort_order or 0),
                    is_active=bool(category.is_active),
                )
            )
        await session.flush()
        return list(
            (
                await session.execute(
                    select(ReputationReviewCategory).where(
                        ReputationReviewCategory.scope == scope
                    )
                )
            ).scalars()
        )

    async def _upsert_categories(
        self, session: AsyncSession, *, account_id: int, rows: list[dict[str, Any]]
    ) -> None:
        scope = self._account_scope(account_id)
        await self._ensure_account_categories(session, account_id=account_id)
        existing = {
            row.code: row
            for row in (
                await session.execute(
                    select(ReputationReviewCategory).where(
                        ReputationReviewCategory.scope == scope
                    )
                )
            ).scalars()
        }
        for payload in rows:
            if not isinstance(payload, dict):
                continue
            code = str(payload.get("code") or "").strip()
            if not code:
                continue
            row = existing.get(code)
            if row is None:
                row = ReputationReviewCategory(
                    scope=scope,
                    account_id=account_id,
                    code=code,
                    label=code,
                    positive_prompt="",
                    negative_prompt="",
                )
                session.add(row)
            row.label = str(payload.get("label") or row.label or code).strip()[:128]
            if payload.get("positive_prompt") is not None:
                row.positive_prompt = str(payload.get("positive_prompt") or "").strip()
            if payload.get("negative_prompt") is not None:
                row.negative_prompt = str(payload.get("negative_prompt") or "").strip()
            if payload.get("sort_order") is not None:
                row.sort_order = int(payload.get("sort_order") or 0)
            if payload.get("is_active") is not None:
                row.is_active = bool(payload.get("is_active"))

    async def _learning_entries(
        self, session: AsyncSession, *, account_id: int, nm_id: int | None = None
    ) -> list[ReputationLearningEntry]:
        conditions = [
            ReputationLearningEntry.account_id == account_id,
            ReputationLearningEntry.is_active.is_(True),
        ]
        if nm_id is not None:
            conditions.append(ReputationLearningEntry.nm_id == int(nm_id))
        return list(
            (
                await session.execute(
                    select(ReputationLearningEntry)
                    .where(*conditions)
                    .order_by(
                        ReputationLearningEntry.created_at.desc(),
                        ReputationLearningEntry.id.desc(),
                    )
                    .limit(300)
                )
            ).scalars()
        )

    def _category_out(
        self, category: ReputationReviewCategory
    ) -> ReputationPromptCategoryOut:
        return ReputationPromptCategoryOut(
            code=category.code,
            label=category.label,
            positive_prompt=category.positive_prompt or "",
            negative_prompt=category.negative_prompt or "",
            sort_order=int(category.sort_order or 0),
            is_active=bool(category.is_active),
            scope=category.scope,
        )

    def _learning_entry_out(
        self, entry: ReputationLearningEntry, categories: list[ReputationReviewCategory]
    ) -> ReputationLearningEntryOut:
        labels = {category.code: category.label for category in categories}
        return ReputationLearningEntryOut(
            id=int(entry.id),
            account_id=int(entry.account_id),
            nm_id=entry.nm_id,
            target_type=entry.target_type,
            category_code=entry.category_code,
            category_label=labels.get(entry.category_code or ""),
            sentiment_scope=entry.sentiment_scope,
            user_instruction=entry.user_instruction,
            applied_text=entry.applied_text,
            stop_word=entry.stop_word,
            source_answer_text=entry.source_answer_text,
            is_active=bool(entry.is_active),
            created_at=entry.created_at,
        )

    def _normalize_learning_text(
        self,
        instruction: str,
        *,
        target_type: str,
        category_code: str | None = None,
        sentiment_scope: str | None = None,
        stop_word: str | None = None,
    ) -> str:
        text = " ".join(str(instruction or "").split()).strip()
        if target_type == "stop_word":
            return (stop_word or text).strip()
        prefix = ""
        if target_type == "category_prompt" and category_code:
            prefix = f"{category_code}"
            if sentiment_scope:
                prefix = f"{prefix}/{sentiment_scope}"
        return f"{prefix}: {text}".strip(": ") if prefix else text

    async def _append_category_learning(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        category_code: str,
        sentiment: str | None,
        text: str,
    ) -> None:
        scope = self._account_scope(account_id)
        await self._ensure_account_categories(session, account_id=account_id)
        category = (
            (
                await session.execute(
                    select(ReputationReviewCategory).where(
                        ReputationReviewCategory.scope == scope,
                        ReputationReviewCategory.code == category_code,
                    )
                )
            )
            .scalars()
            .first()
        )
        if category is None:
            category = ReputationReviewCategory(
                scope=scope,
                account_id=account_id,
                code=category_code,
                label=category_code,
                positive_prompt="",
                negative_prompt="",
                sort_order=999,
                is_active=True,
            )
            session.add(category)
        target_attr = (
            "positive_prompt"
            if str(sentiment or "").lower() == "positive"
            else "negative_prompt"
        )
        current = str(getattr(category, target_attr) or "").strip()
        clean = text.strip()
        if clean and clean.lower() not in current.lower():
            setattr(category, target_attr, f"{current}\n{clean}".strip())

    def _merge_unique(self, values: list[Any]) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        for value in values:
            text = str(value or "").strip()
            key = text.lower()
            if text and key not in seen:
                seen.add(key)
                result.append(text)
        return result

    async def _effective_stop_words(
        self, session: AsyncSession, *, account_id: int, settings: ReputationSettings
    ) -> list[str]:
        config = self._merge_prompt_config(getattr(settings, "config_json", None) or {})
        advanced = config.get("advanced", {})
        prompt_words = await self._prompt_json(
            session, "review_stop_words", [], account_id=account_id
        )
        learned_entries = await self._learning_entries(session, account_id=account_id)
        learned_words = [
            entry.stop_word or entry.applied_text
            for entry in learned_entries
            if entry.target_type == "stop_word"
        ]
        return self._merge_unique(
            [
                *self._normalize_string_list(
                    advanced.get("stop_words") if isinstance(advanced, dict) else []
                ),
                *self._normalize_string_list(
                    getattr(settings, "blacklist_keywords_json", None) or []
                ),
                *self._normalize_string_list(prompt_words),
                *learned_words,
            ]
        )

    def _hard_max_len(self, answer_length: str | None) -> int:
        value = str(answer_length or "default").strip().lower()
        return {
            "short": 500,
            "default": 800,
            "medium": 800,
            "long": 1400,
            "detailed": 1400,
        }.get(value, 800)

    def _tone_instruction(self, tone_key: str | None) -> str | None:
        key = str(tone_key or "").strip().lower()
        if not key or key in {"none", "без тональности", "no", "off"}:
            return None
        mapping = {
            "business": "Business tone: formal, concise, without slang.",
            "деловая": "Business tone: formal, concise, without slang.",
            "joking": "Light, appropriate humor if it does not undermine the situation.",
            "шутливая": "Light, appropriate humor if it does not undermine the situation.",
            "serious": "Serious tone: focus on facts, apologies, and next steps; avoid jokes.",
            "серьёзная": "Serious tone: focus on facts, apologies, and next steps; avoid jokes.",
            "серьезная": "Serious tone: focus on facts, apologies, and next steps; avoid jokes.",
            "encouraging": "Encouraging tone: reassure the customer and offer help.",
            "ободряющая": "Encouraging tone: reassure the customer and offer help.",
            "caring": "Caring tone: warm, empathic, service-oriented.",
            "заботливая": "Caring tone: warm, empathic, service-oriented.",
            "cheerful": "Cheerful tone: friendly, upbeat, but still professional.",
            "весёлая": "Cheerful tone: friendly, upbeat, but still professional.",
            "веселая": "Cheerful tone: friendly, upbeat, but still professional.",
            "friendly": "Friendly tone: personable and approachable.",
            "дружелюбная": "Friendly tone: personable and approachable.",
            "chatty": "Conversational tone: slightly more talkative, but keep it readable.",
            "болтливая": "Conversational tone: slightly more talkative, but keep it readable.",
            "respectful": "Respectful tone: neutral, polite, and tactful.",
            "уважительная": "Respectful tone: neutral, polite, and tactful.",
            "poetic": "Poetic tone: mild metaphors are allowed, but keep the meaning clear.",
            "поэтическая": "Poetic tone: mild metaphors are allowed, but keep the meaning clear.",
            "dramatic": "Dramatic tone: expressive, but not exaggerated.",
            "драматическая": "Dramatic tone: expressive, but not exaggerated.",
            "scientific": "Scientific tone: factual, structured, and precise.",
            "научная": "Scientific tone: factual, structured, and precise.",
            "warm": "Warm tone: polite, friendly, and not overly emotional.",
            "polite": "Polite tone: respectful, clear, and concise.",
            "empathetic": "Empathetic tone. Show understanding, apologize if appropriate, offer help.",
            "clear": "Clear tone: direct, helpful, and easy to understand.",
        }
        return mapping.get(key) or f"Tone of voice: {tone_key}."

    def _prompt_format_values(
        self,
        settings: ReputationSettings,
        item: ReputationItem,
        *,
        classification: dict[str, Any],
        stop_words: list[str],
    ) -> dict[str, Any]:
        config = self._merge_prompt_config(getattr(settings, "config_json", None) or {})
        advanced = config["advanced"]
        tone = str(getattr(settings, "tone", None) or "polite")
        address_format = (
            str(advanced.get("address_format") or "vy_lower").strip().lower()
        )
        if address_format == "vy_caps":
            addr_rule = "Use polite address with capitalized 'Вы/Ваш/Вам'."
        elif address_format == "ty":
            addr_rule = "Use informal address 'ты/твой'."
        else:
            addr_rule = "Use polite address 'вы/ваш/вам' (lowercase)."
        answer_length = str(advanced.get("answer_length") or "default").strip().lower()
        if answer_length == "short":
            length_rule = "Keep it short (1-2 sentences)."
        elif answer_length in {"long", "detailed"}:
            length_rule = "Allow a longer answer if needed (up to ~5 sentences)."
        else:
            length_rule = "Answer length: default."
        emoji_rule = (
            "Emojis: required. Include exactly 1 relevant emoji in the reply."
            if bool(advanced.get("emoji_enabled"))
            else "Emojis: disabled."
        )
        product = self._product_details_for_prompt(item)
        brand = (
            str(
                product.get("brand_name")
                or product.get("brandName")
                or product.get("brand")
                or ""
            ).strip()
            or None
        )
        signature = self._pick_signature(
            settings,
            kind=item.item_type,
            brand=brand,
            rating=item.rating,
        )
        stop_words_rule = (
            f"Avoid these words/phrases: {', '.join(stop_words[:40])}."
            if stop_words
            else ""
        )
        signature_rule = (
            f"End with this signature if appropriate: {signature}." if signature else ""
        )
        return {
            "language": getattr(settings, "language", None) or "ru",
            "tone": tone,
            "hard_max_len": self._hard_max_len(answer_length),
            "stop_words_rule": stop_words_rule,
            "signature_rule": signature_rule,
            "addr_rule": addr_rule,
            "length_rule": length_rule,
            "emoji_rule": emoji_rule,
            "address_format_instruction": addr_rule,
            "answer_length_instruction": length_rule,
            "emoji_instruction": emoji_rule,
            "category_instructions": "",
            "brand": str(brand or ""),
            "buyer_name": "",
        }

    def _render_prompt_template(self, template: str, values: dict[str, Any]) -> str:
        class _SafeFormatDict(dict):
            def __missing__(self, key: str) -> str:
                return ""

        text = str(template or "")
        try:
            rendered = text.format_map(_SafeFormatDict(values))
        except Exception:
            rendered = text
        for key, value in (values or {}).items():
            rendered = rendered.replace(
                "{" + str(key) + "}", "" if value is None else str(value)
            )
        return rendered.strip()

    def _learning_rule_text(self, entry: ReputationLearningEntry) -> str:
        text = str(entry.applied_text or entry.user_instruction or "").strip()
        if not text:
            return ""
        category = str(entry.category_code or "").strip()
        sentiment = str(entry.sentiment_scope or "").strip()
        prefixes = []
        if category and sentiment:
            prefixes.append(f"{category}/{sentiment}:")
        if category:
            prefixes.append(f"{category}:")
        lower = text.lower()
        for prefix in prefixes:
            if lower.startswith(prefix.lower()):
                text = text[len(prefix) :].strip()
                break
        if entry.target_type == "category_prompt" and category:
            scope = f" для категории {category}"
            if sentiment:
                scope += f" ({sentiment})"
            return f"Правило оператора{scope}: {text}"
        if entry.target_type == "base_prompt":
            return f"Общее правило оператора: {text}"
        return text

    def _category_instruction_plan(
        self,
        categories: list[ReputationReviewCategory],
        classification: dict[str, Any],
    ) -> dict[str, Any]:
        category_map = {category.code: category for category in categories}
        matches = [
            item
            for item in (classification.get("categories") or [])
            if isinstance(item, dict) and str(item.get("code") or "").strip()
        ]
        routing_scores = self._collect_routing_scores(matches, classification)
        candidates: list[dict[str, Any]] = []
        for code in self._unique_category_codes(matches):
            category = category_map.get(code)
            if category is None:
                continue
            code_matches = [
                match
                for match in matches
                if str(match.get("code") or "").strip().lower() == code
            ]
            bucket = self._category_bucket_from_matches(code_matches, classification)
            role = self._semantic_role(code, code_matches[0] if code_matches else None)
            ai_score = routing_scores.get(
                code, self._default_routing_score_for_role(role, bucket)
            )
            candidates.append(
                {
                    "code": code,
                    "category": category,
                    "bucket": bucket,
                    "role": role,
                    "ai_score": ai_score,
                    "weighted_score": self._weighted_routing_score(
                        role, bucket, ai_score
                    ),
                }
            )
        if not candidates:
            return self._empty_instruction_plan(
                routing_scores=routing_scores,
                routing_primary_candidate=classification.get(
                    "routing_primary_candidate"
                ),
                routing_secondary_candidate=classification.get(
                    "routing_secondary_candidate"
                ),
            )
        candidates.sort(
            key=lambda item: (
                -int(item["weighted_score"]),
                self._issue_strength_for_role(str(item["role"])),
                int(getattr(item["category"], "sort_order", 0) or 0),
                int(getattr(item["category"], "id", 0) or 0),
                str(item["code"]),
            )
        )
        primary = candidates[0]
        defect_candidate = next(
            (item for item in candidates if item["role"] == "product_defect"), None
        )
        delivery_candidate = next(
            (item for item in candidates if item["role"] == "delivery_packaging"), None
        )
        if (
            defect_candidate is not None
            and defect_candidate["code"] != primary["code"]
            and int(defect_candidate["weighted_score"])
            >= int(primary["weighted_score"]) - 10
        ):
            primary = defect_candidate
        elif (
            delivery_candidate is not None
            and delivery_candidate["code"] != primary["code"]
            and int(delivery_candidate["weighted_score"])
            >= int(primary["weighted_score"]) - 8
        ):
            primary = delivery_candidate
        ordered_candidates = [primary] + [
            item for item in candidates if item["code"] != primary["code"]
        ]
        top2 = ordered_candidates[1] if len(ordered_candidates) > 1 else None
        routing_margin = (
            int(primary["weighted_score"]) - int(top2["weighted_score"])
            if top2
            else int(primary["weighted_score"])
        )
        clear_primary = int(
            primary["weighted_score"]
        ) >= self.ROUTING_CLEAR_PRIMARY_SCORE or (
            int(primary["weighted_score"]) >= self.ROUTING_MIN_PRIMARY_SCORE
            and routing_margin >= self.ROUTING_CLEAR_MARGIN
        )
        soft_primary = (
            int(primary["weighted_score"]) >= self.ROUTING_MIN_PRIMARY_SCORE
            and routing_margin >= self.ROUTING_SOFT_MARGIN
        )
        no_clear_primary = not (clear_primary or soft_primary)
        has_concrete_category = any(
            not self._is_meta_role(str(item["role"])) for item in ordered_candidates
        )
        has_concrete_price_pressure = (
            primary["role"] != "price_complaint"
            and not self._is_meta_role(str(primary["role"]))
        ) or any(
            item["code"] != primary["code"]
            and item["role"] != "price_complaint"
            and not self._is_meta_role(str(item["role"]))
            for item in ordered_candidates
        )
        secondary_candidates: list[dict[str, Any]] = []
        for item in ordered_candidates:
            if item["code"] == primary["code"]:
                continue
            if self._is_meta_role(str(item["role"])):
                continue
            if int(item["weighted_score"]) < self.ROUTING_MIN_SECONDARY_SCORE:
                continue
            if (
                primary["bucket"] in {"negative", "mixed"}
                and not self._is_meta_role(str(primary["role"]))
                and item["role"] == "price_complaint"
            ):
                continue
            if item["bucket"] == "negative":
                continue
            secondary_candidates.append(item)
        secondary = None
        if secondary_candidates:
            secondary_candidates.sort(
                key=lambda item: (
                    0
                    if item["bucket"] == "mixed"
                    else 1
                    if item["bucket"] == "positive"
                    else 2,
                    -int(item["weighted_score"]),
                    self._issue_strength_for_role(str(item["role"])),
                    int(getattr(item["category"], "sort_order", 0) or 0),
                    int(getattr(item["category"], "id", 0) or 0),
                    str(item["code"]),
                )
            )
            secondary = secondary_candidates[0]
        tone_only: list[str] = []
        suppressed: list[str] = []
        for item in ordered_candidates:
            code = str(item["code"])
            if code == primary["code"]:
                continue
            if secondary is not None and code == secondary["code"]:
                continue
            role = str(item["role"])
            bucket = str(item["bucket"])
            if role == "price_complaint":
                (tone_only if has_concrete_price_pressure else suppressed).append(code)
                continue
            if self._is_meta_role(role):
                if role == "mixed" and has_concrete_category:
                    suppressed.append(code)
                elif role == "emotional_negative":
                    tone_only.append(code)
                else:
                    suppressed.append(code)
                continue
            if bucket in {"negative", "mixed"}:
                suppressed.append(code)
                continue
            if bucket == "positive":
                tone_only.append(code)
                continue
            suppressed.append(code)
        lines = [
            "Matched review categories and routing instructions:",
            "Generate one focused reply. Do not turn every category into an equal talking point. Address one primary issue fully and only optionally add one short secondary acknowledgment.",
        ]
        lines.append(
            f"- Primary issue: {primary['category'].label} ({primary['code']}, bucket={self._bucket_to_label(str(primary['bucket']))})"
        )
        if secondary:
            lines.append(
                f"- Optional secondary acknowledgment: {secondary['category'].label} ({secondary['code']}, bucket={self._bucket_to_label(str(secondary['bucket']))})"
            )
        if tone_only:
            lines.append(
                "- Tone-only/context categories: " + ", ".join(sorted(set(tone_only)))
            )
        if suppressed:
            lines.append(
                "- Standalone suppressed categories: "
                + ", ".join(sorted(set(suppressed)))
            )
        has_positive_signal = primary["bucket"] == "mixed" or any(
            item["code"] != primary["code"]
            and item["bucket"] in {"positive", "mixed"}
            and not self._is_meta_role(str(item["role"]))
            for item in ordered_candidates
        )
        if no_clear_primary:
            lines.extend(
                [
                    "",
                    "Reply strategy for this review:",
                    "- No single issue clearly dominates the review.",
                    "- Keep the reply balanced and concise.",
                    "- Do not over-focus on one detail unless it is clearly the main problem.",
                    "- Acknowledge the overall dissatisfaction calmly.",
                    "- Avoid sounding cheerful, promotional, or overly grateful when the review is mixed or disappointed.",
                ]
            )
        elif primary["role"] == "price_complaint":
            lines.extend(
                [
                    "",
                    "Reply strategy for this review:",
                    "- Keep the reply neutral and balanced.",
                    "- Briefly acknowledge the expectation or value gap.",
                    "- Do not argue about price or sound defensive.",
                    "- Avoid sounding cheerful, promotional, or overly grateful when the review is disappointed.",
                ]
            )
        elif self._is_problem_first_role(str(primary["role"])) and primary[
            "bucket"
        ] in {"negative", "mixed"}:
            lines.extend(["", "Reply strategy for this review:"])
            if has_positive_signal:
                lines.append(
                    "- The review contains both praise and a concrete problem."
                )
                lines.append(
                    "- Mention the positive point briefly in one short clause only."
                )
                lines.append("- Spend most of the reply on the concrete problem.")
            else:
                lines.append("- This review is problem-first.")
                lines.append("- Focus the reply mainly on the concrete problem.")
            lines.append("- Do not sound cheerful, promotional, or overly grateful.")
            lines.append(
                "- Use one short empathetic apology if needed, then move to the substance."
            )
        lines.append("")
        lines.append("Primary issue instructions:")
        lines.append(
            self._format_category_instruction(
                primary["category"], str(primary["bucket"])
            )
        )
        if secondary:
            lines.append("")
            lines.append("Optional secondary acknowledgment instructions:")
            lines.append(
                self._format_category_instruction(
                    secondary["category"], str(secondary["bucket"])
                )
            )
        if tone_only:
            lines.append("")
            lines.append("Tone-only/context instructions:")
            for code in sorted(set(tone_only)):
                category = category_map.get(code)
                if not category:
                    continue
                code_matches = [
                    match
                    for match in matches
                    if str(match.get("code") or "").strip().lower() == code
                ]
                lines.append(
                    self._format_tone_only_instruction(
                        category,
                        self._category_bucket_from_matches(
                            code_matches, classification
                        ),
                    )
                )
            lines.append(
                "Use only tone or style constraints from tone-only/context categories; do not create separate content sections for them."
            )
        if classification.get("requires_manual_attention"):
            lines.append(
                "Manual attention note: keep the answer cautious and do not promise refunds, compensation, legal actions, or direct contact outside marketplace rules."
            )
        return {
            "instructions": "\n".join(lines),
            "primary_review_category": primary["code"],
            "primary_review_bucket": primary["bucket"],
            "primary_review_role": primary["role"],
            "primary_review_weighted_score": primary["weighted_score"],
            "secondary_review_categories": [secondary["code"]] if secondary else [],
            "secondary_review_buckets": {secondary["code"]: secondary["bucket"]}
            if secondary
            else {},
            "tone_only_review_categories": sorted(set(tone_only)),
            "suppressed_review_categories": sorted(set(suppressed)),
            "routing_scores": {
                item["code"]: item["ai_score"] for item in ordered_candidates
            },
            "routing_weighted_scores": {
                item["code"]: item["weighted_score"] for item in ordered_candidates
            },
            "routing_margin": routing_margin,
            "no_clear_primary": no_clear_primary,
            "routing_primary_candidate": classification.get(
                "routing_primary_candidate"
            ),
            "routing_secondary_candidate": classification.get(
                "routing_secondary_candidate"
            ),
        }

    def _semantic_role(self, code: str, category: dict[str, Any] | None = None) -> str:
        role = str((category or {}).get("role") or "").strip()
        return role or self.ROUTING_ROLE_ALIASES.get(str(code or "").strip(), "general")

    def _empty_instruction_plan(
        self,
        *,
        routing_scores: dict[str, int] | None = None,
        routing_primary_candidate: Any = None,
        routing_secondary_candidate: Any = None,
    ) -> dict[str, Any]:
        return {
            "instructions": "",
            "primary_review_category": None,
            "primary_review_bucket": None,
            "primary_review_role": None,
            "primary_review_weighted_score": None,
            "secondary_review_categories": [],
            "secondary_review_buckets": {},
            "tone_only_review_categories": [],
            "suppressed_review_categories": [],
            "routing_scores": routing_scores or {},
            "routing_weighted_scores": {},
            "routing_margin": None,
            "no_clear_primary": False,
            "routing_primary_candidate": routing_primary_candidate,
            "routing_secondary_candidate": routing_secondary_candidate,
        }

    def _unique_category_codes(self, matches: Any) -> list[str]:
        seen: set[str] = set()
        codes: list[str] = []
        for match in matches or []:
            if not isinstance(match, dict):
                continue
            code = str(match.get("code") or "").strip().lower()
            if code and code not in seen:
                seen.add(code)
                codes.append(code)
        return codes

    def _category_bucket_from_matches(
        self, matches: list[dict[str, Any]], classification: dict[str, Any]
    ) -> str:
        sentiments = {
            str(match.get("sentiment") or "").strip().lower()
            for match in matches
            if str(match.get("sentiment") or "").strip().lower()
            in {"positive", "negative", "mixed", "neutral"}
        }
        if "negative" in sentiments and "positive" in sentiments:
            return "mixed"
        if "negative" in sentiments:
            return "negative"
        if "mixed" in sentiments:
            return "mixed"
        if "positive" in sentiments:
            return "positive"
        bucket = (
            str(
                classification.get("reply_bucket")
                or classification.get("sentiment")
                or "neutral"
            )
            .strip()
            .lower()
        )
        return (
            bucket
            if bucket in {"positive", "negative", "mixed", "neutral"}
            else "neutral"
        )

    def _collect_routing_scores(
        self, matches: list[dict[str, Any]], classification: dict[str, Any]
    ) -> dict[str, int]:
        scores: dict[str, int] = {}
        explicit = classification.get("routing_scores")
        if isinstance(explicit, dict):
            for code, value in explicit.items():
                normalized_code = str(code or "").strip().lower()
                normalized_score = normalize_need_reply_score(value, fallback=None)
                if normalized_code and normalized_score is not None:
                    scores[normalized_code] = normalized_score
        for match in matches:
            code = str(match.get("code") or "").strip()
            if not code:
                continue
            raw_score = match.get("routing_score")
            score = normalize_need_reply_score(raw_score)
            if score is not None and code not in scores:
                scores[code] = int(score)
        return scores

    def _default_routing_score_for_role(self, role: str, bucket: str) -> int:
        if role == "product_defect" and bucket == "negative":
            return 45
        if role == "delivery_packaging" and bucket == "negative":
            return 40
        if role == "fit_size" and bucket == "mixed":
            return 42
        if bucket == "negative":
            return 35
        if bucket == "mixed":
            return 38
        if bucket == "positive":
            return 20
        return 15

    def _weighted_routing_score(self, role: str, bucket: str, score: int) -> int:
        return (
            int(score)
            + int(self.ROUTING_ROLE_BONUS.get(role, 0))
            + int(self.ROUTING_BUCKET_BONUS.get(bucket, 0))
        )

    def _is_meta_role(self, role: str) -> bool:
        return role in {"mixed", "emotional_negative"}

    def _is_problem_first_role(self, role: str) -> bool:
        return role in {"product_defect", "fit_size"}

    def _issue_strength_for_role(self, role: str) -> int:
        return {
            "product_defect": 0,
            "delivery_packaging": 1,
            "fit_size": 2,
            "quality": 3,
            "price_complaint": 4,
            "expectation_mismatch": 5,
            "emotional_negative": 8,
            "mixed": 9,
        }.get(role, 6)

    def _bucket_to_label(self, bucket: str) -> str:
        if bucket in {"mixed", "negative"}:
            return bucket
        return "positive"

    def _format_category_instruction(
        self, category: ReputationReviewCategory, bucket: str
    ) -> str:
        if bucket == "mixed":
            positive_prompt = str(category.positive_prompt or "").strip()
            negative_prompt = str(category.negative_prompt or "").strip()
            instruction = (
                f"- {category.label} ({category.code}): This category has mixed positive and negative signals. "
                "Briefly acknowledge the positive part, then focus mainly on resolving the negative issue. "
                "Do not contradict yourself. "
            )
            if positive_prompt:
                instruction += f"Positive signal: {positive_prompt}. "
            if negative_prompt:
                instruction += f"Negative resolution should be: {negative_prompt}. "
            return (
                instruction
                + "The negative point must drive the tone and final answer priority."
            )
        return f"- {category.label} ({category.code}, sentiment={bucket}): {category.prompt_for_sentiment(bucket)}"

    def _format_tone_only_instruction(
        self, category: ReputationReviewCategory, bucket: str
    ) -> str:
        code = str(category.code or "").strip().lower()
        role = self._semantic_role(code)
        if role == "emotional_negative":
            return "- emotional_negative: The customer sounds upset. Use extra empathy, calm wording, and no defensiveness. Keep apology brief and move to the main issue."
        if role == "price_complaint":
            return "- price_complaint: Briefly acknowledge the expectation/value gap. Do not argue about price. Do not make price the main topic when there is a concrete product issue."
        guidance = category.prompt_for_sentiment(
            "negative" if bucket in {"negative", "mixed"} else "positive"
        )
        return f"- {category.label} ({code}, apply_as=tone_only): Apply only as tone/context, not as a standalone topic. {guidance}"

    def _classification_failed(self, classification: dict[str, Any]) -> bool:
        if not isinstance(classification, dict):
            return True
        return bool(
            classification.get("failed")
            or classification.get("classification_failed")
            or classification.get("error")
        )

    def _blocked_generation_meta(
        self, status: str, *, classification: dict[str, Any], message: str
    ) -> dict[str, Any]:
        return {
            "source": status,
            "status": status,
            "blocked": True,
            "message": message,
            "classification": classification,
            "debug_trace": {
                "classification_context": classification,
                "blocked_reason": status,
            },
        }

    async def _prompt_context(
        self,
        session: AsyncSession,
        *,
        item: ReputationItem,
        settings: ReputationSettings,
        classification: dict[str, Any],
    ) -> dict[str, Any]:
        if item.item_type == "question":
            prompt_key, default_prompt = (
                "question_instructions_template",
                self.DEFAULT_QUESTION_PROMPT,
            )
        elif item.item_type == "chat":
            prompt_key, default_prompt = (
                "chat_instructions_template",
                self.DEFAULT_CHAT_PROMPT,
            )
        else:
            prompt_key, default_prompt = (
                "review_instructions_template",
                self.DEFAULT_REVIEW_PROMPT,
            )
        base_template = await self._prompt_text(
            session, prompt_key, default_prompt, account_id=item.account_id
        )
        categories = await self._effective_categories(
            session, account_id=item.account_id
        )
        matched_codes = {
            str(category.get("code"))
            for category in (classification.get("categories") or [])
            if isinstance(category, dict) and str(category.get("code") or "").strip()
        }
        sentiment = str(
            classification.get("sentiment") or classification.get("reply_bucket") or ""
        )
        instruction_plan = (
            self._category_instruction_plan(categories, classification)
            if item.item_type == "review"
            else {}
        )
        category_rules = (
            [instruction_plan["instructions"]]
            if instruction_plan.get("instructions")
            else []
        )
        learning_enabled = self._learning_enabled(settings)
        entries = (
            await self._learning_entries(session, account_id=item.account_id)
            if learning_enabled
            else []
        )
        rules: list[str] = []
        for entry in entries:
            if entry.target_type == "stop_word":
                continue
            if (
                entry.nm_id is not None
                and item.nm_id is not None
                and int(entry.nm_id) != int(item.nm_id)
            ):
                continue
            if entry.nm_id is not None and item.nm_id is None:
                continue
            if entry.category_code and entry.category_code not in matched_codes:
                continue
            if entry.sentiment_scope and str(entry.sentiment_scope).lower() not in {
                sentiment.lower(),
                str(classification.get("reply_bucket") or "").lower(),
            }:
                continue
            rule_text = self._learning_rule_text(entry)
            if rule_text:
                rules.append(rule_text)
        stop_words = await self._effective_stop_words(
            session, account_id=item.account_id, settings=settings
        )
        format_values = self._prompt_format_values(
            settings,
            item,
            classification=classification,
            stop_words=stop_words,
        )
        format_values["category_instructions"] = (
            instruction_plan.get("instructions") or ""
        )
        base_prompt = self._render_prompt_template(base_template, format_values)
        return {
            "base_prompt": base_prompt,
            "category_rules": category_rules,
            "rules": rules,
            "stop_words": stop_words,
            "learning_enabled": learning_enabled,
            "instruction_plan": instruction_plan,
            "format_values": format_values,
        }

    def _customer_want_keywords(self, row: ReputationItem) -> list[str]:
        text = self._classification_text(
            text=row.text or "", payload=row.raw_json or {}
        ).lower()
        wants: list[str] = []
        trigger = any(
            token in text
            for token in (
                "хочу",
                "хотел",
                "нужно",
                "не хватает",
                "добавьте",
                "сделайте",
                "ожидал",
                "жаль",
            )
        )
        if not trigger:
            return wants
        keyword_map = (
            ("размеры", ("размер", "маломер", "большемер", "посадк")),
            ("качество", ("качест", "материал", "ткан", "шов", "нитк")),
            ("упаковка", ("упаков", "короб", "пакет")),
            ("цвет и фото", ("цвет", "фото", "картин", "изображ")),
            ("цена", ("цен", "дорог", "стоим")),
            ("доставка", ("достав", "срок")),
            ("комплектация", ("комплект", "детал", "част")),
        )
        for label, keywords in keyword_map:
            if any(keyword in text for keyword in keywords):
                wants.append(label)
        return wants or ["уточнить ожидания покупателя"]

    def _prompt_rules_for_categories(
        self, categories: list[ReputationReviewCategory], codes: Any
    ) -> list[dict[str, Any]]:
        selected = {str(code) for code in codes if str(code or "").strip()}
        rules: list[dict[str, Any]] = []
        for category in categories:
            if selected and category.code not in selected:
                continue
            rules.append(
                {
                    "code": category.code,
                    "label": category.label,
                    "positive_prompt": category.positive_prompt or "",
                    "negative_prompt": category.negative_prompt or "",
                    "scope": category.scope,
                }
            )
        return rules

    async def _reply_text(
        self,
        session: AsyncSession | ReputationItem,
        item: ReputationItem | ReputationSettings,
        settings: ReputationSettings | dict[str, Any],
        classification: dict[str, Any] | None = None,
        *,
        suffix: str | None = None,
        force_ai: bool = False,
    ) -> tuple[str, dict[str, Any]]:
        db_session: AsyncSession | None
        if classification is None:
            db_session = None
            actual_item = session
            actual_settings = item
            actual_classification = settings
        else:
            db_session = session if isinstance(session, AsyncSession) else None
            actual_item = item
            actual_settings = settings
            actual_classification = classification
        item = actual_item  # type: ignore[assignment]
        settings = actual_settings  # type: ignore[assignment]
        classification = (
            actual_classification if isinstance(actual_classification, dict) else {}
        )
        reply_mode = self._effective_reply_mode(
            settings, item.rating, item_type=getattr(item, "item_type", None)
        )
        prompt_context = (
            await self._prompt_context(
                db_session, item=item, settings=settings, classification=classification
            )
            if db_session is not None
            else {}
        )
        instructions, prompt = self._build_ai_prompt_parts(
            item, settings, classification, prompt_context=prompt_context
        )
        debug_trace = self._generation_debug_trace(
            item=item,
            settings=settings,
            classification=classification,
            prompt_context=prompt_context,
            instructions=instructions,
            input_text=prompt,
        )
        meta: dict[str, Any] = {
            "source": "local_rules",
            "reply_mode": reply_mode,
            "ai_attempted": False,
            "rating_mode_map": self._normalize_rating_mode_map(
                getattr(settings, "rating_mode_map_json", None)
            ),
            "learning_enabled": prompt_context.get("learning_enabled"),
            "prompt_rules_count": len(prompt_context.get("rules") or []),
            "category_rules_count": len(prompt_context.get("category_rules") or []),
            "category_instruction_plan": prompt_context.get("instruction_plan") or {},
            "debug_trace": debug_trace,
        }
        if self._classification_failed(classification):
            meta.update(
                {
                    "source": "classification_failed",
                    "status": "classification_failed",
                    "blocked": True,
                    "message": "Classification failed before draft generation.",
                }
            )
            meta["debug_trace"]["blocked_reason"] = "classification_failed"
            return "", meta
        if classification.get("requires_manual_attention") and not force_ai:
            meta.update(
                {
                    "source": "manual_attention",
                    "status": "manual_attention_required",
                    "blocked": True,
                    "message": "Manual attention blocks automatic draft generation.",
                }
            )
            meta["debug_trace"]["blocked_reason"] = "manual_attention_required"
            return "", meta
        ai_available = self._should_use_ai(settings)
        should_try_ai = ai_available and (reply_mode != "manual" or force_ai)
        if should_try_ai:
            meta["source"] = "ai"
            meta["ai_attempted"] = True
            meta["prompt_mode"] = (
                "operator_forced_ai"
                if reply_mode == "manual" and force_ai
                else "settings_ai"
            )
            if reply_mode == "manual" and force_ai:
                meta["manual_mode_overridden_by_operator"] = True
            if classification.get("requires_manual_attention") and force_ai:
                meta["manual_attention_overridden_by_operator"] = True
            try:
                ai_result = await self._generate_ai_reply_with_trace(
                    settings, prompt, instructions=instructions
                )
                text = ai_result["text"]
                text = self._sanitize_reply(
                    text,
                    settings,
                    forbidden_words=prompt_context.get("stop_words") or [],
                )
                meta["debug_trace"].update(ai_result["trace"])
                if text:
                    if suffix:
                        text = f"{text}\n\n{suffix}."
                    meta["ai_model"] = (
                        getattr(settings, "ai_model", None)
                        or self.settings.openai_model
                    )
                    return text.strip(), meta
                meta["status"] = "generation_failed"
                meta["blocked"] = True
                meta["message"] = "AI generation returned an empty reply."
                meta["debug_trace"]["blocked_reason"] = "empty_ai_reply"
                return "", meta
            except Exception as exc:
                meta["source"] = "ai"
                meta["status"] = "generation_failed"
                meta["blocked"] = True
                meta["ai_error"] = exc.__class__.__name__
                meta["message"] = "AI generation failed."
                meta["debug_trace"]["error"] = exc.__class__.__name__
                meta["debug_trace"]["blocked_reason"] = "ai_generation_failed"
                return "", meta
        if ai_available:
            meta.update(
                {
                    "source": "manual_mode",
                    "status": "generation_blocked_manual_mode",
                    "blocked": True,
                    "message": "Reply mode is manual; operator force is required for AI generation.",
                }
            )
            meta["debug_trace"]["blocked_reason"] = "manual_mode"
            return "", meta
        if reply_mode not in {"manual", "semi"}:
            meta.update(
                {
                    "source": "ai_provider_disabled",
                    "status": "generation_unavailable",
                    "blocked": True,
                    "message": "AI provider is disabled and auto reply mode does not allow local fallback drafts.",
                }
            )
            meta["debug_trace"]["blocked_reason"] = "ai_provider_disabled_auto_mode"
            return "", meta
        meta["fallback"] = True
        meta["fallback_reason"] = "ai_provider_disabled"
        meta["debug_trace"]["fallback_reason"] = "ai_provider_disabled"
        return self._default_reply(
            item, settings, suffix=suffix, classification=classification
        ), meta

    def _generation_debug_trace(
        self,
        *,
        item: ReputationItem,
        settings: ReputationSettings,
        classification: dict[str, Any],
        prompt_context: dict[str, Any],
        instructions: str,
        input_text: str,
    ) -> dict[str, Any]:
        instruction_plan = prompt_context.get("instruction_plan") or {}
        model = getattr(settings, "ai_model", None) or self.settings.openai_model
        provider = (
            str(getattr(settings, "ai_provider", None) or "openai").strip().lower()
        )
        return {
            "instructions": instructions,
            "input_text": input_text,
            "raw_messages": [
                {"role": "system", "content": instructions},
                {"role": "user", "content": input_text},
            ],
            "model": model,
            "provider": provider,
            "prompt_tokens": None,
            "completion_tokens": None,
            "latency_ms": None,
            "classification_context": classification,
            "category_instruction_plan": instruction_plan,
            "routing_scores": instruction_plan.get("routing_scores") or {},
            "routing_weighted_scores": instruction_plan.get("routing_weighted_scores")
            or {},
            "routing_primary_candidate": instruction_plan.get(
                "routing_primary_candidate"
            ),
            "routing_secondary_candidate": instruction_plan.get(
                "routing_secondary_candidate"
            ),
            "routing_candidates": [
                {"code": code, "score": score}
                for code, score in (
                    instruction_plan.get("routing_weighted_scores") or {}
                ).items()
            ],
            "settings_snapshot": {
                "reply_mode": getattr(settings, "reply_mode", None),
                "rating_mode_map": self._normalize_rating_mode_map(
                    getattr(settings, "rating_mode_map_json", None)
                ),
                "ai_enabled": bool(getattr(settings, "ai_enabled", False)),
                "ai_provider": provider,
                "ai_model": model,
            },
            "source": "finance_local_reputation",
        }

    def _effective_reply_mode(
        self,
        settings: ReputationSettings,
        rating: int | None,
        *,
        item_type: str | None = None,
    ) -> str:
        rating_map = self._normalize_rating_mode_map(
            getattr(settings, "rating_mode_map_json", None)
        )
        kind = str(item_type or "review").strip().lower()
        mode = (
            rating_map.get(str(rating))
            if kind == "review" and rating is not None
            else None
        )
        if mode is None and kind == "question":
            mode = (
                str(getattr(settings, "questions_reply_mode", None) or "")
                .strip()
                .lower()
                or None
            )
        mode = (
            mode or str(getattr(settings, "reply_mode", None) or "semi").strip().lower()
        )
        return mode if mode in self.ALLOWED_REPLY_MODES else "semi"

    def _should_use_ai(self, settings: ReputationSettings) -> bool:
        ai_enabled = bool(
            getattr(settings, "ai_enabled", False)
            or self.settings.reputation_ai_default_enabled
        )
        provider = (
            str(getattr(settings, "ai_provider", None) or "openai").strip().lower()
        )
        return (
            ai_enabled and provider == "openai" and bool(self.settings.openai_api_key)
        )

    def _normalize_rating_mode_map(self, value: Any) -> dict[str, str]:
        result = dict(self.DEFAULT_RATING_MODE_MAP)
        if isinstance(value, dict):
            for key, raw_mode in value.items():
                rating_key = str(key).strip()
                mode = str(raw_mode).strip().lower()
                if (
                    rating_key in {"1", "2", "3", "4", "5"}
                    and mode in self.ALLOWED_REPLY_MODES
                ):
                    result[rating_key] = mode
        return result

    def _normalize_string_list(self, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            parts = value.split(",")
        elif isinstance(value, list):
            parts = value
        else:
            return []
        return [str(item).strip() for item in parts if str(item).strip()]

    def _payload_text(self, payload: dict[str, Any], *keys: str) -> str | None:
        for key in keys:
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
            if value is not None and not isinstance(value, (dict, list)):
                text = str(value).strip()
                if text:
                    return text
        return None

    def _payload_bool(self, payload: dict[str, Any], *keys: str) -> bool | None:
        for key in keys:
            value = payload.get(key)
            if value is None:
                continue
            if isinstance(value, bool):
                return value
            if isinstance(value, str):
                return value.strip().lower() in {"1", "true", "yes", "y", "да"}
            return bool(value)
        return None

    def _product_details(
        self, payload: dict[str, Any], source_payload: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        source = source_payload if isinstance(source_payload, dict) else payload
        details = (
            source.get("productDetails")
            or source.get("product_details")
            or source.get("product")
        )
        result = dict(details) if isinstance(details, dict) else {}
        for source_key, target_key in (
            ("nmId", "nm_id"),
            ("nm_id", "nm_id"),
            ("imtId", "imt_id"),
            ("supplierArticle", "supplier_article"),
            ("supplier_article", "supplier_article"),
            ("productName", "product_name"),
            ("product_name", "product_name"),
            ("brandName", "brand_name"),
            ("brand_name", "brand_name"),
            ("subjectName", "subject_name"),
        ):
            value = source.get(source_key)
            if value is not None and target_key not in result:
                result[target_key] = value
        return result

    def _media(
        self, payload: dict[str, Any], source_payload: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        source = source_payload if isinstance(source_payload, dict) else payload
        media: list[dict[str, Any]] = []
        for key in ("photoLinks", "photo_links", "photos", "media"):
            value = source.get(key)
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, str) and item.strip():
                        media.append({"type": "image", "url": item.strip()})
                    elif isinstance(item, dict):
                        url = (
                            item.get("fullSize")
                            or item.get("miniSize")
                            or item.get("url")
                            or item.get("big")
                        )
                        next_item = dict(item)
                        if url and "url" not in next_item:
                            next_item["url"] = url
                        next_item.setdefault("type", "image")
                        media.append(next_item)
        video = source.get("video")
        if isinstance(video, dict):
            media.append({"type": "video", **video})
        elif isinstance(video, str) and video.strip():
            media.append({"type": "video", "url": video.strip()})
        return media

    def _bables(
        self, payload: dict[str, Any], source_payload: dict[str, Any] | None = None
    ) -> list[Any]:
        source = source_payload if isinstance(source_payload, dict) else payload
        value = source.get("bables") or source.get("badges") or source.get("tags")
        return value if isinstance(value, list) else []

    def _draft_summary(self, items: list[DraftOut]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for item in items:
            key = str(item.status or "unknown")
            counts[key] = counts.get(key, 0) + 1
        return counts

    def _analytics_window(
        self, *, date_from: date | None, date_to: date | None
    ) -> tuple[datetime, datetime]:
        today = utcnow().date()
        start_date = date_from or (today - timedelta(days=29))
        end_date = date_to or today
        return (
            datetime.combine(start_date, time.min, tzinfo=timezone.utc),
            datetime.combine(end_date, time.max, tzinfo=timezone.utc),
        )

    def _previous_window(
        self, start_dt: datetime, end_dt: datetime
    ) -> tuple[datetime, datetime]:
        span = end_dt - start_dt
        prev_end = start_dt - timedelta(microseconds=1)
        prev_start = prev_end - span
        return prev_start, prev_end

    async def _analytics_timeline(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        start_dt: datetime,
        end_dt: datetime,
        granularity: str,
    ) -> list[dict[str, Any]]:
        dialect_name = (
            getattr(session.bind.dialect, "name", "")
            if session.bind is not None
            else ""
        )
        date_expr = func.date(ReputationItem.received_at)
        if dialect_name == "postgresql" and granularity in {"week", "month"}:
            date_expr = func.date_trunc(granularity, ReputationItem.received_at)
        rows = (
            await session.execute(
                select(
                    date_expr.label("period"),
                    func.count().label("total"),
                    func.avg(ReputationItem.rating).label("avg_rating"),
                )
                .where(
                    ReputationItem.account_id == account_id,
                    ReputationItem.item_type == "review",
                    ReputationItem.received_at >= start_dt,
                    ReputationItem.received_at <= end_dt,
                )
                .group_by(date_expr)
                .order_by(date_expr.asc())
            )
        ).all()
        result: list[dict[str, Any]] = []
        for period, total, avg_rating in rows:
            if isinstance(period, datetime):
                period_key = period.date().isoformat()
            elif isinstance(period, date):
                period_key = period.isoformat()
            else:
                period_key = str(period)
            result.append(
                {
                    "period": period_key,
                    "total": int(total or 0),
                    "avg_rating": round(float(avg_rating), 2)
                    if avg_rating is not None
                    else None,
                }
            )
        return result

    def _public_analytics_status(self, settings: ReputationSettings) -> str:
        if not bool(getattr(settings, "analytics_enabled", False)):
            return "activation_required"
        status = str(getattr(settings, "analytics_status", None) or "")
        return status or (
            "ready" if bool(getattr(settings, "analytics_ready", False)) else "running"
        )

    def _merge_prompt_config(self, config: Any) -> dict[str, Any]:
        source = dict(config) if isinstance(config, dict) else {}
        merged: dict[str, Any] = dict(source)
        advanced_defaults = dict(self.DEFAULT_PROMPT_CONFIG["advanced"])
        advanced_defaults["tone_of_voice"] = dict(
            self.DEFAULT_PROMPT_CONFIG["advanced"]["tone_of_voice"]
        )
        merged["advanced"] = advanced_defaults
        for key in ("chat", "recommendations", "onboarding"):
            default_value = self.DEFAULT_PROMPT_CONFIG.get(key)
            if isinstance(default_value, dict) and not isinstance(
                merged.get(key), dict
            ):
                merged[key] = dict(default_value)
        if not isinstance(config, dict):
            return merged
        advanced = (
            source.get("advanced")
            if isinstance(source.get("advanced"), dict)
            else source
        )
        for key, value in advanced.items():
            if key == "tone_of_voice" and isinstance(value, dict):
                merged["advanced"]["tone_of_voice"].update(
                    {str(k): str(v) for k, v in value.items()}
                )
            elif key == "stop_words":
                merged["advanced"]["stop_words"] = self._normalize_string_list(value)
            elif key in {"chat", "recommendations", "onboarding"}:
                continue
            else:
                merged["advanced"][str(key)] = value
        return merged

    def _build_ai_prompt(
        self,
        item: ReputationItem,
        settings: ReputationSettings,
        classification: dict[str, Any],
        *,
        prompt_context: dict[str, Any] | None = None,
    ) -> str:
        instructions, input_text = self._build_ai_prompt_parts(
            item, settings, classification, prompt_context=prompt_context
        )
        return f"System instructions:\n{instructions}\n\nCustomer data:\n{input_text}".strip()

    def _build_ai_prompt_parts(
        self,
        item: ReputationItem,
        settings: ReputationSettings,
        classification: dict[str, Any],
        *,
        prompt_context: dict[str, Any] | None = None,
    ) -> tuple[str, str]:
        config = self._merge_prompt_config(getattr(settings, "config_json", None) or {})
        advanced = config["advanced"]
        prompt_context = prompt_context or {}
        buyer_name = item.buyer_name_masked if advanced.get("use_buyer_name") else None
        base_prompt = str(prompt_context.get("base_prompt") or "").strip()
        if not base_prompt:
            if item.item_type == "question":
                base_template = self.DEFAULT_QUESTION_PROMPT
            elif item.item_type == "chat":
                base_template = self.DEFAULT_CHAT_PROMPT
            else:
                base_template = self.DEFAULT_REVIEW_PROMPT
            prompt_stop_words = prompt_context.get("stop_words")
            stop_words = (
                prompt_stop_words
                if isinstance(prompt_stop_words, list)
                else self._normalize_string_list(
                    getattr(settings, "blacklist_keywords_json", None) or []
                )
            )
            base_prompt = self._render_prompt_template(
                base_template,
                self._prompt_format_values(
                    settings, item, classification=classification, stop_words=stop_words
                ),
            )
        instruction_lines = [base_prompt]
        for rule in (prompt_context.get("category_rules") or [])[:10]:
            if isinstance(rule, str) and rule.strip():
                instruction_lines.append(rule.strip())
        for rule in (prompt_context.get("rules") or [])[:20]:
            if isinstance(rule, str) and rule.strip():
                instruction_lines.append(rule.strip())

        product = self._product_details_for_prompt(item)
        bables_text = self._bables_text(
            getattr(item, "bables_json", None)
            or (getattr(item, "raw_json", None) or {}).get("bables")
        )
        pros_combined = (
            ", ".join(
                value
                for value in [getattr(item, "pros", None), bables_text]
                if isinstance(value, str) and value.strip()
            )
            or None
        )
        product_name = item.title if advanced.get("mention_product_name") else None
        brand = product.get("brand_name") or product.get("brandName")
        nm_id = (
            product.get("nm_id") or product.get("nmId") or getattr(item, "nm_id", None)
        )
        supplier_article = (
            product.get("supplier_article")
            or product.get("supplierArticle")
            or getattr(item, "sku_id", None)
        )
        instruction_plan = (
            prompt_context.get("instruction_plan")
            if isinstance(prompt_context.get("instruction_plan"), dict)
            else {}
        )
        reply_bucket = self._resolve_reply_bucket_from_plan(
            rating=item.rating,
            instruction_plan=instruction_plan,
            fallback=str(
                classification.get("reply_bucket")
                or classification.get("sentiment")
                or "neutral"
            ),
        )
        template = self._template_for(
            settings, {**classification, "reply_bucket": reply_bucket}
        )
        tone_by_bucket = (
            advanced.get("tone_of_voice")
            if isinstance(advanced.get("tone_of_voice"), dict)
            else {}
        )
        tone_note = (
            self._tone_instruction(tone_by_bucket.get(reply_bucket))
            if isinstance(tone_by_bucket, dict)
            else None
        )
        input_lines = [
            "Customer feedback data:",
            f"- Rating: {item.rating}",
            f"- Buyer name: {buyer_name}",
            f"- Text: {getattr(item, 'text', None)}",
            f"- Pros: {pros_combined}",
            f"- Cons: {getattr(item, 'cons', None)}",
            (
                f"- Product: {product_name} (brand={brand}, nmId={nm_id}, article={supplier_article})"
                if product_name
                else f"- Product: (brand={brand}, nmId={nm_id}, article={supplier_article})"
            ),
        ]
        if bool(advanced.get("photo_reaction_enabled")) and getattr(
            item, "media_json", None
        ):
            input_lines.append(
                "- Customer attached photos/video: yes. Please thank the customer for the media if appropriate."
            )
        if template:
            input_lines.append(
                f"Preferred reply template for this reply bucket ({reply_bucket}): {template}"
            )
        if instruction_plan:
            primary_role = str(
                instruction_plan.get("primary_review_role") or ""
            ).strip()
            if primary_role:
                input_lines.append(f"- Semantic primary role: {primary_role}")
            if instruction_plan.get("no_clear_primary"):
                input_lines.append(
                    "- Routing note: no single issue clearly dominates this review."
                )
            margin = instruction_plan.get("routing_margin")
            if margin is not None:
                input_lines.append(f"- Routing margin between top categories: {margin}")
        if advanced.get("delivery_method"):
            input_lines.append(
                f"- Delivery method selected in shop settings: {advanced.get('delivery_method')}"
            )
        if tone_note:
            input_lines.append(f"- Style requirement (tone of voice): {tone_note}")
        return "\n".join(instruction_lines), "\n".join(input_lines)

    def _product_details_for_prompt(self, item: ReputationItem) -> dict[str, Any]:
        details = getattr(item, "product_details_json", None)
        if isinstance(details, dict) and details:
            return details
        raw = getattr(item, "raw_json", None) or {}
        if not isinstance(raw, dict):
            return {}
        return self._product_details(raw, raw)

    def _bables_text(self, value: Any) -> str | None:
        if not isinstance(value, list):
            return None
        labels: list[str] = []
        for item in value:
            if isinstance(item, str) and item.strip():
                labels.append(item.strip())
            elif isinstance(item, dict):
                for key in ("name", "title", "text", "label", "value"):
                    text = item.get(key)
                    if isinstance(text, str) and text.strip():
                        labels.append(text.strip())
                        break
        return ", ".join(self._merge_unique(labels)) if labels else None

    async def _generate_ai_reply(
        self,
        settings: ReputationSettings,
        prompt: str,
        *,
        instructions: str | None = None,
    ) -> str:
        return (
            await self._generate_ai_reply_with_trace(
                settings, prompt, instructions=instructions
            )
        )["text"]

    async def _generate_ai_reply_with_trace(
        self,
        settings: ReputationSettings,
        prompt: str,
        *,
        instructions: str | None = None,
    ) -> dict[str, Any]:
        provider = (
            str(getattr(settings, "ai_provider", None) or "openai").strip().lower()
        )
        payload = {
            "model": getattr(settings, "ai_model", None) or self.settings.openai_model,
            "instructions": instructions
            or "Ты пишешь короткие и безопасные ответы продавца маркетплейса на русском языке.",
            "input": prompt,
        }
        if provider == "openai":
            payload["temperature"] = 0
        started = perf_counter()
        data = await self._request_openai_response(payload)
        latency_ms = int((perf_counter() - started) * 1000)
        usage = data.get("usage") if isinstance(data, dict) else {}
        if not isinstance(usage, dict):
            usage = {}
        return {
            "text": self._extract_openai_text(data),
            "trace": {
                "raw_messages": [
                    {"role": "system", "content": payload["instructions"]},
                    {"role": "user", "content": payload["input"]},
                ],
                "model": payload["model"],
                "provider": provider,
                "prompt_tokens": usage.get("input_tokens")
                or usage.get("prompt_tokens"),
                "completion_tokens": usage.get("output_tokens")
                or usage.get("completion_tokens"),
                "latency_ms": latency_ms,
            },
        }

    async def _request_openai_response(self, payload: dict[str, Any]) -> dict[str, Any]:
        headers = {
            "Authorization": f"Bearer {self.settings.openai_api_key}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(
            timeout=self.settings.openai_timeout_seconds
        ) as client:
            response = await client.post(
                self.OPENAI_RESPONSES_URL, headers=headers, json=payload
            )
            response.raise_for_status()
            return response.json() if response.text else {}

    def _extract_openai_text(self, payload: dict[str, Any]) -> str:
        direct = payload.get("output_text")
        if isinstance(direct, str) and direct.strip():
            return direct.strip()
        output = payload.get("output")
        if isinstance(output, list):
            parts: list[str] = []
            for item in output:
                if not isinstance(item, dict):
                    continue
                content = item.get("content")
                if not isinstance(content, list):
                    continue
                for block in content:
                    if isinstance(block, dict):
                        text = block.get("text")
                        if isinstance(text, str) and text.strip():
                            parts.append(text.strip())
            if parts:
                return "\n".join(parts).strip()
        return ""

    def _strip_reply_artifacts(self, text: str) -> str:
        cleaned = str(text or "").strip()
        cleaned = re.sub(r"https?://\S+", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", "", cleaned)
        cleaned = re.sub(r"\+?\d[\d\s\-()]{7,}\d", "", cleaned)
        cleaned = re.sub(
            r"^\s*(ответ|вариант ответа|черновик)\s*[:：-]\s*",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(
            r"[^.!?]*\b(номер\s+заказа|пришлите[^.!?]*(фото|видео|номер)|отправьте[^.!?]*(фото|видео|номер)|"
            r"свяжитесь|напишите\s+нам|личн(ые|ых)\s+сообщени[яй])\b[^.!?]*[.!?]?",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
        return " ".join(cleaned.split())

    def _sanitize_reply(
        self,
        text: str,
        settings: ReputationSettings,
        *,
        forbidden_words: list[str] | None = None,
    ) -> str:
        cleaned = self._strip_reply_artifacts(text)
        for forbidden in self._merge_unique(
            [
                *self._normalize_string_list(
                    getattr(settings, "blacklist_keywords_json", None) or []
                ),
                *self._normalize_string_list(forbidden_words or []),
            ]
        ):
            cleaned = re.sub(
                re.escape(forbidden), "", cleaned, flags=re.IGNORECASE
            ).strip()
        return cleaned

    def _default_reply(
        self,
        item: ReputationItem,
        settings: ReputationSettings,
        *,
        suffix: str | None = None,
        classification: dict[str, Any] | None = None,
    ) -> str:
        classification = classification or self._classify_item(item)
        if item.item_type == "question":
            body = "Здравствуйте! Спасибо за вопрос. Уточним информацию по товару и вернёмся с корректным ответом."
        elif item.item_type == "chat":
            body = "Здравствуйте! Спасибо за обращение. Мы внимательно посмотрим сообщение и поможем с решением."
        else:
            body = self._review_reply_text(item, settings, classification)
        signature = self._pick_signature(
            settings,
            kind=item.item_type,
            brand=self._product_details_for_prompt(item).get("brand_name")
            or self._product_details_for_prompt(item).get("brandName"),
            rating=item.rating,
        )
        signature = f"\n\n{signature}" if signature else ""
        tail = f"\n\n{suffix}." if suffix else ""
        return f"{body}{tail}{signature}".strip()

    def _classify_item(self, item: ReputationItem) -> dict[str, Any]:
        return self._classify_payload(
            item_type=item.item_type,
            rating=item.rating,
            text=item.text or "",
            payload=item.raw_json or {},
        )

    def _classify_payload(
        self, *, item_type: str, rating: int | None, text: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        source_text = self._classification_text(text=text, payload=payload)
        normalized = source_text.lower()
        matched: list[dict[str, Any]] = []
        for rule in self.REVIEW_CATEGORY_RULES:
            hits = self._keyword_hits(rule["keywords"], normalized)
            if hits:
                matched.append(
                    {
                        "code": rule["code"],
                        "label": rule["label"],
                        "role": rule["role"],
                        "sentiment": self._category_match_sentiment(
                            item_type=item_type,
                            rating=rating,
                            role=str(rule["role"]),
                            source_text=source_text,
                            hits=hits,
                        ),
                        "score": min(
                            100,
                            45
                            + 10 * len(hits)
                            + (10 if rating is not None and rating <= 2 else 0),
                        ),
                        "routing_score": min(
                            100,
                            45
                            + 10 * len(hits)
                            + (10 if rating is not None and rating <= 2 else 0),
                        ),
                        "matched_terms": hits[:6],
                    }
                )
                extra_sentiments = self._additional_category_sentiments(
                    item_type=item_type,
                    rating=rating,
                    role=str(rule["role"]),
                    source_text=source_text,
                    current_sentiment=str(matched[-1]["sentiment"]),
                )
                for sentiment in extra_sentiments:
                    matched.append(
                        {
                            **matched[-1],
                            "sentiment": sentiment,
                            "score": max(30, int(matched[-1].get("score") or 0) - 5),
                        }
                    )
        if item_type in {"question", "chat"}:
            primary = self._primary_category(matched, rating=rating)
            routing_scores = self._routing_scores_from_matches(matched)
            raw_score = 40 if self.MANUAL_ATTENTION_RE.search(source_text) else 70
            need_reply_score = self._normalize_classification_score(raw_score)
            requires_manual = requires_manual_review_attention(
                need_reply_score, self.settings
            )
            return {
                "source": "finance_local_legacy_reputation_rules",
                "item_type": item_type,
                "rating": rating,
                "sentiment": "neutral" if source_text.strip() else "unknown",
                "priority": "P1" if requires_manual else "P2",
                "need_reply_score": need_reply_score,
                "primary_category": primary,
                "categories": matched,
                "routing_scores": routing_scores,
                "routing_primary_candidate": str((primary or {}).get("code") or "")
                or None,
                "routing_secondary_candidate": self._secondary_routing_candidate(
                    matched, primary
                ),
                "requires_manual_attention": requires_manual,
                "reply_bucket": "manual_attention" if requires_manual else "neutral",
            }
        if not matched and item_type == "review":
            fallback = self._rating_sentiment(rating)
            matched.append(
                {
                    "code": "positive"
                    if fallback == "positive"
                    else "mixed"
                    if fallback == "neutral"
                    else "emotional_negative",
                    "label": "Оценка по рейтингу",
                    "role": "rating_bucket",
                    "sentiment": fallback,
                    "score": 30,
                    "matched_terms": [],
                }
            )
        primary = self._primary_category(matched, rating=rating)
        routing_scores = self._routing_scores_from_matches(matched)
        sentiment = self._derive_sentiment(
            rating=rating, text=source_text, matched=matched
        )
        raw_manual = item_type == "review" and bool(
            self.MANUAL_ATTENTION_RE.search(source_text)
        )
        raw_score = (
            40 if raw_manual else 85 if sentiment in {"negative", "mixed"} else 70
        )
        need_reply_score = self._normalize_classification_score(raw_score)
        requires_manual = requires_manual_review_attention(
            need_reply_score, self.settings
        )
        priority = self._classification_priority(
            item_type=item_type,
            rating=rating,
            sentiment=sentiment,
            primary=primary,
            requires_manual_attention=requires_manual,
        )
        return {
            "source": "finance_local_legacy_reputation_rules",
            "item_type": item_type,
            "rating": rating,
            "sentiment": sentiment,
            "priority": priority,
            "need_reply_score": need_reply_score,
            "primary_category": primary,
            "categories": matched,
            "routing_scores": routing_scores,
            "routing_primary_candidate": str((primary or {}).get("code") or "") or None,
            "routing_secondary_candidate": self._secondary_routing_candidate(
                matched, primary
            ),
            "requires_manual_attention": requires_manual,
            "reply_bucket": self._reply_bucket(
                rating=rating,
                sentiment=sentiment,
                primary=primary,
                requires_manual_attention=requires_manual,
            ),
        }

    def _classification_text(self, *, text: str, payload: dict[str, Any]) -> str:
        parts = [text, str(payload.get("pros") or ""), str(payload.get("cons") or "")]
        bables = payload.get("bables")
        if isinstance(bables, list):
            for item in bables:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict):
                    for key in ("name", "title", "text", "label", "value"):
                        value = item.get(key)
                        if isinstance(value, str) and value.strip():
                            parts.append(value)
                            break
        return " ".join(
            part.strip() for part in parts if isinstance(part, str) and part.strip()
        )

    def _keyword_hits(
        self, keywords: tuple[str, ...], normalized_text: str
    ) -> list[str]:
        hits: list[str] = []
        for keyword in keywords:
            kw = str(keyword or "").strip().lower()
            if not kw:
                continue
            if re.search(
                rf"(?<![0-9a-zа-яё]){re.escape(kw)}",
                normalized_text,
                flags=re.IGNORECASE,
            ):
                hits.append(kw)
        return hits

    def _normalize_classification_score(self, score: int | None) -> int | None:
        normalized = normalize_need_reply_score(score, fallback=None)
        if normalized is None:
            return None
        threshold = manual_attention_threshold(self.settings)
        if normalized < threshold:
            return min(normalized, max(threshold - 1, 0))
        return max(normalized, threshold)

    def _compatible_need_reply_score(
        self, score: int | None, requires_manual_attention: bool
    ) -> int | None:
        normalized = normalize_need_reply_score(score, fallback=None)
        threshold = manual_attention_threshold(self.settings)
        if requires_manual_attention:
            if normalized is None:
                return max(threshold - 1, 0)
            return min(normalized, max(threshold - 1, 0))
        if normalized is None:
            return None
        return max(normalized, threshold)

    def _additional_category_sentiments(
        self,
        *,
        item_type: str,
        rating: int | None,
        role: str,
        source_text: str,
        current_sentiment: str,
    ) -> list[str]:
        if item_type != "review":
            return []
        has_positive = bool(self.POSITIVE_RE.search(source_text))
        has_negative = self._has_negative_signal(source_text)
        result: list[str] = []
        if (
            current_sentiment == REVIEW_SENTIMENT_NEGATIVE
            and role == "fit_size"
            and has_positive
            and rating is not None
            and rating >= 4
        ):
            result.append(REVIEW_SENTIMENT_POSITIVE)
        return result

    def _has_negative_signal(self, text: str) -> bool:
        return bool(self.NEGATIVE_RE.search(text) or self.VALUE_GAP_RE.search(text))

    def _category_match_sentiment(
        self,
        *,
        item_type: str,
        rating: int | None,
        role: str,
        source_text: str,
        hits: list[str],
    ) -> str:
        if item_type in {"question", "chat"}:
            return "neutral"
        hit_set = {str(hit or "").strip().lower() for hit in hits}
        has_negative = self._has_negative_signal(source_text)
        has_positive = bool(self.POSITIVE_RE.search(source_text))
        rating_sentiment = self._rating_sentiment(rating)
        if role == "emotional_negative":
            return (
                "negative"
                if has_negative
                else "positive"
                if rating_sentiment == "positive" and has_positive
                else "neutral"
            )
        if role == "price_complaint":
            if has_negative or rating_sentiment in {"negative", "neutral"}:
                return "negative"
            return "positive" if rating_sentiment == "positive" else "neutral"

        role_negative = False
        if role == "product_defect":
            role_negative = True
        elif role == "delivery_packaging":
            role_negative = bool(hit_set.intersection({"помят", "мятая", "грязн"})) or (
                has_negative and bool(hit_set)
            )
        elif role == "fit_size":
            role_negative = bool(
                hit_set.intersection(
                    {
                        "маломер",
                        "большемер",
                        "мал",
                        "велик",
                        "не подош",
                        "тесн",
                        "широк",
                    }
                )
            )
            role_negative = role_negative or (
                rating is not None and rating <= 3 and has_negative
            )
        elif role == "material":
            role_negative = bool(hit_set.intersection({"тонк", "синтет"})) or (
                rating is not None and rating <= 3 and has_negative
            )
        elif role == "quality":
            role_negative = bool(
                hit_set.intersection({"шов", "нитк", "строч", "обработк", "пуговиц"})
            ) and (has_negative or rating_sentiment != "positive")
            role_negative = role_negative or (
                rating is not None and rating <= 2 and has_negative
            )
        elif role == "color_photo":
            role_negative = bool(hit_set.intersection({"не такой", "отличается"})) or (
                rating is not None and rating <= 3 and has_negative
            )
        elif role == "expectation_mismatch":
            role_negative = has_negative or rating_sentiment in {"negative", "neutral"}
        elif role == "composition_set":
            role_negative = bool(hit_set.intersection({"недоста"})) or (
                rating is not None and rating <= 3 and has_negative
            )
        elif role == "comfort":
            role_negative = bool(hit_set.intersection({"неудоб", "колет"})) or (
                rating is not None and rating <= 3 and has_negative
            )
        elif role == "wash_wear":
            role_negative = bool(
                hit_set.intersection({"катыш", "сел", "села", "линя", "выцвел"})
            ) or (rating is not None and rating <= 3 and has_negative)
        else:
            role_negative = has_negative and rating_sentiment != "positive"

        if role_negative:
            return "negative"
        if rating_sentiment == "positive":
            return "positive"
        if has_negative:
            return "negative"
        if has_positive:
            return "positive"
        if rating_sentiment in {"positive", "negative"}:
            return rating_sentiment
        return "neutral"

    def _rating_sentiment(self, rating: int | None) -> str:
        if rating is None:
            return "unknown"
        if rating <= 2:
            return "negative"
        if rating == 3:
            return "neutral"
        return "positive"

    def _derive_sentiment(
        self, *, rating: int | None, text: str, matched: list[dict[str, Any]]
    ) -> str:
        rating_sentiment = self._rating_sentiment(rating)
        has_negative = self._has_negative_signal(text) or any(
            item.get("sentiment") == "negative" for item in matched
        )
        has_positive = bool(self.POSITIVE_RE.search(text))
        if has_negative and has_positive:
            return "mixed"
        if has_negative:
            return "negative"
        if has_positive:
            return "positive"
        return rating_sentiment

    def _primary_category(
        self, matched: list[dict[str, Any]], *, rating: int | None
    ) -> dict[str, Any] | None:
        if not matched:
            return None
        role_bonus = {
            "product_defect": 20,
            "delivery_packaging": 15,
            "fit_size": 10,
            "comfort": 9,
            "quality": 8,
            "wash_wear": 8,
            "material": 7,
            "price_complaint": 5,
            "color_photo": 5,
            "expectation_mismatch": 4,
            "appearance_style": 4,
            "composition_set": 4,
            "emotional_negative": -15,
            "rating_bucket": -20,
        }
        return max(
            matched,
            key=lambda item: (
                int(item.get("score") or 0)
                + role_bonus.get(str(item.get("role") or ""), 0)
                + (5 if rating is not None and rating <= 2 else 0)
            ),
        )

    def _routing_scores_from_matches(
        self, matched: list[dict[str, Any]]
    ) -> dict[str, int]:
        scores: dict[str, int] = {}
        for item in matched:
            code = str(item.get("code") or "").strip().lower()
            score = normalize_need_reply_score(
                item.get("routing_score", item.get("score")), fallback=None
            )
            if code and score is not None and code not in scores:
                scores[code] = int(score)
        return scores

    def _secondary_routing_candidate(
        self, matched: list[dict[str, Any]], primary: dict[str, Any] | None
    ) -> str | None:
        primary_code = str((primary or {}).get("code") or "").strip().lower()
        candidates = [
            item
            for item in matched
            if str(item.get("code") or "").strip().lower()
            and str(item.get("code") or "").strip().lower() != primary_code
        ]
        if not candidates:
            return None
        secondary = self._primary_category(candidates, rating=None)
        code = str((secondary or {}).get("code") or "").strip().lower()
        return code or None

    def _classification_priority(
        self,
        *,
        item_type: str,
        rating: int | None,
        sentiment: str,
        primary: dict[str, Any] | None,
        requires_manual_attention: bool,
    ) -> str:
        if requires_manual_attention:
            return "P0"
        if item_type in {"question", "chat"}:
            return "P2"
        role = str((primary or {}).get("role") or "")
        if rating is not None and rating <= 2:
            return "P1"
        if sentiment in {"negative", "mixed"} or role in {
            "product_defect",
            "delivery_packaging",
            "fit_size",
        }:
            return "P2"
        return "P3"

    def _bucket_by_rating(self, rating: int | None) -> str:
        if rating is None:
            return "neutral"
        if rating <= 2:
            return "negative"
        if rating == 3:
            return "neutral"
        return "positive"

    def _resolve_reply_bucket_from_plan(
        self,
        *,
        rating: int | None,
        instruction_plan: dict[str, Any] | None,
        fallback: str | None = None,
    ) -> str:
        rating_bucket = self._bucket_by_rating(rating)
        if not instruction_plan:
            bucket = str(fallback or rating_bucket).strip().lower()
            return (
                bucket
                if bucket
                in {"positive", "neutral", "negative", "mixed", "manual_attention"}
                else rating_bucket
            )

        primary_code = (
            str(instruction_plan.get("primary_review_category") or "").strip().lower()
        )
        primary_bucket = (
            str(instruction_plan.get("primary_review_bucket") or "").strip().lower()
        )
        primary_role = (
            str(
                instruction_plan.get("primary_review_role")
                or self._semantic_role(primary_code)
            )
            .strip()
            .lower()
        )
        no_clear_primary = bool(instruction_plan.get("no_clear_primary"))
        tone_only_roles = {
            self._semantic_role(str(code or "").strip().lower())
            for code in (instruction_plan.get("tone_only_review_categories") or [])
            if str(code or "").strip()
        }

        if no_clear_primary:
            if primary_role in {
                "product_defect",
                "delivery_packaging",
            } and primary_bucket in {"negative", "mixed"}:
                return "negative"
            return "neutral"
        if primary_bucket in {"negative", "mixed"}:
            return "neutral" if primary_role == "price_complaint" else "negative"
        if rating_bucket == "positive" and tone_only_roles.intersection(
            {"emotional_negative", "price_complaint"}
        ):
            return "neutral"
        return rating_bucket

    def _reply_bucket(
        self,
        *,
        rating: int | None,
        sentiment: str,
        primary: dict[str, Any] | None,
        requires_manual_attention: bool,
    ) -> str:
        if requires_manual_attention:
            return "manual_attention"
        role = str((primary or {}).get("role") or "")
        if sentiment == "negative" or role in {"product_defect", "delivery_packaging"}:
            return "negative"
        if sentiment in {"mixed", "neutral"} or role == "price_complaint":
            return "neutral"
        if rating is not None and rating >= 4:
            return "positive"
        return "neutral"

    def _review_reply_text(
        self,
        item: ReputationItem,
        settings: ReputationSettings,
        classification: dict[str, Any],
    ) -> str:
        template = self._template_for(settings, classification)
        if template:
            return template
        bucket = str(classification.get("reply_bucket") or "neutral")
        primary = (
            classification.get("primary_category")
            if isinstance(classification.get("primary_category"), dict)
            else {}
        )
        role = str(primary.get("role") or "")
        if bucket == "manual_attention":
            return "Здравствуйте! Спасибо за обратную связь. Нам важно разобраться в ситуации, поэтому передадим отзыв на ручную проверку и внимательно сверим детали."
        if bucket == "positive":
            return "Здравствуйте! Спасибо за тёплый отзыв и высокую оценку. Очень рады, что товар вам понравился."
        if role == "product_defect":
            return "Здравствуйте! Спасибо за отзыв. Нам жаль, что товар пришёл с таким недостатком; обязательно учтём это в проверке качества."
        if role == "fit_size":
            return "Здравствуйте! Спасибо за обратную связь. Нам жаль, что размер или посадка не подошли; передадим замечание команде, чтобы точнее описывать товар."
        if role == "appearance_style":
            return "Здравствуйте! Спасибо за отзыв. Нам жаль, что фасон или внешний вид не совпали с ожиданиями; такая обратная связь помогает точнее передавать особенности модели."
        if role == "material":
            return "Здравствуйте! Спасибо за обратную связь. Учтём ваше замечание о ткани и материале при работе с описанием и качеством товара."
        if role == "color_photo":
            return "Здравствуйте! Спасибо за отзыв. Нам жаль, если оттенок или внешний вид отличались от ожиданий; ваше замечание важно для точной передачи товара в карточке."
        if role == "delivery_packaging":
            return "Здравствуйте! Спасибо, что сообщили. Нам жаль, что возникла проблема с доставкой или упаковкой; обязательно учтём это в дальнейшей работе."
        if role == "price_complaint":
            return "Здравствуйте! Спасибо за честную обратную связь. Понимаем ваше ожидание по соотношению цены и качества и учтём замечание."
        if role == "composition_set":
            return "Здравствуйте! Спасибо за обратную связь. Учтём замечание о комплектности или составе, такие детали важны для корректного описания товара."
        if role == "comfort":
            return "Здравствуйте! Спасибо за отзыв. Нам жаль, что товар оказался не таким удобным, как ожидалось; учтём ваше замечание."
        if role == "wash_wear":
            return "Здравствуйте! Спасибо, что поделились опытом после стирки или носки. Учтём замечание при проверке качества товара."
        if role == "expectation_mismatch":
            return "Здравствуйте! Спасибо за отзыв. Нам жаль, что товар не совпал с ожиданиями; проверим описание и визуальные материалы карточки."
        if bucket == "negative":
            return "Здравствуйте! Спасибо за обратную связь. Нам жаль, что покупка оставила такое впечатление; мы учтём замечание и проверим товар."
        return "Здравствуйте! Спасибо за обратную связь. Мы внимательно изучим ваш отзыв и учтём его в дальнейшей работе."

    def _template_for(
        self, settings: ReputationSettings, classification: dict[str, Any]
    ) -> str | None:
        bucket = str(classification.get("reply_bucket") or "")
        primary = (
            classification.get("primary_category")
            if isinstance(classification.get("primary_category"), dict)
            else {}
        )
        code = str(primary.get("code") or "")
        rating = str(classification.get("rating") or "")
        templates = getattr(settings, "templates_json", None) or {}
        if isinstance(templates, dict):
            for key in (code, bucket, rating):
                value = templates.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
            return None
        if not isinstance(templates, list):
            return None
        for template in templates:
            if not isinstance(template, dict):
                continue
            template_bucket = str(
                template.get("bucket")
                or template.get("sentiment")
                or template.get("type")
                or ""
            ).strip()
            template_code = str(
                template.get("category")
                or template.get("category_code")
                or template.get("code")
                or ""
            ).strip()
            template_rating = str(template.get("rating") or "").strip()
            if template_bucket and template_bucket != bucket:
                continue
            if template_code and template_code != code:
                continue
            if template_rating and template_rating != rating:
                continue
            text = str(
                template.get("text")
                or template.get("body")
                or template.get("template")
                or ""
            ).strip()
            if text:
                return text
        return None

    def _normalize_signature_items(self, signatures: Any) -> list[dict[str, Any]]:
        if not isinstance(signatures, list):
            return []

        normalized: list[dict[str, Any]] = []
        for item in signatures:
            if isinstance(item, str):
                text = item.strip()
                if text:
                    normalized.append(
                        {
                            "text": text[:300],
                            "type": "all",
                            "brand": "all",
                            "rating": None,
                            "is_active": True,
                        }
                    )
                continue

            if not isinstance(item, dict):
                continue

            text = str(
                item.get("text") or item.get("signature") or item.get("value") or ""
            ).strip()
            if not text:
                continue

            kind = str(item.get("type") or "all").strip().lower() or "all"
            if kind not in {"all", "review", "question", "chat"}:
                kind = "all"

            brand = str(item.get("brand") or "all").strip()[:128] or "all"
            rating = item.get("rating")
            if isinstance(rating, str):
                raw_rating = rating.strip().lower()
                if raw_rating in {"", "all", "none", "null"}:
                    rating = None
                elif raw_rating.isdigit():
                    rating = int(raw_rating)
            if not isinstance(rating, int) or rating < 1 or rating > 5:
                rating = None

            is_active = item.get("is_active")
            if not isinstance(is_active, bool):
                is_active = True

            payload = {
                "text": text[:300],
                "type": kind,
                "brand": brand,
                "rating": rating,
                "is_active": is_active,
            }
            created_at = item.get("created_at")
            if isinstance(created_at, str) and created_at.strip():
                payload["created_at"] = created_at.strip()
            normalized.append(payload)

        return normalized

    def _pick_signature(
        self,
        settings: ReputationSettings,
        *,
        kind: str | None = None,
        brand: str | None = None,
        rating: int | None = None,
    ) -> str | None:
        signatures = getattr(settings, "signatures_json", None) or []
        if not isinstance(signatures, list):
            signature = getattr(settings, "signature", None)
            return (
                str(signature).strip()
                if isinstance(signature, str) and signature.strip()
                else None
            )

        kind_l = (kind or "").strip().lower()
        brand_l = (brand or "").strip().lower() or None
        rating_i = rating if isinstance(rating, int) and 1 <= rating <= 5 else None

        candidates: list[tuple[int, str, int]] = []
        for item in signatures:
            if isinstance(item, str) and item.strip():
                candidates.append((0, item.strip(), len(candidates)))
                continue

            if not isinstance(item, dict):
                continue
            if item.get("is_active") is False:
                continue

            text = str(
                item.get("text") or item.get("signature") or item.get("value") or ""
            ).strip()
            if not text:
                continue

            sig_type = item.get("type")
            sig_type = sig_type.strip().lower() if isinstance(sig_type, str) else "all"
            if sig_type not in {"all", kind_l}:
                continue

            sig_brand = item.get("brand")
            sig_brand = (
                sig_brand.strip().lower()
                if isinstance(sig_brand, str) and sig_brand.strip()
                else "all"
            )
            if sig_brand != "all" and not brand_l:
                continue
            if sig_brand != "all" and sig_brand != brand_l:
                continue

            sig_rating = item.get("rating")
            if isinstance(sig_rating, str):
                sig_rating_text = sig_rating.strip().lower()
                if sig_rating_text in {"", "all", "none", "null"}:
                    sig_rating = None
                elif sig_rating_text.isdigit():
                    sig_rating = int(sig_rating_text)
                else:
                    sig_rating = None
            if sig_rating is not None and not (
                isinstance(sig_rating, int) and 1 <= sig_rating <= 5
            ):
                sig_rating = None

            if sig_rating is not None and rating_i is None:
                continue
            if sig_rating is not None and sig_rating != rating_i:
                continue

            score = 0
            if sig_brand != "all":
                score += 2
            if sig_rating is not None:
                score += 1
            candidates.append((score, text, len(candidates)))

        if not candidates:
            signature = getattr(settings, "signature", None)
            return (
                str(signature).strip()
                if isinstance(signature, str) and signature.strip()
                else None
            )

        best_score = max(score for score, _text, _index in candidates)
        best_texts = [item for item in candidates if item[0] == best_score]
        best_texts.sort(key=lambda item: item[2])
        return best_texts[0][1]

    def _summary(self, items: list[ReputationItemOut]) -> dict[str, int]:
        return {
            "unanswered_reviews_count": sum(
                1 for item in items if item.item_type == "review" and item.needs_reply
            ),
            "unanswered_questions_count": sum(
                1 for item in items if item.item_type == "question" and item.needs_reply
            ),
            "unread_chats_count": sum(
                1 for item in items if item.item_type == "chat" and item.needs_reply
            ),
            "negative_unanswered_count": sum(
                1
                for item in items
                if item.needs_reply
                and (
                    item.sentiment == "negative"
                    or (item.rating is not None and item.rating <= 3)
                )
            ),
        }

    def _counts(self, items: list[ReputationItemOut], field: str) -> dict[str, int]:
        counts: dict[str, int] = {}
        for item in items:
            value = getattr(item, field, None)
            key = value.value if hasattr(value, "value") else str(value or "unknown")
            counts[key] = counts.get(key, 0) + 1
        return counts

    def _action_from_item(self, item: ReputationItemOut) -> PortalActionRead:
        manual_attention = bool(
            item.review_requires_manual_attention
            or item.data.get("requires_manual_attention")
            or item.source_payload.get("requires_manual_attention")
        )
        score = normalize_need_reply_score(
            item.review_need_reply_score
            or item.data.get("need_reply_score")
            or item.source_payload.get("need_reply_score")
        )
        draft_id = str(item.draft.id) if item.draft is not None else None
        action_type = (
            "REPUTATION_MANUAL_ATTENTION" if manual_attention else "REPUTATION_REPLY"
        )
        priority = (
            "P0"
            if manual_attention
            else (
                item.priority.value
                if hasattr(item.priority, "value")
                else str(item.priority or "P2")
            )
        )
        if priority not in {"P0", "P1", "P2", "P3", "P4"}:
            priority = "P1" if item.rating is not None and item.rating <= 2 else "P2"
        status = self._action_center_status(item)
        classification = {
            "sentiment": item.sentiment,
            "primary_category": item.review_instruction_plan.primary_review_category
            if item.review_instruction_plan
            else None,
            "primary_bucket": item.review_instruction_plan.primary_review_bucket
            if item.review_instruction_plan
            else None,
            "categories": list(item.review_categories or []),
            "category_matches": list(item.review_category_matches or []),
            "instruction_plan": item.review_instruction_plan.model_dump(mode="json")
            if item.review_instruction_plan
            else None,
        }
        text_excerpt = self._action_excerpt(item)
        return PortalActionRead(
            id=f"reputation:{item.id}",
            source="reputation",
            source_module="reputation",
            source_id=item.id,
            account_id=item.account_id,
            nm_id=item.nm_id,
            sku_id=item.sku_id,
            action_type=action_type,
            title="Нужна ручная проверка отзыва"
            if manual_attention
            else "Ответить на отзыв или вопрос",
            priority=priority,
            severity="critical"
            if priority == "P0"
            else "high"
            if priority in {"P1", "P2"}
            else "medium",
            status=status,
            review_status=self._action_center_review_status(status),
            reason=self._action_reason(
                item, manual_attention=manual_attention, score=score
            ),
            next_step=(
                "Откройте Reputation, проверьте классификацию и решите вручную. Публикация в WB выполняется только из Reputation."
                if manual_attention
                else "Откройте Reputation, подготовьте или проверьте черновик. Публикация в WB требует отдельного подтверждения."
            ),
            confidence="medium" if manual_attention else "high",
            linked_entity={
                "item_id": item.id,
                "item_type": item.item_type,
                "external_id": item.external_id,
            },
            payload={
                "beta": True,
                "source_module": "reputation",
                "rating": item.rating,
                "text_excerpt": text_excerpt,
                "classification": classification,
                "need_reply_score": score,
                "manual_attention": manual_attention,
                "requires_manual_attention": manual_attention,
                "draft_id": draft_id,
                "draft_status": item.draft.status.value
                if item.draft and hasattr(item.draft.status, "value")
                else (str(item.draft.status) if item.draft else None),
                "item_status": item.status,
                "marketplace_change": False,
                "external_operation": False,
                "warnings": [
                    "Reputation is beta in Action Center.",
                    "Action Center status changes do not publish replies or send chats.",
                ],
            },
            raw={"item": item.model_dump(mode="json")},
            can_update=True,
            can_update_status=True,
            can_update_reason=None,
            guided_fix={
                "route_key": "reputation",
                "target_id": item.id,
                "label": "Открыть Reputation",
                "method": "open_reputation_item",
            },
        )

    def _action_center_status(self, item: ReputationItemOut) -> str:
        status = str(item.status or "new").strip().lower()
        draft_status = str(
            item.draft.status.value
            if item.draft and hasattr(item.draft.status, "value")
            else (item.draft.status if item.draft else "")
        ).lower()
        if status in {"answered", "published", "done", "closed"}:
            return "done"
        if status in {"ignored", "rejected", "no_reply_needed", "dismissed"}:
            return "ignored"
        if draft_status in {"done", "approved", "in_progress", "new"} or status in {
            "draft_ready",
            "in_progress",
            "processing",
        }:
            return "in_progress"
        if status in {"blocked", "manual_attention"}:
            return "blocked"
        return "new"

    def _action_center_review_status(self, status: str) -> str:
        if status == "done":
            return "closed"
        if status == "ignored":
            return "dismissed"
        if status == "in_progress":
            return "in_progress"
        if status == "blocked":
            return "review"
        return "new"

    def _action_reason(
        self, item: ReputationItemOut, *, manual_attention: bool, score: int | None
    ) -> str:
        parts: list[str] = []
        if item.rating is not None:
            parts.append(f"rating {item.rating}")
        if item.sentiment:
            parts.append(f"sentiment {item.sentiment}")
        if score is not None:
            parts.append(f"need_reply_score {score}")
        if manual_attention:
            parts.append("manual attention required")
        excerpt = self._action_excerpt(item)
        if excerpt:
            parts.append(excerpt)
        return " · ".join(parts) or "Reputation item requires operator review."

    def _action_excerpt(self, item: ReputationItemOut) -> str:
        text = " ".join(
            str(value or "").strip()
            for value in (item.title, item.text, item.pros, item.cons)
            if str(value or "").strip()
        )
        text = re.sub(r"\s+", " ", text).strip()
        if len(text) <= 240:
            return text
        return text[:237].rstrip() + "..."

    def _result(
        self,
        account_id: int,
        event_type: str,
        *,
        draft_id: str | None = None,
        success: bool,
        external_status: ExternalStatus | None = None,
        warnings: list[str] | None = None,
    ) -> Any:
        from app.schemas.operator import ResultEventOut

        return ResultEventOut(
            module=OperatorModule.REPUTATION,
            event_type=event_type,
            external_status=external_status,
            account_id=account_id,
            draft_id=draft_id,
            title=event_type.replace("_", " "),
            success=success,
            occurred_at=utcnow(),
            warnings=warnings or [],
            data={"external_submit_attempted": event_type == "publish_confirmed"},
        )

    async def _source_counts(
        self, session: AsyncSession, *, account_id: int
    ) -> dict[str, int]:
        rows = (
            await session.execute(
                select(ReputationItem.item_type, func.count())
                .where(ReputationItem.account_id == account_id)
                .group_by(ReputationItem.item_type)
            )
        ).all()
        return {str(source): int(count or 0) for source, count in rows}

    async def _upsert_integration(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        status: str,
        warnings: list[str],
    ) -> None:
        existing = (
            (
                await session.execute(
                    select(PortalIntegration).where(
                        PortalIntegration.account_id == account_id,
                        PortalIntegration.module == "reputation",
                    )
                )
            )
            .scalars()
            .first()
        )
        row = existing or PortalIntegration(account_id=account_id, module="reputation")
        row.enabled = True
        row.mode = "local"
        row.status = status
        row.metadata_json = {"warnings": warnings}
        row.last_sync_at = utcnow()
        if status in {"ok", "empty"}:
            row.last_success_at = utcnow()
            row.last_error_code = None
            row.last_error_message = None
        if existing is None:
            session.add(row)
