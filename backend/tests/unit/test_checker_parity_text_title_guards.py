from __future__ import annotations

from app.services.checker_core.text_policy import (
    forbidden_description_words_text,
    normalize_generated_description,
    validate_description_facts,
)
from app.services.checker_core.title_policy import should_keep_current_title_as_safer


def _title_card() -> dict:
    return {
        "subjectName": "Костюмы",
        "title": "Костюм для офиса классический с юбкой миди",
        "characteristics": [
            {"name": "Комплектация", "value": "жакет, юбка"},
            {"name": "Стиль", "value": "офисный"},
        ],
    }


def _description_card() -> dict:
    return {
        "title": "Костюм для офиса с юбкой миди",
        "subjectName": "Костюмы",
        "characteristics": [
            {"name": "Состав", "value": "62% полиэстер, 32% вискоза, 6% эластан"},
            {"name": "Комплектация", "value": "жакет, юбка"},
            {"name": "Фактура материала", "value": "в рубчик"},
            {"name": "Вырез горловины", "value": "V-образный"},
            {"name": "Модель юбки", "value": "карандаш"},
            {"name": "Тип карманов", "value": "с клапаном, с отрезным бочком"},
        ],
    }


def test_should_keep_current_title_when_candidate_drops_commercial_phrase() -> None:
    keep_current, info = should_keep_current_title_as_safer(
        "Костюм для офиса классический с юбкой миди",
        "Костюм классический с юбкой",
        _title_card(),
    )

    assert keep_current is True
    assert info["reason"] in {
        "candidate_regressed_confirmed_business_tokens",
        "candidate_not_materially_better",
    }


def test_should_keep_current_title_when_candidate_adds_unconfirmed_color() -> None:
    keep_current, info = should_keep_current_title_as_safer(
        "Костюм для офиса классический с юбкой миди",
        "Костюм красный для офиса классический с юбкой миди",
        _title_card(),
    )

    assert keep_current is True
    assert "красный" in info["regression"]["bad_added_tokens"]


def test_description_factual_guard_rejects_changed_composition_percentages() -> None:
    ok, reason = validate_description_facts(
        "Состав изделия: 60% полиэстер, 34% вискоза, 6% эластан.",
        _description_card(),
        allow_visual_facts=False,
    )

    assert ok is False
    assert "состав" in reason.lower() or "процент" in reason.lower()


def test_description_factual_guard_rejects_unsupported_material() -> None:
    ok, reason = validate_description_facts(
        "Модель выполнена из шерсти и полиэстера, подходит для офиса.",
        _description_card(),
        allow_visual_facts=False,
    )

    assert ok is False
    assert "неподтвержд" in reason.lower()


def test_description_factual_guard_rejects_conflicting_texture_claim() -> None:
    ok, reason = validate_description_facts(
        "Модель имеет гладкую текстуру и подходит для офиса.",
        _description_card(),
        allow_visual_facts=False,
    )

    assert ok is False
    assert "фактур" in reason.lower()


def test_description_factual_guard_rejects_review_only_material_leak_from_fabric_guess() -> None:
    card = {
        "title": "Костюм для офиса",
        "subjectName": "Костюмы",
        "characteristics": [
            {"name": "Фактура материала", "value": "костюмная"},
            {"name": "Комплектация", "value": "жакет, брюки"},
        ],
    }

    ok, reason = validate_description_facts(
        "Костюм изготовлен из габардина и подходит для офисных образов.",
        card,
        allow_visual_facts=True,
    )

    assert ok is False
    assert "характер" in reason.lower() or "фактур" in reason.lower()


def test_description_factual_guard_rejects_unconfirmed_texture_even_with_visual_context() -> None:
    ok, reason = validate_description_facts(
        "Материал гладкий на ощупь и имеет гладкую текстуру.",
        _description_card(),
        allow_visual_facts=True,
    )

    assert ok is False
    assert "фактур" in reason.lower() or "неподтвержд" in reason.lower()


def test_description_factual_guard_rejects_unconfirmed_visual_claim_without_grounded_context() -> None:
    card = {
        "title": "Жакет для офиса",
        "subjectName": "Жакеты",
        "characteristics": [{"name": "Состав", "value": "62% полиэстер, 32% вискоза, 6% эластан"}],
    }

    ok, reason = validate_description_facts(
        "Модель дополнена V-образным вырезом и гладкой текстурой.",
        card,
        allow_visual_facts=False,
    )

    assert ok is False
    assert "неподтвержд" in reason.lower()


def test_description_factual_guard_rejects_unconfirmed_performance_claims() -> None:
    ok, reason = validate_description_facts(
        "Материал обладает дышащими свойствами, немнущимся эффектом и не требует утюжки.",
        _description_card(),
        allow_visual_facts=True,
    )

    assert ok is False
    assert "неподтвержд" in reason.lower()


def test_normalize_generated_description_converts_escaped_newlines_and_long_block() -> None:
    raw = "Первое предложение. Второе предложение. Третье предложение. Четвертое предложение.\\n\\nПятый блок."
    normalized = normalize_generated_description(raw)

    assert "\\n\\n" not in normalized
    assert "\n\n" in normalized


def test_description_prompt_has_exact_forbidden_words_list() -> None:
    forbidden = forbidden_description_words_text()

    assert "стильный" in forbidden
    assert "элегантный" in forbidden

