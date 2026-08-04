"""Create Phase 3 feedback, knowledge point, and mastery records.

Revision ID: 20260804_0004
Revises: 20260803_0003
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260804_0004"
down_revision: str | None = "20260803_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "lesson_feedbacks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("lesson_id", sa.Uuid(), nullable=False),
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
    )
    op.create_index(
        "ix_lesson_feedbacks_lesson_id",
        "lesson_feedbacks",
        ["lesson_id"],
        unique=True,
    )

    op.create_table(
        "lesson_feedback_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("feedback_id", sa.Uuid(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=30), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("raw_input", sa.JSON(), nullable=False),
        sa.Column("content", sa.JSON(), nullable=False),
        sa.Column("change_summary", sa.String(length=500), nullable=False),
        sa.Column("ai_job_id", sa.Uuid(), nullable=True, unique=True),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["ai_job_id"], ["ai_jobs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["feedback_id"], ["lesson_feedbacks.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("feedback_id", "version_number"),
    )
    op.create_index(
        "ix_lesson_feedback_versions_feedback_id",
        "lesson_feedback_versions",
        ["feedback_id"],
    )

    op.create_table(
        "knowledge_points",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("subject_id", sa.Uuid(), nullable=False),
        sa.Column("parent_id", sa.Uuid(), nullable=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("normalized_name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["parent_id"], ["knowledge_points.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["subject_id"], ["subjects.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("subject_id", "normalized_name"),
    )
    op.create_index(
        "ix_knowledge_points_subject_id", "knowledge_points", ["subject_id"]
    )
    op.create_index(
        "ix_knowledge_points_subject_parent",
        "knowledge_points",
        ["subject_id", "parent_id"],
    )

    op.create_table(
        "student_masteries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("student_subject_id", sa.Uuid(), nullable=False),
        sa.Column("knowledge_point_id", sa.Uuid(), nullable=False),
        sa.Column("level", sa.String(length=30), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["knowledge_point_id"], ["knowledge_points.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["student_subject_id"], ["student_subjects.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("student_subject_id", "knowledge_point_id"),
    )
    op.create_index(
        "ix_student_masteries_knowledge_point_id",
        "student_masteries",
        ["knowledge_point_id"],
    )
    op.create_index(
        "ix_student_masteries_student_subject_id",
        "student_masteries",
        ["student_subject_id"],
    )
    op.create_index(
        "ix_student_masteries_level",
        "student_masteries",
        ["student_subject_id", "level"],
    )

    op.create_table(
        "mastery_evidence",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("mastery_id", sa.Uuid(), nullable=False),
        sa.Column("feedback_version_id", sa.Uuid(), nullable=False),
        sa.Column("previous_level", sa.String(length=30), nullable=False),
        sa.Column("new_level", sa.String(length=30), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["feedback_version_id"],
            ["lesson_feedback_versions.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["mastery_id"], ["student_masteries.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("mastery_id", "feedback_version_id"),
    )
    op.create_index(
        "ix_mastery_evidence_feedback_version_id",
        "mastery_evidence",
        ["feedback_version_id"],
    )
    op.create_index(
        "ix_mastery_evidence_mastery_id", "mastery_evidence", ["mastery_id"]
    )
    op.create_index(
        "ix_mastery_evidence_mastery_created",
        "mastery_evidence",
        ["mastery_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_mastery_evidence_mastery_created", table_name="mastery_evidence")
    op.drop_index("ix_mastery_evidence_mastery_id", table_name="mastery_evidence")
    op.drop_index(
        "ix_mastery_evidence_feedback_version_id", table_name="mastery_evidence"
    )
    op.drop_table("mastery_evidence")
    op.drop_index("ix_student_masteries_level", table_name="student_masteries")
    op.drop_index(
        "ix_student_masteries_student_subject_id", table_name="student_masteries"
    )
    op.drop_index(
        "ix_student_masteries_knowledge_point_id", table_name="student_masteries"
    )
    op.drop_table("student_masteries")
    op.drop_index(
        "ix_knowledge_points_subject_parent", table_name="knowledge_points"
    )
    op.drop_index("ix_knowledge_points_subject_id", table_name="knowledge_points")
    op.drop_table("knowledge_points")
    op.drop_index(
        "ix_lesson_feedback_versions_feedback_id",
        table_name="lesson_feedback_versions",
    )
    op.drop_table("lesson_feedback_versions")
    op.drop_index("ix_lesson_feedbacks_lesson_id", table_name="lesson_feedbacks")
    op.drop_table("lesson_feedbacks")
