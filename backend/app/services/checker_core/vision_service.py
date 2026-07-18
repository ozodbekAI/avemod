"""
VisionService — product photos -> structured Product DNA evidence.
"""

from __future__ import annotations

import base64
import json
import logging
import re
from typing import Any, List, Optional

import httpx

from app.core.config import get_settings

settings = get_settings()

logger = logging.getLogger(__name__)


def _is_gpt5_model(model: str) -> bool:
    return str(model or "").strip().lower().startswith("gpt-5")


def _apply_openai_generation_params(
    payload: dict[str, Any], *, model: str, max_tokens: int
) -> dict[str, Any]:
    if _is_gpt5_model(model):
        payload["max_completion_tokens"] = max_tokens
        payload["reasoning_effort"] = "minimal"
        return payload

    payload["max_tokens"] = max_tokens
    payload["temperature"] = 0.1
    return payload


PRODUCT_DNA_VERSION = "product_dna_v2"

_DNA_ITEM_ALIASES = {
    "blazer": "jacket",
    "cardigan": "top",
    "coat": "jacket",
    "hoodie": "sweatshirt",
    "jumper": "top",
    "trousers": "pants",
    "pant": "pants",
    "pullover": "top",
    "suit jacket": "jacket",
    "suit pants": "pants",
    "suit trousers": "pants",
    "suit set": "suit",
    "sweater": "top",
    "two-piece suit": "suit",
    "set": "set",
    "нижняя часть": "bottom",
    "верх": "top",
    "низ": "bottom",
    "брюки": "pants",
    "юбка": "skirt",
    "жакет": "jacket",
    "блейзер": "jacket",
    "костюм": "suit",
    "шорты": "shorts",
    "топ": "top",
    "свитшот": "sweatshirt",
    "свитер": "top",
    "джемпер": "top",
}

_DNA_ACCESSORY_TERMS = {
    "accessory",
    "accessories",
    "bag",
    "handbag",
    "purse",
    "belt",
    "necklace",
    "pendant",
    "pearl necklace",
    "jewelry",
    "jewellery",
    "earrings",
    "shirt",
    "bra",
    "scarf",
    "size chart",
    "measurements chart",
    "chart",
    "label",
    "tag",
    "манекен",
    "аксессуар",
    "ремень",
    "сумка",
    "ожерелье",
    "подвеска",
    "рубашка",
    "бюстгальтер",
    "бирка",
}

_DNA_HARD_LAYER_CONTAMINATION_TERMS = {
    "shirt",
    "bra",
    "рубашка",
    "бюстгальтер",
}

_DNA_DECOR_NOISE_TERMS = _DNA_ACCESSORY_TERMS | {
    "pockets",
    "pocket",
    "side pockets",
}

_DNA_TRIVIAL_SUMMARY_TOKENS = {
    "black",
    "white",
    "red",
    "green",
    "blue",
    "gray",
    "grey",
    "pink",
    "purple",
    "brown",
    "beige",
    "burgundy",
    "light blue",
}

_DNA_GARMENT_TERMS = {
    "jacket",
    "pants",
    "skirt",
    "shorts",
    "top",
    "bottom",
    "suit",
    "set",
    "dress",
    "vest",
    "blazer",
    "sweatshirt",
}

_DNA_SUBJECT_ITEM_HINTS = (
    (
        ("костюм", "suit"),
        {"jacket", "pants", "skirt", "shorts", "top", "bottom", "suit", "set", "vest"},
    ),
    (("жакет", "пиджак", "blazer", "jacket"), {"jacket", "top", "blazer"}),
    (("юбка", "skirt"), {"skirt", "bottom"}),
    (("брюки", "pants", "trousers"), {"pants", "bottom"}),
    (("шорты", "shorts"), {"shorts", "bottom"}),
    (("платье", "dress"), {"dress"}),
)

_PRODUCT_DNA_SYSTEM = """Ты — эксперт по визуальному анализу fashion-товаров для Wildberries.
Верни строго JSON без markdown и вводных фраз.
Не выдумывай скрытые детали. Если элемент не виден или спорен — укажи unknown/null и добавь причину в uncertain.
Разделяй наблюдаемую фактуру поверхности и предположение о материале.
Если уверенность по материалу ниже 0.8, material_guess должен быть null.
Не описывай аксессуары, фон, размерные таблицы, украшения и нижний слой как часть товара.
Если виден пиджак, а нижняя часть не подтверждается на фото, не выдумывай юбку/брюки/шорты.
Поле confidence заполняй честно: 0.0 только если по фото нельзя надежно определить сам товар."""

_PRODUCT_DNA_USER = """Проанализируй изображения товара.

Категория товара: %s

ЖЕСТКИЕ ПРАВИЛА:
- Не угадывай скрытые детали товара.
- Если низ или второй элемент комплекта виден не полностью — не называй его юбкой/шортами/брюками, верни "unknown".
- observed_texture и material_guess всегда разделяй.
- Если 2+ фото противоречат друг другу — запиши это в uncertain.
- Если первый кадр закрыт текстом/плашками/обрезан — используй остальные кадры как основной источник.
- Не включай в items/sumary/accessories ремни, сумки, украшения, рубашки под жакетом, бюстгальтеры, размерные таблицы.
- Если на фото виден только жакет или верх изделия — items должен отражать только видимую часть, а не предполагаемый комплект целиком.
- summary пиши только по консенсусу всех фото.

Ответ строго JSON:
{
  "version": "product_dna_v2",
  "confidence": 0.0,
  "is_set": false,
  "is_set_confidence": 0.0,
  "items": [{"type": "unknown", "confidence": 0.0, "visible": true}],
  "observed_texture": null,
  "material_guess": null,
  "color": [],
  "decor": [],
  "fit": [],
  "visible_fasteners": [],
  "visible_pockets": [],
  "uncertain": [],
  "per_photo_notes": [{"photo_index": 1, "visible_parts": [], "occlusion": [], "observation": ""}],
  "summary": ""
}"""


def _json_parse_result(text: str) -> tuple[dict[str, Any], str]:
    raw = str(text or "").strip()
    if not raw:
        return {}, "empty_content"
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE)
        raw = re.sub(r"\s*```$", "", raw)
    try:
        data = json.loads(raw)
        return (data, "") if isinstance(data, dict) else ({}, "not_json_object")
    except Exception as first_exc:
        match = re.search(r"\{.*\}", raw, flags=re.DOTALL)
        if not match:
            return {}, f"parse_failed:{first_exc.__class__.__name__}"
        try:
            data = json.loads(match.group(0))
            return (data, "") if isinstance(data, dict) else ({}, "not_json_object")
        except Exception as second_exc:
            return {}, f"parse_failed:{second_exc.__class__.__name__}"


def _json_from_text(text: str) -> dict[str, Any]:
    data, _ = _json_parse_result(text)
    return data


def _choice_message_text(choice: dict[str, Any]) -> str:
    message = choice.get("message") if isinstance(choice, dict) else {}
    content = (message or {}).get("content")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                text = item.get("text") or item.get("content")
                if isinstance(text, str):
                    parts.append(text)
            elif isinstance(item, str):
                parts.append(item)
        return "\n".join(part.strip() for part in parts if part.strip()).strip()
    return ""


def _as_list(value: Any, limit: int = 12) -> list[Any]:
    raw = value if isinstance(value, list) else ([] if value in (None, "") else [value])
    return [item for item in raw[:limit]]


def _norm_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def _dedupe_strings(values: list[Any], *, limit: int = 12) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in values[:limit]:
        text = re.sub(r"\s+", " ", str(raw or "").strip())
        norm = text.lower()
        if not text or norm in seen:
            continue
        seen.add(norm)
        out.append(text)
    return out


def _contains_noise_term(text: str, terms: set[str]) -> bool:
    norm = _norm_text(text)
    if not norm:
        return False
    return any(term in norm for term in terms)


def _normalize_item_type(raw: Any) -> str:
    text = _norm_text(raw)
    if not text:
        return "unknown"
    if _contains_noise_term(text, _DNA_ACCESSORY_TERMS):
        return "unknown"
    text = _DNA_ITEM_ALIASES.get(text, text)
    if text in {"", "unknown", "неизвестно", "не определено", "none", "null"}:
        return "unknown"
    return text


def _normalize_string_values(
    raw: Any, *, limit: int = 12, drop_noise: set[str] | None = None
) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in _as_list(raw, limit=limit):
        text = re.sub(r"\s+", " ", str(item or "").strip())
        norm = text.lower()
        if not text or norm in seen:
            continue
        if drop_noise and _contains_noise_term(norm, drop_noise):
            continue
        seen.add(norm)
        out.append(text)
    return out


def _normalize_per_photo_notes(raw: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for idx, note in enumerate(_as_list(raw, limit=5), start=1):
        if not isinstance(note, dict):
            continue
        visible_parts = _normalize_string_values(
            note.get("visible_parts"),
            limit=8,
            drop_noise=_DNA_ACCESSORY_TERMS,
        )
        observation = re.sub(r"\s+", " ", str(note.get("observation") or "").strip())
        if _contains_noise_term(
            observation, {"size chart", "measurements chart", "размерная таблица"}
        ):
            observation = ""
        occlusion = _normalize_string_values(note.get("occlusion"), limit=8)
        out.append(
            {
                "photo_index": int(note.get("photo_index") or idx),
                "visible_parts": visible_parts,
                "occlusion": occlusion,
                "observation": observation,
            }
        )
    return out


def _summary_looks_trivial(summary: str) -> bool:
    norm = _norm_text(summary)
    if not norm:
        return True
    if norm in _DNA_TRIVIAL_SUMMARY_TOKENS:
        return True
    words = [w for w in re.split(r"\W+", norm) if w]
    return len(words) <= 2


def _summary_looks_noisy(summary: str) -> bool:
    norm = _norm_text(summary)
    if not norm:
        return False
    if _summary_looks_trivial(norm):
        return True
    return _contains_noise_term(norm, _DNA_ACCESSORY_TERMS)


def _derive_product_dna_confidence(
    explicit_confidence: float,
    *,
    items: list[dict[str, Any]],
    observed_texture: Any,
    material_guess: Any,
    colors: list[str],
    decor: list[str],
    fit: list[str],
    notes: list[dict[str, Any]],
    uncertain: list[str],
) -> float:
    if explicit_confidence > 0:
        return explicit_confidence

    visible_items = [
        float(item.get("confidence") or 0)
        for item in items
        if str(item.get("type") or "").strip().lower() not in {"", "unknown"}
        and bool(item.get("visible", True))
    ]
    note_signal = any(
        note.get("visible_parts") or note.get("observation") for note in notes
    )
    strong_signal_count = sum(
        1
        for value in (observed_texture, material_guess, colors, decor, fit)
        if bool(value)
    )

    if visible_items:
        avg_item_conf = sum(max(0.35, min(v, 1.0)) for v in visible_items) / len(
            visible_items
        )
        derived = 0.2 + (avg_item_conf * 0.55) + min(0.14, strong_signal_count * 0.04)
        if note_signal:
            derived += 0.08
        if uncertain:
            derived -= min(0.18, len(uncertain) * 0.05)
        if any(
            str(item.get("type") or "").strip().lower() == "unknown" for item in items
        ):
            derived -= 0.05
        return max(0.0, min(0.92, derived))

    if note_signal and strong_signal_count >= 2:
        derived = 0.3 + min(0.18, strong_signal_count * 0.05)
        if uncertain:
            derived -= min(0.12, len(uncertain) * 0.04)
        return max(0.0, min(0.58, derived))

    return 0.0


def _build_fallback_summary(
    *,
    items: list[dict[str, Any]],
    observed_texture: Any,
    colors: list[str],
    decor: list[str],
    fit: list[str],
    uncertain: list[str],
) -> str:
    parts: list[str] = []
    item_names = [
        str(item.get("type") or "").strip()
        for item in items
        if str(item.get("type") or "").strip().lower() not in {"", "unknown"}
    ]
    if item_names:
        prefix = "Visible items" if len(item_names) > 1 else "Visible item"
        parts.append(f"{prefix}: {', '.join(item_names)}.")
    if observed_texture:
        parts.append(f"Observed texture: {str(observed_texture).strip()}.")
    if colors:
        parts.append(f"Visible colors: {', '.join(colors)}.")
    if decor:
        parts.append(f"Visible details: {', '.join(decor)}.")
    if fit:
        parts.append(f"Fit cues: {', '.join(fit)}.")
    if uncertain:
        parts.append(f"Uncertain: {', '.join(uncertain[:2])}.")
    return " ".join(parts).strip()


def has_meaningful_product_dna(dna: dict[str, Any] | None) -> bool:
    if not isinstance(dna, dict) or not dna:
        return False

    items = [
        item for item in _as_list(dna.get("items"), limit=8) if isinstance(item, dict)
    ]
    visible_items = [
        item
        for item in items
        if str(item.get("type") or "").strip().lower()
        not in {"", "unknown", "неизвестно"}
    ]
    if visible_items:
        return True

    strong_signal_count = sum(
        1
        for key in (
            "observed_texture",
            "material_guess",
            "decor",
            "fit",
            "visible_fasteners",
            "visible_pockets",
        )
        if bool(dna.get(key))
    )
    has_notes = any(
        isinstance(note, dict)
        and bool(note.get("visible_parts") or note.get("observation"))
        for note in _as_list(dna.get("per_photo_notes"), limit=5)
    )
    summary = str(dna.get("summary") or "").strip()
    if strong_signal_count >= 1 and (
        has_notes or (summary and not _summary_looks_trivial(summary))
    ):
        return True
    if has_notes and bool(dna.get("color")):
        return True

    try:
        return float(dna.get("confidence") or 0) >= 0.45
    except (TypeError, ValueError):
        return False


def _expected_subject_item_types(subject_name: Any) -> set[str]:
    normalized = _norm_text(subject_name)
    if not normalized:
        return set()
    for markers, allowed in _DNA_SUBJECT_ITEM_HINTS:
        if any(marker in normalized for marker in markers):
            return {
                normalized_type
                for normalized_type in (_normalize_item_type(item) for item in allowed)
                if normalized_type != "unknown"
            }
    return set()


def _collect_noise_hits(values: list[str]) -> list[str]:
    hits: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = _norm_text(value)
        if not normalized:
            continue
        for term in _DNA_ACCESSORY_TERMS:
            if term in normalized and term not in seen:
                seen.add(term)
                hits.append(term)
    return hits


def _contains_noise_hit(value: Any, term: str) -> bool:
    normalized = _norm_text(value)
    normalized_term = _norm_text(term)
    if not normalized or not normalized_term:
        return False
    if re.search(rf"(?<!\w){re.escape(normalized_term)}(?!\w)", normalized):
        return True
    return (
        normalized_term in {"рубашка", "бюстгальтер"} and normalized_term in normalized
    )


def _collect_hard_layer_noise_hits(values: list[str]) -> list[str]:
    hits: list[str] = []
    seen: set[str] = set()
    for value in values:
        for term in _DNA_HARD_LAYER_CONTAMINATION_TERMS:
            if term not in seen and _contains_noise_hit(value, term):
                seen.add(term)
                hits.append(term)
    return hits


def _subject_requires_set_confirmation(
    subject_name: str,
    visible_types: list[str],
    *,
    is_set: bool = False,
    is_set_confidence: float = 0.0,
) -> bool:
    normalized = _norm_text(subject_name)
    if not normalized:
        return False
    if not any(
        marker in normalized for marker in ("костюм", "suit", "set", "комплект")
    ):
        return False
    if is_set and float(is_set_confidence or 0.0) >= 0.60:
        return False
    distinct_visible_types = {
        item for item in visible_types if item not in {"set", "suit"}
    }
    has_explicit_set = any(item in {"set", "suit"} for item in visible_types)
    has_top = any(
        item in {"jacket", "top", "vest", "blazer"} for item in distinct_visible_types
    )
    has_bottom = any(
        item in {"pants", "skirt", "shorts", "bottom"}
        for item in distinct_visible_types
    )
    return not has_explicit_set and not (has_top and has_bottom)


def build_product_dna_audit(
    dna: dict[str, Any] | None,
    *,
    subject_name: str = "",
    photo_count: int = 0,
    min_confidence: float = 0.45,
) -> dict[str, Any]:
    if not has_meaningful_product_dna(dna):
        return {
            "trust_state": "empty",
            "status": "empty",
            "grounded": False,
            "confidence": 0.0,
            "reasons": ["not enough grounded visual evidence"],
            "photo_count": max(0, int(photo_count or 0)),
        }

    payload = dna if isinstance(dna, dict) else {}
    try:
        confidence = float(payload.get("confidence") or 0)
    except (TypeError, ValueError):
        confidence = 0.0

    items = [
        item
        for item in _as_list(payload.get("items"), limit=8)
        if isinstance(item, dict)
    ]
    visible_types = [
        _normalize_item_type(item.get("type") or "")
        for item in items
        if bool(item.get("visible", True))
        and _normalize_item_type(item.get("type") or "") not in {"", "unknown"}
    ]
    unknown_only = bool(items) and not visible_types

    notes = _normalize_per_photo_notes(payload.get("per_photo_notes"))
    noisy_text = []
    note_noise_text = []
    summary = str(payload.get("summary") or "").strip()
    if summary:
        noisy_text.append(summary)
    for note in notes:
        visible_part_texts = [
            str(part or "").strip() for part in (note.get("visible_parts") or [])
        ]
        noisy_text.extend(visible_part_texts)
        note_noise_text.extend(visible_part_texts)
        observation = str(note.get("observation") or "").strip()
        if observation:
            noisy_text.append(observation)
            note_noise_text.append(observation)

    contamination_hits = _collect_noise_hits(noisy_text)
    hard_layer_hits = _collect_hard_layer_noise_hits(noisy_text)
    note_contamination_hits = _collect_noise_hits(note_noise_text)
    expected_types = _expected_subject_item_types(
        subject_name or payload.get("subject_name") or ""
    )
    product_visible = bool(
        visible_types
        and (
            not expected_types
            or any(
                item in expected_types or item in _DNA_GARMENT_TERMS
                for item in visible_types
            )
        )
    )
    subject_mismatch = bool(
        expected_types
        and visible_types
        and not any(item in expected_types for item in visible_types)
    )
    payload_is_set = bool(payload.get("is_set"))
    try:
        payload_is_set_conf = float(payload.get("is_set_confidence") or 0.0)
    except (TypeError, ValueError):
        payload_is_set_conf = 0.0
    summary_only_soft_accessory = bool(
        product_visible
        and summary
        and contamination_hits
        and not note_contamination_hits
        and not hard_layer_hits
    )
    if (
        not subject_mismatch
        and _subject_requires_set_confirmation(
            subject_name or payload.get("subject_name") or "",
            visible_types,
            is_set=payload_is_set,
            is_set_confidence=payload_is_set_conf,
        )
        and not summary_only_soft_accessory
    ):
        subject_mismatch = True
    summary_without_garment = bool(
        summary
        and contamination_hits
        and not product_visible
        and not any(term in _norm_text(summary) for term in _DNA_GARMENT_TERMS)
    )

    reasons: list[str] = []
    trust_state = "grounded"
    if confidence < min_confidence:
        trust_state = "weak"
        reasons.append(f"confidence<{min_confidence:.2f}")
    if unknown_only:
        trust_state = "unknown_items"
        reasons.append("items: unknown")
    # Accessories are common on fashion photos. Treat soft accessory hits as
    # metadata when the product is visible, but keep lower-layer/model garments
    # (shirt/bra) as fatal contamination because they can poison Product DNA.
    fatal_contamination = bool(
        (contamination_hits and not product_visible) or hard_layer_hits
    )
    if fatal_contamination:
        trust_state = "contaminated"
        reasons.append(f"accessory contamination: {', '.join(contamination_hits[:3])}")
    if subject_mismatch:
        reasons.append("visible items do not match subject")
        if trust_state == "grounded":
            trust_state = "subject_mismatch"
    if summary_without_garment:
        reasons.append("summary built from accessory-only evidence")

    grounded = not reasons
    if grounded:
        trust_state = "grounded"

    return {
        "trust_state": trust_state,
        "status": trust_state,
        "grounded": grounded,
        "confidence": confidence,
        "reasons": reasons,
        "visible_types": visible_types,
        "expected_types": sorted(expected_types),
        "contamination_hits": contamination_hits[:5],
        "accessory_hits_ignored": contamination_hits[:5]
        if contamination_hits and product_visible
        else [],
        "photo_count": max(0, int(photo_count or 0)),
    }


def is_grounded_product_dna_audit(audit: dict[str, Any] | None) -> bool:
    return bool((audit or {}).get("grounded"))


def is_grounded_product_dna_payload(
    dna: dict[str, Any] | None,
    *,
    subject_name: str = "",
    photo_count: int = 0,
    min_confidence: float = 0.45,
) -> bool:
    return is_grounded_product_dna_audit(
        build_product_dna_audit(
            dna,
            subject_name=subject_name,
            photo_count=photo_count,
            min_confidence=min_confidence,
        )
    )


def product_dna_grounding_state(
    dna: dict[str, Any] | None,
    *,
    subject_name: str = "",
    min_confidence: float = 0.45,
) -> dict[str, Any]:
    return build_product_dna_audit(
        dna,
        subject_name=subject_name,
        min_confidence=min_confidence,
    )


def product_dna_is_grounded(
    dna: dict[str, Any] | None,
    *,
    subject_name: str = "",
    photo_count: int = 0,
    min_confidence: float = 0.45,
) -> bool:
    return is_grounded_product_dna_payload(
        dna,
        subject_name=subject_name,
        photo_count=photo_count,
        min_confidence=min_confidence,
    )


def _has_unknown_only_trivial_signal(
    *,
    items: list[dict[str, Any]],
    observed_texture: Any,
    colors: list[str],
    decor: list[str],
    fit: list[str],
    visible_fasteners: list[str],
    visible_pockets: list[str],
    notes: list[dict[str, Any]],
) -> bool:
    if not items:
        return False
    visible_types = [
        str(item.get("type") or "").strip().lower()
        for item in items
        if bool(item.get("visible", True))
    ]
    if not visible_types or any(
        item_type not in {"", "unknown", "неизвестно"} for item_type in visible_types
    ):
        return False
    strong_signals = (
        bool(observed_texture)
        or bool(colors)
        or bool(decor)
        or bool(fit)
        or bool(visible_fasteners)
        or bool(visible_pockets)
    )
    if strong_signals:
        return False
    return not any(
        note.get("visible_parts") or note.get("observation") for note in notes
    )


def normalize_product_dna_json(
    raw: dict[str, Any], *, subject_name: str = ""
) -> dict[str, Any]:
    data = raw if isinstance(raw, dict) else {}
    for nested_key in ("product_dna", "dna", "visual_evidence", "evidence"):
        nested = data.get(nested_key)
        if isinstance(nested, dict) and not any(
            key in data for key in ("items", "summary", "observed_texture")
        ):
            data = nested
            break
    try:
        confidence = float(
            data.get("confidence", data.get("overall_confidence", 0)) or 0
        )
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(confidence, 1.0))

    try:
        is_set_confidence = float(data.get("is_set_confidence", 0) or 0)
    except (TypeError, ValueError):
        is_set_confidence = 0.0

    items = []
    for item in _as_list(data.get("items"), limit=8):
        if isinstance(item, dict):
            item_type = _normalize_item_type(item.get("type") or "unknown")
            try:
                item_conf = float(item.get("confidence", 0) or 0)
            except (TypeError, ValueError):
                item_conf = 0.0
            items.append(
                {
                    "type": item_type,
                    "confidence": max(0.0, min(item_conf, 1.0)),
                    "visible": bool(item.get("visible", True)),
                }
            )
        elif str(item or "").strip():
            items.append(
                {"type": _normalize_item_type(item), "confidence": 0.5, "visible": True}
            )

    notes = _normalize_per_photo_notes(data.get("per_photo_notes"))

    observed_texture = str(data.get("observed_texture") or "").strip() or None
    colors = _normalize_string_values(data.get("color"), limit=8)
    decor = _normalize_string_values(
        data.get("decor"), limit=12, drop_noise=_DNA_DECOR_NOISE_TERMS
    )
    fit = _normalize_string_values(
        data.get("fit"), limit=8, drop_noise=_DNA_ACCESSORY_TERMS
    )
    visible_fasteners = _normalize_string_values(data.get("visible_fasteners"), limit=8)
    visible_pockets = _normalize_string_values(data.get("visible_pockets"), limit=8)
    uncertain = _normalize_string_values(data.get("uncertain"), limit=12)

    if _has_unknown_only_trivial_signal(
        items=items,
        observed_texture=observed_texture,
        colors=colors,
        decor=decor,
        fit=fit,
        visible_fasteners=visible_fasteners,
        visible_pockets=visible_pockets,
        notes=notes,
    ):
        return {}

    material_guess = data.get("material_guess")
    try:
        material_conf = float(data.get("material_confidence", confidence) or 0)
    except (TypeError, ValueError):
        material_conf = 0.0
    if material_conf < 0.85:
        material_guess = None
    elif material_guess is not None:
        material_guess = str(material_guess).strip() or None

    summary = str(data.get("summary") or "").strip()
    if _summary_looks_noisy(summary):
        uncertain.append("summary rebuilt from normalized evidence")
        summary = ""

    confidence = _derive_product_dna_confidence(
        confidence,
        items=items,
        observed_texture=observed_texture,
        material_guess=material_guess,
        colors=colors,
        decor=decor,
        fit=fit,
        notes=notes,
        uncertain=uncertain,
    )

    visible_types = [
        str(item.get("type") or "").strip().lower()
        for item in items
        if str(item.get("type") or "").strip().lower() not in {"", "unknown"}
    ]
    distinct_visible_types = {
        item_type for item_type in visible_types if item_type not in {"set", "suit"}
    }
    derived_is_set = (
        bool(data.get("is_set", False))
        or any(item_type in {"set", "suit"} for item_type in visible_types)
        or len(distinct_visible_types) >= 2
    )
    if derived_is_set and is_set_confidence < 0.6:
        is_set_confidence = (
            0.6 if len(distinct_visible_types) >= 2 else max(is_set_confidence, 0.45)
        )

    if not summary and has_meaningful_product_dna(
        {
            "items": items,
            "observed_texture": observed_texture,
            "material_guess": material_guess,
            "decor": decor,
            "fit": fit,
            "visible_fasteners": visible_fasteners,
            "visible_pockets": visible_pockets,
            "color": colors,
            "per_photo_notes": notes,
            "confidence": confidence,
        }
    ):
        summary = _build_fallback_summary(
            items=items,
            observed_texture=observed_texture,
            colors=colors,
            decor=decor,
            fit=fit,
            uncertain=uncertain,
        )

    normalized = {
        "version": str(data.get("version") or PRODUCT_DNA_VERSION),
        "subject_name": subject_name or str(data.get("subject_name") or ""),
        "confidence": confidence,
        "is_set": derived_is_set,
        "is_set_confidence": max(0.0, min(is_set_confidence, 1.0)),
        "items": items,
        "observed_texture": observed_texture,
        "material_guess": material_guess,
        "material_confidence": max(0.0, min(material_conf, 1.0)),
        "color": colors,
        "decor": decor,
        "fit": fit,
        "visible_fasteners": visible_fasteners,
        "visible_pockets": visible_pockets,
        "uncertain": uncertain,
        "per_photo_notes": notes,
        "summary": summary,
    }
    if not has_meaningful_product_dna(normalized):
        return {}
    if not any(
        str(item.get("type") or "").strip().lower() not in {"", "unknown", "неизвестно"}
        for item in items
    ) and not any(
        bool(normalized.get(key))
        for key in (
            "observed_texture",
            "material_guess",
            "decor",
            "fit",
            "visible_fasteners",
            "visible_pockets",
            "color",
        )
    ):
        return {}
    return normalized


def product_dna_to_text(dna: dict[str, Any]) -> str:
    if not has_meaningful_product_dna(dna):
        return ""
    parts: list[str] = []
    if dna.get("summary"):
        parts.append(str(dna["summary"]).strip())
    items = ", ".join(
        str(item.get("type"))
        for item in dna.get("items", [])
        if isinstance(item, dict) and item.get("type")
    )
    if items:
        parts.append(f"Items: {items}.")
    if dna.get("observed_texture"):
        parts.append(f"Observed texture: {dna['observed_texture']}.")
    if dna.get("material_guess"):
        parts.append(f"Material guess: {dna['material_guess']}.")
    for key, label in (("color", "Color"), ("decor", "Decor"), ("fit", "Fit")):
        values = [str(x) for x in dna.get(key, []) if str(x).strip()]
        if values:
            parts.append(f"{label}: {', '.join(values)}.")
    uncertain = [str(x) for x in dna.get("uncertain", []) if str(x).strip()]
    if uncertain:
        parts.append(f"Uncertain: {', '.join(uncertain)}.")
    return "\n".join(parts).strip()


class VisionService:
    """GPT-4o-mini orqali mahsulot fotosidan texnik tavsif (Product DNA) yaratadi."""

    def __init__(self) -> None:
        self._api_key = settings.OPENAI_API_KEY
        self._model = settings.OPENAI_VISION_MODEL
        self._base_url = "https://api.openai.com/v1/chat/completions"

    @property
    def is_enabled(self) -> bool:
        return bool(self._api_key and settings.checker_vision_enabled)

    async def generate_product_dna_text(
        self,
        photo_url: str,
        subject_name: str = "",
        photo_urls: Optional[List[str]] = None,
    ) -> str:
        """
        Mahsulot fotosini bir marta tahlil qilib texnik tavsif yaratadi.
        Bu matn DB da saqlanadi va keyingi barcha AI chaqiruvlarida ishlatiladi.

        Returns:
            Detailed technical text description (~300-500 words) yoki "" (xato bo'lsa)
        """
        dna = await self.generate_product_dna_json(photo_url, subject_name, photo_urls)
        return product_dna_to_text(dna)

    async def generate_product_dna_json(
        self,
        photo_url: str,
        subject_name: str = "",
        photo_urls: Optional[List[str]] = None,
    ) -> dict[str, Any]:
        """Analyze product photos and return normalized structured Product DNA."""
        result = await self.generate_product_dna_result(
            photo_url, subject_name, photo_urls
        )
        return result.get("dna") if isinstance(result.get("dna"), dict) else {}

    async def generate_product_dna_result(
        self,
        photo_url: str,
        subject_name: str = "",
        photo_urls: Optional[List[str]] = None,
    ) -> dict[str, Any]:
        """Analyze product photos and return DNA plus failure diagnostics."""
        if not self.is_enabled:
            logger.warning("[vision] OPENAI_API_KEY sozlanmagan")
            return {
                "dna": {},
                "audit": build_product_dna_audit({}, subject_name=subject_name),
                "error": "disabled",
                "raw_excerpt": "",
                "finish_reason": None,
            }

        try:
            user_prompt = _PRODUCT_DNA_USER % (subject_name or "не указана")

            candidate_urls = list(photo_urls or [])
            if photo_url:
                candidate_urls = [photo_url] + candidate_urls

            content_parts: List[dict[str, Any]] = []
            seen_urls: set[str] = set()
            for u in candidate_urls:
                uu = str(u or "").strip()
                if not uu or uu in seen_urls:
                    continue
                seen_urls.add(uu)

                image_b64, mime_type = await self._fetch_image_b64(uu)
                if not image_b64:
                    continue

                content_parts.append(
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{mime_type};base64,{image_b64}",
                            "detail": "high",
                        },
                    }
                )
                if len(content_parts) >= 5:
                    break

            if not content_parts:
                return {
                    "dna": {},
                    "audit": build_product_dna_audit(
                        {}, subject_name=subject_name, photo_count=0
                    ),
                    "error": "no_fetchable_photos",
                    "raw_excerpt": "",
                    "finish_reason": None,
                }

            used_photo_count = len(content_parts)
            content_parts.append({"type": "text", "text": user_prompt})

            payload = {
                "model": self._model,
                "messages": [
                    {"role": "system", "content": _PRODUCT_DNA_SYSTEM},
                    {
                        "role": "user",
                        "content": content_parts,
                    },
                ],
                "response_format": {"type": "json_object"},
            }
            _apply_openai_generation_params(payload, model=self._model, max_tokens=3000)

            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(
                    self._base_url,
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )

            if resp.status_code != 200:
                logger.error(
                    "[vision] OpenAI API error %d: %s",
                    resp.status_code,
                    resp.text[:300],
                )
                return {
                    "dna": {},
                    "audit": build_product_dna_audit(
                        {}, subject_name=subject_name, photo_count=used_photo_count
                    ),
                    "error": f"api_error:{resp.status_code}",
                    "raw_excerpt": resp.text[:600],
                    "finish_reason": None,
                }

            data = resp.json()
            choice = (data.get("choices") or [{}])[0]
            finish_reason = (
                choice.get("finish_reason") if isinstance(choice, dict) else None
            )
            text = _choice_message_text(choice)
            if not text:
                logger.warning(
                    "[vision] empty_product_dna_content | subject=%s | finish_reason=%s",
                    subject_name,
                    finish_reason,
                )
                return {
                    "dna": {},
                    "audit": build_product_dna_audit(
                        {}, subject_name=subject_name, photo_count=used_photo_count
                    ),
                    "error": f"empty_content:{finish_reason or 'unknown'}",
                    "raw_excerpt": "",
                    "finish_reason": finish_reason,
                }
            parsed, parse_error = _json_parse_result(text)
            if not parsed:
                logger.warning(
                    "[vision] parse_failed_product_dna | subject=%s | error=%s | raw_excerpt=%s",
                    subject_name,
                    parse_error,
                    text[:600],
                )
                return {
                    "dna": {},
                    "audit": build_product_dna_audit(
                        {}, subject_name=subject_name, photo_count=used_photo_count
                    ),
                    "error": f"{parse_error}:{text[:240]}",
                    "raw_excerpt": text[:600],
                    "finish_reason": finish_reason,
                }
            dna = normalize_product_dna_json(parsed, subject_name=subject_name)
            audit = build_product_dna_audit(
                dna,
                subject_name=subject_name,
                photo_count=used_photo_count,
            )
            if not dna:
                logger.warning(
                    "[vision] empty_or_non_meaningful_product_dna | subject=%s | raw_excerpt=%s",
                    subject_name,
                    text[:600],
                )
                return {
                    "dna": {},
                    "audit": build_product_dna_audit(
                        {}, subject_name=subject_name, photo_count=used_photo_count
                    ),
                    "error": f"empty_result:{text[:240]}",
                    "raw_excerpt": text[:600],
                    "finish_reason": finish_reason,
                }
            logger.info(
                "[vision] Product DNA JSON yaratildi: confidence=%.2f, kategoriya=%s",
                float(dna.get("confidence") or 0),
                subject_name,
            )
            return {
                "dna": dna,
                "audit": audit,
                "error": None,
                "raw_excerpt": text[:600],
                "finish_reason": finish_reason,
            }

        except httpx.TimeoutException:
            logger.warning("[vision] generate_product_dna_json timeout")
            return {
                "dna": {},
                "audit": build_product_dna_audit({}, subject_name=subject_name),
                "error": "timeout",
                "raw_excerpt": "",
                "finish_reason": None,
            }
        except Exception:
            logger.exception("[vision] generate_product_dna_json xatosi")
            return {
                "dna": {},
                "audit": build_product_dna_audit({}, subject_name=subject_name),
                "error": "exception",
                "raw_excerpt": "",
                "finish_reason": None,
            }

    async def analyze_photo_dna(
        self,
        photo_url: str,
        subject_name: str = "",
    ) -> dict[str, Any]:
        """
        Mahsulot fotosini tahlil qilib Product DNA JSON qaytaradi.
        Fixed file characteristics generation uchun ishlatiladi.
        """
        if not self.is_enabled:
            logger.warning("[vision] OPENAI_API_KEY sozlanmagan")
            return {}

        return await self.generate_product_dna_json(photo_url, subject_name)

    def extract_wb_characteristics(self, dna: dict[str, Any]) -> dict[str, str]:
        """Product DNA dict dan WB xarakteristikalarini chiqaradi."""
        if not dna:
            return {}
        result: dict[str, str] = {}
        wb_chars = dna.get("wb_characteristics", {})
        for char_name, value in wb_chars.items():
            if value and value not in ("unknown", "не определено", "не определён", ""):
                result[char_name] = str(value)
        return result

    def _extract_dna_from_text(self, text: str) -> dict[str, Any]:
        """Texnik tavsif matnidan asosiy ma'lumotlarni ajratib oladi."""
        dna: dict[str, Any] = {"raw_description": text, "wb_characteristics": {}}

        # Extract color
        color_match = re.search(
            r"(?:основной цвет|цвет)[:\s]+([^\n,\.]+)", text, re.IGNORECASE
        )
        if color_match:
            dna["wb_characteristics"]["Цвет"] = color_match.group(1).strip()

        # Extract style
        style_match = re.search(r"(?:стиль)[:\s]+([^\n]+)", text, re.IGNORECASE)
        if style_match:
            dna["wb_characteristics"]["Стиль"] = style_match.group(1).strip()

        # Extract seasonality
        season_match = re.search(
            r"(?:сезонность|сезон)[:\s]+([^\n]+)", text, re.IGNORECASE
        )
        if season_match:
            dna["wb_characteristics"]["Сезон"] = season_match.group(1).strip()

        # Extract material
        mat_match = re.search(r"(?:материал)[:\s]+([^\n]+)", text, re.IGNORECASE)
        if mat_match and "не определ" not in mat_match.group(1).lower():
            dna["wb_characteristics"]["Фактура материала"] = mat_match.group(1).strip()

        return dna

    async def _fetch_image_b64(self, url: str) -> tuple[str, str]:
        """URL dan rasmni yuklab base64 ga o'giradi."""
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(url, follow_redirects=True)
            if resp.status_code != 200:
                logger.warning(
                    "[vision] rasm yuklanmadi: %s → %d", url, resp.status_code
                )
                return "", "image/jpeg"
            mime_type = resp.headers.get("content-type", "image/jpeg").split(";")[0]
            b64 = base64.b64encode(resp.content).decode()
            return b64, mime_type
        except Exception:
            logger.exception("[vision] rasm yuklab olishda xato: %s", url)
            return "", "image/jpeg"


# Singleton
vision_service = VisionService()
