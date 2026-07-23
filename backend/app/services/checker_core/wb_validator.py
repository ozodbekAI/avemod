"""
WB Card Validator Service
Based on wbchecknew/wb_card_validator.py
Validates cards against WB catalog limits and allowed values.
Includes per-subject characteristic metadata from charcs/ and validation/ files.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from app.core.config import get_settings


_RISKY_FUZZY_ALLOWED_FIELDS = {
    "фактура материала",
    "декоративные элементы",
    "комплектация",
    "особенности модели",
    "силуэт",
    "покрой",
    "тип верха",
    "тип низа",
    "модель брюк",
    "модель юбки",
    "модель костюма",
    "тип карманов",
}


def _as_list(v: Any) -> List[Any]:
    """Convert value to list"""
    if v is None:
        return []
    if isinstance(v, list):
        return v
    return [v]


def _norm(s: str) -> str:
    """Normalize string for comparison"""
    return " ".join((s or "").strip().lower().split())


def _char_key(char_name: Any) -> str:
    raw = str(char_name or "").strip()
    normalized = _norm(raw)
    if normalized.startswith("characteristics."):
        normalized = normalized.split("characteristics.", 1)[1].strip()
    return normalized


def _card_char_values(card: Optional[Dict[str, Any]], field_name: str) -> List[str]:
    if not card:
        return []
    target = _char_key(field_name)
    chars = card.get("characteristics") if isinstance(card, dict) else None
    values: List[str] = []
    if isinstance(chars, dict):
        raw = None
        for key, value in chars.items():
            if _char_key(key) == target:
                raw = value
                break
        values.extend(str(item) for item in _as_list(raw) if str(item).strip())
    elif isinstance(chars, list):
        for item in chars:
            if not isinstance(item, dict):
                continue
            if _char_key(item.get("name")) != target:
                continue
            raw = item.get("value", item.get("values"))
            values.extend(str(item) for item in _as_list(raw) if str(item).strip())
    return values


def is_no_touch_characteristic(
    char_name: Any, card: Optional[Dict[str, Any]] = None
) -> bool:
    """Fields that checker must never validate, AI-fix, filter, or suggest."""
    try:
        return get_catalog().is_no_touch_characteristic(char_name, card=card)
    except Exception:
        return False


def is_fixed_file_only_characteristic(char_name: Any) -> bool:
    """Fields whose values must come from fixed-file/manual data, not AI fixes."""
    try:
        return get_catalog().is_fixed_file_only_characteristic(char_name)
    except Exception:
        return False


def _allows_fuzzy_catalog_match(char_name: str) -> bool:
    return _norm(char_name) not in _RISKY_FUZZY_ALLOWED_FIELDS


def _similarity(a: str, b: str) -> float:
    """Fuzzy string similarity ratio (0..1)"""
    return SequenceMatcher(None, _norm(a), _norm(b)).ratio()


def find_best_match(
    value: str, allowed: List[str], threshold: float = 0.72
) -> Optional[str]:
    """
    Find the best matching allowed value for a given value.
    Returns the exact allowed-list string, or None if no match above threshold.
    """
    if not allowed:
        return None
    nv = _norm(value)
    # 1) Exact match (case-insensitive)
    for av in allowed:
        if _norm(av) == nv:
            return av
    # 2) Best fuzzy match
    best_val: Optional[str] = None
    best_score = 0.0
    for av in allowed:
        score = _similarity(value, av)
        if score > best_score:
            best_score = score
            best_val = av
    if best_score >= threshold and best_val is not None:
        return best_val
    return None


@dataclass
class CharMetadata:
    """Metadata for a single characteristic from charcs/{subjectID}.json"""

    charc_id: int
    name: str
    required: bool = False
    unit_name: str = ""
    max_count: int = 0
    popular: bool = False
    charc_type: int = 1  # 0=system, 1=string, 4=number
    is_fixed: bool = False
    is_conditional: bool = False
    condition: Dict[str, Any] = field(default_factory=dict)
    note: str = ""


class DataCatalog:
    """WB Data Catalog - loads limits/allowed values/metadata from extracted folder."""

    def __init__(self, data_path: Union[str, Path]):
        self.data_path = Path(data_path)
        if not self.data_path.is_dir():
            raise FileNotFoundError(f"WB data directory not found: {self.data_path}")

        # Limits by characteristic name
        self.limits_by_name: Dict[str, Dict[str, int]] = {}

        # Allowed values by characteristic name
        self.sprav_by_name: Dict[str, List[str]] = {}

        # SEO keywords by subject name (category)
        self.keywords_by_subject: Dict[str, List[str]] = {}

        # Color values
        self.colors_allowed: Set[str] = set()
        self.colors_allowed_list: List[str] = []
        # Color hierarchy: parent -> shades and shade -> parent
        self.color_parent_to_children: Dict[str, List[str]] = {}
        self.color_value_to_parent: Dict[str, str] = {}
        self.color_parents: List[str] = []
        # Frequency stats from cards_raw (for better "closest shades" ordering)
        self.color_freq: Dict[str, int] = {}
        self.color_parent_freq: Dict[str, int] = {}

        # Per-subject characteristic metadata: subject_id -> list of CharMetadata
        self._charcs_cache: Dict[int, List[CharMetadata]] = {}

        # Per-subject validation rules: subject_id -> {charc_id_str: rule_dict}
        self._validation_cache: Dict[int, Dict[str, Dict]] = {}

        # Set of available subject IDs in the data source
        self._available_subjects: Set[int] = set()

        # Checker scope metadata derived from charcs/*.json.
        self.no_touch_names: Set[str] = set()
        self.fixed_file_only_names: Set[str] = set()
        self.conditional_fill_rules: Dict[str, Dict[str, Any]] = {}

        self._load_limits()
        self._load_sprav()
        self._load_colors()
        self._load_cards_raw_color_stats()
        self._load_keywords()
        self._load_checker_scope_rules()
        self._scan_available_subjects()

    def close(self) -> None:
        """No-op: filesystem mode has nothing to close."""
        return None

    def _read_json(self, inner_path: str) -> Any:
        """Read JSON from extracted data directory."""
        rel_path = inner_path[5:] if inner_path.startswith("data/") else inner_path
        fs_path = self.data_path / rel_path
        with fs_path.open("r", encoding="utf-8") as f:
            return json.load(f)

    def _scan_available_subjects(self) -> None:
        """Scan charcs/ folder to know which subject IDs are available."""
        charcs_dir = self.data_path / "charcs"
        if not charcs_dir.is_dir():
            return
        for fp in charcs_dir.glob("*.json"):
            try:
                self._available_subjects.add(int(fp.stem))
            except ValueError:
                continue

    def _load_limits(self) -> None:
        """Load characteristic limits"""
        try:
            data = self._read_json("data/Справочник лимитов.json")
            if isinstance(data, dict):
                self.limits_by_name = data
        except KeyError:
            self.limits_by_name = {}

    def _load_keywords(self) -> None:
        """Load SEO keywords by subject/category from Ключевые_слова.json"""
        try:
            data = self._read_json("data/Ключевые_слова.json")
            if isinstance(data, dict):
                self.keywords_by_subject = {
                    k.lower(): v for k, v in data.items() if isinstance(v, list)
                }
        except KeyError:
            self.keywords_by_subject = {}

    def _load_sprav(self) -> None:
        """Load generation/allowed values used by AI and UI suggestions."""
        merged: Dict[str, List[str]] = {}

        for inner_path in (
            "data/Справочник генерация.json",
            "data/Ключевые_слова.json",
        ):
            try:
                d = self._read_json(inner_path)
            except KeyError:
                d = None
            if isinstance(d, dict):
                for name, arr in d.items():
                    if name not in merged:
                        merged[name] = []
                    if isinstance(arr, list):
                        merged[name].extend([str(x) for x in arr if x])

        # Dedupe and clean
        cleaned: Dict[str, List[str]] = {}
        for nm, vals in merged.items():
            seen = set()
            out = []
            for v in vals:
                nv = _norm(v)
                if nv and nv not in seen:
                    seen.add(nv)
                    out.append(v)
            cleaned[nm] = out

        self.sprav_by_name = cleaned

    def _load_checker_scope_rules(self) -> None:
        """Load skip/fixed-file-only scope from charcs/*.json metadata."""
        charcs_dir = self.data_path / "charcs"
        if not charcs_dir.is_dir():
            return
        for fp in charcs_dir.glob("*.json"):
            try:
                data = self._read_json(f"data/charcs/{fp.name}")
            except Exception:
                continue
            items = data.get("characteristics") if isinstance(data, dict) else None
            if not isinstance(items, list):
                continue
            for item in items:
                if not isinstance(item, dict):
                    continue
                name = str(item.get("name") or "").strip()
                key = _char_key(name)
                if not key:
                    continue
                condition = (
                    item.get("condition")
                    if isinstance(item.get("condition"), dict)
                    else {}
                )
                action = str(condition.get("action") or "").strip().lower()
                if item.get("is_fixed"):
                    self.fixed_file_only_names.add(key)
                if action == "skip":
                    self.no_touch_names.add(key)
                elif (
                    action == "fill"
                    and condition.get("field")
                    and condition.get("values")
                ):
                    self.conditional_fill_rules.setdefault(key, condition)

    def _load_colors(self) -> None:
        """Load color names"""
        try:
            d = self._read_json("data/color_names.json")
        except KeyError:
            self.colors_allowed = set()
            self.colors_allowed_list = []
            return

        items = None
        if isinstance(d, dict):
            items = d.get("data")
        if not isinstance(items, list):
            self.colors_allowed = set()
            self.colors_allowed_list = []
            return

        vals: List[str] = []
        parent_to_children: Dict[str, Set[str]] = {}
        value_to_parent: Dict[str, str] = {}
        parents_set: Set[str] = set()
        for it in items:
            if not isinstance(it, dict):
                continue
            nm = it.get("name")
            parent = it.get("parentName")
            if isinstance(nm, str) and nm.strip():
                nm_s = nm.strip()
                vals.append(nm_s)
            else:
                nm_s = ""
            if isinstance(parent, str) and parent.strip():
                parent_s = parent.strip()
                vals.append(parent_s)
                parents_set.add(parent_s)
                if nm_s:
                    parent_to_children.setdefault(parent_s, set()).add(nm_s)
                    value_to_parent[_norm(nm_s)] = parent_s
                    value_to_parent[_norm(parent_s)] = parent_s

        # Dedupe
        seen = set()
        out = []
        for v in vals:
            nv = _norm(v)
            if not nv or nv in seen:
                continue
            seen.add(nv)
            out.append(v)
        out_sorted = sorted(out, key=lambda x: _norm(x))

        self.colors_allowed = set(_norm(x) for x in out_sorted)
        self.colors_allowed_list = out_sorted
        self.color_parent_to_children = {
            p: sorted(children, key=lambda x: _norm(x))
            for p, children in parent_to_children.items()
        }
        self.color_value_to_parent = value_to_parent
        self.color_parents = sorted(list(parents_set), key=lambda x: _norm(x))

    def _load_cards_raw_color_stats(self) -> None:
        """Load color frequencies from cards_raw to rank closest shades inside parent groups."""
        try:
            cards = self._read_json("data/cards_raw.json")
        except KeyError:
            self.color_freq = {}
            self.color_parent_freq = {}
            return
        if not isinstance(cards, list):
            self.color_freq = {}
            self.color_parent_freq = {}
            return

        color_freq: Dict[str, int] = {}
        parent_freq: Dict[str, int] = {}

        for card in cards:
            if not isinstance(card, dict):
                continue
            chars = card.get("characteristics") or []
            if not isinstance(chars, list):
                continue

            for ch in chars:
                if not isinstance(ch, dict):
                    continue
                name = str(ch.get("name") or "").strip().lower()
                if "цвет" not in name:
                    continue

                vals = ch.get("value")
                if vals is None:
                    vals = ch.get("values")
                vals_l = vals if isinstance(vals, list) else _as_list(vals)
                for v in vals_l:
                    if not isinstance(v, str) or not v.strip():
                        continue
                    c = v.strip()
                    color_freq[c] = color_freq.get(c, 0) + 1
                    parent = self.get_color_parent(c)
                    if parent:
                        parent_freq[parent] = parent_freq.get(parent, 0) + 1

        self.color_freq = color_freq
        self.color_parent_freq = parent_freq

    # ── Per-subject metadata ────────────────────────────

    def get_subject_chars(self, subject_id: int) -> List[CharMetadata]:
        """
        Get characteristic metadata for a subject.
        Loads from charcs/{subjectID}.json on first call, then caches.
        """
        if subject_id in self._charcs_cache:
            return self._charcs_cache[subject_id]

        if subject_id not in self._available_subjects:
            self._charcs_cache[subject_id] = []
            return []

        try:
            data = self._read_json(f"data/charcs/{subject_id}.json")
        except KeyError:
            self._charcs_cache[subject_id] = []
            return []

        chars_list: List[CharMetadata] = []
        for ch in data.get("characteristics") or []:
            cm = CharMetadata(
                charc_id=ch.get("charcID", 0),
                name=ch.get("name", ""),
                required=ch.get("required", False),
                unit_name=ch.get("unitName", ""),
                max_count=ch.get("maxCount", 0),
                popular=ch.get("popular", False),
                charc_type=ch.get("charcType", 1),
                is_fixed=ch.get("is_fixed", False),
                is_conditional=ch.get("is_conditional", False),
                condition=ch.get("condition", {}),
                note=ch.get("note", ""),
            )
            chars_list.append(cm)

        self._charcs_cache[subject_id] = chars_list
        return chars_list

    def get_char_metadata(
        self, subject_id: int, char_name: str
    ) -> Optional[CharMetadata]:
        """Find CharMetadata by name within a subject"""
        for cm in self.get_subject_chars(subject_id):
            if _norm(cm.name) == _norm(char_name):
                return cm
        return None

    def get_validation_rules(self, subject_id: int) -> Dict[str, Dict]:
        """
        Get validation rules for a subject.
        Loads from validation/{subjectID}.json on first call, then caches.
        Returns {charc_id_str: {name, type, required, maxCount, constraints}}
        """
        if subject_id in self._validation_cache:
            return self._validation_cache[subject_id]

        try:
            data = self._read_json(f"data/validation/{subject_id}.json")
        except KeyError:
            self._validation_cache[subject_id] = {}
            return {}

        rules = data.get("rules", {})
        if not isinstance(rules, dict):
            rules = {}
        self._validation_cache[subject_id] = rules
        return rules

    def is_no_touch_characteristic(
        self, char_name: Any, card: Optional[Dict[str, Any]] = None
    ) -> bool:
        key = _char_key(char_name)
        if not key:
            return False
        if key in self.no_touch_names:
            return True
        condition = self.conditional_fill_rules.get(key)
        if not condition:
            return False
        field = condition.get("field")
        allowed = [
            _norm(str(item))
            for item in _as_list(condition.get("values"))
            if str(item).strip()
        ]
        if not field or not allowed:
            return False
        actual_values = [_norm(item) for item in _card_char_values(card, str(field))]
        if not actual_values:
            return True
        return not any(
            actual == allowed_value
            for actual in actual_values
            for allowed_value in allowed
        )

    def is_fixed_file_only_characteristic(self, char_name: Any) -> bool:
        return _char_key(char_name) in self.fixed_file_only_names

    def should_skip_char(
        self, subject_id: int, char_name: str, card: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Check if a characteristic should be skipped (is_fixed or condition.action=skip)"""
        if self.is_no_touch_characteristic(char_name, card=card):
            return True
        cm = self.get_char_metadata(subject_id, char_name)
        if cm is None:
            return False
        if cm.is_fixed:
            return True
        if cm.is_conditional and cm.condition.get("action") == "skip":
            return True
        if cm.is_conditional and cm.condition.get("action") == "fill":
            return self.is_no_touch_characteristic(char_name, card=card)
        return False

    # ── Core lookups ──────────────────────────────────

    def get_limits(self, char_name: str) -> Optional[Dict[str, int]]:
        """Get min/max limits for characteristic"""
        return self.limits_by_name.get(char_name)

    def get_allowed_values(self, char_name: str) -> Optional[List[str]]:
        """Get allowed values for characteristic"""
        if _norm(char_name) == "цвет":
            return self.colors_allowed_list or None
        exact = self.sprav_by_name.get(char_name)
        if exact is not None:
            return exact
        key = _char_key(char_name)
        for name, values in self.sprav_by_name.items():
            if _char_key(name) == key:
                return values
        return None

    def get_keywords_for_subject(self, subject_name: str) -> List[str]:
        """Get SEO keywords for a subject/category name"""
        if not subject_name:
            return []
        return self.keywords_by_subject.get(subject_name.lower(), [])

    def get_color_parent_names(self) -> List[str]:
        """Return normalized parent color names (compact list for AI selection)."""
        return list(self.color_parents)

    def get_color_parent(self, value: str) -> Optional[str]:
        """Resolve color shade/parent to parent color."""
        if not value:
            return None
        nv = _norm(value)
        parent = self.color_value_to_parent.get(nv)
        if parent:
            return parent
        # Fallback: try fuzzy against known parent names
        best_parent = find_best_match(value, self.color_parents, threshold=0.78)
        if best_parent:
            return best_parent
        return None

    def suggest_related_colors(
        self,
        selected_parent_or_color: str,
        seed_colors: Optional[List[str]] = None,
        total_count: int = 4,
    ) -> List[str]:
        """
        Build final color palette:
        1) select parent
        2) return main color + closest 3/4 shades from that parent
        """
        parent = (
            self.get_color_parent(selected_parent_or_color)
            or (selected_parent_or_color or "").strip()
        )
        if not parent:
            return []

        children = list(self.color_parent_to_children.get(parent, []))
        if not children:
            # Parent exists but no children known -> fallback to parent only
            return [parent]

        seeds = [
            s.strip() for s in (seed_colors or []) if isinstance(s, str) and s.strip()
        ]

        # Main color:
        # - if selected is already a child from this parent, keep it main
        # - otherwise choose best child by seed similarity + frequency
        selected_norm = _norm(selected_parent_or_color or "")
        main_color = None
        for ch in children:
            if _norm(ch) == selected_norm:
                main_color = ch
                break
        if main_color is None:
            scored_main: List[Tuple[float, str]] = []
            for ch in children:
                sim = 0.0
                if seeds:
                    sim = max(_similarity(ch, s) for s in seeds)
                freq = self.color_freq.get(ch, 0)
                score = (sim * 3.0) + (math.log1p(freq) * 0.2)
                scored_main.append((score, ch))
            scored_main.sort(key=lambda x: (-x[0], _norm(x[1])))
            main_color = scored_main[0][1] if scored_main else children[0]

        # Other close colors within parent
        scored: List[Tuple[float, str]] = []
        for ch in children:
            if _norm(ch) == _norm(main_color):
                continue
            sim_to_main = _similarity(ch, main_color)
            sim_to_seed = max((_similarity(ch, s) for s in seeds), default=0.0)
            freq = self.color_freq.get(ch, 0)
            score = (sim_to_main * 2.5) + (sim_to_seed * 1.5) + (math.log1p(freq) * 0.2)
            scored.append((score, ch))
        scored.sort(key=lambda x: (-x[0], _norm(x[1])))

        n = max(3, min(int(total_count or 4), 5))
        out = [main_color]
        for _, ch in scored:
            if len(out) >= n:
                break
            out.append(ch)

        return out

    def is_allowed(self, char_name: str, value: str) -> bool:
        """Check if value is allowed"""
        if _norm(char_name) == "цвет":
            return _norm(value) in self.colors_allowed
        allowed = self.get_allowed_values(char_name) or []
        allowed_norm = {_norm(x) for x in allowed}
        return _norm(value) in allowed_norm

    # ── Auto-fix helpers ──────────────────────────────

    def auto_fix_allowed_value(
        self, char_name: str, invalid_value: str
    ) -> Optional[str]:
        """
        Try to auto-fix an invalid value by finding the closest match in allowed values.
        Returns the corrected value from the allowed list, or None if no good match.
        """
        allowed = self.get_allowed_values(char_name) or []
        if not allowed:
            return None
        return find_best_match(invalid_value, allowed, threshold=0.72)

    def auto_fix_limit_violation(
        self,
        char_name: str,
        current_values: List[str],
        min_count: int,
        max_count: int,
    ) -> Optional[List[str]]:
        """
        Try to auto-fix a limit violation.
        - Too many values → trim to max_count (keep first N)
        - Too few values → suggest from allowed values to fill to min_count
        Returns the fixed list, or None if can't auto-fix.
        """
        count = len(current_values)
        if count > max_count > 0:
            # Trim to max
            return current_values[:max_count]
        if count < min_count:
            # Try to add from allowed values
            allowed = self.get_allowed_values(char_name) or []
            if not allowed:
                return None
            existing_norm = {_norm(v) for v in current_values}
            extras = [v for v in allowed if _norm(v) not in existing_norm]
            needed = min_count - count
            if len(extras) >= needed:
                return current_values + extras[:needed]
        return None


@dataclass
class ErrorReason:
    """Single error reason"""

    type: str  # "limit" | "allowed_values"
    message: str
    # For limit errors:
    min: Optional[int] = None
    max: Optional[int] = None
    actual: Optional[int] = None
    over_limit: Optional[bool] = None  # True=exceeded max, False=below min
    # For allowed_values errors:
    invalidValues: Optional[List[str]] = None
    exampleValues: Optional[List[str]] = None


@dataclass
class ValidationIssue:
    """Validation issue for a characteristic"""

    charcId: Optional[int]
    name: str
    value: Any
    message: str
    severity: str  # "critical" | "error" | "warning"
    category: str  # "limit" | "allowed_values" | "fixed_field" | etc.
    errors: List[ErrorReason]
    allowed_values: Optional[List[str]] = None
    suggested_value: Optional[Any] = None  # Auto-fix suggestion
    auto_fixed: bool = False  # True if auto-fix is confident
    is_fixed_field: bool = False  # True if this is a WB fixed/system field


class CardValidator:
    """Validates WB cards against catalog rules"""

    def __init__(self, catalog: DataCatalog):
        self.catalog = catalog

    # Characteristics that exist in almost all clothing categories — skip "wrong_category" check
    _UNIVERSAL_CHAR_NAMES: Set[str] = {
        "состав",
        "цвет",
        "страна производства",
        "бренд",
        "sku",
        "баркод",
        "артикул ozon",
        "тнвэд",
        "икпу",
        "ставка ндс",
        "код упаковки",
        "номер декларации соответствия",
        "номер сертификата соответствия",
        "дата регистрации сертификата/декларации",
        "дата окончания действия сертификата/декларации",
        "коллекция",
        "рос. размер",
        "размер",
        # Common clothing fields that appear in many (but not all) categories
        "пол",
        "комплектация",
        "рост модели на фото",
        "размер на модели",
        "тип ростовки",
        "особенности модели",
        "назначение",
        "уход за вещами",
        "декоративные элементы",
        "рисунок",
        "фактура материала",
        "параметры модели на фото (ог-от-об)",
        "параметры модели на фото",
    }

    def validate_card(
        self,
        card: Dict[str, Any],
        subject_id: Optional[int] = None,
    ) -> List[ValidationIssue]:
        """Validate a card and return list of issues"""
        out: List[ValidationIssue] = []
        chars = card.get("characteristics") or []
        sid = subject_id or card.get("subjectID") or card.get("subject_id")
        if isinstance(sid, str) and sid.isdigit():
            sid = int(sid)

        # Build set of valid characteristic names for this subject (for wrong_category check)
        valid_char_names: Optional[Set[str]] = None
        subject_chars_list: List[CharMetadata] = []
        if sid:
            subject_chars = self.catalog.get_subject_chars(sid)
            if subject_chars:
                valid_char_names = {_norm(cm.name) for cm in subject_chars}
                subject_chars_list = subject_chars

        # ── Check REQUIRED characteristics that are EMPTY ──────────────────
        if subject_chars_list:
            filled_names = set()
            for ch in chars:
                raw_value = ch.get("value")
                values = _as_list(raw_value)
                if values and not all(str(v).strip() == "" for v in values):
                    filled_names.add(_norm(str(ch.get("name") or "").strip()))
            for cm in subject_chars_list:
                if sid and self.catalog.should_skip_char(sid, cm.name, card):
                    continue
                if cm.required and _norm(cm.name) not in filled_names:
                    # Limit allowed values for response (same as _validate_one_characteristic)
                    _raw_av = self.catalog.get_allowed_values(cm.name)
                    if _raw_av:
                        if _norm(cm.name) == "цвет":
                            _av = self.catalog.get_color_parent_names()
                        else:
                            _av = _raw_av
                    else:
                        _av = None

                    out.append(
                        ValidationIssue(
                            charcId=cm.charc_id,
                            name=cm.name,
                            value=None,
                            message=f"Обязательная характеристика «{cm.name}» не заполнена. Без неё товар не попадёт в фильтры WB.",
                            severity="critical",
                            category="qualification",
                            errors=[
                                ErrorReason(
                                    type="missing_required",
                                    message=f"Характеристика '{cm.name}' является обязательной для категории товара.",
                                )
                            ],
                            allowed_values=_av,
                            suggested_value=None,
                            auto_fixed=False,
                            is_fixed_field=False,
                        )
                    )

        for ch in chars:
            char_name = str(ch.get("name") or "").strip()
            char_id = ch.get("id")
            raw_value = ch.get("value")
            values = _as_list(raw_value)

            if is_no_touch_characteristic(char_name, card):
                continue

            # Skip if no value (empty)
            if not values or all(str(v).strip() == "" for v in values):
                continue

            # Fixed/system fields are controlled by fixed-file checks, not by AI/catalog suggestions.
            if sid:
                char_meta = self.catalog.get_char_metadata(sid, char_name)
                if char_meta and char_meta.is_fixed:
                    continue

            # Skip characteristics marked as action=skip in charcs metadata
            if sid and self.catalog.should_skip_char(sid, char_name, card):
                continue

            # Check if characteristic belongs to this category at all
            if valid_char_names is not None:
                char_name_norm = _norm(char_name)
                if (
                    char_name_norm not in valid_char_names
                    and char_name_norm not in self._UNIVERSAL_CHAR_NAMES
                ):
                    out.append(
                        ValidationIssue(
                            charcId=int(char_id)
                            if isinstance(char_id, (int, str))
                            and str(char_id).isdigit()
                            else None,
                            name=char_name,
                            value=raw_value,
                            message=(
                                f"Характеристика '{char_name}' не предусмотрена для категории "
                                f"'{card.get('subjectName', '')}' и должна быть удалена"
                            ),
                            severity="warning",
                            category="wrong_category",
                            errors=[
                                ErrorReason(
                                    type="wrong_category",
                                    message=(
                                        "Эта характеристика не входит в список допустимых "
                                        "характеристик для данной категории товара"
                                    ),
                                )
                            ],
                            allowed_values=None,
                            suggested_value="__CLEAR__",
                            auto_fixed=False,
                            is_fixed_field=False,
                        )
                    )
                    continue

            issue = self._validate_one_characteristic(ch)
            if issue is not None:
                out.append(issue)

        return out

    def _validate_one_characteristic(
        self, ch: Dict[str, Any]
    ) -> Optional[ValidationIssue]:
        """Validate single characteristic and try to auto-fix"""
        char_id = ch.get("id")
        char_name = str(ch.get("name") or "").strip()
        raw_value = ch.get("value")
        values = _as_list(raw_value)

        if _char_key(char_name) in self.catalog.no_touch_names:
            return None

        reasons: List[ErrorReason] = []
        allowed_values: Optional[List[str]] = None
        suggested_value: Optional[Any] = None
        auto_fixed = False
        review_only_field = _norm(char_name) in {"фактура материала"}

        # 1) Check limits
        lim = self.catalog.get_limits(char_name)
        if lim:
            min_v = lim.get("min", 0)
            max_v = lim.get("max", 999)
            actual = len(values)
            if actual < min_v or actual > max_v:
                over = actual > max_v
                reasons.append(
                    ErrorReason(
                        type="limit",
                        message=f"Количество значений ({actual}) {'превышает максимум' if over else 'меньше минимума'} ({min_v}-{max_v})",
                        min=min_v,
                        max=max_v,
                        actual=actual,
                        over_limit=over,
                    )
                )
                # Try auto-fix limit (skip for color fields — AI handles palette)
                is_color_char = "цвет" in char_name.lower()
                if not is_color_char and not review_only_field:
                    fixed_list = self.catalog.auto_fix_limit_violation(
                        char_name,
                        [str(v) for v in values],
                        min_v,
                        max_v,
                    )
                    if fixed_list is not None:
                        suggested_value = (
                            fixed_list if len(fixed_list) > 1 else fixed_list[0]
                        )
                        auto_fixed = True

        # 2) Check allowed values
        allowed = self.catalog.get_allowed_values(char_name)
        if allowed:
            fuzzy_allowed = _allows_fuzzy_catalog_match(char_name)
            if _norm(char_name) == "цвет":
                # For AI/UI keep compact parent-color list, not hundreds of shades.
                allowed_values = self.catalog.get_color_parent_names()
            else:
                allowed_values = allowed
            allowed_norm = {_norm(x) for x in allowed}
            invalid = [v for v in values if _norm(str(v)) not in allowed_norm]
            if invalid:
                reasons.append(
                    ErrorReason(
                        type="allowed_values",
                        message=f"Недопустимые значения: {', '.join(str(x) for x in invalid[:5])}",
                        invalidValues=invalid[:10],
                        exampleValues=allowed[:10],
                    )
                )
                # Try auto-fix: find closest match for each invalid value
                fixed_values = list(values)  # copy
                all_matched = True
                for i, v in enumerate(fixed_values):
                    if _norm(str(v)) not in allowed_norm:
                        match = (
                            self.catalog.auto_fix_allowed_value(char_name, str(v))
                            if fuzzy_allowed
                            else None
                        )
                        if match:
                            fixed_values[i] = match
                        else:
                            all_matched = False
                if all_matched and not review_only_field:
                    # All invalid values have matches
                    if len(fixed_values) == 1:
                        suggested_value = fixed_values[0]
                    else:
                        suggested_value = fixed_values
                    auto_fixed = True
                elif not auto_fixed:
                    # Partial matches — still suggest what we can
                    partial = []
                    for v in invalid:
                        match = (
                            self.catalog.auto_fix_allowed_value(char_name, str(v))
                            if fuzzy_allowed
                            else None
                        )
                        if match:
                            partial.append(f"{v} → {match}")
                    if partial:
                        suggested_value = "; ".join(partial)

        if not reasons:
            return None

        # Severity logic:
        # - missing_required = critical (blokiruet filtry)
        # - limit/allowed_values = warning (mozhno ispravit')
        has_missing_required = any(r.type == "missing_required" for r in reasons)
        severity = "critical" if has_missing_required else "warning"

        # Build message
        parts = []
        limit_reasons = [r for r in reasons if r.type == "limit"]
        if limit_reasons:
            lr = limit_reasons[0]
            if getattr(lr, "over_limit", True):
                parts.append("превышен лимит")
            else:
                parts.append("недостаточно значений")
        if any(r.type == "allowed_values" for r in reasons):
            parts.append("недопустимые значения")
        msg = f"Характеристика '{char_name}': {' + '.join(parts)}"

        # Determine category
        categories = [r.type for r in reasons]
        category = "+".join(sorted(set(categories)))

        return ValidationIssue(
            charcId=int(char_id)
            if isinstance(char_id, (int, str)) and str(char_id).isdigit()
            else None,
            name=char_name,
            value=raw_value,
            message=msg,
            severity=severity,
            category=category,
            errors=reasons,
            allowed_values=allowed_values,
            suggested_value=suggested_value,
            auto_fixed=auto_fixed,
        )


# Singleton catalog instance
_catalog: Optional[DataCatalog] = None


def _resolve_data_path(raw_path: str | Path) -> Path:
    path = Path(raw_path)
    if path.is_absolute() or path.is_dir():
        return path
    backend_root = Path(__file__).resolve().parents[3]
    for candidate in (
        Path.cwd() / path,
        backend_root / path,
        backend_root.parent / path,
    ):
        if candidate.is_dir():
            return candidate
    return path


def get_catalog() -> DataCatalog:
    """Get or create catalog instance"""
    global _catalog
    if _catalog is None:
        _catalog = DataCatalog(_resolve_data_path(get_settings().wb_checker_data_path))
    return _catalog


def get_validator() -> CardValidator:
    """Get validator instance"""
    return CardValidator(get_catalog())


def validate_card_characteristics(card: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Validate card characteristics against WB catalog.
    Returns list of issues with allowed_values and auto-fix suggestions.
    """
    validator = get_validator()
    subject_id = card.get("subjectID") or card.get("subject_id")
    issues = validator.validate_card(card, subject_id=subject_id)

    result = []
    for issue in issues:
        errors = [
            {
                "type": e.type,
                "message": e.message,
                "min": e.min,
                "max": e.max,
                "actual": e.actual,
                "invalidValues": e.invalidValues,
                "exampleValues": e.exampleValues,
            }
            for e in issue.errors
        ]
        # For wrong_category: inject fix_action=clear so frontend shows "clear" UI
        if issue.category == "wrong_category":
            errors.append({"type": "fix_action", "fix_action": "clear"})
        result.append(
            {
                "charc_id": issue.charcId,
                "name": issue.name,
                "value": issue.value,
                "message": issue.message,
                "severity": issue.severity,
                "category": issue.category,
                "errors": errors,
                "allowed_values": issue.allowed_values,
                "suggested_value": issue.suggested_value,
                "auto_fixed": issue.auto_fixed,
                "is_fixed_field": issue.is_fixed_field,
            }
        )
    return result


def calculate_card_fcs(card: Dict[str, Any]) -> Dict[str, Any]:
    """
    Feature Completeness Score (FCS) — spec 1.3.13.
    Returns dict with fcs (0-100), required_filled, required_total,
    popular_filled, popular_total, interpretation.
    """
    catalog = get_catalog()
    subject_id = card.get("subjectID") or card.get("subject_id")
    if isinstance(subject_id, str) and str(subject_id).isdigit():
        subject_id = int(subject_id)

    if not subject_id:
        return {
            "fcs": 0,
            "required_filled": 0,
            "required_total": 0,
            "popular_filled": 0,
            "popular_total": 0,
            "interpretation": "Категория не определена",
        }

    subject_chars = catalog.get_subject_chars(subject_id)
    if not subject_chars:
        return {
            "fcs": 0,
            "required_filled": 0,
            "required_total": 0,
            "popular_filled": 0,
            "popular_total": 0,
            "interpretation": "Нет данных по категории",
        }

    # Build set of filled characteristic names
    filled_names: set = set()
    chars = card.get("characteristics") or []
    for ch in chars if isinstance(chars, list) else []:
        raw_value = ch.get("value")
        values = _as_list(raw_value)
        if values and not all(str(v).strip() == "" for v in values):
            filled_names.add(_norm(str(ch.get("name") or "").strip()))

    req_chars = [c for c in subject_chars if c.required and not c.is_fixed]
    pop_chars = [
        c for c in subject_chars if c.popular and not c.required and not c.is_fixed
    ]

    req_total = len(req_chars)
    req_filled = sum(1 for c in req_chars if _norm(c.name) in filled_names)
    pop_total = len(pop_chars)
    pop_filled = sum(1 for c in pop_chars if _norm(c.name) in filled_names)

    # FCS = 70% required + 30% popular
    req_score = (req_filled / req_total * 70.0) if req_total > 0 else 70.0
    pop_score = (pop_filled / pop_total * 30.0) if pop_total > 0 else 30.0
    fcs = round(req_score + pop_score)

    if fcs < 60:
        interpretation = "Критически плохо — карточка не попадёт в фильтры"
    elif fcs < 80:
        interpretation = "Средне — заполните обязательные поля"
    elif fcs < 90:
        interpretation = "Хорошо"
    else:
        interpretation = "Отлично"

    return {
        "fcs": fcs,
        "required_filled": req_filled,
        "required_total": req_total,
        "popular_filled": pop_filled,
        "popular_total": pop_total,
        "interpretation": interpretation,
    }
