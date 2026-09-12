"""Require bounded invitation codes for production registration."""

import sqlalchemy as sa

from alembic import op

revision = "20260912_0010"
down_revision = "20260911_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "registration_invites",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("code_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("label", sa.String(100), nullable=False),
        sa.Column("max_uses", sa.Integer(), nullable=False),
        sa.Column("uses_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("max_uses > 0", name="ck_registration_invites_max_uses_positive"),
        sa.CheckConstraint(
            "uses_count >= 0 AND uses_count <= max_uses",
            name="ck_registration_invites_uses_valid",
        ),
    )
    op.create_index(
        "ix_registration_invites_expires_at", "registration_invites", ["expires_at"]
    )
    op.add_column("users", sa.Column("registration_invite_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_users_registration_invite_id",
        "users",
        "registration_invites",
        ["registration_invite_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_users_registration_invite_id", "users", ["registration_invite_id"])


def downgrade() -> None:
    op.drop_index("ix_users_registration_invite_id", table_name="users")
    op.drop_constraint("fk_users_registration_invite_id", "users", type_="foreignkey")
    op.drop_column("users", "registration_invite_id")
    op.drop_index("ix_registration_invites_expires_at", table_name="registration_invites")
    op.drop_table("registration_invites")
