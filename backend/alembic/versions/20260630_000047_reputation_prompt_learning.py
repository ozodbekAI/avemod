"""Add reputation prompt learning tables.

Revision ID: 20260630_000047
Revises: 20260630_000046
Create Date: 2026-06-30
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260630_000047"
down_revision = "20260630_000046"
branch_labels = None
depends_on = None

JSONB = postgresql.JSONB(astext_type=sa.Text())


DEFAULT_REVIEW_PROMPT = (
    "You write marketplace seller replies to customer reviews. Output plain text only. "
    "No markdown, links, phone numbers, emails, or mentions that you are an AI. "
    "Language: {language}. Base tone: {tone}. Hard max length: {hard_max_len} characters. "
    "{stop_words_rule} {signature_rule}"
)

DEFAULT_QUESTION_PROMPT = (
    "You write marketplace seller replies to customer questions. Output plain text only. "
    "No markdown, links, phone numbers, emails, or mentions that you are an AI. "
    "Language: {language}. Base tone: {tone}. Hard max length: {hard_max_len} characters. "
    "{stop_words_rule} {signature_rule}"
)

DEFAULT_CHAT_PROMPT = (
    "You write short, helpful seller replies in a marketplace buyer chat. Output plain text only. "
    "Be concise and clear. Language: {language}. Tone: {tone}. Max length: {hard_max_len} characters."
)

DEFAULT_CATEGORIES = [
    (
        "product_quality",
        "Качество товара",
        "Thank the buyer, reinforce that the product met expectations, and keep the reply warm.",
        "Apologize for the quality issue, acknowledge the defect clearly, and say the feedback will be checked.",
        10,
    ),
    (
        "size_fit",
        "Размер и посадка",
        "Thank the buyer and mention that accurate sizing feedback helps other customers.",
        "Acknowledge the size or fit problem, avoid blaming the buyer, and recommend checking the size grid.",
        20,
    ),
    (
        "packaging_delivery",
        "Упаковка и доставка",
        "Thank the buyer and briefly note that careful delivery experience matters.",
        "Apologize for packaging or delivery inconvenience and promise to review the handling/packaging process.",
        30,
    ),
    (
        "appearance_expectation",
        "Внешний вид и ожидания",
        "Thank the buyer for noting appearance and confirm that the team values accurate product presentation.",
        "Acknowledge that the product did not match expectations and say the description/photos will be reviewed.",
        40,
    ),
    (
        "price_value",
        "Цена и ценность",
        "Thank the buyer and emphasize the value/benefit they noticed.",
        "Acknowledge the value concern without arguing about price and thank the buyer for the signal.",
        50,
    ),
    (
        "service_communication",
        "Сервис и коммуникация",
        "Thank the buyer for the dialogue and keep the tone especially respectful.",
        "Apologize for the communication issue, state that the case will be checked, and keep the answer calm.",
        60,
    ),
]


def upgrade() -> None:
    op.create_table(
        "reputation_prompt_records",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("scope", sa.String(length=64), nullable=False, server_default="global"),
        sa.Column("key", sa.String(length=96), nullable=False),
        sa.Column("value_text", sa.Text(), nullable=True),
        sa.Column("value_json", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("scope", "key", name="uq_reputation_prompt_records_scope_key"),
    )
    op.create_index("ix_reputation_prompt_records_scope", "reputation_prompt_records", ["scope"])
    op.create_index("ix_reputation_prompt_records_key", "reputation_prompt_records", ["key"])

    op.create_table(
        "reputation_review_categories",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("scope", sa.String(length=64), nullable=False, server_default="global"),
        sa.Column("account_id", sa.BigInteger(), nullable=True),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("label", sa.String(length=128), nullable=False),
        sa.Column("positive_prompt", sa.Text(), nullable=False),
        sa.Column("negative_prompt", sa.Text(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("TRUE")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["wb_accounts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("scope", "code", name="uq_reputation_review_categories_scope_code"),
    )
    op.create_index("ix_reputation_review_categories_scope", "reputation_review_categories", ["scope"])
    op.create_index("ix_reputation_review_categories_code", "reputation_review_categories", ["code"])
    op.create_index("ix_reputation_review_categories_account_id", "reputation_review_categories", ["account_id"])
    op.create_index("ix_reputation_review_categories_is_active", "reputation_review_categories", ["is_active"])

    op.create_table(
        "reputation_learning_entries",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("account_id", sa.BigInteger(), nullable=False),
        sa.Column("reputation_item_id", sa.BigInteger(), nullable=True),
        sa.Column("nm_id", sa.BigInteger(), nullable=True),
        sa.Column("target_type", sa.String(length=32), nullable=False),
        sa.Column("category_code", sa.String(length=64), nullable=True),
        sa.Column("sentiment_scope", sa.String(length=16), nullable=True),
        sa.Column("user_instruction", sa.Text(), nullable=False),
        sa.Column("applied_text", sa.Text(), nullable=False),
        sa.Column("stop_word", sa.String(length=120), nullable=True),
        sa.Column("source_answer_text", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("TRUE")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["wb_accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["reputation_item_id"], ["reputation_items.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_reputation_learning_entries_account_active", "reputation_learning_entries", ["account_id", "is_active"])
    op.create_index("ix_reputation_learning_entries_account_nm", "reputation_learning_entries", ["account_id", "nm_id"])
    op.create_index("ix_reputation_learning_entries_target", "reputation_learning_entries", ["target_type"])
    op.create_index("ix_reputation_learning_entries_account_id", "reputation_learning_entries", ["account_id"])
    op.create_index("ix_reputation_learning_entries_nm_id", "reputation_learning_entries", ["nm_id"])
    op.create_index("ix_reputation_learning_entries_category_code", "reputation_learning_entries", ["category_code"])
    op.create_index("ix_reputation_learning_entries_is_active", "reputation_learning_entries", ["is_active"])

    prompt_table = sa.table(
        "reputation_prompt_records",
        sa.column("scope", sa.String),
        sa.column("key", sa.String),
        sa.column("value_text", sa.Text),
        sa.column("value_json", JSONB),
    )
    op.bulk_insert(
        prompt_table,
        [
            {"scope": "global", "key": "review_instructions_template", "value_text": DEFAULT_REVIEW_PROMPT, "value_json": None},
            {"scope": "global", "key": "question_instructions_template", "value_text": DEFAULT_QUESTION_PROMPT, "value_json": None},
            {"scope": "global", "key": "chat_instructions_template", "value_text": DEFAULT_CHAT_PROMPT, "value_json": None},
            {"scope": "global", "key": "tone_map", "value_text": None, "value_json": {"polite": "Polite and concise.", "warm": "Warm and friendly.", "empathetic": "Empathetic and careful.", "clear": "Clear and factual."}},
        ],
    )

    category_table = sa.table(
        "reputation_review_categories",
        sa.column("scope", sa.String),
        sa.column("code", sa.String),
        sa.column("label", sa.String),
        sa.column("positive_prompt", sa.Text),
        sa.column("negative_prompt", sa.Text),
        sa.column("sort_order", sa.Integer),
        sa.column("is_active", sa.Boolean),
    )
    op.bulk_insert(
        category_table,
        [
            {
                "scope": "global",
                "code": code,
                "label": label,
                "positive_prompt": positive_prompt,
                "negative_prompt": negative_prompt,
                "sort_order": sort_order,
                "is_active": True,
            }
            for code, label, positive_prompt, negative_prompt, sort_order in DEFAULT_CATEGORIES
        ],
    )


def downgrade() -> None:
    op.drop_index("ix_reputation_learning_entries_is_active", table_name="reputation_learning_entries")
    op.drop_index("ix_reputation_learning_entries_category_code", table_name="reputation_learning_entries")
    op.drop_index("ix_reputation_learning_entries_nm_id", table_name="reputation_learning_entries")
    op.drop_index("ix_reputation_learning_entries_account_id", table_name="reputation_learning_entries")
    op.drop_index("ix_reputation_learning_entries_target", table_name="reputation_learning_entries")
    op.drop_index("ix_reputation_learning_entries_account_nm", table_name="reputation_learning_entries")
    op.drop_index("ix_reputation_learning_entries_account_active", table_name="reputation_learning_entries")
    op.drop_table("reputation_learning_entries")
    op.drop_index("ix_reputation_review_categories_is_active", table_name="reputation_review_categories")
    op.drop_index("ix_reputation_review_categories_account_id", table_name="reputation_review_categories")
    op.drop_index("ix_reputation_review_categories_code", table_name="reputation_review_categories")
    op.drop_index("ix_reputation_review_categories_scope", table_name="reputation_review_categories")
    op.drop_table("reputation_review_categories")
    op.drop_index("ix_reputation_prompt_records_key", table_name="reputation_prompt_records")
    op.drop_index("ix_reputation_prompt_records_scope", table_name="reputation_prompt_records")
    op.drop_table("reputation_prompt_records")
