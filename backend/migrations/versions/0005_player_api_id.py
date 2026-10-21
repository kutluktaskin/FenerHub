"""oyunculara SportsAPI kimliği (fotoğraf eşleşmesi için)

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-21

Değer kadro senkronunda (sync.sync_squad) ve açılışta önbellekteki kadro cevabından
(sync.fill_player_ids, istek atmaz) doldurulur.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: Union[str, Sequence[str], None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("players") as batch:
        batch.add_column(sa.Column("api_id", sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("players") as batch:
        batch.drop_column("api_id")
