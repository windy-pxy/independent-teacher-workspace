"""Allow independent teachers and persist authentication rate limits."""

import sqlalchemy as sa

from alembic import op

revision = "20260910_0008"
down_revision = "20260806_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("uq_users_single_active", table_name="users")
    op.add_column("users", sa.Column("recovery_code_hash", sa.String(64), nullable=True))
    op.add_column(
        "users",
        sa.Column("ai_access_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.alter_column("users", "ai_access_enabled", server_default=sa.false())
    op.create_table(
        "auth_rate_limits",
        sa.Column("key_hash", sa.String(64), primary_key=True),
        sa.Column("window_start", sa.BigInteger(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
    )


def downgrade() -> None:
    count = op.get_bind().scalar(sa.text("SELECT count(*) FROM users WHERE is_active = true"))
    if count and count > 1:
        raise RuntimeError("Cannot restore single-teacher constraint with multiple active accounts")
    op.create_index(
        "uq_users_single_active",
        "users",
        ["is_active"],
        unique=True,
        postgresql_where=sa.text("is_active = true"),
    )
    op.drop_table("auth_rate_limits")
    op.drop_column("users", "ai_access_enabled")
    op.drop_column("users", "recovery_code_hash")
