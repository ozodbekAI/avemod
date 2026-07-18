from __future__ import annotations

import re
from collections import Counter
from typing import Any, Dict, Iterable, List, Tuple

from app.core.config import get_settings

settings = get_settings()

_WORD_RE = re.compile(r"[а-яёa-z0-9-]+", re.IGNORECASE)
_ALLOWED_TITLE_RE = re.compile(r"^[A-Za-zА-Яа-яЁё0-9\-\s]+$")

COLOR_WORDS = {
    "черный",
    "белый",
    "красный",
    "синий",
    "зеленый",
    "серый",
    "бежевый",
    "розовый",
    "голубой",
    "желтый",
    "коричневый",
    "фиолетовый",
    "оранжевый",
    "бордовый",
    "бирюзовый",
    "сиреневый",
    "малиновый",
    "салатовый",
    "персиковый",
    "лавандовый",
    "мятный",
    "хаки",
    "молочный",
    "айвори",
    "бордо",
    "индиго",
    "марсала",
    "пудровый",
    "графитовый",
    "шоколадный",
    "песочный",
    "кремовый",
    "изумрудный",
    "васильковый",
    "терракотовый",
    "мандариновый",
    "горчичный",
    "жемчужный",
}

FORBIDDEN_GENDER_WORDS = {
    "женский",
    "мужской",
    "детский",
    "для",
    "девочки",
    "мальчика",
}

FORBIDDEN_MARKETING_WORDS = {
    "топ",
    "хит",
    "лучший",
    "идеальный",
    "премиум",
    "люкс",
    "супер",
    "модный",
    "трендовый",
    "качественный",
    "безупречный",
    "стильный",
}

FORBIDDEN_EMOTIONAL_WORDS = {
    "красивый",
    "элегантный",
    "шикарный",
    "роскошный",
    "великолепный",
    "прекрасный",
    "очаровательный",
}

FORBIDDEN_ATTR_ZONE_WORDS = {
    "хлопок",
    "полиэстер",
    "вискоза",
    "шелк",
    "лен",
    "шерсть",
    "акрил",
    "кашемир",
    "спандекс",
    "эластан",
    "полиамид",
    "нейлон",
    "сезон",
    "зима",
    "лето",
    "демисезон",
    "осень",
    "весна",
    "страна",
    "производства",
    "турция",
    "китай",
    "россия",
    "италия",
    "премиального",
    "качества",
}

STOPWORDS = {
    "и",
    "в",
    "во",
    "на",
    "с",
    "со",
    "к",
    "по",
    "из",
    "за",
    "от",
    "для",
    "или",
    "а",
    "но",
    "под",
    "над",
    "при",
    "о",
    "об",
    "без",
    "не",
    "же",
    "ли",
    "для",
    "под",
    "подо",
}

NOISY_TOKENS = {
    "подходит",
    "подходят",
    "подойдет",
    "можно",
    "может",
    "имеет",
    "имеются",
    "выполнен",
    "выполнена",
    "выполнено",
    "представлен",
    "представлена",
    "подчеркивает",
    "обеспечивает",
    "создает",
}

KEY_FEATURE_NAME_KEYS = (
    "фасон",
    "модел",
    "силуэт",
    "крой",
    "тип",
    "длина",
    "посад",
    "особенност",
)
CONSTRUCTIVE_NAME_KEYS = (
    "застеж",
    "вырез",
    "ворот",
    "карман",
    "пояс",
    "разрез",
    "баск",
    "рукав",
    "борт",
    "лацкан",
    "манжет",
    "кокетк",
)
PURPOSE_NAME_KEYS = ("назнач", "стиль", "повод", "событ", "образ")
COLOR_NAME_KEYS = ("цвет",)

PURPOSE_PHRASE_MAP = {
    "для офиса": "офисный",
    "для работы": "деловой",
    "для вечера": "вечерний",
    "для праздника": "праздничный",
    "для прогулки": "повседневный",
    "на каждый день": "повседневный",
    "повседневной носки": "повседневный",
}
_PURPOSE_PHRASE_EQUIVALENTS = {
    "для офиса": {"офисный", "деловой"},
    "для работы": {"деловой", "офисный"},
    "для вечера": {"вечерний"},
    "для праздника": {"праздничный", "вечерний"},
    "для прогулки": {"повседневный"},
    "на каждый день": {"повседневный"},
    "повседневной носки": {"повседневный"},
}

PURPOSE_WORDS = {
    "офисный",
    "деловой",
    "вечерний",
    "повседневный",
    "праздничный",
    "коктейльный",
    "сценический",
}

COMMERCIAL_SIGNAL_WORDS = {
    "полоска",
    "полоску",
    "полоске",
    "клетка",
    "клетку",
    "клетке",
    "кант",
    "кантом",
    "мини",
    "миди",
    "макси",
    "палаццо",
    "оверсайз",
    "жакет",
    "пиджак",
    "брюки",
    "юбка",
    "юбку",
    "блузка",
    "блузку",
    "рубашка",
    "жилет",
    "жилетку",
    "шорты",
    "бантом",
    "бант",
}

COMMERCIAL_SIGNAL_PHRASES = {
    "с кантом",
    "в полоску",
    "брюки палаццо",
    "блузка с бантом",
    "юбка миди",
    "юбка мини",
    "юбка макси",
}

CATEGORY_NORMALIZATION = {
    "костюмы": "костюм",
    "платья": "платье",
    "юбки": "юбка",
    "жакеты": "жакет",
    "рубашки": "рубашка",
    "блузки": "блузка",
    "пиджаки": "пиджак",
    "комбинезоны": "комбинезон",
}


def _norm_space(text: str) -> str:
    return " ".join((text or "").strip().split())


def _tokenize(text: str) -> List[str]:
    return _WORD_RE.findall((text or "").lower())


def _iter_characteristics(card: Dict[str, Any]) -> Iterable[Tuple[str, str]]:
    chars = card.get("characteristics") or []
    if isinstance(chars, dict):
        for k, v in chars.items():
            if v is None:
                continue
            if isinstance(v, list):
                vv = ", ".join(str(x) for x in v if x is not None)
            else:
                vv = str(v)
            if vv.strip():
                yield str(k), vv.strip()
        return

    if isinstance(chars, list):
        for ch in chars:
            if not isinstance(ch, dict):
                continue
            name = str(ch.get("name") or "").strip()
            if not name:
                continue
            val = ch.get("value")
            if val is None:
                val = ch.get("values")
            if isinstance(val, list):
                vv = ", ".join(str(x) for x in val if x is not None)
            elif val is not None:
                vv = str(val).strip()
            else:
                vv = ""
            if vv:
                yield name, vv


def _split_values(raw: str) -> List[str]:
    text = str(raw or "").strip()
    if not text:
        return []
    parts = re.split(r"[,;/]| и | / ", text, flags=re.IGNORECASE)
    out = [_norm_space(p) for p in parts if _norm_space(p)]
    return out or [text]


def _is_forbidden_token(token: str, allow_color: bool = False) -> bool:
    if token in STOPWORDS or token in NOISY_TOKENS:
        return True
    if token in FORBIDDEN_GENDER_WORDS:
        return True
    if token in FORBIDDEN_MARKETING_WORDS or token in FORBIDDEN_EMOTIONAL_WORDS:
        return True
    if token in FORBIDDEN_ATTR_ZONE_WORDS:
        return True
    if not allow_color and token in COLOR_WORDS:
        return True
    return False


def _normalize_slot_phrase(
    raw: str, max_tokens: int = 2, allow_color: bool = False
) -> str:
    text = _norm_space(str(raw or "").replace("«", " ").replace("»", " "))
    if not text:
        return ""

    low = text.lower()
    for source, repl in PURPOSE_PHRASE_MAP.items():
        if source in low:
            return repl

    tokens: List[str] = []
    for token in _tokenize(text):
        if len(token) < 3:
            continue
        if token.isdigit():
            continue
        if _is_forbidden_token(token, allow_color=allow_color):
            continue
        if token in tokens:
            continue
        tokens.append(token)
        if len(tokens) >= max_tokens:
            break

    return " ".join(tokens)


def extract_category(card: Dict[str, Any]) -> str:
    for key in ("subjectName", "subject_name", "category_name"):
        raw = str(card.get(key) or "").strip()
        if not raw:
            continue
        parts = [p.strip() for p in raw.split("/") if p.strip()]
        candidate = parts[-1] if parts else raw
        normalized = _normalize_slot_phrase(candidate, max_tokens=2, allow_color=False)
        if normalized:
            raw_cat = normalized.split()[0]
            return CATEGORY_NORMALIZATION.get(raw_cat, raw_cat)

    title_words = [
        w
        for w in _tokenize(str(card.get("title") or ""))
        if not _is_forbidden_token(w, allow_color=False)
    ]
    if title_words:
        raw_cat = title_words[0]
        return CATEGORY_NORMALIZATION.get(raw_cat, raw_cat)
    return "товар"


def _extract_slots(card: Dict[str, Any]) -> Dict[str, List[str]]:
    slots = {"feature": [], "constructive": [], "purpose": [], "color": []}
    for name, value in _iter_characteristics(card):
        name_l = name.lower()
        values = _split_values(value)
        for raw in values:
            if any(k in name_l for k in KEY_FEATURE_NAME_KEYS):
                norm = _normalize_slot_phrase(raw, max_tokens=2, allow_color=False)
                if norm:
                    slots["feature"].append(norm)
            if any(k in name_l for k in CONSTRUCTIVE_NAME_KEYS):
                norm = _normalize_slot_phrase(raw, max_tokens=2, allow_color=False)
                if norm:
                    slots["constructive"].append(norm)
            if any(k in name_l for k in PURPOSE_NAME_KEYS):
                norm = _normalize_slot_phrase(raw, max_tokens=2, allow_color=False)
                if norm:
                    slots["purpose"].append(norm)
            if any(k in name_l for k in COLOR_NAME_KEYS):
                for token in _tokenize(raw):
                    if token in COLOR_WORDS:
                        slots["color"].append(token)

    for source, repl in PURPOSE_PHRASE_MAP.items():
        all_text = " ".join(
            [
                str(card.get("title") or ""),
                str(card.get("description") or ""),
            ]
        ).lower()
        if source in all_text:
            slots["purpose"].append(repl)

    return slots


def _unique_phrases(items: Iterable[str]) -> List[str]:
    out: List[str] = []
    seen = set()
    for item in items:
        norm = _norm_space(item).lower()
        if not norm or norm in seen:
            continue
        seen.add(norm)
        out.append(norm)
    return out


def _collect_evidence_tokens(card: Dict[str, Any]) -> set[str]:
    texts = [
        str(card.get("title") or ""),
        str(card.get("description") or ""),
        str(card.get("subjectName") or ""),
        str(card.get("subject_name") or ""),
        str(card.get("category_name") or ""),
    ]
    for _, value in _iter_characteristics(card):
        texts.append(value)

    out = set()
    full = " ".join(texts).lower()
    for source, repl in PURPOSE_PHRASE_MAP.items():
        if source in full:
            out.add(repl)
    for token in _tokenize(" ".join(texts)):
        if len(token) < 3 or token.isdigit():
            continue
        if token in FORBIDDEN_MARKETING_WORDS or token in FORBIDDEN_EMOTIONAL_WORDS:
            continue
        out.add(token)
    return out


def _ordered_evidence_terms(card: Dict[str, Any]) -> List[str]:
    sources: List[str] = [
        str(card.get("title") or ""),
        str(card.get("description") or ""),
    ]
    for _, value in _iter_characteristics(card):
        sources.append(value)

    ordered: List[str] = []
    seen = set()
    full = " ".join(sources).lower()
    for source, repl in PURPOSE_PHRASE_MAP.items():
        if source in full and repl not in seen:
            seen.add(repl)
            ordered.append(repl)

    for src in sources:
        for token in _tokenize(src):
            if len(token) < 4 or token.isdigit():
                continue
            if _is_forbidden_token(token, allow_color=True):
                continue
            if token in FORBIDDEN_MARKETING_WORDS or token in FORBIDDEN_EMOTIONAL_WORDS:
                continue
            if token in seen:
                continue
            seen.add(token)
            ordered.append(token)
    return ordered


def _pick_title_context_feature(card: Dict[str, Any], category: str) -> str:
    title = str(card.get("title") or "")
    cand = []
    for token in _tokenize(title):
        if len(token) < 4:
            continue
        if token == category:
            continue
        if _is_forbidden_token(token, allow_color=False):
            continue
        cand.append(token)
    if cand:
        return cand[0]
    return ""


def _confirmed_title_color(card: Dict[str, Any]) -> str:
    slots = _extract_slots(card)
    colors = _unique_phrases(slots["color"])
    if len(colors) != 1:
        return ""

    base_title_tokens = set(_tokenize(str(card.get("title") or "")))
    color = colors[0]
    if color in base_title_tokens:
        return color
    return ""


def _append_unique(parts: List[str], phrase: str) -> None:
    phrase = _norm_space(phrase)
    if not phrase:
        return
    phrase_tokens = set(_tokenize(phrase))
    for existing in parts:
        if phrase_tokens & set(_tokenize(existing)):
            return
    parts.append(phrase)


def build_title_from_card(
    card: Dict[str, Any],
    min_len: int | None = None,
    max_len: int | None = None,
) -> str:
    min_len = int(min_len if min_len is not None else settings.MIN_TITLE_LENGTH)
    max_len = int(max_len if max_len is not None else settings.MAX_TITLE_LENGTH)

    category = extract_category(card)
    slots = _extract_slots(card)

    key_feature = (_unique_phrases(slots["feature"]) or [""])[0]
    if not key_feature:
        key_feature = _pick_title_context_feature(card, category)
    if not key_feature:
        evidence = [
            t for t in _collect_evidence_tokens(card) if len(t) >= 4 and t != category
        ]
        key_feature = sorted(evidence)[0] if evidence else ""

    constructive = (_unique_phrases(slots["constructive"]) or [""])[0]
    purpose = (
        _unique_phrases([x for x in slots["purpose"] if x in PURPOSE_WORDS]) or [""]
    )[0]
    color = _confirmed_title_color(card)

    parts: List[str] = []
    _append_unique(parts, category)
    _append_unique(parts, key_feature)
    _append_unique(parts, constructive)
    _append_unique(parts, purpose)
    if color:
        _append_unique(parts, color)

    if len(parts) < 2:
        fallback = [p for p in (category, key_feature, constructive, purpose) if p]
        if fallback:
            parts = fallback[:2]

    # Enrich to min length using still-confirmed optional parts.
    backups = _unique_phrases(
        slots["feature"] + slots["constructive"] + slots["purpose"]
    )
    for b in backups:
        if len(_norm_space(" ".join(parts))) >= min_len:
            break
        candidate = _norm_space(" ".join(parts + [b]))
        if len(candidate) <= max_len:
            _append_unique(parts, b)

    # Trim from the end if too long (optional slots first).
    while len(_norm_space(" ".join(parts))) > max_len and len(parts) > 2:
        parts.pop()

    title = _norm_space(" ".join(parts))
    if not title:
        return ""

    title = title[0].upper() + title[1:]
    valid, _ = validate_title(title, card, min_len=min_len, max_len=max_len)
    if valid:
        return title

    # Conservative fallback: enrich with confirmed evidence terms to reach 40-60.
    fallback_parts: List[str] = []
    _append_unique(fallback_parts, category)
    _append_unique(fallback_parts, key_feature)
    _append_unique(fallback_parts, constructive)
    _append_unique(fallback_parts, purpose)
    if color:
        _append_unique(fallback_parts, color)

    for term in _ordered_evidence_terms(card):
        if term == category:
            continue
        candidate = _norm_space(" ".join(fallback_parts + [term]))
        if len(candidate) > max_len:
            continue
        _append_unique(fallback_parts, term)
        if len(candidate) >= min_len:
            break

    while (
        len(_norm_space(" ".join(fallback_parts))) > max_len and len(fallback_parts) > 2
    ):
        fallback_parts.pop()

    fallback = _norm_space(" ".join(fallback_parts))
    if fallback:
        fallback = fallback[0].upper() + fallback[1:]
    return fallback


def _category_match(title_words: List[str], category: str) -> bool:
    if not category:
        return True
    cat = category.lower()
    for w in title_words[:2]:
        if w == cat:
            return True
        if len(cat) >= 4 and (w.startswith(cat[:4]) or cat.startswith(w[:4])):
            return True
    return False


def _stem(w: str, length: int = 6) -> str:
    """Return a simple prefix stem for Russian morphological matching."""
    return w[:length] if len(w) >= length else w


def check_title_facts(title: str, card: Dict[str, Any]) -> Tuple[bool, str]:
    words = _tokenize(title)
    evidence = _collect_evidence_tokens(card)
    allowed_derived = set(PURPOSE_PHRASE_MAP.values()) | PURPOSE_WORDS

    # Build stem-based evidence set for morphological tolerance (Russian inflection, 5-char prefix)
    evidence_stems = {_stem(t, 5) for t in evidence if len(t) >= 5}
    # Also accept category tokens
    category = extract_category(card).lower()
    subj = str(card.get("subjectName") or card.get("subject_name") or "").lower()
    extra_ok = {t for t in _tokenize(subj) if len(t) >= 4}

    for w in words:
        if len(w) < 4:
            continue
        if w in STOPWORDS:
            continue
        if w in allowed_derived:
            continue
        if w in COLOR_WORDS:
            continue
        if w == category:
            continue
        if w in extra_ok:
            continue
        if w in evidence:
            continue
        # Morphological fallback: match by 5-char stem (handles Russian inflections)
        if len(w) >= 5 and _stem(w, 5) in evidence_stems:
            continue
        return False, f"Неподтверждённый признак: {w}"
    return True, ""


def _has_key_model_feature(
    title_words: List[str], category: str, card: Dict[str, Any]
) -> bool:
    expected = set()
    slots = _extract_slots(card)
    for item in slots["feature"]:
        expected.update(_tokenize(item))

    if not expected:
        expected.update(
            t
            for t in _collect_evidence_tokens(card)
            if len(t) >= 4 and t not in COLOR_WORDS and t != category
        )

    if not expected:
        return len([w for w in title_words if len(w) >= 4 and w != category]) >= 1

    # Build stem set for morphological matching
    expected_stems = {_stem(t, 5) for t in expected if len(t) >= 5}

    for w in title_words:
        if w in expected and w != category and w not in COLOR_WORDS:
            return True
        # Morphological variant match (e.g. двубортный vs двубортная vs двубортным)
        if (
            len(w) >= 5
            and w != category
            and w not in COLOR_WORDS
            and _stem(w, 5) in expected_stems
        ):
            return True

    # Fallback: accept any word confirmed by evidence tokens (broader check).
    # This handles AI-generated titles using valid forms not in feature slots.
    evidence = _collect_evidence_tokens(card)
    evidence_stems_all = {_stem(t, 5) for t in evidence if len(t) >= 5}
    for w in title_words:
        if (
            len(w) >= 5
            and w != category
            and w not in COLOR_WORDS
            and w not in FORBIDDEN_MARKETING_WORDS
            and w not in FORBIDDEN_EMOTIONAL_WORDS
            and w not in FORBIDDEN_ATTR_ZONE_WORDS
            and w not in STOPWORDS
            and (_stem(w, 5) in evidence_stems_all or w in evidence)
        ):
            return True
    return False


def extract_preserve_tokens(current_title: str, card: Dict[str, Any]) -> set[str]:
    evidence = _collect_evidence_tokens(card)
    evidence_stems = {_stem(token, 5) for token in evidence if len(token) >= 5}
    title_tokens = set(_tokenize(current_title))
    preserve: set[str] = set()
    for token in title_tokens:
        if token in COMMERCIAL_SIGNAL_WORDS:
            preserve.add(token)
            continue
        if token in evidence:
            preserve.add(token)
            continue
        if len(token) >= 5 and _stem(token, 5) in evidence_stems:
            preserve.add(token)
    return preserve


def _candidate_covers_phrase(
    phrase: str,
    *,
    candidate_tokens: set[str],
    candidate_stems: set[str],
) -> tuple[bool, str | None]:
    phrase_tokens = [token for token in _tokenize(phrase) if token not in STOPWORDS]
    if phrase_tokens and all(
        token in candidate_tokens
        or (len(token) >= 5 and _stem(token, 5) in candidate_stems)
        for token in phrase_tokens
    ):
        return True, None

    equivalents = _PURPOSE_PHRASE_EQUIVALENTS.get(phrase) or set()
    for token in equivalents:
        if token in candidate_tokens or (
            len(token) >= 5 and _stem(token, 5) in candidate_stems
        ):
            return True, token
    return False, None


def title_business_regression(
    current_title: str, candidate: str, card: Dict[str, Any]
) -> tuple[bool, dict]:
    current_tokens = set(_tokenize(current_title))
    candidate_tokens = set(_tokenize(candidate))
    candidate_stems = {_stem(token, 5) for token in candidate_tokens if len(token) >= 5}
    preserve = extract_preserve_tokens(current_title, card)
    dropped = sorted(preserve - candidate_tokens)
    current_norm = _norm_space(str(current_title or "").lower())
    dropped_phrases: List[str] = []
    preserved_phrases: List[str] = []
    covered_phrase_equivalents: Dict[str, str] = {}

    for phrase in sorted(_PURPOSE_PHRASE_EQUIVALENTS):
        if phrase not in current_norm:
            continue
        covered, matched_equivalent = _candidate_covers_phrase(
            phrase,
            candidate_tokens=candidate_tokens,
            candidate_stems=candidate_stems,
        )
        if covered and matched_equivalent:
            phrase_tokens = set(_tokenize(phrase))
            dropped = [token for token in dropped if token not in phrase_tokens]
            covered_phrase_equivalents[phrase] = matched_equivalent

    for phrase in sorted(COMMERCIAL_SIGNAL_PHRASES):
        if phrase not in current_norm:
            continue
        preserved_phrases.append(phrase)
        covered, matched_equivalent = _candidate_covers_phrase(
            phrase,
            candidate_tokens=candidate_tokens,
            candidate_stems=candidate_stems,
        )
        if not covered:
            dropped_phrases.append(phrase)
        elif matched_equivalent:
            covered_phrase_equivalents[phrase] = matched_equivalent
    added = sorted(candidate_tokens - current_tokens)
    bad_added = [
        token
        for token in added
        if token in COLOR_WORDS or token in FORBIDDEN_ATTR_ZONE_WORDS
    ]
    return bool(dropped or dropped_phrases or bad_added), {
        "current_title": current_title,
        "candidate_title": candidate,
        "preserved_tokens": sorted(preserve),
        "dropped_tokens": dropped,
        "preserved_phrases": preserved_phrases,
        "dropped_phrases": dropped_phrases,
        "covered_phrase_equivalents": covered_phrase_equivalents,
        "added_tokens": added,
        "bad_added_tokens": bad_added,
    }


def _title_material_improvement(
    current_title: str,
    candidate_title: str,
    card: Dict[str, Any],
) -> tuple[bool, dict]:
    current_valid_strict, current_reason = validate_title(
        current_title, card, strict_content=True
    )
    candidate_valid_strict, candidate_reason = validate_title(
        candidate_title, card, strict_content=True
    )
    current_valid_loose, _ = validate_title(current_title, card, strict_content=False)
    candidate_valid_loose, _ = validate_title(
        candidate_title, card, strict_content=False
    )

    current_category = extract_category(card).lower()
    current_tokens = [token for token in _tokenize(current_title) if len(token) >= 4]
    candidate_tokens = [
        token for token in _tokenize(candidate_title) if len(token) >= 4
    ]

    current_has_feature = _has_key_model_feature(current_tokens, current_category, card)
    candidate_has_feature = _has_key_model_feature(
        candidate_tokens, current_category, card
    )

    if not current_valid_loose and candidate_valid_loose:
        return True, {
            "material_improvement": "candidate_fixed_loose_validation",
            "current_validation_reason": current_reason,
            "candidate_validation_reason": candidate_reason,
        }
    if not current_valid_strict and candidate_valid_strict:
        return True, {
            "material_improvement": "candidate_fixed_strict_validation",
            "current_validation_reason": current_reason,
            "candidate_validation_reason": candidate_reason,
        }
    if (
        len(_norm_space(current_title)) < int(settings.MIN_TITLE_LENGTH)
        and candidate_valid_loose
        and len(_norm_space(candidate_title)) >= int(settings.MIN_TITLE_LENGTH)
    ):
        return True, {
            "material_improvement": "candidate_fixed_length",
            "current_validation_reason": current_reason,
            "candidate_validation_reason": candidate_reason,
        }
    if candidate_has_feature and not current_has_feature and candidate_valid_loose:
        return True, {
            "material_improvement": "candidate_added_confirmed_feature",
            "current_validation_reason": current_reason,
            "candidate_validation_reason": candidate_reason,
        }
    return False, {
        "material_improvement": "",
        "current_validation_reason": current_reason,
        "candidate_validation_reason": candidate_reason,
    }


def should_keep_current_title_as_safer(
    current_title: str,
    candidate_title: str,
    card: Dict[str, Any],
) -> tuple[bool, dict]:
    current_title = _norm_space(current_title)
    candidate_title = _norm_space(candidate_title)
    if not current_title or not candidate_title:
        return False, {
            "reason": "missing_title",
            "current_title": current_title,
            "candidate_title": candidate_title,
        }

    current_valid, current_reason = validate_title(
        current_title, card, strict_content=True
    )
    candidate_valid, candidate_reason = validate_title(
        candidate_title, card, strict_content=True
    )
    regressed, regression_info = title_business_regression(
        current_title, candidate_title, card
    )
    improved, improvement_info = _title_material_improvement(
        current_title, candidate_title, card
    )

    keep_current = False
    reason = ""

    if current_valid and regressed:
        keep_current = True
        reason = "candidate_regressed_confirmed_business_tokens"
    elif current_valid and not candidate_valid:
        keep_current = True
        reason = "current_title_already_strict_valid"
    elif current_valid and not improved:
        keep_current = True
        reason = "candidate_not_materially_better"

    return keep_current, {
        "reason": reason,
        "current_valid": current_valid,
        "candidate_valid": candidate_valid,
        "current_validation_reason": current_reason,
        "candidate_validation_reason": candidate_reason,
        "material_improvement": improvement_info.get("material_improvement", ""),
        "regression": regression_info,
    }


def validate_title(
    title: str,
    card: Dict[str, Any],
    min_len: int | None = None,
    max_len: int | None = None,
    strict_content: bool = False,
) -> Tuple[bool, str]:
    min_len = int(min_len if min_len is not None else settings.MIN_TITLE_LENGTH)
    max_len = int(max_len if max_len is not None else settings.MAX_TITLE_LENGTH)

    if not title or not isinstance(title, str):
        return False, "Пустое название"

    title = _norm_space(title)
    if not title:
        return False, "Пустое название"

    if len(title) < min_len:
        return (
            False,
            f"Слишком короткое ({len(title)} символов, нужно {min_len}-{max_len})",
        )
    if len(title) > max_len:
        return (
            False,
            f"Слишком длинное ({len(title)} символов, нужно {min_len}-{max_len})",
        )

    if "\n" in title or "\r" in title:
        return False, "Название должно быть в одну строку"
    if re.search(r"\b(?:https?://|www\.)", title, re.IGNORECASE):
        return False, "В названии запрещены ссылки"
    if re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", title):
        return False, "В названии запрещены email"
    if re.search(r"\+?\d[\d\-\s()]{8,}\d", title):
        return False, "В названии запрещены номера телефонов"
    if not _ALLOWED_TITLE_RE.fullmatch(title):
        return False, "Недопустимые символы в названии"

    if strict_content:
        words = _tokenize(title)
        category = extract_category(card).lower()
        evidence = _collect_evidence_tokens(card)
        has_context = bool(category or evidence)
        if has_context and not _category_match(words, category):
            return False, "Название не начинается с категории товара"
        if has_context:
            facts_ok, facts_reason = check_title_facts(title, card)
            if not facts_ok:
                return False, facts_reason
            if not _has_key_model_feature(words, category, card):
                return (
                    False,
                    "Название не содержит подтверждённый ключевой признак модели",
                )

    return True, ""
