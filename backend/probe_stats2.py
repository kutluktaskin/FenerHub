"""/players/{id}/statistics cevabının yapısını kısaca yazar (sezon, turnuva, maç/gol/asist alanları).
Sonucu probe_out2.txt dosyasına yazar. API anahtarını yazmaz.
Kullanım: python probe_stats2.py
"""
import json
import os

import requests
from dotenv import load_dotenv

load_dotenv()
BASE = "https://api.sportsapipro.com/v2/football/api"
HEADERS = {"x-api-key": os.environ["SPORTS_API_KEY"], "User-Agent": "curl/8"}
KEEP = ("appearances", "matchesStarted", "goals", "assists", "minutesPlayed", "rating")

out = []


def log(text=""):
    print(text)
    out.append(text)


def shrink(obj, depth=0):
    """Büyük iç içe yapıyı küçültür: uzun alt nesneleri kısaltır."""
    if isinstance(obj, dict):
        if depth >= 3:
            return "{...}"
        return {k: shrink(v, depth + 1) for k, v in obj.items()}
    if isinstance(obj, list):
        return [shrink(v, depth + 1) for v in obj[:6]]
    return obj


with open("squad_raw.json", encoding="utf-8") as f:
    items = json.load(f)["data"]["players"]

wanted = []
for key in ("Kahveci", "Lukaku"):
    for it in items:
        if key in it["player"]["name"]:
            wanted.append(it["player"])
            break

for p in wanted:
    log(f"\n##### {p['name']} (id {p['id']}) #####")
    r = requests.get(f"{BASE}/players/{p['id']}/statistics", headers=HEADERS, timeout=30)
    log(f"durum: {r.status_code}")
    data = r.json().get("data", {})
    log("data anahtarları: " + ", ".join(data.keys()))
    seasons = data.get("seasons", [])
    log(f"sezon kaydı sayısı: {len(seasons)}")
    for i, s in enumerate(seasons[:8]):
        stats = s.get("statistics", {})
        small = {k: v for k, v in s.items() if k != "statistics"}
        log(f"\n-- kayıt {i} --")
        log("diğer alanlar: " + json.dumps(shrink(small), ensure_ascii=False)[:600])
        log("istatistik: " + json.dumps({k: stats.get(k) for k in KEEP}, ensure_ascii=False))

with open("probe_out2.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(out))
print("\nBitti. probe_out2.txt dosyasını aç, içindekini bana yapıştır.")