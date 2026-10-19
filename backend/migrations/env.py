"""Alembic ortamı: bağlantı adresi ve şema uygulamanın kendisinden gelir.

DATABASE_URL varsa Postgres (Neon), yoksa yerel SQLite (app/database.py).
Uygulama açılırken app/migrate.py run_migrations() bunu çağırır; elle de
`alembic upgrade head` ile çalıştırılabilir (backend klasöründe).
"""
import sys
from pathlib import Path

from alembic import context

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # backend/ (app paketi için)

from app import models  # noqa: E402,F401  (tabloları metadata'ya kaydeder)
from app.database import Base, engine  # noqa: E402

config = context.config
target_metadata = Base.metadata
# Not: logging.config.fileConfig bilerek çağrılmıyor; uygulama içinden çalışırken
# uvicorn'un log ayarlarını bozmasın.


def run_migrations_offline() -> None:
    context.configure(
        url=str(engine.url),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=engine.dialect.name == "sqlite",
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            # SQLite ALTER TABLE'ı sınırlı destekler; batch modu tabloyu güvenle yeniden kurar
            render_as_batch=connection.dialect.name == "sqlite",
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
