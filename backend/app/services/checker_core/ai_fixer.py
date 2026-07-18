from __future__ import annotations

import json
import re
from typing import Any

import httpx

from app.core.config import Settings, get_settings
from app.services.checker_core.text_policy import (
    build_ai_characteristics_payload,
    build_composition_guardrail,
    forbidden_description_words_text,
)
from app.services.checker_core.wb_logic_prompt import build_wb_logic_block
from app.services.checker_core.wb_validator import (
    is_fixed_file_only_characteristic,
    is_no_touch_characteristic,
)


def _extract_json(text: str) -> dict[str, Any]:
    raw = (text or "").strip()
    if not raw:
        return {}
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?", "", raw, flags=re.IGNORECASE).strip()
        raw = re.sub(r"```$", "", raw).strip()
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", raw)
        if not match:
            return {}
        try:
            parsed = json.loads(match.group(0))
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}


class CheckerAIFixer:
    """Original wb-optimizer compatible text fixer for checker issues.

    This intentionally keeps the same prompt contract as the old checker:
    recommended_value, requires_human_check, suggestion_kind, candidate_values,
    used_sources, evidence, photo_evidence, and fix_action.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    @property
    def is_enabled(self) -> bool:
        return bool(self.settings.checker_ai_enabled and self.settings.openai_api_key)

    async def _call_json(
        self,
        prompt: str,
        *,
        image_urls: list[str] | None = None,
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        messages: list[dict[str, Any]]
        clean_image_urls = [
            str(url).strip() for url in (image_urls or []) if str(url).strip()
        ]
        if clean_image_urls:
            content: list[dict[str, Any]] = [
                {"type": "image_url", "image_url": {"url": url, "detail": "high"}}
                for url in clean_image_urls[
                    : int(self.settings.checker_ai_context_photos_count or 2)
                ]
            ]
            content.append({"type": "text", "text": prompt})
            messages = [{"role": "user", "content": content}]
        else:
            messages = [{"role": "user", "content": prompt}]

        model = (
            self.settings.openai_vision_model
            if clean_image_urls
            else self.settings.openai_model
        )
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "response_format": {"type": "json_object"},
        }
        limit = int(max_tokens or self.settings.checker_ai_max_output_tokens or 4096)
        if str(model or "").lower().startswith("gpt-5"):
            payload["max_completion_tokens"] = limit
            payload["reasoning_effort"] = "minimal"
        else:
            payload["temperature"] = float(self.settings.checker_ai_temperature)
            payload["max_tokens"] = limit
        async with httpx.AsyncClient(
            timeout=float(self.settings.openai_timeout_seconds)
        ) as client:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.settings.openai_api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
        text = ((data.get("choices") or [{}])[0].get("message") or {}).get(
            "content"
        ) or ""
        return _extract_json(text)

    def _photo_urls(self, card: dict[str, Any]) -> list[str]:
        urls: list[str] = []
        for item in card.get("photos") or []:
            if isinstance(item, dict):
                url = (
                    item.get("canonical_url")
                    or item.get("big")
                    or item.get("c516x688")
                    or item.get("tm")
                    or item.get("url")
                )
            else:
                url = item
            text = str(url or "").strip()
            if text and text not in urls:
                urls.append(text)
        return urls

    def _issue_needs_visual_context(self, issue: dict[str, Any]) -> bool:
        text = " ".join(
            str(issue.get(key) or "")
            for key in ("name", "title", "description", "message", "error_type")
        ).lower()
        return any(
            marker in text
            for marker in (
                "фото",
                "визу",
                "цвет",
                "материал",
                "фактура",
                "комплектац",
                "застеж",
                "карман",
                "силуэт",
                "модель",
                "тип верха",
                "тип низа",
            )
        )

    async def audit_card(
        self, *, card: dict[str, Any], product_dna: str = ""
    ) -> list[dict[str, Any]]:
        if not self.is_enabled:
            return []

        subject_name = card.get("subjectName") or card.get("subject_name") or ""
        subject_id = card.get("subjectID") or card.get("subject_id") or ""
        compact: dict[str, Any] = {
            "subjectID": subject_id,
            "subjectName": subject_name,
            "brand": card.get("brand"),
            "title": card.get("title"),
            "description": card.get("description"),
        }
        chars_raw = card.get("characteristics") or []
        if isinstance(chars_raw, list):
            char_list = [
                {
                    "id": ch.get("id"),
                    "name": ch.get("name", ""),
                    "value": ch.get("value", ch.get("values")),
                }
                for ch in chars_raw
                if isinstance(ch, dict)
            ]
        elif isinstance(chars_raw, dict):
            char_list = [{"name": k, "value": v} for k, v in chars_raw.items()]
        else:
            char_list = []

        fixed_chars = {
            str(name).strip().lower()
            for name in (card.get("_fixed_file_chars") or [])
            if str(name).strip()
        }
        color_names = {"цвет", "color", "основной цвет", "цвет товара"}
        compact["characteristics"] = [
            ch
            for ch in char_list
            if str(ch.get("name") or "").strip().lower()
            not in fixed_chars | color_names
            and not is_no_touch_characteristic(ch.get("name"), card=card)
            and not is_fixed_file_only_characteristic(ch.get("name"))
        ]

        valid_char_names = card.get("_valid_char_names") or []
        valid_chars_section = ""
        if valid_char_names:
            valid_chars_section = f"""
ДОПУСТИМЫЕ ХАРАКТЕРИСТИКИ ДЛЯ КАТЕГОРИИ "{subject_name}":
{json.dumps(valid_char_names, ensure_ascii=False)}
Если в карточке есть характеристики НЕ из этого списка и они заполнены — это ошибка.
"""
        dna_block = ""
        if product_dna:
            dna_block = f"\nТЕХНИЧЕСКОЕ ОПИСАНИЕ ТОВАРА ПО ФОТО (источник истины о товаре):\n{product_dna[:2000]}\n"

        logic_block = build_wb_logic_block(include_output=False)
        prompt = f"""
РОЛЬ: Ты — старший модератор-аудитор маркетплейса Wildberries.

{logic_block}

ЗАДАЧА: Проанализируй фото, title/description и карточку товара. Найди РЕАЛЬНЫЕ ошибки и несоответствия.
Не выдумывай — если не уверен, ставь severity="warning".
Если на одном фото есть текст/плашки/обрезка или часть товара не видна — сверяй вывод по другим фото,
не делай вывод только по одному кадру.

КАТЕГОРИЯ ТОВАРА: "{subject_name}" (subjectID={subject_id})
{valid_chars_section}
{dna_block}
ЧТО ПРОВЕРЯТЬ:
1. ФОТО ↔ ХАРАКТЕРИСТИКИ — Цвет, тип, фасон, комплектность соответствуют?
2. TITLE / DESCRIPTION ↔ ФОТО / КАТЕГОРИЯ / ХАРАКТЕРИСТИКИ — название и описание соответствуют реальному товару?
3. ХАРАКТЕРИСТИКИ ↔ ФОТО — проверяй только визуальные противоречия по значениям.
   НЕ делай выводы про allowed_values/"списки допустимых" — это проверяет backend-валидатор.
4. ДАТЫ/СЕРТИФИКАТЫ — НЕ анализируй, НЕ предлагай исправления.
5. ЦВЕТ — НЕ анализируй характеристику «Цвет», она проверяется отдельно.

ВАЖНО:
• Title/description АНАЛИЗИРУЙ, но не переписывай прямо в аудите — только возвращай ошибки.
• НЕ анализируй vendorCode/артикул.
• Если проблема относится к title, используй name="title".
• Если проблема относится к description, используй name="description".
• Один issue = одно поле.
• Для текста допустимы только name="title" или name="description".
• Никогда не объединяй title и description в одном issue.
• Не возвращай name с "/", "|", "," или несколькими полями.

CARD JSON:
{json.dumps(compact, ensure_ascii=False)[:4000]}

ФОРМАТ ОТВЕТА — строго JSON, без markdown:
{{
  "errors": [
    {{
      "charcId": <int или null>,
      "name": "<название характеристики или поля>",
      "value": <текущее значение>,
      "message": "<краткое описание проблемы, 1-2 предложения>",
      "severity": "critical|error|warning",
      "category": "photo|text|identification|qualification|mixed",
      "fix_action": "replace|clear|swap|compound",
      "swap_to_name": "<если fix_action=swap>",
      "swap_to_value": "<если fix_action=swap>",
      "compound_fixes": [],
      "errors": [{{"type": "vision_mismatch|category_mismatch|text_mismatch|contradiction|other", "message": "<подробнее>"}}]
    }}
  ]
}}

Если ошибок нет — верни: {{"errors": []}}
""".strip()
        result = await self._call_json(
            prompt,
            image_urls=None if product_dna else self._photo_urls(card),
            max_tokens=int(self.settings.checker_ai_max_output_tokens or 4096),
        )
        errors = (
            result.get("errors") or result.get("items")
            if isinstance(result, dict)
            else []
        )
        return (
            [item for item in errors if isinstance(item, dict)]
            if isinstance(errors, list)
            else []
        )

    async def generate_fixes(
        self,
        *,
        card: dict[str, Any],
        issues: list[dict[str, Any]],
        product_dna: str = "",
    ) -> dict[str, dict[str, Any]]:
        if not self.is_enabled or not issues:
            return {}
        clean_issues = [
            issue
            for issue in issues
            if not is_no_touch_characteristic(
                issue.get("name") or issue.get("title"), card=card
            )
            and not is_fixed_file_only_characteristic(
                issue.get("name") or issue.get("title")
            )
        ]
        if not clean_issues:
            return {}
        prompt = self._build_prompt(
            card=card, issues=clean_issues, product_dna=product_dna
        )
        needs_vision = any(
            self._issue_needs_visual_context(issue) for issue in clean_issues
        )
        parsed = await self._call_json(
            prompt,
            image_urls=self._photo_urls(card) if needs_vision else None,
            max_tokens=int(self.settings.checker_ai_max_output_tokens or 4096),
        )
        fixes = parsed.get("fixes") if isinstance(parsed, dict) else {}
        return (
            {str(key): value for key, value in fixes.items() if isinstance(value, dict)}
            if isinstance(fixes, dict)
            else {}
        )

    async def refix_value(
        self,
        *,
        card: dict[str, Any],
        char_name: str,
        current_value: Any,
        failed_reason: str,
        allowed_values: list[Any],
        limits: dict[str, Any] | None = None,
        product_dna: str = "",
    ) -> dict[str, Any]:
        if not self.is_enabled:
            return {}
        if is_no_touch_characteristic(
            char_name, card=card
        ) or is_fixed_file_only_characteristic(char_name):
            return {}

        subject = card.get("subjectName") or card.get("subject_name") or ""
        limit_hint = ""
        if limits:
            mn, mx = limits.get("min"), limits.get("max")
            if mn is not None or mx is not None:
                limit_hint = (
                    f"\nЛимит: от {mn} до {mx} значений. Верни массив правильной длины."
                )
        color_hint = ""
        if "цвет" in (char_name or "").lower():
            color_hint = (
                "\nЭто цветовая характеристика: верни ОДИН parent color "
                "(не массив оттенков). Backend сам развернет его в близкие оттенки."
            )
        dna_block = (
            f"\nТЕХНИЧЕСКОЕ ОПИСАНИЕ ТОВАРА ПО ФОТО:\n{product_dna[:1500]}\n"
            if product_dna
            else ""
        )
        logic_block = build_wb_logic_block(include_output=False)

        prompt = f"""
ЗАДАЧА: Подобрать правильное значение для характеристики товара на Wildberries.

{logic_block}

Товар: "{card.get("title")}" (категория: {subject})
Характеристика: "{char_name}"
Текущее значение: {json.dumps(current_value, ensure_ascii=False)}
Предыдущая попытка не прошла проверку: {failed_reason}
{dna_block}
ДОПУСТИМЫЕ ЗНАЧЕНИЯ (выбирай ТОЛЬКО из этого списка!):
{json.dumps(allowed_values[:80], ensure_ascii=False)}
{limit_hint}
{color_hint}

ВАЖНО:
- Если ни одно значение нельзя подтвердить уверенно, верни `"recommended_value": null`.
- В этом случае добавь `"requires_human_check": true`, `"suggestion_kind": "candidate"` и 1-3 `"candidate_values"` из допустимого списка.
- Не выбирай случайный allowed value только чтобы ответ не был пустым.
- Для визуально рискованных полей при недостатке visual evidence возвращай requires_human_check вместо догадки.
- Добавь `"used_sources"` и `"evidence"` для объяснения выбора.
- В `"used_sources"` указывай ТОЛЬКО реально использованные входы.
- Не указывай "product_dna", если Product DNA не был передан в prompt.
- Не указывай "photos", если фото не были приложены в этом вызове.
- Если ориентируешься на фото/visual DNA, добавь `"photo_evidence"` с 1-3 наблюдениями.

Ответ строго JSON:
{{
  "recommended_value": "<string или array — ТОЧНО из списка, либо null>",
  "reason": "<почему именно это или почему нужен human check>",
  "confidence": <число 0..1>,
  "requires_human_check": <true|false>,
  "suggestion_kind": "exact_fix|candidate|draft_text|no_safe_fix",
  "candidate_values": ["<1-3 кандидата из списка>"],
  "used_sources": ["allowed_values|card_characteristics|product_dna|photos"],
  "evidence": {{"observed": ["<факт 1>"], "constraint": "<что ограничивает выбор>"}},
  "photo_evidence": [{{"photo_index": 1, "observation": "<что видно>"}}]
}}
""".strip()
        return await self._call_json(
            prompt, max_tokens=int(self.settings.checker_ai_max_output_tokens or 4096)
        )

    async def generate_title(
        self,
        *,
        card: dict[str, Any],
        product_dna: str = "",
        seo_keywords: list[str] | None = None,
        extra_instructions: str | None = None,
    ) -> dict[str, Any]:
        if not self.is_enabled:
            return {}

        subject = card.get("subjectName") or card.get("subject_name") or ""
        brand = card.get("brand") or ""
        current_title = str(card.get("title") or "").strip()
        char_hints: list[str] = []
        for ch in (card.get("characteristics") or [])[:20]:
            if not isinstance(ch, dict):
                continue
            name = ch.get("name", "")
            value = ch.get("value", ch.get("values"))
            if is_no_touch_characteristic(name, card=card):
                continue
            if name and value:
                char_hints.append(f"{name}: {value}")
        chars_text = "\n".join(char_hints) if char_hints else "нет данных"
        tech_desc = card.get("tech_description") or ""
        logic_block = build_wb_logic_block(include_output=False)
        dna_block = (
            f"\nВИЗУАЛЬНОЕ ОПИСАНИЕ ТОВАРА (из фото):\n{product_dna[:1500]}\n"
            if product_dna
            else ""
        )
        kw_block = (
            f'\nSEO-КЛЮЧЕВЫЕ СЛОВА КАТЕГОРИИ "{subject}" (используй хотя бы 1-2 естественно):\n{", ".join(seo_keywords[:15])}\n'
            if seo_keywords
            else ""
        )
        extra_block = (
            f"\nДОПОЛНИТЕЛЬНЫЕ ИНСТРУКЦИИ ПОЛЬЗОВАТЕЛЯ:\n{str(extra_instructions).strip()[:1200]}\n"
            if extra_instructions
            else ""
        )

        prompt = f"""
ЗАДАЧА: Создай название товара для Wildberries на основе характеристик карточки.

{logic_block}

Категория: "{subject}"
Бренд (НЕ включать в название!): "{brand}"
Текущее название: "{current_title}"

Характеристики товара:
{chars_text}

{"Техническое описание:" + chr(10) + tech_desc[:800] if tech_desc else ""}
{dna_block}{kw_block}{extra_block}
СТРОГИЕ ПРАВИЛА:
• Формула: [Категория] [ключевой признак] [конструктив] [назначение] [цвет при необходимости]
• Длина: 40–60 символов (идеально 40–50)
• ЗАПРЕЩЕНО включать бренд "{brand}"
• ЗАПРЕЩЕНО: пол, маркетинг (стильный, топ, хит, лучший, идеальный, премиум, красивый)
• ЗАПРЕЩЕНО: CAPS, спецсимволы, эмодзи, запятые, повтор слов
• ЗАПРЕЩЕНО: «для + существительное» без исключений.
• Если не удаётся уложиться в 40–60 символов без нарушения правил — верни `"requires_human_check": true` и `"suggestion_kind": "draft_text"`.
• Если текущее название уже валидно, переписывай минимально и сохраняй подтверждённые коммерческие признаки.
• Сохраняй признаки вроде: полоска, клетка, кант, мини, миди, макси, палаццо, оверсайз, если они подтверждены текущей карточкой.
• Не добавляй цвет/сезон/год, если это не ключевой подтверждённый признак.
• Если текущее название короткое, удлиняй его подтверждёнными конструктивными признаками, а НЕ новым цветом.
• Не удаляй слова вроде жакет, брюки, юбка, офисный, миди, палаццо, кант, если они подтверждены текущей карточкой.
• Не добавляй цвет, если в характеристиках нет ровно одного подтверждённого цвета или этот цвет не виден в текущем названии/фото.
• Если текущее название уже безопасно и валидно, предпочти минимальную правку вместо стилистического переписывания.
• Если не уверен в цвете/стиле/сезоне — не добавляй их и лучше верни `"requires_human_check": true`.
• В `"used_sources"` указывай ТОЛЬКО реально использованные входы.
• Не указывай "product_dna", если блок Product DNA в prompt отсутствует.
• Не указывай "photos", если фото не были приложены в этом вызове.
• Верни ОДИН лучший вариант

Ответ строго JSON:
{{
  "recommended_value": "<созданное название>",
  "reason": "<какие признаки использованы>",
  "reason_short": "<1 короткое предложение для UI>",
  "confidence": <число 0..1>,
  "requires_human_check": <true|false>,
  "suggestion_kind": "exact_fix|draft_text|candidate|no_safe_fix",
  "used_sources": ["card_characteristics|product_dna|photos|seo_keywords"],
  "preserved_tokens": ["<что сохранено из текущего названия>"],
  "dropped_tokens": ["<что убрано из текущего названия>"],
  "added_tokens": ["<что добавлено>"],
  "evidence": {{"observed": ["<факт 1>", "<факт 2>"], "constraint": "<что ограничивает выбор>"}},
  "photo_evidence": [{{"photo_index": 1, "observation": "<что видно>"}}]
}}
""".strip()
        return await self._call_json(
            prompt,
            image_urls=None if product_dna else self._photo_urls(card),
            max_tokens=int(self.settings.checker_ai_max_output_tokens or 4096),
        )

    async def generate_description(
        self,
        *,
        card: dict[str, Any],
        product_dna: str = "",
        seo_keywords: list[str] | None = None,
        extra_instructions: str | None = None,
    ) -> dict[str, Any]:
        if not self.is_enabled:
            return {}

        subject = card.get("subjectName") or card.get("subject_name") or ""
        title = card.get("title") or ""
        card_for_description = {
            **card,
            "characteristics": [
                item
                for item in (card.get("characteristics") or [])
                if not (
                    isinstance(item, dict)
                    and is_no_touch_characteristic(item.get("name"), card=card)
                )
            ],
        }
        char_hints = build_ai_characteristics_payload(card_for_description, limit=25)
        tech_desc = card.get("tech_description") or ""
        composition_guardrail = build_composition_guardrail(card)
        logic_block = build_wb_logic_block(include_output=False)
        forbidden_words = forbidden_description_words_text()
        dna_block = (
            f"\nВИЗУАЛЬНОЕ ОПИСАНИЕ ТОВАРА (из фото):\n{product_dna[:1500]}\n"
            if product_dna
            else ""
        )
        kw_block = (
            f'\nSEO-КЛЮЧЕВЫЕ СЛОВА КАТЕГОРИИ "{subject}" (обязательно включи минимум 2-3 из них естественно):\n{", ".join(seo_keywords[:20])}\n'
            if seo_keywords
            else ""
        )
        instructions_block = (
            f"\nДОПОЛНИТЕЛЬНЫЕ ИНСТРУКЦИИ ПОЛЬЗОВАТЕЛЯ:\n{extra_instructions[:1200]}\n"
            if extra_instructions
            else ""
        )

        prompt = f"""
ЗАДАЧА: Создай описание товара для Wildberries на основе характеристик карточки.

{logic_block}

Категория: "{subject}"
Название: "{title}"

Характеристики товара:
{json.dumps(char_hints, ensure_ascii=False)}

{"Техническое описание (источник истины):" + chr(10) + tech_desc[:1000] if tech_desc else ""}
{"Подтвержденный состав: " + composition_guardrail + chr(10) if composition_guardrail else ""}{dna_block}{kw_block}{instructions_block}
СТРОГИЕ ПРАВИЛА:
• Длина: 1000–1800 символов
• Формат: 3–6 абзацев, без списков, маркеров, нумерации
• Каждый абзац: 2–4 предложения
• Структура: вступление → конструкция/посадка → материал (если подтверждён) → назначение → особенности/уход
• Пиши ТОЛЬКО факты из характеристик — не придумывай
• Если есть подтвержденный состав, переписывай его дословно по компонентам и процентам
• ЗАПРЕЩЕНО складывать проценты, объединять материалы или заменять один материал другим
• Не добавляй материал, состав или проценты, если их нет в явных данных карточки
• Не используй слабый визуальный контекст как доказательство состава/материала
• Если фактов недостаточно для безопасного текста — верни `"requires_human_check": true` и `"suggestion_kind": "draft_text"`
• Пиши для покупателя, а не для внутреннего технического отчета
• Не перегружай текст служебными деталями
• Не включай рост модели, параметры модели, размер на модели, коллекцию, сезон/год, страну производства, если это не критично для выбора товара
• ЗАПРЕЩЕНО: маркетинг, эмоции, обещания эффекта, ссылки, телефоны, CAPS, эмодзи
• Строго не используй эти слова и их формы из валидатора: {forbidden_words}
• Верни готовый текст описания

Ответ строго JSON:
{{
  "recommended_value": "<готовое описание 1000–1800 символов>",
  "reason": "<структура и источники>",
  "reason_short": "<1 короткое предложение для UI>",
  "confidence": <число 0..1>,
  "requires_human_check": <true|false>,
  "suggestion_kind": "exact_fix|draft_text|candidate|no_safe_fix",
  "used_sources": ["card_characteristics|product_dna|photos|seo_keywords"],
  "evidence": {{"observed": ["<факт 1>", "<факт 2>"], "constraint": "<что ограничивает выбор>"}},
  "photo_evidence": [{{"photo_index": 1, "observation": "<что видно>"}}]
}}
""".strip()
        return await self._call_json(
            prompt,
            image_urls=None if product_dna else self._photo_urls(card),
            max_tokens=max(
                int(self.settings.checker_ai_max_output_tokens or 4096), 2048
            ),
        )

    async def refix_title(
        self, *, card: dict[str, Any], current_title: str, failed_reason: str
    ) -> dict[str, Any]:
        if not self.is_enabled:
            return {}
        subject = card.get("subjectName") or card.get("subject_name") or ""
        brand = card.get("brand") or ""
        char_hints: list[str] = []
        for ch in (card.get("characteristics") or [])[:15]:
            if not isinstance(ch, dict):
                continue
            name = ch.get("name", "")
            value = ch.get("value", ch.get("values"))
            if is_no_touch_characteristic(name, card=card):
                continue
            if name and value:
                char_hints.append(f"{name}: {value}")
        chars_text = "\n".join(char_hints) if char_hints else "нет данных"
        logic_block = build_wb_logic_block(include_output=False)
        prompt = f"""
ЗАДАЧА: Исправь название товара для Wildberries.

{logic_block}

Категория: "{subject}"
Бренд (НЕ включать!): "{brand}"
Текущее предложение: "{current_title}"
Причина отказа: {failed_reason}

Характеристики товара:
{chars_text}

СТРОГИЕ ПРАВИЛА:
• Длина: 40–60 символов
• ЗАПРЕЩЕНО: бренд, пол, маркетинг, CAPS, спецсимволы, эмодзи, запятые
• Структура: [Категория] [ключевой признак] [конструктив] [назначение] [цвет при необходимости]
• Верни ОДИН лучший вариант

Ответ строго JSON:
{{
  "recommended_value": "<исправленное название>",
  "reason": "<что исправлено>"
}}
""".strip()
        return await self._call_json(
            prompt, max_tokens=int(self.settings.checker_ai_max_output_tokens or 4096)
        )

    async def refix_description(
        self,
        *,
        card: dict[str, Any],
        current_description: str,
        failed_reason: str,
    ) -> dict[str, Any]:
        if not self.is_enabled:
            return {}
        subject = card.get("subjectName") or card.get("subject_name") or ""
        title = card.get("title") or ""
        char_hints: list[dict[str, Any]] = []
        chars_raw = card.get("characteristics") or []
        if isinstance(chars_raw, list):
            for ch in chars_raw[:20]:
                if not isinstance(ch, dict):
                    continue
                name = ch.get("name")
                value = ch.get("value", ch.get("values"))
                if is_no_touch_characteristic(name, card=card):
                    continue
                if name and value:
                    char_hints.append({"name": name, "value": value})
        elif isinstance(chars_raw, dict):
            for key, value in list(chars_raw.items())[:20]:
                if is_no_touch_characteristic(key, card=card):
                    continue
                if value:
                    char_hints.append({"name": key, "value": value})
        logic_block = build_wb_logic_block(include_output=False)
        forbidden_words = forbidden_description_words_text()
        prompt = f"""
ЗАДАЧА: Исправь описание товара для Wildberries.

{logic_block}

Категория: "{subject}"
Название: "{title}"
Текущее описание:
{current_description[:2800]}

Причина отказа валидатора: {failed_reason}

Характеристики товара:
{json.dumps(char_hints, ensure_ascii=False)}

СТРОГИЕ ПРАВИЛА:
• Длина: 1000-1800 символов
• Формат: 3-6 абзацев, без списков
• Каждый абзац: 2-4 предложения
• Пиши только факты, без маркетинга, CAPS, эмодзи
• Строго не используй эти слова и их формы из валидатора: {forbidden_words}
• Если причина отказа содержит запрещенные слова — полностью замени их нейтральными фактами, не повторяй их
• Пиши для покупателя; не добавляй рост модели, параметры модели, размер на модели, коллекцию, сезон/год, страну производства без явной необходимости
• Верни ОДИН готовый вариант описания

Ответ строго JSON:
{{
  "recommended_value": "<готовое описание 1000-1800>",
  "reason": "<что исправлено>"
}}
""".strip()
        return await self._call_json(
            prompt,
            max_tokens=max(
                int(self.settings.checker_ai_max_output_tokens or 4096), 2048
            ),
        )

    def _build_prompt(
        self,
        *,
        card: dict[str, Any],
        issues: list[dict[str, Any]],
        product_dna: str = "",
    ) -> str:
        compact_card: dict[str, Any] = {
            "subjectName": card.get("subjectName") or card.get("subject_name") or "",
            "brand": card.get("brand"),
            "characteristics": [
                {
                    "name": item.get("name"),
                    "value": item.get("value", item.get("values")),
                }
                for item in (card.get("characteristics") or [])[:30]
                if isinstance(item, dict)
                and not is_no_touch_characteristic(item.get("name"), card=card)
            ],
        }
        issues_data: list[dict[str, Any]] = []
        for index, issue in enumerate(issues):
            if is_no_touch_characteristic(
                issue.get("name") or issue.get("title"), card=card
            ):
                continue
            if is_fixed_file_only_characteristic(
                issue.get("name") or issue.get("title")
            ):
                continue
            issue_id = str(issue.get("id") if issue.get("id") is not None else index)
            entry = {
                "id": issue_id,
                "error_type": issue.get("error_type") or issue.get("code") or "",
                "name": issue.get("name") or issue.get("title") or "",
                "current_value": issue.get("current_value") or issue.get("value"),
                "description": issue.get("description") or issue.get("message") or "",
            }
            allowed_values = issue.get("allowed_values") or []
            if allowed_values:
                entry["allowed_values"] = allowed_values[:60]
            for error in issue.get("errors") or []:
                if isinstance(error, dict) and error.get("type") == "limit":
                    entry["min_limit"] = error.get("min")
                    entry["max_limit"] = error.get("max")
            issues_data.append(entry)

        dna_block = (
            f"\nТЕХНИЧЕСКОЕ ОПИСАНИЕ ТОВАРА ПО ФОТО:\n{product_dna[:2000]}\n"
            if product_dna
            else ""
        )
        logic_block = build_wb_logic_block(include_output=True)
        return f"""
РОЛЬ: Ты — SEO-эксперт и копирайтер Wildberries.

{logic_block}

ЗАДАЧА: Для каждой проблемы создай ГОТОВОЕ ИСПРАВЛЕНИЕ с конкретным значением.

КАРТОЧКА ТОВАРА:
{json.dumps(compact_card, ensure_ascii=False)[:3500]}
{dna_block}
СПИСОК ПРОБЛЕМ:
{json.dumps(issues_data, ensure_ascii=False)[:5000]}

ПРАВИЛА:
• Если есть allowed_values → выбирай СТРОГО из этого списка (точное совпадение).
• ⚠️ СВОБОДНЫЕ ПОЛЯ (FREE-FORM):
  - Если allowed_values НЕТ — это СВОБОДНОЕ ПОЛЕ, можно писать любой текст.
  - Примеры: "Комплектация" ("костюм-двойка, Жакет - 1шт, Брюки - 1шт").
  - Формат свободный (дефисы, цифры, скобки допустимы).
  - НЕ предлагай clear — просто скорректируй текст на основе фото.
• Если есть min_limit/max_limit:
  - стремись заполнить максимально полно, но только подтверждёнными значениями;
  - если уверенно подтверждены только 1-2 значения, верни только их;
  - никогда не добивай список до max_limit за счёт предположений.
• Для цветовых полей ("Цвет", "Основной цвет") → верни ОДИН parent color строкой, НЕ массив.
• Для title → 40-60 символов, без бренда, без пола, без маркетинга.
• Для description → 1000-1800 символов, 3-6 абзацев, без маркетинга.
• Если точного подтверждения нет — разрешено вернуть `"recommended_value": null`.
• В таком случае обязательно верни `"requires_human_check": true`, `"suggestion_kind": "candidate"` и 1-3 `"candidate_values"`.
• Не подставляй случайное allowed value только ради заполнения.
• recommended_value заполняй только когда это безопасный `suggestion_kind="exact_fix"` и значение подтверждено данными.
• Для визуально рискованных полей при слабом/неподтвержденном visual evidence лучше верни `"recommended_value": null`, `"requires_human_check": true` и `suggestion_kind="no_safe_fix"` или `"candidate"`.
• Добавь `"used_sources"` как список из: allowed_values, card_characteristics, product_dna, photos.
• В `"used_sources"` указывай ТОЛЬКО реально использованные входы.
• Не указывай "product_dna", если блок Product DNA в prompt отсутствует.
• Не указывай "photos", если фото не были приложены в этом вызове.
• Добавь `"evidence"` с краткими фактами, на которых основан выбор.
• Если использовались фото — добавь `"photo_evidence"` с 1-3 наблюдениями по кадрам.
• ЗАПРЕЩЕНО: советы, инструкции, пустые строки вместо значений.
• Используй Product DNA (техническое описание по фото) для выбора характеристик.

ФОРМАТ ОТВЕТА — строго JSON:
{{
  "fixes": {{
    "<id проблемы>": {{
      "recommended_value": "<string или array или null>",
      "reason": "<почему именно это значение>",
      "confidence": <число 0..1>,
      "requires_human_check": <true|false>,
      "suggestion_kind": "exact_fix|candidate|draft_text|no_safe_fix",
      "candidate_values": ["<1-3 возможных значения>"],
      "used_sources": ["allowed_values|card_characteristics|product_dna|photos"],
      "evidence": {{"observed": ["<факт 1>", "<факт 2>"], "constraint": "<что ограничивает выбор>"}},
      "photo_evidence": [{{"photo_index": 1, "observation": "<что видно>"}}],
      "fix_action": "replace|clear|swap",
      "swap_to_name": "<только если swap>",
      "swap_to_value": "<только если swap>"
    }}
  }}
}}
""".strip()
