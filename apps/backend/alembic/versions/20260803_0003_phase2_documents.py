"""Create Phase 2 prompt templates and lesson document versions.

Revision ID: 20260803_0003
Revises: 20260803_0002
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260803_0003"
down_revision: str | None = "20260803_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "prompt_templates",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("subject_id", sa.Uuid(), nullable=True),
        sa.Column("template_key", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("purpose", sa.String(length=100), nullable=False),
        sa.Column("grade_band", sa.String(length=50), nullable=True),
        sa.Column("current_version_number", sa.Integer(), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["subject_id"], ["subjects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "owner_user_id", "template_key", "grade_band", "subject_id"
        ),
    )
    op.create_index(
        "ix_prompt_templates_owner_key",
        "prompt_templates",
        ["owner_user_id", "template_key"],
    )
    op.create_index(
        "ix_prompt_templates_owner_user_id", "prompt_templates", ["owner_user_id"]
    )
    op.create_index("ix_prompt_templates_subject_id", "prompt_templates", ["subject_id"])

    op.create_table(
        "prompt_template_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("template_id", sa.Uuid(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("system_prompt", sa.Text(), nullable=False),
        sa.Column("user_prompt_template", sa.Text(), nullable=False),
        sa.Column("output_schema", sa.JSON(), nullable=False),
        sa.Column("change_reason", sa.String(length=500), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["template_id"], ["prompt_templates.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("template_id", "version_number"),
    )
    op.create_index(
        "ix_prompt_template_versions_template_id",
        "prompt_template_versions",
        ["template_id"],
    )

    op.add_column("ai_jobs", sa.Column("owner_user_id", sa.Uuid(), nullable=True))
    op.add_column(
        "ai_jobs", sa.Column("prompt_template_version_id", sa.Uuid(), nullable=True)
    )
    op.create_foreign_key(
        "fk_ai_jobs_owner_user_id",
        "ai_jobs",
        "users",
        ["owner_user_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_ai_jobs_prompt_template_version_id",
        "ai_jobs",
        "prompt_template_versions",
        ["prompt_template_version_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_ai_jobs_owner_user_id", "ai_jobs", ["owner_user_id"])

    op.create_table(
        "lesson_documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("lesson_id", sa.Uuid(), nullable=False),
        sa.Column("document_type", sa.String(length=50), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("current_version_number", sa.Integer(), nullable=False),
        sa.Column("approved_version_number", sa.Integer(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["lesson_id"], ["lessons.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("lesson_id", "document_type"),
    )
    op.create_index("ix_lesson_documents_lesson_id", "lesson_documents", ["lesson_id"])
    op.create_index(
        "ix_lesson_documents_lesson_status",
        "lesson_documents",
        ["lesson_id", "status"],
    )

    op.create_table(
        "document_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=30), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("content", sa.JSON(), nullable=False),
        sa.Column("change_summary", sa.String(length=500), nullable=False),
        sa.Column("ai_job_id", sa.Uuid(), nullable=True, unique=True),
        sa.Column("docx_object_key", sa.String(length=500), nullable=True),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["ai_job_id"], ["ai_jobs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["document_id"], ["lesson_documents.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("document_id", "version_number"),
    )
    op.create_index(
        "ix_document_versions_document_id", "document_versions", ["document_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_document_versions_document_id", table_name="document_versions")
    op.drop_table("document_versions")
    op.drop_index("ix_lesson_documents_lesson_status", table_name="lesson_documents")
    op.drop_index("ix_lesson_documents_lesson_id", table_name="lesson_documents")
    op.drop_table("lesson_documents")
    op.drop_index("ix_ai_jobs_owner_user_id", table_name="ai_jobs")
    op.drop_constraint(
        "fk_ai_jobs_prompt_template_version_id", "ai_jobs", type_="foreignkey"
    )
    op.drop_constraint("fk_ai_jobs_owner_user_id", "ai_jobs", type_="foreignkey")
    op.drop_column("ai_jobs", "prompt_template_version_id")
    op.drop_column("ai_jobs", "owner_user_id")
    op.drop_index(
        "ix_prompt_template_versions_template_id", table_name="prompt_template_versions"
    )
    op.drop_table("prompt_template_versions")
    op.drop_index("ix_prompt_templates_subject_id", table_name="prompt_templates")
    op.drop_index("ix_prompt_templates_owner_user_id", table_name="prompt_templates")
    op.drop_index("ix_prompt_templates_owner_key", table_name="prompt_templates")
    op.drop_table("prompt_templates")
