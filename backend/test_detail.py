import os
import json
import requests
from dotenv import load_dotenv

load_dotenv()
BASE = "https://api.sportsapipro.com/v2/football/api"
HEADERS = {"x-api-key": os.environ["SPORTS_API_KEY"], "User-Agent": "curl/8"}
MID = 16483697  # Fenerbahçe - Alanyaspor

for name in ("incidents", "statistics", "lineups", "shotmap"):
    path = f"/match/{MID}/{name}"
    r = requests.get(BASE + path, headers=HEADERS, timeout=30)
    print(r.status_code, path, "|", r.text[:150].replace("\n", " "))
    if r.ok:
        with open(f"detail_{name}.json", "w", encoding="utf-8") as f:
            json.dump(r.json(), f, indent=2, ensure_ascii=False)