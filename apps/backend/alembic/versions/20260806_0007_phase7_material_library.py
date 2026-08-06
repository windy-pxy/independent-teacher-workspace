"""Create Phase 7 material text chunks and optimistic versioning.

Revision ID: 20260806_0007
Revises: 20260805_0006
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260806_0007"
down_revision: str | None = "20260805_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "uploaded_materials",
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
    )
    op.create_table(
        "material_chunks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("material_id", sa.Uuid(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("source_locator", sa.String(length=100), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("char_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("chunk_index >= 0", name="ck_material_chunks_index_nonnegative"),
        sa.CheckConstraint("char_count > 0", name="ck_material_chunks_chars_positive"),
        sa.ForeignKeyConstraint(
            ["material_id"], ["uploaded_materials.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("material_id", "chunk_index"),
    )
    op.create_index("ix_material_chunks_material_id", "material_chunks", ["material_id"])
    op.create_index(
        "ix_material_chunks_material_order",
        "material_chunks",
        ["material_id", "chunk_index"],
    )


def downgrade() -> None:
    op.drop_table("material_chunks")
    op.drop_column("uploaded_materials", "version")
