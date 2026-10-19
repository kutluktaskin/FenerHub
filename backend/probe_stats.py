"""Oyuncu istatistiği endpoint'ini bulmak için birkaç adresi dener.
Sonucu probe_out.txt dosyasına yazar. API anahtarını dosyaya YAZMAZ.
Kullanım: python probe_stats.py
"""
import json
import os

import requests
from dotenv import load_dotenv

load_dotenv()
BASE = "https://api.sportsapipro.com/v2/football/api"
FB_ID = 3052
HEADERS = {"x-api-key": os.environ["SPORTS_API_KEY"], "User-Agent": "curl/8"}

out = []


def log(text=""):
    print(text)
    out.append(text)


if os.path.exists("squad_raw.json"):
    with open("squad_raw.json", encoding="utf-8") as f:
        items = json.load(f)["data"]["players"]
else:
    print("squad_raw.json yok, kadro API'den çekiliyor (1 istek)...")
    r = requests.get(f"{BASE}/teams/{FB_ID}/players", headers=HEADERS, timeout=30)
    print("Kadro isteği:", r.status_code)
    r.raise_for_status()
    data = r.json()
    with open("squad_raw.json", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    items = data["data"]["players"]

log("=== squad_raw.json: ilk oyuncu ===")
log(json.dumps(items[0], ensure_ascii=False, indent=1)[:1500])

pid = items[0]["player"].get("id")
log(f"\nDeneme için oyuncu id: {pid}")

paths = [
    f"/players/{pid}",
    f"/players/{pid}/statistics",
    f"/players/{pid}/stats",
    f"/players/{pid}/statistics/seasons",
    f"/players/{pid}/events/last/0",
    f"/teams/{FB_ID}/statistics",
    f"/teams/{FB_ID}/top-players",
    f"/teams/{FB_ID}/players/statistics",
]

for path in paths:
    try:
        r = requests.get(BASE + path, headers=HEADERS, timeout=30)
        log(f"\n=== {path} -> {r.status_code} ===")
        log(r.text[:700])
    except Exception as err:
        log(f"\n=== {path} -> HATA: {err} ===")

with open("probe_out.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(out))
print("\nBitti. probe_out.txt dosyasını aç, içindekini bana yapıştır.")