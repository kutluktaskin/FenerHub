"""skor tahmin oyunu ve maçın oyuncusu oylaması

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-21
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: Union[str, Sequence[str], None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "predictions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("match_id", sa.Integer(), nullable=False),
        sa.Column("player", sa.String(length=64), nullable=False),
        sa.Column("nick", sa.String(length=40), nullable=False),
        sa.Column("home", sa.Integer(), nullable=False),
        sa.Column("away", sa.Integer(), nullable=False),
        sa.Column("ts", sa.Integer(), nullable=False),
        sa.Column("points", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["match_id"], ["matches.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("match_id", "player", name="uq_predictions_match_player"),
    )
    op.create_index("ix_predictions_player", "predictions", ["player"])
    op.create_table(
        "motm_votes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("match_id", sa.Integer(), nullable=False),
        sa.Column("player", sa.String(length=64), nullable=False),
        sa.Column("choice", sa.String(length=80), nullable=False),
        sa.Column("ts", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["match_id"], ["matches.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("match_id", "player", name="uq_motm_match_player"),
    )


def downgrade() -> None:
    op.drop_table("motm_votes")
    op.drop_index("ix_predictions_player", table_name="predictions")
    op.drop_table("predictions")
