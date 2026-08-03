"""Create Phase 1 students, plans, lessons, and secure sessions.

Revision ID: 20260803_0002
Revises: 20260802_0001
Create Date: 2026-08-03
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260803_0002"
down_revision: str | None = "20260802_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

plan_item_type = sa.Enum(
    "CHAPTER", "KNOWLEDGE_POINT", "TOPIC", name="planitemtype", native_enum=False, length=30
)
plan_item_status = sa.Enum(
    "NOT_STARTED",
    "IN_PROGRESS",
    "COMPLETED",
    "REVIEW_NEEDED",
    name="planitemstatus",
    native_enum=False,
    length=30,
)
lesson_type = sa.Enum(
    "NEW_LESSON",
    "REVIEW",
    "EXERCISE",
    "EXAM",
    "PAPER_REVIEW",
    name="lessontype",
    native_enum=False,
    length=30,
)
lesson_status = sa.Enum(
    "PLANNED",
    "COMPLETED",
    "CANCELED",
    "RESCHEDULED",
    name="lessonstatus",
    native_enum=False,
    length=20,
)


def timestamps() -> list[sa.Column[object]]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    ]


def upgrade() -> None:
    # Phase 0 sessions cannot satisfy double-submit CSRF, so invalidate them during upgrade.
    op.execute(sa.text("DELETE FROM user_sessions"))
    op.add_column("user_sessions", sa.Column("csrf_token_hash", sa.String(64), nullable=False))

    op.create_table(
        "subjects",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("normalized_name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("owner_user_id", "normalized_name"),
    )
    op.create_index("ix_subjects_owner_user_id", "subjects", ["owner_user_id"])

    op.create_table(
        "students",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("display_name", sa.String(100), nullable=False),
        sa.Column("grade", sa.String(50), nullable=True),
        sa.Column("region", sa.String(100), nullable=True),
        sa.Column("school", sa.String(200), nullable=True),
        sa.Column("learning_characteristics", sa.Text(), nullable=True),
        sa.Column("guardian_requirements", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_students_owner_user_id", "students", ["owner_user_id"])
    op.create_index("ix_students_owner_archived", "students", ["owner_user_id", "archived_at"])

    op.create_table(
        "student_subjects",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("student_id", sa.Uuid(), nullable=False),
        sa.Column("subject_id", sa.Uuid(), nullable=False),
        sa.Column("textbook_version", sa.String(200), nullable=True),
        sa.Column("current_foundation", sa.Text(), nullable=True),
        sa.Column("overall_goal", sa.Text(), nullable=True),
        sa.Column("stage_goal", sa.Text(), nullable=True),
        sa.Column("teaching_requirements", sa.Text(), nullable=True),
        sa.Column("attention_notes", sa.Text(), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(["student_id"], ["students.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["subject_id"], ["subjects.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("student_id", "subject_id"),
    )
    op.create_index("ix_student_subjects_student_id", "student_subjects", ["student_id"])
    op.create_index("ix_student_subjects_subject_id", "student_subjects", ["subject_id"])
    op.create_index(
        "ix_student_subjects_student", "student_subjects", ["student_id", "archived_at"]
    )

    op.create_table(
        "teaching_plans",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("student_subject_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(
            ["student_subject_id"], ["student_subjects.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_teaching_plans_student_subject_id", "teaching_plans", ["student_subject_id"]
    )
    op.create_index(
        "ix_teaching_plans_student_subject",
        "teaching_plans",
        ["student_subject_id", "archived_at"],
    )

    op.create_table(
        "teaching_plan_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("plan_id", sa.Uuid(), nullable=False),
        sa.Column("parent_id", sa.Uuid(), nullable=True),
        sa.Column("item_type", plan_item_type, nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("estimated_minutes", sa.Integer(), nullable=False),
        sa.Column("actual_minutes", sa.Integer(), nullable=False),
        sa.Column("status", plan_item_status, nullable=False),
        sa.Column("progress_notes", sa.Text(), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(["plan_id"], ["teaching_plans.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["parent_id"], ["teaching_plan_items.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_teaching_plan_items_plan_id", "teaching_plan_items", ["plan_id"])
    op.create_index(
        "ix_plan_items_tree", "teaching_plan_items", ["plan_id", "parent_id", "sort_order"]
    )

    op.create_table(
        "teaching_plan_revisions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("plan_id", sa.Uuid(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("adjustment_reason", sa.String(500), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["plan_id"], ["teaching_plans.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("plan_id", "version_number"),
    )
    op.create_index("ix_teaching_plan_revisions_plan_id", "teaching_plan_revisions", ["plan_id"])

    op.create_table(
        "lessons",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("student_subject_id", sa.Uuid(), nullable=False),
        sa.Column("scheduled_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("planned_minutes", sa.Integer(), nullable=False),
        sa.Column("actual_minutes", sa.Integer(), nullable=True),
        sa.Column("lesson_type", lesson_type, nullable=False),
        sa.Column("theme", sa.String(300), nullable=False),
        sa.Column("special_requirements", sa.Text(), nullable=True),
        sa.Column("status", lesson_status, nullable=False),
        sa.Column("rescheduled_from_lesson_id", sa.Uuid(), nullable=True),
        sa.Column("makeup_for_lesson_id", sa.Uuid(), nullable=True),
        sa.Column("cancellation_reason", sa.String(500), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(
            ["student_subject_id"], ["student_subjects.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["rescheduled_from_lesson_id"], ["lessons.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["makeup_for_lesson_id"], ["lessons.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_lessons_student_subject_id", "lessons", ["student_subject_id"])
    op.create_index(
        "ix_lessons_student_subject_start", "lessons", ["student_subject_id", "scheduled_start"]
    )
    op.create_index("ix_lessons_status_start", "lessons", ["status", "scheduled_start"])

    op.create_table(
        "lesson_plan_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("lesson_id", sa.Uuid(), nullable=False),
        sa.Column("plan_item_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["lesson_id"], ["lessons.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["plan_item_id"], ["teaching_plan_items.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("lesson_id", "plan_item_id"),
    )
    op.create_index("ix_lesson_plan_items_lesson_id", "lesson_plan_items", ["lesson_id"])
    op.create_index("ix_lesson_plan_items_plan_item_id", "lesson_plan_items", ["plan_item_id"])


def downgrade() -> None:
    op.drop_index("ix_lesson_plan_items_plan_item_id", table_name="lesson_plan_items")
    op.drop_index("ix_lesson_plan_items_lesson_id", table_name="lesson_plan_items")
    op.drop_table("lesson_plan_items")
    op.drop_index("ix_lessons_status_start", table_name="lessons")
    op.drop_index("ix_lessons_student_subject_start", table_name="lessons")
    op.drop_index("ix_lessons_student_subject_id", table_name="lessons")
    op.drop_table("lessons")
    op.drop_index("ix_teaching_plan_revisions_plan_id", table_name="teaching_plan_revisions")
    op.drop_table("teaching_plan_revisions")
    op.drop_index("ix_plan_items_tree", table_name="teaching_plan_items")
    op.drop_index("ix_teaching_plan_items_plan_id", table_name="teaching_plan_items")
    op.drop_table("teaching_plan_items")
    op.drop_index("ix_teaching_plans_student_subject", table_name="teaching_plans")
    op.drop_index("ix_teaching_plans_student_subject_id", table_name="teaching_plans")
    op.drop_table("teaching_plans")
    op.drop_index("ix_student_subjects_student", table_name="student_subjects")
    op.drop_index("ix_student_subjects_subject_id", table_name="student_subjects")
    op.drop_index("ix_student_subjects_student_id", table_name="student_subjects")
    op.drop_table("student_subjects")
    op.drop_index("ix_students_owner_archived", table_name="students")
    op.drop_index("ix_students_owner_user_id", table_name="students")
    op.drop_table("students")
    op.drop_index("ix_subjects_owner_user_id", table_name="subjects")
    op.drop_table("subjects")
    op.drop_column("user_sessions", "csrf_token_hash")
