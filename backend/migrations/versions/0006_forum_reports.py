"""forum: mesaj bildirme (3 farklı kullanıcı bildirince mesaj gizlenir)

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-21
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: Union[str, Sequence[str], None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("posts") as batch:
        batch.add_column(sa.Column("hidden", sa.Boolean(), server_default=sa.false(), nullable=False))
    op.create_table(
        "post_reports",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("post_id", sa.Integer(), nullable=False),
        sa.Column("reporter", sa.String(length=64), nullable=False),
        sa.Column("ts", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["post_id"], ["posts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("post_id", "reporter", name="uq_post_reports_post_reporter"),
    )


def downgrade() -> None:
    op.drop_table("post_reports")
    with op.batch_alter_table("posts") as batch:
        batch.drop_column("hidden")
