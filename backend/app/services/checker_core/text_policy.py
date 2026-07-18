from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Tuple

from app.core.config import get_settings
from .title_policy import extract_category

settings = get_settings()

_WORD_RE = re.compile(r"[а-яёa-z0-9-]+", re.IGNORECASE)
_SENTENCE_RE = re.compile(r"[.!?]+")
_EMOJI_RE = re.compile(r"[\U0001F300-\U0001FAFF\U00002700-\U000027BF]")

FORBIDDEN_WORDS = {
    "стильный",
    "модный",
    "тренд",
    "топ",
    "хит",
    "лучший",
    "идеальный",
    "премиум",
    "люкс",
    "супер",
    "красивый",
    "элегантный",
    "роскошный",
    "безупречный",
    "шикарный",
    "великолепный",
    "уникальный",
    "стройнит",
    "самый",
}


def forbidden_description_words_text() -> str:
    return ", ".join(sorted(FORBIDDEN_WORDS))


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
}

STRUCTURAL_KEYS = (
    "силуэт",
    "фасон",
    "крой",
    "длина",
    "рукав",
    "вырез",
    "ворот",
    "застеж",
    "комплект",
    "тип",
    "посадк",
    "карман",
    "пояс",
    "подклад",
)

MATERIAL_KEYS = (
    "состав",
    "материал",
    "ткан",
    "хлоп",
    "вискоз",
    "полиэстер",
    "шерст",
    "лен",
)
PURPOSE_HINTS = (
    "назнач",
    "офис",
    "делов",
    "вечер",
    "повседнев",
    "празднич",
    "на каждый день",
    "сценари",
)
LOW_VALUE_ADMIN_PATTERNS = (
    "рост модели",
    "параметры модели",
    "размер на модели",
    "коллекция",
    "страна производства",
    "весна-лето",
    "осень-зима",
)
_COMPOSITION_NAME_KEYS = ("состав", "материал")
_COMPOSITION_EN_ALIASES = {
    "polyester": "полиэстер",
    "viscose": "вискоза",
    "rayon": "rayon",
    "nylon": "нейлон",
    "elastane": "эластан",
    "spandex": "эластан",
    "wool": "шерсть",
    "linen": "лен",
    "silk": "шелк",
    "acrylic": "акрил",
}
_COMPOSITION_RU_ALIASES = {
    "пэ": "полиэстер",
}
_KNOWN_MATERIAL_TERMS = {
    "акрил",
    "вискоза",
    "кашемир",
    "лен",
    "лайкра",
    "нейлон",
    "полиамид",
    "полиэстер",
    "спандекс",
    "хлопок",
    "шелк",
    "шерсть",
    "эластан",
}
_DESCRIPTION_FACT_DOMAIN_SPECS = {
    "fabric_type": {
        "label": "тип ткани/фактуру материала",
        "name_keys": ("фактура", "материал", "ткан"),
        "patterns": {
            "gabardine": (r"\bгабардин\w*\b",),
            "jersey": (r"\bтрикотаж\w*\b",),
            "suiting": (r"\bкостюмн\w*\b",),
            "tweed": (r"\bтвид\w*\b",),
            "lace": (r"\bкружев\w*\b",),
        },
    },
    "texture": {
        "label": "фактуру материала",
        "name_keys": ("фактура", "текстур"),
        "patterns": {
            "ribbed": (r"\b(?:в\s+)?рубчик\w*\b",),
            "smooth": (r"\bгладк\w*\b",),
            "pleated": (r"\bплисс\w*\b",),
            "lace": (r"\bкружев\w*\b",),
            "quilted": (r"\bстеган\w*\b",),
            "boucle": (r"\bбукле\b",),
        },
    },
    "neckline": {
        "label": "вырез",
        "name_keys": ("вырез", "горловин"),
        "patterns": {
            "v_neck": (r"v[- ]?образ\w*", r"\bv-neck\b"),
            "round": (r"\bкругл\w*\b",),
            "square": (r"\bквадрат\w*\b",),
            "boat": (r"\bлодочк\w*\b",),
            "stand": (r"\bстойк\w*\b",),
        },
    },
    "fit": {
        "label": "силуэт/посадку",
        "name_keys": ("силуэт", "фасон", "крой", "посадк"),
        "patterns": {
            "fitted": (r"\bпритал\w*\b",),
            "straight": (r"\bпрям\w*\b",),
            "loose": (r"\bсвободн\w*\b",),
            "oversize": (r"\bоверсайз\b",),
        },
    },
    "pockets": {
        "label": "тип карманов",
        "name_keys": ("карман",),
        "patterns": {
            "flap": (r"\bклапан\w*\b",),
            "patch": (r"\bнакладн\w*\b",),
            "side_seam": (r"\bотрезн\w*\s+бочк\w*\b", r"\bв\s+боков\w*\s+шв\w*\b"),
            "without": (r"\bбез\s+карман\w*\b",),
        },
    },
    "fastening": {
        "label": "вид застежки",
        "name_keys": ("застеж",),
        "patterns": {
            "buttons": (r"\bпугов\w*\b",),
            "zipper": (r"\bмолни\w*\b",),
            "hooks": (r"\bкрюч\w*\b",),
            "without": (r"\bбез\s+застеж\w*\b",),
        },
    },
    "skirt_model": {
        "label": "модель юбки",
        "name_keys": ("модель юбки",),
        "patterns": {
            "pencil": (r"\bкарандаш\w*\b",),
            "pleated": (r"\bплисс\w*\b",),
            "wrap": (r"\bзапах\w*\b",),
            "straight": (r"\bпрям\w*\b",),
        },
    },
    "pants_model": {
        "label": "модель брюк",
        "name_keys": ("модель брюк",),
        "patterns": {
            "palazzo": (r"\bпалаццо\b",),
            "wide": (r"\bширок\w*\b",),
            "straight": (r"\bпрям\w*\b",),
            "flare": (r"\bклеш\w*\b",),
            "cargo": (r"\bкарго\b",),
        },
    },
    "top_type": {
        "label": "тип верха",
        "name_keys": ("тип верха",),
        "patterns": {
            "jacket": (r"\bжакет\w*\b", r"\bпиджак\w*\b", r"\bблейзер\w*\b"),
            "top": (r"\bтоп\w*\b",),
            "vest": (r"\bжилет\w*\b",),
            "sweatshirt": (
                r"\bсвитшот\w*\b",
                r"\bхуди\b",
                r"\bтолстовк\w*\b",
                r"\bсвитер\w*\b",
            ),
        },
    },
    "bottom_type": {
        "label": "тип низа",
        "name_keys": ("тип низа",),
        "patterns": {
            "skirt": (r"\bюбк\w*\b",),
            "pants": (r"\bбрюк\w*\b",),
            "shorts": (r"\bшорт\w*\b",),
        },
    },
}

_DESCRIPTION_UNCONFIRMED_CLAIM_PATTERNS = {
    "дышащие свойства": (r"\bдышащ\w*\b",),
    "немнущийся эффект": (r"\bнемнущ\w*\b", r"\bне\s+требует\s+утюж\w*\b"),
    "износостойкость": (r"\bизносостойк\w*\b",),
    "тактильные свойства": (
        r"\bприятн\w*\s+тактильн\w*\b",
        r"\bгладк\w*\s+на\s+ощупь\b",
    ),
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


def _normalize_material_name(text: str) -> str:
    raw = _norm_space(str(text or "").lower().replace("ё", "е"))
    raw = raw.strip(" .,:;-—/")
    if not raw:
        return ""
    raw = re.sub(r"\s+", " ", raw)
    raw = _COMPOSITION_EN_ALIASES.get(raw, raw)
    raw = _COMPOSITION_RU_ALIASES.get(raw, raw)
    return raw


def _extract_composition_pairs(value: Any) -> List[Tuple[str, int]]:
    raw = _norm_space(str(value or ""))
    if not raw:
        return []

    normalized = raw.replace("％", "%")
    normalized = re.sub(
        r"(\d{1,3})\s*([A-Za-zА-Яа-яЁё][A-Za-zА-Яа-яЁё\s\-/]{1,30}?)\s*%",
        r"\1% \2",
        normalized,
    )

    patterns = (
        re.compile(
            r"(\d{1,3})\s*%\s*([A-Za-zА-Яа-яЁё][A-Za-zА-Яа-яЁё\s\-/]{1,30}?)(?=(?:[,;.]|\n|\s+и\s+|$))"
        ),
        re.compile(
            r"([A-Za-zА-Яа-яЁё][A-Za-zА-Яа-яЁё\s\-/]{1,30}?)\s*(\d{1,3})\s*%(?=(?:[,;.]|\n|\s+и\s+|$))"
        ),
    )

    out: List[Tuple[str, int]] = []
    seen: set[Tuple[str, int]] = set()
    for pattern in patterns:
        for match in pattern.finditer(normalized):
            if pattern is patterns[0]:
                percent = int(match.group(1))
                material = _normalize_material_name(match.group(2))
            else:
                material = _normalize_material_name(match.group(1))
                percent = int(match.group(2))
            if not material or not (0 < percent <= 100):
                continue
            key = (material, percent)
            if key in seen:
                continue
            seen.add(key)
            out.append(key)
    return out


def _extract_material_mentions(text: str) -> set[str]:
    mentions: set[str] = set()
    for token in _tokenize(text):
        normalized = _normalize_material_name(token)
        if normalized in _KNOWN_MATERIAL_TERMS:
            mentions.add(normalized)
            continue
        for material in _KNOWN_MATERIAL_TERMS:
            prefix = material[:4]
            if len(normalized) >= 4 and normalized.startswith(prefix):
                mentions.add(material)
                break
    return mentions


def _normalize_fact_text(text: str) -> str:
    return _norm_space(str(text or "").lower().replace("ё", "е"))


def _match_fact_families(text: str, patterns: Dict[str, tuple[str, ...]]) -> set[str]:
    normalized = _normalize_fact_text(text)
    if not normalized:
        return set()
    matched: set[str] = set()
    for family, family_patterns in patterns.items():
        if any(
            re.search(pattern, normalized, flags=re.IGNORECASE)
            for pattern in family_patterns
        ):
            matched.add(family)
    return matched


def _matches_any_pattern(text: str, patterns: Iterable[str]) -> bool:
    normalized = _normalize_fact_text(text)
    if not normalized:
        return False
    return any(
        re.search(pattern, normalized, flags=re.IGNORECASE) for pattern in patterns
    )


def extract_confirmed_visual_facts(card: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for name, value in _iter_characteristics(card):
        normalized_name = _normalize_fact_text(name)
        normalized_value = _norm_space(value)
        if not normalized_value:
            continue
        for domain, spec in _DESCRIPTION_FACT_DOMAIN_SPECS.items():
            if not any(key in normalized_name for key in spec["name_keys"]):
                continue
            entry = out.setdefault(
                domain, {"label": spec["label"], "raw_values": [], "families": set()}
            )
            entry["raw_values"].append(normalized_value)
            entry["families"].update(
                _match_fact_families(normalized_value, spec["patterns"])
            )
    return out


def _collect_trusted_description_source_text(card: Dict[str, Any]) -> str:
    chunks: List[str] = []
    for key in ("title", "description", "subjectName", "subject_name"):
        value = _norm_space(str(card.get(key) or ""))
        if value:
            chunks.append(value)
    for name, value in _iter_characteristics(card):
        normalized_name = _norm_space(name)
        normalized_value = _norm_space(value)
        if normalized_name:
            chunks.append(normalized_name)
        if normalized_value:
            chunks.append(normalized_value)
    return "\n".join(chunks)


def format_composition_pairs(pairs: Iterable[Tuple[str, int]]) -> str:
    chunks = [
        f"{percent}% {material}" for material, percent in pairs if material and percent
    ]
    return ", ".join(chunks)


def extract_card_composition_facts(card: Dict[str, Any]) -> List[Tuple[str, int]]:
    preferred: List[Tuple[str, int]] = []
    fallback: List[Tuple[str, int]] = []
    for name, value in _iter_characteristics(card):
        lower = name.lower()
        pairs = _extract_composition_pairs(value)
        if len(pairs) < 2:
            continue
        if "состав" in lower:
            return pairs
        if any(key in lower for key in _COMPOSITION_NAME_KEYS) and not preferred:
            preferred = pairs
        elif not fallback:
            fallback = pairs
    return preferred or fallback


def build_composition_guardrail(card: Dict[str, Any]) -> str:
    pairs = extract_card_composition_facts(card)
    return format_composition_pairs(pairs)


def build_ai_characteristics_payload(
    card: Dict[str, Any], *, limit: int = 25
) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    for idx, (name, value) in enumerate(_iter_characteristics(card)):
        if idx >= limit:
            break
        normalized_value = _norm_space(value)
        if any(key in name.lower() for key in _COMPOSITION_NAME_KEYS):
            pairs = _extract_composition_pairs(value)
            if len(pairs) >= 2:
                normalized_value = format_composition_pairs(pairs)
        if normalized_value:
            out.append({"name": name, "value": normalized_value})
    return out


def detect_description_composition_conflict(
    card: Dict[str, Any], description: str
) -> Tuple[bool, str]:
    source_pairs = extract_card_composition_facts(card)
    if len(source_pairs) < 2:
        return False, ""

    description_pairs = _extract_composition_pairs(description)
    if not description_pairs:
        return False, ""

    source_map = {percent: material for material, percent in source_pairs}
    desc_map = {percent: material for material, percent in description_pairs}

    missing = sorted(percent for percent in source_map if percent not in desc_map)
    extra = sorted(percent for percent in desc_map if percent not in source_map)
    material_mismatch = sorted(
        percent
        for percent in (set(source_map) & set(desc_map))
        if _normalize_material_name(source_map[percent])
        != _normalize_material_name(desc_map[percent])
    )

    if missing or extra or material_mismatch:
        fragments: List[str] = []
        if missing:
            fragments.append(
                "пропущены проценты: " + ", ".join(f"{p}%" for p in missing[:5])
            )
        if extra:
            fragments.append(
                "добавлены неподтвержденные проценты: "
                + ", ".join(f"{p}%" for p in extra[:5])
            )
        if material_mismatch:
            fragments.append(
                "проценты привязаны к другим материалам: "
                + ", ".join(f"{p}%" for p in material_mismatch[:5])
            )
        return True, "Описание искажает состав изделия (" + "; ".join(fragments) + ")"

    return False, ""


def extract_confirmed_material_facts(card: Dict[str, Any]) -> Dict[str, Any]:
    composition_pairs = extract_card_composition_facts(card)
    materials: List[str] = []
    material_lines: List[str] = []
    seen_materials: set[str] = set()

    for material, _percent in composition_pairs:
        normalized = _normalize_material_name(material)
        if normalized and normalized not in seen_materials:
            seen_materials.add(normalized)
            materials.append(normalized)

    for name, value in _iter_characteristics(card):
        lower_name = name.lower()
        if not any(key in lower_name for key in MATERIAL_KEYS):
            continue
        normalized_value = _norm_space(value)
        if not normalized_value:
            continue
        material_lines.append(normalized_value)
        for token in _tokenize(normalized_value):
            normalized = _normalize_material_name(token)
            if normalized in _KNOWN_MATERIAL_TERMS and normalized not in seen_materials:
                seen_materials.add(normalized)
                materials.append(normalized)

    return {
        "materials": materials,
        "composition_percentages": [
            {"material": material, "percent": percent}
            for material, percent in composition_pairs
        ],
        "material_lines": material_lines,
    }


def validate_description_facts(
    description: str,
    card: Dict[str, Any],
    *,
    allow_visual_facts: bool = False,
) -> Tuple[bool, str]:
    text = str(description or "").strip()
    if not text:
        return False, "Описание пустое"

    confirmed = extract_confirmed_material_facts(card)
    confirmed_materials = {
        _normalize_material_name(item)
        for item in (confirmed.get("materials") or [])
        if _normalize_material_name(item)
    }
    confirmed_pairs = {
        (_normalize_material_name(item.get("material")), int(item.get("percent")))
        for item in (confirmed.get("composition_percentages") or [])
        if _normalize_material_name(item.get("material"))
        and str(item.get("percent") or "").strip().isdigit()
    }

    conflict, conflict_reason = detect_description_composition_conflict(card, text)
    if conflict:
        return False, conflict_reason

    desc_pairs = {
        (_normalize_material_name(material), percent)
        for material, percent in _extract_composition_pairs(text)
        if _normalize_material_name(material)
    }
    if desc_pairs and not confirmed_pairs:
        return False, "Описание добавляет неподтверждённый состав/проценты"
    if confirmed_pairs and desc_pairs and desc_pairs != confirmed_pairs:
        return False, "Описание меняет подтверждённый состав или проценты"

    desc_materials = _extract_material_mentions(text)
    unsupported_materials = sorted(
        material
        for material in desc_materials
        if material and material not in confirmed_materials
    )
    if unsupported_materials and not allow_visual_facts:
        return False, (
            "Описание добавляет неподтверждённые материалы: "
            + ", ".join(unsupported_materials[:5])
        )

    confirmed_visual_facts = extract_confirmed_visual_facts(card)
    for domain, spec in _DESCRIPTION_FACT_DOMAIN_SPECS.items():
        claimed_families = _match_fact_families(text, spec["patterns"])
        if not claimed_families:
            continue
        confirmed_entry = confirmed_visual_facts.get(domain) or {}
        confirmed_families = set(confirmed_entry.get("families") or set())
        confirmed_raw = [
            str(item)
            for item in (confirmed_entry.get("raw_values") or [])
            if str(item).strip()
        ]
        if confirmed_families:
            if claimed_families.isdisjoint(confirmed_families):
                return False, (
                    f"Описание меняет подтверждённую характеристику «{spec['label']}»"
                    + (f" (карточка: {confirmed_raw[0]})" if confirmed_raw else "")
                )
        elif confirmed_raw:
            return False, (
                f"Описание добавляет неподтверждённую характеристику «{spec['label']}»"
                + f" (карточка: {confirmed_raw[0]})"
            )
        elif not allow_visual_facts:
            return (
                False,
                f"Описание добавляет неподтверждённую характеристику «{spec['label']}»",
            )

    trusted_source_text = _collect_trusted_description_source_text(card)
    for label, patterns in _DESCRIPTION_UNCONFIRMED_CLAIM_PATTERNS.items():
        if _matches_any_pattern(text, patterns) and not _matches_any_pattern(
            trusted_source_text, patterns
        ):
            return False, f"Описание добавляет неподтверждённое свойство «{label}»"

    return True, ""


def _paragraphs(text: str) -> List[str]:
    text = (text or "").replace("\r\n", "\n").strip()
    if not text:
        return []
    return [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]


def _has_bullets(text: str) -> bool:
    for line in (text or "").splitlines():
        ln = line.strip()
        if not ln:
            continue
        if ln.startswith(("-", "*", "•")):
            return True
        if re.match(r"^\d+[\).\:\-]\s*", ln):
            return True
    return False


def _has_forbidden_words(text: str) -> List[str]:
    words = _tokenize(text)
    bad = sorted({w for w in words if w in FORBIDDEN_WORDS})
    return bad


def _sentences_count(paragraph: str) -> int:
    c = len(_SENTENCE_RE.findall(paragraph))
    return c if c > 0 else (1 if paragraph.strip() else 0)


def _meaningful_tokens(text: str) -> List[str]:
    out = []
    for t in _tokenize(text):
        if len(t) < 4:
            continue
        if t in STOPWORDS:
            continue
        out.append(t)
    return out


def _title_keyword_coverage(title: str, description: str) -> float:
    title_tokens = list(dict.fromkeys(_meaningful_tokens(title)))
    if not title_tokens:
        return 1.0
    desc_tokens = set(_meaningful_tokens(description))
    if not desc_tokens:
        return 0.0
    # Use 5-char stem matching to handle Russian morphological variants
    desc_stems = {t[:5] for t in desc_tokens if len(t) >= 5}
    matched = sum(
        1
        for t in title_tokens
        if t in desc_tokens or (len(t) >= 5 and t[:5] in desc_stems)
    )
    return matched / max(1, len(title_tokens))


def _has_structure_requirements(
    text: str, paragraphs: List[str], card: Dict[str, Any]
) -> Tuple[bool, str]:
    if not paragraphs:
        return False, "Описание пустое"

    full_lower = text.lower()
    category = extract_category(card)
    title = str(card.get("title") or "").strip()

    # 1) Intro paragraph must reference item/category/title.
    intro = paragraphs[0].lower()
    if (
        category
        and category not in intro
        and not any(tok in intro for tok in _meaningful_tokens(title)[:3])
    ):
        return False, "Вступление не содержит категорию/название товара"

    # 2) Construction block.
    if not any(any(k in p.lower() for k in STRUCTURAL_KEYS) for p in paragraphs):
        return False, "Нет блока про конструкцию и посадку"

    # 3) Material block if material exists in characteristics.
    has_material_data = bool(_pick_by_keys(card, MATERIAL_KEYS, limit=1))
    if has_material_data and not any(k in full_lower for k in MATERIAL_KEYS):
        return False, "Не отражены материалы из характеристик"

    # 4) Purpose block.
    if not any(k in full_lower for k in PURPOSE_HINTS):
        return False, "Нет блока с назначением/сценарием использования"

    return True, ""


def normalize_generated_description(text: str) -> str:
    raw = str(text or "").strip()
    if not raw:
        return ""

    if "\\n" in raw:
        raw = raw.replace("\\r\\n", "\n").replace("\\n", "\n")

    raw = raw.replace("\r\n", "\n").replace("\r", "\n")
    raw = re.sub(r"\n{3,}", "\n\n", raw)

    if "\n\n" not in raw and len(raw) >= 900:
        sentences = re.split(r"(?<=[.!?])\s+", raw)
        chunks: List[str] = []
        current: List[str] = []
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue
            current.append(sentence)
            if len(current) >= 3:
                chunks.append(" ".join(current).strip())
                current = []
        if current:
            chunks.append(" ".join(current).strip())
        raw = "\n\n".join(chunk for chunk in chunks if chunk)

    cleaned_paragraphs: List[str] = []
    removed_any = False
    for paragraph in _paragraphs(raw):
        sentences = re.split(r"(?<=[.!?])\s+", paragraph)
        kept: List[str] = []
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue
            lower = sentence.lower()
            if any(pattern in lower for pattern in LOW_VALUE_ADMIN_PATTERNS):
                removed_any = True
                continue
            kept.append(sentence)
        if kept:
            cleaned_paragraphs.append(" ".join(kept).strip())
    if removed_any:
        candidate = "\n\n".join(cleaned_paragraphs).strip()
        if len(candidate) >= min(500, max(250, int(len(raw) * 0.65))):
            raw = candidate

    raw = re.sub(r"[ \t]+\n", "\n", raw)
    raw = re.sub(r"\n[ \t]+", "\n", raw)
    return raw.strip()


def describe_description_failures(card: Dict[str, Any]) -> Dict[str, Any]:
    description = str(card.get("description") or "").strip()
    if not description:
        return {
            "valid": True,
            "reason": "",
            "forbidden_words": [],
            "missing_blocks": [],
        }

    valid, reason = validate_description(description, card, strict_structure=True)
    missing_blocks: List[str] = []
    paragraphs = _paragraphs(description)
    if paragraphs:
        ok, structure_reason = _has_structure_requirements(
            description, paragraphs, card
        )
        if not ok:
            missing_blocks.append(structure_reason)
    return {
        "valid": valid,
        "reason": "" if valid else reason,
        "forbidden_words": _has_forbidden_words(description),
        "missing_blocks": missing_blocks,
    }


def audit_current_description(card: Dict[str, Any]) -> Tuple[bool, str]:
    failures = describe_description_failures(card)
    return bool(failures.get("valid")), str(failures.get("reason") or "")


def validate_description(
    description: str,
    card: Dict[str, Any],
    min_len: int | None = None,
    max_len: int | None = None,
    strict_structure: bool = False,
) -> Tuple[bool, str]:
    min_len = int(min_len if min_len is not None else settings.MIN_DESCRIPTION_LENGTH)
    max_len = int(
        max_len
        if max_len is not None
        else getattr(settings, "MAX_DESCRIPTION_LENGTH", 1800)
    )

    if not description or not isinstance(description, str):
        return False, "Пустое описание"

    text = description.strip()
    if not text:
        return False, "Пустое описание"

    if len(text) < min_len:
        return (
            False,
            f"Описание слишком короткое ({len(text)}, нужно {min_len}-{max_len})",
        )
    if len(text) > max_len:
        return (
            False,
            f"Описание слишком длинное ({len(text)}, нужно {min_len}-{max_len})",
        )

    if re.search(r"\b(?:https?://|www\.)", text, re.IGNORECASE):
        return False, "В описании запрещены ссылки"
    if re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", text):
        return False, "В описании запрещены email"
    if re.search(r"\+?\d[\d\-\s()]{8,}\d", text):
        return False, "В описании запрещены номера телефонов"

    if strict_structure:
        if _EMOJI_RE.search(text):
            return False, "В описании запрещены эмодзи"
        if _has_bullets(text):
            return False, "Описание должно быть без списков и маркеров"
        bad_words = _has_forbidden_words(text)
        if bad_words:
            return (
                False,
                f"В описании запрещены маркетинговые слова: {', '.join(bad_words[:5])}",
            )
        paragraphs = _paragraphs(text)
        has_context = bool(
            extract_category(card)
            or str(card.get("title") or "").strip()
            or list(_iter_characteristics(card))
        )
        if has_context:
            ok, reason = _has_structure_requirements(text, paragraphs, card)
            if not ok:
                return False, reason
        title = str(card.get("title") or "").strip()
        if title and _title_keyword_coverage(title, text) < 0.35:
            return False, "Описание слабо связано с названием товара"

        composition_conflict, composition_reason = (
            detect_description_composition_conflict(card, text)
        )
        if composition_conflict:
            return False, composition_reason

    return True, ""


def _pick_by_keys(
    card: Dict[str, Any], keys: Iterable[str], limit: int = 8
) -> List[Tuple[str, str]]:
    out: List[Tuple[str, str]] = []
    for k, v in _iter_characteristics(card):
        kk = k.lower()
        if any(key in kk for key in keys):
            out.append((k, v))
            if len(out) >= limit:
                break
    return out


def _fallback_value_list(items: List[Tuple[str, str]], limit: int = 6) -> str:
    if not items:
        return ""
    chunks = [f"{k.lower()}: {v}" for k, v in items[:limit]]
    return "; ".join(chunks)


def build_description_from_card(
    card: Dict[str, Any],
    title_hint: str | None = None,
    min_len: int | None = None,
    max_len: int | None = None,
) -> str:
    min_len = int(min_len if min_len is not None else settings.MIN_DESCRIPTION_LENGTH)
    max_len = int(
        max_len
        if max_len is not None
        else getattr(settings, "MAX_DESCRIPTION_LENGTH", 1800)
    )

    title = _norm_space(title_hint or str(card.get("title") or ""))
    category = extract_category(card)
    structural = _pick_by_keys(card, STRUCTURAL_KEYS, limit=8)
    material = _pick_by_keys(card, MATERIAL_KEYS, limit=4)
    purpose = _pick_by_keys(card, ("назнач", "стиль", "повод"), limit=3)
    attrs = list(_iter_characteristics(card))

    p1 = (
        f"{title or category.capitalize()} относится к категории «{category}» и сформирован по подтверждённым данным карточки. "
        "Описание передаёт фактические свойства изделия без маркетинговых формулировок и неподтверждённых обещаний."
    )

    struct_text = _fallback_value_list(structural)
    if struct_text:
        p2 = (
            "Конструкция и посадка сформированы по текущим параметрам карточки: "
            f"{struct_text}. Такой формат сохраняет согласованность между названием, характеристиками и визуальным представлением товара."
        )
    else:
        p2 = (
            "Конструкция и посадка описываются через подтверждённые параметры из карточки. "
            "Приоритет отдан фасону, длине, типу рукава, вырезу и элементам кроя, если эти параметры заполнены в характеристиках."
        )

    normalized_composition = build_composition_guardrail(card)
    mat_text = normalized_composition or _fallback_value_list(material)
    if mat_text:
        p3 = (
            "Материалы и состав указываются только в рамках заполненных характеристик: "
            f"{mat_text}. Формулировки даны нейтрально и используются только в пределах подтверждённых значений."
        )
    else:
        p3 = (
            "Сведения о материалах и составе выводятся только из характеристик карточки. "
            "Если параметр не заполнен, в тексте не добавляются предположения о ткани, составе или стране производства."
        )

    purpose_text = _fallback_value_list(purpose)
    p4 = (
        f"Назначение модели определяется конструкцией и фактическими параметрами товара: {purpose_text or 'сценарии использования описаны нейтрально на основе текущих данных'}. "
        "Описание ориентировано на понятные ситуации применения и поддерживает релевантность поиска за счёт согласованности ключевых признаков."
    )

    attrs_text = _fallback_value_list(attrs, limit=7)
    p5 = (
        "Для фильтров WB и корректной индексации используются подтверждённые параметры карточки: "
        f"{attrs_text or 'основные характеристики изделия'}. "
        "Перед публикацией рекомендуется сверить заполнение полей и медиаконтент на отсутствие противоречий. "
        "Уход и эксплуатация должны соответствовать указанным характеристикам и не выходить за пределы подтверждённых данных."
    )

    paragraphs = [_norm_space(p) for p in (p1, p2, p3, p4, p5) if p.strip()]

    # Keep 3-6 paragraphs and 2-4 sentences in each.
    expansions = [
        "Текст синхронизирован с карточкой и не добавляет признаков, которых нет в характеристиках или визуальном контенте.",
        "Такой формат снижает риск противоречий при модерации и улучшает качество индексации по релевантным запросам.",
        "Все ключевые формулировки привязаны к заполненным полям карточки и отражают фактические параметры товара.",
    ]
    exp_idx = 0

    def _join_text() -> str:
        return "\n\n".join(paragraphs)

    while len(_join_text()) < min_len:
        sentence = expansions[exp_idx % len(expansions)]
        exp_idx += 1
        inserted = False
        for i in range(len(paragraphs) - 1, -1, -1):
            if _sentences_count(paragraphs[i]) < 4:
                paragraphs[i] = f"{paragraphs[i]} {sentence}"
                inserted = True
                break
        if not inserted:
            break

    text = _join_text()
    if len(text) > max_len:
        trimmed = text[:max_len]
        cut = max(trimmed.rfind(". "), trimmed.rfind("! "), trimmed.rfind("? "))
        if cut > int(max_len * 0.7):
            trimmed = trimmed[: cut + 1].strip()
        text = trimmed

    # Safety: if trim broke paragraphing, rebuild from current paragraphs and hard-cut last paragraph only.
    pars = _paragraphs(text)
    if not (3 <= len(pars) <= 6):
        text = _join_text()[:max_len].strip()

    return text
