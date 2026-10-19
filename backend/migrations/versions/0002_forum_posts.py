"""forum mesajları ana veritabanında (eskiden ayrı forum.db)

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-20

Eski forum.db'deki mesajlar scripts/migrate_to_postgres.py ile aktarılır.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, Sequence[str], None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "posts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("room", sa.String(length=64), nullable=False),
        sa.Column("nick", sa.String(length=40), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("fire", sa.Integer(), server_default="0", nullable=False),
        sa.Column("heart", sa.Integer(), server_default="0", nullable=False),
        sa.Column("ts", sa.Integer(), nullable=False),
        sa.Column("owner", sa.String(length=64), nullable=True),
        sa.Column("parent_id", sa.Integer(), nullable=True),
        # sa.false(): SQLite'ta 0, Postgres'te false olarak yazılır
        sa.Column("deleted", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.ForeignKeyConstraint(["parent_id"], ["posts.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_posts_room_id", "posts", ["room", "id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_posts_room_id", table_name="posts")
    op.drop_table("posts")
