"""Veritabanı bağlantısı.

DATABASE_URL ortam değişkeni varsa (Render'da Neon Postgres) onu, yoksa yerelde
backend/fenerbahce.db SQLite dosyasını kullanır. Şema Alembic ile yönetilir
(migrations/), uygulama açılırken run_migrations() en güncel sürüme getirir.

Not: Bu modül .env dosyasını kendisi okumaz. backend/.env içindeki DATABASE_URL'yi
sadece scripts/migrate_to_postgres.py kullanır; yerelde uygulama SQLite'ta kalır
(yanlışlıkla canlı veritabanına yazılmasın). Neon'a bağlanmak için değişkeni
kabukta açıkça ver.
"""
import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

BASE_DIR = Path(__file__).resolve().parent.parent
SQLITE_URL = f"sqlite:///{BASE_DIR / 'fenerbahce.db'}"


def database_url() -> str:
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        return SQLITE_URL
    # Neon/Heroku tarzı adresler psycopg 3 sürücüsüyle kullanılır
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


DATABASE_URL = database_url()
IS_SQLITE = DATABASE_URL.startswith("sqlite")

if IS_SQLITE:
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
else:
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,      # Neon boşta uyuyup bağlantıyı kapatabilir
        pool_recycle=300,
        pool_size=5,
        max_overflow=5,
        # Neon'un havuzlu (PgBouncer) bağlantısında sunucu tarafı hazır sorgular sorun çıkarır
        connect_args={"prepare_threshold": None},
    )

SessionLocal = sessionmaker(bind=engine, autoflush=False)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def db_label() -> str:
    """Loglar için: sadece veritabanı türü ve sunucu (kullanıcı adı/parola yazılmaz)."""
    return f"{engine.dialect.name} · {engine.url.host or engine.url.database}"
