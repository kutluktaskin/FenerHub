"""Puan durumu endpoint'ini doğrular. Ham cevapları standings_*.json dosyasına kaydeder.
Sonucu probe_out4.txt dosyasına yazar. API anahtarını yazmaz.
Kullanım: python probe_standings.py
"""
import glob
import json
import os

import requests
from dotenv import load_dotenv

load_dotenv()
BASE = "https://api.sportsapipro.com/v2/football/api"
HEADERS = {"x-api-key": os.environ["SPORTS_API_KEY"], "User-Agent": "curl/8"}
SEASON_START = 1782864000  # 1 Temmuz 2026
TARGETS = {"Trendyol Süper Lig": "super_lig", "UEFA Champions League": "uefa"}

out = []


def log(text=""):
    print(text)
    out.append(text)


def get(path):
    r = requests.get(BASE + path, headers=HEADERS, timeout=30)
    log(f"\n{path} -> {r.status_code}")
    return r


# 1) Maç kayıtlarından turnuva ve sezon id'lerini bul
found = {}
for fn in glob.glob("pages_fb/*.json"):
    with open(fn, encoding="utf-8") as f:
        events = json.load(f)
    for e in events:
        if e.get("startTimestamp", 0) < SEASON_START:
            continue
        ut = (e.get("tournament") or {}).get("uniqueTournament") or {}
        name = ut.get("name", "")
        if name in TARGETS and name not in found:
            found[name] = {
                "tournament_id": ut.get("id"),
                "season_id": (e.get("season") or {}).get("id"),
            }

log("=== Bulunan id'ler ===")
log(json.dumps(found, ensure_ascii=False, indent=1))

for name, ids in found.items():
    t, s = ids["tournament_id"], ids["season_id"]
    key = TARGETS[name]
    log(f"\n##### {name} (turnuva {t}, sezon {s}) #####")

    # 2) Sezon listesi: bulunan sezon id'si listede var mı?
    r = get(f"/tournaments/{t}/seasons")
    if r.status_code == 200:
        seasons = (r.json().get("seasons")
                   or (r.json().get("data") or {}).get("seasons") or [])
        log("İlk 3 sezon: " + json.dumps(seasons[:3], ensure_ascii=False))
        log(f"Bulunan sezon ({s}) listede mi: {any(x.get('id') == s for x in seasons)}")
    else:
        log(r.text[:300])

    # 3) Puan durumu (doğru yol: tekil 'tournament' ve 'season')
    r = get(f"/tournament/{t}/season/{s}/standings")
    log(r.text[:600])
    if r.status_code == 200:
        with open(f"standings_{key}.json", "w", encoding="utf-8") as f:
            json.dump(r.json(), f, ensure_ascii=False, indent=1)
        log(f"   ^^^ ÇALIŞTI, standings_{key}.json dosyasına kaydedildi")

with open("probe_out4.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(out))
print("\nBitti. probe_out4.txt içeriğini bana yapıştır.")