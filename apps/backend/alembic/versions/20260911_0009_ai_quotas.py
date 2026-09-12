"""Add bounded monthly AI usage for each independent teacher."""

import sqlalchemy as sa

from alembic import op

revision = "20260911_0009"
down_revision = "20260910_0008"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column("users", sa.Column("privacy_notice_version", sa.String(20), nullable=True))
    op.add_column(
        "users",
        sa.Column("privacy_accepted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("users", sa.Column("deletion_requested_at", sa.DateTime(timezone=True)))
    op.add_column("users", sa.Column("deletion_scheduled_for", sa.DateTime(timezone=True)))
    op.add_column(
        "users",
        sa.Column("ai_monthly_job_limit", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_check_constraint(
        "ck_users_ai_monthly_job_limit_nonnegative",
        "users",
        "ai_monthly_job_limit >= 0",
    )
    op.execute(
        sa.text("UPDATE users SET ai_monthly_job_limit = 200 WHERE ai_access_enabled = true")
    )
    op.create_table(
        "ai_usage_months",
        sa.Column(
            "owner_user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("month_key", sa.String(7), primary_key=True),
        sa.Column("job_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("input_tokens", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("job_count >= 0", name="ck_ai_usage_job_count_nonnegative"),
        sa.CheckConstraint("input_tokens >= 0", name="ck_ai_usage_input_tokens_nonnegative"),
        sa.CheckConstraint("output_tokens >= 0", name="ck_ai_usage_output_tokens_nonnegative"),
    )


def downgrade() -> None:
    op.drop_table("ai_usage_months")
    op.drop_constraint("ck_users_ai_monthly_job_limit_nonnegative", "users", type_="check")
    op.drop_column("users", "ai_monthly_job_limit")
    op.drop_column("users", "privacy_accepted_at")
    op.drop_column("users", "privacy_notice_version")
    op.drop_column("users", "deletion_scheduled_for")
    op.drop_column("users", "deletion_requested_at")
