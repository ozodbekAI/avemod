"""Add local Photo Studio module tables.

Revision ID: 20260623_000040
Revises: 20260623_000039
Create Date: 2026-06-23 00:40:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260623_000040"
down_revision = "20260623_000039"
branch_labels = None
depends_on = None

JSONB = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.create_table(
        "photo_projects",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("account_id", sa.BigInteger(), nullable=False),
        sa.Column("nm_id", sa.BigInteger(), nullable=False),
        sa.Column("sku_id", sa.BigInteger(), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("source_issue_id", sa.BigInteger(), nullable=True),
        sa.Column("source_action_key", sa.String(length=255), nullable=True),
        sa.Column("created_by_user_id", sa.BigInteger(), nullable=True),
        sa.Column("preferred_version_id", sa.BigInteger(), nullable=True),
        sa.Column("approved_version_id", sa.BigInteger(), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["account_id"], ["wb_accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["auth_users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_photo_projects_account_id", "photo_projects", ["account_id"])
    op.create_index("ix_photo_projects_account_nm", "photo_projects", ["account_id", "nm_id"])
    op.create_index("ix_photo_projects_account_status", "photo_projects", ["account_id", "status"])
    op.create_index("ix_photo_projects_nm_id", "photo_projects", ["nm_id"])
    op.create_index("ix_photo_projects_sku_id", "photo_projects", ["sku_id"])
    op.create_index("ix_photo_projects_status", "photo_projects", ["status"])
    op.create_index("ix_photo_projects_source_issue_id", "photo_projects", ["source_issue_id"])
    op.create_index("ix_photo_projects_source_action_key", "photo_projects", ["source_action_key"])
    op.create_index("ix_photo_projects_created_by_user_id", "photo_projects", ["created_by_user_id"])
    op.create_index("ix_photo_projects_preferred_version_id", "photo_projects", ["preferred_version_id"])
    op.create_index("ix_photo_projects_approved_version_id", "photo_projects", ["approved_version_id"])

    op.create_table(
        "photo_assets",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("account_id", sa.BigInteger(), nullable=False),
        sa.Column("nm_id", sa.BigInteger(), nullable=True),
        sa.Column("project_id", sa.BigInteger(), nullable=True),
        sa.Column("asset_type", sa.String(length=32), nullable=False),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("storage_key", sa.String(length=500), nullable=True),
        sa.Column("original_file_name", sa.String(length=255), nullable=True),
        sa.Column("mime_type", sa.String(length=64), nullable=False),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("checksum", sa.String(length=128), nullable=True),
        sa.Column("exif_removed", sa.Boolean(), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("source_asset_id", sa.BigInteger(), nullable=True),
        sa.Column("is_test", sa.Boolean(), nullable=False),
        sa.Column("created_by_user_id", sa.BigInteger(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata_json", JSONB, nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["wb_accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["auth_users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["project_id"], ["photo_projects.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["source_asset_id"], ["photo_assets.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("account_id", "checksum", "source_url", name="uq_photo_assets_source_checksum"),
    )
    op.create_index("ix_photo_assets_account_id", "photo_assets", ["account_id"])
    op.create_index("ix_photo_assets_account_nm", "photo_assets", ["account_id", "nm_id"])
    op.create_index("ix_photo_assets_project", "photo_assets", ["project_id"])
    op.create_index("ix_photo_assets_nm_id", "photo_assets", ["nm_id"])
    op.create_index("ix_photo_assets_project_id", "photo_assets", ["project_id"])
    op.create_index("ix_photo_assets_asset_type", "photo_assets", ["asset_type"])
    op.create_index("ix_photo_assets_source_type", "photo_assets", ["source_type"])
    op.create_index("ix_photo_assets_checksum", "photo_assets", ["checksum"])
    op.create_index("ix_photo_assets_is_test", "photo_assets", ["is_test"])
    op.create_index("ix_photo_assets_created_by_user_id", "photo_assets", ["created_by_user_id"])

    op.create_table(
        "photo_versions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("account_id", sa.BigInteger(), nullable=False),
        sa.Column("project_id", sa.BigInteger(), nullable=False),
        sa.Column("asset_id", sa.BigInteger(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("parent_version_id", sa.BigInteger(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=True),
        sa.Column("brief_text", sa.Text(), nullable=True),
        sa.Column("change_summary", sa.Text(), nullable=True),
        sa.Column("generation_job_id", sa.BigInteger(), nullable=True),
        sa.Column("created_by_user_id", sa.BigInteger(), nullable=True),
        sa.Column("approved_by_user_id", sa.BigInteger(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["account_id"], ["wb_accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["approved_by_user_id"], ["auth_users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["asset_id"], ["photo_assets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["auth_users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["parent_version_id"], ["photo_versions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["project_id"], ["photo_projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("account_id", "project_id", "version_number", name="uq_photo_versions_project_number"),
    )
    op.create_index("ix_photo_versions_account_id", "photo_versions", ["account_id"])
    op.create_index("ix_photo_versions_project_id", "photo_versions", ["project_id"])
    op.create_index("ix_photo_versions_asset_id", "photo_versions", ["asset_id"])
    op.create_index("ix_photo_versions_status", "photo_versions", ["status"])
    op.create_index("ix_photo_versions_project_status", "photo_versions", ["project_id", "status"])
    op.create_index("ix_photo_versions_generation_job_id", "photo_versions", ["generation_job_id"])
    op.create_index("ix_photo_versions_created_by_user_id", "photo_versions", ["created_by_user_id"])
    op.create_index("ix_photo_versions_approved_by_user_id", "photo_versions", ["approved_by_user_id"])

    op.create_table(
        "photo_generation_jobs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("account_id", sa.BigInteger(), nullable=False),
        sa.Column("project_id", sa.BigInteger(), nullable=False),
        sa.Column("input_asset_ids_json", JSONB, nullable=False),
        sa.Column("job_type", sa.String(length=64), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=True),
        sa.Column("model", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("prompt_version", sa.String(length=64), nullable=True),
        sa.Column("sanitized_prompt", sa.Text(), nullable=True),
        sa.Column("settings_snapshot_json", JSONB, nullable=False),
        sa.Column("requested_by_user_id", sa.BigInteger(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("progress_percent", sa.Integer(), nullable=False),
        sa.Column("output_asset_ids_json", JSONB, nullable=False),
        sa.Column("error_code", sa.String(length=128), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["account_id"], ["wb_accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["photo_projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["auth_users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_photo_generation_jobs_account_id", "photo_generation_jobs", ["account_id"])
    op.create_index("ix_photo_jobs_account_status", "photo_generation_jobs", ["account_id", "status"])
    op.create_index("ix_photo_jobs_project", "photo_generation_jobs", ["project_id"])
    op.create_index("ix_photo_generation_jobs_project_id", "photo_generation_jobs", ["project_id"])
    op.create_index("ix_photo_generation_jobs_job_type", "photo_generation_jobs", ["job_type"])
    op.create_index("ix_photo_generation_jobs_status", "photo_generation_jobs", ["status"])

    op.create_table(
        "photo_project_messages",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("account_id", sa.BigInteger(), nullable=False),
        sa.Column("project_id", sa.BigInteger(), nullable=False),
        sa.Column("author_user_id", sa.BigInteger(), nullable=True),
        sa.Column("author_type", sa.String(length=32), nullable=False),
        sa.Column("message_type", sa.String(length=32), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("linked_asset_ids_json", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["wb_accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["author_user_id"], ["auth_users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["project_id"], ["photo_projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_photo_messages_project_created", "photo_project_messages", ["project_id", "created_at"])
    op.create_index("ix_photo_project_messages_account_id", "photo_project_messages", ["account_id"])
    op.create_index("ix_photo_project_messages_project_id", "photo_project_messages", ["project_id"])
    op.create_index("ix_photo_project_messages_author_user_id", "photo_project_messages", ["author_user_id"])
    op.create_index("ix_photo_project_messages_message_type", "photo_project_messages", ["message_type"])

    op.create_table(
        "photo_project_events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("account_id", sa.BigInteger(), nullable=False),
        sa.Column("project_id", sa.BigInteger(), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("actor_user_id", sa.BigInteger(), nullable=True),
        sa.Column("payload_json", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["wb_accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["auth_users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["project_id"], ["photo_projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_photo_events_project_created", "photo_project_events", ["project_id", "created_at"])
    op.create_index("ix_photo_project_events_account_id", "photo_project_events", ["account_id"])
    op.create_index("ix_photo_project_events_project_id", "photo_project_events", ["project_id"])
    op.create_index("ix_photo_project_events_event_type", "photo_project_events", ["event_type"])

    op.create_table(
        "photo_settings",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("account_id", sa.BigInteger(), nullable=False),
        sa.Column("provider_mode", sa.String(length=32), nullable=False),
        sa.Column("default_provider", sa.String(length=64), nullable=True),
        sa.Column("default_model", sa.String(length=128), nullable=True),
        sa.Column("default_aspect_ratio", sa.String(length=32), nullable=True),
        sa.Column("default_output_format", sa.String(length=16), nullable=False),
        sa.Column("max_upload_mb", sa.Integer(), nullable=False),
        sa.Column("allowed_mime_types_json", JSONB, nullable=False),
        sa.Column("generation_enabled", sa.Boolean(), nullable=False),
        sa.Column("editing_enabled", sa.Boolean(), nullable=False),
        sa.Column("external_apply_enabled", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["wb_accounts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("account_id", name="uq_photo_settings_account"),
    )
    op.create_index("ix_photo_settings_account_id", "photo_settings", ["account_id"])


def downgrade() -> None:
    op.drop_index("ix_photo_settings_account_id", table_name="photo_settings")
    op.drop_table("photo_settings")
    op.drop_index("ix_photo_project_events_event_type", table_name="photo_project_events")
    op.drop_index("ix_photo_project_events_project_id", table_name="photo_project_events")
    op.drop_index("ix_photo_project_events_account_id", table_name="photo_project_events")
    op.drop_index("ix_photo_events_project_created", table_name="photo_project_events")
    op.drop_table("photo_project_events")
    op.drop_index("ix_photo_project_messages_message_type", table_name="photo_project_messages")
    op.drop_index("ix_photo_project_messages_author_user_id", table_name="photo_project_messages")
    op.drop_index("ix_photo_project_messages_project_id", table_name="photo_project_messages")
    op.drop_index("ix_photo_project_messages_account_id", table_name="photo_project_messages")
    op.drop_index("ix_photo_messages_project_created", table_name="photo_project_messages")
    op.drop_table("photo_project_messages")
    op.drop_index("ix_photo_generation_jobs_status", table_name="photo_generation_jobs")
    op.drop_index("ix_photo_generation_jobs_job_type", table_name="photo_generation_jobs")
    op.drop_index("ix_photo_generation_jobs_project_id", table_name="photo_generation_jobs")
    op.drop_index("ix_photo_jobs_project", table_name="photo_generation_jobs")
    op.drop_index("ix_photo_jobs_account_status", table_name="photo_generation_jobs")
    op.drop_index("ix_photo_generation_jobs_account_id", table_name="photo_generation_jobs")
    op.drop_table("photo_generation_jobs")
    op.drop_index("ix_photo_versions_approved_by_user_id", table_name="photo_versions")
    op.drop_index("ix_photo_versions_created_by_user_id", table_name="photo_versions")
    op.drop_index("ix_photo_versions_generation_job_id", table_name="photo_versions")
    op.drop_index("ix_photo_versions_project_status", table_name="photo_versions")
    op.drop_index("ix_photo_versions_status", table_name="photo_versions")
    op.drop_index("ix_photo_versions_asset_id", table_name="photo_versions")
    op.drop_index("ix_photo_versions_project_id", table_name="photo_versions")
    op.drop_index("ix_photo_versions_account_id", table_name="photo_versions")
    op.drop_table("photo_versions")
    op.drop_index("ix_photo_assets_created_by_user_id", table_name="photo_assets")
    op.drop_index("ix_photo_assets_is_test", table_name="photo_assets")
    op.drop_index("ix_photo_assets_checksum", table_name="photo_assets")
    op.drop_index("ix_photo_assets_source_type", table_name="photo_assets")
    op.drop_index("ix_photo_assets_asset_type", table_name="photo_assets")
    op.drop_index("ix_photo_assets_project_id", table_name="photo_assets")
    op.drop_index("ix_photo_assets_nm_id", table_name="photo_assets")
    op.drop_index("ix_photo_assets_project", table_name="photo_assets")
    op.drop_index("ix_photo_assets_account_nm", table_name="photo_assets")
    op.drop_index("ix_photo_assets_account_id", table_name="photo_assets")
    op.drop_table("photo_assets")
    op.drop_index("ix_photo_projects_approved_version_id", table_name="photo_projects")
    op.drop_index("ix_photo_projects_preferred_version_id", table_name="photo_projects")
    op.drop_index("ix_photo_projects_created_by_user_id", table_name="photo_projects")
    op.drop_index("ix_photo_projects_source_action_key", table_name="photo_projects")
    op.drop_index("ix_photo_projects_source_issue_id", table_name="photo_projects")
    op.drop_index("ix_photo_projects_status", table_name="photo_projects")
    op.drop_index("ix_photo_projects_sku_id", table_name="photo_projects")
    op.drop_index("ix_photo_projects_nm_id", table_name="photo_projects")
    op.drop_index("ix_photo_projects_account_status", table_name="photo_projects")
    op.drop_index("ix_photo_projects_account_nm", table_name="photo_projects")
    op.drop_index("ix_photo_projects_account_id", table_name="photo_projects")
    op.drop_table("photo_projects")
