"""Takım logolarını bir kez indirir: frontend/img/teams/{api_id}.png

  python download_logos.py            # eksik logoları indirir
  python download_logos.py --dry-run  # sadece kaç istek atılacağını gösterir
  python download_logos.py --keep 60  # kalan günlük kota 60'a inince dur (varsayılan 40)

Kota Render'daki otomatik senkronla ortak: kalan istek --keep değerine inince durur,
böylece maç günü canlı veri için pay kalır. Kota sıfırlandıktan sonra çalıştırmak en iyisi.

SportsAPI dokümanına göre logo istekleri (V2) API anahtarı ister ve günlük kotadan düşer;
logolar değişmediği için bir kez indirip saklamak önerilir. Bu script sadece eksik
dosyaları ister, ilk hatada durur. Takım listesi pages_fb sayfalarından okunur
(istek atmaz). Yeni rakipler geldikçe tekrar çalıştırılabilir.
"""
import json
import os
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()
ROOT = Path(__file__).resolve().parent
PAGES = ROOT / "pages_fb"
OUT = ROOT.parent / "frontend" / "img" / "teams"
URL = "https://api.sportsapipro.com/v2/football/images/teams/{id}"
FB_ID = 3052   # Fenerbahçe logosu zaten img/fenerbahce-logo.png


def team_ids():
    ids = {}
    for f in sorted(PAGES.glob("*.json")):
        for e in json.loads(f.read_text(encoding="utf-8")):
            for side in ("homeTeam", "awayTeam"):
                t = e.get(side) or {}
                if t.get("id") and t["id"] != FB_ID:
                    ids[t["id"]] = t.get("name")
    return ids


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    ids = team_ids()
    missing = {i: n for i, n in ids.items() if not (OUT / f"{i}.png").exists()}
    print(f"{len(ids)} takım, {len(missing)} logo eksik (her biri 1 istek).")
    if "--dry-run" in sys.argv or not missing:
        write_manifest()
        return
    keep = int(sys.argv[sys.argv.index("--keep") + 1]) if "--keep" in sys.argv else 40
    headers = {"x-api-key": os.environ["SPORTS_API_KEY"], "User-Agent": "curl/8"}
    for tid, name in missing.items():
        r = requests.get(URL.format(id=tid), headers=headers, timeout=30)
        ctype = r.headers.get("content-type", "")
        if r.status_code != 200 or not ctype.startswith("image/"):
            print(f"!! {name} ({tid}): HTTP {r.status_code} {ctype} — durduruldu.")
            break
        (OUT / f"{tid}.png").write_bytes(r.content)
        left = r.headers.get("x-ratelimit-remaining")
        print(f"   {name} ({tid}) {len(r.content) // 1024} KB · kalan kota: {left}")
        if left is not None and int(left) <= keep:
            print(f"Kalan kota {left} <= {keep}: senkron için durduruldu. Kalanlar sonra indirilebilir.")
            break
        time.sleep(0.3)
    write_manifest()


def write_manifest():
    # Sitede hangi logoların olduğunu söyler (api.js bunu okur; olmayan takım için renkli rozet)
    have = sorted(int(p.stem) for p in OUT.glob("*.png") if p.stem.isdigit())
    (OUT / "index.json").write_text(json.dumps(have), encoding="utf-8")
    print(f"index.json: {len(have)} logo")


if __name__ == "__main__":
    main()
