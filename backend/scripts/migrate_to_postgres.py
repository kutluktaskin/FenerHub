"""Tek seferlik aktarım: yerel SQLite verisi (+ sitedeki canlı forum mesajları) -> DATABASE_URL.

  # backend/.env içinde DATABASE_URL=postgresql://... (Neon) tanımlıyken, backend klasöründe:
  python scripts/migrate_to_postgres.py --dry-run          # sadece ne aktarılacağını gösterir
  python scripts/migrate_to_postgres.py                    # aktarır
  python scripts/migrate_to_postgres.py --no-prod-forum    # sitedeki forumu çekmeden

- Hedef şema önce Alembic ile kurulur (app/migrate.py).
- teams, players, matches, player_stats, absences, standings: id'ler korunur; hedefte aynı
  id zaten varsa o satır atlanır (tekrar çalıştırmak güvenli).
- Forum: yerel forum.db + sitedeki mesajlar (herkese açık /api/forum/posts, SportsAPI kotası
  harcamaz). İki kaynağın id'leri çakışabildiği için mesajlar yeniden numaralanır, yanıt
  bağlantıları eşlenir; aynı (oda, takma ad, zaman, metin) ikinci kez eklenmez.
  Sitedeki mesajların sahiplik anahtarı API'de olmadığından aktarılan mesajlarda "Sil" çıkmaz.
- seed.py ÇALIŞTIRILMAZ; hiçbir kaynak veri silinmez.
"""
import argparse
import os
import sqlite3
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
load_dotenv(BACKEND / ".env")

PROD_API = "https://fenerhub.onrender.com"
TABLE_ORDER = ["teams", "players", "matches", "player_stats", "absences", "standings"]


def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default=str(BACKEND / "fenerbahce.db"))
    ap.add_argument("--forum-db", default=str(BACKEND / "forum.db"))
    ap.add_argument("--prod-api", default=PROD_API)
    ap.add_argument("--no-prod-forum", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--allow-sqlite-target", action="store_true",
                    help="test için: DATABASE_URL bir SQLite dosyası olabilir")
    return ap.parse_args()


def main():
    args = parse_args()
    if not os.environ.get("DATABASE_URL"):
        sys.exit("DATABASE_URL tanımlı değil (backend/.env). Hedef olmadan aktarım yapılmaz.")

    from sqlalchemy import create_engine, func, insert, select, text
    from app import models
    from app.database import db_label, engine as target
    from app.migrate import run_migrations

    if target.dialect.name == "sqlite" and not args.allow_sqlite_target:
        sys.exit("Hedef SQLite görünüyor; Neon adresi bekleniyordu (test için --allow-sqlite-target).")
    if Path(args.source).resolve().as_posix() in str(target.url):
        sys.exit("Kaynak ve hedef aynı dosya.")

    print("Hedef:", db_label())
    if not args.dry_run:
        run_migrations()

    tables = models.Base.metadata.tables
    source = create_engine(f"sqlite:///{args.source}")

    # ---- Ana tablolar: id'ler korunur ----
    with source.connect() as src, target.begin() as dst:
        for name in TABLE_ORDER:
            table = tables[name]
            rows = [dict(r._mapping) for r in src.execute(select(table))]
            existing = set(dst.execute(select(table.c.id)).scalars()) if not args.dry_run else set()
            new = [r for r in rows if r["id"] not in existing]
            print(f"{name}: kaynakta {len(rows)}, eklenecek {len(new)}")
            if new and not args.dry_run:
                dst.execute(insert(table), new)
        # Postgres'te id sayaçlarını ileri al (yeni kayıtlar çakışmasın)
        if target.dialect.name == "postgresql" and not args.dry_run:
            for name in TABLE_ORDER + ["posts"]:
                dst.execute(text(
                    f"SELECT setval(pg_get_serial_sequence('{name}', 'id'), "
                    f"COALESCE((SELECT MAX(id) FROM {name}), 0) + 1, false)"))

    # ---- Forum: yerel forum.db + sitedeki mesajlar ----
    posts = []                       # (kaynak, eski_id, alanlar)
    if Path(args.forum_db).exists():
        con = sqlite3.connect(args.forum_db)
        con.row_factory = sqlite3.Row
        for r in con.execute("SELECT * FROM posts ORDER BY id"):
            posts.append(("yerel", r["id"], {
                "room": r["room"], "nick": r["nick"], "body": r["body"], "fire": r["fire"] or 0,
                "heart": r["heart"] or 0, "ts": r["ts"], "owner": r["owner"],
                "parent_id": r["parent_id"], "deleted": bool(r["deleted"])}))
        con.close()
    print(f"yerel forum.db: {len(posts)} mesaj")

    if not args.no_prod_forum:
        from app.forum import FIXTURES, ROOMS
        rooms = sorted(ROOMS) + ["mac-" + m["id"] for m in FIXTURES]
        prod = 0
        for room in rooms:
            try:
                r = requests.get(f"{args.prod_api}/api/forum/posts", params={"room": room, "limit": 100}, timeout=60)
                r.raise_for_status()
            except requests.RequestException as err:
                print(f"!! sitedeki '{room}' odası alınamadı ({err}); atlandı")
                continue
            for p in reversed(r.json()):                       # eskiden yeniye
                posts.append(("site", p["id"], {
                    "room": p["room"], "nick": p["nick"], "body": p["body"], "fire": p["fire"],
                    "heart": p["heart"], "ts": p["ts"], "owner": None,
                    "parent_id": p["parent_id"], "deleted": bool(p["deleted"])}))
                prod += 1
        print(f"sitedeki forum: {prod} mesaj ({len(rooms)} oda)")

    posts.sort(key=lambda x: (x[2]["ts"], x[1]))
    posts_t = tables["posts"]
    with target.begin() as dst:
        seen = set()
        if not args.dry_run:
            for row in dst.execute(select(posts_t.c.room, posts_t.c.nick, posts_t.c.ts, posts_t.c.body)):
                seen.add(tuple(row))
        id_map, added = {}, 0
        for src_name, old_id, fields in posts:
            key = (fields["room"], fields["nick"], fields["ts"], fields["body"])
            if key in seen:
                continue
            seen.add(key)
            parent = id_map.get((src_name, fields["parent_id"])) if fields["parent_id"] else None
            if args.dry_run:
                added += 1
                continue
            new_id = dst.execute(insert(posts_t).values(**{**fields, "parent_id": parent})
                                 .returning(posts_t.c.id)).scalar_one()
            id_map[(src_name, old_id)] = new_id
            added += 1
        print(f"posts: eklenecek {added}" if args.dry_run else f"posts: {added} mesaj eklendi")
        if not args.dry_run:
            total = dst.execute(select(func.count()).select_from(posts_t)).scalar()
            print(f"posts: hedefte toplam {total}")
    print("Bitti." if not args.dry_run else "Deneme bitti, hiçbir şey yazılmadı.")


if __name__ == "__main__":
    main()
