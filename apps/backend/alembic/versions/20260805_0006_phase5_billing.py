"""Create Phase 5 lesson billing and payment allocation records.

Revision ID: 20260805_0006
Revises: 20260805_0005
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260805_0006"
down_revision: str | None = "20260805_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "lessons",
        sa.Column("unit_price_cents", sa.BigInteger(), server_default="0", nullable=False),
    )
    op.add_column(
        "lessons",
        sa.Column("receivable_cents", sa.BigInteger(), server_default="0", nullable=False),
    )
    op.add_column(
        "lessons",
        sa.Column(
            "receivable_is_overridden",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )
    op.add_column(
        "lessons",
        sa.Column("receivable_override_reason", sa.String(length=500), nullable=True),
    )
    op.create_check_constraint(
        "ck_lessons_unit_price_nonnegative", "lessons", "unit_price_cents >= 0"
    )
    op.create_check_constraint(
        "ck_lessons_receivable_nonnegative", "lessons", "receivable_cents >= 0"
    )

    op.create_table(
        "payments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("amount_cents", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(length=3), server_default="CNY", nullable=False),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("method", sa.String(length=50), nullable=False),
        sa.Column("reference", sa.String(length=200), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("voided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("void_reason", sa.String(length=500), nullable=True),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("amount_cents > 0", name="ck_payments_amount_positive"),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_payments_owner_user_id", "payments", ["owner_user_id"])
    op.create_index("ix_payments_paid_at", "payments", ["paid_at"])
    op.create_index("ix_payments_voided_at", "payments", ["voided_at"])
    op.create_index(
        "ix_payments_owner_paid_at", "payments", ["owner_user_id", "paid_at"]
    )

    op.create_table(
        "payment_allocations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("payment_id", sa.Uuid(), nullable=False),
        sa.Column("lesson_id", sa.Uuid(), nullable=False),
        sa.Column("amount_cents", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "amount_cents > 0", name="ck_payment_allocations_amount_positive"
        ),
        sa.ForeignKeyConstraint(["lesson_id"], ["lessons.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["payment_id"], ["payments.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("payment_id", "lesson_id"),
    )
    op.create_index(
        "ix_payment_allocations_payment_id", "payment_allocations", ["payment_id"]
    )
    op.create_index(
        "ix_payment_allocations_lesson_id", "payment_allocations", ["lesson_id"]
    )


def downgrade() -> None:
    op.drop_table("payment_allocations")
    op.drop_table("payments")
    op.drop_constraint("ck_lessons_receivable_nonnegative", "lessons", type_="check")
    op.drop_constraint("ck_lessons_unit_price_nonnegative", "lessons", type_="check")
    op.drop_column("lessons", "receivable_override_reason")
    op.drop_column("lessons", "receivable_is_overridden")
    op.drop_column("lessons", "receivable_cents")
    op.drop_column("lessons", "unit_price_cents")
