"""Create Phase 4 wrong-question, upload, review, and exercise records.

Revision ID: 20260805_0005
Revises: 20260804_0004
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260805_0005"
down_revision: str | None = "20260804_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "uploaded_materials",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("student_subject_id", sa.Uuid(), nullable=True),
        sa.Column("purpose", sa.String(length=50), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("object_key", sa.String(length=500), nullable=False),
        sa.Column("mime_type", sa.String(length=100), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("processing_status", sa.String(length=30), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["student_subject_id"], ["student_subjects.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("object_key"),
    )
    op.create_index(
        "ix_uploaded_materials_owner_user_id", "uploaded_materials", ["owner_user_id"]
    )
    op.create_index(
        "ix_uploaded_materials_student_subject_id",
        "uploaded_materials",
        ["student_subject_id"],
    )
    op.create_index(
        "ix_uploaded_materials_owner_sha",
        "uploaded_materials",
        ["owner_user_id", "sha256"],
    )

    op.create_table(
        "wrong_questions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("student_subject_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("current_version_number", sa.Integer(), nullable=False),
        sa.Column("approved_version_number", sa.Integer(), nullable=True),
        sa.Column("mastery_status", sa.String(length=30), nullable=False),
        sa.Column("last_reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_count", sa.Integer(), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["student_subject_id"], ["student_subjects.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_wrong_questions_student_subject_id", "wrong_questions", ["student_subject_id"]
    )
    op.create_index(
        "ix_wrong_questions_subject_mastery_review",
        "wrong_questions",
        ["student_subject_id", "mastery_status", "last_reviewed_at"],
    )

    op.create_table(
        "wrong_question_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("wrong_question_id", sa.Uuid(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=30), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("content", sa.JSON(), nullable=False),
        sa.Column("image_material_id", sa.Uuid(), nullable=True),
        sa.Column("change_summary", sa.String(length=500), nullable=False),
        sa.Column("ai_job_id", sa.Uuid(), nullable=True),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["ai_job_id"], ["ai_jobs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["image_material_id"], ["uploaded_materials.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["wrong_question_id"], ["wrong_questions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ai_job_id"),
        sa.UniqueConstraint("wrong_question_id", "version_number"),
    )
    op.create_index(
        "ix_wrong_question_versions_wrong_question_id",
        "wrong_question_versions",
        ["wrong_question_id"],
    )
    op.create_index(
        "ix_wrong_question_versions_image_material_id",
        "wrong_question_versions",
        ["image_material_id"],
    )

    op.create_table(
        "wrong_question_knowledge_points",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("wrong_question_id", sa.Uuid(), nullable=False),
        sa.Column("knowledge_point_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["knowledge_point_id"], ["knowledge_points.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["wrong_question_id"], ["wrong_questions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("wrong_question_id", "knowledge_point_id"),
    )
    op.create_index(
        "ix_wrong_question_knowledge_points_wrong_question_id",
        "wrong_question_knowledge_points",
        ["wrong_question_id"],
    )
    op.create_index(
        "ix_wrong_question_knowledge_points_knowledge_point_id",
        "wrong_question_knowledge_points",
        ["knowledge_point_id"],
    )

    op.create_table(
        "wrong_question_reviews",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("wrong_question_id", sa.Uuid(), nullable=False),
        sa.Column("result_level", sa.String(length=30), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["wrong_question_id"], ["wrong_questions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_wrong_question_reviews_wrong_question_id",
        "wrong_question_reviews",
        ["wrong_question_id"],
    )
    op.create_index(
        "ix_wrong_question_reviews_question_time",
        "wrong_question_reviews",
        ["wrong_question_id", "reviewed_at"],
    )

    op.create_table(
        "generated_question_sets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("student_subject_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("current_version_number", sa.Integer(), nullable=False),
        sa.Column("approved_version_number", sa.Integer(), nullable=True),
        sa.Column("parameters", sa.JSON(), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["student_subject_id"], ["student_subjects.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_generated_question_sets_student_subject_id",
        "generated_question_sets",
        ["student_subject_id"],
    )
    op.create_index(
        "ix_generated_question_sets_subject_status",
        "generated_question_sets",
        ["student_subject_id", "status"],
    )

    op.create_table(
        "generated_question_set_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("question_set_id", sa.Uuid(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=30), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("content", sa.JSON(), nullable=False),
        sa.Column("change_summary", sa.String(length=500), nullable=False),
        sa.Column("ai_job_id", sa.Uuid(), nullable=True),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["ai_job_id"], ["ai_jobs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["question_set_id"], ["generated_question_sets.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ai_job_id"),
        sa.UniqueConstraint("question_set_id", "version_number"),
    )
    op.create_index(
        "ix_generated_question_set_versions_question_set_id",
        "generated_question_set_versions",
        ["question_set_id"],
    )

    op.create_table(
        "generated_questions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("question_set_id", sa.Uuid(), nullable=False),
        sa.Column("approved_version_number", sa.Integer(), nullable=False),
        sa.Column("question_key", sa.String(length=100), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("stem_markdown", sa.Text(), nullable=False),
        sa.Column("answer_markdown", sa.Text(), nullable=False),
        sa.Column("analysis_markdown", sa.Text(), nullable=False),
        sa.Column("difficulty", sa.String(length=30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["question_set_id"], ["generated_question_sets.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("question_set_id", "approved_version_number", "question_key"),
    )
    op.create_index(
        "ix_generated_questions_question_set_id", "generated_questions", ["question_set_id"]
    )
    op.create_index(
        "ix_generated_questions_set_order",
        "generated_questions",
        ["question_set_id", "sort_order"],
    )

    op.create_table(
        "generated_question_knowledge_points",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("generated_question_id", sa.Uuid(), nullable=False),
        sa.Column("knowledge_point_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["generated_question_id"], ["generated_questions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["knowledge_point_id"], ["knowledge_points.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("generated_question_id", "knowledge_point_id"),
    )
    op.create_index(
        "ix_generated_question_knowledge_points_generated_question_id",
        "generated_question_knowledge_points",
        ["generated_question_id"],
    )
    op.create_index(
        "ix_generated_question_knowledge_points_knowledge_point_id",
        "generated_question_knowledge_points",
        ["knowledge_point_id"],
    )


def downgrade() -> None:
    op.drop_table("generated_question_knowledge_points")
    op.drop_table("generated_questions")
    op.drop_table("generated_question_set_versions")
    op.drop_table("generated_question_sets")
    op.drop_table("wrong_question_reviews")
    op.drop_table("wrong_question_knowledge_points")
    op.drop_table("wrong_question_versions")
    op.drop_table("wrong_questions")
    op.drop_table("uploaded_materials")
