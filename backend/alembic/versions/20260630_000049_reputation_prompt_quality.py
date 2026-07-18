"""Improve reputation prompt defaults for AI generation.

Revision ID: 20260630_000049
Revises: 20260630_000048
Create Date: 2026-06-30
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260630_000049"
down_revision = "20260630_000048"
branch_labels = None
depends_on = None


PROMPTS = {
    "review_instructions_template": (
        "You write marketplace seller replies to customer reviews. "
        "Output plain text only. No markdown. No links. No phone numbers. No emails. "
        "Do not mention that you are an AI. "
        "{addr_rule} {length_rule} {emoji_rule} "
        "Language: {language}. Base tone: {tone}. "
        "Hard max length: {hard_max_len} characters. "
        "{stop_words_rule} {signature_rule}"
    ),
    "question_instructions_template": (
        "You write marketplace seller replies to customer questions. "
        "Output plain text only. No markdown. No links. No phone numbers. No emails. "
        "Do not mention that you are an AI. "
        "{addr_rule} {length_rule} {emoji_rule} "
        "Language: {language}. Base tone: {tone}. "
        "Hard max length: {hard_max_len} characters. "
        "{stop_words_rule} {signature_rule}"
    ),
    "chat_instructions_template": (
        "You write short, helpful seller replies in a marketplace buyer chat. "
        "Output plain text only. No markdown. No links. No phone numbers. No emails. "
        "Be concise and clear. Ask clarifying questions only if required. "
        "{addr_rule} {emoji_rule} {stop_words_rule} "
        "Language: {language}. Tone: {tone}. Max length: {hard_max_len} characters."
    ),
}

OLD_PROMPTS = {
    "review_instructions_template": (
        "You write marketplace seller replies to customer reviews. Output plain text only. "
        "No markdown, links, phone numbers, emails, or mentions that you are an AI. "
        "Language: {language}. Base tone: {tone}. Hard max length: {hard_max_len} characters. "
        "{stop_words_rule} {signature_rule}"
    ),
    "question_instructions_template": (
        "You write marketplace seller replies to customer questions. Output plain text only. "
        "No markdown, links, phone numbers, emails, or mentions that you are an AI. "
        "Language: {language}. Base tone: {tone}. Hard max length: {hard_max_len} characters. "
        "{stop_words_rule} {signature_rule}"
    ),
    "chat_instructions_template": (
        "You write short, helpful seller replies in a marketplace buyer chat. Output plain text only. "
        "Be concise and clear. Language: {language}. Tone: {tone}. Max length: {hard_max_len} characters."
    ),
}

CATEGORY_PROMPTS = {
    "brak_i_sostoyanie_tovara": (
        "Поблагодари покупателя и коротко отметь, что качество товара оправдало ожидания.",
        "Спокойно признай проблему с браком или состоянием товара, не спорь с покупателем и скажи, что замечание передадим в проверку качества.",
    ),
    "razmer_i_posadka": (
        "Поблагодари за обратную связь по размеру и отметь, что она помогает другим покупателям.",
        "Признай проблему с размером или посадкой без обвинения покупателя; можно мягко рекомендовать сверяться с размерной сеткой.",
    ),
    "dostavka_i_upakovka": (
        "Поблагодари покупателя и коротко отметь, что аккуратная доставка и упаковка важны.",
        "Извинись за неудобство с доставкой или упаковкой и скажи, что замечание будет учтено в работе.",
    ),
    "ozhidanie_i_realnost": (
        "Поблагодари за оценку внешнего вида и точного представления товара.",
        "Признай, что ожидания не совпали с товаром, и скажи, что описание или визуальные материалы карточки будут проверены.",
    ),
    "tsena_i_sootnoshenie_tsena_kachestvo": (
        "Коротко подчеркни пользу или ценность товара, которую отметил покупатель.",
        "Признай ожидание по соотношению цены и качества, не спорь о цене и не оправдывайся.",
    ),
    "kachestvo_i_poshiv": (
        "Поблагодари за оценку материала, пошива или качества товара.",
        "Признай замечание по качеству, материалу или пошиву и скажи, что оно будет учтено при проверке товара.",
    ),
    "emotional_negative": (
        "Сохраняй спокойный и уважительный тон, без лишней радости.",
        "Ответь спокойно и с эмпатией, не защищайся, не спорь и не усиливай конфликт.",
    ),
}


def upgrade() -> None:
    bind = op.get_bind()
    for key, new_value in PROMPTS.items():
        bind.execute(
            sa.text(
                """
                UPDATE reputation_prompt_records
                SET value_text = :new_value
                WHERE scope = 'global'
                  AND key = :key
                  AND (value_text = :old_value OR value_text IS NULL OR btrim(value_text) = '')
                """
            ),
            {"key": key, "new_value": new_value, "old_value": OLD_PROMPTS[key]},
        )
    for code, (positive_prompt, negative_prompt) in CATEGORY_PROMPTS.items():
        bind.execute(
            sa.text(
                """
                UPDATE reputation_review_categories
                SET positive_prompt = :positive_prompt,
                    negative_prompt = :negative_prompt
                WHERE scope = 'global'
                  AND code = :code
                  AND (
                    positive_prompt ILIKE 'Thank %'
                    OR positive_prompt ILIKE 'Keep %'
                    OR negative_prompt ILIKE 'Acknowledge %'
                    OR negative_prompt ILIKE 'Apologize %'
                    OR negative_prompt ILIKE 'Respond %'
                    OR btrim(positive_prompt) = ''
                    OR btrim(negative_prompt) = ''
                  )
                """
            ),
            {
                "code": code,
                "positive_prompt": positive_prompt,
                "negative_prompt": negative_prompt,
            },
        )


def downgrade() -> None:
    bind = op.get_bind()
    for key, old_value in OLD_PROMPTS.items():
        bind.execute(
            sa.text(
                """
                UPDATE reputation_prompt_records
                SET value_text = :old_value
                WHERE scope = 'global' AND key = :key AND value_text = :new_value
                """
            ),
            {"key": key, "old_value": old_value, "new_value": PROMPTS[key]},
        )
