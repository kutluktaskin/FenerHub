"""SportsAPI önbelleği veritabanında (eskiden diskteki JSON dosyaları)

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-20

Tablo boşsa uygulama açılırken repodaki eski önbellek dosyaları içe aktarılır
(app/cache.py seed_from_files), ilk açılışta istek harcanmasın.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: Union[str, Sequence[str], None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "api_cache",
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column("data", sa.Text(), nullable=False),
        sa.Column("fetched_at", sa.Float(), nullable=False),
        sa.PrimaryKeyConstraint("key"),
    )


def downgrade() -> None:
    op.drop_table("api_cache")
