"""Uygulama açılırken veritabanı şemasını en güncel Alembic sürümüne getirir.

Render'ın ücretsiz planında komut satırı olmadığı için migration'lar burada çalışır;
başlatma komutunun değişmesi gerekmez. Veri silinmez:
- Alembic öncesi oluşturulmuş veritabanı (tablolar var, alembic_version yok) veriye
  dokunmadan 0001 olarak işaretlenir, sonra yeni migration'lar uygulanır.
- Boş veritabanında (yeni Neon) bütün tablolar oluşturulur.
"""
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

from .database import engine

BACKEND_DIR = Path(__file__).resolve().parent.parent
BASELINE = "0001"


def alembic_config() -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    return cfg


def run_migrations() -> None:
    cfg = alembic_config()
    tables = set(inspect(engine).get_table_names())
    if "alembic_version" not in tables and "teams" in tables:
        print("Veritabanı Alembic öncesinden: 0001 olarak işaretleniyor (veri değişmez)", flush=True)
        command.stamp(cfg, BASELINE)
    command.upgrade(cfg, "head")
    print(f"Veritabanı şeması güncel ({engine.dialect.name})", flush=True)
