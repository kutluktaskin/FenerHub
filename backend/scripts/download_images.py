"""Takım logolarını ve oyuncu fotoğraflarını bir kez indirir (siteye statik dosya olarak girer).

  python -m scripts.download_images              # eksikleri indirir (backend klasöründe)
  python -m scripts.download_images --dry-run    # sadece neyin eksik olduğunu gösterir
  python -m scripts.download_images --max 15     # bu çalışmada en fazla 15 görsel (varsayılan 15)
  python -m scripts.download_images --keep 40    # kalan günlük kota 40'a inince dur (varsayılan 40)

Çıktı: frontend/img/teams/<takım api id>.png ve frontend/img/players/<oyuncu api id>.png,
her klasörde index.json (sitede hangi görsellerin olduğunu söyler; olmayana rozet/avatar).
Her görsel 1 istek ve kota Render'daki otomatik senkronla ortak: --max ve --keep ile günlük
bütçe (%60) korunur. Kota her gece 03:00 TSİ yenilenir; birkaç güne yayarak çalıştırın.

Öncelik: önce en yakın tarihli rakiplerin logoları, sonra Fenerbahçe kadrosunun fotoğrafları,
sonra geçmiş rakipler. Takım listesi önbellekteki maç sayfalarından, oyuncular veritabanından
okunur (istek atmaz). Sadece eksik dosyalar istenir; ilk hatada durur.
"""
import json
import os
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

from app import cache, models
from app.database import SessionLocal

load_dotenv()
BACKEND = Path(__file__).resolve().parents[1]
IMG = BACKEND.parent / "frontend" / "img"
TEAMS, PLAYERS = IMG / "teams", IMG / "players"
URLS = {
    "team": "https://api.sportsapipro.com/v2/football/images/teams/{id}",
    "player": "https://api.sportsapipro.com/v2/football/images/players/{id}",
}
FB_ID = 3052   # Fenerbahçe logosu zaten img/fenerbahce-logo.png


def opponents():
    """Rakipler: önce gelecek maçlar (en yakın önce), sonra geçmiş maçlar (en yeni önce)."""
    events = {}
    for name in ("next_0", "next_1", "last_0"):
        for e in cache.get(f"pages:{name}") or []:
            events[e["id"]] = e
    now = time.time()
    future = sorted((e for e in events.values() if e.get("startTimestamp", 0) >= now), key=lambda e: e["startTimestamp"])
    past = sorted((e for e in events.values() if e.get("startTimestamp", 0) < now), key=lambda e: -e["startTimestamp"])
    out = {}
    for e in future + past:
        for side in ("homeTeam", "awayTeam"):
            t = e.get(side) or {}
            if t.get("id") and t["id"] != FB_ID and t["id"] not in out:
                out[t["id"]] = (t.get("name"), e.get("startTimestamp", 0) >= now)
    return out


def squad():
    with SessionLocal() as db:
        return {p.api_id: p.name for p in db.query(models.Player).filter(models.Player.api_id.is_not(None))}


def queue():
    """(tür, id, ad) sırası: gelecek rakipler, kadro, geçmiş rakipler; sadece eksik olanlar."""
    teams = opponents()
    upcoming = [("team", i, n) for i, (n, fut) in teams.items() if fut]
    past = [("team", i, n) for i, (n, fut) in teams.items() if not fut]
    players = [("player", i, n) for i, n in squad().items()]
    folder = {"team": TEAMS, "player": PLAYERS}
    return [q for q in upcoming + players + past if not (folder[q[0]] / f"{q[1]}.png").exists()]


def arg(name, default):
    return int(sys.argv[sys.argv.index(name) + 1]) if name in sys.argv else default


def main():
    TEAMS.mkdir(parents=True, exist_ok=True)
    PLAYERS.mkdir(parents=True, exist_ok=True)
    todo = queue()
    print(f"Eksik görsel: {len(todo)} (her biri 1 istek). İlk 5: {[(k, n) for k, _, n in todo[:5]]}")
    if "--dry-run" in sys.argv or not todo:
        write_manifests()
        return
    limit, keep = arg("--max", 15), arg("--keep", 40)
    headers = {"x-api-key": os.environ["SPORTS_API_KEY"], "User-Agent": "curl/8"}
    folder = {"team": TEAMS, "player": PLAYERS}
    done = 0
    for kind, pid, name in todo[:limit]:
        r = requests.get(URLS[kind].format(id=pid), headers=headers, timeout=30)
        ctype = r.headers.get("content-type", "")
        left = r.headers.get("x-ratelimit-remaining")
        if r.status_code != 200 or not ctype.startswith("image/"):
            print(f"!! {name} ({kind} {pid}): HTTP {r.status_code} {ctype} · kalan kota: {left} — durduruldu.")
            break
        (folder[kind] / f"{pid}.png").write_bytes(r.content)
        done += 1
        print(f"   {kind:6} {name} ({pid}) {len(r.content) // 1024} KB · kalan kota: {left}")
        if left is not None and int(left) <= keep:
            print(f"Kalan kota {left} <= {keep}: günlük bütçe için durduruldu.")
            break
        time.sleep(0.3)
    print(f"Bu çalışmada {done} görsel indirildi; kalan eksik: {len(todo) - done}")
    write_manifests()


def write_manifests():
    # Sitede hangi görsellerin olduğunu söyler (api.js okur; olmayana rozet / baş harfli avatar)
    for folder in (TEAMS, PLAYERS):
        have = sorted(int(p.stem) for p in folder.glob("*.png") if p.stem.isdigit())
        (folder / "index.json").write_text(json.dumps(have), encoding="utf-8")
        print(f"{folder.name}/index.json: {len(have)} görsel")


if __name__ == "__main__":
    main()
