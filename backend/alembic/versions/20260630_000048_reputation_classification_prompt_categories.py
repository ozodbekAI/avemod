"""Seed reputation classification prompt categories.

Revision ID: 20260630_000048
Revises: 20260630_000047
Create Date: 2026-06-30
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260630_000048"
down_revision = "20260630_000047"
branch_labels = None
depends_on = None


CATEGORIES = [
    (
        "brak_i_sostoyanie_tovara",
        "Брак и состояние товара",
        "Thank the buyer, reinforce that the product met expectations, and keep the reply warm.",
        "Acknowledge the defect or condition issue, do not argue, and say the feedback will be checked.",
        10,
    ),
    (
        "razmer_i_posadka",
        "Размер и посадка",
        "Thank the buyer and mention that accurate sizing feedback helps other customers.",
        "Acknowledge the size or fit problem, avoid blaming the buyer, and recommend checking the size grid.",
        20,
    ),
    (
        "dostavka_i_upakovka",
        "Доставка и упаковка",
        "Thank the buyer and briefly note that careful delivery experience matters.",
        "Apologize for packaging or delivery inconvenience and promise to review the handling/packaging process.",
        30,
    ),
    (
        "ozhidanie_i_realnost",
        "Ожидание и реальность",
        "Thank the buyer for noting appearance and confirm that the team values accurate product presentation.",
        "Acknowledge that the product did not match expectations and say the description/photos will be reviewed.",
        40,
    ),
    (
        "tsena_i_sootnoshenie_tsena_kachestvo",
        "Цена и ценность",
        "Thank the buyer and emphasize the value/benefit they noticed.",
        "Acknowledge the value concern without arguing about price and thank the buyer for the signal.",
        50,
    ),
    (
        "kachestvo_i_poshiv",
        "Качество и пошив",
        "Thank the buyer for noting material, sewing, or product quality.",
        "Acknowledge quality or sewing concerns and say the feedback will be considered in product checks.",
        60,
    ),
    (
        "emotional_negative",
        "Эмоционально негативный отзыв",
        "Keep the response calm and concise.",
        "Respond calmly, acknowledge the emotion, avoid defensiveness, and move the issue to manual attention if needed.",
        70,
    ),
]


def upgrade() -> None:
    bind = op.get_bind()
    for code, label, positive_prompt, negative_prompt, sort_order in CATEGORIES:
        bind.execute(
            sa.text(
                """
            INSERT INTO reputation_review_categories
                (scope, code, label, positive_prompt, negative_prompt, sort_order, is_active)
            VALUES
                ('global', %(code)s, %(label)s, %(positive_prompt)s, %(negative_prompt)s, %(sort_order)s, TRUE)
            ON CONFLICT (scope, code) DO NOTHING
            """.replace("%(", ":").replace(")s", "")
            ),
            {
                "code": code,
                "label": label,
                "positive_prompt": positive_prompt,
                "negative_prompt": negative_prompt,
                "sort_order": sort_order,
            },
        )


def downgrade() -> None:
    codes = ", ".join(f"'{code}'" for code, *_ in CATEGORIES)
    op.execute(f"DELETE FROM reputation_review_categories WHERE scope = 'global' AND code IN ({codes})")
