from __future__ import annotations

from typing import Any, Dict, Iterable, List, Tuple

from .title_policy import validate_title
from .text_policy import validate_description
from .vision_service import is_grounded_product_dna_audit


class _EnumValue:
    def __init__(self, value: str) -> None:
        self.value = value


class IssueCategory:
    TITLE = _EnumValue("title")
    DESCRIPTION = _EnumValue("description")
    CHARACTERISTICS = _EnumValue("characteristics")
    CATEGORY = _EnumValue("identity")


class IssueSeverity:
    CRITICAL = _EnumValue("critical")
    WARNING = _EnumValue("medium")
    IMPROVEMENT = _EnumValue("low")
    INFO = _EnumValue("info")


class IssueStatus:
    PENDING = _EnumValue("new")


CardIssue = Any

_VISUAL_RISKY_SCORE_FIELDS = {
    "фактура материала",
    "комплектация",
    "тип верха",
    "тип низа",
    "модель брюк",
    "модель юбки",
    "модель костюма",
    "тип карманов",
    "особенности модели",
    "декоративные элементы",
    "вид застежки",
}


def _as_text(v: Any) -> str:
    return "" if v is None else str(v)


def _norm(s: str) -> str:
    return " ".join((s or "").strip().lower().split())


def _safe_int(v: Any, default: int = 0) -> int:
    try:
        n = int(v)
        return n
    except (TypeError, ValueError):
        return default


def _clamp(v: float, mn: int, mx: int) -> int:
    return int(max(mn, min(mx, round(v))))


def _issue_category(issue: CardIssue) -> str:
    c = issue.category
    if hasattr(c, "value"):
        return str(c.value)
    return str(c or "")


def _issue_severity(issue: CardIssue) -> str:
    s = issue.severity
    if hasattr(s, "value"):
        return str(s.value)
    return str(s or "")


def _issue_status(issue: CardIssue) -> str:
    s = getattr(issue, "status", None)
    if hasattr(s, "value"):
        return str(s.value)
    return str(s or "")


def _is_visual_risky_issue(issue: CardIssue) -> bool:
    field_path = _norm(_as_text(getattr(issue, "field_path", "")))
    if field_path.startswith("characteristics."):
        field_path = field_path.split(".", 1)[1]
    return field_path in _VISUAL_RISKY_SCORE_FIELDS


def _severity_weight(issue: CardIssue) -> int:
    sev = _issue_severity(issue)
    if sev == IssueSeverity.CRITICAL.value:
        return 3
    if sev in {
        IssueSeverity.WARNING.value,
        IssueSeverity.IMPROVEMENT.value,
        IssueSeverity.INFO.value,
    }:
        return 2
    return 1


def _iter_characteristics(
    raw_data: Dict[str, Any], fallback: Any
) -> Iterable[Tuple[str, str]]:
    chars = raw_data.get("characteristics") if isinstance(raw_data, dict) else None
    if chars is None:
        chars = fallback or []

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


def _meaningful_tokens(text: str) -> List[str]:
    stop = {
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
    }
    out: List[str] = []
    for raw in _norm(text).replace(",", " ").replace(".", " ").split():
        token = "".join(ch for ch in raw if ch.isalnum() or ch == "-")
        if len(token) < 4:
            continue
        if token in stop:
            continue
        out.append(token)
    return out


def _title_desc_coverage(title: str, description: str) -> float:
    tks = list(dict.fromkeys(_meaningful_tokens(title)))
    if not tks:
        return 1.0
    desc_set = set(_meaningful_tokens(description))
    if not desc_set:
        return 0.0
    # Use 5-char stem matching for Russian morphological tolerance
    desc_stems = {t[:5] for t in desc_set if len(t) >= 5}
    hit = sum(1 for t in tks if t in desc_set or (len(t) >= 5 and t[:5] in desc_stems))
    return hit / max(1, len(tks))


class SuperValidatorService:
    """
    Media-less super validator:
    computes Text / Attributes / Consistency and final score.
    """

    def evaluate(
        self,
        *,
        card: Any,
        raw_data: Dict[str, Any],
        issues: List[CardIssue],
        base_breakdown: Dict[str, Any] | None = None,
        fcs: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        base = dict(base_breakdown or {})
        title = _as_text(raw_data.get("title") or getattr(card, "title", "")).strip()
        description = _as_text(
            raw_data.get("description") or getattr(card, "description", "")
        ).strip()
        card_ctx: Dict[str, Any] = {
            "title": title,
            "description": description,
            "brand": _as_text(raw_data.get("brand") or getattr(card, "brand", "")),
            "subjectName": _as_text(
                raw_data.get("subjectName") or getattr(card, "subject_name", "")
            ),
            "subject_name": _as_text(getattr(card, "subject_name", "")),
            "category_name": _as_text(getattr(card, "category_name", "")),
            "characteristics": raw_data.get("characteristics")
            or getattr(card, "characteristics", {})
            or {},
        }

        # --- Text score (title + description) ---
        title_score = 20
        desc_score = 20
        title_valid, _ = validate_title(title, card_ctx)
        desc_valid, _ = validate_description(description, card_ctx)
        if not title_valid:
            title_score -= 7
        if not desc_valid:
            desc_score -= 7

        title_pen = 0
        desc_pen = 0
        attr_pen = 0
        consistency_pen = 0
        mismatch_count = 0

        for iss in issues:
            w = _severity_weight(iss)
            cat = _issue_category(iss)
            code = _norm(_as_text(iss.code))
            path = _norm(_as_text(iss.field_path))
            text_blob = f"{code} {_norm(_as_text(iss.title))} {_norm(_as_text(iss.description))}"

            if cat == IssueCategory.TITLE.value or path == "title":
                title_pen += w
            if cat == IssueCategory.DESCRIPTION.value or path == "description":
                desc_pen += w
            if cat in (
                IssueCategory.CHARACTERISTICS.value,
                IssueCategory.CATEGORY.value,
            ):
                attr_pen += w

            if any(
                k in text_blob
                for k in ("mismatch", "contradiction", "конфликт", "несоответств")
            ):
                mismatch_count += 1
                consistency_pen += w

        title_score = _clamp(title_score - min(10, title_pen * 2), 0, 20)
        desc_score = _clamp(desc_score - min(10, desc_pen * 2), 0, 20)

        # --- Attributes score (FCS-based when available) ---
        fcs_score = (fcs or {}).get("fcs", None)
        if fcs_score is not None:
            # Use FCS directly: convert 0-100 → 0-20 band, then penalise issues
            completeness_bonus = (fcs_score / 100.0) * 8.0
        else:
            required_keys = ("цвет", "размер", "материал", "состав")
            names = [
                _norm(k)
                for k, _ in _iter_characteristics(
                    raw_data, getattr(card, "characteristics", {})
                )
            ]
            required_present = sum(
                1 for req in required_keys if any(req in nm for nm in names)
            )
            completeness_bonus = (required_present / len(required_keys)) * 8.0
        characteristics_score = _clamp(
            12 + completeness_bonus - min(14, attr_pen * 2), 0, 20
        )

        # --- Consistency score (0..10, exposed as seo_score for backward compatibility) ---
        consistency_score = 10
        if not title_valid:
            consistency_score -= 1
        if not desc_valid:
            consistency_score -= 1

        coverage = _title_desc_coverage(title, description)
        if coverage < 0.5:
            consistency_score -= 3
        elif coverage < 0.7:
            consistency_score -= 1

        consistency_score -= min(5, consistency_pen + mismatch_count)
        consistency_score = _clamp(consistency_score, 0, 10)

        text_score_100 = _clamp(((title_score + desc_score) / 40) * 100, 0, 100)
        attributes_score_100 = _clamp((characteristics_score / 20) * 100, 0, 100)
        consistency_score_100 = _clamp((consistency_score / 10) * 100, 0, 100)

        final_score = _clamp(
            0.45 * text_score_100
            + 0.35 * attributes_score_100
            + 0.20 * consistency_score_100,
            0,
            100,
        )
        pending_issues = [
            issue
            for issue in issues
            if _issue_status(issue) in {"", IssueStatus.PENDING.value}
        ]
        pending_codes = {
            _norm(
                _as_text(
                    getattr(issue, "code", None) or getattr(issue, "issue_code", None)
                )
            )
            for issue in pending_issues
        }
        if "no_photos" in pending_codes:
            final_score = min(final_score, 35)
        elif "few_photos" in pending_codes:
            final_score = min(final_score, 65)
        if "add_more_photos" in pending_codes:
            final_score = min(final_score, 92)
        if "no_video" in pending_codes:
            final_score = min(final_score, 95)
        if "no_description" in pending_codes:
            final_score = min(final_score, 55)
        if "no_title" in pending_codes or "title_too_short" in pending_codes:
            final_score = min(final_score, 45)
        product_dna_audit = getattr(card, "product_dna_audit", None) or {}
        if not is_grounded_product_dna_audit(product_dna_audit) and any(
            _is_visual_risky_issue(issue) for issue in pending_issues
        ):
            final_score = min(final_score, 60)

        current_score = _safe_int(base.get("total_score"), default=final_score)
        ready_gain = sum(
            max(0, _safe_int(getattr(issue, "score_impact", 0), default=0))
            for issue in pending_issues
            if not bool(getattr(issue, "requires_human_check", False))
            and bool(
                _as_text(
                    getattr(issue, "suggested_value", None)
                    or getattr(issue, "ai_suggested_value", None)
                ).strip()
            )
        )
        potential_gain = sum(
            max(0, _safe_int(getattr(issue, "score_impact", 0), default=0))
            for issue in pending_issues
        )
        ready_score = min(100, final_score + ready_gain)
        potential_score = min(100, final_score + potential_gain)
        suggested_score = ready_score

        # Preserve legacy keys for frontend widgets.
        result = {
            "title_score": title_score,
            "description_score": desc_score,
            "characteristics_score": characteristics_score,
            "photos_score": _safe_int(base.get("photos_score"), default=0),
            "video_score": _safe_int(base.get("video_score"), default=0),
            "seo_score": consistency_score,  # compatibility key used as Cons in UI
            "total_score": final_score,
            "max_possible": 100,
            # Super-validator explicit blocks
            "text_score": text_score_100,
            "attributes_score": attributes_score_100,
            "consistency_score": consistency_score_100,
            "current_score": current_score,
            "suggested_score": suggested_score,
            "ready_score": ready_score,
            "potential_score": potential_score,
            "final_score": final_score,
            "sv_version": "media_aware_v2",
            # FCS — Feature Completeness Score (spec 1.3.13)
            "fcs": (fcs or {}).get("fcs", 0),
            "fcs_required_filled": (fcs or {}).get("required_filled", 0),
            "fcs_required_total": (fcs or {}).get("required_total", 0),
            "fcs_popular_filled": (fcs or {}).get("popular_filled", 0),
            "fcs_popular_total": (fcs or {}).get("popular_total", 0),
            "fcs_interpretation": (fcs or {}).get("interpretation", ""),
        }
        return result


super_validator_service = SuperValidatorService()
