"""sakatlık kayıtlarına kaynak alanı (api / manual)

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-20

Mevcut kayıtların hepsi elle girildiği için "manual" olur; otomatik güncelleme
(app/absences_sync.py) manual kayıtlara dokunmaz.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: Union[str, Sequence[str], None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("absences") as batch:
        batch.add_column(sa.Column("source", sa.String(length=10), nullable=False, server_default="manual"))


def downgrade() -> None:
    with op.batch_alter_table("absences") as batch:
        batch.drop_column("source")
