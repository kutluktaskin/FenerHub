"""SportsAPI cevaplarının önbelleği (api_cache tablosu).

Render'ın diski kalıcı olmadığı için önbellek veritabanında durur: sunucu uyuyup
uyandığında ya da yeniden deploy edildiğinde aynı veri tekrar çekilmez (kota korunur).

Anahtarlar:
  pages:next_0, pages:next_1, pages:last_0   takımın maç listesi sayfaları
  detail:<maç api id>:<tür>                  lineups | incidents | statistics | done
  standings                                  puan durumu tabloları
  player_stats                               oyuncu maç/gol/asist toplamları
  squad_raw                                  kadro cevabı
"""
import json
import time
from pathlib import Path

from .database import SessionLocal
from .models import ApiCache

BACKEND_DIR = Path(__file__).resolve().parent.parent


def get_with_time(key: str):
    """(veri, çekilme zamanı) döndürür; kayıt yoksa (None, 0)."""
    with SessionLocal() as session:
        row = session.get(ApiCache, key)
        if not row:
            return None, 0
        return json.loads(row.data), row.fetched_at


def get(key: str):
    return get_with_time(key)[0]


def age(key: str) -> float:
    """Kaydın yaşı (saniye). Kayıt yoksa sonsuz: 'süresi dolmuş' sayılır."""
    with SessionLocal() as session:
        row = session.get(ApiCache, key)
        return time.time() - row.fetched_at if row else float("inf")


def put(key: str, data, fetched_at: float | None = None) -> None:
    text = json.dumps(data, ensure_ascii=False)
    stamp = time.time() if fetched_at is None else fetched_at
    with SessionLocal() as session, session.begin():
        row = session.get(ApiCache, key)
        if row:
            row.data, row.fetched_at = text, stamp
        else:
            session.add(ApiCache(key=key, data=text, fetched_at=stamp))


def delete(key: str) -> None:
    with SessionLocal() as session, session.begin():
        row = session.get(ApiCache, key)
        if row:
            session.delete(row)


def seed_from_files() -> None:
    """Tablo boşsa eski önbellek dosyalarını (repoda duranlar) içe aktarır."""
    with SessionLocal() as session:
        if session.query(ApiCache.key).first():
            return

    def load(path: Path):
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    count = 0
    for f in sorted((BACKEND_DIR / "pages_fb").glob("*.json")):
        if (data := load(f)) is not None:
            put(f"pages:{f.stem}", data, f.stat().st_mtime)
            count += 1
    for f in sorted((BACKEND_DIR / "detail_cache").glob("*_*.json")):
        api_id, kind = f.stem.split("_", 1)
        if (data := load(f)) is not None:
            put(f"detail:{api_id}:{kind}", data, f.stat().st_mtime)
            count += 1
    for f in (BACKEND_DIR / "detail_cache").glob("*_done.flag"):
        put(f"detail:{f.name.split('_', 1)[0]}:done", True, f.stat().st_mtime)
        count += 1
    # Bu iki dosya çekilme zamanını kendi içinde tutar
    for name, key, field in (("standings_cache.json", "standings", "tables"),
                             ("player_stats_cache.json", "player_stats", "stats")):
        data = load(BACKEND_DIR / name)
        if data and field in data:
            put(key, data[field], data.get("fetched_at", 0))
            count += 1
    squad = BACKEND_DIR / "squad_raw.json"
    if (data := load(squad)) is not None:
        put("squad_raw", data, squad.stat().st_mtime)
        count += 1
    print(f"Önbellek dosyalardan veritabanına aktarıldı: {count} kayıt", flush=True)
